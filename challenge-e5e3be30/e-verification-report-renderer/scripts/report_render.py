#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""report_render.py — 证据卡片集 → 核验报告 Markdown → 真实渲染预览（PDF/HTML，带降级链）。

用法：
  python3 report_render.py --cards evidence-cards.md --case case.json \
      --result result.json --outdir OUTDIR

产物（写入 --outdir）：
  verification-report.md   报告 Markdown（封面信息 + 判定分布 + 不确定性汇总 +
                           证据卡片全文 + 渲染链实际路径与降级说明）
  verification-report.pdf  当 xelatex / pdflatex / pandoc 任一可用且编译成功
  verification-report.html 自包含 HTML 预览（内联 CSS），上述工具全缺或全部失败时生成
  render-info.json         渲染链探测与尝试日志（供下游 merge 进 result.json）

渲染链（每步真实探测并真实执行，绝不伪造产物）：
  1. which xelatex   → 极简 LaTeX 模板编译 PDF
  2. which pdflatex  → 同上（CJK 内容可能编译失败，失败则诚实降级）
  3. which pandoc    → pandoc -o pdf
  4. 全缺/全败       → 自包含 HTML，并在报告尾部注明"渲染降级"

退出码：0 成功（至少 HTML 产出）/ 1 全部渲染路径失败 / 2 用法或 IO 错误。
仅依赖 Python3 标准库；latex/pandoc 经 shutil.which 探测、subprocess 调用。
"""
import argparse
import datetime
import html
import json
import os
import re
import shutil
import subprocess
import sys

VERDICT_ENUM = ["supported", "partially_supported", "contradicted",
                "insufficient_evidence"]
VERDICT_ZH = {
    "supported": "支持",
    "partially_supported": "部分支持",
    "contradicted": "反驳",
    "insufficient_evidence": "证据不足",
}


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: 文件不存在: {path}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"ERROR: JSON 解析失败 {path}: {e}", file=sys.stderr)
        sys.exit(2)


# ---------------------------------------------------------------- 报告 Markdown

def build_report_md(case, result, cards_md, chain_note_placeholder):
    case_id = case.get("case_id", "UNKNOWN")
    date = datetime.date.today().isoformat()
    verdicts = result.get("verdicts") if isinstance(result, dict) else None
    if not isinstance(verdicts, list):
        verdicts = []
    dist = {k: 0 for k in VERDICT_ENUM}
    for v in verdicts:
        if isinstance(v, dict) and v.get("verdict") in dist:
            dist[v["verdict"]] += 1
    lines = []
    lines.append("# 文献证据核验报告")
    lines.append("")
    lines.append("## 封面信息")
    lines.append("")
    lines.append("| 项目 | 内容 |")
    lines.append("| --- | --- |")
    lines.append(f"| case_id | {case_id} |")
    lines.append(f"| 生成日期 | {date} |")
    lines.append(f"| 论断总数 | {len(verdicts)} |")
    lines.append(f"| result.json status | {result.get('status', '—')} |")
    lines.append("")
    lines.append("## 四级判定分布")
    lines.append("")
    lines.append("| 判定 | 含义 | 数量 |")
    lines.append("| --- | --- | --- |")
    for k in VERDICT_ENUM:
        lines.append(f"| {k} | {VERDICT_ZH[k]} | {dist[k]} |")
    lines.append("")
    lines.append("## 论断判定统计表")
    lines.append("")
    lines.append("| claim_id | 判定 | 不确定性 |")
    lines.append("| --- | --- | --- |")
    for v in verdicts:
        unc = (v.get("uncertainty") or "（无）") if isinstance(v, dict) else "—"
        unc = unc.replace("|", "\\|").replace("\n", "<br>")
        lines.append(f"| {v.get('claim_id', '?')} | {v.get('verdict', '?')} | {unc} |")
    lines.append("")
    lines.append("## 不确定性汇总")
    lines.append("")
    any_unc = False
    for v in verdicts:
        if isinstance(v, dict) and v.get("uncertainty"):
            any_unc = True
            u = v["uncertainty"].replace("\n", " ")
            lines.append(f"- **{v.get('claim_id', '?')}**：{u}")
    if not any_unc:
        lines.append("（全部论断均未标注不确定性。）")
    lines.append("")
    lines.append("## 证据卡片全文")
    lines.append("")
    lines.append(cards_md.strip())
    lines.append("")
    lines.append(chain_note_placeholder)
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- Markdown 解析

def split_row(line):
    """按未转义的竖线拆分表格行。"""
    return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]]


def is_sep_row(line):
    cells = split_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", c or "") for c in cells)


def parse_blocks(md_text):
    """把 Markdown 切成块：('h',level,text) ('p',text) ('table',rows) ('list',items)
    ('hr',) ('raw',text)。"""
    blocks = []
    lines = md_text.split("\n")
    i = 0
    para = []

    def flush_para():
        if para:
            blocks.append(("p", " ".join(x.strip() for x in para).strip()))
            para.clear()

    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if not s:
            flush_para()
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            flush_para()
            blocks.append(("h", len(m.group(1)), m.group(2).strip()))
            i += 1
            continue
        if s.startswith("|") and i + 1 < len(lines) and is_sep_row(lines[i + 1]):
            flush_para()
            rows = [split_row(ln)]
            i += 2  # 跳过表头与分隔行
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i]))
                i += 1
            blocks.append(("table", rows))
            continue
        if re.match(r"^[-*]\s+", s):
            flush_para()
            items = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i].strip()):
                items.append(re.sub(r"^[-*]\s+", "", lines[i].strip()))
                i += 1
            blocks.append(("list", items))
            continue
        if s in ("---", "***", "___"):
            flush_para()
            blocks.append(("hr",))
            i += 1
            continue
        para.append(ln)
        i += 1
    flush_para()
    return blocks


# ---------------------------------------------------------------- HTML 渲染

def md_inline_html(text):
    t = html.escape(text, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = t.replace("\\|", "|").replace("<br>", "<br/>")
    return t


def md_to_html(md_text, title):
    parts = []
    for b in parse_blocks(md_text):
        if b[0] == "h":
            lvl = min(b[1], 4)
            parts.append(f"<h{lvl}>{md_inline_html(b[2])}</h{lvl}>")
        elif b[0] == "p":
            parts.append(f"<p>{md_inline_html(b[1])}</p>")
        elif b[0] == "table":
            rows = b[1]
            parts.append("<table>")
            parts.append("<thead><tr>" + "".join(
                f"<th>{md_inline_html(c)}</th>" for c in rows[0]) + "</tr></thead>")
            parts.append("<tbody>")
            for r in rows[1:]:
                parts.append("<tr>" + "".join(
                    f"<td>{md_inline_html(c)}</td>" for c in r) + "</tr>")
            parts.append("</tbody></table>")
        elif b[0] == "list":
            parts.append("<ul>" + "".join(
                f"<li>{md_inline_html(x)}</li>" for x in b[1]) + "</ul>")
        elif b[0] == "hr":
            parts.append("<hr/>")
    css = """
