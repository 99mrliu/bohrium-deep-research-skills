#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck.py — 终检（工作流最后一步）。

校验项（边界说明：不做计数闭合审计，那是另一方向的职责）：
  1. 合同完整性：result.json 是否含 output_contract.required_fields 全部字段；
     仍为 null 的字段必须在 uncertainty 中有对应说明，否则判校验失败。
  2. 证据锚定真实性：judgments 中 not_met / uncertain 判据的 evidence.quote
     必须是所引用记录标题或摘要的真实子串（大小写不敏感），防止“编造证据”。
  3. status 终置：全部通过 → completed；有降级或失败 → 保持 partial 并写明原因。

产物：work/selfcheck.json；增量更新 result.json 的 status / uncertainty / change_records。
退出码：0=全部校验通过；2=输入不足导致部分校验被跳过（诚实降级）；3=校验失败。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

EXIT_OK, EXIT_INSUFFICIENT, EXIT_INVALID = 0, 2, 3

DEFAULT_FIELDS = [
    "case_id", "status", "near_misses", "fragility_report", "facet_coverage",
    "omission_statement", "recheck_worklist", "sources", "uncertainty",
    "change_records",
]


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def find_material(input_dir, case, key, fallbacks):
    cands = []
    mats = (case or {}).get("materials") or {}
    if mats.get(key):
        cands.append(os.path.join(input_dir, mats[key]))
    cands.extend(os.path.join(input_dir, name) for name in fallbacks)
    for path in cands:
        if os.path.exists(path):
            return path
    return None


def load_items(path, container_key):
    data = load_json(path)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get(container_key), list):
        return data[container_key]
    raise ValueError("%s 结构不识别" % os.path.basename(path))


