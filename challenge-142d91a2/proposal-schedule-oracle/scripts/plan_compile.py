#!/usr/bin/env python3
"""plan_compile.py -- 阶段计划 JSON 的结构校验与依赖图 DAG 检测（编译门）。

校验项（任一命中即 valid=false，退出码 1，计划不得进入 CPM 裁定）：
  - 顶层结构：plan_id / constraints / tasks / milestones 齐备；
  - 资源约束：period_months>0、staff 角色->正整数、total_budget_cny>0、
    resource_windows 窗口区间 [起,止] 合法；
  - 任务字段：id 唯一、必填字段齐全、duration_person_days>0、
    required_role 有编制、assigned_workers 不超过该角色编制、
    requires_window 已声明、earliest_start_month>=1；
  - 依赖图：无悬空依赖（dangling_dependency）、无环（dependency_cycle，
    报告环路径）；
  - 里程碑：id 唯一、挂接任务存在、deliverable 与 assessment 非空。

用法:
    python3 plan_compile.py PLAN_JSON OUT_JSON
退出码: 0=校验通过; 1=存在问题(已拦截); 2=用法或文件错误
"""
import json
import sys

TASK_REQUIRED = ["id", "name", "duration_person_days", "depends_on",
                 "required_role", "cost_cny"]
MLS_REQUIRED = ["id", "task_id", "deliverable", "assessment"]


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def find_cycles(task_ids, deps):
    """三色 DFS 检测依赖环，返回环路径列表（元素为 id 列表）。"""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {t: WHITE for t in task_ids}
    cycles, stack = [], []

    def dfs(u):
        color[u] = GRAY
        stack.append(u)
        for v in deps.get(u, []):
            if v not in color:
                continue
            if color[v] == GRAY:
                cycles.append(stack[stack.index(v):] + [v])
            elif color[v] == WHITE:
                dfs(v)
        stack.pop()
        color[u] = BLACK

    for t in task_ids:
        if color[t] == WHITE:
            dfs(t)
    return cycles


