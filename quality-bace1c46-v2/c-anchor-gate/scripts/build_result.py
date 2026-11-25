#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — 组装交付物 result.json 与 evidence_table.md。

用法:
    python3 build_result.py --workdir /app/work --output-dir /app/output \
        [--case /input/case.json]

status 规则:
    ≥1 条 verified 锚定且无畸形输入  -> success
    全部弃权                          -> partial (limits 说明)
    无任何文档                        -> partial (explanation 说明)
    缺少 index/gated 等致命输入       -> failed (exit 1)

退出码: 0 = 正常; 1 = 致命输入缺失; 2 = argparse 用法错误。
"""
import argparse
import json
import os
import sys

ANCHORED = ("verified", "verified_span", "repaired_locator")
ABSTAIN = ("abstain_unverifiable", "abstain_no_text_layer")


def eprint(*a):
    print(*a, file=sys.stderr)


def load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def mirror_output_contract(case):
    """防御式递归：把 case.json 中 output_contract 声明的字段镜像出来。

    在整棵 case 树中查找声明字段的值；找不到则 None（调用方记入 uncertainties）。
    """
    if not isinstance(case, dict):
        return None, []
    contract = case.get("output_contract")
    if contract is None:
        return None, []

    if isinstance(contract, dict):
        fields = list(contract.keys())
    elif isinstance(contract, list):
        fields = [x for x in contract if isinstance(x, str)]
    else:
        return None, ["output_contract has unexpected type: %s"
                      % type(contract).__name__]

    def deep_find(node, key):
        # 不回溯 output_contract 子树自身，否则会命中声明的 schema 而非实际值
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "output_contract":
                    continue
                if k == key:
                    return v
            for k, v in node.items():
                if k == "output_contract":
                    continue
                hit = deep_find(v, key)
                if hit is not None:
                    return hit
        elif isinstance(node, list):
            for v in node:
                hit = deep_find(v, key)
                if hit is not None:
                    return hit
        return None

    mirrored, missing = {}, []
    for fld in fields:
        val = deep_find(case, fld)
        if val is None:
            missing.append(fld)
        mirrored[fld] = val
    return mirrored, ["output_contract field %r not found in case.json" % f
                      for f in missing]


def main(argv=None):
    ap = argparse.ArgumentParser(description="assemble result.json")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--case", default=None)
    args = ap.parse_args(argv)

    index_path = os.path.join(args.workdir, "index.json")
    if not os.path.exists(index_path):
        eprint("fatal: %s missing; run build_index.py first" % index_path)
        return 1
    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)
    docs = index.get("documents", [])

    case, case_id = {}, index.get("case_id")
    if args.case and os.path.exists(args.case):
        try:
            with open(args.case, "r", encoding="utf-8") as f:
                case = json.load(f)
            case_id = case.get("case_id") or case.get("id") or case_id
        except (OSError, json.JSONDecodeError) as exc:
            eprint("warning: cannot read case.json: %s" % exc)

    gated_path = os.path.join(args.workdir, "gated.jsonl")
    gated = load_jsonl(gated_path) if os.path.exists(gated_path) else []

    uncertainties, change_records, limits = [], [], []

    mirrored, missing_notes = mirror_output_contract(case)
    uncertainties.extend(missing_notes)

    for d in docs:
        if not d.get("text_layer"):
            uncertainties.append("doc %s has no usable text layer: %s"
                                 % (d["doc_id"], d.get("note")))

    evidence_records, abstentions = [], []
    coverage = {d["doc_id"]: {"paragraphs_indexed": d.get("paragraphs", 0),
                              "claims_anchored": 0} for d in docs}
    for rec in gated:
        v = rec.get("verdict")
        if v in ANCHORED:
            evidence_records.append({
                "doc_id": rec["doc_id"],
                "claim_id": rec["claim_id"],
                "judgment": rec.get("judgment"),
                "quote": rec.get("quote"),
                "locator": rec.get("final_locator"),
                "verdict": v,
                "rationale": rec.get("rationale"),
            })
            cov = coverage.setdefault(rec["doc_id"],
                                      {"paragraphs_indexed": 0,
                                       "claims_anchored": 0})
            cov["claims_anchored"] += 1
            if v == "repaired_locator":
                change_records.append({
                    "type": "locator_repair",
                    "doc_id": rec["doc_id"],
                    "claim_id": rec["claim_id"],
                    "old_locator": rec.get("locator"),
                    "new_locator": rec.get("final_locator")})
        elif v in ABSTAIN:
            abstentions.append({
                "doc_id": rec.get("doc_id"),
                "claim_id": rec.get("claim_id"),
                "judgment": rec.get("judgment"),
                "verdict": v,
                "reason": rec.get("reason"),
                "claimed_locator": rec.get("locator"),
                "quote": rec.get("quote"),
            })

    n_docs = len(docs)
    n_anchored = len(evidence_records)
    n_abstained = len(abstentions)

    if n_docs == 0:
        status = "partial"
        limits.append("no documents discovered in case.json / input-dir; "
                      "nothing could be anchored")
    elif n_anchored >= 1:
        status = "success"
        if n_abstained:
            limits.append("%d of %d judgment rows abstained (see abstentions)"
                          % (n_abstained, n_anchored + n_abstained))
    elif gated:
        status = "partial"
        limits.append("all %d judgment rows abstained; no anchor could be "
                      "verified" % len(gated))
    else:
        status = "partial"
        limits.append("documents indexed but no judgment rows were gated "
                      "(gated.jsonl missing or empty)")

    result = {
        "case_id": case_id,
        "status": status,
        "evidence_records": evidence_records,
        "abstentions": abstentions,
        "anchor_coverage": coverage,
        "uncertainties": uncertainties,
        "change_records": change_records,
        "limits": limits,
    }
    if mirrored is not None:
        result["output_contract"] = mirrored

    os.makedirs(args.output_dir, exist_ok=True)
    result_path = os.path.join(args.output_dir, "result.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # evidence_table.md
    lines = ["# Evidence Table", "",
             "| claim_id | judgment | quote | locator | verdict |",
             "|---|---|---|---|---|"]
    all_rows = sorted(gated, key=lambda r: (r.get("doc_id", ""),
                                            str(r.get("claim_id", ""))))
    def cell(x):
        s = "" if x is None else str(x)
        return s.replace("|", "\\|").replace("\n", " ")
    for rec in all_rows:
        loc = rec.get("final_locator") or rec.get("locator") or ""
        lines.append("| %s | %s | %s | %s | %s |" % (
            cell(rec.get("claim_id")), cell(rec.get("judgment")),
            cell(rec.get("quote")), cell(loc), cell(rec.get("verdict"))))
    table_path = os.path.join(args.output_dir, "evidence_table.md")
    with open(table_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print("result.json written: %s (status=%s, evidence=%d, abstentions=%d)"
          % (result_path, status, n_anchored, n_abstained))
    print("evidence_table.md written: %s (%d rows)"
          % (table_path, len(all_rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
