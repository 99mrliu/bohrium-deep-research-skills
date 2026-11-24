#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""matrix_check.py — 研究证据矩阵（study matrix, JSONL）结构门控校验。

每行一个研究记录（JSON 对象），字段约定：
  study_id, design, n, population, intervention, outcome_domain,
  direction, magnitude, limits, source{ref_id, locator}

门控规则：
  S1 必填键齐备（study_id 为非空字符串且不重复）
  S2 design / direction 取值在受控词表内
  S3 n 为正整数或 null
  S4 source.ref_id 与 source.locator 非空（locator 为文献内定位，如 "p.3 表2"）

退出码：0 通过；1 门控违例（stdout 逐项失败清单，含 S 编号）；2 用法/IO 错误。
仅使用 Python 标准库。
"""
import argparse
import json
import sys

DESIGNS = {"rct", "cohort", "case_control", "cross_sectional",
           "in_vitro", "in_silico", "review", "meta_analysis", "other"}
DIRECTIONS = {"positive", "negative", "null", "mixed"}
REQUIRED_KEYS = ["study_id", "design", "n", "population", "intervention",
                 "outcome_domain", "direction", "magnitude", "limits", "source"]


def main():
    ap = argparse.ArgumentParser(
        description="校验 study_matrix.jsonl 的结构完整性（门控 S1-S4）")
    ap.add_argument("--matrix", required=True, help="study_matrix.jsonl 路径")
    args = ap.parse_args()

    try:
        with open(args.matrix, "r", encoding="utf-8") as fh:
            raw_lines = fh.read().splitlines()
    except OSError as exc:
        print(f"IO 错误: 无法读取矩阵文件 {args.matrix}: {exc}", file=sys.stderr)
        return 2

    violations = []
    seen_ids = {}
    n_records = 0

    for lineno, raw in enumerate(raw_lines, start=1):
        line = raw.strip()
        if not line:
            continue
        n_records += 1
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            violations.append(f"S1 行{lineno}: 非合法 JSON 行 ({exc.msg})")
            continue
        if not isinstance(rec, dict):
            violations.append(f"S1 行{lineno}: 记录不是 JSON 对象")
            continue

        # S1 必填键齐备
        missing = [k for k in REQUIRED_KEYS if k not in rec]
        if missing:
            violations.append(f"S1 行{lineno}: 缺少必填键 {missing}")
        sid = rec.get("study_id")
        if "study_id" in rec and (not isinstance(sid, str) or not sid.strip()):
            violations.append(f"S1 行{lineno}: study_id 必须为非空字符串")
        elif isinstance(sid, str):
            if sid in seen_ids:
                violations.append(
                    f"S1 行{lineno}: study_id {sid!r} 与行{seen_ids[sid]} 重复")
            else:
                seen_ids[sid] = lineno

        # S2 design / direction 受控词表
        if "design" in rec and rec["design"] not in DESIGNS:
            violations.append(
                f"S2 行{lineno}: design={rec['design']!r} 不在受控词表 {sorted(DESIGNS)}")
        if "direction" in rec and rec["direction"] not in DIRECTIONS:
            violations.append(
                f"S2 行{lineno}: direction={rec['direction']!r} 不在受控词表 {sorted(DIRECTIONS)}")

        # S3 n 类型（注意 bool 是 int 的子类，须先排除）
        if "n" in rec:
            n = rec["n"]
            if n is not None and (isinstance(n, bool) or not isinstance(n, int) or n <= 0):
                violations.append(f"S3 行{lineno}: n={n!r} 必须为正整数或 null")

        # S4 source{ref_id, locator}
        if "source" in rec:
            src = rec["source"]
            if not isinstance(src, dict):
                violations.append(f"S4 行{lineno}: source 必须为对象 {{ref_id, locator}}")
            else:
                for key in ("ref_id", "locator"):
                    v = src.get(key)
                    if not isinstance(v, str) or not v.strip():
                        violations.append(
                            f"S4 行{lineno}: source.{key} 缺失或为空"
                            f"（locator 应为文献内定位，如 \"p.3 表2\"）")

    if n_records == 0:
        violations.append("S1 文件不含任何研究记录")

    if violations:
        print(f"matrix_check 未通过: {len(violations)} 项违例")
        for v in violations:
            print("  " + v)
        return 1
    print(f"matrix_check 通过: {n_records} 条研究记录, S1-S4 全部满足")
    return 0


if __name__ == "__main__":
    sys.exit(main())
