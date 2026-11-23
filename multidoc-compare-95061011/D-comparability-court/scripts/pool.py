#!/usr/bin/env python3
"""pool.py — 合成守门：任何定量/定性合成之前，必须先向本脚本申请 permit。

输入：decisions.jsonl + synthesis_request.json
  synthesis_request.json:
    {"request_id": "REQ-01",
     "docs": ["DOC-01", "DOC-02"],          # 必须 ≥2 篇
     "field": "degradation_rate_eta",        # 想比较的字段
     "claim_type": "quantitative",           # quantitative | qualitative
     "required_dimensions": ["task", ...],   # 缺省 = 六核心维度
     "claim_text": "想做的断言"}

输出（--out 指定的 JSON）：
  permit: {"status": "permit", "permit_id": "PERMIT-<request_id>",
           "normalization_notes": [...], "caveats": [...], "decisions_used": [...]}
  block:  {"status": "block", "permit_id": null,
           "blocking": [{decision_id, dimension, verdict, 双方取值与 quote 定位}, ...]}

判定规则（见 references/verdict-taxonomy.md）：
  quantitative 仅放行 comparable/convertible；qualitative 额外放行 subset_only；
  blocked / undecidable / 缺少裁定记录 → 一律 block。退出码恒为 0，以 status 字段为准。
"""
import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

CORE_DIMENSIONS = ["task", "metric", "units", "material", "pollutant", "budget"]
DEFAULT_PERMIT_POLICY = {
    "quantitative": ["comparable", "convertible"],
    "qualitative": ["comparable", "convertible", "subset_only"],
}


def load_decisions(path):
    idx = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec["dimension"] == "__overall__":
                continue
            idx[(tuple(rec["doc_pair"]), rec["dimension"])] = rec
    return idx


def main() -> int:
    ap = argparse.ArgumentParser(description="合成守门：permit 或 block")
    ap.add_argument("--decisions", required=True, help="decide.py 输出的 decisions.jsonl")
    ap.add_argument("--request", required=True, help="synthesis_request.json")
    ap.add_argument("--rules", default=None, help="可选：comparability-rules.json（读取其中的 permit_policy）")
    ap.add_argument("--out", required=True, help="输出 permit/block 结果 JSON")
    args = ap.parse_args()

    idx = load_decisions(args.decisions)
    req = json.loads(Path(args.request).read_text(encoding="utf-8"))

    policy = DEFAULT_PERMIT_POLICY
    if args.rules:
        rules = json.loads(Path(args.rules).read_text(encoding="utf-8"))
        policy = rules.get("permit_policy", policy)

    request_id = str(req.get("request_id", "REQ-UNKNOWN"))
    docs = list(req.get("docs", []))
    claim_type = str(req.get("claim_type", "quantitative"))
    field = str(req.get("field", ""))
    dims = list(req.get("required_dimensions") or CORE_DIMENSIONS)
    claim_text = str(req.get("claim_text", ""))

    result = {
        "request_id": request_id,
        "claim_type": claim_type,
        "field": field,
        "docs": docs,
        "required_dimensions": dims,
        "claim_text": claim_text,
        "status": None,
        "permit_id": None,
        "normalization_notes": [],
        "caveats": [],
        "blocking": [],
        "decisions_used": [],
    }

    if claim_type not in policy:
        result["status"] = "block"
        result["blocking"].append({"reason": f"未知 claim_type '{claim_type}'（允许: {sorted(policy)}）"})
    elif len(docs) < 2:
        # 单篇摘要不构成多文档比较：守门直接拒绝
        result["status"] = "block"
        result["blocking"].append({"reason": f"合成请求仅含 {len(docs)} 篇论文（<2），不构成多文档比较"})
    else:
        allowed = set(policy[claim_type])
        for a, b in combinations(sorted(docs), 2):
            for dim in dims:
                rec = idx.get(((a, b), dim))
                if rec is None:
                    result["blocking"].append({
                        "reason": "缺少裁定记录", "doc_pair": [a, b], "dimension": dim,
                        "hint": "先补条件档案并重跑 build_profiles.py + decide.py",
                    })
                    continue
                result["decisions_used"].append(rec["decision_id"])
                if rec["verdict"] not in allowed:
                    bd = rec.get("blocking_detail", {})
                    result["blocking"].append({
                        "decision_id": rec["decision_id"],
                        "doc_pair": [a, b],
                        "dimension": dim,
                        "verdict": rec["verdict"],
                        "note": rec.get("note", ""),
                        "value_a": bd.get("value_a"),
                        "value_b": bd.get("value_b"),
                    })
                elif rec["verdict"] == "convertible":
                    result["normalization_notes"].append(
                        f"{a}×{b} / {dim}: {rec.get('note', '')} [{rec['decision_id']}]")
                elif rec["verdict"] == "subset_only":
                    result["caveats"].append(
                        f"{a}×{b} / {dim}: 仅 subset_only——{rec.get('note', '')} "
                        f"（报告必须注明口径差异）[{rec['decision_id']}]")
        result["status"] = "permit" if not result["blocking"] else "block"
        if result["status"] == "permit":
            result["permit_id"] = f"PERMIT-{request_id}"
            result["allowed_assertion"] = claim_text
        else:
            result["blocked_assertion"] = claim_text

    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if result["status"] == "permit":
        print(f"PERMIT 签发: {result['permit_id']}（{claim_type} / {field} / {' × '.join(docs)}）")
        for n in result["normalization_notes"]:
            print(f"  [归一化] {n}")
        for c in result["caveats"]:
            print(f"  [注意] {c}")
    else:
        print(f"BLOCK 阻断: {request_id}（{claim_type} / {field} / {' × '.join(docs)}）")
        for bitem in result["blocking"]:
            if "decision_id" in bitem:
                va, vb = bitem.get("value_a") or {}, bitem.get("value_b") or {}
                print(f"  [阻断] {bitem['doc_pair'][0]}×{bitem['doc_pair'][1]} / {bitem['dimension']}: "
                      f"{bitem['verdict']} — {va.get('value')!r} vs {vb.get('value')!r} [{bitem['decision_id']}]")
            else:
                print(f"  [阻断] {bitem.get('reason')}")
    print(f"结果已写入 {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
