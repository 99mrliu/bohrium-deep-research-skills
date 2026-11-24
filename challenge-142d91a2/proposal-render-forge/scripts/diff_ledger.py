#!/usr/bin/env python3
"""diff_ledger.py -- 版本间修订对照与修改记录表渲染。

用法:
    python3 diff_ledger.py diff OLD_JSON NEW_JSON OUT_MD
    python3 diff_ledger.py revisions DOC_JSON OUT_MD

diff 子命令:
  基于两个版本 document JSON 的实际内容逐节对照（非依赖 revision 声明），
  逐节列出新增/删除/改写段落与字数差，并报告 schedule 等表格的行级变更
  （新增行/删除行/修改行的单元格对照）。供导师评审时说明修改史。
  段落对齐使用 difflib.SequenceMatcher（标准库），结果确定。

revisions 子命令:
  把 document JSON 的 revision 数组（声明的修改史）渲染为 GFM 修改记录表。
  与 diff 报告互为印证：revision 是声明，diff 是可机器复核的事实。
"""
import difflib
import json
import sys

OP_LABEL = {"create": "新建", "add": "新增", "delete": "删除", "rewrite": "改写"}


def count_chars(paras):
    return sum(len("".join(p.split())) for p in paras)


def index_sections(doc):
    return {s["id"]: s for s in doc["sections"]}


def quote(text, prefix="    "):
    return prefix + "「%s」" % text


