#!/usr/bin/env python3
"""protocol_lint.py — 筛选协议结构检查器。

协议是筛选的"冻结规则"：每条纳排标准必须编号化、可机械执行、
且声明冻结时间。本脚本解析 protocol.md 并检查：

  - 存在 `冻结时间: <ISO-8601>` 行（协议冻结留痕）；
  - 标准条目格式：`- [I1] ...`（纳入）/ `- [E1] ...`（排除），ID 唯一；
  - 每条标准正文 ≥10 个字符（排除"同上"式空标准）；
  - 至少 1 条纳入标准与 1 条排除标准；
  - 修订区（`## 修订记录`）若存在，每条修订须有日期与原因。

用法：
  python3 protocol_lint.py --protocol /app/work/protocol.md \
      --out /app/work/protocol_lint
输出 protocol_lint.json / protocol_lint.md；
通过退出码 0，违例 1，参数错误 2。仅标准库。
"""
import argparse
import json
import re
import sys
from pathlib import Path

CRITERION_RE = re.compile(r"^-\s*\[([IE])(\d+)\]\s*(.+)$")
FREEZE_RE = re.compile(r"冻结时间[:：]\s*(\S+)")
REVISION_RE = re.compile(r"^-\s*(\d{4}-\d{2}-\d{2})\s+(.+)$")


def lint(text):
    fails, warns = [], []
    criteria = {}
    m = FREEZE_RE.search(text)
    freeze_time = m.group(1) if m else None
    if not freeze_time:
        fails.append("缺少 `冻结时间: <ISO-8601>` 行，协议未冻结")
    in_revision = False
    revision_count = 0
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            in_revision = s.startswith("## 修订记录")
            continue
        cm = CRITERION_RE.match(s)
        if cm:
            kind, num, body = cm.groups()
            cid = kind + num
            if cid in criteria:
                fails.append("标准编号重复: %s" % cid)
            if len(body) < 10:
                fails.append("标准 %s 正文过短（<10 字符），不可机械执行" % cid)
            criteria[cid] = {"kind": "include" if kind == "I" else "exclude",
                             "text": body}
            continue
        if in_revision and s.startswith("-"):
            if REVISION_RE.match(s):
                revision_count += 1
            else:
                warns.append("修订记录条目缺日期或原因: %s" % s[:60])
    n_inc = sum(1 for c in criteria.values() if c["kind"] == "include")
    n_exc = sum(1 for c in criteria.values() if c["kind"] == "exclude")
    if n_inc == 0:
        fails.append("没有任何纳入标准 [I*]")
    if n_exc == 0:
        fails.append("没有任何排除标准 [E*]")
    return {"passed": not fails, "fails": fails, "warnings": warns,
            "freeze_time": freeze_time,
            "criteria": sorted(criteria), "n_include": n_inc,
            "n_exclude": n_exc, "n_revisions": revision_count}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    text = Path(args.protocol).read_text(encoding="utf-8")
    rep = lint(text)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# 协议结构检查", "",
             "判定：**%s**；纳入标准 %d 条、排除标准 %d 条、修订 %d 条；冻结时间：%s。"
             % ("通过" if rep["passed"] else "未通过", rep["n_include"],
                rep["n_exclude"], rep["n_revisions"],
                rep["freeze_time"] or "缺失"), ""]
    if rep["fails"]:
        lines.append("## 违例")
        lines += ["- " + f for f in rep["fails"]]
    if rep["warnings"]:
        lines.append("## 警告")
        lines += ["- " + w for w in rep["warnings"]]
    out.with_suffix(".md").write_text("\n".join(lines) + "\n",
                                      encoding="utf-8")
    print(json.dumps({"passed": rep["passed"], "fails": len(rep["fails"]),
                      "criteria": len(rep["criteria"])}, ensure_ascii=False))
    return 0 if rep["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
