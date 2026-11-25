#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck.py — 预算调度技能自检（合成场景，不含真实数据）。

场景：12 项合成核验队列，预算 64 请求 / 900 秒 / 16384 token。
断言：
  1. 计划第 0 步为检查点写入（R0）；
  2. 依赖序被遵守（被依赖者先调度）；
  3. 预算耗尽到连降级计划都容纳不下时，计划被拒绝且退出码为 1；
  4. 剩余预算跌破阈值时触发降级，degradation_report.json 恰好列出被放弃项；
  5. 检查点被篡改时 restore 退出码为 1；
  6. 干净检查点恢复后 pending 队列与写入时完全一致；
  7. 成本报告合计与从账本原始行重算的合计相等（重算而非信任）。

退出码：0 全部通过；1 存在失败断言；2 用法错误。
仅使用 Python 标准库。
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.normpath(os.path.join(HERE, "..", "examples", "fixtures"))

LEDGER = os.path.join(HERE, "budget_ledger.py")
PLAN = os.path.join(HERE, "plan_schedule.py")
CKPT = os.path.join(HERE, "checkpoint.py")
DEGRADE = os.path.join(HERE, "degrade_plan.py")
COST = os.path.join(HERE, "cost_report.py")

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append((name, bool(cond), detail))
    print("[%s] %s%s" % ("PASS" if cond else "FAIL", name,
                         (" — " + detail) if detail else ""))


