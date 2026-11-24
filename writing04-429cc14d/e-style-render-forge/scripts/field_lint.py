#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""field_lint.py — style-render-forge 阶段 2：字段 lint（仅标准库，确定性，无网络）。

用法：
    python3 field_lint.py --records records.json --out DIR [--roundtrip other_records.json]

规则：
    L1 必备字段（按类型）：期刊论文必备 作者/题名/刊名/年；卷期页中至少页码或文章号，
       缺失 → error 并登记占位（渲染器将输出 [缺: 页码]）。
    L2 DOI 语法：^10\.\\d{4,9}/\\S+$，不合规 → error。
    L3 页码范围格式：^\\d+([-–]\\d+)?$（单页合法），不合规 → error。
    L4 作者姓名格式：检出全小写拉丁姓名、名缩写可疑形式 → warning；
       >3 作者提示 GB/T 将用“等/et al.”省略 → info。
    L5 类型标识存在且与类型匹配（journal-article↔[J] 等），缺失/不符 → error。
    L6 年份为 4 位且在 [1900, 2100] → 否则 error（缺年由 L1 负责）。
    L7 中英混排标点：中文条目（题名/刊名含 CJK）检出 CJK 紧邻半角标点 → warning；
       西文条目检出全角句读 → warning。
    L8 往返稳定：--roundtrip 给出第二份 records.json，对规范化核心字段做字段级 diff，
       任何差异 → error。