def main():
    ap = argparse.ArgumentParser(description="result.json 终检")
    ap.add_argument("--input-dir", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    args = ap.parse_args()

    checks = []  # 每项 {"name", "status": pass|fail|skipped, "detail"}
    overall_exit = EXIT_OK
    try:
        os.makedirs(args.work, exist_ok=True)
        result_path = os.path.join(args.output_dir, "result.json")
        if not os.path.exists(result_path):
            print("result.json 不存在，终检无法进行", file=sys.stderr)
            return EXIT_INVALID
        result = load_json(result_path)
        case_path = os.path.join(args.input_dir, "case.json")
        case = load_json(case_path) if os.path.exists(case_path) else {}

        # --- 校验 1：合同字段完整性 ---
        fields = ((case.get("output_contract") or {}).get("required_fields")
                  or DEFAULT_FIELDS)
        missing = [f for f in fields if f not in result]
        null_unexplained = []
        unc_text = " ".join(str(u) for u in (result.get("uncertainty") or []))
        for f in fields:
            if f in ("status", "case_id"):
                continue
            if result.get(f) is None and f not in unc_text:
                null_unexplained.append(f)
        if missing:
            checks.append({"name": "contract_fields_present", "status": "fail",
                           "detail": "缺字段: %s" % ", ".join(missing)})
            overall_exit = EXIT_INVALID
        elif null_unexplained:
            checks.append({"name": "contract_fields_present", "status": "fail",
                           "detail": "字段为 null 且 uncertainty 无说明: %s"
                                     % ", ".join(null_unexplained)})
            overall_exit = EXIT_INVALID
        else:
            checks.append({"name": "contract_fields_present", "status": "pass",
                           "detail": "%d 个合同字段齐备；null 字段均有 uncertainty 说明"
                                     % len(fields)})

        # --- 校验 2：证据锚定真实性 ---
        records_path = find_material(args.input_dir, case, "records", ["records.json"])
        judgments_path = find_material(args.input_dir, case, "judgments",
                                       ["judgments.json", "decisions.json"])
        if not (records_path and judgments_path):
            checks.append({"name": "evidence_anchor_authenticity", "status": "skipped",
                           "detail": "records 或 judgments 缺失，证据锚定校验跳过"})
            if overall_exit == EXIT_OK:
                overall_exit = EXIT_INSUFFICIENT
        else:
            try:
                records = {r.get("record_id"): r
                           for r in load_items(records_path, "records")}
                judgments = load_items(judgments_path, "items")
            except ValueError as e:
                print("输入校验失败: %s" % e, file=sys.stderr)
                return EXIT_INVALID
            bad = []
            checked = 0
            for it in judgments:
                rec = records.get(it.get("record_id"))
                for c in (it.get("criteria") or []):
                    ev = c.get("evidence")
                    if not ev:
                        if c.get("verdict") in ("not_met", "uncertain"):
                            bad.append({"record_id": it.get("record_id"),
                                        "criterion": c.get("criterion_id"),
                                        "problem": "not_met/uncertain 判据缺 evidence"})
                        continue
                    quote = str(ev.get("quote") or "")
                    if not quote:
                        bad.append({"record_id": it.get("record_id"),
                                    "criterion": c.get("criterion_id"),
                                    "problem": "evidence.quote 为空"})
                        continue
                    checked += 1
                    if rec is None:
                        bad.append({"record_id": it.get("record_id"),
                                    "criterion": c.get("criterion_id"),
                                    "problem": "record_id 在 records 中不存在"})
                        continue
                    src = ev.get("source", "abstract")
                    hay = (rec.get("title") or "") if src == "title" else (
                        (rec.get("title") or "") + " " + (rec.get("abstract") or ""))
                    if quote.lower() not in hay.lower():
                        bad.append({"record_id": it.get("record_id"),
                                    "criterion": c.get("criterion_id"),
                                    "problem": "quote 未锚定到 %s 原文: %r" % (src, quote)})
            if bad:
                checks.append({"name": "evidence_anchor_authenticity", "status": "fail",
                               "detail": json.dumps(bad, ensure_ascii=False)})
                overall_exit = EXIT_INVALID
            else:
                checks.append({"name": "evidence_anchor_authenticity", "status": "pass",
                               "detail": "%d 条证据 quote 全部锚定到题录真实片段" % checked})

        # --- 校验 3：status 终置 ---
        degraded = bool(result.get("uncertainty"))
        failed = any(c["status"] == "fail" for c in checks)
        skipped = any(c["status"] == "skipped" for c in checks)
        if failed:
            result["status"] = "partial"
            note = "selfcheck 存在校验失败项，status 保持 partial，详见 work/selfcheck.json。"
        elif skipped or degraded:
            result["status"] = "partial"
            note = ("selfcheck 通过但有降级/说明项（见 uncertainty），status 置 partial。"
                    if not skipped else
                    "selfcheck 部分校验因输入不足被跳过，status 置 partial。")
        else:
            result["status"] = "completed"
            note = "selfcheck 全部通过，status 置 completed。"
        checks.append({"name": "status_finalization",
                       "status": "pass" if not failed else "fail",
                       "detail": note})
        unc = result.get("uncertainty") or []
        if result["status"] == "partial" and note not in unc:
            unc.append(note)
        result["uncertainty"] = unc

        report = {
            "generated_by": "selfcheck.py v1.0.0",
            "ts": utcnow(),
            "scope_note": "本终检不做计数闭合审计（属另一方向职责）。",
            "checks": checks,
            "final_status": result["status"],
        }
        sc_path = os.path.join(args.work, "selfcheck.json")
        save_json(sc_path, report)
        result["change_records"].append({
            "ts": utcnow(),
            "action": "selfcheck: %s" % result["status"],
            "files": [sc_path, result_path]})
        save_json(result_path, result)
        for c in checks:
            print("[%s] %s — %s" % (c["status"], c["name"], c["detail"]))
        return overall_exit
    except Exception as e:
        print("selfcheck 未预期失败: %s" % e, file=sys.stderr)
        return EXIT_INVALID


if __name__ == "__main__":
    sys.exit(main())
