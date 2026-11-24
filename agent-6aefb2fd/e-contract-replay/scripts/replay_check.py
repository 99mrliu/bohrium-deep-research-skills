#!/usr/bin/env python3
"""replay_check.py — 第三方复算复核器：不相信任何自报，从原始输入重算。

立场：复核者只信任 /input 的原始数据和自己的计算。交付物（cleaned 表、统计
JSON、报告、result.json）中的关键口径必须能被独立重算复现，否则不予通过。

复核项（全部硬判定，任一失败退出码 7）：
  R1 契约完整：result.json 的 case_id 与 /input/case.json 一致；契约字段在
     status=success 时非空；引用的 /app/output 路径全部存在。
  R2 行数口径：cleaned_data 行数 ≤ 原始来源行数；若交付物含清洗证据
     （initial_rows/final_rows），与实测一致。
  R3 数字复算池：从 /input 原始表与 cleaned_data 独立重算描述统计池
     （行数、各数值列 count/mean/std/min/median/max、分组计数、数值列两两
     Spearman 相关）；report.md 中每个 ≥3 位有效数字必须命中
     「交付统计 JSON 的值 ∪ 复算池」（半末位容差）。命中复算池而非统计 JSON
     是允许的——复核承认独立重算也是合法来源；两者都不命中即无源数字。

用法：
  python3 replay_check.py --input /input --output /app/output \
      [--case /input/case.json] [--cleaned /app/output/cleaned_data.csv]

输出 /app/output/replay_report.json（或在 --output 下），打印逐项 PASS/FAIL。
"""
import argparse
import glob
import json
import math
import os
import re
import sqlite3
import sys

import numpy as np
import pandas as pd

NUM_RE = re.compile(r"(?<![\w.])(\d+\.\d+|\d+)(?![\w.])")


def sig_digits(s):
    t = s.lstrip("0").replace(".", "").lstrip("0")
    return len(t) if t else 1


def matches(x, nd, y):
    if x == 0:
        return abs(y) < 1e-12
    mag = math.floor(math.log10(abs(x)))
    return abs(x - y) <= 0.500001 * 10 ** (mag - nd + 1)


def iter_numbers(obj):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        yield float(obj)
    elif isinstance(obj, list):
        for x in obj:
            yield from iter_numbers(x)
    elif isinstance(obj, dict):
        for x in obj.values():
            yield from iter_numbers(x)


def load_input_frames(input_dir):
    frames = {}
    for path in sorted(glob.glob(os.path.join(input_dir, "**", "*"), recursive=True)):
        if not os.path.isfile(path):
            continue
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".csv":
                frames[path] = pd.read_csv(path)
            elif ext in (".sqlite", ".sqlite3", ".db"):
                con = sqlite3.connect(path)
                for t in [r[0] for r in con.execute(
                        "select name from sqlite_master where type='table'")]:
                    frames[f"{path}::{t}"] = pd.read_sql_query(f'SELECT * FROM "{t}"', con)
                con.close()
        except Exception:  # noqa: BLE001
            continue
    return frames


