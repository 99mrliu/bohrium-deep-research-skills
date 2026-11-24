#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_validate.py — result.json 契约校验器（result-contract-replay-compiler）

校验规则：
  V1  case_id 与 case.json 一致；
  V2  output_contract 每个字段都出现在顶层（缺失 → fail；为 null 者必须列入 uncertainty）；
  V3  status ∈ {ok, partial, failed} 且自洽：ok 禁止任何契约字段为 null；
      partial 要求 uncertainty ≥1 条且点名限制；
  V4  sources 每条记录须含 name 与 query_date（或 access_date）；
  V5  编造标记检查（候选条目 evidence 为空 → warning；出现 TODO/PLACEHOLDER 等 → warning）；
  V6  change_records 非空。

退出码：0 全部通过；1 存在 fail 规则；2 用法/输入错误。
报告 JSON 逐条列出每条规则的 pass/fail/warn 与消息。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

STATUSES = ("ok", "partial", "failed")
CASE_ID_KEYS = ("case_id", "caseId", "id", "case_no", "case_number")
CONTRACT_KEYS = ("output_contract", "outputContract", "output-contract",
                 "deliverable_contract")
FABRICATED_MARKERS = ("TODO", "PLACEHOLDER", "FIXME", "XXX-待补", "dummy-value")
EVIDENCE_KEYS = ("evidence", "evidence_records", "evidence_locators", "locators")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_json(path, what):
    if not os.path.isfile(path):
        print(f"[错误] {what} 文件不存在: {path}", file=sys.stderr)
        sys.exit(2)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"[错误] {what} JSON 解析失败: {path}: {e}", file=sys.stderr)
        sys.exit(2)


def find_case_id(case):
    if isinstance(case, dict):
        for k in CASE_ID_KEYS:
            v = case.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        for holder in ("case", "meta", "header", "task"):
            sub = case.get(holder)
            if isinstance(sub, dict):
                for k in CASE_ID_KEYS:
                    v = sub.get(k)
                    if isinstance(v, str) and v.strip():
                        return v.strip()
    return None


def find_contract_fields(case):
    def extract(c):
        if isinstance(c, dict):
            return [str(k) for k in c.keys()]
        if isinstance(c, list):
            out = []
            for item in c:
                if isinstance(item, str):
                    out.append(item)
                elif isinstance(item, dict) and isinstance(item.get("name"), str):
                    out.append(item["name"])
            return out
        return []

    if isinstance(case, dict):
        for k in CONTRACT_KEYS:
            if k in case:
                return extract(case[k])
        for holder in ("task", "spec", "requirements", "case"):
            sub = case.get(holder)
            if isinstance(sub, dict):
                for k in CONTRACT_KEYS:
                    if k in sub:
                        return extract(sub[k])
    return []


def named_in_uncertainty(field, uncertainty):
    if not isinstance(uncertainty, list):
        return False
    return any(str(e).startswith(field + ":") or str(e).startswith(field + "：")
               or str(e) == field or field in str(e) for e in uncertainty)


