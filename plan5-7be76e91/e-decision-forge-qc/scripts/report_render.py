#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""report_render.py — 决策包渲染为自包含报告（decision-forge-qc）。

把 decision_package.json（可选叠加 sensitivity.json）渲染为：
  * report.html —— 自包含 HTML：内联 CSS、无外部依赖、不依赖 JS；
    含选择结论、确认项 confirmed/pending 分区、七类字段比较矩阵、
    决策日志（淘汰规则+证据引用）、评分与权重、敏感性分析各节；
    页脚固定标注生成方式与案例 id；
  * report.md —— 同结构的 Markdown 版本。

确定性：默认输出不含任何时间戳；如需标注生成时间，用 --generated-at
显式传入固定字符串。同一输入双跑产物逐字节一致。

退出码：0=成功；2=输入/用法错误；3=输入结构缺少渲染必需字段。
"""
import argparse
import html
import json
import sys
from pathlib import Path

CATEGORIES = [
    ("assumptions", "假设"),
    ("variables", "变量"),
    ("controls", "对照"),
    ("steps", "步骤"),
    ("parameters", "参数"),
    ("resources", "资源"),
    ("evaluation_criteria", "判读标准"),
]
CONF_KIND_LABELS = {
    "safety": "安全", "ethics": "伦理",
    "equipment_availability": "设备可用性", "expert": "专家确认",
}


class InputError(Exception):
    """输入/用法错误（退出码 2）。"""


class RenderError(Exception):
    """渲染必需字段缺失（退出码 3）。"""


def load_json(path, what):
    p = Path(path)
    if not p.is_file():
        raise InputError(f"{what}不存在: {p}")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except UnicodeDecodeError as e:
        raise InputError(f"{what}不是合法 UTF-8: {p}: {e}")
    except json.JSONDecodeError as e:
        raise InputError(f"{what} JSON 解析失败: {p}: {e}")


def esc(x):
    return html.escape(str(x), quote=True)


def fmt(x):
    return f"{x:.6f}"


def require(pkg):
    if not isinstance(pkg, dict):
        raise RenderError("decision_package 顶层必须是 JSON 对象")
    for key in ("case_id", "plans", "matrix", "eliminations",
                "scores", "weights", "confirmations", "selection"):
        if key not in pkg:
            raise RenderError(f"决策包缺少渲染必需字段: {key}")


def weighted_totals(pkg):
    weights = pkg["weights"]
    total = sum(weights.values())
    wn = {d: weights[d] / total for d in sorted(weights)} if total > 0 else {}
    totals = {pid: sum(pkg["scores"][pid].get(d, 0.0) * w for d, w in wn.items())
              for pid in sorted(pkg["scores"])}
    return wn, totals


CSS = """
body{font-family:-apple-system,"Helvetica Neue","PingFang SC","Microsoft YaHei",sans-serif;
margin:0 auto;max-width:1000px;padding:24px;color:#222;line-height:1.6}
h1{border-bottom:3px solid #2c5f8a;padding-bottom:8px}
h2{border-bottom:1px solid #ccc;padding-bottom:4px;margin-top:32px}
table{border-collapse:collapse;width:100%;margin:12px 0}
th,td{border:1px solid #bbb;padding:6px 10px;vertical-align:top;text-align:left}
th{background:#eef3f8}
tr:nth-child(even) td{background:#fafafa}
.banner{background:#fff3cd;border:1px solid #e0a800;padding:10px 14px;
font-weight:bold;margin:16px 0}
.final{color:#1a7f37;font-weight:bold}.provisional{color:#b25d00;font-weight:bold}
.flip{color:#b00;font-weight:bold}
footer{margin-top:40px;border-top:2px solid #999;padding-top:12px;
font-size:0.9em;color:#555}
ul{margin:4px 0;padding-left:20px}
code{background:#f0f0f0;padding:1px 4px}
""".strip()


def item_text(item):
    if isinstance(item, dict):
        iid = item.get("id", "")
        text = item.get("text", "")
        return f"[{iid}] {text}" if iid else str(text)
    return str(item)


def build_model(pkg, sens):
    """把渲染所需内容组织成 (heading, html_block, md_lines) 的节列表。"""
    case_id = pkg["case_id"]
    plans = {p["plan_id"]: p for p in pkg["plans"]}
    plan_ids = sorted(plans)
    selection = pkg["selection"]
    confirmations = pkg["confirmations"]
    confirmed = [c for c in confirmations if c.get("status") == "confirmed"]
    pending = [c for c in confirmations if c.get("status") == "pending"]
    wn, totals = weighted_totals(pkg)
    ranking = sorted(totals, key=lambda p: (-totals[p], p))
    sections = []

    # 1. 选择结论
    status = selection.get("status", "unknown")
    status_cls = "final" if status == "final" else "provisional"
    sel_plan = selection.get("selected_plan_id")
    h = [f"<p>选定方案：<strong>{esc(sel_plan)}</strong> "
         f"（{esc(plans.get(sel_plan, {}).get('name', ''))}）</p>",
         f"<p>结论状态：<span class=\"{status_cls}\">{esc(status)}</span>"
         + ("（存在未完成的确认项，结论已降级为 provisional，不得作为最终执行依据）"
            if status == "provisional" else "（全部确认项已完成）") + "</p>",
         f"<p>选择理由：{esc(selection.get('rationale', ''))}</p>"]
    m = ["## 1. 选择结论", "",
         f"- 选定方案: **{sel_plan}**（{plans.get(sel_plan, {}).get('name', '')}）",
         f"- 结论状态: **{status}**"
         + ("（存在未完成的确认项，结论降级，不得作为最终执行依据）"
            if status == "provisional" else "（全部确认项已完成）"),
         f"- 选择理由: {selection.get('rationale', '')}", ""]
    dr = selection.get("discarded_reasons", [])
    if dr:
        h.append("<table><tr><th>未选方案</th><th>放弃原因</th></tr>")
        m += ["| 未选方案 | 放弃原因 |", "|---------|---------|"]
        for d in dr:
            h.append(f"<tr><td>{esc(d.get('plan_id', ''))}</td>"
                     f"<td>{esc(d.get('reason', ''))}</td></tr>")
            m.append(f"| {d.get('plan_id', '')} | {d.get('reason', '')} |")
        h.append("</table>")
        m.append("")
    sections.append(("1. 选择结论", "\n".join(h), m))

    # 2. 确认项（confirmed / pending 分区）
    h = ["<h3>已确认（confirmed）</h3>"]
    m = ["## 2. 确认项状态", "", "### 已确认（confirmed）", ""]
    if confirmed:
        h.append("<table><tr><th>id</th><th>类别</th><th>事项</th><th>备注</th></tr>")
        m += ["| id | 类别 | 事项 | 备注 |", "|----|------|------|------|"]
        for c in confirmed:
            kind = CONF_KIND_LABELS.get(c.get("kind"), c.get("kind", ""))
            h.append(f"<tr><td>{esc(c.get('id',''))}</td><td>{esc(kind)}</td>"
                     f"<td>{esc(c.get('item',''))}</td><td>{esc(c.get('note',''))}</td></tr>")
            m.append(f"| {c.get('id','')} | {kind} | {c.get('item','')} | {c.get('note','')} |")
        h.append("</table>")
    else:
        h.append("<p>（无）</p>")
        m.append("（无）")
    m.append("")
    h.append("<h3>未确认（pending）—— 不得写成已确认事实</h3>")
    m += ["### 未确认（pending）—— 不得写成已确认事实", ""]
    if pending:
        h.append("<table><tr><th>id</th><th>类别</th><th>事项</th><th>备注</th></tr>")
        m += ["| id | 类别 | 事项 | 备注 |", "|----|------|------|------|"]
        for c in pending:
            kind = CONF_KIND_LABELS.get(c.get("kind"), c.get("kind", ""))
            h.append(f"<tr><td>{esc(c.get('id',''))}</td><td>{esc(kind)}</td>"
                     f"<td>{esc(c.get('item',''))}</td><td>{esc(c.get('note',''))}</td></tr>")
            m.append(f"| {c.get('id','')} | {kind} | {c.get('item','')} | {c.get('note','')} |")
        h.append("</table>")
    else:
        h.append("<p>（无）</p>")
        m.append("（无）")
    m.append("")
    sections.append(("2. 确认项状态", "\n".join(h), m))

    # 3. 七类字段比较矩阵
    h, m = [], ["## 3. 七类字段比较矩阵", ""]
    matrix = pkg["matrix"]
    for cat, label in CATEGORIES:
        h.append(f"<h3>{esc(label)}（{esc(cat)}）</h3>")
        h.append("<table><tr>" + "".join(
            f"<th>{esc(pid)}<br>{esc(plans[pid].get('name',''))}</th>"
            for pid in plan_ids) + "</tr><tr>")
        m += [f"### {label}（{cat}）", ""]
        for pid in plan_ids:
            items = matrix.get(pid, {}).get(cat, [])
            h.append("<td><ul>" + "".join(
                f"<li>{esc(item_text(it))}</li>" for it in items) + "</ul></td>")
            m.append(f"- **{pid}**:")
            for it in items:
                m.append(f"  - {item_text(it)}")
        h.append("</tr></table>")
        m.append("")
    sections.append(("3. 七类字段比较矩阵", "\n".join(h), m))

    # 4. 决策日志
    h, m = [], ["## 4. 决策日志（淘汰：谁被淘汰、依据哪条规则哪条证据）", ""]
    elims = pkg["eliminations"]
    if elims:
        h.append("<table><tr><th>被淘汰方案</th><th>淘汰规则</th><th>证据引用</th></tr>")
        m += ["| 被淘汰方案 | 淘汰规则 | 证据引用 |", "|-----------|---------|---------|"]
        for e in elims:
            refs = ", ".join(str(r) for r in e.get("evidence_refs", []))
            h.append(f"<tr><td>{esc(e.get('plan_id',''))}</td>"
                     f"<td><code>{esc(e.get('rule',''))}</code></td>"
                     f"<td>{esc(refs)}</td></tr>")
            m.append(f"| {e.get('plan_id','')} | `{e.get('rule','')}` | {refs} |")
        h.append("</table>")
    else:
        h.append("<p>（无硬规则淘汰；全部经加权评分比较）</p>")
        m.append("（无硬规则淘汰；全部经加权评分比较）")
    m.append("")
    sections.append(("4. 决策日志", "\n".join(h), m))

    # 5. 评分与权重
    dims = sorted(wn)
    h = ["<h3>权重（已归一化）</h3>",
         "<table><tr><th>维度</th><th>权重</th></tr>"]
    m = ["## 5. 评分与权重", "", "### 权重（已归一化）", "",
         "| 维度 | 权重 |", "|------|------|"]
    for d in dims:
        h.append(f"<tr><td>{esc(d)}</td><td>{fmt(wn[d])}</td></tr>")
        m.append(f"| {d} | {fmt(wn[d])} |")
    h.append("</table>")
    m += ["", "### 维度分与加权总分", ""]
    h.append("<h3>维度分与加权总分</h3><table><tr><th>方案</th>"
             + "".join(f"<th>{esc(d)}</th>" for d in dims)
             + "<th>加权总分</th><th>排名</th></tr>")
    m += ["| 方案 | " + " | ".join(dims) + " | 加权总分 | 排名 |",
          "|------|" + "------|" * (len(dims) + 2)]
    rank_pos = {pid: i + 1 for i, pid in enumerate(ranking)}
    for pid in ranking:
        cells = "".join(f"<td>{esc(pkg['scores'][pid].get(d, ''))}</td>" for d in dims)
        h.append(f"<tr><td>{esc(pid)}</td>{cells}<td>{fmt(totals[pid])}</td>"
                 f"<td>{rank_pos[pid]}</td></tr>")
        m.append("| " + pid + " | "
                 + " | ".join(str(pkg["scores"][pid].get(d, "")) for d in dims)
                 + f" | {fmt(totals[pid])} | {rank_pos[pid]} |")
    h.append("</table>")
    m.append("")
    sections.append(("5. 评分与权重", "\n".join(h), m))

    # 6. 敏感性分析
    if sens:
        b = sens["baseline"]
        v = sens["verdict"]
        h = [f"<p>基线首选：<strong>{esc(b['top'])}</strong>；稳健性 verdict："
             f"<strong>{esc(v['status'])}</strong> — {esc(v['note'])}</p>",
             "<table><tr><th>情景</th><th>扰动维度</th><th>方向</th>"
             "<th>首选</th><th>是否翻转</th></tr>"]
        m = ["## 6. 敏感性分析", "",
             f"- 基线首选: **{b['top']}**；verdict: **{v['status']}** — {v['note']}", "",
             "| 情景 | 扰动维度 | 方向 | 首选 | 是否翻转 |",
             "|------|---------|------|------|---------|"]
        for s in sens["scenarios"]:
            flip = "是" if s["flipped"] else "否"
            h.append(f"<tr><td>{esc(s['name'])}</td><td>{esc(s['dimension'])}</td>"
                     f"<td>{esc(s['direction'])}</td><td>{esc(s['top'])}</td>"
                     f"<td class=\"{'flip' if s['flipped'] else ''}\">{flip}</td></tr>")
            m.append(f"| {s['name']} | {s['dimension']} | {s['direction']} "
                     f"| {s['top']} | {'**是**' if s['flipped'] else '否'} |")
        h.append("</table>")
        m += ["", "### 翻转阈值", "",
              "| 维度 | 下调翻转 | 上调翻转 |", "|------|---------|---------|"]
        h.append("<h3>翻转阈值</h3><table><tr><th>维度</th><th>下调翻转</th>"
                 "<th>上调翻转</th></tr>")
        for th in sens["thresholds"]:
            d, u = th["down_flip"], th["up_flip"]
            ds = (f"≤{fmt(d['threshold'])} → {d['new_top']}" if d else "（[0,1] 内无）")
            us = (f"≥{fmt(u['threshold'])} → {u['new_top']}" if u else "（[0,1] 内无）")
            h.append(f"<tr><td>{esc(th['dimension'])}</td><td>{esc(ds)}</td>"
                     f"<td>{esc(us)}</td></tr>")
            m.append(f"| {th['dimension']} | {ds} | {us} |")
        h.append("</table>")
        m.append("")
        sections.append(("6. 敏感性分析", "\n".join(h), m))

    return case_id, plans, sections


def render_html(pkg, sens, generated_at):
    case_id, plans, sections = build_model(pkg, sens)
    parts = ["<!DOCTYPE html>", "<html lang=\"zh-CN\">", "<head>",
             "<meta charset=\"utf-8\">",
             f"<title>方案选择决策报告 — {esc(case_id)}</title>",
             f"<style>{CSS}</style>", "</head>", "<body>",
             f"<h1>实验方案选择决策报告</h1>",
             f"<p>案例 id：<code>{esc(case_id)}</code></p>"]
    if pkg.get("synthetic"):
        parts.append("<div class=\"banner\">合成示例 / SYNTHETIC EXAMPLE —— "
                     "本报告数据为演示用合成数据，不是真实案例结果，"
                     "不得作为真实实验依据。</div>")
    for heading, block, _ in sections:
        parts.append(f"<h2>{esc(heading)}</h2>")
        parts.append(block)
    footer = ("本报告由 decision-forge-qc/scripts/report_render.py 使用 Python "
              "标准库确定性渲染生成：内联 CSS、无外部依赖、不依赖 JavaScript；"
              "输出默认不含时间戳，同一输入双跑产物逐字节一致。")
    if generated_at:
        footer += f" 生成时间（由调用方参数显式传入）：{generated_at}。"
    footer += f" 案例 id：{case_id}。"
    if pkg.get("synthetic"):
        footer += " 本报告为合成示例 / SYNTHETIC EXAMPLE。"
    parts.append(f"<footer>{esc(footer)}</footer>")
    parts.append("</body>\n</html>")
    return "\n".join(parts) + "\n"


def render_md(pkg, sens, generated_at):
    case_id, plans, sections = build_model(pkg, sens)
    lines = ["# 实验方案选择决策报告", "", f"- 案例 id: `{case_id}`"]
    if pkg.get("synthetic"):
        lines.append("- **合成示例 / SYNTHETIC EXAMPLE —— 演示用合成数据，"
                     "不是真实案例结果，不得作为真实实验依据。**")
    lines.append("")
    for _, _, md_lines in sections:
        lines.extend(md_lines)
    lines.append("---")
    footer = ("本报告由 decision-forge-qc/scripts/report_render.py 使用 Python "
              "标准库确定性渲染生成；输出默认不含时间戳，同一输入双跑产物逐字节一致。")
    if generated_at:
        footer += f"生成时间（由调用方参数显式传入）：{generated_at}。"
    footer += f"案例 id：{case_id}。"
    if pkg.get("synthetic"):
        footer += "本报告为合成示例 / SYNTHETIC EXAMPLE。"
    lines.append(footer)
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="把 decision_package.json（可选叠加 sensitivity.json）渲染为自包含 "
                    "report.html + report.md。退出码 0=成功 / 2=输入错误 / "
                    "3=渲染必需字段缺失。")
    ap.add_argument("--package", required=True, help="decision_package.json 路径")
    ap.add_argument("--sensitivity", default=None,
                    help="sensitivity.json 路径（可选，提供时渲染敏感性节）")
    ap.add_argument("--outdir", default=".", help="报告输出目录（默认当前目录）")
    ap.add_argument("--generated-at", default=None,
                    help="固定生成时间标注（可选；不传则输出完全无时间戳，保证双跑一致）")
    args = ap.parse_args(argv)

    try:
        pkg = load_json(args.package, "决策包文件")
        sens = (load_json(args.sensitivity, "敏感性结果文件")
                if args.sensitivity else None)
    except InputError as e:
        print(f"输入错误: {e}", file=sys.stderr)
        return 2
    try:
        require(pkg)
        html_text = render_html(pkg, sens, args.generated_at)
        md_text = render_md(pkg, sens, args.generated_at)
    except RenderError as e:
        print(f"渲染前置条件不满足: {e}", file=sys.stderr)
        return 3

    outdir = Path(args.outdir)
    try:
        outdir.mkdir(parents=True, exist_ok=True)
        with open(outdir / "report.html", "w", encoding="utf-8") as f:
            f.write(html_text)
        with open(outdir / "report.md", "w", encoding="utf-8") as f:
            f.write(md_text)
    except OSError as e:
        print(f"输入错误: 无法写出报告到 {outdir}: {e}", file=sys.stderr)
        return 2

    print(f"渲染完成：{outdir / 'report.html'} 与 {outdir / 'report.md'} "
          f"（case_id={pkg['case_id']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
