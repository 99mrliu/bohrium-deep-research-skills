#!/usr/bin/env python3
"""render_kb.py — 交接渲染第 2 步：生成可导航的知识交接包（确定性渲染）。

把编目与模型的答案（work/answers.json）渲染为一套人读交接物，写入
/app/output/handover/：
  catalog.csv        全文件清单（file_id, 路径, 类型, 大小, sha256前8, 状态, 重复于, 版本标记）
  knowledge_index.md 知识库地图：目录树、版本与重复说明、问题索引（链接到答案卡）
  answers/qXX_<id>.md 每题一张答案卡：答案、带来源坐标的论断、引文原文、
                      不确定性与回链（反向链接到 catalog 行）
  version_notes.md   重复副本与版本标记的并列说明（无版本时如实写"未识别"）
渲染只重组已有内容，不新增事实；所有坐标原样保留供 link_check 核验。
退出码恒 0。
"""
import argparse
import csv
import json
import os
import re
import sys
import time


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    a = ap.parse_args()
    hand = os.path.join(a.out, "handover")
    ans_dir = os.path.join(hand, "answers")
    os.makedirs(ans_dir, exist_ok=True)

    def load(p, default):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return default

    catalog = load(os.path.join(a.work, "render_catalog.json"), {"files": []})
    questions = load(os.path.join(a.work, "questions.json"), {"questions": []})["questions"]
    answers = {x["question_id"]: x for x in
               load(os.path.join(a.work, "answers.json"), {"answers": []}).get("answers", [])}
    by_id = {e["file_id"]: e for e in catalog["files"]}

    # 1) catalog.csv
    with open(os.path.join(hand, "catalog.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file_id", "relpath", "suffix", "size", "sha256_8",
                    "text_status", "n_lines", "duplicate_of", "version_tag"])
        for e in catalog["files"]:
            w.writerow([e["file_id"], e["relpath"], e["suffix"], e["size"],
                        (e["sha256"] or "")[:8], e["text_status"], e["n_lines"],
                        e["duplicate_of"] or "", e["version_tag"] or ""])

    # 2) version_notes.md
    lines = ["# 版本与重复说明", ""]
    dups = [e for e in catalog["files"] if e["duplicate_of"]]
    vers = [e for e in catalog["files"] if e["version_tag"]]
    if dups:
        lines.append("## 字节级重复副本")
        for e in dups:
            lines.append("- `%s` 与 `%s` 内容完全相同（%s）。" % (
                e["relpath"], by_id[e["duplicate_of"]]["relpath"], (e["sha256"] or "")[:8]))
        lines.append("")
    if vers:
        lines.append("## 文件名版本标记")
        for e in vers:
            lines.append("- `%s`：标记 %s（依据文件名；行政备注与内容冲突时以行政备注为准）"
                         % (e["relpath"], e["version_tag"]))
        lines.append("")
    if not dups and not vers:
        lines.append("未识别到重复副本或版本标记。")
    unreadable = [e for e in catalog["files"] if e["text_status"] != "ok"]
    if unreadable:
        lines.append("## 不可读/未抽取文件")
        for e in unreadable:
            lines.append("- `%s`：%s" % (e["relpath"], e["text_status"]))
    with open(os.path.join(hand, "version_notes.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    # 3) 答案卡
    cards = []
    for q in questions:
        qid = q["question_id"]
        ans = answers.get(qid, {})
        card_name = "q_%s.md" % re.sub(r"[^\w\-]+", "_", qid)
        cl = ["# 答案卡 %s" % qid, "",
              "**问题**：%s" % q["question"], "",
              "**答案**：%s" % (ans.get("answer") or "（待答）"), ""]
        if ans.get("claims"):
            cl.append("## 论断与证据")
            for c in ans["claims"]:
                cl.append("- %s" % c.get("claim", ""))
                for ev in c.get("evidence", []):
                    fe = by_id.get(ev.get("file_id"), {})
                    cl.append("  - 证据 `[%s|%s|%s]`：\"%s\"（源文件：%s）" % (
                        ev.get("file_id"), ev.get("sha8", "?"),
                        "L%s-L%s" % (ev.get("line_start", "?"), ev.get("line_end", "?")),
                        ev.get("quote", ""), fe.get("relpath", "?")))
        if ans.get("uncertainty"):
            cl += ["", "## 不确定性"] + ["- %s" % u for u in ans["uncertainty"]]
        cl += ["", "---", "返回 [知识库地图](../knowledge_index.md)"]
        with open(os.path.join(ans_dir, card_name), "w", encoding="utf-8") as f:
            f.write("\n".join(cl) + "\n")
        cards.append((qid, card_name))

    # 4) knowledge_index.md
    tree = {}
    for e in catalog["files"]:
        parts = e["relpath"].split(os.sep)
        d = tree
        for p in parts[:-1]:
            d = d.setdefault(p, {})
        d[parts[-1]] = e["file_id"]

    def render_tree(node, depth=0):
        out = []
        for k in sorted(node):
            if isinstance(node[k], dict):
                out.append("  " * depth + "- %s/" % k)
                out += render_tree(node[k], depth + 1)
            else:
                out.append("  " * depth + "- %s 〔%s〕" % (k, node[k]))
        return out

    il = ["# 知识库地图", "",
          "生成时间：%s。本地图与 catalog.csv、答案卡互链，全部坐标可机检。" %
          time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "",
          "## 文件树", ""] + render_tree(tree) + [
          "", "## 版本与重复", "", "见 [version_notes.md](version_notes.md)。",
          "", "## 问题与答案卡", ""]
    for qid, card in cards:
        il.append("- %s → [answers/%s](answers/%s)" % (qid, card, card))
    il += ["", "## 编目", "", "全文件清单见 [catalog.csv](catalog.csv)。"]
    with open(os.path.join(hand, "knowledge_index.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(il) + "\n")
    print(json.dumps({"cards": len(cards), "files": len(catalog["files"]),
                      "handover": hand}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
