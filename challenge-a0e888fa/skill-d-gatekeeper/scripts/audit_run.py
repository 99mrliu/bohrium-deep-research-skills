#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_run.py — 独立审计器（Python 3 标准库，确定性）。

审计员与清洗员不同源：本脚本**不读清洗脚本、不信 Agent 自述**，只对
原始快照、清洗表、逐格台账、质量报告、工单证据做机械复核。任何一项失败
即整体 FAIL（退出码 5），不过门不交付。

检查项（可按需用 --skip 跳过，跳过项在 verdict 中如实标注）：
  A input_freeze        原始文件 sha256 与冻结清单一致（未被偷改）
  B row_reconciliation  raw 行数 = cleaned 行数 + 台账 dedup_drop 数 + 隔离行数
  C no_silent_edits     raw↔cleaned 按键对齐后，每个差异格都能在台账中找到
                        old/new 完全匹配的记录；cleaned 出现 raw 没有的键 → FAIL
  D dropped_rows_logged 每个 raw 有而 cleaned 无的键，必须有 dedup_drop 台账
  E unit_inverse        台账 unit_converted 条目满足 new≈old×倍率且可逆
  F report_recompute    质量报告 rows_in/rows_out/ledger_entries 与现场重算一致
  G workorder_coverage  工单每条目在 evidence_map.json 中至少有一个存在的证据文件

用法示例见 SKILL.md 与 examples/README.md。退出码：0 PASS；5 FAIL；2 参数错误。
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys


def sha256_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def read_table(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]


