#!/usr/bin/env python3
"""ledger_check.py — 台账独立复核器：不相信 clean_ledger 的自报，重新验证。

以第三方姿态复核一次清洗：
  1. 重读原始表与 cleaned_<name>.csv，独立重算默认规则（R2 完全重复、R4 中位数/众数
     填补、R5 1.5×IQR 围栏），与 cleaning_ledger.json 的每条分录逐项比对；
  2. 验证会计恒等式 初始行数−最终行数=Σrows_removed；
  3. 抽验 outlier flags：每个被标记值确实越出围栏；每个越出围栏的值确实被标记。

用法：
  python3 ledger_check.py --table 原始.csv --work /app/work --name mytable

退出码：0=复核通过；5=发现不一致（明细打印到 stderr 并写 ledger_check.json）。
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True, help="清洗前的原始 CSV")
    ap.add_argument("--work", required=True, help="clean_ledger.py 的输出目录")
    ap.add_argument("--name", default=None)
    args = ap.parse_args()
    name = args.name or os.path.splitext(os.path.basename(args.table))[0]

    problems = []
    raw = pd.read_csv(args.table)
    raw.columns = [str(c).strip() for c in raw.columns]
    cleaned = pd.read_csv(os.path.join(args.work, f"cleaned_{name}.csv"))
    ledger = json.load(open(os.path.join(args.work, "cleaning_ledger.json"),
                            encoding="utf-8"))

    # 1. 会计恒等式
    if ledger["initial_rows"] != len(raw):
        problems.append(f"台账 initial_rows={ledger['initial_rows']} 与实际原始行数 {len(raw)} 不符")
    if ledger["final_rows"] != len(cleaned):
        problems.append(f"台账 final_rows={ledger['final_rows']} 与 cleaned 文件行数 {len(cleaned)} 不符")
    if ledger["initial_rows"] - ledger["final_rows"] != ledger["total_rows_removed"]:
        problems.append("台账自身不平衡：initial−final ≠ Σrows_removed")

    # 2. 独立重算 R2（完全重复行）
    expect_after_dup = raw.loc[~raw.duplicated(keep="first")].reset_index(drop=True)
    r2 = next((e for e in ledger["entries"] if e["seq"] == "R2"), None)
    if r2 and r2["rows_removed"] != int(raw.duplicated(keep="first").sum()):
        problems.append(f"R2 登记删除 {r2['rows_removed']}，独立重算为 "
                        f"{int(raw.duplicated(keep='first').sum())}")

    # 3. 独立重算 R4（填补值）
    r4 = next((e for e in ledger["entries"] if e["seq"] == "R4"), None)
    recomputed_cells = 0
    ref = expect_after_dup.copy()
    for c in ref.columns:
        s = ref[c]
        nmiss = int(s.isna().sum())
        if nmiss == 0 or len(s) == 0:
            continue
        pct = nmiss / len(s)
        if pct <= 0.05 and not s.isna().all():
            fill = float(s.median()) if pd.api.types.is_numeric_dtype(s) \
                else s.mode(dropna=True).iloc[0]
            recomputed_cells += nmiss
            got = cleaned[c]
            exp = s.fillna(fill)
            if len(got) == len(exp) and not np.allclose(
                    pd.to_numeric(got, errors="coerce").to_numpy(dtype=float, na_value=np.nan),
                    pd.to_numeric(exp, errors="coerce").to_numpy(dtype=float, na_value=np.nan),
                    rtol=1e-9, atol=1e-12, equal_nan=True):
                problems.append(f"R4 列 {c} 填补结果与独立重算不一致")
    if r4 and r4["cells_modified"] != recomputed_cells:
        problems.append(f"R4 登记填补 {r4['cells_modified']} 格，独立重算为 {recomputed_cells}")

    # 4. 异常值标记完备性
    flag_path = os.path.join(args.work, f"{name}_outlier_flags.csv")
    flags = pd.read_csv(flag_path) if os.path.exists(flag_path) else pd.DataFrame(
        columns=["row", "column", "value", "fence_low", "fence_high"])
    flagged = {(int(r["row"]) - 2, r["column"]) for _, r in flags.iterrows()}
    expect_flag = set()
    base = cleaned
    for c in base.columns:
        s = base[c]
        if not pd.api.types.is_numeric_dtype(s) or s.notna().sum() < 4:
            continue
        q1, q3 = float(s.quantile(0.25)), float(s.quantile(0.75))
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        for i in np.flatnonzero(((s < lo) | (s > hi)).fillna(False).to_numpy()):
            expect_flag.add((int(i), c))
    if flagged != expect_flag:
        problems.append(f"R5 异常标记与独立重算不一致：多标 {sorted(flagged - expect_flag)[:5]}，"
                        f"漏标 {sorted(expect_flag - flagged)[:5]}")

    doc = {"table": name, "problems": problems, "passed": not problems}
    json.dump(doc, open(os.path.join(args.work, "ledger_check.json"), "w",
                        encoding="utf-8"), ensure_ascii=False, indent=2)
    if problems:
        for p in problems:
            print("LEDGER_CHECK_FAIL:", p, file=sys.stderr)
        sys.exit(5)
    print(f"LEDGER_CHECK_STATUS: ok independent recompute matches ledger for '{name}'")


if __name__ == "__main__":
    main()
