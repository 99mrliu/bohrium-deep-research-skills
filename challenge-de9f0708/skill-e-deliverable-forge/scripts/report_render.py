#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""report_render.py — 把 result.json 渲染成人读审查报告。

输出：
  --out-md   audit_report.md：标题（含 case_id 与生成说明）、概要段（status、
             severity×类别交叉计数表、待复核数、未检查面清单）、逐条问题卡片
             （编号/类别/严重度徽章/定位/逐字 quote 引用块/依据/建议/verdict_status）、
             修改优先级清单（critical→major→minor→info，每条一句行动）、
             尾部 uncertainty 与 change_log。
  --out-html audit_report.html：同内容的自包含 CSS 单文件，无外部依赖。

确定性：无时间戳、无随机数，同一输入必得同一输出。缺键不崩，exit 0。
"""
import argparse
import html
import json
import os
import sys

SEVERITY_ORDER = ["critical", "major", "minor", "info"]
SEVERITY_BADGE = {"critical": "【CRITICAL】", "major": "【MAJOR】",
                  "minor": "【MINOR】", "info": "【INFO】"}
SEVERITY_LABEL = {"critical": "严重（critical）", "major": "重要（major）",
                  "minor": "次要（minor）", "info": "提示（info）"}


def load_json(path):
    if not os.path.isfile(path):
        return None, "file not found: %s" % path
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except Exception as e:
        return None, "cannot parse %s: %s" % (path, e)


def as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def not_reviewed_text(item):
    """not_reviewed 条目兼容 dict {facet, reason} 与纯字符串。"""
    if isinstance(item, dict):
        facet = item.get("facet", "(未命名审查面)")
        reason = item.get("reason", "")
        return "%s —— %s" % (facet, reason) if reason else str(facet)
    return str(item)


def count_matrix(findings):
    """severity×type 交叉计数。types 按字母序保证确定性。返回 (types, {sev: {type: n}})。"""
    types = sorted({str(f.get("type", "(unknown)")) for f in findings
                    if isinstance(f, dict)})
    matrix = {sev: {t: 0 for t in types} for sev in SEVERITY_ORDER}
    for f in findings:
        if not isinstance(f, dict):
            continue
        sev = f.get("severity")
        t = str(f.get("type", "(unknown)"))
        if sev in matrix and t in matrix[sev]:
            matrix[sev][t] += 1
    return types, matrix


def first_sentence(text):
    """取建议的第一句作为优先级清单的行动句。"""
    s = (text or "").strip()
    for sep in ("。", "！", "？", ". ", "! ", "? "):
        idx = s.find(sep)
        if idx >= 0:
            return s[:idx + 1]
    return s


def priority_list(findings):
    """按 critical→major→minor→info 排序（同级按 id 稳定序）。"""
    rank = {s: i for i, s in enumerate(SEVERITY_ORDER)}
    keyed = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        keyed.append((rank.get(f.get("severity"), len(SEVERITY_ORDER)),
                      str(f.get("id", "")), f))
    keyed.sort(key=lambda x: (x[0], x[1]))
    return [f for _, _, f in keyed]


def loc_str(f):
    loc = f.get("location") or {}
    if not isinstance(loc, dict):
        return "(无定位)"
    s = "%s 第%s页" % (loc.get("file", "?"), loc.get("page", "?"))
    if loc.get("section"):
        s += "「%s」" % loc["section"]
    return s


def build_markdown(result, source_path):
    case_id = result.get("case_id", "(unknown)")
    status = result.get("status", "(missing)")
    findings = [f for f in as_list(result.get("findings")) if isinstance(f, dict)]
    not_reviewed = as_list(result.get("not_reviewed"))
    uncertainty = as_list(result.get("uncertainty"))
    change_log = as_list(result.get("change_log"))
    pending = [f for f in findings
               if str(f.get("verdict_status", "")).startswith("待复核")]

    L = []
    L.append("# 审查报告：%s" % case_id)
    L.append("")
    L.append("> 本报告由 report_render.py 自 `%s` 机械渲染生成，内容以 result.json 为准；"
             "合成示例输出，非正式测评结果。" % os.path.basename(source_path))
    L.append("")
    L.append("## 一、概要")
    L.append("")
    L.append("- **交付状态 status**：`%s`" % status)
    L.append("- **问题总数**：%d（critical %d / major %d / minor %d / info %d）"
             % (len(findings),
                sum(1 for f in findings if f.get("severity") == "critical"),
                sum(1 for f in findings if f.get("severity") == "major"),
                sum(1 for f in findings if f.get("severity") == "minor"),
                sum(1 for f in findings if f.get("severity") == "info")))
    L.append("- **待复核**：%d 条" % len(pending))
    L.append("- **概要**：%s" % (result.get("summary") or "(无)"))
    L.append("")
    types, matrix = count_matrix(findings)
    if types:
        L.append("### 严重度 × 类别交叉计数")
        L.append("")
        L.append("| severity | " + " | ".join(types) + " | 合计 |")
        L.append("|" + "---|" * (len(types) + 2))
        for sev in SEVERITY_ORDER:
            row = matrix[sev]
            L.append("| %s | %s | %d |" % (sev, " | ".join(str(row[t]) for t in types),
                                            sum(row.values())))
        L.append("")
    L.append("### 未检查面（not_reviewed）")
    L.append("")
    if not_reviewed:
        for item in not_reviewed:
            L.append("- %s" % not_reviewed_text(item))
    else:
        L.append("- 无（全部审查面均已覆盖）")
    L.append("")
    L.append("## 二、逐条问题卡片")
    L.append("")
    for i, f in enumerate(findings, 1):
        sev = f.get("severity", "info")
        badge = SEVERITY_BADGE.get(sev, "【%s】" % str(sev).upper())
        L.append("### %d. %s %s（%s）"
                 % (i, badge, f.get("id", "F%02d" % i), f.get("type", "(unknown)")))
        L.append("")
        L.append("- **类别 type**：`%s`%s"
                 % (f.get("type", "(unknown)"),
                    "（category: `%s`）" % f["category"] if f.get("category") else ""))
        L.append("- **严重度**：%s" % SEVERITY_LABEL.get(sev, sev))
        L.append("- **定位**：%s" % loc_str(f))
        quote = ((f.get("location") or {}).get("quote")
                 if isinstance(f.get("location"), dict) else None) or "(无逐字摘录)"
        L.append("- **原文摘录**：")
        L.append("")
        for line in str(quote).splitlines() or ["(无逐字摘录)"]:
            L.append("  > " + line)
        L.append("")
        L.append("- **依据 evidence**：%s" % (f.get("evidence") or "(无)"))
        L.append("- **修改建议**：%s" % (f.get("suggestion") or "(无)"))
        L.append("- **判定状态 verdict_status**：%s" % (f.get("verdict_status") or "(无)"))
        L.append("")
    L.append("## 三、修改优先级清单")
    L.append("")
    ordered = priority_list(findings)
    if ordered:
        for f in ordered:
            sev = f.get("severity", "info")
            L.append("- %s **%s**：%s"
                     % (SEVERITY_BADGE.get(sev, ""), f.get("id", "?"),
                        first_sentence(f.get("suggestion"))))
    else:
        L.append("- 无需修改项。")
    L.append("")
    L.append("## 四、不确定项与变更记录")
    L.append("")
    L.append("### uncertainty")
    L.append("")
    if uncertainty:
        for u in uncertainty:
            L.append("- %s" % u)
    else:
        L.append("- 无")
    L.append("")
    L.append("### change_log")
    L.append("")
    if change_log:
        for c in change_log:
            L.append("- %s" % c)
    else:
        L.append("- 无")
    L.append("")
    return "\n".join(L)


HTML_CSS = """
body{font-family:-apple-system,'Helvetica Neue','PingFang SC','Microsoft YaHei',sans-serif;
max-width:920px;margin:2rem auto;padding:0 1rem;color:#1f2328;line-height:1.65}
h1{border-bottom:2px solid #444;padding-bottom:.3rem}
h2{border-bottom:1px solid #ccc;padding-bottom:.2rem;margin-top:2rem}
table{border-collapse:collapse;margin:1rem 0}
th,td{border:1px solid #bbb;padding:.3rem .8rem;text-align:center}
th{background:#f0f2f5}
blockquote{border-left:4px solid #d97706;margin:.6rem 0;padding:.3rem 1rem;
background:#fffbeb;color:#57430e}
.card{border:1px solid #ccc;border-radius:8px;padding:.8rem 1.2rem;margin:1rem 0;
box-shadow:0 1px 2px rgba(0,0,0,.06)}
.badge{display:inline-block;padding:.1rem .55rem;border-radius:10px;color:#fff;
font-size:.82rem;font-weight:700;vertical-align:middle}
.b-critical{background:#c0392b}.b-major{background:#e67e22}
.b-minor{background:#b7950b}.b-info{background:#2e86c1}
.meta{color:#666;font-size:.9rem}
.pending{background:#fdf2e9;border-color:#e67e22}
ul.tight li{margin:.25rem 0}
"""


def md_escape_text(s):
    return html.escape(str(s), quote=False)


def build_html(result, source_path):
    """与 Markdown 同内容的自包含 HTML（内联 CSS，无外部依赖）。"""
    e = md_escape_text
    case_id = result.get("case_id", "(unknown)")
    status = result.get("status", "(missing)")
    findings = [f for f in as_list(result.get("findings")) if isinstance(f, dict)]
    not_reviewed = as_list(result.get("not_reviewed"))
    uncertainty = as_list(result.get("uncertainty"))
    change_log = as_list(result.get("change_log"))
    pending = [f for f in findings
               if str(f.get("verdict_status", "")).startswith("待复核")]
    types, matrix = count_matrix(findings)

    H = ["<!DOCTYPE html><html lang=\"zh\"><head><meta charset=\"utf-8\">",
         "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
         "<title>审查报告：%s</title>" % e(case_id),
         "<style>%s</style></head><body>" % HTML_CSS,
         "<h1>审查报告：%s</h1>" % e(case_id),
         "<p class=\"meta\">本报告由 report_render.py 自 %s 机械渲染生成，内容以 result.json 为准；"
         "合成示例输出，非正式测评结果。</p>" % e(os.path.basename(source_path)),
         "<h2>一、概要</h2><ul class=\"tight\">",
         "<li><b>交付状态 status</b>：<code>%s</code></li>" % e(status),
         "<li><b>问题总数</b>：%d（critical %d / major %d / minor %d / info %d）</li>"
         % (len(findings),
            sum(1 for f in findings if f.get("severity") == "critical"),
            sum(1 for f in findings if f.get("severity") == "major"),
            sum(1 for f in findings if f.get("severity") == "minor"),
            sum(1 for f in findings if f.get("severity") == "info")),
         "<li><b>待复核</b>：%d 条</li>" % len(pending),
         "<li><b>概要</b>：%s</li>" % e(result.get("summary") or "(无)"),
         "</ul>"]
    if types:
        H.append("<h3>严重度 × 类别交叉计数</h3><table><tr><th>severity</th>")
        H.extend("<th>%s</th>" % e(t) for t in types)
        H.append("<th>合计</th></tr>")
        for sev in SEVERITY_ORDER:
            row = matrix[sev]
            H.append("<tr><td><b>%s</b></td>%s<td>%d</td></tr>"
                     % (sev, "".join("<td>%d</td>" % row[t] for t in types),
                        sum(row.values())))
        H.append("</table>")
    H.append("<h3>未检查面（not_reviewed）</h3><ul class=\"tight\">")
    if not_reviewed:
        H.extend("<li>%s</li>" % e(not_reviewed_text(x)) for x in not_reviewed)
    else:
        H.append("<li>无（全部审查面均已覆盖）</li>")
    H.append("</ul><h2>二、逐条问题卡片</h2>")
    for i, f in enumerate(findings, 1):
        sev = f.get("severity", "info")
        is_pending = str(f.get("verdict_status", "")).startswith("待复核")
        quote = ((f.get("location") or {}).get("quote")
                 if isinstance(f.get("location"), dict) else None) or "(无逐字摘录)"
        H.append("<div class=\"card%s\">" % (" pending" if is_pending else ""))
        H.append("<h3>%d. <span class=\"badge b-%s\">%s</span> %s（%s）</h3>"
                 % (i, e(sev), e(str(sev).upper()), e(f.get("id", "F%02d" % i)),
                    e(f.get("type", "(unknown)"))))
        H.append("<ul class=\"tight\">")
        H.append("<li><b>类别 type</b>：<code>%s</code>%s</li>"
                 % (e(f.get("type", "(unknown)")),
                    "（category: <code>%s</code>）" % e(f["category"])
                    if f.get("category") else ""))
        H.append("<li><b>严重度</b>：%s</li>" % e(SEVERITY_LABEL.get(sev, sev)))
        H.append("<li><b>定位</b>：%s</li>" % e(loc_str(f)))
        H.append("</ul>")
        H.append("<b>原文摘录</b><blockquote>%s</blockquote>"
                 % "<br>".join(e(x) for x in str(quote).splitlines()))
        H.append("<ul class=\"tight\">")
        H.append("<li><b>依据 evidence</b>：%s</li>" % e(f.get("evidence") or "(无)"))
        H.append("<li><b>修改建议</b>：%s</li>" % e(f.get("suggestion") or "(无)"))
        H.append("<li><b>判定状态 verdict_status</b>：%s</li>"
                 % e(f.get("verdict_status") or "(无)"))
        H.append("</ul></div>")
    H.append("<h2>三、修改优先级清单</h2><ul class=\"tight\">")
    ordered = priority_list(findings)
    if ordered:
        for f in ordered:
            sev = f.get("severity", "info")
            H.append("<li><span class=\"badge b-%s\">%s</span> <b>%s</b>：%s</li>"
                     % (e(sev), e(str(sev).upper()), e(f.get("id", "?")),
                        e(first_sentence(f.get("suggestion")))))
    else:
        H.append("<li>无需修改项。</li>")
    H.append("</ul><h2>四、不确定项与变更记录</h2><h3>uncertainty</h3><ul class=\"tight\">")
    H.extend("<li>%s</li>" % e(u) for u in uncertainty) if uncertainty else \
        H.append("<li>无</li>")
    H.append("</ul><h3>change_log</h3><ul class=\"tight\">")
    H.extend("<li>%s</li>" % e(c) for c in change_log) if change_log else \
        H.append("<li>无</li>")
    H.append("</ul></body></html>")
    return "\n".join(str(x) for x in H)


def main():
    ap = argparse.ArgumentParser(
        description="把 result.json 渲染成人读审查报告（Markdown + 自包含 HTML）。")
    ap.add_argument("--result", required=True, help="result.json 路径")
    ap.add_argument("--out-md", required=True, help="audit_report.md 输出路径")
    ap.add_argument("--out-html", required=True, help="audit_report.html 输出路径")
    args = ap.parse_args()

    result, err = load_json(args.result)
    if err:
        result = {"case_id": "(unavailable)", "status": "blocked", "findings": [],
                  "summary": "result.json 读取失败：%s" % err,
                  "not_reviewed": [], "uncertainty": [err], "change_log": []}
    md = build_markdown(result, args.result)
    html_doc = build_html(result, args.result)
    for path, text in ((args.out_md, md), (args.out_html, html_doc)):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
            f.write("\n")
    print("rendered %d finding(s) -> %s , %s"
          % (len([f for f in as_list(result.get("findings")) if isinstance(f, dict)]),
             args.out_md, args.out_html))
    return 0


if __name__ == "__main__":
    sys.exit(main())
