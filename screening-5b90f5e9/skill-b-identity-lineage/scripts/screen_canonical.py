#!/usr/bin/env python3
"""screen_canonical.py - canonical 级筛选：校验模型判定并传播到副本。

输入:
  /app/work/canonical_records.json
  /app/work/screen_judgments.jsonl  （模型判定，格式见 templates/screen_judgments.md）
输出:
  /app/work/final_decisions.jsonl   canonical 结论 + 副本继承清单
  /app/work/screening_counts.json   included/excluded/needs_human 计数
校验:
  - 每个 canonical 必须有且仅有一条判定；
  - decision ∈ {include, exclude, needs_human}，且 reason_code 前缀一致
    （include→IN-*, exclude→EX-*, needs_human→BND-*）；
  - include/exclude 必须给 evidence_quote，且归一化（NFKC+小写+压缩空白）后
    是 title/abstract 的子串；锚定失败写 anchor_failures.json 并 exit 3（重锚）；
  - needs_human 可免引用，但 note 必填。

退出码: 0=通过; 2=输入缺失; 3=校验失败。
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

DECISION_PREFIX = {"include": "IN-", "exclude": "EX-", "needs_human": "BND-"}


def norm_text(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", str(s)).lower()
    s = re.sub(r"[^0-9a-z一-鿿]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="canonical 级筛选判定校验与传播")
    ap.add_argument("--work", default="/app/work", help="工作目录 (默认 /app/work)")
    ap.add_argument("--judgments", default=None,
                    help="判定文件路径 (默认 /app/work/screen_judgments.jsonl)")
    args = ap.parse_args()
    work = Path(args.work)

    can_path = work / "canonical_records.json"
    if not can_path.exists():
        print(json.dumps({"ok": False, "exit": 2,
                          "reason": "canonical_records.json 不存在，请先运行 build_canonical.py"},
                         ensure_ascii=False))
        return 2
    canonical = json.loads(can_path.read_text(encoding="utf-8"))["canonical_records"]
    can_index = {c["canonical_id"]: c for c in canonical}

    jpath = Path(args.judgments) if args.judgments else work / "screen_judgments.jsonl"
    if not jpath.exists():
        print(json.dumps({"ok": False, "exit": 2,
                          "reason": f"判定文件不存在: {jpath}（需模型批量判定后落盘）"},
                         ensure_ascii=False))
        return 2

    judgments, bad_lines = [], []
    for ln, line in enumerate(jpath.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            judgments.append(json.loads(line))
        except json.JSONDecodeError as e:
            bad_lines.append(f"line {ln}: JSON 解析失败: {e}")

    failures = list(bad_lines)
    by_canon = {}
    for j in judgments:
        cid = j.get("canonical_id")
        if cid not in can_index:
            failures.append(f"未知 canonical_id: {cid}")
            continue
        if cid in by_canon:
            failures.append(f"重复判定: {cid}")
            continue
        by_canon[cid] = j

    for cid in can_index:
        if cid not in by_canon:
            failures.append(f"缺少判定: {cid}")

    for cid, j in by_canon.items():
        dec = j.get("decision")
        rc = (j.get("reason_code") or "").strip()
        if dec not in DECISION_PREFIX:
            failures.append(f"{cid}: decision 非法: {dec!r}")
            continue
        if not rc.startswith(DECISION_PREFIX[dec]):
            failures.append(f"{cid}: reason_code 前缀与 decision 不一致: {rc!r} vs {dec}")
        c = can_index[cid]
        if dec in ("include", "exclude"):
            quote = (j.get("evidence_quote") or "").strip()
            if not quote:
                failures.append(f"{cid}: {dec} 必须提供 evidence_quote")
                continue
            haystack = norm_text((c["screen_text"].get("title") or "") + " "
                                 + (c["screen_text"].get("abstract") or ""))
            if norm_text(quote) not in haystack:
                failures.append(f"{cid}: evidence_quote 锚定失败（非 title/abstract 子串）: "
                                f"{quote[:80]!r}")
        else:
            if not (j.get("note") or "").strip():
                failures.append(f"{cid}: needs_human 必须填写 note 说明原因")

    if failures:
        (work / "anchor_failures.json").write_text(json.dumps(
            {"failures": failures,
             "action": "请按失败项重锚 evidence_quote（必须是 title/abstract 原文片段）后重跑"},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": False, "exit": 3, "failures": failures},
                         ensure_ascii=False))
        return 3

    counts = {"include": 0, "exclude": 0, "needs_human": 0}
    lines = []
    for c in canonical:
        j = by_canon[c["canonical_id"]]
        counts[j["decision"]] += 1
        inherited = [{"record_id": m, "inherited_from": c["canonical_id"],
                      "via": "cluster_lineage"}
                     for m in c["members"] if m != c["canonical_record_id"]]
        lines.append({
            "canonical_id": c["canonical_id"],
            "cluster_id": c["cluster_id"],
            "canonical_record_id": c["canonical_record_id"],
            "decision": j["decision"],
            "reason_code": j["reason_code"],
            "evidence_quote": j.get("evidence_quote"),
            "note": j.get("note"),
            "members": c["members"],
            "propagated_copies": inherited,
        })

    with (work / "final_decisions.jsonl").open("w", encoding="utf-8") as fh:
        for row in lines:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = {"screened": len(canonical),
               "included": counts["include"],
               "excluded": counts["exclude"],
               "needs_human": counts["needs_human"],
               "propagated_records": sum(len(l["propagated_copies"]) for l in lines),
               "closure": len(canonical) == sum(counts.values())}
    (work / "screening_counts.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(3)
