#!/usr/bin/env python3
"""finalize.py — 把覆盖矩阵、停止决定、候选证据集按 output_contract 装配成 result.json。

用法:
  python3 finalize.py --case /input/case.json --work /app/work --out /app/output

行为:
  - 读 /app/work/coverage_report.json（measure.py 产物）与 case.json；
  - result.json 必含 case_id / status / sources / uncertainty 及 output_contract
    动态读出的每一个字段（禁止硬编码字段名）；
  - 填不了的契约字段留空容器，并在 field_notes 与 uncertainty 写明原因；
  - status 诚实三值：complete（全部 SQ sufficient 且决定为 evidence_sufficient）、
    partial（有 thin/starved、handoff、解析失败或空契约字段等已声明保留）、
    blocked（无覆盖报告或快照零记录）；
  - 覆盖矩阵与停止决定同时以独立文件落盘 /app/output 供复核。

退出码: 0=基于真实覆盖报告装配；2=降级交付（缺覆盖报告/case 损坏，交付 blocked 骨架）。
"""
import argparse, json, os, sys, time

BUILTIN_FIELDS = ("case_id", "status", "sources", "uncertainty")


def contract_fields(case):
    c = case.get("output_contract")
    if isinstance(c, list):
        return [str(x) for x in c]
    if isinstance(c, dict):
        for k in ("fields", "required"):
            if isinstance(c.get(k), list):
                return [str(x) for x in c[k]]
        return sorted(c.keys())
    return []


def load_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description="按 output_contract 装配覆盖测量结果为 result.json")
    ap.add_argument("--case", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    degraded = []
    case = load_json(args.case)
    if not isinstance(case, dict):
        degraded.append("case.json 缺失或损坏，case_id 与契约无法确认")
        case = {}
    report = load_json(os.path.join(args.work, "coverage_report.json"))
    if not isinstance(report, dict):
        degraded.append("缺少 /app/work/coverage_report.json：请先运行 measure.py；"
                        "本次只能交付 blocked 骨架")
        report = None

    fields = contract_fields(case)
    uncertainty = list(degraded)
    matrix, decision, records_total, problems = [], {"decision": None, "reason": None}, 0, []
    candidates = []
    if report:
        matrix = report.get("matrix") or []
        decision = report.get("stop_decision") or {}
        records_total = report.get("records_total") or 0
        problems = report.get("problems") or []
        uncertainty.extend(problems)
        # 候选证据集：任一子问题的可用证据（不去重夹具标记，原样登记）
        seen = {}
        for row in matrix:
            usable = set(row.get("usable_rids") or [])
            for ev in row.get("evidence") or []:
                if ev.get("rid") not in usable:
                    continue
                c = seen.setdefault(ev["rid"], {"rid": ev["rid"], "title": ev.get("title"),
                                                "year": ev.get("year"), "doi": ev.get("doi"),
                                                "supports": []})
                c["supports"].append(row["sq_id"])
        candidates = sorted(seen.values(), key=lambda x: x["rid"])
        for row in matrix:
            if row["sufficiency"] == "starved":
                uncertainty.append("子问题 %s 零可用证据（缺口: %s），已触发 handoff_to_human"
                                   % (row["sq_id"], row["gap"] or "no_records"))
            elif row["sufficiency"] == "thin":
                uncertainty.append("子问题 %s 证据薄弱（可用 %d 条<%d），按 thin 如实交付"
                                   % (row["sq_id"], row["usable_hits"],
                                      report.get("thresholds", {}).get(
                                          "sufficient_min_usable", 3)))
            for rid in row.get("conflicted_rids") or []:
                uncertainty.append("子问题 %s 的冲突意见夹具记录 %s 仅登记为争议证据，"
                                   "不做学术裁决" % (row["sq_id"], rid))
            if row.get("metadata_missing_hits"):
                uncertainty.append("子问题 %s 有 %d 条证据缺年份或 DOI，归属核验受限"
                                   % (row["sq_id"], row["metadata_missing_hits"]))
        if decision.get("decision") == "handoff_to_human":
            uncertainty.append("停止决定 handoff_to_human：%s" % decision.get("reason"))

    if report and records_total == 0:
        status = "blocked"
    elif report is None:
        status = "blocked"
    elif uncertainty:
        status = "partial"
    else:
        status = "complete"

    summary = ("测量 %d 条快照记录 × %d 个子问题：sufficient %d / thin %d / starved %d；"
               "停止决定 %s（%s）" % (
                   records_total, len(matrix),
                   sum(1 for r in matrix if r["sufficiency"] == "sufficient"),
                   sum(1 for r in matrix if r["sufficiency"] == "thin"),
                   sum(1 for r in matrix if r["sufficiency"] == "starved"),
                   decision.get("decision"), decision.get("reason"))) if report else \
              "覆盖测量未完成：" + "；".join(degraded)

    result = {
        "case_id": case.get("case_id"),
        "status": status,
        "summary": summary,
        "candidates": candidates,
        "coverage_matrix": matrix,
        "sufficiency": {r["sq_id"]: r["sufficiency"] for r in matrix},
        "stop_decision": decision,
        "gaps": {r["sq_id"]: r["gap"] for r in matrix},
        "sources": ([{"kind": "file", "path": f["path"]}
                     for f in (report or {}).get("input_files", [])
                     if f.get("record_lists")] +
                    [{"kind": "artifact", "path": n}
                     for n in ("coverage_matrix.json", "stop_decision.json")]),
        "uncertainty": uncertainty,
        "method": "c-coverage-compass: decompose→measure(sq×evidence)→grade→marginal-gain→stop",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    # 契约纪律：动态读出的每个字段都必须出现；无对应产物则留空并说明
    field_notes = {}
    for f in fields:
        if f in BUILTIN_FIELDS:
            continue
        if f not in result:
            result[f] = []
            uncertainty.append("output_contract 字段 %s 无对应产物，留空待补" % f)
    for f in fields:
        if result.get(f) in ([], "", {}):
            field_notes[f] = ("本字段为空的原因已在 uncertainty 中说明"
                              if any(f in u for u in uncertainty) else
                              "本次运行无此类条目（如实留空，非遗漏）")
    result["field_notes"] = field_notes
    if status == "complete" and uncertainty:
        result["status"] = status = "partial"
    if status != "complete" and not uncertainty:
        uncertainty.append("状态为 %s 但未定位到具体保留项，请人工复核" % status)

    with open(os.path.join(args.out, "result.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "coverage_matrix.json"), "w", encoding="utf-8") as fh:
        json.dump({"matrix": matrix,
                   "thresholds": (report or {}).get("thresholds")}, fh,
                  ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "stop_decision.json"), "w", encoding="utf-8") as fh:
        json.dump(decision, fh, ensure_ascii=False, indent=2)

    print(json.dumps({"ok": not degraded, "status": status,
                      "contract_fields": len(fields), "candidates": len(candidates),
                      "stop_decision": decision.get("decision"),
                      "uncertainty_items": len(uncertainty)}, ensure_ascii=False))
    sys.exit(2 if degraded else 0)


if __name__ == "__main__":
    main()
