#!/usr/bin/env python3
"""run_minimal_example.py — 端到端运行 examples/minimal 并打印自检结果。

用法：在 bundle 根目录执行  python3 scripts/run_minimal_example.py

产物（写入 examples/minimal/output/）：
  records.json   归一化题录记录（含 locator）
  chains.json    版本链 + 生命周期裁决 + 链接决策证据
  alerts.json    窗口预警（每条链至多一条，按优先级排序）
  result.json    按 case.json output_contract 装配的最终结果
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLE_ROOT = os.path.dirname(HERE)
EXAMPLE_DIR = os.path.join(BUNDLE_ROOT, "examples", "minimal")
sys.path.insert(0, HERE)

import common          # noqa: E402
import chain_link      # noqa: E402
import lifecycle       # noqa: E402
import assemble_result # noqa: E402


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def main():
    case = common.load_json(os.path.join(EXAMPLE_DIR, "case.json"))
    materials_dir = os.path.join(EXAMPLE_DIR, case.get("materials_dir", "materials"))
    output_dir = os.path.join(EXAMPLE_DIR, case.get("output_dir", "output"))
    os.makedirs(output_dir, exist_ok=True)

    # 1. 抽取
    records, anomalies = common.extract_records(materials_dir)
    print("[1] 抽取记录 %d 条；材料异常 %d 件" % (len(records), len(anomalies)))

    # 2. 版本链构建
    chains, decisions = chain_link.build_chains(records)
    print("[2] 构建版本链 %d 条；链接决策 %d 条" % (len(chains), len(decisions)))

    # 3. 生命周期裁决 + 预警分类
    evaluated, alerts, unresolved = lifecycle.evaluate_chains(chains, decisions)
    print("[3] 预警 %d 条；未解析 %d 条" % (len(alerts), len(unresolved)))
    for a in alerts:
        print("    - [%s/%s] %s :: %s" % (
            a["priority"], a["alert_type"], a["chain_id"], a["title"]))

    # 4. 装配与契约校验
    notes = []
    if case.get("synthetic"):
        notes.append("synthetic data: " + str(case.get("synthetic_note", "")))
    result = assemble_result.assemble_result(
        case, evaluated, alerts, unresolved, anomalies, notes)

    write_json(os.path.join(output_dir, "records.json"), records)
    write_json(os.path.join(output_dir, "chains.json"), evaluated)
    write_json(os.path.join(output_dir, "alerts.json"), alerts)
    write_json(os.path.join(output_dir, "result.json"), result)
    print("[4] 产物已写入 %s" % os.path.relpath(output_dir, BUNDLE_ROOT))

    # 5. 自检
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, ok, detail))

    by_id = {c["chain_id"]: c for c in evaluated}
    # 链数：8 条记录 → 5 条链
    check("链数 == 5", len(evaluated) == 5, "actual=%d" % len(evaluated))
    # 预印本 + 正式版合并为一条链且为 version_update
    merged = [c for c in evaluated
              if "arxiv:2401.00001v1" in c["members"]
              and "crossref:10.1234/jcat.2024.0001" in c["members"]]
    check("预印本+正式版合并为一链", len(merged) == 1,
          "matches=%d" % len(merged))
    if merged:
        cid = merged[0]["chain_id"]
        al = [a for a in alerts if a["chain_id"] == cid]
        check("合并链预警为 version_update",
              len(al) == 1 and al[0]["alert_type"] == "version_update",
              "alerts=%s" % [a["alert_type"] for a in al])
        check("合并链无重复 new_work 预警",
              not any(a["alert_type"] == "new_work" for a in al), "")
        check("合并链生命周期 published",
              merged[0]["lifecycle_state"] == "published",
              merged[0]["lifecycle_state"])
    # v1→v2 修订链
    rev = [c for c in evaluated
           if sum(1 for m in c["members"] if "2402.00002" in m) == 2]
    check("v1+v2 合并为一链", len(rev) == 1, "matches=%d" % len(rev))
    if rev:
        check("修订链生命周期 revised",
              rev[0]["lifecycle_state"] == "revised",
              rev[0]["lifecycle_state"])
    # 撤稿链
    ret = [a for a in alerts if a["alert_type"] == "retraction_notice"]
    check("撤稿预警存在且 critical",
          len(ret) == 1 and ret[0]["priority"] == "critical",
          "alerts=%s" % [(a["alert_type"], a["priority"]) for a in ret])
    check("撤稿预警排在首位", alerts and alerts[0]["alert_type"] == "retraction_notice",
          alerts[0]["alert_type"] if alerts else "none")
    # 孤立记录进入 unresolved
    check("孤立记录进入 unresolved", len(unresolved) == 1,
          "unresolved=%d" % len(unresolved))
    # 契约齐全
    contract = case.get("output_contract", [])
    check("result.json 覆盖 output_contract 全部字段",
          all(f in result for f in contract),
          "missing=%s" % [f for f in contract if f not in result])
    check("status 诚实降级为 partial（存在 unresolved）",
          result["status"] == "partial", result["status"])
    # locator 完整性：所有 state_evidence 均带 file+pointer
    all_loc = [l for c in evaluated for l in c["state_evidence"]]
    check("全部证据带 locator(file+pointer)",
          all("file" in l and "pointer" in l for l in all_loc) and bool(all_loc),
          "evidence=%d" % len(all_loc))

    failed = 0
    for name, ok, detail in checks:
        print("    [%s] %s%s" % ("PASS" if ok else "FAIL", name,
                                 (" — " + detail) if detail and not ok else ""))
        failed += 0 if ok else 1
    print("自检: %d/%d 通过" % (len(checks) - failed, len(checks)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
