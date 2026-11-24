#!/usr/bin/env python3
"""surgery_lint.py — 最小改动校验：未涉及页哈希不变、主题未被改写、change_records 完整。

用法:
    python3 surgery_lint.py <v1.pptx> <final.pptx> --ops ops_journal.json \
        --log ops_log.json --report surgery_report.json

校验项：
  1. untouched_slides_unchanged：按 ops_journal 重放页索引簿记（insert/delete/move 移位），
     凡未被文本类 op（set_title/replace_text/set_bullets/add_figure）触及的原始页，
     其在最终稿对应位置的 text_hash 必须与 v1 相同；
  2. slide_count_consistent：簿记重放后的页数 == 最终稿页数；
  3. theme_unmodified：ppt/theme/themeN.xml 字节级一致；
  4. change_records_complete：每个 applied op 有非空 reason、存在的 rollback 版本文件、
     version_after 版本文件存在；
  5. failed_ops：存在 failed op 记 error。
退出码：0 = 无 error；1 = 有 error；2 = 输入缺失。
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deck_common as dc

TEXT_OPS = {"set_title", "replace_text", "set_bullets", "add_figure"}


def replay_index_bookkeeping(n_orig: int, applied_ops: list[dict]) -> list:
    """返回与最终稿逐位对应的 token 列表。

    token: ("orig", 原始页号, 是否被文本类 op 修改) 或 ("new", op_id)。
    """
    tokens = [["orig", i, False] for i in range(1, n_orig + 1)]
    for op in applied_ops:
        kind = op["op"]
        if kind in TEXT_OPS:
            pos = op.get("slide")
            if pos and 1 <= pos <= len(tokens) and tokens[pos - 1][0] == "orig":
                tokens[pos - 1][2] = True
        elif kind == "insert_slide":
            after = int(op.get("after") or 0)
            tokens.insert(after, ["new", op["op_id"]])
        elif kind == "delete_slide":
            pos = op.get("slide")
            if pos and 1 <= pos <= len(tokens):
                tokens.pop(pos - 1)
        elif kind == "move_slide":
            frm, to = int(op["params"]["from"]), int(op["params"]["to"])
            if 1 <= frm <= len(tokens) and 1 <= to <= len(tokens):
                tok = tokens.pop(frm - 1)
                tokens.insert(to - 1, tok)
    return tokens


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="最小改动与可审计性校验，输出 surgery_report.json")
    ap.add_argument("v1", help="手术前版本（versions/v1.pptx）")
    ap.add_argument("final", help="手术后最终 deck")
    ap.add_argument("--ops", required=True, help="ops_journal.json")
    ap.add_argument("--log", required=True, help="ops_log.json")
    ap.add_argument("--report", required=True, help="输出 surgery_report.json")
    args = ap.parse_args(argv)

    for p in (args.v1, args.final, args.ops, args.log):
        if not os.path.exists(p):
            print(f"error: input not found: {p}", file=sys.stderr)
            return 2

    d1 = dc.load_deck(args.v1)
    d2 = dc.load_deck(args.final)
    journal = dc.load_json(args.ops)
    log = dc.load_json(args.log)
    status_by_id = {o["op_id"]: o["status"] for o in log.get("ops", [])}
    # 簿记重放以 journal 的完整 op 定义为准，只保留 log 中 applied 的 op
    applied = [op for op in journal.get("ops", [])
               if status_by_id.get(op.get("op_id")) == "applied"]
    applied_log = [o for o in log.get("ops", []) if o["status"] == "applied"]
    failed = [o for o in log.get("ops", []) if o["status"] == "failed"]

    checks, errors, warnings = [], [], []

    # 1) 页数一致性
    tokens = replay_index_bookkeeping(d1["slide_count"], applied)
    count_ok = len(tokens) == d2["slide_count"]
    checks.append({"check": "slide_count_consistent",
                   "expected": len(tokens), "actual": d2["slide_count"], "pass": count_ok})
    if not count_ok:
        errors.append(f"journal bookkeeping predicts {len(tokens)} slides but final deck "
                      f"has {d2['slide_count']}")

    # 2) 未涉及页哈希不变
    untouched_bad = []
    if count_ok:
        hash1 = {s["index"]: s["text_hash"] for s in d1["slides"]}
        for pos, tok in enumerate(tokens, start=1):
            if tok[0] == "orig" and not tok[2]:
                want = hash1[tok[1]]
                got = d2["slides"][pos - 1]["text_hash"]
                if want != got:
                    untouched_bad.append({"orig_slide": tok[1], "final_pos": pos})
                    errors.append(
                        f"untouched slide {tok[1]} changed (final position {pos})"
                    )
    checks.append({"check": "untouched_slides_unchanged",
                   "expected": 0, "actual": len(untouched_bad),
                   "pass": not untouched_bad})

    # 3) 主题未被改写
    t1, t2 = dc.theme_bytes(args.v1), dc.theme_bytes(args.final)
    theme_ok = (t1 == t2) and (t1 is not None)
    checks.append({"check": "theme_unmodified",
                   "expected": d1["theme"].get("sha1"), "actual": d2["theme"].get("sha1"),
                   "pass": theme_ok})
    if not theme_ok:
        errors.append("theme XML bytes differ between v1 and final deck")

    # 4) change_records 完整性
    bad_records = []
    versions_dir = os.path.dirname(os.path.abspath(args.v1))
    for o in log.get("ops", []):
        if o["status"] != "applied":
            continue
        problems = []
        if not (o.get("reason") or "").strip():
            problems.append("empty reason")
        rb = o.get("rollback")
        if not rb or not os.path.exists(rb):
            problems.append(f"rollback missing: {rb}")
        va = o.get("version_after")
        if not va or not os.path.exists(os.path.join(versions_dir, f"{va}.pptx")):
            problems.append(f"version_after missing: {va}")
        if problems:
            bad_records.append({"op_id": o["op_id"], "problems": problems})
            errors.append(f"change_record {o['op_id']}: {'; '.join(problems)}")
    checks.append({"check": "change_records_complete",
                   "expected": f"{len(applied)} complete records",
                   "actual": f"{len(applied) - len(bad_records)} complete records",
                   "pass": not bad_records})

    # 5) failed ops
    checks.append({"check": "no_failed_ops", "expected": 0, "actual": len(failed),
                   "pass": not failed})
    for o in failed:
        errors.append(f"op {o['op_id']} failed: {o.get('detail')}")

    # 附注：journal 里声明但 log 中缺失的 op
    logged = {o["op_id"] for o in log.get("ops", [])}
    for op in journal.get("ops", []):
        if op.get("op_id") not in logged:
            warnings.append(f"journal op {op.get('op_id')} has no log record")

    report = {
        "v1": os.path.abspath(args.v1),
        "final": os.path.abspath(args.final),
        "checks": checks,
        "untouched_violations": untouched_bad,
        "bad_change_records": bad_records,
        "errors": errors,
        "warnings": warnings,
        "pass": not errors,
        "summary": (f"checks={len(checks)} errors={len(errors)} warnings={len(warnings)} "
                    f"applied_ops={len(applied)}"),
    }
    dc.dump_json(report, args.report)
    print(f"surgery_lint: {report['summary']} -> {args.report}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
