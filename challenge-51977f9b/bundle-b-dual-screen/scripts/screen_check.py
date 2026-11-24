#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""screen_check.py — 双人独立筛选决策记录的规则校验。

决策行（JSONL，每行一条）schema：
  {"record_id": "R01", "round": 1, "screener": "A"|"B",
   "decision": "include"|"exclude"|"uncertain",
   "reason_code": "EX-POP"|null, "reason_text": "..."}

规则：
  S1 字段齐全、取值合法（record_id 须存在于 records，round 须等于 --round）；
  S2 完整性：该轮每条待筛记录必须有 A、B 各恰好一条判定（列出缺失/重复组合）；
  S3 decision=exclude 必须有 reason_code（属于 --criteria 的排除条款代码表）
     且 reason_text 不少于 8 个字符；
  S4 uncertain 不得直接计入纳入（只许经仲裁转判）；本脚本统计并提示；
  S5 若 --freeze-file 指向的冻结文件已存在，任何新决策一律拒绝。

退出码：0=通过；2=输入/材料不足（records 或 decisions 缺失不可读）；
3=校验失败（逐条列出违规）。
"""
import argparse
import json
import os
import sys

VALID_SCREENERS = {"A", "B"}
VALID_DECISIONS = {"include", "exclude", "uncertain"}
REQUIRED_FIELDS = ["record_id", "round", "screener", "decision",
                   "reason_code", "reason_text"]
MIN_REASON_LEN = 8


def eprint(msg):
    print(msg, file=sys.stderr)


def load_records(path):
    """兼容 {"records": [...]} 与顶层列表两种形态；返回 (ids, error)。"""
    if not os.path.isfile(path):
        return None, f"records 文件不存在：{path}"
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, f"records 文件无法解析（{exc}）"
    items = data.get("records") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        return None, "records 文件中没有记录列表（records 为空或形态错误）"
    ids = []
    for i, it in enumerate(items):
        rid = it.get("record_id") or it.get("id") if isinstance(it, dict) else None
        if not rid:
            return None, f"records 第 {i + 1} 条缺少 record_id"
        ids.append(str(rid))
    return ids, None


def load_criteria_codes(path):
    """读取排除条款代码表；文件缺失返回 None（S3 退化为只查非空并警告）。"""
    if not path:
        return None
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    codes = data.get("exclusion_codes") if isinstance(data, dict) else data
    out = set()
    if isinstance(codes, list):
        for c in codes:
            if isinstance(c, dict) and c.get("code"):
                out.add(str(c["code"]))
            elif isinstance(c, str):
                out.add(c)
    return out or None


def main():
    ap = argparse.ArgumentParser(
        description="校验某一轮双人独立筛选的决策记录（规则 S1–S5）。",
        epilog="退出码：0=通过；2=records/decisions 缺失或不可读；3=存在违规（逐条列出）。",
    )
    ap.add_argument("--records", required=True, help="本轮待筛记录清单 JSON")
    ap.add_argument("--decisions", required=True, help="决策 JSONL（含 A、B 两名筛选者）")
    ap.add_argument("--round", type=int, required=True, choices=[1, 2],
                    help="轮次：1=题录级，2=全文级")
    ap.add_argument("--criteria", default=None,
                    help="排除条款代码表 JSON（S3 校验 reason_code 合法性）")
    ap.add_argument("--freeze-file", default=None,
                    help="冻结文件路径；若已存在则拒绝一切新决策（S5）")
    args = ap.parse_args()

    # S5：冻结语义优先——纳入集一旦冻结，任何新决策都是违规
    if args.freeze_file and os.path.isfile(args.freeze_file):
        eprint(f"[S5] 违规：纳入集已冻结（{args.freeze_file} 存在），"
               f"禁止追加或修改任何筛选决策。如需修改请走解冻流程并写 change_records。")
        return 3

    record_ids, err = load_records(args.records)
    if err:
        eprint(f"[E-INPUT] {err}")
        return 2
    if not os.path.isfile(args.decisions):
        eprint(f"[E-INPUT] decisions 文件不存在：{args.decisions}")
        return 2

    criteria_codes = load_criteria_codes(args.criteria)
    if args.criteria and criteria_codes is None:
        print(f"  [警告] criteria 文件不可用（{args.criteria}），"
              f"S3 仅检查 reason_code 非空，不核对代码表")

    decisions = []
    read_err = None
    with open(args.decisions, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                decisions.append((ln, json.loads(line)))
            except json.JSONDecodeError as exc:
                read_err = f"decisions 第 {ln} 行不是合法 JSON（{exc}）"
                break
    if read_err:
        eprint(f"[E-INPUT] {read_err}")
        return 2
    if not decisions:
        eprint("[E-INPUT] decisions 文件为空，无任何决策行")
        return 2

    violations = []
    id_set = set(record_ids)
    pair_count = {}   # (record_id, screener) -> 次数
    uncertain = 0

    for ln, d in decisions:
        # ---- S1：字段齐全、取值合法 ----
        if not isinstance(d, dict):
            violations.append(f"[S1] 第 {ln} 行：决策行必须是 JSON 对象")
            continue
        missing = [k for k in REQUIRED_FIELDS if k not in d]
        if missing:
            violations.append(f"[S1] 第 {ln} 行：缺字段 {missing}")
            continue
        rid, sc, dec = str(d["record_id"]), d["screener"], d["decision"]
        if rid not in id_set:
            violations.append(f"[S1] 第 {ln} 行：record_id={rid} 不在本轮待筛记录中")
        if sc not in VALID_SCREENERS:
            violations.append(f"[S1] 第 {ln} 行：screener={sc!r} 非法（须为 A 或 B）")
        if dec not in VALID_DECISIONS:
            violations.append(f"[S1] 第 {ln} 行：decision={dec!r} 非法"
                              f"（须为 include/exclude/uncertain）")
        if d["round"] != args.round:
            violations.append(f"[S1] 第 {ln} 行：round={d['round']} 与 --round {args.round} 不符")
        if dec == "exclude":
            # ---- S3：排除理由强制 ----
            rc = d.get("reason_code")
            rt = d.get("reason_text")
            if not rc:
                violations.append(f"[S3] 第 {ln} 行：{rid}/{sc} 判定 exclude 但缺 reason_code")
            elif criteria_codes is not None and rc not in criteria_codes:
                violations.append(f"[S3] 第 {ln} 行：{rid}/{sc} 的 reason_code={rc!r} "
                                  f"不在排除条款代码表中")
            if not isinstance(rt, str) or len(rt.strip()) < MIN_REASON_LEN:
                violations.append(f"[S3] 第 {ln} 行：{rid}/{sc} 判定 exclude 但 "
                                  f"reason_text 少于 {MIN_REASON_LEN} 个字符")
        if dec == "uncertain":
            uncertain += 1
        key = (rid, sc)
        pair_count[key] = pair_count.get(key, 0) + 1

    # ---- S2：完整性（缺失与重复）----
    for rid in record_ids:
        for sc in ("A", "B"):
            n = pair_count.get((rid, sc), 0)
            if n == 0:
                violations.append(f"[S2] 缺失组合：{rid} 缺筛选者 {sc} 的判定")
            elif n > 1:
                violations.append(f"[S2] 重复判定：{rid}/{sc} 出现 {n} 次（应恰好 1 次）")

    if violations:
        print(f"[FAIL] 第 {args.round} 轮筛选决策校验未通过，共 {len(violations)} 处违规：")
        for v in violations:
            print(f"  {v}")
        return 3

    n_records = len(record_ids)
    print(f"[OK] 第 {args.round} 轮筛选决策校验通过：{n_records} 条记录 × A/B 双人，"
          f"共 {len(decisions)} 条决策。")
    if uncertain:
        print(f"  [S4 提示] 含 {uncertain} 条 uncertain：不得直接计入纳入，"
              f"须经 adjudicate.py 仲裁转判后方可定论。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
