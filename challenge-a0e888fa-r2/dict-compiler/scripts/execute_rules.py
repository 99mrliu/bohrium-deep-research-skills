#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""execute_rules.py — 确定性执行 rules.final.json 中的规则，输出清洗结果与逐格台账。

执行顺序（固定）：
  1. sentinel_missing  哨兵 → 缺失标记（置空 + QC 标记，绝不插补）
  2. dedup             归一化主键去重（keep 依据记入台账）
  3. unit_scale        单位换算（保留原值列 + 新增换算列）
  4. range_qc / physical_bound / lod_below  QC 标记（仅标记，不改数值）

输出：cleaned.csv、ledger.csv（逐格：行/字段/旧值/新值/rule_id/source 行号）、
      digest.md（全部数字从产物重算，含 sha256）。

退出码: 0 = 正常；5 = 输入不合法/执行失败。
"""
import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

NUM_RE = re.compile(r'^-?\d+(\.\d+)?$')
QC_KINDS = ("range_qc", "physical_bound", "lod_below")


def is_num(s):
    return bool(NUM_RE.match(s.strip()))


def fmt(x):
    """确定性数值格式化：消除浮点尾差，整数不带小数点。"""
    if x == int(x) and abs(x) < 1e15:
        return str(int(x))
    s = "%.10f" % x
    s = s.rstrip("0")
    return s[:-1] if s.endswith(".") else s


def sanitize_unit(u):
    return (u.replace("μ", "u").replace("/", "_per_")
             .replace(" ", "").replace("°", "deg"))


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description="规则确定性执行引擎")
    ap.add_argument("--rules", required=True, help="rules.final.json")
    ap.add_argument("--data", required=True, help="待清洗数据 CSV")
    ap.add_argument("--out", required=True, help="输出目录")
    args = ap.parse_args()

    try:
        rules_final = json.loads(Path(args.rules).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print("EXIT 5: 无法读取 rules.final.json: %s" % e, file=sys.stderr)
        return 5
    rules = rules_final.get("rules", [])

    try:
        with open(args.data, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            base_cols = list(reader.fieldnames or [])
            rows = []
            for i, r in enumerate(reader, 1):
                r["_src_row"] = i
                rows.append(r)
    except OSError as e:
        print("EXIT 5: 无法读取数据文件: %s" % e, file=sys.stderr)
        return 5

    n_input = len(rows)
    ledger = []
    seq = [0]
    qc = {}  # (src_row, field) -> [flags]

    def flag(src_row, field, name):
        fl = qc.setdefault((src_row, field), [])
        if name not in fl:
            fl.append(name)

    def log(src_row, field, old, new, action, flag_name, rule):
        seq[0] += 1
        src = rule.get("source", {})
        ledger.append({
            "seq": seq[0], "row": src_row, "field": field,
            "old_value": old, "new_value": new, "action": action,
            "flag": flag_name, "rule_id": rule["rule_id"],
            "source_file": src.get("file", ""),
            "source_line": src.get("line", "")})

    # ---- 1. 哨兵 → 缺失标记（置空，不插补） --------------------------------
    for rule in rules:
        if rule["kind"] != "sentinel_missing":
            continue
        field = rule["field"]
        tokens = set(rule["params"]["tokens"])
        for row in rows:
            if field not in row:
                continue
            raw = row[field]
            if raw is None:
                raw = ""
            if raw.strip() in tokens:
                display = raw if raw.strip() else "blank"
                row[field] = ""
                flag(row["_src_row"], field, "missing")
                log(row["_src_row"], field, raw, "", "marked_missing",
                    "missing:%s" % display, rule)

    # ---- 2. 归一化主键去重 --------------------------------------------------
    for rule in rules:
        if rule["kind"] != "dedup":
            continue
        key = rule["params"]["key"]
        keep = rule["params"].get("keep", "first")
        norm = rule["params"].get("normalize", ["strip", "upper"])

        def normalize(v):
            for op in norm:
                if op == "strip":
                    v = v.strip()
                elif op == "upper":
                    v = v.upper()
                elif op == "lower":
                    v = v.lower()
            return v

        seen = {}
        kept = []
        for row in rows:
            raw = row.get(key, "") or ""
            k = normalize(raw)
            if k in seen:
                drop = row if keep == "first" else seen[k]
                if keep == "last":
                    seen[k] = row
                    kept = [r for r in kept if r is not drop]
                log(drop["_src_row"], key, drop.get(key, ""), "",
                    "dedup_drop",
                    "dup_of_row:%d" % seen[k]["_src_row"], rule)
                if keep == "first":
                    continue
                kept.append(row)
                continue
            seen[k] = row
            kept.append(row)
        rows = kept

    # ---- 3. 单位换算（保留原值列 + 新增换算列） ------------------------------
    conv_cols = []
    for rule in rules:
        if rule["kind"] != "unit_scale":
            continue
        field = rule["field"]
        factor = float(rule["params"]["factor"])
        col = "%s__%s" % (field, sanitize_unit(rule["params"]["to_unit"]))
        if col not in conv_cols:
            conv_cols.append(col)
        for row in rows:
            v = (row.get(field, "") or "").strip()
            if v == "":
                row.setdefault(col, "")
                continue
            if is_num(v):
                new = fmt(float(v) * factor)
                row[col] = new
                log(row["_src_row"], field, row[field], new,
                    "unit_convert",
                    "%s->%s x%s" % (rule["params"]["from_unit"],
                                    rule["params"]["to_unit"],
                                    fmt(factor)), rule)
            else:
                row.setdefault(col, "")
                flag(row["_src_row"], field, "non_numeric")
                log(row["_src_row"], field, row[field], row[field],
                    "uninterpretable", "non_numeric", rule)

    # ---- 4. QC 物理界 / 有效范围 / 检出限（仅标记，不改数值） -----------------
    for rule in rules:
        if rule["kind"] not in QC_KINDS:
            continue
        field = rule["field"]
        p = rule["params"]
        for row in rows:
            v = (row.get(field, "") or "").strip()
            if v == "":
                continue  # 缺失已有 marked_missing 记录，不重复标记
            if not is_num(v):
                flag(row["_src_row"], field, "non_numeric")
                log(row["_src_row"], field, row[field], row[field],
                    "qc_flag", "non_numeric", rule)
                continue
            x = float(v)
            if rule["kind"] == "lod_below":
                if x < float(p["lod"]):
                    flag(row["_src_row"], field, "below_lod")
                    log(row["_src_row"], field, row[field], row[field],
                        "qc_flag", "below_lod:%s" % fmt(float(p["lod"])), rule)
            else:
                lo, hi = float(p["lo"]), float(p["hi"])
                out = (x < lo or x > hi
                       or (x == lo and not p.get("lo_inclusive", True))
                       or (x == hi and not p.get("hi_inclusive", True)))
                if out:
                    lb = "[" if p.get("lo_inclusive", True) else "("
                    rb = "]" if p.get("hi_inclusive", True) else ")"
                    flag(row["_src_row"], field, "out_of_range")
                    log(row["_src_row"], field, row[field], row[field],
                        "qc_flag",
                        "out_of_range:%s%s,%s%s"
                        % (lb, fmt(lo), fmt(hi), rb), rule)

    # ---- 输出 cleaned.csv ---------------------------------------------------
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    qc_fields = []
    for rule in rules:
        if rule["kind"] in QC_KINDS + ("sentinel_missing",) \
                and rule["field"] not in qc_fields:
            qc_fields.append(rule["field"])
    qc_cols = ["%s__qc" % f for f in qc_fields]
    final_cols = base_cols + conv_cols + qc_cols

    cleaned_path = out / "cleaned.csv"
    with open(cleaned_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=final_cols,
                           extrasaction="ignore")
        w.writeheader()
        for row in rows:
            rec = {c: row.get(c, "") for c in final_cols}
            for f in qc_fields:
                rec["%s__qc" % f] = ";".join(
                    qc.get((row["_src_row"], f), []))
            w.writerow(rec)

    # ---- 输出 ledger.csv ----------------------------------------------------
    ledger_path = out / "ledger.csv"
    with open(ledger_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "seq", "row", "field", "old_value", "new_value", "action",
            "flag", "rule_id", "source_file", "source_line"])
        w.writeheader()
        w.writerows(ledger)

    # ---- digest.md（数字从产物重算） ----------------------------------------
    with open(cleaned_path, newline="", encoding="utf-8") as fh:
        rdr = csv.DictReader(fh)
        out_rows = list(rdr)
        out_cols = list(rdr.fieldnames or [])
    with open(ledger_path, newline="", encoding="utf-8") as fh:
        led = list(csv.DictReader(fh))

    def count(pred):
        return sum(1 for e in led if pred(e))

    miss_by_field = {}
    for e in led:
        if e["action"] == "marked_missing":
            miss_by_field[e["field"]] = miss_by_field.get(e["field"], 0) + 1
    flag_counts = {}
    for e in led:
        if e["action"] == "qc_flag":
            name = e["flag"].split(":")[0]
            flag_counts[name] = flag_counts.get(name, 0) + 1

    L = []
    L.append("# 执行摘要 digest")
    L.append("")
    L.append("## 规模（从产物重算）")
    L.append("- 输入数据行: %d" % n_input)
    L.append("- 去重丢弃: %d" % count(lambda e: e["action"] == "dedup_drop"))
    L.append("- 输出数据行: %d" % len(out_rows))
    L.append("- 输出列数: %d" % len(out_cols))
    L.append("")
    L.append("## 变更统计（从 ledger.csv 重算）")
    L.append("- 缺失标记 marked_missing: %d（%s）"
             % (count(lambda e: e["action"] == "marked_missing"),
                ", ".join("%s:%d" % kv for kv in sorted(miss_by_field.items()))
                or "无"))
    L.append("- 单位换算 unit_convert: %d"
             % count(lambda e: e["action"] == "unit_convert"))
    L.append("- QC 标记 qc_flag: %d（%s）"
             % (count(lambda e: e["action"] == "qc_flag"),
                ", ".join("%s:%d" % kv for kv in sorted(flag_counts.items()))
                or "无"))
    L.append("- 无法解释 uninterpretable: %d"
             % count(lambda e: e["action"] == "uninterpretable"))
    L.append("- 台账记录总数: %d" % len(led))
    L.append("")
    L.append("## 完整性")
    L.append("- cleaned.csv sha256: `%s`" % sha256_of(cleaned_path))
    L.append("- ledger.csv  sha256: `%s`" % sha256_of(ledger_path))
    L.append("")
    L.append("## 覆盖缺口与不确定性（来自 rules.final.json）")
    for g in rules_final.get("gaps", []):
        if g["type"] == "uncovered_field":
            L.append("- 未覆盖字段 `%s`：%s。" % (g["field"], g["disposition"]))
        elif g["type"] == "unresolved_line":
            L.append("- 字典行 %s:%s（%s）：%s。"
                     % (g["file"], g["line"], g.get("unparsed_id", ""),
                        g["disposition"]))
        else:
            L.append("- 工单条目 %s：%s。"
                     % (g.get("wo_id", "?"), g["disposition"]))
    if not rules_final.get("gaps"):
        L.append("- （无缺口）")
    L.append("")
    L.append("## 诚实声明")
    L.append("- 未插补任何缺失/非法源值；缺失值仅被分类标记（置空 + QC 标记）。")
    L.append("- 未推断任何总体统计量；QC 物理界/范围/检出限仅做逐格标记，"
             "不修改数值。")
    L.append("- 每一处改动均见 ledger.csv 逐格记录（rule_id + 字典/工单"
             "文件行号），无可追溯出处的处理不存在。")
    (out / "digest.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    print("execute_rules: 输入 %d 行 → 输出 %d 行；台账 %d 条；"
          "cleaned.csv / ledger.csv / digest.md 已写出"
          % (n_input, len(out_rows), len(led)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
