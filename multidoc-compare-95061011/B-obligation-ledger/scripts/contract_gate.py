#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_gate.py — 交付门禁：检查 /app/output/result.json 是否满足平台契约。

检查项：
  1. result.json 是合法 JSON 对象；
  2. case_id 存在且与 case.json 的 case_id 一致（原样复制，不得改写）；
  3. case.json 的 output_contract 列出的全部字段都作为顶层键出现
     （output_contract 支持 list[str] / list[dict(name|field|key)] / dict 三种形态）；
     若 case.json 无 output_contract，退化为只查 {case_id, status, sources, uncertainty}；
  4. status ∈ {success, partial, failed}；
  5. sources、uncertainty 键必须存在；
  6. status=partial 时 uncertainty 必须非空；
  7. 若提供 --obligations：每个仍 open 的 obligation_id 必须逐字出现在
     uncertainty 的文本中（显式豁免或如实交代），否则失败。

全部通过打印 GATE PASS 并退出 0；任一失败打印 GATE FAIL 并退出 1。
"""
import argparse
import json
import os
import sys

REQUIRED_BASE = ("case_id", "status", "sources", "uncertainty")
VALID_STATUS = ("success", "partial", "failed")


def load_json(path, label):
    if not os.path.isfile(path):
        print("[gate] 错误：%s 不存在：%s" % (label, path), file=sys.stderr)
        sys.exit(2)
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            print("[gate] 错误：%s 不是合法 JSON：%s" % (path, e), file=sys.stderr)
            sys.exit(2)


def contract_fields(case):
    oc = case.get("output_contract")
    if oc is None:
        return None
    fields = []
    if isinstance(oc, dict):
        fields = list(oc.keys())
    elif isinstance(oc, list):
        for item in oc:
            if isinstance(item, str):
                fields.append(item)
            elif isinstance(item, dict):
                for k in ("name", "field", "key", "id"):
                    if item.get(k):
                        fields.append(str(item[k]))
                        break
    return fields


def main():
    ap = argparse.ArgumentParser(description="result.json 交付门禁")
    ap.add_argument("--result", required=True, help="/app/output/result.json")
    ap.add_argument("--case", required=True, help="/input/case.json")
    ap.add_argument("--obligations", default=None, help="最终 obligations.jsonl（检查 open 义务是否已交代）")
    args = ap.parse_args()

    failures = []
    result = load_json(args.result, "result.json")
    case = load_json(args.case, "case.json")

    if not isinstance(result, dict):
        failures.append("result.json 顶层必须是 JSON 对象")
        result = {}

    # 2. case_id
    rid = result.get("case_id")
    cid = case.get("case_id")
    if not rid:
        failures.append("result.json 缺少 case_id")
    elif cid and rid != cid:
        failures.append("case_id 不一致：result=%r 但 case.json=%r（必须原样复制）" % (rid, cid))

    # 3. output_contract
    fields = contract_fields(case)
    if fields is None:
        print("[gate] case.json 无 output_contract，退化为基础契约 %s" % (list(REQUIRED_BASE),))
        fields = []
    for fld in fields:
        if fld not in result:
            failures.append("output_contract 字段 %r 未出现在 result.json 顶层" % fld)

    # 4. status
    st = result.get("status")
    if st not in VALID_STATUS:
        failures.append("status=%r 非法，须为 %s" % (st, VALID_STATUS))

    # 5. sources / uncertainty
    for k in ("sources", "uncertainty"):
        if k not in result:
            failures.append("result.json 缺少键 %r" % k)

    # 6. partial 时 uncertainty 非空
    unc = result.get("uncertainty")
    unc_text = json.dumps(unc, ensure_ascii=False) if unc is not None else ""
    unc_empty = unc is None or unc == "" or unc == [] or unc == {}
    if st == "partial" and unc_empty:
        failures.append("status=partial 但 uncertainty 为空（必须写明缺失边界）")

    # 7. open 义务交代
    if args.obligations:
        open_ids = []
        with open(args.obligations, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                o = json.loads(line)
                if o.get("status") == "open":
                    open_ids.append(o["obligation_id"])
        for oid in open_ids:
            if oid not in unc_text:
                failures.append("open 义务 %s 未在 uncertainty 中交代（须显式豁免或如实列出）" % oid)
        if open_ids:
            print("[gate] 台账仍有 %d 条 open 义务，已核对 uncertainty 覆盖" % len(open_ids))

    if failures:
        print("GATE FAIL（%d 项）：" % len(failures))
        for x in failures:
            print("  - " + x)
        sys.exit(1)
    print("GATE PASS：case_id=%s status=%s contract 字段 %d 个全部在位" % (rid, st, len(fields)))
    sys.exit(0)


if __name__ == "__main__":
    main()