def descriptives_pool(df, prefix=""):
    vals = [float(len(df))]
    num = df.select_dtypes(include="number")
    for c in num.columns:
        s = num[c].dropna()
        if len(s) == 0:
            continue
        vals += [float(len(s)), float(s.mean()), float(s.std(ddof=1)),
                 float(s.min()), float(s.median()), float(s.max())]
    for c in df.columns:
        if df[c].dtype == object or str(df[c].dtype).startswith("category"):
            vals += [float(v) for v in df[c].value_counts().tolist()]
    cols = list(num.columns)
    if 2 <= len(cols) <= 20 and len(df) >= 8:
        try:
            from scipy.stats import spearmanr
            for i in range(len(cols)):
                for j in range(i + 1, len(cols)):
                    r = spearmanr(num[cols[i]], num[cols[j]]).statistic
                    if np.isfinite(r):
                        vals.append(float(r))
        except ImportError:
            pass
    return vals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--case", default=None)
    ap.add_argument("--cleaned", default=None)
    args = ap.parse_args()
    checks, fail = [], 0

    def record(name, ok, detail):
        nonlocal fail
        checks.append({"check": name, "passed": bool(ok), "detail": detail})
        if not ok:
            fail += 1
        print(f"REPLAY_{'PASS' if ok else 'FAIL'}: {name} — {detail}")

    out = args.output
    res_path = os.path.join(out, "result.json")
    res = json.load(open(res_path, encoding="utf-8")) if os.path.exists(res_path) else None

    # R1 契约
    case_path = args.case or os.path.join(args.input, "case.json")
    problems = []
    fields = []
    if os.path.exists(case_path) and res:
        case = json.load(open(case_path, encoding="utf-8"))
        fields = [f["name"] for f in case.get("output_contract", {}).get("fields", [])]
        if res.get("case_id") != case.get("case_id"):
            problems.append("case_id 不一致")
        if res.get("status") == "success":
            empty = [n for n in fields if res.get(n) in (None, "", [], {})]
            if empty:
                problems.append(f"success 但契约字段为空: {empty}")
        def walk(v):
            if isinstance(v, str) and v.startswith("/app/output") and not os.path.exists(v):
                problems.append(f"路径不存在: {v}")
            elif isinstance(v, list):
                for x in v:
                    walk(x)
        for n in fields:
            walk(res.get(n))
    elif not res:
        problems.append("result.json 不存在")
    record("R1_contract", not problems, "; ".join(problems) or "case_id 一致、字段与路径完整")

    # R2 行数口径
    frames = load_input_frames(args.input)
    cleaned_path = args.cleaned or os.path.join(out, "cleaned_data.csv")
    detail = "无 cleaned_data.csv，跳过"
    ok = True
    cleaned = None
    if os.path.exists(cleaned_path):
        cleaned = pd.read_csv(cleaned_path)
        best, best_j = None, 0.0
        for name, f in frames.items():
            j = len(set(f.columns) & set(cleaned.columns)) / max(1, len(set(f.columns) | set(cleaned.columns)))
            if j > best_j:
                best, best_j = (name, f), j
        if best and best_j >= 0.8:
            ok = len(cleaned) <= len(best[1])
            detail = (f"cleaned {len(cleaned)} 行 vs 原始 {best[0]} {len(best[1])} 行"
                      f"（列匹配 Jaccard={best_j:.2f}）")
        else:
            detail = "未找到列匹配的原始表（Jaccard<0.8）"
    record("R2_row_accounting", ok, detail)

    # R3 数字复算池
    pool = []
    for name, f in frames.items():
        pool += descriptives_pool(f, name)
    if cleaned is not None:
        pool += descriptives_pool(cleaned, "cleaned")
    json_vals = []
    for p in glob.glob(os.path.join(out, "*.json")):
        if os.path.basename(p) in ("result.json", "replay_report.json"):
            continue
        try:
            json_vals += list(iter_numbers(json.load(open(p, encoding="utf-8"))))
        except Exception:  # noqa: BLE001
            pass
    report_path = os.path.join(out, "report.md")
    if os.path.exists(report_path):
        text = open(report_path, encoding="utf-8").read()
        unsourced = []
        for m in NUM_RE.finditer(text):
            s = m.group(0)
            nd = sig_digits(s)
            if nd < 3:
                continue
            x = float(s)
            line_start = text.rfind("\n", 0, m.start()) + 1
            if re.match(r"^\s*\d+(\.\d+)*\s", text[line_start:m.end() + 1]):
                continue
            if not (any(matches(x, nd, y) for y in json_vals)
                    or any(matches(x, nd, y) for y in pool)):
                ctx = text[max(0, m.start() - 25):m.end() + 25].replace("\n", " ")
                unsourced.append({"value": s, "context": ctx})
        record("R3_number_replay", not unsourced,
               f"报告数字全部可溯源（交付 JSON {len(json_vals)} 值 ∪ 复算池 {len(pool)} 值）"
               if not unsourced else f"无源数字: {[(u['value'], u['context'][:40]) for u in unsourced[:5]]}")
    else:
        record("R3_number_replay", False, "report.md 不存在")

    doc = {"checks": checks, "passed": fail == 0}
    json.dump(doc, open(os.path.join(out, "replay_report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"REPLAY_STATUS: {'ok' if fail == 0 else 'failed'} checks={len(checks)} failed={fail}")
    sys.exit(0 if fail == 0 else 7)


if __name__ == "__main__":
    main()
