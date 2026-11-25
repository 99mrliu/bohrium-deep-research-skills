#!/usr/bin/env python3
"""gated_screen.py — 信任门之后的轻量筛查 + 按契约装配 result.json。

只筛查 forensics.py 信任门放行的记录（trusted_records.jsonl）；隔离登记册与
元数据法证结论原样嵌入交付物（integrity_report 是 result.json 的一等公民字段）。
筛查逻辑刻意从简（年份窗 + 术语命中），本技能的重器在 forensics.py。

用法:
  python3 gated_screen.py --case /input/case.json --work /app/work --out /app/output

退出码:
  0  result.json 已装配（status 为 complete 或 partial）；
  1  forensics.py 前置产物缺失/损坏，只能交付 blocked 骨架；
  2  快照零记录（或零解析记录），result.json 以 status=blocked 交付。
"""
import argparse
import json
import os
import re
import sys
import time

STOPWORDS = set("""the a an and or of in on for to with by from at as is are was were
be been we our this that these those it its their between among within using based
study studies approach via new""".split())

# 轻量跨语词表：仅当 RQ 中真实出现左侧中文概念时才扩展右侧英文检索词。
# 本技能的重心在取证而非术语工程，词表保持最小；领域外 RQ 自动退化为
# 拉丁词 + CJK 二元组，不臆造术语。
LEXICON = {
    "锂": ["lithium"], "钠": ["sodium"], "金属": ["metal"], "负极": ["anode"],
    "正极": ["cathode"], "固态": ["solid state", "solid"], "电解质": ["electrolyte"],
    "界面": ["interface", "interfacial"], "稳定": ["stability", "stable"],
    "枝晶": ["dendrite"], "钙钛矿": ["perovskite"], "太阳能": ["solar", "photovoltaic"],
    "电池": ["cell", "battery"], "效率": ["efficiency"], "钝化": ["passivation"],
    "晶界": ["grain boundary"], "催化": ["catalysis", "catalyst"],
    "实验": ["experiment", "experimental"], "机器学习": ["machine learning"],
    "深度学习": ["deep learning"], "蛋白质": ["protein"], "基因": ["gene"],
    "肿瘤": ["tumor", "cancer"],
}


def derive_criteria(rq):
    rq = rq or ""
    years = [int(y) for y in re.findall(r"(?:19|20)\d{2}", rq)]
    window = [min(years), max(years)] if len(years) >= 2 else (
        [years[0], years[0]] if years else None)
    terms = set(w for w in re.findall(r"[a-z0-9]+", rq.lower())
                if w not in STOPWORDS and len(w) > 2)
    expanded = []
    for concept, en_terms in LEXICON.items():
        if concept in rq:
            terms.update(en_terms)
            expanded.append({"concept": concept, "terms": en_terms})
    for run in re.findall(r"[一-鿿]+", rq):
        terms.update(run[i:i + 2] for i in range(len(run) - 1))
    need = 3 if len(terms) >= 8 else (2 if terms else 0)
    return {"year_window": window, "terms": sorted(terms),
            "crosslingual_expansion": expanded, "hit_threshold": need}


