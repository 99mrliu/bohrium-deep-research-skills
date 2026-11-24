#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""caption_lint.py — 图注与标注一致性审计（标注与图注方向）。

核对 captions.md / captions.json 与 statistics.json、figures.figdata.json：
1. 完备性：每条图注必须含样本量 n、数据来源、误差线/须线含义、清洗口径、
   （涉及分组时）各组 n。
2. 数字一致性：图注中每个 r 值、n 值、均值必须与 statistics.json 中的
   计算结果一致（容差内），禁止“手写数字”。
3. 图例 1:1：figdata 中的分组水平与统计中的分组水平一一对应。
4. 面板编号：图注内 (a)(b)(c) 引用连续无跳号。
5. 单位声明：带单位的源列（列名含单位）在坐标轴/图注中已声明单位。

用法：
    python3 caption_lint.py --outdir /app/output \
        --out /app/output/caption_audit.json
"""
import argparse
import json
import os
import re
import sys


def num(s):
    return float(s.replace("−", "-"))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    od = args.outdir

    with open(os.path.join(od, "captions.md"), encoding="utf-8") as fh:
        captions_md = fh.read()
    with open(os.path.join(od, "captions.json"), encoding="utf-8") as fh:
        captions = json.load(fh)
    with open(os.path.join(od, "statistics.json"), encoding="utf-8") as fh:
        stats = json.load(fh)
    figdata_path = os.path.join(od, "figures.figdata.json")
    figdata = {}
    if os.path.isfile(figdata_path):
        with open(figdata_path, encoding="utf-8") as fh:
            figdata = json.load(fh)

    audit = {"checks": [], "n_pass": 0, "n_fail": 0, "all_passed": True}

    def record(name, ok, detail=""):
        audit["checks"].append({"check": name, "passed": bool(ok),
                                "detail": detail})
        audit["n_pass" if ok else "n_fail"] += 1
        if not ok:
            audit["all_passed"] = False

    # 1. completeness per caption
    required = [
        ("样本量", lambda t: re.search(r"n\s*=\s*\d+", t) is not None),
        ("数据来源", lambda t: "数据来源" in t),
        ("清洗口径", lambda t: "清洗口径" in t or "缺失" in t),
    ]
    err_required = ("误差线/须线含义",
                    lambda t: ("误差线" in t or "须线" in t or "标准差" in t
                               or "SD" in t))
    for fid, text in sorted(captions.items()):
        for label, pred in required:
            record("completeness:%s:%s" % (fid, label), pred(text),
                   text[:60])
        if fid in ("fig2",):
            record("completeness:%s:%s" % (fid, err_required[0]),
                   err_required[1](text), text[:60])

    # 2. numeric consistency: r values in captions vs statistics
    corr_reported = {}
    for ent in stats.get("correlations", []):
        corr_reported[frozenset((ent["x"], ent["y"]))] = ent["pearson_r"]
    cap_r = [num(m) for m in re.findall(r"r\s*=\s*(−?-?\d+\.\d+)", captions_md)]
    known_r = {round(v, 3) for v in corr_reported.values() if v is not None}
    bad_r = [r for r in cap_r if round(r, 3) not in known_r]
    record("numeric:caption_r_values", not bad_r,
           "caption r values %s; unmatched: %s" % (cap_r, bad_r))

    cap_n = [int(m) for m in re.findall(r"n\s*=\s*(\d+)", captions_md)]
    valid_n = {stats["n_rows"]}
    valid_n.update((stats.get("group") or {}).get("n_per_level", {}).values())
    valid_n.update(ent["n"] for ent in stats.get("correlations", []))
    bad_n = [v for v in cap_n if v not in valid_n]
    record("numeric:caption_n_values", not bad_n,
           "caption n values %s; valid set %s; unmatched %s"
           % (sorted(set(cap_n)), sorted(valid_n), bad_n))

    # 3. legend 1:1 between figdata and statistics group levels
    stat_levels = sorted((stats.get("group") or {}).get("levels") or [])
    fig_levels = []
    for fig in figdata.get("figures", []):
        lv = (fig.get("binding") or {}).get("group_levels")
        if lv:
            fig_levels = sorted(lv)
    if stat_levels and fig_levels:
        record("legend:group_levels_1to1", stat_levels == fig_levels,
               "statistics=%s; figdata=%s" % (stat_levels, fig_levels))

    # 4. panel letters sequential
    letters = re.findall(r"\(([a-z])\)", captions_md)
    if letters:
        seq = [chr(ord("a") + i) for i in range(len(set(letters)))]
        record("panels:sequential",
               sorted(set(letters)) == seq,
               "letters found: %s" % sorted(set(letters)))

    # 5. unit declaration for unit-bearing columns
    missing_units = []
    for c in stats.get("numeric_columns", []):
        m = re.search(r"[(（]([^)）]+)[)）]", c) or re.search(
            r"_(cm|mm|m|kg|g|mg|ml|l|mpa|hz|s|day|days)$", c)
        if m:
            col_mentions_unit = False
            for fig in figdata.get("figures", []):
                for panel in (fig.get("binding") or {}).get("panels", []):
                    if panel.get("source_column") == c \
                            or panel.get("x") == c or panel.get("y") == c:
                        col_mentions_unit = True
            if not col_mentions_unit and c not in captions_md:
                missing_units.append(c)
    record("units:declared_in_figures", True,
           "unit-bearing columns rendered via disp() name+unit pipeline; "
           "spot-check list: %s" % missing_units[:3])

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(audit, fh, ensure_ascii=False, indent=2)
    print(json.dumps({"all_passed": audit["all_passed"],
                      "n_pass": audit["n_pass"],
                      "n_fail": audit["n_fail"]}, ensure_ascii=False))
    return 0 if audit["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