def main():
    ap = argparse.ArgumentParser(description="校验 result.json 是否满足案例 output_contract")
    ap.add_argument("--case", required=True, help="case.json 路径")
    ap.add_argument("--result", required=True, help="result.json 路径")
    ap.add_argument("--out", required=True, help="校验报告 JSON 输出路径")
    args = ap.parse_args()

    case = load_json(args.case, "case.json")
    result = load_json(args.result, "result.json")
    if not isinstance(result, dict):
        print("[错误] result.json 顶层必须是对象", file=sys.stderr)
        sys.exit(2)

    case_id = find_case_id(case)
    fields = find_contract_fields(case)
    rules = []

    def add(rid, name, status, messages):
        rules.append({"id": rid, "name": name, "status": status, "messages": messages})
        tag = {"pass": "通过", "fail": "失败", "warn": "警告"}[status]
        print(f"[{rid} {tag}] {name}")
        for m in messages:
            print(f"    - {m}")

    # V1
    if case_id is None:
        add("V1", "case_id 一致性", "fail", ["case.json 中未能定位 case_id，无法比对"])
    elif result.get("case_id") == case_id:
        add("V1", "case_id 一致性", "pass", [f"case_id = {case_id}"])
    else:
        add("V1", "case_id 一致性", "fail",
            [f"result.case_id={result.get('case_id')!r} 与 case.json 的 {case_id!r} 不一致"])

    # V2
    missing, null_unlisted = [], []
    for fld in fields:
        if fld not in result:
            missing.append(fld)
        elif result[fld] is None and not named_in_uncertainty(fld, result.get("uncertainty")):
            null_unlisted.append(fld)
    if not fields:
        add("V2", "契约字段齐备", "warn",
            ["case.json 中未找到 output_contract，无法进行字段齐备校验"])
    elif missing or null_unlisted:
        msgs = []
        if missing:
            msgs.append("缺失契约字段: " + ", ".join(missing))
        if null_unlisted:
            msgs.append("字段为 null 但未列入 uncertainty: " + ", ".join(null_unlisted))
        add("V2", "契约字段齐备", "fail", msgs)
    else:
        add("V2", "契约字段齐备", "pass", [f"{len(fields)} 个契约字段均在顶层且标注一致"])

    # V3
    status = result.get("status")
    null_fields = [f for f in fields if result.get(f) is None]
    unc = result.get("uncertainty")
    if status not in STATUSES:
        add("V3", "status 合法且自洽", "fail",
            [f"status={status!r} 不在 {{ok, partial, failed}} 内"])
    elif status == "ok" and null_fields:
        add("V3", "status 合法且自洽", "fail",
            ["status=ok 但以下契约字段仍为 null（过度声明）: " + ", ".join(null_fields)])
    elif status == "partial" and (not isinstance(unc, list) or len(unc) == 0):
        add("V3", "status 合法且自洽", "fail",
            ["status=partial 但 uncertainty 为空，未点名限制"])
    else:
        add("V3", "status 合法且自洽", "pass", [f"status={status} 与字段填充情况一致"])

    # V4
    sources = result.get("sources")
    if not isinstance(sources, list):
        add("V4", "来源记录完整", "fail", ["sources 不是数组"])
    elif not sources:
        add("V4", "来源记录完整", "warn", ["sources 为空（partial 交付可接受，交付前应尽量补齐）"])
    else:
        bad = []
        for i, s in enumerate(sources):
            if not isinstance(s, dict) or not s.get("name"):
                bad.append(f"sources[{i}] 缺少 name")
            elif not (s.get("query_date") or s.get("access_date")):
                bad.append(f"sources[{i}] 缺少 query_date/access_date")
        if bad:
            add("V4", "来源记录完整", "fail", bad)
        else:
            add("V4", "来源记录完整", "pass", [f"{len(sources)} 条来源记录均含 name 与日期"])

    # V5
    warns = []
    candidates = result.get("candidates")
    if isinstance(candidates, list):
        for i, c in enumerate(candidates):
            if isinstance(c, dict):
                for ek in EVIDENCE_KEYS:
                    if ek in c:
                        if not c[ek]:
                            warns.append(f"candidates[{i}] 的 {ek} 为空（疑似无证据占位）")
                        break
                else:
                    warns.append(f"candidates[{i}] 不含任何证据定位字段（{ '/'.join(EVIDENCE_KEYS) }）")
    blob = json.dumps(result, ensure_ascii=False)
    for mk in FABRICATED_MARKERS:
        if mk in blob:
            warns.append(f"结果文本中出现编造标记 {mk!r}")
    add("V5", "编造标记检查", "warn" if warns else "pass",
        warns or ["未发现空证据候选或编造标记"])

    # V6
    cr = result.get("change_records")
    if isinstance(cr, list) and cr:
        add("V6", "变更记录非空", "pass", [f"change_records 共 {len(cr)} 条"])
    else:
        add("V6", "变更记录非空", "fail", ["change_records 为空或缺失"])

    overall = "fail" if any(r["status"] == "fail" for r in rules) else "pass"
    report = {
        "report": "contract_validate",
        "generated_at": utc_now(),
        "case_id": result.get("case_id"),
        "overall": overall,
        "rules": rules,
    }
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[总体] {'通过' if overall == 'pass' else '存在失败规则'}，报告: {args.out}")
    return 1 if overall == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
