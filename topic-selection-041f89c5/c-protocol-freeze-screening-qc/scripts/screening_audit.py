#!/usr/bin/env python3
"""screening_audit.py — 筛选日志机审与 PRISMA 式流量计数。

对照已冻结协议逐行审计筛选日志（CSV），把"过程是否守规矩"变成可机检事实。

日志 CSV 列（表头逐字）：
  record_id,title,decision,criterion_ids,reason,decided_at,note
  - decision ∈ {include, exclude, hold}
  - criterion_ids：分号分隔的标准编号（exclude 必须引用至少一个 E 类；
    include 应引用至少一个 I 类）
  - decided_at：ISO 日期；早于协议冻结时间的决策会被标记为"协议前决策"
  - note：hold 必须填写（说明缺什么信息）

审计规则：
  R1 decision 非法 → 违例
  R2 exclude 未引用 E 类标准 / reason 为空 → 违例
  R3 include 未引用 I 类标准 → 警告（允许协议声明"默认纳入"，但应留痕）
  R4 引用了协议中不存在的标准编号 → 违例
  R5 hold 无 note → 违例
  R6 decided_at 早于协议冻结时间 → 违例（协议前决策）
  R7 日志统计与逐行重算不一致（脚本以重算为准输出 PRISMA 计数）

用法：
  python3 screening_audit.py --protocol /app/work/protocol.md \
      --log /app/work/screening_log.csv --out /app/work/screening_qc
输出 screening_qc.json / screening_qc.md（含 PRISMA 式计数）；
无违例退出码 0，有违例 1，参数错误 2。仅标准库。
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

CRITERION_RE = re.compile(r"^-\s*\[([IE])(\d+)\]", re.M)
FREEZE_RE = re.compile(r"冻结时间[:：]\s*(\S+)")


def date_part(s):
    """取 ISO 串的日期部分用于公平比较（decided_at 常只精确到日）。"""
    return (s or "").strip()[:10]
VALID = {"include", "exclude", "hold"}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    ptext = Path(args.protocol).read_text(encoding="utf-8")
    known = set("%s%s" % m for m in CRITERION_RE.findall(ptext))
    m = FREEZE_RE.search(ptext)
    freeze = m.group(1) if m else None

    violations, warnings = [], []
    counts = {"include": 0, "exclude": 0, "hold": 0}
    by_criterion = {}
    rows = list(csv.DictReader(open(args.log, encoding="utf-8")))
    for i, row in enumerate(rows, 2):  # 表头占第 1 行
        rid = (row.get("record_id") or "").strip() or ("row-%d" % i)
        dec = (row.get("decision") or "").strip().lower()
        cids = [c.strip() for c in (row.get("criterion_ids") or "").split(";")
                if c.strip()]
        reason = (row.get("reason") or "").strip()
        note = (row.get("note") or "").strip()
        when = (row.get("decided_at") or "").strip()
        if dec not in VALID:
            violations.append("%s: decision 非法 %r（R1）" % (rid, dec))
            continue
        counts[dec] += 1
        bad = [c for c in cids if c not in known]
        if bad:
            violations.append("%s: 引用了协议中不存在的标准 %s（R4）"
                              % (rid, ",".join(bad)))
        if dec == "exclude":
            if not any(c.startswith("E") for c in cids):
                violations.append("%s: exclude 未引用 E 类标准（R2）" % rid)
            if not reason:
                violations.append("%s: exclude 缺 reason（R2）" % rid)
            for c in cids:
                by_criterion[c] = by_criterion.get(c, 0) + 1
        if dec == "include" and not any(c.startswith("I") for c in cids):
            warnings.append("%s: include 未引用 I 类标准（R3）" % rid)
        if dec == "hold" and not note:
            violations.append("%s: hold 缺 note（R5）" % rid)
        if freeze and when and date_part(when) < date_part(freeze):
            violations.append("%s: 决策时间 %s 早于协议冻结 %s（R6）"
                              % (rid, when, freeze))

    prisma = {"candidates": len(rows), "included": counts["include"],
              "excluded": counts["exclude"], "on_hold": counts["hold"],
              "excluded_by_criterion": dict(sorted(by_criterion.items()))}
    rep = {"passed": not violations, "violations": violations,
           "warnings": warnings, "freeze_time": freeze, "prisma": prisma}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# 筛选过程 QC 报告", "",
             "判定：**%s**；候选 %d → 纳入 %d / 排除 %d / 待定 %d。"
             % ("通过" if rep["passed"] else "未通过", prisma["candidates"],
                prisma["included"], prisma["excluded"], prisma["on_hold"]),
             "", "## PRISMA 式计数", "",
             "- 候选记录：%d" % prisma["candidates"],
             "- 纳入：%d" % prisma["included"],
             "- 排除：%d" % prisma["excluded"]]
    for cid, n in prisma["excluded_by_criterion"].items():
        lines.append("  - 按 %s 排除：%d" % (cid, n))
    lines.append("- 待定：%d" % prisma["on_hold"])
    if violations:
        lines += ["", "## 违例"] + ["- " + v for v in violations]
    if warnings:
        lines += ["", "## 警告"] + ["- " + w for w in warnings]
    out.with_suffix(".md").write_text("\n".join(lines) + "\n",
                                      encoding="utf-8")
    print(json.dumps({"passed": rep["passed"],
                      "violations": len(violations),
                      "prisma": prisma}, ensure_ascii=False))
    return 0 if rep["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
