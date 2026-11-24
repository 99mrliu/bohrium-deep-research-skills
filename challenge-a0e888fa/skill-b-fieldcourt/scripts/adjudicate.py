#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""adjudicate.py — 裁定验证与确定性执行引擎（Python 3 标准库）。

输入：field_survey.py 产出、经 Agent 填写的 decisions.json。
两段式：
  --validate   只校验：字段全覆盖、missing 分类合法、单位在注册表、
               key_columns 存在、每个非默认处置都有 source 依据；不触碰数据。
  --run        校验通过后确定性执行：缺失分类标记、单位可乘换算（带逆运算
               复核）、归一化去重（冲突全部保留并隔离）、物理界标记。
产物：cleaned.csv、ledger.csv（逐格台账）、review_queue.csv、
      field_summary.json、digest.md（Agent 一次读完的紧凑摘要）。
铁律：绝不插补；未声明的字段一律原样保留；换算失败回退原值并记台账。
退出码：0 正常；2 参数错误；4 校验失败；6 运行期硬错误。
"""
import argparse
import csv
import decimal
import json
import os
import re
import sys

decimal.getcontext().prec = 40

MISSING_CLASSES = {"not_detected", "below_lod", "entry_missing", "true_zero"}
POLICIES = {"mark", "empty", "keep"}
# 单位注册表：仅可乘线性换算（相对因子）；温度等带偏移换算一律拒绝。
UNIT_REGISTRY = {
    "concentration": {"mg/L": 1.0, "μg/mL": 1.0, "µg/mL": 1.0, "g/L": 1000.0,
                      "μg/L": 0.001, "µg/L": 0.001, "ng/L": 1e-6,
                      "mg/mL": 1e6, "g/mL": 1e9, "%": 1e4},
    "mass": {"mg": 1.0, "g": 1000.0, "μg": 0.001, "µg": 0.001, "kg": 1e6},
    "volume": {"mL": 1.0, "L": 1000.0, "μL": 0.001, "µL": 0.001},
    "dimensionless": {"NTU": 1.0, "pH": 1.0, "": 1.0},
}
RE_NUM = re.compile(r"^[+-]?\d+(\.\d+)?$")
RE_SCI = re.compile(r"^[+-]?\d+(\.\d+)?[eE][+-]?\d+$")
RE_UNIT_SUFFIX = re.compile(r"^([+-]?\d+(?:\.\d+)?)\s*([a-zA-Zμµ%/][a-zA-Zμµ%/0-9.·^-]*)$")
FULLWIDTH = {chr(ord("０") + i): str(i) for i in range(10)}
FULLWIDTH.update({"．": ".", "　": " "})


def find_unit(unit):
    for dim, reg in UNIT_REGISTRY.items():
        if unit in reg:
            return dim, reg[unit]
    return None, None


def norm_key(s):
    t = "".join(FULLWIDTH.get(c, c) for c in s.strip())
    t = re.sub(r"\s+", " ", t)
    return t.casefold()


def fmt_num(x):
    """确定性格式化：尽量短且不丢精度（repr 往返）。"""
    if x == int(x) and abs(x) < 1e15:
        return str(int(x))
    return repr(x)


def fmt_dec(d):
    """Decimal → 最短无噪声十进制文本（去尾零、不丢精度、不用科学计数法）。"""
    if d == d.to_integral_value():
        return str(int(d))
    return format(d.normalize(), "f")


def load_decisions(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print("ERROR: decisions.json 不可读: %s" % e, file=sys.stderr)
        sys.exit(2)


def validate(dec, header):
    errors = []
    fields = dec.get("fields", {})
    for col in header:
        if col not in fields:
            errors.append("字段 %r 缺少裁定（不允许缺省）" % col)
    for name, f in fields.items():
        if name not in header:
            errors.append("裁定了表中不存在的字段 %r" % name)
            continue
        if f.get("role") not in ("measurement", "identifier", "metadata"):
            errors.append("%s: role 非法" % name)
        if f.get("policy") not in POLICIES:
            errors.append("%s: policy 须为 mark|empty|keep" % name)
        for tok, cls in (f.get("missing") or {}).items():
            if cls not in MISSING_CLASSES:
                errors.append("%s: 哨兵 %r 的分类 %r 非法" % (name, tok, cls))
        canon = (f.get("unit") or {}).get("canonical")
        if canon is not None:
            dim, _ = find_unit(canon)
            if dim is None:
                errors.append("%s: 规范单位 %r 不在注册表（带偏移换算一律拒绝）"
                              % (name, canon))
        ucol = (f.get("unit") or {}).get("from_column")
        if ucol is not None and ucol not in header:
            errors.append("%s: unit.from_column %r 不在表头" % (name, ucol))
        bcol = (f.get("bounds_by") or {}).get("column")
        if bcol is not None and bcol not in header:
            errors.append("%s: bounds_by.column %r 不在表头" % (name, bcol))
        if (f.get("policy") in ("empty",)
                or (f.get("unit") or {}).get("canonical") is not None) \
                and not f.get("source"):
            errors.append("%s: 非默认处置必须填写 source 依据定位" % name)
    for kc in dec.get("key_columns", []):
        if kc not in header:
            errors.append("主键列 %r 不在表头" % kc)
    if dec.get("key_columns") and dec.get("dedup", {}).get("keep") not in (
            "most_complete", "first", "last"):
        errors.append("dedup.keep 须为 most_complete|first|last")
    return errors


def run(dec, outdir):
    table = dec["table"]
    with open(table, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    header, data = rows[0], [r for r in rows[1:]]
    idx = {name: j for j, name in enumerate(header)}
    os.makedirs(outdir, exist_ok=True)
    ledger = [["row", "field", "action", "old", "new", "rule", "source"]]
    review = [["row", "field", "value", "reason"]]
    stats = {name: {"missing_classified": 0, "unit_converted": 0,
                    "out_of_bounds": 0, "iqr_outlier": 0}
             for name in header}

    # 1) 逐格：缺失分类 + 单位换算 + 物理界
    cleaned = []
    for rno, row in enumerate(data, 2):  # 行号含表头偏移
        row = list(row) + [""] * (len(header) - len(row))
        for name, fdec in dec["fields"].items():
            j = idx[name]
            v = row[j]
            t = v.strip()
            miss = fdec.get("missing") or {}
            if t in miss or (t == "" and "" in miss) or (t == "" and "<空>" in miss):
                cls = miss.get(t) or miss.get("") or miss.get("<空>")
                stats[name]["missing_classified"] += 1
                pol = fdec.get("policy", "mark")
                if pol == "empty":
                    ledger.append([rno, name, "missing_to_empty", v, "",
                                   "missing:%s" % cls, fdec.get("source", "")])
                    row[j] = ""
                else:  # mark / keep：原值保留，仅台账记录分类
                    ledger.append([rno, name, "missing_marked", v, v,
                                   "missing:%s" % cls, fdec.get("source", "")])
                continue
            # 单位换算（三种形态：独立单位列 from_column、内嵌单位、字段级唯一单位）
            unit_dec = fdec.get("unit") or {}
            canon = unit_dec.get("canonical")
            u_col = unit_dec.get("from_column")
            if canon and (RE_NUM.match(t) or RE_SCI.match(t)
                          or RE_UNIT_SUFFIX.match(t)):
                if u_col:
                    if u_col not in idx:
                        ledger.append([rno, name, "unit_rejected", v, v,
                                       "from_column %r 不存在" % u_col,
                                       fdec.get("source", "")])
                        continue
                    num_s, u_in = t, (row[idx[u_col]].strip() or None)
                else:
                    m = RE_UNIT_SUFFIX.match(t)
                    num_s, u_in = (t, None)
                    if m:
                        num_s, u_in = m.group(1), m.group(2)
                observed = unit_dec.get("observed") or []
                u_eff = u_in or (observed[0] if len(observed) == 1 else None)
                convert_only = unit_dec.get("convert_only")
                skip_convert = bool(convert_only) and u_eff not in convert_only
                if skip_convert:
                    pass  # 非目标量纲行（如 NTU）：声明不换算，不留噪声台账
                elif u_eff is None:
                    ledger.append([rno, name, "unit_unknown", v, v,
                                   "no_source_unit", fdec.get("source", "")])
                    review.append([rno, name, v, "单位不明：保留原值"])
                elif u_eff != canon:
                    d1, f1 = find_unit(u_eff)
                    d2, f2 = find_unit(canon)
                    if d1 is None or d1 != d2:
                        ledger.append([rno, name, "unit_rejected", v, v,
                                       "not_in_registry_or_dim_mismatch",
                                       fdec.get("source", "")])
                        review.append([rno, name, v, "单位 %r 不可换算为 %r：保留原值"
                                       % (u_eff, canon)])
                    else:
                        try:
                            x = decimal.Decimal(num_s)
                            f1d = decimal.Decimal(str(f1))
                            f2d = decimal.Decimal(str(f2))
                            y = x * f1d / f2d
                            if y * f2d / f1d != x:
                                raise ValueError("inverse check failed")
                            new = fmt_dec(y)
                            ledger.append([rno, name, "unit_converted", v, new,
                                           "%s->%s (x%g)" % (u_eff, canon, f1 / f2),
                                           fdec.get("source", "")])
                            row[j] = new
                            if u_col and row[idx[u_col]].strip() != canon:
                                ledger.append([rno, u_col, "unit_label_updated",
                                               row[idx[u_col]], canon,
                                               "follow %s" % name,
                                               fdec.get("source", "")])
                                row[idx[u_col]] = canon
                            stats[name]["unit_converted"] += 1
                        except (ValueError, OverflowError) as e:
                            ledger.append([rno, name, "unit_conversion_failed", v, v,
                                           str(e), fdec.get("source", "")])
                            review.append([rno, name, v, "换算失败回退原值: %s" % e])
            # 物理界标记（只标记，不删除）；支持按分组列的差异化界（长表）
            b = fdec.get("bounds") or {}
            bby = fdec.get("bounds_by") or {}
            if bby.get("column"):
                gv = row[idx[bby["column"]]].strip() if bby["column"] in idx else ""
                b = (bby.get("map") or {}).get(gv) or b
            tv = row[j].strip()
            if (b.get("min") is not None or b.get("max") is not None) \
                    and (RE_NUM.match(tv) or RE_SCI.match(tv)):
                x = float(tv)
                if (b.get("min") is not None and x < b["min"]) or \
                   (b.get("max") is not None and x > b["max"]):
                    stats[name]["out_of_bounds"] += 1
                    ledger.append([rno, name, "out_of_bounds_flag", row[j], row[j],
                                   "bounds:[%s,%s]" % (b.get("min"), b.get("max")),
                                   fdec.get("source", "")])
        cleaned.append(row)

    # 2) 归一化去重
    key_cols = dec.get("key_columns") or []
    dropped = 0
    if key_cols:
        groups = {}
        for i, row in enumerate(cleaned):
            key = "␟".join(norm_key(row[idx[k]]) for k in key_cols)
            groups.setdefault(key, []).append(i)
        keyset = {idx[k] for k in key_cols}
        keep_policy = dec.get("dedup", {}).get("keep", "most_complete")
        keep_idx, conflict = set(), 0
        for key, members in groups.items():
            if len(members) == 1:
                keep_idx.add(members[0])
                continue
            # 冲突判定：比较**非键列**。非键列全同（差异仅在键的写法，
            # 如大小写/空格/全半角）⇒ 近似重复，按策略去重；
            # 非键列不同 ⇒ 键冲突，全部保留并隔离复核。
            nonkey_eq = {tuple(v for j, v in enumerate(cleaned[i]) if j not in keyset)
                         for i in members}
            if len(nonkey_eq) > 1:
                conflict += 1
                for i in members:
                    keep_idx.add(i)
                    review.append([i + 2, "/".join(key_cols),
                                   key, "主键冲突：非键值不一致，全部保留待复核"])
                continue
            if keep_policy == "first":
                winner = members[0]
            elif keep_policy == "last":
                winner = members[-1]
            else:  # most_complete：非空单元格最多；并列取先
                winner = max(members,
                             key=lambda i: (sum(1 for c in cleaned[i] if c.strip()),
                                            -i))
            for i in members:
                if i == winner:
                    keep_idx.add(i)
                else:
                    dropped += 1
                    ledger.append([i + 2, "/".join(key_cols), "dedup_drop",
                                   json.dumps(cleaned[i], ensure_ascii=False), "",
                                   "dedup:%s" % keep_policy, "decisions.json"])
        cleaned = [row for i, row in enumerate(cleaned) if i in keep_idx]
        stats["_dedup"] = {"groups": sum(1 for m in groups.values() if len(m) > 1),
                           "dropped": dropped, "key_conflicts": conflict}

    # 3) IQR 诊断标记（辅助证据，不处置）
    for name, fdec in dec["fields"].items():
        if fdec.get("role") != "measurement":
            continue
        j = idx[name]
        xs = sorted(float(r[j]) for r in cleaned
                    if RE_NUM.match(r[j].strip()) or RE_SCI.match(r[j].strip()))
        if len(xs) < 4:
            continue
        q1 = xs[len(xs) // 4]
        q3 = xs[(3 * len(xs)) // 4]
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        for r in cleaned:
            tv = r[j].strip()
            if (RE_NUM.match(tv) or RE_SCI.match(tv)):
                x = float(tv)
                if x < lo or x > hi:
                    stats[name]["iqr_outlier"] += 1

    # 4) 写产物
    with open(os.path.join(outdir, "cleaned.csv"), "w", encoding="utf-8",
              newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(cleaned)
    with open(os.path.join(outdir, "ledger.csv"), "w", encoding="utf-8",
              newline="") as f:
        csv.writer(f, lineterminator="\n").writerows(ledger)
    with open(os.path.join(outdir, "review_queue.csv"), "w", encoding="utf-8",
              newline="") as f:
        csv.writer(f, lineterminator="\n").writerows(review)
    summary = {"table": table, "rows_in": len(data), "rows_out": len(cleaned),
               "fields": stats}
    with open(os.path.join(outdir, "field_summary.json"), "w",
              encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    md = ["# 裁定执行摘要", "",
          "- 行: %d → %d（去重丢弃 %d，键冲突保留 %d 组）" % (
              len(data), len(cleaned),
              stats.get("_dedup", {}).get("dropped", 0),
              stats.get("_dedup", {}).get("key_conflicts", 0)),
          "- 台账条目: %d | 复核队列: %d" % (len(ledger) - 1, len(review) - 1), ""]
    for name in header:
        s = stats[name]
        md.append("- `%s`: 缺失分类 %d，单位换算 %d，越界 %d，IQR 诊断 %d" % (
            name, s["missing_classified"], s["unit_converted"],
            s["out_of_bounds"], s["iqr_outlier"]))
    with open(os.path.join(outdir, "digest.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--decisions", required=True, help="填写完成的 decisions.json")
    ap.add_argument("--validate", action="store_true", help="只校验不执行")
    ap.add_argument("--run", action="store_true", help="校验并执行")
    ap.add_argument("--out", default=None, help="产物目录（--run 必填）")
    args = ap.parse_args()
    if not args.validate and not args.run:
        print("ERROR: 须指定 --validate 或 --run", file=sys.stderr)
        sys.exit(2)
    dec = load_decisions(args.decisions)
    with open(dec["table"], encoding="utf-8-sig", newline="") as f:
        header = next(csv.reader(f), None)
    if not header:
        print("ERROR: 表为空", file=sys.stderr)
        sys.exit(6)
    errors = validate(dec, header)
    if errors:
        for e in errors:
            print("INVALID: " + e, file=sys.stderr)
        sys.exit(4)
    print(json.dumps({"validation": "pass", "fields": len(dec["fields"])},
                     ensure_ascii=False))
    if args.run:
        if not args.out:
            print("ERROR: --run 需要 --out", file=sys.stderr)
            sys.exit(2)
        summary = run(dec, args.out)
        print(json.dumps({"status": "ok", "rows_in": summary["rows_in"],
                          "rows_out": summary["rows_out"],
                          "out": os.path.abspath(args.out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