def screen(trusted, rq):
    crit = derive_criteria(rq)
    window, terms, need = crit["year_window"], crit["terms"], crit["hit_threshold"]
    ledger, counts = [], {"included": 0, "excluded": 0, "uncertain": 0}
    for rec in trusted:
        text = " ".join([rec["title"], rec["abstract"], rec["venue"]]).lower()
        hits = [t for t in terms if t in text]
        if window and rec["year"] and not (window[0] <= rec["year"] <= window[1]):
            disp, codes = "exclude", ["year_out_of_window:%s!in:%s" % (rec["year"], window)]
        elif need and len(hits) >= need:
            disp, codes = "include", ["term_hits:%d>=%d" % (len(hits), need)]
        elif hits:
            disp, codes = "uncertain", ["weak_term_hits:%d<%d" % (len(hits), need)]
        else:
            disp, codes = "exclude", ["no_term_hits"]
        if rec["year"] is None:
            codes.append("year_missing:无法核验年份窗")
        for w in rec.get("metadata_warnings", []):
            codes.append("metadata_warning:" + w)
        counts[{"include": "included", "exclude": "excluded"}.get(disp, "uncertain")] += 1
        ledger.append({"rid": rec["rid"], "disposition": disp, "reason_codes": codes,
                       "matched_terms": hits, "title": rec["title"], "year": rec["year"],
                       "doi": rec["doi"], "source_file": rec["rid"].split("::")[0]})
    return ledger, counts, crit


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
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def main():
    ap = argparse.ArgumentParser(
        description="信任门之后的轻量筛查与 result.json 契约装配")
    ap.add_argument("--case", required=True)
    ap.add_argument("--work", required=True, help="forensics.py 的产物目录")
    ap.add_argument("--out", required=True, help="交付目录，如 /app/output")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    case = {}
    if os.path.isfile(args.case):
        try:
            case = load_json(args.case)
        except Exception:
            pass
    fields = contract_fields(case)

    def write_result(result):
        result.setdefault("case_id", case.get("case_id"))
        result.setdefault("status", "blocked")
        result.setdefault("sources", [])
        notes = result.get("field_notes") or {}
        for f in fields:
            if f not in result:
                result[f] = []
                result["uncertainty"].append(
                    "output_contract 字段 %s 无对应产物，留空待补" % f)
            if result.get(f) in ([], "", {}) and f not in ("uncertainty",):
                notes[f] = ("本字段为空的原因已在 uncertainty 中说明"
                            if any(f in u for u in result["uncertainty"]) else
                            "本次运行无此类条目（如实留空，非遗漏）")
        result["field_notes"] = notes
        with open(os.path.join(args.out, "result.json"), "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)

    # ---- 前置产物核验（不过则诚实 blocked，exit=1）----
    need_files = ["forensics_report.json", "trusted_records.jsonl",
                  "quarantine.jsonl", "metadata_forensics.json"]
    missing = [n for n in need_files
               if not os.path.isfile(os.path.join(args.work, n))]
    if missing:
        write_result({
            "uncertainty": ["forensics.py 前置产物缺失，无法筛查: %s；"
                            "请先运行 forensics.py" % ", ".join(missing)],
            "summary": "取证产物缺失，交付 blocked 骨架",
        })
        print(json.dumps({"ok": False, "status": "blocked",
                          "reason": "missing forensics artifacts: %s" % missing},
                         ensure_ascii=False))
        sys.exit(1)

    report = load_json(os.path.join(args.work, "forensics_report.json"))
    trusted = load_jsonl(os.path.join(args.work, "trusted_records.jsonl"))
    quarantine = load_jsonl(os.path.join(args.work, "quarantine.jsonl"))
    meta = load_json(os.path.join(args.work, "metadata_forensics.json"))

    ledger, counts, crit = screen(trusted, case.get("research_question"))
    candidates = [{"rid": l["rid"], "title": l["title"], "year": l["year"],
                   "doi": l["doi"], "matched_terms": l["matched_terms"],
                   "source": l["source_file"]}
                  for l in ledger if l["disposition"] == "include"]

    # ---- integrity_report：一等公民字段 ----
    integrity = {
        "files": [{"path": f["path"], "sha256": f.get("sha256"),
                   "bytes": f.get("bytes"), "format": f.get("format"),
                   "record_count": f.get("record_count", 0),
                   "anomalies": len(f.get("anomalies", [])),
                   "parse_error": f.get("parse_error")}
                  for f in report.get("files", [])],
        "totals": report.get("totals", {}),
        "quarantine_by_category": report.get("totals", {}).get(
            "quarantine_by_category", {}),
        "metadata_forensics": {k: meta.get(k) for k in
                               ("status", "origin", "total", "authentic",
                                "mismatch", "absent", "note") if k in meta},
        "artifacts": {"work": ["forensics_report.json", "trusted_records.jsonl",
                               "quarantine.jsonl", "metadata_forensics.json"],
                      "out": ["result.json", "ledger.jsonl", "candidates.json"]},
    }

    # ---- uncertainty 汇总（诚实 partial 的依据）----
    uncertainty = list(report.get("problems", []))
    for f in report.get("files", []):
        if f.get("parse_error"):
            uncertainty.append("文件 %s 解析失败: %s" % (f["path"], f["parse_error"]))
        for a in f.get("anomalies", []):
            uncertainty.append("文件 %s 异常行 %s (%s): %s"
                               % (f["path"], a.get("at"), a.get("kind"), a.get("detail")))
    for q in quarantine:
        if q["category"] == "fixture_conflict_opinion":
            uncertainty.append("冲突意见夹具 %s（%s）已登记为争议证据，本技能不做学术裁决"
                               % (q["qid"], q["rid"]))
    if meta.get("status") == "no_reference_list":
        uncertainty.append(meta["note"])
    for p in meta.get("papers", []):
        if p["verdict"] == "absent":
            uncertainty.append("清单文献 %s 在快照中缺失（absent）" % p["ref_id"])
        elif p["verdict"] == "mismatch":
            uncertainty.append("清单文献 %s 元数据与快照不一致（mismatch）: %s"
                               % (p["ref_id"], p.get("detail", "")))
    if counts["uncertain"]:
        uncertainty.append("%d 条可信记录处置为 uncertain（弱命中），需人工复核"
                           % counts["uncertain"])

    totals = report.get("totals", {})
    if totals.get("records_parsed", 0) == 0:
        status = "blocked"
        uncertainty.append("快照解析后零记录：有限快照之外的世界不存在，不补造文献")
    else:
        status = "partial" if uncertainty else "complete"

    omissions = ([{"rid": q["rid"], "qid": q["qid"], "reason": q["note"]}
                  for q in quarantine] +
                 [{"ref_id": p["ref_id"], "reason": "署名清单文献在快照中缺失"}
                  for p in meta.get("papers", []) if p["verdict"] == "absent"])

    result = {
        "case_id": case.get("case_id"),
        "summary": ("取证：%d 个文件（sha256 已登记），解析 %d 条记录；信任门放行 %d 条、"
                    "隔离 %d 条（%s）；清单法证 authentic %d / mismatch %d / absent %d；"
                    "筛查：纳入 %d / 排除 %d / 待复核 %d"
                    % (totals.get("files_seen", 0), totals.get("records_parsed", 0),
                       totals.get("records_trusted", 0),
                       totals.get("records_quarantined", 0),
                       json.dumps(totals.get("quarantine_by_category", {}),
                                  ensure_ascii=False),
                       meta.get("authentic", 0), meta.get("mismatch", 0),
                       meta.get("absent", 0),
                       counts["included"], counts["excluded"], counts["uncertain"])),
        "candidates": candidates,
        "screening_log": ledger,
        "integrity_report": integrity,
        "quarantine_register": quarantine,
        "omissions": omissions,
        "status": status,
        "sources": ([{"kind": "file", "path": f["path"], "sha256": f.get("sha256")}
                     for f in report.get("files", []) if f.get("record_count")] +
                    [{"kind": "artifact", "path": n}
                     for n in ("ledger.jsonl", "candidates.json")]),
        "uncertainty": uncertainty,
        "method": "b-snapshot-forensics: forensics(指纹/解析/隔离/法证) → gated_screen(信任门后筛查+契约装配)",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    write_result(result)

    with open(os.path.join(args.out, "ledger.jsonl"), "w", encoding="utf-8") as fh:
        for row in ledger:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    with open(os.path.join(args.out, "candidates.json"), "w", encoding="utf-8") as fh:
        json.dump({"criteria": crit, "counts": counts, "candidates": candidates},
                  fh, ensure_ascii=False, indent=2)

    print(json.dumps({"ok": status != "blocked", "status": status,
                      "trusted": len(trusted), "candidates": len(candidates),
                      "quarantined": len(quarantine),
                      "uncertainty_items": len(uncertainty)}, ensure_ascii=False))
    sys.exit(2 if status == "blocked" else 0)


if __name__ == "__main__":
    main()
