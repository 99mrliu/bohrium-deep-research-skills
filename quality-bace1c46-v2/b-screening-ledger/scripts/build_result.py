#!/usr/bin/env python3
"""build_result.py — 组装最终 result.json 与 screening_report.md。

用法:
    python3 build_result.py --workdir /app/work --output-dir /app/output --case /input/case.json

status 规则:
    success —— 全部唯一候选均有有效决定、无 uncertain 待定、flow 不变量全部通过
               （包括“全部排除但理由完整”的情形）；
    partial —— 存在未筛选候选 / uncertain 待定 / 空候选集（附零结果说明）/
               不变量未全部通过（附 limits 说明）；
    failed  —— 缺少 harvest_report 等关键中间产物，无法组装可信结果。

退出码: 0 = result.json 已写出（status 字段本身可能是 partial）；2 = 用法/IO 错误。
仅 Python 3 标准库。
"""
import argparse
import json
import os
import sys

CASE_ID_KEYS = ("case_id", "caseid", "id", "case")
CONTRACT_KEYS = ("output_contract", "contract", "output_fields", "required_fields")


def find_case_id(obj):
    if isinstance(obj, dict):
        for k in CASE_ID_KEYS:
            for kk, vv in obj.items():
                if str(kk).strip().lower() == k and isinstance(vv, (str, int)):
                    return str(vv)
        for vv in obj.values():
            r = find_case_id(vv)
            if r:
                return r
    elif isinstance(obj, list):
        for it in obj:
            r = find_case_id(it)
            if r:
                return r
    return None


def find_contract(obj):
    found = {}

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                kl = str(k).strip().lower()
                if kl == "output_contract" and isinstance(v, dict) and "output_contract" not in found:
                    found["output_contract"] = v
                elif kl == "contract" and isinstance(v, dict) and "contract" not in found:
                    found["contract"] = v
                elif kl == "output_fields" and isinstance(v, list) and "output_fields" not in found:
                    found["output_fields"] = v
                elif kl == "required_fields" and isinstance(v, list) and "required_fields" not in found:
                    found["required_fields"] = v
                walk(v)
        elif isinstance(o, list):
            for it in o:
                walk(it)

    walk(obj)
    return found


