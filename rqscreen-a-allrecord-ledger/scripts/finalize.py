#!/usr/bin/env python3
"""finalize.py — 汇总本方向全部产物,按 case.json 的 output_contract 生成 result.json。

用法:
  python3 finalize.py --case /input/case.json --input-dir /input \
      --work /app/work --out /app/output

规则:
  - result.json 必含 case_id、status、sources、uncertainty;
  - output_contract 中列出的每个字段都必须出现在 result.json 中(能填则填,
    填不了的填空容器并在 uncertainty 说明),绝不臆造字段值;
  - status 取值: complete(全步骤成功) / partial(有步骤缺失或失败) / blocked(输入缺失);
  - 所有数值来自产物文件,不允许手工填写。
"""
import argparse, json, os, time

def load(p, default=None):
    try:
        if p.endswith(".jsonl"):
            return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default

def contract_fields(case):
    c = case.get("output_contract")
    if isinstance(c, list):
        return [str(x) for x in c]
    if isinstance(c, dict):
        if isinstance(c.get("fields"), list):
            return [str(x) for x in c["fields"]]
        return sorted(c.keys())
    return []

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    case = load(args.case, {})
    uncertainty, missing_steps = [], []

    ingest = load(os.path.join(args.work, "ingest_report.json"))
    ledger = load(os.path.join(args.out, "ledger.jsonl"), [])
    dups = load(os.path.join(args.work, "duplicates.jsonl"), [])
    summ = load(os.path.join(args.out, "screening_summary.json"), {})
    cands = load(os.path.join(args.out, "candidates.json"), [])
    attrib = load(os.path.join(args.out, "attribution.json"), {})
    if ingest is None:
        missing_steps.append("ingest")
    if not ledger:
        missing_steps.append("screen(ledger.jsonl 缺失或为空)")
        uncertainty.append("筛查台账缺失:未能完成逐条处置")

    if attrib and attrib.get("status") == "no_reference_list":
        uncertainty.append(attrib.get("note"))
    if attrib:
        for p in attrib.get("papers", []):
            if p.get("status") == "missing":
                uncertainty.append("清单文献 %s(%s)在快照中未找到匹配记录"
                                   % (p.get("ref_id"), p.get("title", "")[:60]))
            elif p.get("match", {}).get("metadata_diff"):
                uncertainty.append("清单文献 %s 元数据与快照记录不一致: %s"
                                   % (p.get("ref_id"), "; ".join(p["match"]["metadata_diff"])))
    if summ:
        u = summ.get("counts", {}).get("uncertain", 0)
        if u:
            uncertainty.append("%d 条记录处置为 uncertain,需人工复核" % u)

    sources = [{"kind": "file", "path": f["path"], "records": f.get("records")}
               for f in (ingest or {}).get("files", []) if f.get("records")]
    sources += [{"kind": "artifact", "path": p} for p in
                ["ingest_report.json", "duplicates.jsonl", "ledger.jsonl",
                 "screening_summary.json", "candidates.json", "attribution.json"]
                if os.path.exists(os.path.join(args.work, p)) or os.path.exists(os.path.join(args.out, p))]

    status = "blocked" if missing_steps and not ledger else ("partial" if (missing_steps or uncertainty) else "complete")
    counts = (summ or {}).get("counts", {})
    base = {
        "case_id": case.get("case_id"),
        "summary": "对输入快照完成全记录筛查:解析 %s 条记录,去重移除 %s 条(其中输入夹具标注的合成重复 %s 条),"
                   "逐条处置:纳入 %s / 排除 %s / 待复核 %s;署名文献清单核验 %s 篇(匹配 %s, 存疑 %s, 缺失 %s)。"
                   % ((ingest or {}).get("records_total", "?"), len(dups),
                      sum(1 for d in dups if d.get("synthetic_flag")),
                      counts.get("included", "?"), counts.get("excluded", "?"),
                      counts.get("uncertain", "?"),
                      attrib.get("total", "无清单"), attrib.get("matched", "-"),
                      attrib.get("ambiguous", "-"), attrib.get("missing", "-")),
        "candidates": cands,
        "screening_ledger": ledger,
        "duplicates": dups,
        "attribution": attrib.get("papers", attrib),
        "evidence_log": {
            "ledger": "ledger.jsonl (逐条 rid+disposition+reason_codes+命中词+片段)",
            "summary": "screening_summary.json (PRISMA 计数)",
            "duplicates": "duplicates.jsonl (去重对与方法)",
            "attribution": "attribution.json (清单文献归属核验)"},
        "sources": sources,
        "status": status,
        "uncertainty": uncertainty,
        "missing_steps": missing_steps,
        "method": "rqscreen-a-allrecord-ledger: ingest→dedupe→criteria screening→attribution",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    result = dict(base)
    for f in contract_fields(case):
        if f not in result:
            for alias in ("subquestions", "sub_questions"):
                if f == "subquestions" or alias == f:
                    result[f] = list((summ or {}).get("criteria", {}).get("subquestion_map", {}).keys())
                    break
            if f not in result:
                result[f] = []
                uncertainty.append("output_contract 字段 %s 无对应产物,留空" % f)
    result["uncertainty"] = uncertainty
    with open(os.path.join(args.out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({"ok": True, "status": status, "contract_fields": len(contract_fields(case)),
                      "uncertainty_items": len(uncertainty)}, ensure_ascii=False))

if __name__ == "__main__":
    main()
