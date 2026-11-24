#!/usr/bin/env python3
"""cpm_check.py -- 关键路径计算与可行性机器裁定（裁定门）。

输入经 plan_compile.py 通过的计划 JSON，执行：
  1. 前向 pass：ES = max(earliest_start_month-1, 前置任务 EF 最大值)，
     EF = ES + 人日/(21*assigned_workers)；
  2. 后向 pass：LF = min(后继 LS, 项目工期)，总时差 slack = LS - ES；
  3. 关键路径：slack≈0 的最长链；总工期(月) vs period_months，
     超期 fail 并给出超出量与压缩建议（关键路径上 parallelizable/
     trimmable 任务）；
  4. 经费：逐月均匀摊销、累计 vs total_budget_cny，超支 fail；
  5. 人力：逐月各角色 assigned_workers 合计 vs staff 编制，超载月份 fail；
  6. 窗口：requires_window 任务的执行区间必须整体落入可得性窗口；
  7. 可并行任务组：最早开始月相同、相互无依赖传递的任务组。

全部判定写入 feasibility_report.json。

用法:
    python3 cpm_check.py PLAN_JSON OUT_JSON
退出码: 0=可行(feasible=true); 1=不可行(已裁定 fail); 2=用法/结构错误
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plan_compile import validate_plan  # noqa: E402

WORK_DAYS_PER_MONTH = 21
EPS = 1e-9


def active_months(es, ef):
    """任务执行的月份列表（1 起算，月 m 覆盖区间 [m-1, m)）。"""
    import math
    return list(range(int(math.floor(es + EPS)) + 1,
                      int(math.ceil(ef - EPS)) + 1))


def compute(plan):
    cons = plan["constraints"]
    staff = cons["staff"]
    tasks = {t["id"]: t for t in plan["tasks"]}
    ids = [t["id"] for t in plan["tasks"]]
    deps = {t["id"]: list(t.get("depends_on", [])) for t in plan["tasks"]}

    # 拓扑序（Kahn）；有环时由 validate_plan 拦截，此处防御性报错
    indeg = {t: len(deps[t]) for t in ids}
    queue = [t for t in ids if indeg[t] == 0]
    topo = []
    while queue:
        u = queue.pop(0)
        topo.append(u)
        for v in ids:
            if u in deps[v]:
                indeg[v] -= 1
                if indeg[v] == 0:
                    queue.append(v)
    if len(topo) != len(ids):
        raise ValueError("dependency graph is not a DAG")

    dur, workers = {}, {}
    for t in ids:
        aw = tasks[t].get("assigned_workers", 1)
        workers[t] = aw
        dur[t] = tasks[t]["duration_person_days"] / (WORK_DAYS_PER_MONTH * aw)

    # 前向 pass
    es, ef = {}, {}
    for t in topo:
        lo = tasks[t].get("earliest_start_month", 1) - 1
        es[t] = max([lo] + [ef[d] for d in deps[t]])
        ef[t] = es[t] + dur[t]
    duration = max(ef.values())

    # 后向 pass
    succ = {t: [] for t in ids}
    for t in ids:
        for d in deps[t]:
            succ[d].append(t)
    lf, ls = {}, {}
    for t in reversed(topo):
        lf[t] = min([duration] + [ls[s] for s in succ[t]])
        ls[t] = lf[t] - dur[t]
    slack = {t: ls[t] - es[t] for t in ids}

    # 关键路径：从 EF 最大的零时差任务回溯
    end = max(ids, key=lambda t: ef[t])
    path = [end]
    while True:
        cur = path[0]
        prev = [d for d in deps[cur]
                if abs(ef[d] - es[cur]) < EPS and abs(slack[d]) < EPS]
        if not prev:
            break
        path.insert(0, max(prev, key=lambda d: ef[d]))
    critical_tasks = sorted([t for t in ids if abs(slack[t]) < EPS],
                            key=lambda t: es[t])

    # 压缩建议：关键路径上可并行/可裁剪任务
    suggestions = []
    for t in critical_tasks:
        tk = tasks[t]
        if tk.get("parallelizable") and workers[t] < staff[tk["required_role"]]:
            new_dur = tk["duration_person_days"] / (
                WORK_DAYS_PER_MONTH * staff[tk["required_role"]])
            suggestions.append({
                "task_id": t, "kind": "parallelize",
                "detail": "可由 %d 人分摊（%s 编制 %d），工期 %.1f -> %.1f 月；"
                          "须先消除并行后的人力超载" % (
                              staff[tk["required_role"]], tk["required_role"],
                              staff[tk["required_role"]], dur[t], new_dur)})
        if tk.get("trimmable"):
            suggestions.append({
                "task_id": t, "kind": "trim_scope",
                "detail": "范围可裁剪（如缩减样本量/降低指标档位），"
                          "当前 %.1f 月位于关键路径" % dur[t]})

    # 逐月经费与人力
    n_months = int(duration + 1 - EPS) + 1
    monthly_spend = [0.0] * (n_months + 1)
    monthly_staff = {r: [0] * (n_months + 1) for r in staff}
    for t in ids:
        months = active_months(es[t], ef[t])
        per = tasks[t]["cost_cny"] / max(len(months), 1)
        for m in months:
            monthly_spend[m] += per
            monthly_staff[tasks[t]["required_role"]][m] += workers[t]
    total_cost = sum(tasks[t]["cost_cny"] for t in ids)
    budget = cons["total_budget_cny"]
    cum, budget_monthly = 0.0, []
    for m in range(1, n_months + 1):
        cum += monthly_spend[m]
        budget_monthly.append({"month": m,
                               "spend_cny": round(monthly_spend[m], 2),
                               "cumulative_cny": round(cum, 2)})
    over_budget = total_cost > budget + EPS

    overloaded = []
    staffing_monthly = []
    for m in range(1, n_months + 1):
        row = {"month": m}
        for role in staff:
            req = monthly_staff[role][m]
            row[role] = req
            if req > staff[role]:
                overloaded.append({"month": m, "role": role,
                                   "required": req,
                                   "available": staff[role]})
        staffing_monthly.append(row)

    # 窗口违例
    windows = cons.get("resource_windows", {})
    window_violations = []
    for t in ids:
        wname = tasks[t].get("requires_window")
        if not wname:
            continue
        lo, hi = windows[wname]
        start_month = int(es[t]) + 1
        if start_month < lo - EPS or ef[t] > hi + EPS:
            window_violations.append({
                "task_id": t, "window": wname,
                "task_span_months": [start_month, round(ef[t], 2)],
                "window_months": [lo, hi]})

    # 可并行任务组：同 ES 且无依赖传递
    reachable = {t: set() for t in ids}
    for t in ids:
        stack = list(deps[t])
        while stack:
            u = stack.pop()
            if u not in reachable[t]:
                reachable[t].add(u)
                stack.extend(deps[u])
    by_es = {}
    for t in ids:
        by_es.setdefault(round(es[t], 6), []).append(t)
    parallel_groups = []
    for k in sorted(by_es):
        grp = by_es[k]
        if len(grp) < 2:
            continue
        indep = all(b not in reachable[a] and a not in reachable[b]
                    for i, a in enumerate(grp) for b in grp[i + 1:])
        if indep:
            parallel_groups.append({"start_month": round(k + 1, 2),
                                    "tasks": sorted(grp)})

    period = cons["period_months"]
    over_schedule = duration > period + EPS
    over_by = round(duration - period, 2) if over_schedule else 0.0
    feasible = not (over_schedule or over_budget or overloaded
                    or window_violations)
    verdicts = []
    verdicts.append("超期：总工期 %.1f 月 > 周期 %s 月，超出 %.1f 月"
                    % (duration, period, over_by) if over_schedule else
                    "周期：总工期 %.1f 月 <= 周期 %s 月" % (duration, period))
    verdicts.append("超支：计划经费 %d 元 > 预算 %d 元" % (total_cost, budget)
                    if over_budget else
                    "经费：计划 %d 元 <= 预算 %d 元" % (total_cost, budget))
    verdicts.append("人力超载 %d 个月份" % len(overloaded) if overloaded
                    else "人力：各月需求均在编制内")
    verdicts.append("窗口违例 %d 项" % len(window_violations)
                    if window_violations else "窗口：资源可得性均满足")

    report = {
        "plan_id": plan.get("plan_id"),
        "feasible": feasible,
        "period_months": period,
        "project_duration_months": round(duration, 2),
        "over_schedule": over_schedule,
        "over_by_months": over_by,
        "critical_path": path,
        "critical_tasks": critical_tasks,
        "tasks": [{"id": t, "name": tasks[t]["name"],
                   "duration_months": round(dur[t], 2),
                   "assigned_workers": workers[t],
                   "es_month": round(es[t], 2), "ef_month": round(ef[t], 2),
                   "ls_month": round(ls[t], 2), "lf_month": round(lf[t], 2),
                   "slack_months": round(slack[t], 2)} for t in ids],
        "compression_suggestions": suggestions,
        "budget": {"total_planned_cny": total_cost, "budget_cny": budget,
                   "over_budget": over_budget, "monthly": budget_monthly},
        "staffing": {"staff": staff, "monthly": staffing_monthly,
                     "overloaded_months": overloaded},
        "window_violations": window_violations,
        "parallel_groups": parallel_groups,
        "verdicts": verdicts,
    }
    return report


def main(argv):
    if len(argv) != 3:
        sys.stderr.write(__doc__)
        return 2
    plan_path, out_path = argv[1], argv[2]
    try:
        with open(plan_path, encoding="utf-8") as f:
            plan = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.stderr.write("cpm_check: 无法读取计划: %s\n" % e)
        return 2
    problems, _ = validate_plan(plan)
    if problems:
        sys.stderr.write("cpm_check: 计划未通过编译门（%d 个问题），"
                         "先运行 plan_compile.py 修复\n" % len(problems))
        return 2
    try:
        report = compute(plan)
    except ValueError as e:
        sys.stderr.write("cpm_check: %s\n" % e)
        return 2
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({
        "feasible": report["feasible"],
        "duration_months": report["project_duration_months"],
        "period_months": report["period_months"],
        "critical_path": report["critical_path"],
        "overloaded_months": len(report["staffing"]["overloaded_months"]),
        "over_budget": report["budget"]["over_budget"],
    }, ensure_ascii=False))
    return 0 if report["feasible"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
