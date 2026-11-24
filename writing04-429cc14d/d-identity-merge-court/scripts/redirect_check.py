#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""redirect_check.py — 引用重定向复核（identity-merge-court / 方向 D）。

归并施加后，所有被并条目的引用出现点必须全部重定向到 canonical。
本脚本按"标签字符串检索"检查稿件中是否仍残留被并 id / 原 cite key：
  - 检查对象：redirect_map.json 中每个被吸收记录的 record_id 与原 cite_key；
  - 匹配方式：边界安全的字面检索（前后不得紧邻字母/数字/下划线/连字符）；
  - 输出：残留清单 residual_report.json / residual_report.md；
  - 退出码：有残留 → 1；干净 → 0；输入错误 → 2。

用法：
  python3 redirect_check.py --manuscript manuscript.txt --redirect_map redirect_map.json --out OUTDIR
  竞赛环境：python3 /skills/weekly-skill/scripts/redirect_check.py --manuscript /app/work/manuscript.txt \
      --redirect_map /app/work/merge/redirect_map.json --out /app/work/redirect
"""
import argparse
import json
import re
import sys
from pathlib import Path

SCHEMA_VERSION = "1.0"


def main(argv=None):
    ap = argparse.ArgumentParser(description="引用重定向复核：检出仍引用被并 id/原标签的残留")
    ap.add_argument("--manuscript", required=True)
    ap.add_argument("--redirect_map", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    try:
        text = Path(args.manuscript).read_text(encoding="utf-8")
        rmap = json.loads(Path(args.redirect_map).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"输入读取失败: {exc}", file=sys.stderr)
        return 2

    # 每个被吸收记录 → 待检索标签集合 + 重定向目标
    checks = []  # (label, absorbed_id, canonical_id)
    rec_red = rmap.get("record_redirects", {})
    key_red = rmap.get("cite_key_redirects", {})
    for absorbed, canon in sorted(rec_red.items()):
        checks.append((absorbed, absorbed, canon))
    for old_key, new_key in sorted(key_red.items()):
        absorbed = next((a for a, c in rec_red.items()
                         if key_red.get(a) == new_key and a in rec_red), None)
        checks.append((old_key, absorbed or "", new_key))

    residuals = []
    lines = text.splitlines()
    seen = set()
    for label, absorbed, canon in checks:
        if not label or label in seen:
            continue
        seen.add(label)
        pat = re.compile(r"(?<![\w-])" + re.escape(label) + r"(?![\w-])")
        for lineno, line in enumerate(lines, 1):
            if pat.search(line):
                residuals.append({"label": label, "absorbed_record_id": absorbed,
                                  "redirect_to": canon, "line": lineno,
                                  "excerpt": line.strip()[:200]})

    report = {"schema_version": SCHEMA_VERSION, "tool": "redirect_check.py",
              "manuscript": str(args.manuscript),
              "checked_labels": sorted(seen),
              "residual_count": len(residuals),
              "clean": not residuals,
              "residuals": residuals}

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "residual_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = ["# 引用重定向残留复核", "",
          f"- 稿件: {args.manuscript}",
          f"- 检查标签数: {len(seen)}",
          f"- 残留: {len(residuals)}", ""]
    if residuals:
        md.append("| 行号 | 残留标签 | 应重定向到 | 摘录 |")
        md.append("|---|---|---|---|")
        for r in residuals:
            md.append(f"| {r['line']} | `{r['label']}` | `{r['redirect_to']}` | {r['excerpt']} |")
    else:
        md.append("无残留：所有被并标签均已重定向到 canonical。")
    (out_dir / "residual_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    if residuals:
        print(f"发现 {len(residuals)} 处残留引用（退出码 1）：")
        for r in residuals:
            print(f"  行 {r['line']}: `{r['label']}` 应重定向到 `{r['redirect_to']}`")
        print(f"详见 {out_dir}/residual_report.json")
        return 1
    print(f"无残留：{len(seen)} 个被并标签均未在稿件中出现（退出码 0）。")
    print(f"已写出: {out_dir}/residual_report.json, residual_report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
