#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""trust_scores.py — 字段信任分汇总 + quarantine 清单 + 回填 result.json

汇总前三步产物（field_profile.json / text_health_report.json /
repair_ledger.json / records_final.jsonl），为每条记录输出 field_trust：
  trusted    原值存在且通过全部检查
  repaired   经可验证安全修复（乱码修复、实体反转义、DOI 规范化、控制字符清除）
  filled     经快照内保守补全（强键、唯一取值、留痕可溯）
  missing    缺失或占位符，且无强键可补
  untrusted  存在但未通过校验（畸形 DOI、越界年份、不可修复乱码、页码形态异常）

含任一 untrusted 关键字段（title/abstract/year）或不可修复乱码的记录进入
quarantine 清单，供下游判定"证据可用性"。本技能不做纳排判定本身。

--finalize 时把产物按 output_contract 字段名回填进 result.json；
无法映射的合同字段保留 null 并在 uncertainty 说明；status 如实给
success / partial。

退出码：0 成功；2 运行/IO 错误；3 合同不满足（缺前置产物或 result.json
骨架缺失）。幂等：所有输出整体重写。
"""
import argparse
import json
import os
import sys

CRITICAL_FIELDS = ["title", "abstract", "year", "publication_year"]

# 合同字段名 -> 产物 的关键词映射（小写包含匹配）
CONTRACT_MAPPING = [
    (("profile", "completeness"), "profile_summary"),
    (("trust",), "field_trust"),
    (("repair", "ledger", "change"), "repair_ledger"),
    (("quarantine",), "quarantine"),
    (("language",), "language_flags"),
    (("decision", "screening", "inclusion", "exclusion"), "out_of_scope"),
]


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def build_trust(work):
    profile = load_json(os.path.join(work, "field_profile.json"))
    health = load_json(os.path.join(work, "text_health_report.json"))
    ledger = load_json(os.path.join(work, "repair_ledger.json"))
    records = []
    with open(os.path.join(work, "records_final.jsonl"),
              "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                records.append(json.loads(line))

    trust = {}   # rid -> {field: {"status":..., "reasons":[...]}}
    for rec in records:
        rid = rec["record_id"]
        trust[rid] = {}
        for field, value in rec.items():
            if field == "record_id":
                continue
            missing = value is None or (isinstance(value, str)
                                        and not value.strip())
            trust[rid][field] = {
                "status": "missing" if missing else "trusted",
                "reasons": [] if not missing else ["absent_or_empty"],
            }

    def mark(rid, field, status, reason):
        entry = trust.setdefault(rid, {}).setdefault(
            field, {"status": "missing", "reasons": ["absent_or_empty"]})
        # 严重度：untrusted > missing > filled > repaired > trusted
        order = {"trusted": 0, "repaired": 1, "filled": 2,
                 "missing": 3, "untrusted": 4}
        if order[status] >= order[entry["status"]] or \
                status in ("repaired", "filled"):
            entry["status"] = status
        entry["reasons"].append(reason)

    # 画像阶段：取值域违规视为 untrusted（字段级统计直接进 summary）
    for rid, flags in profile.get("domain_flags", {}).items():
        for flag in flags:
            mark(rid, flag["field"], "untrusted", flag["issue"])
    # 记录里没出现但画像统计为 placeholder 的字段：补 missing 标记
    placeholders = {"n/a", "na", "n.a.", ".", "-", "--", "none", "null",
                    "unknown", "missing", "?", "tbd", "not available"}
    for rec in records:
        rid = rec["record_id"]
        for field, value in rec.items():
            if field == "record_id":
                continue
            if isinstance(value, str) and \
                    value.strip().lower() in placeholders:
                mark(rid, field, "missing", "placeholder_value")

    # 文本健康：修复 -> repaired；不可修复 -> untrusted
    for issue in health.get("issues", []):
        if issue["action"] == "repaired":
            mark(issue["record_id"], issue["field"], "repaired",
                 issue["issue"])
        else:
            mark(issue["record_id"], issue["field"], "untrusted",
                 issue["issue"])

    # 修复台账：规范化 -> repaired；补全 -> filled；畸形 DOI -> untrusted
    for change in ledger.get("changes", []):
        status = "repaired" if change["rule"] == "doi_normalize" else "filled"
        mark(change["record_id"], change["field"], status, change["rule"])
    for flag in ledger.get("doi_flags", []):
        mark(flag["record_id"], "doi", "untrusted", flag["issue"])

    # quarantine：关键字段 untrusted 或不可修复乱码
    unrepairable = {"%s.%s" % (i["record_id"], i["field"])
                    for i in health.get("issues", [])
                    if i["action"] == "flagged_untrusted"}
    quarantine = []
    for rid, fields in trust.items():
        reasons = []
        for field in CRITICAL_FIELDS:
            if fields.get(field, {}).get("status") == "untrusted":
                reasons.append("critical_field_untrusted:%s" % field)
        for key in unrepairable:
            if key.startswith(rid + "."):
                reasons.append("unrepairable_text:%s" % key.split(".", 1)[1])
        if fields.get("doi", {}).get("status") == "untrusted":
            reasons.append("doi_untrusted")
        if reasons:
            quarantine.append({"record_id": rid,
                               "reasons": sorted(set(reasons))})

    language_flags = {rid: e for rid, e in
                      profile.get("language", {}).items()
                      if e.get("language_flag")}

    result = {
        "generated_by": "trust_scores.py",
        "records_total": len(records),
        "field_trust": trust,
        "quarantine": sorted(quarantine, key=lambda q: q["record_id"]),
        "language_flags": language_flags,
        "profile_summary": {
            "records_total": profile.get("records_total"),
            "fields": profile.get("fields"),
        },
        "repair_ledger": ledger,
        "notes": ["field_trust 供下游判定证据可用性；本技能不做纳排判定；",
                   "missing 不等于排除，untrusted 才进 quarantine。"],
    }
    return result


def finalize_result(output_dir, trust_result, sources):
    """按 output_contract 回填 result.json；返回 (status, 未填字段列表)。"""
    result_path = os.path.join(output_dir, "result.json")
    if not os.path.exists(result_path):
        print("ERROR: %s 不存在，请先运行 scaffold_result.py" % result_path,
              file=sys.stderr)
        sys.exit(3)
    result = load_json(result_path)
    contract_fields = [k for k in result
                       if k not in ("case_id", "status", "sources",
                                    "uncertainty", "change_records")]
    unfilled = []

    def note(msg):
        if msg not in result["uncertainty"]:  # 幂等：不重复追加
            result["uncertainty"].append(msg)

    for field in contract_fields:
        if result.get(field) is not None:
            continue
        target = None
        low = field.lower()
        for keywords, name in CONTRACT_MAPPING:
            if any(k in low for k in keywords):
                target = name
                break
        if target == "out_of_scope" or target is None:
            note("合同字段 %s 无法由本技能填充（%s），保留 null。"
                 % (field, "纳排判定不在本技能范围" if target == "out_of_scope"
                    else "无匹配产物"))
            unfilled.append(field)
        elif target == "profile_summary":
            result[field] = trust_result["profile_summary"]
        else:
            result[field] = trust_result[target]
    result["change_records"] = (
        trust_result["repair_ledger"].get("changes", [])
        + [{"note": "冲突未补全（保守策略）", **c}
           for c in trust_result["repair_ledger"].get("conflicts", [])])
    result["sources"] = sources
    result["status"] = "partial" if unfilled else "success"
    if unfilled:
        note("status=partial：合同字段 %s 保留 null。" % ",".join(unfilled))
    with open(result_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2, sort_keys=True)
    return result["status"], unfilled


def main(argv=None):
    parser = argparse.ArgumentParser(description="字段信任分汇总与 result.json 回填")
    parser.add_argument("--work", default="/app/work", help="中间产物目录")
    parser.add_argument("--output", default="/app/output", help="交付目录")
    parser.add_argument("--records-source", default=None,
                        help="原始题录来源描述（写入 result.json sources）")
    parser.add_argument("--finalize", action="store_true",
                        help="回填 /app/output/result.json")
    args = parser.parse_args(argv)
    try:
        for name in ("field_profile.json", "text_health_report.json",
                     "repair_ledger.json", "records_final.jsonl"):
            if not os.path.exists(os.path.join(args.work, name)):
                print("ERROR: 缺前置产物 %s，请按流程先运行前面脚本" % name,
                      file=sys.stderr)
                return 3
        trust_result = build_trust(args.work)
        os.makedirs(args.output, exist_ok=True)
        trust_path = os.path.join(args.output, "trust_scores.json")
        with open(trust_path, "w", encoding="utf-8") as fh:
            json.dump(trust_result, fh, ensure_ascii=False, indent=2,
                      sort_keys=True)
        # 修复台账同时作为独立交付物复制一份
        ledger_path = os.path.join(args.output, "repair_ledger.json")
        with open(ledger_path, "w", encoding="utf-8") as fh:
            json.dump(trust_result["repair_ledger"], fh,
                      ensure_ascii=False, indent=2, sort_keys=True)
        print("OK: %d 条记录；quarantine=%d，language_flags=%d -> %s, %s"
              % (trust_result["records_total"],
                 len(trust_result["quarantine"]),
                 len(trust_result["language_flags"]),
                 trust_path, ledger_path))
        if args.finalize:
            sources = ["case.json（含 output_contract）",
                       args.records_source or "快照内题录（离线）",
                       "全程离线，无联网补全"]
            status, unfilled = finalize_result(args.output, trust_result,
                                               sources)
            print("OK: result.json 已回填，status=%s，未填字段=%s"
                  % (status, unfilled or "无"))
        return 0
    except SystemExit:
        raise
    except FileNotFoundError as exc:
        print("ERROR: 文件不存在: %s" % exc, file=sys.stderr)
        return 2
    except (ValueError, OSError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2
    except Exception as exc:  # 顶层兜底
        print("ERROR: 未预期异常: %r" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