def run(argv, cwd=None):
    proc = subprocess.run([sys.executable] + argv, cwd=cwd,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True)
    return proc.returncode, proc.stdout, proc.stderr


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def main():
    queue = os.path.join(FIX, "task_queue.json")
    policy = os.path.join(FIX, "scheduling_policy.json")
    case = os.path.join(FIX, "case_fixture.json")
    spend_file = os.path.join(FIX, "spend_events.jsonl")

    tmp = tempfile.mkdtemp(prefix="budget_scheduler_selfcheck_")
    ledger = os.path.join(tmp, "ledger.jsonl")
    state = os.path.join(tmp, "budget_state.json")

    # ---- 阶段 A：新鲜账本 → 正常计划 --------------------------------------
    rc, out, err = run([LEDGER, "state", "--ledger", ledger,
                        "--policy", policy, "--out", state])
    check("A0 空账本 state 重算成功", rc == 0, err.strip())

    plan_a = os.path.join(tmp, "plan_a.json")
    rc, out, err = run([PLAN, "--queue", queue, "--state", state,
                        "--policy", policy, "--out", plan_a])
    check("A1 初始计划生成成功", rc == 0, err.strip())
    plan = load_json(plan_a)
    check("A2 计划第 0 步为检查点写入",
          plan["steps"] and plan["steps"][0]["id"] == "__checkpoint__",
          plan["steps"][0]["id"] if plan["steps"] else "空计划")
    check("A3 初始为 normal 模式", plan.get("mode") == "normal", plan.get("mode"))

    order = {s["id"]: s["seq"] for s in plan["steps"]}
    qitems = {it["id"]: it for it in load_json(queue)["items"]}
    dep_ok = all(order[d] < order[iid]
                 for iid in order if iid in qitems
                 for d in qitems[iid].get("deps", []) if d in order)
    check("A4 依赖序被遵守", dep_ok)
    mand_skipped = [s for s in plan.get("skipped", []) if s.get("mandatory")]
    check("A5 正常计划不丢强制任务", not mand_skipped, str(mand_skipped))

    # ---- 阶段 B：检查点写入 / 篡改 / 恢复 ---------------------------------
    workdir = os.path.join(tmp, "work")
    os.makedirs(workdir, exist_ok=True)
    draft = os.path.join(tmp, "result_draft.json")
    write_json(draft, {"case_id": "SYNTH-AD3E9357-000", "status": "partial",
                       "facsimile_forensics": None,
                       "uncertainty": ["合成草稿：字段未填"]})
    completed_f = os.path.join(tmp, "completed.json")
    pending_f = os.path.join(tmp, "pending.json")
    done_ids = ["v01", "v02"]
    pend_ids = [i for i in qitems if i not in done_ids]
    write_json(completed_f, done_ids)
    write_json(pending_f, pend_ids)

    rc, out, err = run([CKPT, "write", "--workdir", workdir, "--result", draft,
                        "--completed", completed_f, "--pending", pending_f])
    check("B1 检查点写入成功", rc == 0, err.strip())

    restored = os.path.join(tmp, "restored.json")
    rc, out, err = run([CKPT, "restore", "--workdir", workdir, "--out", restored])
    check("B2 干净检查点恢复成功", rc == 0, err.strip())
    r = load_json(restored)
    check("B3 恢复后 pending 队列与写入时一致", r["pending"] == pend_ids)
    check("B4 恢复后 completed 与写入时一致", r["completed"] == done_ids)

    ck_path = os.path.join(workdir, "checkpoint.json")
    good = load_json(ck_path)
    bad = dict(good)
    bad["completed"] = list(good["completed"]) + ["v99"]  # 篡改，不重算哈希
    write_json(ck_path, bad)
    rc, out, err = run([CKPT, "restore", "--workdir", workdir,
                        "--out", os.path.join(tmp, "restored_bad.json")])
    check("B5 篡改检查点被拒绝（退出码 1）", rc == 1, err.strip())
    write_json(ck_path, good)  # 还原，供后续使用

    # ---- 阶段 C：模拟花费 → 跌破阈值 → 降级 -------------------------------
    with open(spend_file, "r", encoding="utf-8") as fh:
        spend_lines = [json.loads(x) for x in fh if x.strip()]
    for payload in spend_lines:
        rc, out, err = run([LEDGER, "append", "--ledger", ledger,
                            "--kind", "spend", "--payload", json.dumps(payload)])
        if rc != 0:
            break
    check("C0 花费事件追加成功（%d 条）" % len(spend_lines), rc == 0, err.strip())

    rc, out, err = run([LEDGER, "verify", "--ledger", ledger])
    check("C1 账本链校验通过", rc == 0, err.strip())

    rc, out, err = run([LEDGER, "state", "--ledger", ledger,
                        "--policy", policy, "--out", state])
    st = load_json(state)
    check("C2 状态显示跌破阈值维度", bool(st.get("below_threshold")),
          str(st.get("below_threshold")) + " remaining=" + str(st["remaining"]))

    plan_c = os.path.join(tmp, "plan_c.json")
    rc, out, err = run([PLAN, "--queue", queue, "--state", state,
                        "--policy", policy, "--out", plan_c])
    plan_c_obj = load_json(plan_c)
    check("C3 阈值触发后计划转为 degrade 模式", rc == 0
          and plan_c_obj.get("mode") == "degrade", out.strip())
    check("C4 降级计划仍以检查点为第 0 步",
          plan_c_obj["steps"][0]["id"] == "__checkpoint__"
          and plan_c_obj["steps"][1]["id"] == "__degrade__")

    executed = [p["step_id"] for p in spend_lines
                if p.get("step_id", "").startswith("v")]
    write_json(completed_f, executed)
    expected_dropped = sorted(set(qitems) - set(executed))
    dg_plan = os.path.join(tmp, "degrade_plan.json")
    dg_report = os.path.join(tmp, "degradation_report.json")
    rc, out, err = run([DEGRADE, "--state", state, "--contract", case,
                        "--queue", queue, "--completed", completed_f,
                        "--out-plan", dg_plan, "--report", dg_report])
    check("C5 降级计划生成成功", rc == 0, err.strip())
    rep = load_json(dg_report)
    got_dropped = sorted(d["id"] for d in rep["dropped_verifications"])
    check("C6 degradation_report 恰好列出被放弃项",
          got_dropped == expected_dropped,
          "got=%s want=%s" % (got_dropped, expected_dropped))
    contract = load_json(case)["output_contract"]["fields"]
    want_null = sorted(f for f, s in contract.items() if not s.get("mandatory"))
    check("C7 非强制契约字段全部置 null",
          sorted(rep["contract_null_fields"]) == want_null)
    rc, out, err = run([LEDGER, "append", "--ledger", ledger, "--kind", "degrade",
                        "--payload", json.dumps({"trigger": "R3",
                                                 "report": dg_report})])
    check("C8 降级事件入账", rc == 0, err.strip())

    # ---- 阶段 D：预算耗尽 → 拒绝计划（退出码 1） ---------------------------
    rc, out, err = run([LEDGER, "append", "--ledger", ledger, "--kind", "spend",
                        "--payload", json.dumps({"step_id": "v09-retry",
                                                 "requests": 6, "seconds": 60,
                                                 "tokens": 900})])
    rc2, out, err = run([LEDGER, "state", "--ledger", ledger,
                         "--policy", policy, "--out", state])
    rc, out, err = run([PLAN, "--queue", queue, "--state", state,
                        "--policy", policy, "--out", os.path.join(tmp, "plan_d.json")])
    check("D1 预算耗尽时拒绝计划（退出码 1）", rc == 1, err.strip())

    # ---- 阶段 E：账本损坏检测 ---------------------------------------------
    tampered = os.path.join(tmp, "ledger_tampered.jsonl")
    with open(ledger, "r", encoding="utf-8") as fh:
        raw_lines = [json.loads(x) for x in fh if x.strip()]
    raw_lines[3]["payload"]["requests"] = 999  # 篡改第 4 行
    with open(tampered, "w", encoding="utf-8") as fh:
        for ln in raw_lines:
            fh.write(json.dumps(ln, ensure_ascii=False) + "\n")
    rc, out, err = run([LEDGER, "verify", "--ledger", tampered])
    check("E1 篡改账本被 verify 检出（退出码 1）", rc == 1, err.strip())
    rc, out, err = run([LEDGER, "append", "--ledger", tampered, "--kind", "note",
                        "--payload", json.dumps({"x": 1})])
    check("E2 损坏账本拒绝追加（退出码 1）", rc == 1, err.strip())
    rc, out, err = run([CKPT, "restore", "--workdir", workdir,
                        "--ledger", tampered,
                        "--out", os.path.join(tmp, "restored_bad2.json")])
    check("E3 检查点与账本链头不符被拒绝（退出码 1）", rc == 1, err.strip())

    # ---- 阶段 F：成本报告 == 账本重算 -------------------------------------
    rep_json = os.path.join(tmp, "cost_report.json")
    rep_md = os.path.join(tmp, "cost_report.md")
    rc, out, err = run([COST, "--ledger", ledger, "--out", rep_json,
                        "--md", rep_md])
    check("F1 成本报告生成成功", rc == 0, err.strip())
    rep = load_json(rep_json)
    sums = {"requests": 0, "seconds": 0, "tokens": 0}
    with open(ledger, "r", encoding="utf-8") as fh:
        for raw in fh:
            ln = json.loads(raw)
            if ln["kind"] == "spend":
                for d in sums:
                    sums[d] += int(ln["payload"].get(d, 0))
    check("F2 成本报告合计等于账本重算合计",
          rep["spent_total"] == sums,
          "report=%s recomputed=%s" % (rep["spent_total"], sums))
    st_final = load_json(state)
    check("F3 报告剩余量与 state 重算一致",
          rep["remaining"] == st_final["remaining"],
          "report=%s state=%s" % (rep["remaining"], st_final["remaining"]))

    # ---- 汇总 --------------------------------------------------------------
    n_pass = sum(1 for _, ok, _ in CHECKS if ok)
    n_all = len(CHECKS)
    print("-" * 60)
    print("SELFCHECK %s: %d/%d assertions passed (workdir=%s)"
          % ("OK" if n_pass == n_all else "FAILED", n_pass, n_all, tmp))
    return 0 if n_pass == n_all else 1


if __name__ == "__main__":
    sys.exit(main())
