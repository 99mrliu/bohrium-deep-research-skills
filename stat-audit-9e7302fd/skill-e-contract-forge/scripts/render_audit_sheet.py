#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_audit_sheet.py — 审查单渲染器（bundle E / contract-forge-audit）。

把 findings JSONL 渲染成同源三件套，杜绝交付物漂移：
  (a) audit_sheet.md    —— 按严重度→facet 分组，含汇总计数表与「待复核/未解决」专区；
  (b) audit_sheet.html  —— 自包含（内联 CSS、无外部资源、UTF-8）可视化预览；
  (c) audit_findings.json —— 机器可读 findings 数据（供填入 result.json）。

输入每行一个 JSON 对象，必备键：
  id, facet, category, severity, location, quote, message, fix, status
约定取值：
  severity ∈ {critical, major, minor, suggestion}
  category ∈ {事实错误, 证据不足, 规范问题, 建议}
  status   ∈ {open, resolved, 待复核}
无效行带行号拒绝；存在任何无效行时以非零码退出且不产出文件。
仅依赖 Python 标准库。
"""
import argparse
import html
import json
import os
import sys

REQUIRED_KEYS = ["id", "facet", "category", "severity", "location",
                 "quote", "message", "fix", "status"]
SEVERITIES = ["critical", "major", "minor", "suggestion"]
CATEGORIES = ["事实错误", "证据不足", "规范问题", "建议"]
STATUSES = ["open", "resolved", "待复核"]
SEVERITY_ZH = {"critical": "致命", "major": "严重", "minor": "次要",
               "suggestion": "建议"}


def eprint(msg):
    print("render_audit_sheet: %s" % msg, file=sys.stderr)


def load_findings(path):
    if not os.path.isfile(path):
        eprint("ERROR: findings 文件不存在: %s" % path)
        sys.exit(2)
    findings, errors = [], []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        eprint("ERROR: findings 文件读取失败: %s (%s)" % (path, exc))
        sys.exit(2)
    for lineno, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append("第 %d 行: JSON 解析失败 (%s)" % (lineno, exc))
            continue
        if not isinstance(row, dict):
            errors.append("第 %d 行: 必须是 JSON 对象" % lineno)
            continue
        missing = [k for k in REQUIRED_KEYS if k not in row]
        if missing:
            errors.append("第 %d 行: 缺少必备键 %s" % (lineno, ", ".join(missing)))
            continue
        bad = [k for k in REQUIRED_KEYS if not isinstance(row[k], str) or not row[k].strip()]
        if bad:
            errors.append("第 %d 行: 键 %s 必须为非空字符串" % (lineno, ", ".join(bad)))
            continue
        if row["severity"] not in SEVERITIES:
            errors.append("第 %d 行: severity %r 非法，应为 %s"
                          % (lineno, row["severity"], "/".join(SEVERITIES)))
        if row["category"] not in CATEGORIES:
            errors.append("第 %d 行: category %r 非法，应为 %s"
                          % (lineno, row["category"], "/".join(CATEGORIES)))
        if row["status"] not in STATUSES:
            errors.append("第 %d 行: status %r 非法，应为 %s"
                          % (lineno, row["status"], "/".join(STATUSES)))
        findings.append({k: row[k].strip() for k in REQUIRED_KEYS})
    if errors:
        for err in errors:
            eprint("INVALID: %s" % err)
        eprint("ERROR: 共 %d 处输入错误，未产出任何文件。" % len(errors))
        sys.exit(1)
    if not findings:
        eprint("ERROR: findings 文件为空（无有效行）。")
        sys.exit(1)
    return findings


def summarize(findings):
    sev = {s: 0 for s in SEVERITIES}
    cat = {c: 0 for c in CATEGORIES}
    st = {s: 0 for s in STATUSES}
    for f in findings:
        sev[f["severity"]] += 1
        cat[f["category"]] += 1
        st[f["status"]] += 1
    return sev, cat, st


def render_md(findings, source_name):
    sev, cat, st = summarize(findings)
    out = []
    out.append("# 审查单（audit_sheet）")
    out.append("")
    out.append("> 由 render_audit_sheet.py 从 `%s` 同源渲染；"
               "与 audit_sheet.html / audit_findings.json 数据一致。" % source_name)
    out.append("")
    out.append("## 汇总")
    out.append("")
    out.append("| 维度 | 取值 | 数量 |")
    out.append("| --- | --- | --- |")
    for s in SEVERITIES:
        out.append("| 严重度 | %s (%s) | %d |" % (s, SEVERITY_ZH[s], sev[s]))
    for c in CATEGORIES:
        out.append("| 缺陷类型 | %s | %d |" % (c, cat[c]))
    for s in STATUSES:
        out.append("| 处置状态 | %s | %d |" % (s, st[s]))
    out.append("")
    out.append("## 明细（按严重度 → 审查面分组）")
    for s in SEVERITIES:
        group = [f for f in findings if f["severity"] == s]
        if not group:
            continue
        out.append("")
        out.append("### %s %s（%d 条）" % (s, SEVERITY_ZH[s], len(group)))
        facets = sorted({f["facet"] for f in group})
        for facet in facets:
            out.append("")
            out.append("#### %s" % facet)
            for f in [g for g in group if g["facet"] == facet]:
                out.append("")
                out.append("- **[%s] %s**（%s / %s）"
                           % (f["id"], f["message"], f["category"], f["status"]))
                out.append("  - 原文位置: %s" % f["location"])
                out.append("  - 原文引用: 「%s」" % f["quote"])
                out.append("  - 依据/说明: %s" % f["message"])
                out.append("  - 修改建议: %s" % f["fix"])
    pending = [f for f in findings if f["status"] in ("待复核", "open")]
    out.append("")
    out.append("## 待复核 / 未解决")
    out.append("")
    if pending:
        out.append("| id | 状态 | 严重度 | 位置 | 问题 |")
        out.append("| --- | --- | --- | --- | --- |")
        for f in pending:
            out.append("| %s | %s | %s | %s | %s |"
                       % (f["id"], f["status"], f["severity"],
                          f["location"], f["message"]))
    else:
        out.append("（无）")
    out.append("")
    return "\n".join(out)


def render_html(findings, source_name):
    sev, cat, st = summarize(findings)
    esc = html.escape
    rows = []
    for f in findings:
        rows.append(
            "<tr class='sev-%(s)s'><td>%(id)s</td><td>%(facet)s</td>"
            "<td>%(cat)s</td><td><span class='badge sev-%(s)s'>%(s)s</span></td>"
            "<td>%(loc)s</td><td class='quote'>%(quote)s</td><td>%(msg)s</td>"
            "<td>%(fix)s</td><td>%(st)s</td></tr>" % {
                "s": esc(f["severity"]), "id": esc(f["id"]),
                "facet": esc(f["facet"]), "cat": esc(f["category"]),
                "loc": esc(f["location"]), "quote": esc(f["quote"]),
                "msg": esc(f["message"]), "fix": esc(f["fix"]),
                "st": esc(f["status"])})
    summary_rows = []
    for s in SEVERITIES:
        summary_rows.append("<tr><td>严重度</td><td>%s (%s)</td><td>%d</td></tr>"
                            % (s, SEVERITY_ZH[s], sev[s]))
    for c in CATEGORIES:
        summary_rows.append("<tr><td>缺陷类型</td><td>%s</td><td>%d</td></tr>"
                            % (esc(c), cat[c]))
    for s in STATUSES:
        summary_rows.append("<tr><td>处置状态</td><td>%s</td><td>%d</td></tr>"
                            % (esc(s), st[s]))
    pending = [f for f in findings if f["status"] in ("待复核", "open")]
    pending_items = "".join(
        "<li><b>%s</b>（%s / %s）%s — %s</li>"
        % (esc(f["id"]), esc(f["status"]), esc(f["severity"]),
           esc(f["location"]), esc(f["message"])) for f in pending) or "<li>（无）</li>"
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>审查单 audit_sheet</title>
<style>
body{{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;margin:2em;color:#222}}
h1{{border-bottom:2px solid #444;padding-bottom:.3em}}
table{{border-collapse:collapse;width:100%;margin:1em 0;font-size:14px}}
th,td{{border:1px solid #ccc;padding:6px 8px;vertical-align:top;text-align:left}}
th{{background:#f0f0f0}}
.quote{{color:#555;font-style:italic}}
.badge{{padding:1px 6px;border-radius:4px;color:#fff;font-size:12px}}
.badge.sev-critical{{background:#c0392b}}.badge.sev-major{{background:#e67e22}}
.badge.sev-minor{{background:#f1c40f;color:#333}}.badge.sev-suggestion{{background:#7f8c8d}}
tr.sev-critical{{background:#fdecea}}tr.sev-major{{background:#fdf3e7}}
.meta{{color:#666;font-size:13px}}
</style>
</head>
<body>
<h1>审查单（audit_sheet）</h1>
<p class="meta">由 render_audit_sheet.py 从 <code>{src}</code> 同源渲染，共 {n} 条发现。
本文件自包含（无外部资源），可直接用浏览器打开检查。</p>
<h2>汇总</h2>
<table><thead><tr><th>维度</th><th>取值</th><th>数量</th></tr></thead>
<tbody>{summary}</tbody></table>
<h2>明细</h2>
<table><thead><tr><th>id</th><th>审查面</th><th>缺陷类型</th><th>严重度</th>
<th>原文位置</th><th>原文引用</th><th>依据/说明</th><th>修改建议</th><th>状态</th></tr></thead>
<tbody>{rows}</tbody></table>
<h2>待复核 / 未解决</h2>
<ul>{pending}</ul>
</body>
</html>
""".format(src=esc(source_name), n=len(findings),
           summary="\n".join(summary_rows), rows="\n".join(rows),
           pending=pending_items)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="把 findings JSONL 同源渲染为 audit_sheet.md / audit_sheet.html / "
                    "audit_findings.json 三件套。")
    ap.add_argument("findings", help="findings JSONL 路径")
    ap.add_argument("--outdir", default=".", help="输出目录（默认当前目录）")
    ap.add_argument("--out-md", default=None, help="audit_sheet.md 输出路径")
    ap.add_argument("--out-html", default=None, help="audit_sheet.html 输出路径")
    ap.add_argument("--out-json", default=None, help="audit_findings.json 输出路径")
    args = ap.parse_args(argv)

    findings = load_findings(args.findings)
    os.makedirs(args.outdir, exist_ok=True)
    out_md = args.out_md or os.path.join(args.outdir, "audit_sheet.md")
    out_html = args.out_html or os.path.join(args.outdir, "audit_sheet.html")
    out_json = args.out_json or os.path.join(args.outdir, "audit_findings.json")

    source_name = os.path.basename(args.findings)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(render_md(findings, source_name))
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(render_html(findings, source_name))
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({"source": source_name, "count": len(findings),
                   "findings": findings}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    eprint("OK: %d 条发现 → %s, %s, %s" % (len(findings), out_md, out_html, out_json))
    return 0


if __name__ == "__main__":
    sys.exit(main())