body{font-family:-apple-system,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',
 'Noto Sans CJK SC',sans-serif;max-width:960px;margin:2em auto;padding:0 1.2em;
 color:#222;line-height:1.65}
h1{border-bottom:3px solid #2c5f8a;padding-bottom:.3em}
h2{border-bottom:1px solid #ccc;padding-bottom:.2em;margin-top:1.6em}
table{border-collapse:collapse;width:100%;margin:1em 0;font-size:.95em}
th,td{border:1px solid #bbb;padding:.45em .6em;text-align:left;vertical-align:top}
th{background:#eef3f8}
tr:nth-child(even) td{background:#fafafa}
strong{color:#2c5f8a}
hr{border:none;border-top:1px dashed #bbb;margin:1.5em 0}
"""
    return ("<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"utf-8\"/>\n"
            f"<title>{html.escape(title)}</title>\n<style>{css}</style>\n</head>\n<body>\n"
            + "\n".join(parts) + "\n</body>\n</html>\n")


# ---------------------------------------------------------------- LaTeX 渲染

_LATEX_ESC = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
    "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}


def latex_escape(s):
    # 单趟替换，避免已插入的 LaTeX 命令被二次转义
    return re.sub(r"([\\&%$#_{}~^])", lambda m: _LATEX_ESC[m.group(1)], s)


def md_inline_latex(text):
    t = latex_escape(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", t)
    t = t.replace(r"\textbackslash{}|", r"\textbar{}")  # 表格内转义竖线
    t = t.replace("<br/>", r"\newline{}").replace("<br>", r"\newline{}")
    return t


def md_to_latex(md_text, title):
    out = [r"\documentclass[11pt]{article}",
           r"\usepackage[margin=2.2cm]{geometry}",
           r"\usepackage{longtable}",
           r"\setlength{\parskip}{0.5em}",
           r"\setlength{\parindent}{0pt}",
           r"\begin{document}"]
    for b in parse_blocks(md_text):
        if b[0] == "h":
            cmd = {1: "section", 2: "subsection"}.get(b[1], "subsubsection")
            out.append(f"\\{cmd}*{{{md_inline_latex(b[2])}}}")
        elif b[0] == "p":
            out.append(md_inline_latex(b[1]) + "\n")
        elif b[0] == "table":
            rows = b[1]
            n = max(len(r) for r in rows)
            w = 0.94 / max(n, 1)
            spec = "|" + "|".join(f"p{{{w:.3f}\\linewidth}}" for _ in range(n)) + "|"
            out.append(f"\\begin{{longtable}}{{{spec}}}")
            out.append(r"\hline")
            hdr = rows[0] + [""] * (n - len(rows[0]))
            out.append(" & ".join(md_inline_latex(c) for c in hdr) + r" \\ \hline")
            out.append(r"\endhead")
            for r in rows[1:]:
                r = r + [""] * (n - len(r))
                out.append(" & ".join(md_inline_latex(c) for c in r) + r" \\ \hline")
            out.append(r"\end{longtable}")
        elif b[0] == "list":
            out.append(r"\begin{itemize}")
            for x in b[1]:
                out.append(f"\\item {md_inline_latex(x)}")
            out.append(r"\end{itemize}")
        elif b[0] == "hr":
            out.append(r"\bigskip\hrule\bigskip")
    out.append(r"\end{document}")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- 渲染链

def file_ok(path, min_size=100):
    return os.path.isfile(path) and os.path.getsize(path) >= min_size


def try_latex(engine, md_text, title, outdir):
    """真实调用 latex 引擎；成功返回 PDF 路径，失败返回 None。"""
    tex_path = os.path.join(outdir, "verification-report.tex")
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(md_to_latex(md_text, title))
    try:
        proc = subprocess.run(
            [engine, "-interaction=nonstopmode", "-halt-on-error",
             "verification-report.tex"],
            cwd=outdir, capture_output=True, timeout=240)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"  [{engine}] 调用失败: {e}")
        return None
    pdf = os.path.join(outdir, "verification-report.pdf")
    if proc.returncode == 0 and file_ok(pdf):
        return pdf
    tail = (proc.stdout or b"")[-400:].decode("utf-8", "replace")
    print(f"  [{engine}] 编译失败（returncode={proc.returncode}）: {tail!r}")
    return None


def try_pandoc(md_path, outdir):
    pdf = os.path.join(outdir, "verification-report.pdf")
    try:
        proc = subprocess.run(["pandoc", md_path, "-o", pdf],
                              cwd=outdir, capture_output=True, timeout=240)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"  [pandoc] 调用失败: {e}")
        return None
    if proc.returncode == 0 and file_ok(pdf):
        return pdf
    tail = (proc.stderr or b"")[-400:].decode("utf-8", "replace")
    print(f"  [pandoc] 失败（returncode={proc.returncode}）: {tail!r}")
    return None


def render_html(md_text, title, outdir):
    path = os.path.join(outdir, "verification-report.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md_to_html(md_text, title))
    return path if file_ok(path, min_size=50) else None


def main(argv=None):
    p = argparse.ArgumentParser(
        description="证据卡片集 → 核验报告 Markdown → 真实渲染预览（PDF/HTML 降级链）")
    p.add_argument("--cards", required=True, help="evidence-cards.md 路径")
    p.add_argument("--case", required=True, help="case.json 路径")
    p.add_argument("--result", required=True, help="result.json 路径（取 verdicts 统计）")
    p.add_argument("--outdir", required=True, help="产物输出目录")
    args = p.parse_args(argv)

    os.makedirs(args.outdir, exist_ok=True)
    case = load_json(args.case)
    result = load_json(args.result)
    try:
        with open(args.cards, "r", encoding="utf-8") as f:
            cards_md = f.read()
    except FileNotFoundError:
        print(f"ERROR: 文件不存在: {args.cards}", file=sys.stderr)
        return 2

    # 第一步：探测工具并真实尝试渲染（先用不含渲染链说明的报告体）
    attempts = []
    body = build_report_md(case, result, cards_md, "")
    md_path = os.path.join(args.outdir, "verification-report.md")

    chain = None
    preview = None
    for method in ("xelatex", "pdflatex", "pandoc", "html"):
        if method == "html":
            preview = render_html(body, "文献证据核验报告", args.outdir)
            if preview:
                chain = "html"
                attempts.append("html: 成功（自包含 HTML 预览）")
            else:
                attempts.append("html: 失败（无法写出 HTML 文件）")
            break
        found = shutil.which(method)
        if not found:
            attempts.append(f"{method}: 未安装（which 未找到），跳过")
            continue
        attempts.append(f"{method}: 检测到 {found}，尝试渲染")
        if method == "pandoc":
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(body)
            preview = try_pandoc(md_path, args.outdir)
        else:
            preview = try_latex(method, body, "文献证据核验报告", args.outdir)
        if preview:
            chain = method
            attempts[-1] += " → 成功"
            break
        attempts[-1] += " → 失败，降级"

    if not chain or not preview:
        print("ERROR: 全部渲染路径失败，无任何预览产物", file=sys.stderr)
        return 1

    # 第二步：把真实渲染链说明写进报告尾部，并用已选定方法重渲最终版
    degraded = chain != "xelatex"
    note_lines = ["## 渲染链实际路径与降级说明", ""]
    for a in attempts:
        note_lines.append(f"- {a}")
    note_lines.append("")
    note_lines.append(f"- 最终采用渲染链：**{chain}**")
    # 预览内嵌本说明，无法在文内给出自身精确字节数；精确大小见 render-info.json
    note_lines.append(f"- 预览产物：`{os.path.basename(preview)}`"
                      f"（真实渲染生成，未伪造；最终字节数见 render-info.json）")
    if degraded:
        note_lines.append("- 渲染降级声明：优先渲染链（xelatex）不可用或失败，"
                          "本预览为降级产物，版式可能与 LaTeX/PDF 版存在差异。")
    chain_note = "\n".join(note_lines)
    final_md = build_report_md(case, result, cards_md, chain_note)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(final_md)
    if chain == "html":
        preview = render_html(final_md, "文献证据核验报告", args.outdir)
    elif chain == "pandoc":
        preview = try_pandoc(md_path, args.outdir)
    else:
        preview = try_latex(chain, final_md, "文献证据核验报告", args.outdir)
    if not preview:
        print("ERROR: 最终版重渲染失败", file=sys.stderr)
        return 1

    info = {
        "chain": chain,
        "preview_path": os.path.abspath(preview),
        "preview_size_bytes": os.path.getsize(preview),
        "report_markdown_path": os.path.abspath(md_path),
        "attempts": attempts,
        "degraded": degraded,
        "timestamp": datetime.datetime.now(
            datetime.timezone.utc).astimezone().isoformat(timespec="seconds"),
    }
    info_path = os.path.join(args.outdir, "render-info.json")
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"OK: 报告 Markdown → {md_path}")
    print(f"OK: 渲染链={chain}，预览 → {preview}（{os.path.getsize(preview)} 字节）")
    print(f"OK: 渲染日志 → {info_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