def read_jsonl(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="组装 result.json 与 screening_report.md")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--case", required=True)
    args = ap.parse_args(argv)

    w = args.workdir
    try:
        with open(args.case, "r", encoding="utf-8") as f:
            case = json.load(f)
    except Exception as e:
        print("ERROR: 无法解析 case.json: %s" % e, file=sys.stderr)
        return 2

    os.makedirs(args.output_dir, exist_ok=True)
    case_id = find_case_id(case) or "unknown"
    contract = find_contract(case)

    harvest_path = os.path.join(w, "harvest_report.json")
    if not os.path.exists(harvest_path):
        # failed：连收割都没做过
        result = {
            "case_id": case_id,
            "status": "failed",
            "output_contract": contract,
            "screening": [], "evidence_records": [], "flow": None,
            "omissions": ["未找到 harvest_report.json：init_ledger.py 未运行，"
                          "无法组装可信结果。"],
            "uncertainties": ["流水线未执行"],
            "change_records": [],
        }
        with open(os.path.join(args.output_dir, "result.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print("status=failed (no harvest_report)")
        return 0

    with open(harvest_path, "r", encoding="utf-8") as f:
        harvest = json.load(f)
    candidates = read_jsonl(os.path.join(w, "candidates.jsonl"))
    duplicates = read_jsonl(os.path.join(w, "duplicates.jsonl"))
    screening_rows = read_jsonl(os.path.join(w, "screening.jsonl"))
    change_rows = read_jsonl(os.path.join(w, "change_records.jsonl"))
    flow = None
    flow_path = os.path.join(w, "flow.json")
    if os.path.exists(flow_path):
        with open(flow_path, "r", encoding="utf-8") as f:
            flow = json.load(f)

    # 生效决定（同一 cand_id 最后一行生效）
    effective = {}
    for r in screening_rows:
        effective[r["cand_id"]] = r

    uncertainties = list(harvest.get("notes") or [])

    # ---- candidate_set ----
    candidate_set = []
    for c in candidates:
        d = effective.get(c["cand_id"])
        merged = [mid for dup in duplicates if dup["survivor"] == c["cand_id"]
                  for mid in dup.get("merged_ids", [])]
        entry = {
            "cand_id": c["cand_id"],
            "metadata": {k: c[k] for k in ("title", "authors", "year", "doi",
                                           "abstract_snippet")},
            "source": {"snapshot": c.get("source") or "",
                       "path": c.get("source_path") or ""},
            "merged_from": merged,
            "decision": d["decision"] if d else "unscreened",
            "criterion": d.get("criterion") if d else None,
            "rationale": d.get("rationale") if d else None,
            "evidence_quote": d.get("evidence_quote") if d else None,
            "rank_rationale": d.get("rank_rationale") if d else None,
        }
        if d is None:
            uncertainties.append("%s 尚无有效筛选决定（未筛选）" % c["cand_id"])
        elif d["decision"] == "uncertain":
            uncertainties.append("%s 判为 uncertain：%s" % (c["cand_id"], d["rationale"]))
        candidate_set.append(entry)

    # ---- evidence_records ----
    evidence_records = [{"cand_id": r["cand_id"], "evidence_quote": r["evidence_quote"],
                         "criterion": r["criterion"], "verified": True}
                        for r in effective.values()]

    # ---- status ----
    limits = []
    n_unscreened = sum(1 for e in candidate_set if e["decision"] == "unscreened")
    n_uncertain = sum(1 for e in candidate_set if e["decision"] == "uncertain")
    invariants_ok = True
    if flow is None:
        invariants_ok = False
        limits.append("flow_check.py 未运行，流程计数缺失")
    else:
        invariants_ok = all(inv.get("pass") for inv in flow.get("invariants", {}).values())
        if not invariants_ok:
            limits.append("流程算术不变量未全部通过，详见 flow.json.invariants")
    if not candidates:
        status = "partial"
        limits.append("空候选集：identified=0，已按诚实零结果流程处理，未发明任何候选")
    elif n_unscreened or n_uncertain or not invariants_ok:
        status = "partial"
        if n_unscreened:
            limits.append("%d 条候选未筛选" % n_unscreened)
        if n_uncertain:
            limits.append("%d 条候选待定（uncertain），需补充元数据/全文后复筛" % n_uncertain)
    else:
        status = "success"

    omissions = list(flow.get("omissions", [])) if flow else []
    if n_unscreened and not any("未筛选" in o for o in omissions):
        omissions.append("未筛选声明：%d 条候选无有效决定。" % n_unscreened)

    result = {
        "case_id": case_id,
        "status": status,
        "limits": limits,
        "output_contract": contract,
        "candidate_set": candidate_set,
        "screening": candidate_set,  # 兼容别名：同一内容的另一视图名
        "evidence_records": evidence_records,
        "flow": flow,
        "omissions": omissions,
        "uncertainties": uncertainties,
        "change_records": change_rows,
        "summary": {
            "identified": (flow or {}).get("identified", harvest.get("identified_raw")),
            "unique": len(candidates),
            "duplicates_removed": len(duplicates),
            "included": sum(1 for e in candidate_set if e["decision"] == "include"),
            "excluded": sum(1 for e in candidate_set if e["decision"] == "exclude"),
            "uncertain": n_uncertain,
            "unscreened": n_unscreened,
        },
    }
    # 镜像 contract 声明的全部 required 字段；缺者填 null 并记入 uncertainties
    req = list(contract.get("required_fields") or contract.get("output_fields") or [])
    oc = contract.get("output_contract")
    if isinstance(oc, dict):
        req = req or list(oc.get("required_fields") or oc.get("output_fields") or [])
    for field in req:
        if isinstance(field, str) and field not in result:
            result[field] = None
            uncertainties.append("output_contract 声明的字段 %r 暂无法填充，置 null" % field)

    out_path = os.path.join(args.output_dir, "result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # ---- screening_report.md ----
    md = ["# 筛选决定报告（screening-decision-ledger）", "",
          "- case_id: `%s`" % case_id,
          "- status: **%s**" % status,
          "- identified=%(identified)s unique=%(unique)s duplicates=%(duplicates_removed)s "
          "included=%(included)s excluded=%(excluded)s uncertain=%(uncertain)s "
          "unscreened=%(unscreened)s" % result["summary"], ""]
    if limits:
        md += ["## 限制（limits）", ""] + ["- " + l for l in limits] + [""]
    md += ["## 逐条决定", ""]
    for e in candidate_set:
        md.append("### %s — %s" % (e["cand_id"], e["metadata"]["title"]))
        md.append("- 决定: **%s** | criterion: %s" % (e["decision"], e["criterion"]))
        if e["rationale"]:
            md.append("- 理由: %s" % e["rationale"])
        if e["evidence_quote"]:
            md.append("- 证据引句（已机器核验）: \"%s\"" % e["evidence_quote"])
        if e["rank_rationale"]:
            md.append("- 排序理由: %s" % e["rank_rationale"])
        if e["merged_from"]:
            md.append("- 去重合并: 吸收 %s" % ", ".join(e["merged_from"]))
        md.append("")
    if omissions:
        md += ["## 遗漏声明", ""] + ["- " + o for o in omissions] + [""]
    md.append("> 本报告由脚本生成；所有证据引句均通过 apply_decisions.py 的"
              "归一化子串核验。")
    with open(os.path.join(args.output_dir, "screening_report.md"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(md))

    with open(os.path.join(w, "change_records.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"action": "build_result", "status": status,
                            "output": out_path}, ensure_ascii=False) + "\n")

    print("status=%s included=%d excluded=%d uncertain=%d unscreened=%d -> %s"
          % (status, result["summary"]["included"], result["summary"]["excluded"],
             n_uncertain, n_unscreened, out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
