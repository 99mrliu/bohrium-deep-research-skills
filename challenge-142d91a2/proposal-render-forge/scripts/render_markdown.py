#!/usr/bin/env python3
"""render_markdown.py -- 开题文档 JSON -> 可编辑 Markdown（确定性渲染）。

用法:
    python3 render_markdown.py DOC_JSON OUT_MD

渲染规则:
  - 章节编号由 sections 数组自动生成（校验恰好为 1..7 连续不重）；
  - 表格渲染为 GFM 表格（单元格内 | 转义为 \\|）；
  - 段落中的 [S#] 来源标注原样保留，文末依据 sources 数组自动生成来源清单；
  - 页眉信息（版本/日期等）全部取自 meta 字段，脚本不读系统时钟。

确定性: 同一输入 JSON 必产生字节级一致的输出（可用 cmp 验证）。
拦截: schema 校验失败时打印全部错误并以退出码 2 拒绝渲染（fail-fast）。
schema 详见 references/document_schema.md。
"""
import json
import re
import sys

SECTION_IDS = [
    "background_gap", "problem_definition", "objectives",
    "technical_route", "schedule", "risks", "outcomes",
]
META_REQUIRED = ["title", "discipline", "degree", "author", "advisor",
                 "period", "budget_wan", "version", "date"]
PERIOD_REQUIRED = ["start", "end", "quarters"]
SCHEDULE_HEADERS = ["编号", "任务", "开始季度", "结束季度", "交付物"]
CITE_RE = re.compile(r"\[S\d+\]")


def validate_document(doc):
    """返回错误列表；空列表表示通过。所有规则见 references/document_schema.md 第 6 节。"""
    errors = []
    meta = doc.get("meta")
    if not isinstance(meta, dict):
        errors.append("缺少 meta 对象")
    else:
        for k in META_REQUIRED:
            if k not in meta:
                errors.append("meta 缺少必备字段: %s" % k)
        period = meta.get("period")
        if isinstance(period, dict):
            for k in PERIOD_REQUIRED:
                if k not in period:
                    errors.append("meta.period 缺少必备字段: %s" % k)
        else:
            errors.append("meta.period 必须为对象")

    sections = doc.get("sections")
    if not isinstance(sections, list):
        errors.append("缺少 sections 数组")
    else:
        if len(sections) != 7:
            errors.append("sections 必须恰好 7 项（七要素），实际 %d 项" % len(sections))
        numbers = [s.get("number") for s in sections if isinstance(s, dict)]
        if sorted(numbers) != [1, 2, 3, 4, 5, 6, 7]:
            errors.append("章节 number 必须恰好为 1..7 连续不重，实际: %s" % numbers)
        for s in sections:
            if not isinstance(s, dict):
                errors.append("存在非对象章节条目")
                continue
            sid = s.get("id")
            if sid not in SECTION_IDS:
                errors.append("章节 id 非法（须属于七要素固定集合）: %s" % sid)
            paras = s.get("paragraphs")
            if (not isinstance(paras, list) or not paras
                    or any(not isinstance(p, str) or not p.strip() for p in paras)):
                errors.append("章节 %s 的 paragraphs 必须为非空字符串数组" % sid)
        sched = [s for s in sections if isinstance(s, dict) and s.get("id") == "schedule"]
        if sched:
            tab = sched[0].get("table")
            if not isinstance(tab, dict):
                errors.append("schedule 节必须含 table（甘特图单一事实源）")
            else:
                if tab.get("headers") != SCHEDULE_HEADERS:
                    errors.append("schedule 表头必须为 %s，实际: %s"
                                  % (SCHEDULE_HEADERS, tab.get("headers")))
                quarters = (doc.get("meta") or {}).get("period", {}).get("quarters")
                for row in tab.get("rows", []):
                    try:
                        start, end = int(row[2]), int(row[3])
                        if not (1 <= start <= end):
                            raise ValueError
                        if isinstance(quarters, int) and end > quarters:
                            errors.append("schedule 行 %s 结束季度 %d 超出周期总季度数 %d"
                                          % (row[0], end, quarters))
                    except (IndexError, TypeError, ValueError):
                        errors.append("schedule 行起止季度非法（须为 1<=起<=止 的整数）: %s" % row)

    sources = doc.get("sources")
    if not isinstance(sources, list):
        errors.append("缺少 sources 数组（可为空数组）")
        sources = []
    known = {s.get("id") for s in sources if isinstance(s, dict)}
    for s in (sections or []):
        if not isinstance(s, dict):
            continue
        for p in s.get("paragraphs") or []:
            if not isinstance(p, str):
                continue
            for tag in CITE_RE.findall(p):
                if tag.strip("[]") not in known:
                    errors.append("章节 %s 存在悬挂引用 %s（sources 中无对应条目）"
                                  % (s.get("id"), tag))
    if not isinstance(doc.get("revision"), list):
        errors.append("缺少 revision 数组（初稿至少含一条 create 记录）")
    return errors


def esc_cell(x):
    return str(x).replace("|", "\\|")


def render_table(tab):
    out = ["", "**%s**" % tab["caption"], ""]
    out.append("| " + " | ".join(esc_cell(h) for h in tab["headers"]) + " |")
    out.append("|" + "|".join([" --- "] * len(tab["headers"])) + "|")
    for row in tab["rows"]:
        out.append("| " + " | ".join(esc_cell(c) for c in row) + " |")
    out.append("")
    return out


def render_source(s):
    parts = ["[%s] %s. %s. %s, %s."
             % (s["id"], s.get("authors", ""), s.get("title", ""),
                s.get("venue", ""), s.get("year", ""))]
    if s.get("url"):
        parts.append(s["url"] + ".")
    if s.get("note"):
        parts.append("（%s）" % s["note"])
    return " ".join(parts)


def render_markdown(doc):
    meta = doc["meta"]
    period = meta["period"]
    lines = [
        "# %s" % meta["title"],
        "",
        "- 学科方向：%s（%s）" % (meta["discipline"], meta["degree"]),
        "- 申请人：%s；导师：%s" % (meta["author"], meta["advisor"]),
        "- 研究周期：%s 至 %s（共 %d 个季度）"
        % (period["start"], period["end"], int(period["quarters"])),
        "- 经费预算：%s 万元" % meta["budget_wan"],
        "- 版本：%s（%s）" % (meta["version"], meta["date"]),
        "",
        "---",
        "",
    ]
    for sec in sorted(doc["sections"], key=lambda s: s["number"]):
        lines.append("## %d %s" % (sec["number"], sec["title"]))
        lines.append("")
        for p in sec["paragraphs"]:
            lines.append(p)
            lines.append("")
        if sec.get("table"):
            lines.extend(render_table(sec["table"]))
    lines.append("## 参考文献")
    lines.append("")
    for s in doc["sources"]:
        lines.append(render_source(s))
        lines.append("")
    return "\n".join(lines)


def main(argv):
    if len(argv) != 3 or argv[1] in ("-h", "--help"):
        sys.exit("usage: render_markdown.py DOC_JSON OUT_MD")
    with open(argv[1], encoding="utf-8") as f:
        doc = json.load(f)
    errors = validate_document(doc)
    if errors:
        print("schema 校验失败，拒绝渲染（共 %d 处）:" % len(errors), file=sys.stderr)
        for e in errors:
            print("  - %s" % e, file=sys.stderr)
        sys.exit(2)
    text = render_markdown(doc)
    with open(argv[2], "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(json.dumps({"out": argv[2], "bytes": len(text.encode("utf-8")),
                      "sections": len(doc["sections"]),
                      "sources": len(doc["sources"])}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv)
