#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""transform_stub.py — 合成示例用确定性变换脚本（仅标准库，无随机、无网络）。

两种模式：
  stats  统计源文字数等写入 stats.json
  draft  从 main.md 抽取段落生成确定性 draft.md，并写 draft_meta.json；
         若 --table 指向的文件缺失，则在草稿中留下数据缺口占位行。

退出码：0 成功；1 参数/IO 错误。
"""
import argparse
import json
import os
import re
import sys

GAP_LINE = "【数据缺口：{table} 缺失，性能对比数据待补】"


def count_chars(text):
    """正文字数 = CJK 字数 + 字母数字词数。"""
    return (len(re.findall(r"[一-鿿]", text))
            + len(re.findall(r"[A-Za-z0-9]+", text)))


def write_json(obj, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def cmd_stats(a):
    with open(a.input, "r", encoding="utf-8") as f:
        text = f.read()
    stats = {
        "source": a.input,
        "char_count": count_chars(text),
        "paragraphs": len([p for p in text.split("\n\n") if p.strip()]),
        "headings": len(re.findall(r"(?m)^#{1,6}\s", text)),
    }
    write_json(stats, a.output)
    print(f"[stub stats] {a.input} -> {a.output}: {stats['char_count']} 字")
    return 0


def cmd_draft(a):
    with open(a.main, "r", encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"(?m)^#\s+(.+)$", text)
    title = m.group(1).strip() if m else "科研成果"
    paras = [p.strip() for p in text.split("\n\n")
             if p.strip() and not p.strip().startswith("#")]
    body = paras[0] if paras else "（源文无可用段落）"
    lines = [f"# {title}（转化推介稿）", "", body]
    if a.table:
        if os.path.isfile(a.table):
            with open(a.table, "r", encoding="utf-8") as f:
                first = f.readline().strip()
            lines += ["", f"性能对比数据（表头）：{first}"]
        else:
            lines += ["", GAP_LINE.format(table=a.table)]
    draft = "\n".join(lines) + "\n"
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(draft)
    write_json({"draft_chars": count_chars(draft),
                "table_present": bool(a.table and os.path.isfile(a.table))},
               a.meta)
    print(f"[stub draft] -> {a.out}（{count_chars(draft)} 字）")
    return 0


def main():
    p = argparse.ArgumentParser(description="合成示例确定性变换 stub")
    sub = p.add_subparsers(dest="cmd", required=True)
    ps = sub.add_parser("stats")
    ps.add_argument("input")
    ps.add_argument("output")
    ps.set_defaults(fn=cmd_stats)
    pd = sub.add_parser("draft")
    pd.add_argument("--main", required=True)
    pd.add_argument("--out", required=True)
    pd.add_argument("--meta", required=True)
    pd.add_argument("--table", default=None)
    pd.set_defaults(fn=cmd_draft)
    a = p.parse_args()
    try:
        return a.fn(a)
    except OSError as e:
        print(f"[stub] IO 错误: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
