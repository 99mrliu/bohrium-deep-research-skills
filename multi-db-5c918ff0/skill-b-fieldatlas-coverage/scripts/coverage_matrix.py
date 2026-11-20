#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""coverage_matrix.py — 库×字段覆盖矩阵、单库独有文献识别、系统性缺口识别
与库间记录数对账，并把结果渲染为 coverage_report.md。

输入：
  --cards        field_cards.jsonl（map_fields.py 产出，必填）
  --map-report   map_report.json（对账/丢弃留痕，可选）
  --ledger       status_ledger.json（状态台账摘要，可选，用于渲染报告）
  --template     报告模板（默认 ../templates/coverage_report.md）
  --case-id      覆盖 case_id（默认从 --summary 或占位）

输出：
  /app/work/coverage_matrix.json   机器可读结果（矩阵/独有/缺口/对账/撤回）
  /app/work/coverage_report.md     渲染报告（模板占位符替换）

聚类口径（最小必要，不做模糊匹配——模糊去重属 identitymerge-dedup-engine 方向）：
  优先 DOI（小写化）精确聚类；无 DOI 时按 归一题名+年份 精确聚类；
  cluster_key 相同的记录视为同一论文的跨库副本。

退出码：0=完成；2=卡片缺失或为空（材料不足）；3=输入非法。
"""
import argparse
import json
import os
import sys
import time

FIELDS = [
    "identifiers.doi", "identifiers.pmid", "identifiers.pmcid",
    "title", "authors", "container", "year", "volume", "issue", "pages",
    "type", "abstract", "pub_date", "cited_by", "references", "license",
    "status",
]
STATUSES = ("present", "missing", "unknown", "not_provided")
SOURCE_PRIORITY = ["crossref", "europepmc", "publisher", "recordlist",
                   "jsonl", "csv", "unknown"]


def read_cards(path):
    cards = []
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                cards.append(json.loads(ln))
    return cards


def src_order(sources):
    return sorted(sources,
                  key=lambda s: (SOURCE_PRIORITY.index(s)
                                 if s in SOURCE_PRIORITY else len(SOURCE_PRIORITY), s))


def build(cards, map_report):
    sources = src_order({c.get("source") for c in cards})
    matrix = {s: {fld: {st: 0 for st in STATUSES} for fld in FIELDS}
              for s in sources}
    clusters = {}
    for c in cards:
        s = c.get("source")
        for fld in FIELDS:
            st = (c.get("fields", {}).get(fld) or {}).get("status", "missing")
            if st not in STATUSES:
                st = "missing"
            if s in matrix:
                matrix[s][fld][st] += 1
        ck = c.get("cluster_key")
        cl = clusters.setdefault(ck, {
            "cluster_key": ck, "sources": set(), "records": 0,
            "title": None, "year": None, "doi": None, "retracted": False})
        cl["sources"].add(s)
        cl["records"] += 1
        if not cl["title"]:
            cl["title"] = (c.get("fields", {}).get("title") or {}).get("value")
        if not cl["year"]:
            cl["year"] = (c.get("fields", {}).get("year") or {}).get("value")
        if not cl["doi"]:
            cl["doi"] = (c.get("fields", {}).get("identifiers.doi") or {}).get("value")
        cl["retracted"] = cl["retracted"] or bool(c.get("retracted"))

    single_source = [
        {"cluster_key": cl["cluster_key"], "source": sorted(cl["sources"])[0],
         "title": cl["title"], "year": cl["year"], "doi": cl["doi"],
         "retracted": cl["retracted"]}
        for cl in clusters.values() if len(cl["sources"]) == 1
    ]
    single_source.sort(key=lambda x: (x["source"], x["cluster_key"]))

    total_records = len(cards)
    systematic_gaps = []
    for fld in FIELDS:
        present_total = sum(matrix[s][fld]["present"] for s in sources)
        if total_records and present_total == 0:
            np_total = sum(matrix[s][fld]["not_provided"] for s in sources)
            un_total = sum(matrix[s][fld]["unknown"] for s in sources)
            mi_total = sum(matrix[s][fld]["missing"] for s in sources)
            if np_total == total_records:
                reason = "not_provided_in_all_sources"
            elif un_total > 0:
                reason = "schema_provided_but_empty_or_unparsed"
            else:
                reason = "key_absent_in_all_records"
            systematic_gaps.append({
                "field": fld, "reason": reason,
                "per_source": {s: matrix[s][fld] for s in sources},
                "note": "三个/全部来源在该字段均无 present 值，列为系统性缺口字段。"})
    systematic_gaps.sort(key=lambda g: g["field"])

    retracted_records = [
        {"cluster_key": cl["cluster_key"], "title": cl["title"],
         "doi": cl["doi"], "sources": sorted(cl["sources"])}
        for cl in clusters.values() if cl["retracted"]
    ]
    retracted_records.sort(key=lambda r: r["cluster_key"])

    reconciliation = {"per_source": {}, "grand": {"returned": 0, "parsed": 0,
                                                  "dropped": 0}}
    if map_report:
        for s, t in (map_report.get("totals") or {}).items():
            reconciliation["per_source"][s] = {
                "returned": t.get("returned", 0),
                "parsed": t.get("parsed", 0),
                "dropped": t.get("dropped", 0),
                "parse_rate": (round(t.get("parsed", 0) / t.get("returned", 1), 4)
                               if t.get("returned") else None),
            }
            for k in ("returned", "parsed", "dropped"):
                reconciliation["grand"][k] += t.get(k, 0)
        reconciliation["dropped_records"] = map_report.get("dropped_records", [])

    return {
        "sources": sources,
        "fields": FIELDS,
        "matrix": matrix,
        "total_records": total_records,
        "unique_papers": len(clusters),
        "clusters": [
            {"cluster_key": cl["cluster_key"], "sources": sorted(cl["sources"]),
             "title": cl["title"], "year": cl["year"], "doi": cl["doi"],
             "retracted": cl["retracted"]}
            for cl in sorted(clusters.values(), key=lambda c: c["cluster_key"])],
        "single_source_unique": single_source,
        "systematic_gaps": systematic_gaps,
        "retracted_records": retracted_records,
        "reconciliation": reconciliation,
    }


# ---------------------------------------------------------------- 渲染

def md_matrix(result):
    lines = ["| 字段 | 来源 | " + " | ".join(STATUSES) + " |", "|---|---|" +
             "---|" * len(STATUSES)]
    for fld in result["fields"]:
        for s in result["sources"]:
            cell = result["matrix"][s][fld]
            lines.append("| %s | %s | %s |" % (
                fld, s, " | ".join(str(cell[st]) for st in STATUSES)))
    lines.append("")
    lines.append("图例：present=来源提供且记录有非空可解析值；unknown=字段存在但为空/不可解析；"
                 "missing=载荷内其他记录有而本条缺失；not_provided=来源/载荷不提供该字段。")
    return "\n".join(lines)


def md_single_source(result):
    if not result["single_source_unique"]:
        return "（无单库独有文献：全部论文至少被两个来源覆盖。）"
    lines = ["| cluster_key | 唯一来源 | 题名 | 年份 | DOI |", "|---|---|---|---|---|"]
    for e in result["single_source_unique"]:
        lines.append("| %s | %s | %s | %s | %s |" % (
            e["cluster_key"], e["source"], e["title"] or "—", e["year"] or "—",
            e["doi"] or "—"))
    return "\n".join(lines)


def md_gaps(result):
    if not result["systematic_gaps"]:
        return "（无系统性缺口字段：每个归一字段至少一个来源有 present 值。）"
    lines = ["| 字段 | 原因 | 各来源计数(present/missing/unknown/not_provided) |",
             "|---|---|---|"]
    for g in result["systematic_gaps"]:
        per = "; ".join("%s: %d/%d/%d/%d" % (
            s, g["per_source"][s]["present"], g["per_source"][s]["missing"],
            g["per_source"][s]["unknown"], g["per_source"][s]["not_provided"])
            for s in result["sources"])
        lines.append("| %s | %s | %s |" % (g["field"], g["reason"], per))
    return "\n".join(lines)


def md_reconciliation(result):
    rec = result["reconciliation"]
    if not rec.get("per_source"):
        return "（无 map_report，无法对账。）"
    lines = ["| 来源 | 返回总数 | 解析成功 | 丢弃 | 解析率 |", "|---|---|---|---|---|"]
    for s in rec["per_source"]:
        t = rec["per_source"][s]
        lines.append("| %s | %d | %d | %d | %s |" % (
            s, t["returned"], t["parsed"], t["dropped"], t["parse_rate"]))
    g = rec["grand"]
    lines.append("| **合计** | %d | %d | %d | — |" % (
        g["returned"], g["parsed"], g["dropped"]))
    if rec.get("dropped_records"):
        lines.append("")
        lines.append("丢弃明细（逐条留痕）：")
        for d in rec["dropped_records"]:
            lines.append("- `%s` record[%s]: %s" % (
                d.get("file"), d.get("index"), d.get("reason")))
    return "\n".join(lines)


def md_retracted(result):
    if not result["retracted_records"]:
        return "（无撤回/更正标记记录。）"
    lines = ["| cluster_key | 题名 | DOI | 来源 |", "|---|---|---|---|"]
    for r in result["retracted_records"]:
        lines.append("| %s | %s | %s | %s |" % (
            r["cluster_key"], r["title"] or "—", r["doi"] or "—",
            ", ".join(r["sources"])))
    return "\n".join(lines)


def render(template_text, result, case_id, ledger):
    ledger_md = "（status_ledger.json 未提供或为空，请先运行 status_ledger.py。）"
    if ledger and ledger.get("entries"):
        rows = ["| 类别 | 条数 |", "|---|---|"]
        for k in sorted(ledger.get("summary", {})):
            rows.append("| %s | %d |" % (k, ledger["summary"][k]))
        ledger_md = "\n".join(rows)
    rep = {
        "{{CASE_ID}}": case_id,
        "{{GENERATED_AT}}": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "{{SOURCES}}": ", ".join(result["sources"]),
        "{{TOTAL_RECORDS}}": str(result["total_records"]),
        "{{UNIQUE_PAPERS}}": str(result["unique_papers"]),
        "{{MATRIX_TABLE}}": md_matrix(result),
        "{{SINGLE_SOURCE_TABLE}}": md_single_source(result),
        "{{SYSTEMATIC_GAP_TABLE}}": md_gaps(result),
        "{{RECONCILIATION_TABLE}}": md_reconciliation(result),
        "{{RETRACTED_TABLE}}": md_retracted(result),
        "{{LEDGER_SUMMARY}}": ledger_md,
    }
    out = template_text
    for k, v in rep.items():
        out = out.replace(k, v)
    return out


def main():
    ap = argparse.ArgumentParser(
        description="库×字段覆盖矩阵 + 单库独有 + 系统性缺口 + 对账（exit 0/2/3）。")
    ap.add_argument("--cards", default="/app/work/field_cards.jsonl")
    ap.add_argument("--map-report", default="/app/work/map_report.json")
    ap.add_argument("--ledger", default="/app/work/status_ledger.json")
    ap.add_argument("--template", default=None,
                    help="报告模板路径（默认 ../templates/coverage_report.md）")
    ap.add_argument("--summary", default=None, help="case_summary.json（取 case_id，可选）")
    ap.add_argument("--case-id", default=None)
    ap.add_argument("--out", default="/app/work/coverage_matrix.json")
    ap.add_argument("--md", default="/app/work/coverage_report.md")
    args = ap.parse_args()

    if not os.path.isfile(args.cards):
        print("ERROR: field_cards.jsonl 不存在（材料不足，exit 2）: %s"
              % args.cards, file=sys.stderr)
        return 2
    try:
        cards = read_cards(args.cards)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        print("ERROR: field_cards.jsonl 非法（校验失败，exit 3）: %s" % e,
              file=sys.stderr)
        return 3
    if not cards:
        print("ERROR: field_cards 为空（材料不足，诚实降级，exit 2）", file=sys.stderr)
        return 2

    map_report = None
    if os.path.isfile(args.map_report):
        try:
            with open(args.map_report, "r", encoding="utf-8") as f:
                map_report = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            map_report = None
    ledger = None
    if os.path.isfile(args.ledger):
        try:
            with open(args.ledger, "r", encoding="utf-8") as f:
                ledger = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            ledger = None

    result = build(cards, map_report)

    case_id = args.case_id
    if not case_id and args.summary and os.path.isfile(args.summary):
        try:
            with open(args.summary, "r", encoding="utf-8") as f:
                case_id = (json.load(f).get("case_id") or None)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            case_id = None
    result["case_id"] = case_id or "UNKNOWN_CASE"

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    template = args.template
    if not template:
        template = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "templates", "coverage_report.md")
    if os.path.isfile(template):
        with open(template, "r", encoding="utf-8") as f:
            template_text = f.read()
        md_out = render(template_text, result, result["case_id"], ledger)
        md_dir = os.path.dirname(os.path.abspath(args.md))
        os.makedirs(md_dir, exist_ok=True)
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(md_out)
        md_note = "; 报告 -> %s" % args.md
    else:
        md_note = "; 模板缺失，跳过 markdown 渲染"

    print("OK: 覆盖矩阵 -> %s (记录=%d, 论文=%d, 单库独有=%d, 系统性缺口=%s, "
          "撤回标记=%d)%s" % (
              args.out, result["total_records"], result["unique_papers"],
              len(result["single_source_unique"]),
              ",".join(g["field"] for g in result["systematic_gaps"]) or "无",
              len(result["retracted_records"]), md_note))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("ERROR: coverage_matrix 未捕获异常（诚实降级，exit 2）: %r" % e,
              file=sys.stderr)
        sys.exit(2)
