#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""assemble_result.py --case <case.json> --anchors <anchors_verified.json>
   --contradictions <md> --out <result.json> --status <complete|partial|failed>
   --note <str> [--sources <materials.json>]

读取 case.json 中的 output_contract（容忍 list / dict / properties 三种形态），
确保结果包含每个契约字段：可从审查工件映射的填入，否则填 null 并记 uncertainty；
附加 case_id, status, sources, uncertainty, change_record（追加 时间戳+note）。
绝不覆盖已有非空值。仅标准库，无网络。
"""
import argparse
import datetime
import json
import os
import sys


def die(msg):
    sys.stderr.write("错误: %s\n" % msg)
    sys.exit(1)


def parse_contract(case):
    """Return list of contract field names, tolerating list/dict/properties shapes."""
    oc = None
    for k in ("output_contract", "outputContract", "输出契约", "deliverable_contract"):
        if isinstance(case, dict) and k in case:
            oc = case[k]
            break
    if oc is None:
        return []
    fields = []
    if isinstance(oc, list):
        for item in oc:
            if isinstance(item, str):
                fields.append(item)
            elif isinstance(item, dict):
                name = item.get("name") or item.get("field") or item.get("key")
                if name:
                    fields.append(str(name))
                else:
                    fields.extend(str(k) for k in item.keys())
    elif isinstance(oc, dict):
        props = oc.get("properties")
        if isinstance(props, dict):
            fields.extend(str(k) for k in props.keys())
        else:
            fields.extend(str(k) for k in oc.keys())
    return fields


def get_case_id(case):
    if isinstance(case, dict):
        for k in ("case_id", "caseId", "id", "案例编号"):
            if k in case and isinstance(case[k], (str, int)):
                return str(case[k])
    return "unknown"


def map_field(field, anchors, contradictions_text):
    """Try to fill a contract field from review artifacts. Returns (value, note)."""
    f = field.lower()
    entries = anchors.get("entries", [])
    if any(h in f for h in ("evidence", "ledger", "证据", "台账")):
        return entries, "由 anchors_verified.json 全量映射"
    if any(h in f for h in ("verdict", "conclusion", "结论", "可行性")):
        # derive verdict from statuses: any fail -> 不可行; missing/unknown -> 有条件可行
        sts = {e["status"] for e in entries}
        if "fail" in sts:
            return "不可行", "存在 fail 判定（见证据台账），按分级规则判不可行"
        if sts & {"missing", "unknown"}:
            return "有条件可行", "存在 missing/unknown 判定，按分级规则判有条件可行"
        if sts and sts <= {"pass", "not_applicable"}:
            return "可行", "全部判定为 pass/not_applicable"
        return None, None
    if any(h in f for h in ("contradiction", "矛盾", "冲突")):
        return contradictions_text, "由 scan_contradictions.py 报告全文映射"
    if any(h in f for h in ("risk", "风险")):
        return [e for e in entries if e.get("category") == "风险与异常"], None
    if any(h in f for h in ("summary", "摘要", "概述")):
        n = len(entries)
        st = {}
        for e in entries:
            st[e["status"]] = st.get(e["status"], 0) + 1
        return "共 %d 条证据判定，状态分布: %s" % (n, st), "自动统计摘要"
    return None, None


def main():
    ap = argparse.ArgumentParser(
        description="按 case.json 的 output_contract 装配 result.json")
    ap.add_argument("--case", required=True)
    ap.add_argument("--anchors", required=True)
    ap.add_argument("--contradictions", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--status", required=True,
                    choices=["complete", "partial", "failed"])
    ap.add_argument("--note", default="")
    ap.add_argument("--sources", default=None, help="materials.json（可选，用于 sources）")
    a = ap.parse_args()

    for p in (a.case, a.anchors, a.contradictions):
        if not os.path.isfile(p):
            die("找不到文件: %s" % p)
    with open(a.case, "r", encoding="utf-8") as f:
        case = json.load(f)
    with open(a.anchors, "r", encoding="utf-8") as f:
        anchors = json.load(f)
    with open(a.contradictions, "r", encoding="utf-8") as f:
        contradictions_text = f.read()

    if os.path.isfile(a.out):
        with open(a.out, "r", encoding="utf-8") as f:
            try:
                result = json.load(f)
            except json.JSONDecodeError:
                die("已有 %s 不是合法 JSON；拒绝覆盖，请先人工检查" % a.out)
    else:
        result = {}

    uncertainty = result.get("uncertainty")
    if not isinstance(uncertainty, list):
        uncertainty = []

    fields = parse_contract(case)
    for field in fields:
        existing = result.get(field)
        if existing not in (None, "", [], {}):
            continue  # 绝不覆盖已有非空值
        value, note = map_field(field, anchors, contradictions_text)
        if value is None:
            result[field] = None
            uncertainty.append("契约字段 %r 无法从审查工件自动映射，置 null，"
                               "需人工补写" % field)
        else:
            result[field] = value
            if note:
                uncertainty.append("契约字段 %r: %s" % (field, note))

    result.setdefault("case_id", get_case_id(case))
    result["status"] = a.status

    sources = result.get("sources")
    if not isinstance(sources, list):
        sources = []
    if a.sources and os.path.isfile(a.sources):
        with open(a.sources, "r", encoding="utf-8") as f:
            mats = json.load(f).get("materials", [])
        for m in mats:
            sp = m.get("source_path")
            if sp and sp not in sources:
                sources.append(sp)
    result["sources"] = sources
    result["uncertainty"] = uncertainty

    cr = result.get("change_record")
    if not isinstance(cr, list):
        cr = []
    cr.append({"timestamp": datetime.datetime.now().astimezone().isoformat(),
               "status": a.status, "note": a.note or "(无备注)"})
    result["change_record"] = cr

    out_dir = os.path.dirname(os.path.abspath(a.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    missing = [fld for fld in fields if result.get(fld) is None]
    sys.stdout.write("OK: %s -> %s (status=%s, 契约字段 %d 个, 其中 %d 个为 null: %s)\n"
                     % (a.case, a.out, a.status, len(fields), len(missing), missing))
    sys.exit(0)


if __name__ == "__main__":
    main()
