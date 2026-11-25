#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fragility_report.py — 排除稳健性（fragility）分析。

只消费上游 judgments，回答："排除决定有多依赖单一脆弱判据？"
指标：
  - 主理由码（primary_reason_code）分布；
  - 单理由排除（恰好一条判据 not_met）数量与占比；
  - 无 not_met 依据的排除（excluded_without_not_met）数量；
  - fragile_share = (单理由排除 + 无 not_met 排除) / 排除总数，
    >= 阈值（默认 0.5，--threshold 可调）即置 fragile_flag=true，提示整体排除面脆弱。

产物：work/fragility_report.json；增量填充 result.json 的 fragility_report 字段。
退出码：0=通过；2=judgments 缺失（诚实降级）；3=校验失败。
"""
import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

EXIT_OK, EXIT_INSUFFICIENT, EXIT_INVALID = 0, 2, 3


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


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


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


def load_judgments(path):
    data = load_json(path)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    raise ValueError("judgments 文件结构不识别：应为 list 或含 items 的 object")


def ensure_result(result_path, case_id):
    if os.path.exists(result_path):
        return load_json(result_path)
    return {"case_id": case_id, "status": "partial",
            "sources": [], "uncertainty": [], "change_records": []}


def add_source(result, path, role):
    entry = {"path": path, "sha256": sha256_of(path), "role": role}
    sources = [s for s in (result.get("sources") or []) if s.get("path") != path]
    sources.append(entry)
    result["sources"] = sources


def add_uncertainty(result, note):
    unc = result.get("uncertainty") or []
    if note not in unc:
        unc.append(note)
    result["uncertainty"] = unc


def main():
    ap = argparse.ArgumentParser(description="排除稳健性（fragility）分析")
    ap.add_argument("--input-dir", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    ap.add_argument("--threshold", type=float, default=0.5,
                    help="fragile_share 报警阈值（默认 0.5）")
    args = ap.parse_args()

    try:
        os.makedirs(args.work, exist_ok=True)
        os.makedirs(args.output_dir, exist_ok=True)
        result_path = os.path.join(args.output_dir, "result.json")
        case_path = os.path.join(args.input_dir, "case.json")
        case = load_json(case_path) if os.path.exists(case_path) else {}
        result = ensure_result(result_path, case.get("case_id"))

        judgments_path = find_material(args.input_dir, case, "judgments",
                                       ["judgments.json", "decisions.json"])
        if not judgments_path:
            result["fragility_report"] = None
            add_uncertainty(result,
                            "字段 fragility_report 置 null：judgments/decisions 缺失，"
                            "排除稳健性分析未执行（诚实降级）。")
            result["change_records"].append({
                "ts": utcnow(),
                "action": "fragility_report: judgments missing, degraded",
                "files": [result_path]})
            save_json(result_path, result)
            print("judgments 缺失：fragility 降级", file=sys.stderr)
            return EXIT_INSUFFICIENT

        try:
            items = load_judgments(judgments_path)
        except (ValueError, json.JSONDecodeError) as e:
            print("judgments 校验失败: %s" % e, file=sys.stderr)
            return EXIT_INVALID

        exclusions = [it for it in items if it.get("decision") == "exclude"]
        reason_counter = Counter(
            it.get("primary_reason_code") or "UNSPECIFIED" for it in exclusions)
        single_reason, uncertain_based, robust = [], [], []
        for it in exclusions:
            criteria = it.get("criteria") or []
            not_met = [c for c in criteria if c.get("verdict") == "not_met"]
            entry = {
                "record_id": it.get("record_id"),
                "primary_reason_code": it.get("primary_reason_code"),
                "not_met_criteria": [c.get("criterion_id") for c in not_met],
            }
            if len(not_met) == 1:
                single_reason.append(entry)
            elif len(not_met) == 0:
                uncertain_based.append(entry)
            else:
                robust.append(entry)

        n_ex = len(exclusions)
        fragile_share = ((len(single_reason) + len(uncertain_based)) / n_ex) if n_ex else 0.0
        report = {
            "generated_by": "fragility_report.py v1.0.0",
            "total_exclusions": n_ex,
            "reason_code_distribution": dict(sorted(
                reason_counter.items(), key=lambda kv: (-kv[1], kv[0]))),
            "single_reason_exclusions": {
                "count": len(single_reason),
                "share": round(len(single_reason) / n_ex, 4) if n_ex else None,
                "items": single_reason,
            },
            "excluded_without_not_met": {
                "count": len(uncertain_based),
                "items": uncertain_based,
            },
            "robust_exclusions": {"count": len(robust),
                                  "items": robust},
            "fragile_share": round(fragile_share, 4),
            "fragile_threshold": args.threshold,
            "fragile_flag": fragile_share >= args.threshold if n_ex else False,
            "interpretation": (
                "fragile_share=%.3f %s阈值 %.2f：%s" % (
                    fragile_share,
                    ">=" if fragile_share >= args.threshold else "<",
                    args.threshold,
                    "排除面整体偏脆弱，建议优先复核单理由排除与无 not_met 排除"
                    if n_ex and fragile_share >= args.threshold
                    else "排除面稳健性可接受")),
        }
        out_path = os.path.join(args.work, "fragility_report.json")
        save_json(out_path, report)

        result["fragility_report"] = report
        add_source(result, judgments_path, "judgments")
        result["change_records"].append({
            "ts": utcnow(),
            "action": "fragility_report: fragile_share=%.3f flag=%s" % (
                fragile_share, report["fragile_flag"]),
            "files": [out_path, result_path]})
        save_json(result_path, result)
        print("排除 %d 条；fragile_share=%.3f；fragile_flag=%s" % (
            n_ex, fragile_share, report["fragile_flag"]))
        return EXIT_OK
    except Exception as e:
        print("fragility_report 未预期失败: %s" % e, file=sys.stderr)
        return EXIT_INVALID


if __name__ == "__main__":
    sys.exit(main())
