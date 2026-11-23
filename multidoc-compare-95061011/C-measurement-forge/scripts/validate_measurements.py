#!/usr/bin/env python3
"""validate_measurements.py — 机检 agent 确认后的 measurements.jsonl。

每条记录(测量记录)字段:
  measurement_id      必填, 唯一
  document_id         必填, 源文档 id
  paragraph_id        必填, 段落 id (须能在 --paras 索引中找到)
  quote               必填, 逐字原文句(必须逐字出现在该段落文本中)
  value_raw           必填, 原文数值串(必须出现在 quote 中)
  value               必填, 数值(float, 与 value_raw 一致)
  unit                必填, 原单位原文(可解析; 无法解析须置 "unregistered_unit_accepted": true)
  quantity_kind       必填, 须在 quantity-kinds 登记表中
  metric_definition   status="reported" 时必填非空(口径随值走: 公式或仪器口径)
  condition_context   建议填: 同句/同段条件窗(材料/污染物/投加量/光源/温度/pH 等)
  status              "reported"(原文直报) | "derived"(换算/计算派生) | "excluded"(弃用)
  note                可选

机检项(违反 -> error, 退出码非零):
  V1 必填字段齐全; measurement_id 唯一
  V2 quote 逐字落地: 逐字出现在 (document_id, paragraph_id) 的段落文本中
  V3 value_raw 出现在 quote 中, 且 float(value_raw) == value
  V4 unit 可被 units.parse_unit 解析(或显式标记 unregistered 并接受不换算)
  V5 quantity_kind 在登记表 (references/quantity-kinds.json) 中
  V6 status == "reported" 的记录 metric_definition 非空
告警项(不致命, 打印 WARNING):
  W1 禁止跨论文誊抄: value_raw 数值串出现在其他文档的段落文本中 -> 告警
  W2 condition_context 为空

用法:
  python3 validate_measurements.py MEAS.jsonl --paras PARAS.jsonl [--kinds KINDS.json] [--strict]
  --strict 时告警也算失败。
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from units import parse_unit  # noqa: E402

DEFAULT_KINDS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "references", "quantity-kinds.json")
REQUIRED = ["measurement_id", "document_id", "paragraph_id", "quote",
            "value_raw", "value", "unit", "quantity_kind", "status"]
VALID_STATUS = {"reported", "derived", "excluded"}


def load_paras(path):
    idx = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            doc = rec.get("document_id") or rec.get("source_document_id") or "UNKNOWN"
            pid = rec.get("paragraph_id")
            idx.setdefault(doc, {})[pid] = rec.get("text", "")
    return idx


def main(argv=None):
    ap = argparse.ArgumentParser(description="机检测量记录")
    ap.add_argument("measurements", help="measurements.jsonl")
    ap.add_argument("--paras", required=True, help="段落索引 jsonl (quote 逐字核验依据)")
    ap.add_argument("--kinds", default=DEFAULT_KINDS, help="quantity-kinds 登记表 json")
    ap.add_argument("--strict", action="store_true", help="告警也判失败")
    args = ap.parse_args(argv)

    with open(args.kinds, "r", encoding="utf-8") as f:
        kinds = set(json.load(f)["quantity_kinds"].keys())
    paras = load_paras(args.paras)

    errors, warnings = [], []
    seen_ids = set()
    records = []
    with open(args.measurements, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"line {ln}: JSON 解析失败: {e}")
                continue
            records.append((ln, rec))

    for ln, rec in records:
        mid = rec.get("measurement_id", f"line{ln}")
        # V1
        for fld in REQUIRED:
            if fld not in rec or rec[fld] is None or (isinstance(rec[fld], str) and not rec[fld].strip()):
                errors.append(f"{mid}: 缺少必填字段 {fld}")
        if rec.get("measurement_id") in seen_ids:
            errors.append(f"{mid}: measurement_id 重复")
        seen_ids.add(rec.get("measurement_id"))
        st = rec.get("status")
        if st not in VALID_STATUS:
            errors.append(f"{mid}: status 非法: {st!r} (须为 {sorted(VALID_STATUS)})")
        doc, pid = rec.get("document_id"), rec.get("paragraph_id")
        quote, vraw = rec.get("quote", ""), rec.get("value_raw", "")
        ptext = paras.get(doc, {}).get(pid)
        # V2
        if ptext is None:
            errors.append(f"{mid}: 段落索引中找不到 {doc}/{pid}")
        elif quote and quote not in ptext:
            errors.append(f"{mid}: quote 未逐字出现在 {doc}/{pid} 段落文本中")
        # V3
        if quote and vraw and vraw not in quote:
            errors.append(f"{mid}: value_raw {vraw!r} 不在 quote 中")
        try:
            fv = float(vraw)
            if abs(float(rec.get("value")) - fv) > max(1e-12, abs(fv) * 1e-9):
                errors.append(f"{mid}: value {rec.get('value')} 与 value_raw {vraw} 不一致")
        except (TypeError, ValueError):
            errors.append(f"{mid}: value_raw/value 无法解析为数值")
        # V4
        unit = rec.get("unit")
        if unit:
            if parse_unit(unit) is None and not rec.get("unregistered_unit_accepted"):
                errors.append(f"{mid}: 单位 {unit!r} 无法解析; "
                              f"若为未登记单位请置 unregistered_unit_accepted=true(保留原单位不换算)")
        # V5
        if rec.get("quantity_kind") and rec["quantity_kind"] not in kinds:
            errors.append(f"{mid}: quantity_kind {rec['quantity_kind']!r} 不在登记表")
        # V6
        if st == "reported" and not str(rec.get("metric_definition", "")).strip():
            errors.append(f"{mid}: status=reported 但 metric_definition 为空(口径随值走, 必填)")
        # W1 跨论文誊抄: 数值串(整词边界)出现在他篇段落
        if vraw:
            pat = re.compile(r"(?<![\w.])" + re.escape(vraw) + r"(?![\w])")
            for odoc, pmap in paras.items():
                if odoc == doc:
                    continue
                for opid, otext in pmap.items():
                    if pat.search(otext):
                        warnings.append(f"{mid}: value_raw {vraw!r} 也出现在他篇 {odoc}/{opid}, 疑似跨论文誊抄")
                        break
        # W2
        if not str(rec.get("condition_context", "")).strip():
            warnings.append(f"{mid}: condition_context 为空(建议记录同句/同段条件窗)")

    for w in warnings:
        print("WARNING:", w)
    if errors:
        print(f"\nVALIDATION FAILED: {len(errors)} error(s), {len(warnings)} warning(s)")
        for e in errors:
            print("ERROR:", e)
        return 1
    if warnings and args.strict:
        print(f"\nVALIDATION FAILED (strict): {len(warnings)} warning(s)")
        return 1
    print(f"VALIDATION OK: {len(records)} record(s), {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
