#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_report.py — 自包含 HTML 审计报告渲染器（纯 Python3 标准库，离线）。

产出（写入 --output-dir）：
  * audit_report.html       单文件、内联 CSS、无外部资源/JS；所有内容 html.escape；
  * audit_report_preview.txt 同内容的纯文本速览。

版面：页头（case_id / status / 生成说明）→ 主结果（任意嵌套 dict/list 通用
递归渲染）→ evidence 表（若存在）→ uncertainties → change_records →
partial_limits。供第二人并排检视“结果—证据—不确定性—变更历史”。
"""
import argparse
import datetime
import html
import json
import os
import sys

CSS = """
body{font-family:-apple-system,"Helvetica Neue","PingFang SC","Microsoft YaHei",
sans-serif;margin:0;background:#f5f6f8;color:#1f2329;line-height:1.55}
.wrap{max-width:1080px;margin:0 auto;padding:24px}
header{background:#1f3a5f;color:#fff;padding:20px 28px;border-radius:10px;
margin-bottom:18px}
header h1{margin:0 0 6px;font-size:20px}
header .meta{font-size:13px;opacity:.9}
.badge{display:inline-block;padding:2px 10px;border-radius:12px;font-size:13px;
font-weight:600;margin-left:8px;vertical-align:middle}
.badge-success{background:#2e7d32}.badge-partial{background:#f9a825;color:#222}
.badge-failed{background:#c62828}.badge-unknown{background:#666}
section{background:#fff;border:1px solid #e3e6ea;border-radius:10px;
padding:16px 20px;margin-bottom:16px}
h2{font-size:16px;margin:0 0 10px;border-left:4px solid #1f3a5f;padding-left:8px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border:1px solid #dfe3e8;padding:6px 9px;text-align:left;
vertical-align:top;word-break:break-word}
th{background:#eef1f5}
blockquote{margin:6px 0;padding:6px 12px;border-left:3px solid #90a4ae;
background:#fafbfc;color:#37474f;font-size:13px}
.kv{font-size:13px}.kv b{color:#1f3a5f}
ul{margin:6px 0;padding-left:20px}
pre{background:#f6f8fa;border:1px solid #e3e6ea;border-radius:6px;
padding:8px 10px;font-size:12px;overflow-x:auto;white-space:pre-wrap}
.small{font-size:12px;color:#666}
"""

RESERVED = ("case_id", "status", "evidence", "uncertainties",
            "change_records", "partial_limits")


def esc(x):
    return html.escape(str(x), quote=True)


def render_value_html(val, depth=0):
    """通用递归渲染 dict/list/标量为 HTML。"""
    if isinstance(val, dict):
        if not val:
            return '<span class="small">（空对象）</span>'
        rows = "".join(
            "<tr><th style=\"width:22%%\">%s</th><td>%s</td></tr>"
            % (esc(k), render_value_html(v, depth + 1))
            for k, v in val.items())
        return "<table>%s</table>" % rows
    if isinstance(val, list):
        if not val:
            return '<span class="small">（空列表）</span>'
        if all(not isinstance(x, (dict, list)) for x in val):
            return "<ul>%s</ul>" % "".join(
                "<li>%s</li>" % esc(x) for x in val)
        return "<ol>%s</ol>" % "".join(
            "<li>%s</li>" % render_value_html(x, depth + 1) for x in val)
    if val is None:
        return '<span class="small">null</span>'
    if isinstance(val, bool):
        return esc("true" if val else "false")
    return esc(val)


def evidence_table_html(evidence):
    if not isinstance(evidence, list) or not evidence:
        return '<p class="small">无 evidence 记录。</p>'
    cols = []
    for row in evidence:
        if isinstance(row, dict):
            for k in row.keys():
                if k not in cols:
                    cols.append(k)
    if not cols:
        return '<p class="small">evidence 记录为空。</p>'
    head = "".join("<th>%s</th>" % esc(c) for c in cols)
    body = []
    for row in evidence:
        if not isinstance(row, dict):
            body.append("<tr><td colspan=\"%d\">%s</td></tr>"
                        % (len(cols), esc(row)))
            continue
        tds = []
        for c in cols:
            cell = row.get(c, "")
            if c in ("quote", "evidence_quote", "excerpt") and isinstance(cell, str):
                tds.append("<td><blockquote>%s</blockquote></td>" % esc(cell))
            else:
                tds.append("<td>%s</td>" % render_value_html(cell))
        body.append("<tr>%s</tr>" % "".join(tds))
    return "<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (
        head, "".join(body))


def simple_list_html(items):
    if not items:
        return '<p class="small">无。</p>'
    if isinstance(items, list):
        return "<ul>%s</ul>" % "".join(
            "<li>%s</li>" % render_value_html(x) for x in items)
    return render_value_html(items)


def change_records_html(records):
    if not isinstance(records, list) or not records:
        return '<p class="small">无变更记录。</p>'
    head = ("<tr><th>#</th><th>target_path</th><th>old_value</th>"
            "<th>new_value</th><th>reviewer</th><th>rationale</th>"
            "<th>date</th></tr>")
    rows = []
    for i, r in enumerate(records, 1):
        if not isinstance(r, dict):
            rows.append("<tr><td>%d</td><td colspan=\"6\">%s</td></tr>"
                        % (i, esc(r)))
            continue
        rows.append(
            "<tr><td>%d</td><td><code>%s</code></td><td>%s</td><td>%s</td>"
            "<td>%s</td><td>%s</td><td>%s</td></tr>"
            % (i, esc(r.get("target_path", "")),
               render_value_html(r.get("old_value")),
               render_value_html(r.get("new_value")),
               esc(r.get("reviewer", "")), esc(r.get("rationale", "")),
               esc(r.get("date", ""))))
    return "<table><thead>%s</thead><tbody>%s</tbody></table>" % (
        head, "".join(rows))


def render_html(result, generated_at):
    status = result.get("status", "unknown")
    badge = '<span class="badge badge-%s">%s</span>' % (
        esc(status) if status in ("success", "partial", "failed") else "unknown",
        esc(status))
    parts = [
        "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
        "<title>审计报告 - %s</title>" % esc(result.get("case_id", "?")),
        "<style>%s</style></head><body><div class=\"wrap\">" % CSS,
        "<header><h1>文献评估交付审计报告 %s</h1>" % badge,
        "<div class=\"meta\">case_id: <b>%s</b> ｜ 生成时间: %s ｜ "
        "本报告为单文件自包含渲染（无外部资源），供人工复核使用。</div></header>"
        % (esc(result.get("case_id", "（缺失）")), esc(generated_at)),
    ]

    # 主结果区：除保留字段外的全部顶层字段，通用递归渲染
    main_keys = [k for k in result.keys() if k not in RESERVED]
    parts.append("<section><h2>主结果</h2>")
    if main_keys:
        parts.append("<table>%s</table>" % "".join(
            "<tr><th style=\"width:22%%\">%s</th><td>%s</td></tr>"
            % (esc(k), render_value_html(result[k])) for k in main_keys))
    else:
        parts.append('<p class="small">无契约字段结果。</p>')
    parts.append("</section>")

    parts.append("<section><h2>证据（evidence）与定位</h2>%s</section>"
                 % evidence_table_html(result.get("evidence")))
    parts.append("<section><h2>不确定性（uncertainties）</h2>%s</section>"
                 % simple_list_html(result.get("uncertainties")))
    parts.append("<section><h2>变更记录（change_records）</h2>%s</section>"
                 % change_records_html(result.get("change_records")))
    parts.append("<section><h2>部分交付边界（partial_limits）</h2>%s</section>"
                 % (render_value_html(result["partial_limits"])
                    if "partial_limits" in result
                    else '<p class="small">无（status 非 partial 或未声明）。</p>'))
    parts.append("<p class=\"small\">由 render_report.py 离线渲染；"
                 "所有内容经 HTML 转义。</p>")
    parts.append("</div></body></html>")
    return "\n".join(parts)


def render_value_text(val, indent=0):
    pad = "  " * indent
    lines = []
    if isinstance(val, dict):
        if not val:
            lines.append(pad + "（空对象）")
        for k, v in val.items():
            if isinstance(v, (dict, list)) and v:
                lines.append(pad + "%s:" % k)
                lines.extend(render_value_text(v, indent + 1))
            else:
                lines.append(pad + "%s: %s" % (k, _scalar_text(v)))
    elif isinstance(val, list):
        if not val:
            lines.append(pad + "（空列表）")
        for x in val:
            if isinstance(x, (dict, list)):
                lines.append(pad + "-")
                lines.extend(render_value_text(x, indent + 1))
            else:
                lines.append(pad + "- %s" % _scalar_text(x))
    else:
        lines.append(pad + _scalar_text(val))
    return lines


def _scalar_text(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def render_text(result, generated_at):
    w = []
    w.append("=" * 64)
    w.append("文献评估交付审计报告（纯文本预览）")
    w.append("case_id: %s    status: %s" % (result.get("case_id", "（缺失）"),
                                              result.get("status", "?")))
    w.append("生成时间: %s" % generated_at)
    w.append("=" * 64)

    w.append("\n[主结果]")
    for k in result.keys():
        if k in RESERVED:
            continue
        v = result[k]
        if isinstance(v, (dict, list)) and v:
            w.append("%s:" % k)
            w.extend(render_value_text(v, 1))
        else:
            w.append("%s: %s" % (k, _scalar_text(v)))

    w.append("\n[证据 evidence]")
    ev = result.get("evidence")
    if isinstance(ev, list) and ev:
        for i, row in enumerate(ev, 1):
            if isinstance(row, dict):
                quote = row.get("quote") or row.get("evidence_quote") or ""
                w.append("  %d) quote: %s" % (i, quote))
                for k, v in row.items():
                    if k in ("quote", "evidence_quote"):
                        continue
                    w.append("     %s: %s" % (k, _scalar_text(v)))
            else:
                w.append("  %d) %s" % (i, _scalar_text(row)))
    else:
        w.append("  （无）")

    w.append("\n[不确定性 uncertainties]")
    unc = result.get("uncertainties")
    if isinstance(unc, list) and unc:
        for x in unc:
            w.append("  - %s" % _scalar_text(x))
    else:
        w.append("  （无）")

    w.append("\n[变更记录 change_records]")
    cr = result.get("change_records")
    if isinstance(cr, list) and cr:
        for i, r in enumerate(cr, 1):
            if isinstance(r, dict):
                w.append("  %d) %s: %r -> %r  (reviewer=%s, date=%s)"
                         % (i, r.get("target_path", "?"),
                            r.get("old_value"), r.get("new_value"),
                            r.get("reviewer", "?"), r.get("date", "?")))
                w.append("     rationale: %s" % r.get("rationale", ""))
            else:
                w.append("  %d) %s" % (i, _scalar_text(r)))
    else:
        w.append("  （无）")

    w.append("\n[部分交付边界 partial_limits]")
    if "partial_limits" in result:
        w.extend(render_value_text(result["partial_limits"], 1))
    else:
        w.append("  （无）")
    w.append("")
    return "\n".join(w)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="自包含 HTML 审计报告渲染器（离线，纯标准库）")
    ap.add_argument("--result", required=True, help="result.json 路径")
    ap.add_argument("--output-dir", required=True, help="报告输出目录")
    args = ap.parse_args(argv)

    try:
        with open(args.result, "r", encoding="utf-8") as f:
            result = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print("[ERROR] 无法读取 result.json: %s (%s)" % (args.result, e))
        return 1
    if not isinstance(result, dict):
        print("[ERROR] result.json 顶层必须是 JSON 对象")
        return 1

    os.makedirs(args.output_dir, exist_ok=True)
    generated_at = datetime.datetime.now().isoformat(timespec="seconds")

    html_path = os.path.join(args.output_dir, "audit_report.html")
    text_path = os.path.join(args.output_dir, "audit_report_preview.txt")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_html(result, generated_at))
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(render_text(result, generated_at))

    print("[OK] HTML 审计报告: %s" % html_path)
    print("[OK] 纯文本预览:   %s" % text_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
