#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fill_report.py — 报告占位符重算注入渲染器（纯标准库、确定性输出）。

从 cleaned.csv / ledger.csv（事实源）与 summary.json（case_id 与配置）重算全部数字，
注入 references/report_template.md 的 {{placeholder}} 体系，输出：
  quality_report.md   —— Markdown 数据质量报告
  quality_report.html —— 内联 SVG 图表、带简洁 CSS 的单文件 HTML 报告

铁律：报告中每个数字都必须由本脚本从产物重算注入，禁止手写。
退出码：
  0  渲染成功
  4  拒绝渲染：模板含未知占位符，或清洗产物缺件 / 不可解析
"""

import argparse
import csv
import html as html_mod
import json
import re
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_REFUSE = 4

PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
IMG_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")
HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$")

ACTION_LABELS = {
    "unit_convert": "单位换算",
    "drop_duplicate": "重复行剔除",
    "drop_invalid": "非法值剔除（不插补）",
    "flag_outlier": "异常标记（保留原值）",
    "keep_unchanged": "复核保留",
}

CSS = (
    "body{font-family:-apple-system,'Helvetica Neue',Arial,'PingFang SC','Microsoft YaHei',sans-serif;"
    "max-width:880px;margin:2em auto;padding:0 1.2em;color:#222;line-height:1.65;}"
    "h1{border-bottom:2px solid #4C78A8;padding-bottom:.3em;font-size:24px;}"
    "h2{border-bottom:1px solid #ddd;padding-bottom:.2em;margin-top:1.8em;font-size:19px;}"
    "h3{font-size:16px;margin-top:1.3em;}"
    "table{border-collapse:collapse;margin:1em 0;width:100%;}"
    "th,td{border:1px solid #ccc;padding:6px 10px;text-align:left;font-size:14px;}"
    "th{background:#f2f5f9;}"
    "figure{margin:1.2em 0;}"
    "figcaption{font-size:13px;color:#555;margin-top:.4em;}"
    "code{background:#f5f5f5;padding:1px 4px;border-radius:3px;}"
)


class UnknownPlaceholder(Exception):
    """模板中出现占位符重算表之外的名字。"""

    def __init__(self, names):
        self.names = list(names)
        super().__init__(", ".join(self.names))


def fmt_num(v):
    """确定性数字格式：最多 4 位小数、去尾零。"""
    s = f"{float(v):.4f}".rstrip("0").rstrip(".")
    if s in ("", "-0"):
        return "0"
    return s


def fmt_pct(v):
    return f"{float(v):.2f}%"


def read_csv_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fields = list(reader.fieldnames or [])
    return fields, rows


def is_missing(v):
    return v is None or str(v).strip() == ""


def field_label(f):
    return "（整行）" if f == "*" else f


def compute_stats(cleaned_path, ledger_path):
    """从 cleaned.csv + ledger.csv 重算全部统计量。这是唯一事实源。"""
    fields, rows = read_csv_rows(cleaned_path)
    n_rows = len(rows)
    n_fields = len(fields)
    missing_by_field = {f: 0 for f in fields}
    for r in rows:
        for f in fields:
            if is_missing(r.get(f)):
                missing_by_field[f] += 1
    missing_total = sum(missing_by_field.values())
    denom = n_rows * n_fields
    missing_rate = round(100.0 * missing_total / denom, 2) if denom else 0.0

    _, ledger = read_csv_rows(ledger_path)
    action_counts = {}
    action_fields = {}
    field_issue_counts = {}
    field_actions = {}
    field_rows = {}
    for rec in ledger:
        action = (rec.get("action") or "").strip()
        field = (rec.get("field") or "").strip() or "*"
        row_id = (rec.get("row_id") or "").strip()
        action_counts[action] = action_counts.get(action, 0) + 1
        field_issue_counts[field] = field_issue_counts.get(field, 0) + 1
        action_fields.setdefault(action, [])
        if field not in action_fields[action]:
            action_fields[action].append(field)
        field_actions.setdefault(field, [])
        if action not in field_actions[field]:
            field_actions[field].append(action)
        field_rows.setdefault(field, [])
        if row_id and row_id not in field_rows[field]:
            field_rows[field].append(row_id)

    return {
        "total_rows": n_rows,
        "total_fields": n_fields,
        "fields": fields,
        "missing_by_field": missing_by_field,
        "missing_values_total": missing_total,
        "missing_rate_pct": missing_rate,
        "change_records": len(ledger),
        "action_counts": action_counts,
        "action_fields": action_fields,
        "field_issue_counts": field_issue_counts,
        "field_actions": field_actions,
        "field_rows": field_rows,
        "duplicate_groups_removed": action_counts.get("drop_duplicate", 0),
        "unit_conversions": action_counts.get("unit_convert", 0),
        "outliers_flagged": action_counts.get("flag_outlier", 0),
        "invalid_values_dropped": action_counts.get("drop_invalid", 0),
    }


def md_table(headers, rows):
    out = ["| " + " | ".join(str(h) for h in headers) + " |",
           "| " + " | ".join(["---"] * len(headers)) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def build_figures_section(figures_index_path):
    if figures_index_path is None or not Path(figures_index_path).is_file():
        return ("本报告未嵌入图表：未找到 figures_index.json"
                "（figures_svg.py 尚未运行或出图失败）。"
                "该降级情况必须在 result.json 的 status / uncertainty 中如实说明。")
    idx = json.loads(Path(figures_index_path).read_text(encoding="utf-8"))
    lines = []
    for i, fig in enumerate(idx.get("figures", []), 1):
        lines.append(f"### 图 {i}：{fig['title']}")
        lines.append("")
        lines.append(f"![{fig['title']}]({fig['file']})")
        lines.append("")
        lines.append(f"- 图表类型：{fig['kind_label']}")
        lines.append(f"- 选择依据：{fig['rationale']}")
        lines.append(f"- 图注：{fig['caption']}")
        lines.append("")
    for sk in idx.get("skipped", []):
        lines.append(f"- （未出图）{sk['target']}：{sk['reason']}")
    if not idx.get("figures") and not idx.get("skipped"):
        lines.append("figures_index.json 中无任何图表记录。")
    return "\n".join(lines).rstrip("\n")


def build_placeholders(stats, summary, figures_index_path):
    case_id = summary.get("case_id", "UNKNOWN")
    fic = stats["field_issue_counts"]
    field_issue_rows = []
    for f in sorted(fic, key=lambda x: (x == "*", x)):
        field_issue_rows.append([
            field_label(f),
            fic[f],
            "、".join(ACTION_LABELS.get(a, a) for a in stats["field_actions"].get(f, [])),
            "、".join(stats["field_rows"].get(f, [])) or "—",
        ])
    if not field_issue_rows:
        field_issue_rows.append(["（无）", 0, "—", "—"])
    missing_rows = [
        [f, stats["missing_by_field"][f], stats["total_rows"] - stats["missing_by_field"][f]]
        for f in stats["fields"]
    ] or [["（无字段）", 0, 0]]
    action_rows = []
    for a in sorted(stats["action_counts"]):
        action_rows.append([
            ACTION_LABELS.get(a, a),
            a,
            stats["action_counts"][a],
            "、".join(field_label(f) for f in stats["action_fields"].get(a, [])),
        ])
    if not action_rows:
        action_rows.append(["（无变更）", "—", 0, "—"])
    return {
        "case_id": str(case_id),
        "total_rows": str(stats["total_rows"]),
        "total_fields": str(stats["total_fields"]),
        "missing_total": str(stats["missing_values_total"]),
        "missing_rate_pct": fmt_pct(stats["missing_rate_pct"]),
        "change_records_total": str(stats["change_records"]),
        "duplicate_groups_removed": str(stats["duplicate_groups_removed"]),
        "unit_conversions": str(stats["unit_conversions"]),
        "outliers_flagged": str(stats["outliers_flagged"]),
        "invalid_values_dropped": str(stats["invalid_values_dropped"]),
        "field_issue_table": md_table(["字段", "问题条数", "涉及动作", "涉及行"], field_issue_rows),
        "missing_by_field_table": md_table(["字段", "缺失数", "非缺失数"], missing_rows),
        "action_summary_table": md_table(["处理动作", "动作代码", "笔数", "影响字段"], action_rows),
        "figures_section": build_figures_section(figures_index_path),
    }


def render_markdown(template_text, placeholders):
    body = COMMENT_RE.sub("", template_text)
    unknown = sorted(set(PLACEHOLDER_RE.findall(body)) - set(placeholders))
    if unknown:
        raise UnknownPlaceholder(unknown)
    rendered = PLACEHOLDER_RE.sub(lambda m: str(placeholders[m.group(1)]), body)
    return rendered.strip() + "\n"


def inline_format(text):
    t = html_mod.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)


def render_table_html(block):
    def cells(row):
        return [c.strip() for c in row.strip().strip("|").split("|")]
    header = cells(block[0])
    body_rows = [cells(r) for r in block[2:]] if len(block) > 2 else []
    parts = ["<table>",
             "<thead><tr>" + "".join(f"<th>{inline_format(c)}</th>" for c in header) + "</tr></thead>",
             "<tbody>"]
    for r in body_rows:
        parts.append("<tr>" + "".join(f"<td>{inline_format(c)}</td>" for c in r) + "</tr>")
    parts.append("</tbody></table>")
    return "\n".join(parts)


def md_to_html(md, base_dir):
    """极简确定性 Markdown -> HTML：标题 / 表格 / 无序列表 / 段落 / SVG 图片内联。"""
    lines = md.split("\n")
    out = []
    i = 0
    list_open = False

    def close_list():
        nonlocal list_open
        if list_open:
            out.append("</ul>")
            list_open = False

    while i < len(lines):
        s = lines[i].strip()
        if not s:
            close_list()
            i += 1
            continue
        if s.startswith("|"):
            close_list()
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i].strip())
                i += 1
            out.append(render_table_html(block))
            continue
        m = HEADING_RE.match(s)
        if m:
            close_list()
            level = len(m.group(1))
            out.append(f"<h{level}>{inline_format(m.group(2))}</h{level}>")
            i += 1
            continue
        mimg = IMG_RE.match(s)
        if mimg:
            close_list()
            alt, src = mimg.group(1), mimg.group(2)
            if src.lower().endswith(".svg"):
                svg_path = (Path(base_dir) / src).resolve()
                try:
                    svg_text = svg_path.read_text(encoding="utf-8")
                    svg_text = re.sub(r"<\?xml[^>]*\?>", "", svg_text).strip()
                    out.append(f"<figure>{svg_text}<figcaption>{inline_format(alt)}</figcaption></figure>")
                except OSError:
                    out.append(f"<figure><p>[图表文件缺失：{html_mod.escape(src)}]</p></figure>")
            else:
                out.append(f'<figure><img src="{html_mod.escape(src)}" alt="{html_mod.escape(alt)}"></figure>')
            i += 1
            continue
        if s.startswith("- "):
            if not list_open:
                out.append("<ul>")
                list_open = True
            out.append(f"<li>{inline_format(s[2:])}</li>")
            i += 1
            continue
        close_list()
        out.append(f"<p>{inline_format(s)}</p>")
        i += 1
    close_list()
    return "\n".join(out)


def render_report(cleaned_path, ledger_path, summary_path, template_path,
                  figures_index_path, base_dir):
    """完整渲染管线，返回 (markdown, html, stats, placeholders)。check_consistency 复用。"""
    stats = compute_stats(cleaned_path, ledger_path)
    summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    template_text = Path(template_path).read_text(encoding="utf-8")
    fig_idx = Path(figures_index_path) if figures_index_path else None
    placeholders = build_placeholders(stats, summary, fig_idx)
    md = render_markdown(template_text, placeholders)
    body = md_to_html(md, base_dir)
    title = f"数据质量报告 {placeholders['case_id']}"
    html_doc = (
        "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{html_mod.escape(title)}</title>\n<style>{CSS}</style>\n</head>\n<body>\n"
        + body + "\n</body>\n</html>\n"
    )
    return md, html_doc, stats, placeholders


def main(argv=None):
    ap = argparse.ArgumentParser(description="占位符重算注入，渲染 quality_report.md / .html")
    ap.add_argument("--cleaned", required=True, help="cleaned.csv 路径")
    ap.add_argument("--ledger", required=True, help="ledger.csv 路径")
    ap.add_argument("--summary", required=True, help="summary.json 路径")
    ap.add_argument("--template",
                    default=str(Path(__file__).resolve().parent.parent / "references" / "report_template.md"),
                    help="报告模板路径（默认取技能内 references/report_template.md）")
    ap.add_argument("--figures-index", default=None,
                    help="figures_index.json 路径；缺省时图表节以文字说明降级")
    ap.add_argument("--out-md", required=True, help="输出 quality_report.md 路径")
    ap.add_argument("--out-html", required=True, help="输出 quality_report.html 路径")
    args = ap.parse_args(argv)

    for p in (args.cleaned, args.ledger, args.summary, args.template):
        if not Path(p).is_file():
            print(f"[fill_report] 拒绝渲染：输入缺件 {p}", file=sys.stderr)
            return EXIT_REFUSE
    try:
        md, html_doc, _stats, _ph = render_report(
            args.cleaned, args.ledger, args.summary, args.template,
            args.figures_index, Path(args.out_md).resolve().parent)
    except UnknownPlaceholder as e:
        print(f"[fill_report] 拒绝渲染：模板含未知占位符：{', '.join(e.names)}", file=sys.stderr)
        return EXIT_REFUSE
    except (OSError, ValueError, csv.Error) as e:
        print(f"[fill_report] 拒绝渲染：输入不可解析：{e}", file=sys.stderr)
        return EXIT_REFUSE
    Path(args.out_md).write_text(md, encoding="utf-8")
    Path(args.out_html).write_text(html_doc, encoding="utf-8")
    print(f"[fill_report] 已生成 {args.out_md} 与 {args.out_html}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