def diff_paragraphs(old_paras, new_paras):
    """返回 (新增列表, 删除列表, 改写对列表)。改写对为 (旧段, 新段)。"""
    sm = difflib.SequenceMatcher(a=old_paras, b=new_paras, autojunk=False)
    added, deleted, rewritten = [], [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        olds, news = old_paras[i1:i2], new_paras[j1:j2]
        if tag == "delete":
            deleted.extend(olds)
        elif tag == "insert":
            added.extend(news)
        else:  # replace：按位置配对为改写，余者计为新增/删除
            for o, n in zip(olds, news):
                rewritten.append((o, n))
            deleted.extend(olds[len(news):])
            added.extend(news[len(olds):])
    return added, deleted, rewritten


def diff_table(old_tab, new_tab):
    """行级对照：按首列（编号）对齐。返回报告行列表。"""
    if not old_tab and not new_tab:
        return []
    old_rows = {r[0]: r for r in (old_tab or {}).get("rows", [])}
    new_rows = {r[0]: r for r in (new_tab or {}).get("rows", [])}
    lines = []
    for code in new_rows:
        if code not in old_rows:
            lines.append("  - 新增行 %s：%s" % (code, " / ".join(map(str, new_rows[code]))))
    for code in old_rows:
        if code not in new_rows:
            lines.append("  - 删除行 %s：%s" % (code, " / ".join(map(str, old_rows[code]))))
    headers = (new_tab or old_tab)["headers"]
    for code in old_rows:
        if code in new_rows and old_rows[code] != new_rows[code]:
            o, n = old_rows[code], new_rows[code]
            changes = []
            for h, ov, nv in zip(headers, o, n):
                if ov != nv:
                    changes.append("%s %s→%s" % (h, ov, nv))
            lines.append("  - 修改行 %s：%s" % (code, "；".join(changes)))
    return lines


def render_diff(old, new):
    om, nm = old["meta"], new["meta"]
    lines = [
        "# 修订对照报告：%s → %s" % (om["version"], nm["version"]),
        "",
        "- 旧版本：%s（%s）" % (om["version"], om["date"]),
        "- 新版本：%s（%s）" % (nm["version"], nm["date"]),
        "- 题目：%s" % nm["title"],
        "",
    ]
    old_secs, new_secs = index_sections(old), index_sections(new)
    total_old = sum(count_chars(s["paragraphs"]) for s in old["sections"])
    total_new = sum(count_chars(s["paragraphs"]) for s in new["sections"])
    lines.append("全文总字数（段落口径）：%d → %d（Δ %+d）"
                 % (total_old, total_new, total_new - total_old))
    lines.append("")
    unchanged = []
    for sid in new_secs:
        sec_new = new_secs[sid]
        sec_old = old_secs.get(sid)
        lines.append("## 第 %d 节 %s" % (sec_new["number"], sec_new["title"]))
        lines.append("")
        if sec_old is None:
            lines.append("- 整节新增，字数 %d。" % count_chars(sec_new["paragraphs"]))
            lines.append("")
            continue
        added, deleted, rewritten = diff_paragraphs(sec_old["paragraphs"],
                                                    sec_new["paragraphs"])
        tab_lines = diff_table(sec_old.get("table"), sec_new.get("table"))
        if not added and not deleted and not rewritten and not tab_lines:
            unchanged.append(str(sec_new["number"]))
            lines.pop()  # 撤掉标题与空行，统一汇总到文末
            lines.pop()
            continue
        co, cn = count_chars(sec_old["paragraphs"]), count_chars(sec_new["paragraphs"])
        lines.append("字数：%d → %d（Δ %+d）；段落 %d → %d"
                     % (co, cn, cn - co,
                        len(sec_old["paragraphs"]), len(sec_new["paragraphs"])))
        lines.append("")
        for p in added:
            lines.append("- 新增段落：")
            lines.append(quote(p))
        for p in deleted:
            lines.append("- 删除段落：")
            lines.append(quote(p))
        for o, n in rewritten:
            lines.append("- 改写段落（字数 %+d）：" % (count_chars([n]) - count_chars([o])))
            lines.append("  - 原文：")
            lines.append(quote(o))
            lines.append("  - 新文：")
            lines.append(quote(n))
        if tab_lines:
            lines.append("- 表格《%s》行级变更：" % (sec_new.get("table") or {}).get("caption", ""))
            lines.extend(tab_lines)
        lines.append("")
    lines.append("## 无变化章节")
    lines.append("")
    lines.append("第 %s 节内容逐字节一致。" % ("、".join(unchanged) if unchanged else "（无）"))
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("本报告由 diff_ledger.py 基于两版 document JSON 的实际内容机械生成，"
                 "与 revision 数组渲染的修改记录表互为印证。")
    lines.append("")
    return "\n".join(lines)


def render_revisions(doc):
    meta = doc["meta"]
    lines = [
        "# 修改记录表：%s（%s）" % (meta["title"], meta["version"]),
        "",
        "| 日期 | 章节 | 操作 | 理由 |",
        "| --- | --- | --- | --- |",
    ]
    for r in doc["revision"]:
        sec = r["section"]
        sec_label = "全文" if int(sec) == 0 else "第 %s 节" % sec
        lines.append("| %s | %s | %s | %s |"
                     % (r["date"], sec_label,
                        OP_LABEL.get(r["op"], r["op"]),
                        str(r["reason"]).replace("|", "\\|")))
    lines.append("")
    lines.append("共 %d 条记录（来源：document JSON 的 revision 数组）。" % len(doc["revision"]))
    lines.append("")
    return "\n".join(lines)


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        sys.exit("usage: diff_ledger.py diff OLD_JSON NEW_JSON OUT_MD\n"
                 "       diff_ledger.py revisions DOC_JSON OUT_MD")
    mode = argv[1]
    if mode == "diff" and len(argv) == 5:
        with open(argv[2], encoding="utf-8") as f:
            old = json.load(f)
        with open(argv[3], encoding="utf-8") as f:
            new = json.load(f)
        text = render_diff(old, new)
    elif mode == "revisions" and len(argv) == 4:
        with open(argv[2], encoding="utf-8") as f:
            doc = json.load(f)
        text = render_revisions(doc)
    else:
        sys.exit("参数数量错误，见 --help")
    out = argv[-1]
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(json.dumps({"mode": mode, "out": out,
                      "bytes": len(text.encode("utf-8"))}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv)
