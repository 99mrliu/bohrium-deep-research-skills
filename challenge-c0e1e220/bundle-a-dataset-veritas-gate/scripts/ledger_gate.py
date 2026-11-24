#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ledger_gate — dataset-veritas-gate 重心脚本 2：清洗账本机器核验门。

不信任何台账文件里写的内容：从原始输入**重放**确定性清洗规则，独立验证三件事：
  1. 闭合律（LEDGER_CLOSURE_MISMATCH）
       rows_raw == rows_kept + rows_dropped（用台账自报数字先算一遍）
  2. 规则重放（RULE_REPLAY_MISMATCH）
       重读原始文件 → dedupe exact keep-first（→ 如有 R4 再重放异常剔除）→
       重放得到的 kept/dropped 行号集合必须与台账记录一致
  3. 清洗产物哈希（CLEANED_HASH_MISMATCH）
       重算 cleaned_table.csv 的整文件 sha256 与逐行内容哈希，与台账比对

用法：
  python3 ledger_gate.py check --input-dir /input --work-dir /app/work
      全部通过 exit 0 并打印 PASS 明细；任一违例 exit 1 并打印违例码。
"""
import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipeline_a as pa

CLOSURE = "LEDGER_CLOSURE_MISMATCH"
HASH = "CLEANED_HASH_MISMATCH"
REPLAY = "RULE_REPLAY_MISMATCH"


def _recompute_outlier_flags(post_rows):
    """不读台账：对去重后数据的每个数值列独立重算 1.5×IQR 栅栏与被标记行。
    返回 {col_index: (fences, flagged_row_indices)}。"""
    out = {}
    if not post_rows:
        return out
    n_cols = max(len(r) for r in post_rows)
    for j in range(n_cols):
        vals = [pa.try_float(r[j]) if j < len(r) else None for r in post_rows]
        valid = [v for v in vals if v is not None]
        non_missing = sum(1 for r in post_rows
                          if j < len(r) and not pa.is_missing(r[j]))
        if not non_missing or len(valid) < 0.9 * non_missing or len(valid) < 4:
            continue
        lo, hi = pa.iqr_fences(valid)
        flagged = [i for i, v in enumerate(vals) if v is not None and (v < lo or v > hi)]
        out[j] = ([lo, hi], flagged)
    return out


def replay_rules(raw_rows, ledger):
    """从原始行重放清洗规则（不信台账数字，只按台账记录的规则种类重放）。
    返回 (kept_raw_rows, dropped_raw_rows, detail)。"""
    kept, dup_dropped = pa.dedupe_keep_first(raw_rows)
    post_rows = [r for _, r in kept]
    dropped = list(dup_dropped)
    detail = {"dedupe_dropped": len(dup_dropped)}
    has_r4 = any(r.get("id") == "R4" for r in ledger.get("rules", []))
    if has_r4:
        # R4 异常剔除：从去重后数据确定性重算栅栏与标记行，再重放剔除
        flags = _recompute_outlier_flags(post_rows)
        flagged = sorted({i for _, (_, idxs) in flags.items() for i in idxs})
        detail["outlier_dropped"] = len(flagged)
        detail["recomputed_flagged_rows"] = flagged
        keep_set = [kept[i][0] for i in range(len(kept)) if i not in set(flagged)]
        dropped += [kept[i][0] for i in flagged]
        return sorted(keep_set), sorted(dropped), detail
    return sorted(i for i, _ in kept), sorted(dropped), detail


def check(input_dir, work_dir, ledger_path=None, cleaned_path=None):
    """返回 (ok, lines, violations)。"""
    lines = []
    violations = []
    ledger_path = ledger_path or os.path.join(work_dir, "cleaning_ledger.json")
    if not os.path.isfile(ledger_path):
        return False, [f"[FAIL] 台账不存在: {ledger_path}"], ["LEDGER_MISSING"]
    with open(ledger_path, "r", encoding="utf-8") as f:
        ledger = json.load(f)

    rows_raw = ledger.get("rows_raw")
    rows_kept = ledger.get("rows_kept")
    rows_dropped = ledger.get("rows_dropped")

    # ---- 1. 闭合律（台账自报数字）
    if rows_raw is None or rows_kept is None or rows_dropped is None:
        violations.append(CLOSURE)
        lines.append(f"[FAIL] {CLOSURE}: 台账缺 rows_raw/rows_kept/rows_dropped 字段")
    elif rows_raw != rows_kept + rows_dropped:
        violations.append(CLOSURE)
        lines.append(f"[FAIL] {CLOSURE}: rows_raw({rows_raw}) != "
                     f"rows_kept({rows_kept}) + rows_dropped({rows_dropped})")
    else:
        lines.append(f"[PASS] 闭合律: rows_raw({rows_raw}) == "
                     f"rows_kept({rows_kept}) + rows_dropped({rows_dropped})")

    # ---- 2. 规则重放（不信台账，重读原始输入）
    src_name = ledger.get("source_file")
    src_path = os.path.join(input_dir, src_name) if src_name else None
    if not src_path or not os.path.isfile(src_path):
        violations.append(REPLAY)
        lines.append(f"[FAIL] {REPLAY}: 找不到台账记录的原始文件 {src_name}")
    else:
        src_sha = pa.sha256_file(src_path)
        if src_sha != ledger.get("source_sha256"):
            violations.append(REPLAY)
            lines.append(f"[FAIL] {REPLAY}: 原始文件 sha256 与台账不符"
                         f"（文件已被替换？）{src_sha[:16]}… != {ledger.get('source_sha256', '')[:16]}…")
        kind = ledger.get("source_kind", "csv")
        if kind == "csv":
            raw_rows = pa.read_csv_table(src_path)["rows"]
        else:
            raw_rows = pa.read_sqlite_table(src_path)["rows"]
        kept_replay, dropped_replay, detail = replay_rules(raw_rows, ledger)
        kept_ledger = sorted(ledger.get("kept_raw_rows", []))
        drop_ledger = sorted(
            i for r in ledger.get("rules", []) if r.get("semantics") == "drop"
            for i in r.get("dropped_raw_rows", []))
        replay_rows_raw = len(raw_rows)
        if replay_rows_raw != rows_raw:
            violations.append(REPLAY)
            lines.append(f"[FAIL] {REPLAY}: 重放原始行数 {replay_rows_raw} != 台账 rows_raw {rows_raw}")
        elif kept_replay != kept_ledger:
            violations.append(REPLAY)
            lines.append(f"[FAIL] {REPLAY}: 重放 kept 行号集合与台账不一致"
                         f"（重放 {len(kept_replay)} 行 vs 台账 {len(kept_ledger)} 行）")
        elif sorted(dropped_replay) != drop_ledger:
            violations.append(REPLAY)
            lines.append(f"[FAIL] {REPLAY}: 重放 dropped 行号集合（{len(dropped_replay)} 行）"
                         f"与台账 drop 规则记录（{len(drop_ledger)} 行）不一致")
        else:
            extra = f"，异常剔除 {detail['outlier_dropped']} 行" if "outlier_dropped" in detail else ""
            lines.append(f"[PASS] 规则重放: 原始 {replay_rows_raw} 行 → 去重剔除 "
                         f"{detail['dedupe_dropped']} 行{extra}，kept/dropped 集合与台账完全一致")

    # ---- 3. 清洗产物哈希
    cleaned_path = cleaned_path or os.path.join(work_dir, ledger.get("cleaned_file", "cleaned_table.csv"))
    if not os.path.isfile(cleaned_path):
        violations.append(HASH)
        lines.append(f"[FAIL] {HASH}: 清洗产物不存在: {cleaned_path}")
    else:
        actual_sha = pa.sha256_file(cleaned_path)
        hash_ok = actual_sha == ledger.get("cleaned_sha256")
        row_hash_ok = True
        recomputed = []
        with open(cleaned_path, "r", encoding="utf-8", newline="") as f:
            rdr = csv.reader(f)
            next(rdr, None)
            for r in rdr:
                recomputed.append(pa.row_hash(r))
        ledger_hashes = ledger.get("row_hashes", [])
        if len(recomputed) != len(ledger_hashes):
            row_hash_ok = False
            lines.append(f"[FAIL] {HASH}: 行数不符 cleaned({len(recomputed)}) vs 台账({len(ledger_hashes)})")
        else:
            for i, (a, b) in enumerate(zip(recomputed, ledger_hashes)):
                if a != b:
                    row_hash_ok = False
                    lines.append(f"[FAIL] {HASH}: 第 {i + 1} 数据行内容哈希不符（行被篡改？）")
                    break
        if not hash_ok:
            lines.append(f"[FAIL] {HASH}: cleaned_table.csv 整文件 sha256 与台账不符")
        if not (hash_ok and row_hash_ok):
            violations.append(HASH)
        else:
            lines.append(f"[PASS] 产物哈希: cleaned_table.csv sha256={actual_sha[:16]}…，"
                         f"{len(recomputed)} 行逐行哈希全部一致")

    ok = not violations
    lines.insert(0, f"ledger_gate {'PASS' if ok else 'FAIL'} — {ledger.get('source_file')}")
    return ok, lines, violations


def main():
    ap = argparse.ArgumentParser(prog="ledger_gate.py", description="清洗账本机器核验门")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pc = sub.add_parser("check")
    pc.add_argument("--input-dir", required=True)
    pc.add_argument("--work-dir", required=True)
    pc.add_argument("--ledger", default=None)
    pc.add_argument("--cleaned", default=None)
    args = ap.parse_args()
    ok, lines, violations = check(args.input_dir, args.work_dir,
                                  args.ledger, args.cleaned)
    for ln in lines:
        print(ln)
    if violations:
        print("violations: " + ",".join(sorted(set(violations))))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
