#!/usr/bin/env python3
"""clean_ledger.py — 清洗即记账：有序规则引擎 + 复式行数台账 + 分级异常登记册。

每条清洗规则按固定优先级顺序执行，且必须登记：谓词、rows_in、rows_out、
rows_removed、cells_modified。脚本结束时强制核对会计恒等式：

    初始行数 − 最终行数 == Σ 各规则 rows_removed

任何静默丢行（不平衡）都会以非零退出码失败——宁可报错，不可静默。

规则优先级（见 references/rule_priority.md 的完整论证）：
  R1 结构修复（列名去空白、全空列登记）
  R2 完全重复行：保留首条，删其余
  R3 主键冲突（仅当 rules.json 指定 key_columns）：保留首条
  R4 缺失值：缺失率 ≤5% → 数值列中位数/类别列众数填补；>5% → 不填补，登记
  R5 异常值：1.5×IQR 只标记不删除，写 <name>_outlier_flags.csv

用法：
  python3 clean_ledger.py --table data.csv --name mytable --out /app/work \
      [--rules rules.json] [--key-cols col1,col2]

输出（--out 目录）：
  cleaned_<name>.csv        清洗后数据
  cleaning_ledger.json      台账（每条规则一条分录 + 会计恒等式核对结果）
  anomaly_register.json     分级异常登记册（ok/watch/critical）
  <name>_outlier_flags.csv  异常值标记（仅当有异常值）
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

MISS_WATCH, MISS_CRIT = 0.05, 0.20


def grade(pct, watch=MISS_WATCH, crit=MISS_CRIT):
    return "critical" if pct > crit else ("watch" if pct > watch else "ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True)
    ap.add_argument("--name", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--rules", default=None, help="可选 rules.json：覆盖默认阈值/主键")
    ap.add_argument("--key-cols", default=None)
    args = ap.parse_args()

    cfg = {"miss_impute_max": MISS_WATCH, "iqr_k": 1.5,
           "key_columns": args.key_cols.split(",") if args.key_cols else None}
    if args.rules:
        cfg.update(json.load(open(args.rules, encoding="utf-8")))

    name = args.name or os.path.splitext(os.path.basename(args.table))[0]
    os.makedirs(args.out, exist_ok=True)
    df = pd.read_csv(args.table)
    ledger, register = [], {"table": name, "source": os.path.abspath(args.table),
                            "missing_by_column": {}, "outliers_by_column": {},
                            "duplicates": {}, "notes": []}
    n0 = len(df)

    # R1 结构修复
    cols_before = list(df.columns)
    df.columns = [str(c).strip() for c in df.columns]
    renamed = {b: a for a, b in zip(df.columns, cols_before) if a != b}
    empty_cols = [c for c in df.columns if df[c].isna().all()]
    if empty_cols:
        register["notes"].append(f"全空列（保留但不参与统计）: {empty_cols}")
    ledger.append({"seq": "R1", "rule": "structure_repair",
                   "predicate": "列名 strip；登记全空列",
                   "renamed_columns": renamed, "empty_columns": empty_cols,
                   "rows_in": len(df), "rows_out": len(df), "rows_removed": 0,
                   "cells_modified": 0})

    # R2 完全重复行
    dup_mask = df.duplicated(keep="first")
    n_dup = int(dup_mask.sum())
    if n_dup:
        register["duplicates"]["exact"] = {"removed": n_dup,
                                           "rows": sorted((np.flatnonzero(dup_mask.to_numpy()) + 2).tolist())}
    df = df.loc[~dup_mask].reset_index(drop=True)
    ledger.append({"seq": "R2", "rule": "dedup_exact",
                   "predicate": "全列值完全相同且非首现",
                   "rows_in": int(n_dup + len(df)), "rows_out": len(df),
                   "rows_removed": n_dup, "cells_modified": 0})

    # R3 主键冲突
    if cfg["key_columns"]:
        missing_keys = [k for k in cfg["key_columns"] if k not in df.columns]
        if missing_keys:
            register["notes"].append(f"指定主键列不存在，跳过 R3: {missing_keys}")
            ledger.append({"seq": "R3", "rule": "dedup_key", "predicate": "主键列不存在，跳过",
                           "rows_in": len(df), "rows_out": len(df),
                           "rows_removed": 0, "cells_modified": 0})
        else:
            kmask = df.duplicated(subset=cfg["key_columns"], keep="first")
            n_k = int(kmask.sum())
            register["duplicates"]["key_conflict"] = {"key_columns": cfg["key_columns"],
                                                      "removed": n_k}
            df = df.loc[~kmask].reset_index(drop=True)
            ledger.append({"seq": "R3", "rule": "dedup_key",
                           "predicate": f"主键 {cfg['key_columns']} 重复，保留首条",
                           "rows_in": int(n_k + len(df)), "rows_out": len(df),
                           "rows_removed": n_k, "cells_modified": 0})

    # R4 缺失值
    cells_mod = 0
    for c in df.columns:
        s = df[c]
        nmiss = int(s.isna().sum())
        if nmiss == 0:
            continue
        pct = nmiss / max(1, len(df))
        entry = {"missing": nmiss, "pct": round(pct, 4), "grade": grade(pct)}
        if pct <= cfg["miss_impute_max"] and not df[c].isna().all():
            if pd.api.types.is_numeric_dtype(s):
                fill = float(s.median())
            else:
                fill = s.mode(dropna=True).iloc[0]
            df[c] = s.fillna(fill)
            entry["action"] = "imputed"
            entry["fill_value"] = fill if isinstance(fill, (int, float)) else str(fill)
            cells_mod += nmiss
        else:
            entry["action"] = "kept_and_flagged"
        register["missing_by_column"][c] = entry
    ledger.append({"seq": "R4", "rule": "missing_policy",
                   "predicate": f"缺失率≤{cfg['miss_impute_max']:.0%} 填补（数值=中位数,类别=众数），否则保留并登记",
                   "rows_in": len(df), "rows_out": len(df),
                   "rows_removed": 0, "cells_modified": int(cells_mod)})

    # R5 异常值标记（不删除）
    flag_rows = []
    for c in df.columns:
        s = df[c]
        if not pd.api.types.is_numeric_dtype(s) or s.notna().sum() < 4:
            continue
        q1, q3 = float(s.quantile(0.25)), float(s.quantile(0.75))
        iqr = q3 - q1
        lo, hi = q1 - cfg["iqr_k"] * iqr, q3 + cfg["iqr_k"] * iqr
        idx = np.flatnonzero(((s < lo) | (s > hi)).fillna(False).to_numpy())
        register["outliers_by_column"][c] = {
            "count": int(len(idx)), "fences": [round(lo, 6), round(hi, 6)],
            "grade": "watch" if 0 < len(idx) <= 0.05 * len(df) else
                     ("critical" if len(idx) > 0 else "ok")}
        for i in idx:
            flag_rows.append({"row": int(i) + 2, "column": c,
                              "value": float(s.iloc[i]),
                              "fence_low": round(lo, 6), "fence_high": round(hi, 6)})
    ledger.append({"seq": "R5", "rule": "outlier_flag_only",
                   "predicate": f"{cfg['iqr_k']}×IQR 围栏，只标记不删除",
                   "rows_in": len(df), "rows_out": len(df),
                   "rows_removed": 0, "cells_modified": 0,
                   "flagged_cells": len(flag_rows)})

    # 会计恒等式
    total_removed = sum(e["rows_removed"] for e in ledger)
    balanced = (n0 - len(df)) == total_removed
    ledger_doc = {"table": name, "initial_rows": int(n0), "final_rows": int(len(df)),
                  "total_rows_removed": int(total_removed), "balanced": balanced,
                  "entries": ledger}
    if not balanced:
        json.dump(ledger_doc, open(os.path.join(args.out, "cleaning_ledger.json"), "w",
                                   encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"LEDGER_FAIL: 行数会计不平衡 {n0}-{len(df)} != {total_removed}", file=sys.stderr)
        sys.exit(4)

    cleaned_path = os.path.join(args.out, f"cleaned_{name}.csv")
    df.to_csv(cleaned_path, index=False)
    if flag_rows:
        pd.DataFrame(flag_rows).to_csv(
            os.path.join(args.out, f"{name}_outlier_flags.csv"), index=False)
    json.dump(ledger_doc, open(os.path.join(args.out, "cleaning_ledger.json"), "w",
                               encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(register, open(os.path.join(args.out, "anomaly_register.json"), "w",
                             encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"CLEAN_LEDGER_STATUS: ok rows {n0}->{len(df)} removed={total_removed} "
          f"imputed_cells={cells_mod} outlier_flags={len(flag_rows)} balanced=True")


if __name__ == "__main__":
    main()