输出 DIR/lint_report.json 与 DIR/lint_report.md；存在 error 级发现时退出码 1，否则 0。
"""
import argparse
import json
import os
import re
import sys

DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
PAGES_RE = re.compile(r"^\d+([-–]\d+)?$")
YEAR_RE = re.compile(r"^\d{4}$")
CJK_RE = re.compile(r"[一-鿿]")
CJK_HALF_PUNCT = re.compile(r"[一-鿿][,;:!?()]|[,;:!?()][一-鿿]")
FULLWIDTH_PUNCT = re.compile(r"[，。；：（）【】]")

TYPE_REQUIRED = {
    "journal-article": ["authors", "title", "venue", "year"],
    "book": ["authors", "title", "year", "publisher"],
    "inproceedings": ["authors", "title", "venue", "year"],
    "incollection": ["authors", "title", "venue", "year"],
    "thesis": ["authors", "title", "year", "publisher"],
    "report": ["authors", "title", "year", "publisher"],
    "electronic": ["title", "url"],
    "newspaper": ["authors", "title", "venue", "year"],
    "misc": ["title"],
}

TYPE_TAG_EXPECTED = {
    "journal-article": "J", "book": "M", "inproceedings": "C",
    "incollection": "A", "thesis": "D", "report": "R",
    "electronic": "EB/OL", "newspaper": "N", "misc": None,
}

FIELD_LABEL = {
    "authors": "作者", "title": "题名", "venue": "刊名/来源", "year": "年份",
    "volume": "卷", "issue": "期", "pages": "页码", "article_number": "文章号",
    "publisher": "出版者", "address": "出版地", "doi": "DOI", "url": "网址",
}

ROUNDTRIP_FIELDS = [
    "id", "type", "authors", "editors", "title", "title_alt", "year", "venue",
    "volume", "issue", "pages", "article_number", "publisher", "address",
    "doi", "url", "isbn", "language", "type_tag",
]


def _label(field):
    return FIELD_LABEL.get(field, field)


def _find(findings, rule, severity, rid, field, message):
    findings.append({
        "rule": rule, "severity": severity, "record_id": rid,
        "field": field, "message": message,
    })


def lint_record(rec, findings):
    rid = rec.get("id", "?")
    rtype = rec.get("type") or "misc"

    # L1 必备字段
    for field in TYPE_REQUIRED.get(rtype, TYPE_REQUIRED["misc"]):
        val = rec.get(field)
        missing = (val is None) or (isinstance(val, (list, str)) and not val)
        if missing:
            _find(findings, "L1", "error", rid, field,
                  f"{rtype} 缺必备字段 [{_label(field)}]，渲染将输出占位符 [缺: {_label(field)}]，"
                  f"不得凭记忆补齐")
    if rtype == "journal-article":
        if not rec.get("pages") and not rec.get("article_number"):
            _find(findings, "L1", "error", rid, "pages",
                  "期刊论文既无页码也无文章号，渲染将输出占位符 [缺: 页码]")
        for opt in ("volume", "issue"):
            if not rec.get(opt):
                _find(findings, "L1", "warning", rid, opt,
                      f"期刊论文缺 [{_label(opt)}]，渲染时按现有字段省略该段")

    # L2 DOI 语法
    doi = rec.get("doi")
    if doi and not DOI_RE.match(doi):
        _find(findings, "L2", "error", rid, "doi",
              f"DOI `{doi}` 不符合 ^10.\\d{{4,9}}/ 语法，保留原值待人工核验")

    # L3 页码范围
    pages = rec.get("pages")
    if pages and not PAGES_RE.match(pages.strip()):
        _find(findings, "L3", "error", rid, "pages",
              f"页码 `{pages}` 非标准范围格式（应为 数字[-–数字]，单页合法），保留原值")

    # L4 作者姓名格式
    authors = rec.get("authors") or []
    for a in authors:
        if not CJK_RE.search(a) and re.search(r"[A-Za-z]", a):
            if a == a.lower():
                _find(findings, "L4", "warning", rid, "authors",
                      f"作者 `{a}` 全小写，疑似姓名格式异常，保留原样不改写")
            elif "," not in a:
                toks = a.split()
                if len(toks) >= 2 and toks[0][0].islower():
                    _find(findings, "L4", "warning", rid, "authors",
                          f"作者 `{a}` 首词小写，疑似姓/名顺序或大小写异常，保留原样不改写")
    if len(authors) > 3:
        _find(findings, "L4", "info", rid, "authors",
              f"作者共 {len(authors)} 名，GB/T 7714 渲染将列前 3 名后加 等/et al.，"
              f"导出格式保留全部作者")

    # L5 类型标识
    expected = TYPE_TAG_EXPECTED.get(rtype)
    tag = rec.get("type_tag")
    if expected is None:
        if not tag:
            _find(findings, "L5", "warning", rid, "type_tag",
                  f"类型 {rtype} 无标准文献类型标识，渲染将按 [Z]（其他）处理并在报告中标注")
    elif tag != expected:
        _find(findings, "L5", "error", rid, "type_tag",
              f"类型 {rtype} 应配标识 [{expected}]，实际为 {('[' + tag + ']') if tag else '缺失'}")

    # L6 年份
    year = rec.get("year")
    if year is not None:
        if not YEAR_RE.match(str(year)):
            _find(findings, "L6", "error", rid, "year",
                  f"年份 `{year}` 非 4 位数字")
        elif not (1900 <= int(year) <= 2100):
            _find(findings, "L6", "error", rid, "year",
                  f"年份 {year} 超出合理区间 [1900, 2100]，保留原值待核验")

    # L7 中英混排标点
    zh_entry = bool(CJK_RE.search((rec.get("title") or "") + (rec.get("venue") or "")))
    for field in ("title", "venue"):
        val = rec.get(field)
        if not val:
            continue
        if zh_entry and CJK_HALF_PUNCT.search(val):
            _find(findings, "L7", "warning", rid, field,
                  f"中文条目 `{_label(field)}` 检出 CJK 紧邻半角标点: `{val}`，"
                  f"lint 不改写原文，请人工确认是否应全角化")
        if not zh_entry and FULLWIDTH_PUNCT.search(val):
            _find(findings, "L7", "warning", rid, field,
                  f"西文条目 `{_label(field)}` 检出全角标点: `{val}`，保留原样")


def roundtrip_diff(recs_a, recs_b, findings):
    map_a = {r.get("id"): r for r in recs_a}
    map_b = {r.get("id"): r for r in recs_b}
    for rid in sorted(set(map_a) | set(map_b)):
        if rid not in map_a:
            _find(findings, "L8", "error", rid, "-", "往返后多出记录")
            continue
        if rid not in map_b:
            _find(findings, "L8", "error", rid, "-", "往返后丢失记录")
            continue
        ra, rb = map_a[rid], map_b[rid]
        for f in ROUNDTRIP_FIELDS:
            va, vb = ra.get(f), rb.get(f)
            if va != vb:
                _find(findings, "L8", "error", rid, f,
                      f"往返字段级 diff: `{f}` 由 {va!r} 变为 {vb!r}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="style-render-forge 字段 lint")
    ap.add_argument("--records", required=True, help="records.json 路径")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--roundtrip", help="第二份 records.json，触发 L8 往返 diff")
    args = ap.parse_args(argv)

    with open(args.records, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    records = payload.get("records", [])

    findings = []
    for rec in records:
        lint_record(rec, findings)

    if args.roundtrip:
        with open(args.roundtrip, "r", encoding="utf-8") as fh:
            other = json.load(fh).get("records", [])
        roundtrip_diff(records, other, findings)

    sev_order = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: (sev_order.get(f["severity"], 3),
                                 f["rule"], f["record_id"], f["field"]))
    n_err = sum(1 for f in findings if f["severity"] == "error")
    n_warn = sum(1 for f in findings if f["severity"] == "warning")
    n_info = sum(1 for f in findings if f["severity"] == "info")

    os.makedirs(args.out, exist_ok=True)
    report = {
        "schema": "style-render-forge/lint-report/v1",
        "records_file": os.path.basename(args.records),
        "record_count": len(records),
        "roundtrip_file": os.path.basename(args.roundtrip) if args.roundtrip else None,
        "summary": {"error": n_err, "warning": n_warn, "info": n_info,
                    "exit_code": 1 if n_err else 0},
        "findings": findings,
    }
    with open(os.path.join(args.out, "lint_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    lines = [
        "# lint 报告（field_lint.py L1–L8）",
        "",
        f"- records 文件: `{os.path.basename(args.records)}`（{len(records)} 条）",
        f"- 往返对照: {('`' + os.path.basename(args.roundtrip) + '`') if args.roundtrip else '未执行'}",
        f"- 结论: error {n_err} / warning {n_warn} / info {n_info}"
        f" → 退出码 {1 if n_err else 0}",
        "",
        "| 规则 | 级别 | 记录 | 字段 | 说明 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for f in findings:
        lines.append(f"| {f['rule']} | {f['severity']} | {f['record_id']} "
                     f"| {f['field']} | {f['message'].replace('|', '｜')} |")
    if not findings:
        lines.append("| - | - | - | - | 无任何发现 |")
    lines.append("")
    with open(os.path.join(args.out, "lint_report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    print(json.dumps(report["summary"], ensure_ascii=False))
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