def validate_plan(plan):
    """返回 (problems, cycles)。problems 元素: {kind, ...详情}。"""
    problems = []
    if not isinstance(plan, dict):
        return [{"kind": "not_an_object"}], []

    for key in ("plan_id", "constraints", "tasks", "milestones"):
        if key not in plan:
            problems.append({"kind": "missing_top_level", "field": key})
    if problems:
        return problems, []

    # ---- 资源约束 ----
    cons = plan["constraints"]
    if not isinstance(cons, dict):
        return [{"kind": "constraints_not_object"}], []
    if not _num(cons.get("period_months")) or cons["period_months"] <= 0:
        problems.append({"kind": "bad_constraint", "field": "period_months"})
    staff = cons.get("staff")
    if not isinstance(staff, dict) or not staff:
        problems.append({"kind": "bad_constraint", "field": "staff"})
        staff = {}
    else:
        for role, n in staff.items():
            if not isinstance(n, int) or n <= 0:
                problems.append({"kind": "bad_staff_count", "role": role,
                                 "value": n})
    if not _num(cons.get("total_budget_cny")) or cons["total_budget_cny"] <= 0:
        problems.append({"kind": "bad_constraint", "field": "total_budget_cny"})
    windows = cons.get("resource_windows", {})
    if not isinstance(windows, dict):
        problems.append({"kind": "bad_constraint", "field": "resource_windows"})
        windows = {}
    else:
        for name, win in windows.items():
            if (not isinstance(win, list) or len(win) != 2
                    or not all(_num(x) for x in win) or win[0] > win[1]):
                problems.append({"kind": "bad_window", "window": name})

    # ---- 任务 ----
    tasks = plan["tasks"]
    if not isinstance(tasks, list) or not tasks:
        problems.append({"kind": "tasks_empty"})
        tasks = []
    ids, deps = [], {}
    seen = set()
    for i, t in enumerate(tasks):
        label = t.get("id", "tasks[%d]" % i) if isinstance(t, dict) \
            else "tasks[%d]" % i
        if not isinstance(t, dict):
            problems.append({"kind": "task_not_object", "task": label})
            continue
        for f in TASK_REQUIRED:
            if f not in t:
                problems.append({"kind": "missing_field", "task": label,
                                 "field": f})
        tid = t.get("id")
        if tid is not None:
            if tid in seen:
                problems.append({"kind": "duplicate_task_id", "task": tid})
            seen.add(tid)
            ids.append(tid)
            d = t.get("depends_on", [])
            deps[tid] = d if isinstance(d, list) else []
            if not isinstance(d, list):
                problems.append({"kind": "bad_field_type", "task": tid,
                                 "field": "depends_on"})
        if _num(t.get("duration_person_days")):
            if t["duration_person_days"] <= 0:
                problems.append({"kind": "bad_field_value", "task": label,
                                 "field": "duration_person_days"})
        elif "duration_person_days" in t:
            problems.append({"kind": "bad_field_type", "task": label,
                             "field": "duration_person_days"})
        if "cost_cny" in t and (
                not _num(t["cost_cny"]) or t["cost_cny"] < 0):
            problems.append({"kind": "bad_field_value", "task": label,
                             "field": "cost_cny"})
        role = t.get("required_role")
        if role is not None and role not in staff:
            problems.append({"kind": "role_not_staffed", "task": label,
                             "role": role})
        aw = t.get("assigned_workers", 1)
        if not isinstance(aw, int) or aw <= 0:
            problems.append({"kind": "bad_field_value", "task": label,
                             "field": "assigned_workers"})
        elif role in staff and aw > staff[role]:
            problems.append({"kind": "workers_exceed_staff", "task": label,
                             "assigned": aw, "staffed": staff[role]})
        es = t.get("earliest_start_month", 1)
        if not _num(es) or es < 1:
            problems.append({"kind": "bad_field_value", "task": label,
                             "field": "earliest_start_month"})
        win = t.get("requires_window")
        if win is not None and win not in windows:
            problems.append({"kind": "unknown_window", "task": label,
                             "window": win})

    # ---- 依赖图：悬空 + 环 ----
    for tid, dlist in deps.items():
        for d in dlist:
            if d not in seen:
                problems.append({"kind": "dangling_dependency", "task": tid,
                                 "depends_on": d})
    cycles = find_cycles(ids, deps)
    for cyc in cycles:
        problems.append({"kind": "dependency_cycle", "cycle": cyc})

    # ---- 里程碑 ----
    mss = plan["milestones"]
    if not isinstance(mss, list):
        problems.append({"kind": "milestones_not_list"})
        mss = []
    mseen = set()
    for i, m in enumerate(mss):
        label = m.get("id", "milestones[%d]" % i) if isinstance(m, dict) \
            else "milestones[%d]" % i
        if not isinstance(m, dict):
            problems.append({"kind": "milestone_not_object", "milestone": label})
            continue
        for f in MLS_REQUIRED:
            if f not in m:
                problems.append({"kind": "missing_field", "milestone": label,
                                 "field": f})
        mid = m.get("id")
        if mid is not None:
            if mid in mseen:
                problems.append({"kind": "duplicate_milestone_id",
                                 "milestone": mid})
            mseen.add(mid)
        if m.get("task_id") is not None and m["task_id"] not in seen:
            problems.append({"kind": "milestone_bad_task", "milestone": label,
                             "task_id": m["task_id"]})
        if "deliverable" in m and not str(m.get("deliverable") or "").strip():
            problems.append({"kind": "milestone_no_deliverable",
                             "milestone": label})
        if "assessment" in m and not str(m.get("assessment") or "").strip():
            problems.append({"kind": "milestone_no_assessment",
                             "milestone": label})
    return problems, cycles


def main(argv):
    if len(argv) != 3:
        sys.stderr.write(__doc__)
        return 2
    plan_path, out_path = argv[1], argv[2]
    try:
        with open(plan_path, encoding="utf-8") as f:
            plan = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        report = {"valid": False, "problem_count": 1,
                  "problems": [{"kind": "unreadable_plan", "detail": str(e)}],
                  "cycles": []}
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(json.dumps({"valid": False, "problems": 1}, ensure_ascii=False))
        return 1
    problems, cycles = validate_plan(plan)
    report = {"plan_id": plan.get("plan_id") if isinstance(plan, dict) else None,
              "tasks": len(plan.get("tasks", [])) if isinstance(plan, dict) else 0,
              "milestones": len(plan.get("milestones", []))
              if isinstance(plan, dict) else 0,
              "problem_count": len(problems),
              "valid": not problems,
              "problems": problems,
              "cycles": cycles}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({"valid": report["valid"],
                      "problems": len(problems)}, ensure_ascii=False))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
