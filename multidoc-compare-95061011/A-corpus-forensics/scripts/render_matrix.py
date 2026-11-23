#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_matrix.py — 把通过机检的 cells.jsonl 渲染成人类可读的 comparison-matrix.md。

矩阵布局：行 = 共同字段（field），列 = 论文（source_document_id）；
单元格显示 value（或 status），并附锚点 paragraph_id#content_hash；
文末附每格 quote 的出处清单。仅做渲染，不做任何数值合成。

用法：
  python3 render_matrix.py --registry <dir-or-registry.json> --cells cells.jsonl \
      --out comparison-matrix.md
退出码：0 正常；1 用法或 IO 错误。
"""
import argparse
import json
import os
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(description="渲染比较矩阵 markdown 视图")
    ap.add_argument("--registry", required=True, help="registry.json 或其所在目录")
    ap.add_argument("--cells", required=True, help="cells.jsonl")
    ap.add_argument("--out", required=True, help="输出 comparison-matrix.md 路径")
    args = ap.parse_args(argv)

    reg_path = args.registry
    if os.path.isdir(reg_path):
        reg_path = os.path.join(reg_path, "registry.json")
    with open(reg_path, "r", encoding="utf-8") as f:
        registry = json.load(f)
    titles = {d["doc_id"]: d.get("title_guess", "") for d in registry.get("documents", [])}

    cells = []
    with open(args.cells, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cells.append(json.loads(line))

    fields = []
    for c in cells:
        if c["field"] not in fields:
            fields.append(c["field"])
    doc_ids = sorted({c["source_document_id"] for c in cells})
    by_key = {(c["field"], c["source_document_id"]): c for c in cells}

    lines = []
    lines.append("# Comparison Matrix (rendered from verified cells)")
    lines.append("")
    lines.append("每格：value（或 status）+ 锚点 `paragraph_id#content_hash`；仅渲染，无数值合成。")
    lines.append("")
    header = "| field | " + " | ".join(doc_ids) + " |"
    sep = "|" + "---|" * (len(doc_ids) + 1)
    lines.append(header)
    lines.append(sep)
    for field in fields:
        row = [field]
        for d in doc_ids:
            c = by_key.get((field, d))
            if c is None:
                row.append("—")
                continue
            if c.get("status") == "reported":
                cell_text = "**%s**" % c.get("value", "")
            else:
                cell_text = "*%s*" % c.get("status")
            anchor = "`%s#%s`" % (c.get("paragraph_id", "?"), c.get("content_hash", "?"))
            row.append("%s<br>%s" % (cell_text, anchor))
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("## Source quotes")
    lines.append("")
    for c in cells:
        q = (c.get("quote") or "").replace("\n", " ")
        lines.append("- `%s` / `%s` / `%s#%s` (%s): \"%s\""
                     % (c["field"], c["source_document_id"], c.get("paragraph_id"),
                        c.get("content_hash"), c.get("status"), q))
    lines.append("")
    lines.append("## Document titles")
    lines.append("")
    for d in doc_ids:
        lines.append("- **%s**: %s" % (d, titles.get(d, "")))
    lines.append("")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("matrix written to %s (%d fields x %d docs)" % (args.out, len(fields), len(doc_ids)),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