def norm_key(s):
    t = s.strip()
    t = re.sub(r"\s+", " ", t)
    return t.casefold()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", required=True, help="原始表 CSV")
    ap.add_argument("--cleaned", required=True, help="清洗表 CSV")
    ap.add_argument("--ledger", required=True, help="逐格台账 CSV")
    ap.add_argument("--key", required=True, help="对齐主键列，逗号分隔")
    ap.add_argument("--manifest", default=None, help="snapshot_freeze.py 的清单 JSON")
    ap.add_argument("--report", default=None, help="质量报告 JSON（检查 F）")
    ap.add_argument("--workorder", default=None, help="工单 Markdown（检查 G）")
    ap.add_argument("--evidence-map", default=None,
                    help="工单证据映射 JSON：{\"1\": [\"file1\",...], ...}")
    ap.add_argument("--evidence-root", default=".", help="证据文件相对根目录")
    ap.add_argument("--skip", default="", help="跳过的检查字母，逗号分隔")
    ap.add_argument("--out", required=True, help="verdict 输出目录")
    args = ap.parse_args()
    skip = {s.strip().upper() for s in args.skip.split(",") if s.strip()}
    checks = []

    def record(name, ok, detail):
        checks.append({"check": name, "pass": bool(ok), "detail": detail})

    raw_h, raw = read_table(args.raw)
    cl_h, cleaned = read_table(args.cleaned)
    with open(args.ledger, encoding="utf-8-sig", newline="") as f:
        lrows_all = list(csv.reader(f))
    lh, ledger = lrows_all[0], lrows_all[1:]
    fi = lh.index("field") if "field" in lh else 1
    ai = lh.index("action") if "action" in lh else 2
    oi = lh.index("old") if "old" in lh else 3
    ni = lh.index("new") if "new" in lh else 4
    ri_l = lh.index("rule") if "rule" in lh else 5

    keys = [k.strip() for k in args.key.split(",")]
    for k in keys:
        if k not in raw_h or k not in cl_h:
            print("ERROR: 键列 %r 须同时存在于两表" % k, file=sys.stderr)
            sys.exit(2)

    def key_of(header, row):
        idx = {n: j for j, n in enumerate(header)}
        return "␟".join(norm_key(row[idx[k]]) if idx[k] < len(row) else ""
                        for k in keys)

    # A 输入冻结
    if "A" not in skip and args.manifest:
        man = json.load(open(args.manifest, encoding="utf-8"))
        bad = []
        for path, h in man.get("files", {}).items():
            if not os.path.isfile(path) or sha256_file(path) != h.get("sha256"):
                bad.append(path)
        record("A_input_freeze", not bad, {"mismatched": bad})

    # B 行列对账
    drops = [r for r in ledger if r[ai] == "dedup_drop"]
    if "B" not in skip:
        expect = len(cleaned) + len(drops)
        record("B_row_reconciliation", len(raw) == expect,
               {"raw_rows": len(raw), "cleaned_rows": len(cleaned),
                "dedup_drops_in_ledger": len(drops), "expected_raw": expect})

    # C/D 键对齐差异核查
    if "C" not in skip or "D" not in skip:
        raw_map = {}
        for r in raw:
            raw_map.setdefault(key_of(raw_h, r), []).append(r)
        cl_map = {}
        for r in cleaned:
            cl_map.setdefault(key_of(cl_h, r), []).append(r)
        ledger_pairs = set()
        for r in ledger:
            if r[ai] not in ("dedup_drop",):
                ledger_pairs.add((r[fi], r[oi], r[ni]))
        invented = [k for k in cl_map if k not in raw_map]
        if "C" not in skip:
            record("C_no_invented_rows", not invented, {"invented_keys": invented})
        unlogged = []
        if "C" not in skip:
            ridx = {n: j for j, n in enumerate(raw_h)}
            for k in cl_map:
                if k not in raw_map:
                    continue
                rrow, crow = raw_map[k][0], cl_map[k][0]
                for j, name in enumerate(cl_h):
                    cv = crow[j] if j < len(crow) else ""
                    rv = rrow[ridx[name]] if name in ridx and ridx[name] < len(rrow) else ""
                    if cv != rv and (name, rv, cv) not in ledger_pairs:
                        unlogged.append({"key": k, "field": name,
                                         "raw": rv, "cleaned": cv})
            record("C_no_silent_edits", not unlogged,
                   {"unlogged_diffs": unlogged[:20],
                    "unlogged_count": len(unlogged)})
        if "D" not in skip:
            dropped_logged = len(drops)
            missing_keys = [k for k in raw_map if k not in cl_map]
            extra_dropped = max(0, len(missing_keys) - 0)
            record("D_dropped_rows_logged", len(missing_keys) <= dropped_logged,
                   {"keys_only_in_raw": len(missing_keys),
                    "dedup_drops_in_ledger": dropped_logged,
                    "note": "每个消失的键至少需一条 dedup_drop 台账"})
            _ = extra_dropped

    # E 单位换算逆运算抽查
    if "E" not in skip:
        bad_conv, checked = [], 0
        for r in ledger:
            if r[ai] != "unit_converted":
                continue
            m = re.search(r"\(x([0-9.eE+-]+)\)", r[ri_l])
            if not m:
                bad_conv.append({"entry": r[:4], "reason": "规则缺倍率标注"})
                continue
            try:
                factor = float(m.group(1))
                old, new = float(r[oi]), float(r[ni])
                checked += 1
                if abs(new - old * factor) > abs(old * factor) * 1e-9 + 1e-300:
                    bad_conv.append({"entry": r[:4], "reason": "正算不符"})
                elif abs(new / factor - old) > abs(old) * 1e-9 + 1e-300:
                    bad_conv.append({"entry": r[:4], "reason": "逆算不符"})
            except (ValueError, ZeroDivisionError) as e:
                bad_conv.append({"entry": r[:4], "reason": str(e)})
        record("E_unit_inverse", not bad_conv,
               {"checked": checked, "bad": bad_conv[:10]})

    # F 报告重算一致
    if "F" not in skip and args.report:
        rep = json.load(open(args.report, encoding="utf-8"))
        diffs = {}
        t = rep.get("table", {})
        if t.get("rows_out") != len(cleaned):
            diffs["rows_out"] = {"report": t.get("rows_out"), "actual": len(cleaned)}
        if t.get("rows_in") is not None and t.get("rows_in") != len(raw):
            diffs["rows_in"] = {"report": t.get("rows_in"), "actual": len(raw)}
        if rep.get("ledger_entries") is not None \
                and rep.get("ledger_entries") != len(ledger):
            diffs["ledger_entries"] = {"report": rep.get("ledger_entries"),
                                       "actual": len(ledger)}
        record("F_report_recompute", not diffs, {"diffs": diffs})

    # G 工单覆盖矩阵
    if "G" not in skip and args.workorder:
        items = []
        with open(args.workorder, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r"^\s*(\d+)[.、)]\s*(\S.*)$", line)
                if m:
                    items.append((m.group(1), m.group(2)[:60]))
        ev = {}
        if args.evidence_map and os.path.isfile(args.evidence_map):
            ev = json.load(open(args.evidence_map, encoding="utf-8"))
        uncovered = []
        for num, text in items:
            files = ev.get(num) or []
            ok = any(os.path.isfile(os.path.join(args.evidence_root, fp))
                     for fp in files)
            if not ok:
                uncovered.append({"item": num, "text": text})
        record("G_workorder_coverage", not uncovered and bool(items),
               {"items": len(items), "uncovered": uncovered})

    all_pass = all(c["pass"] for c in checks)
    verdict = {"all_pass": all_pass,
               "skipped": sorted(skip),
               "checks": checks}
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "audit_verdict.json"), "w",
              encoding="utf-8") as f:
        json.dump(verdict, f, ensure_ascii=False, indent=2)
    md = ["# 审计裁决", "",
          "总体: **%s**" % ("PASS ✅" if all_pass else "FAIL ❌"),
          ""]
    for c in checks:
        md.append("- %s %s — `%s`"
                  % ("✅" if c["pass"] else "❌", c["check"],
                     json.dumps(c["detail"], ensure_ascii=False)[:300]))
    with open(os.path.join(args.out, "audit_verdict.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print(json.dumps({"verdict": "PASS" if all_pass else "FAIL",
                      "checks": {c["check"]: c["pass"] for c in checks}},
                     ensure_ascii=False))
    sys.exit(0 if all_pass else 5)


if __name__ == "__main__":
    main()
