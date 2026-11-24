#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""status_ledger.py — 法律状态台账校验器（登记优先协议 / register-first protocol）。

用法:
    python3 status_ledger.py validate --ledger status.jsonl --sources sources.json [--today YYYY-MM-DD]

台账每行一个 JSON 对象:
    {patent_ref, asserted_status, status_effective_date, source_id, query_date, note}

校验规则（违规逐条打印，退出码 1）:
    S1  asserted_status 只能由 tier=register / official_gazette 的来源支撑；
        aggregation / repost / unknown 级来源只能支撑 "unknown"（未核验）声明。
    S2  每条断言必须带 query_date（且为合法 ISO 日期）。
    S3  query_date 早于 --today 前 90 天 → 警告 "状态可能滞后"（警告，不判失败）。
    S4  asserted_status 枚举 {granted, expired, withdrawn, rejected, pending, unknown}；
        "unknown" 是一等公民式的诚实取值。
    S5  同一 patent_ref 出现冲突断言 → 输出冲突块：双方保留，登记级来源优先
        作为头条状态（headline），并标记 conflict_disclosed=true。冲突本身不判失败。
    S6  status_effective_date 必须是 ISO YYYY-MM-DD 或显式 null（键缺失视为违规）。

退出码: 0 = 通过（可有警告与已披露冲突）; 1 = 治理违规; 2 = 用法/输入错误。
"""
import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

STATUS_ENUM = {"granted", "expired", "withdrawn", "rejected", "pending", "unknown"}
REGISTER_TIERS = {"register", "official_gazette"}
TIER_PRIORITY = {"register": 0, "official_gazette": 1, "aggregation": 2, "repost": 3, "unknown": 4}
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LAG_DAYS = 90


def parse_iso(value):
    """严格解析 ISO YYYY-MM-DD；非法返回 None。"""
    if not isinstance(value, str) or not ISO_RE.match(value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def load_sources(path):
    """读取 sources.json，返回 source_id -> 条目 的映射。容忍 list / {sources:[...]} / {id: {...}} 三种形态。"""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"[输入错误] sources 文件不存在: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[输入错误] sources 文件不是合法 JSON: {path}: {exc}")
    if isinstance(raw, dict) and isinstance(raw.get("sources"), list):
        entries = raw["sources"]
    elif isinstance(raw, list):
        entries = raw
    elif isinstance(raw, dict):
        entries = [dict(v, source_id=k) for k, v in raw.items() if isinstance(v, dict)]
    else:
        raise SystemExit(f"[输入错误] sources 文件结构无法识别: {path}")
    table = {}
    for e in entries:
        if not isinstance(e, dict):
            continue
        sid = e.get("source_id") or e.get("id")
        if sid:
            table[str(sid)] = e
    return table


def validate(ledger_path, sources_path, today):
    table = load_sources(sources_path)
    try:
        lines = Path(ledger_path).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        raise SystemExit(f"[输入错误] ledger 文件不存在: {ledger_path}")

    violations, warnings, records = [], [], []
    for lineno, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            violations.append({"rule": "S0", "line": lineno, "patent_ref": None,
                               "message": f"行不是合法 JSON: {exc}"})
            continue
        if not isinstance(rec, dict):
            violations.append({"rule": "S0", "line": lineno, "patent_ref": None,
                               "message": "行不是 JSON 对象"})
            continue

        ref = rec.get("patent_ref")
        status = rec.get("asserted_status")
        sid = rec.get("source_id")
        qdate_raw = rec.get("query_date")

        if not ref:
            violations.append({"rule": "S0", "line": lineno, "patent_ref": None,
                               "message": "缺少 patent_ref"})
        # S4: 状态枚举
        if status not in STATUS_ENUM:
            violations.append({"rule": "S4", "line": lineno, "patent_ref": ref,
                               "message": f"asserted_status={status!r} 不在枚举 {sorted(STATUS_ENUM)} 内"})
        # S1: 来源层级纪律
        src = table.get(str(sid)) if sid is not None else None
        tier = (src or {}).get("tier", "unknown")
        if tier not in TIER_PRIORITY:
            tier = "unknown"
        if src is None:
            violations.append({"rule": "S1", "line": lineno, "patent_ref": ref,
                               "message": f"source_id={sid!r} 未在 sources.json 中登记，按 unknown 级处理，"
                                          f"不得支撑 asserted_status={status!r}"})
        elif tier not in REGISTER_TIERS and status != "unknown":
            violations.append({"rule": "S1", "line": lineno, "patent_ref": ref,
                               "message": f"来源 {sid} 的 tier={tier}，aggregation/repost/unknown 级来源只能支撑 "
                                          f"'unknown'（未核验）声明，不得断言 {status!r}"})
        # S2: query_date 必须存在且为合法 ISO
        qdate = parse_iso(qdate_raw)
        if qdate is None:
            violations.append({"rule": "S2", "line": lineno, "patent_ref": ref,
                               "message": f"缺少 query_date 或格式非法: {qdate_raw!r}（每条断言必须带查询日期）"})
        elif today is not None:
            # S3: 滞后警告
            lag = (today - qdate).days
            if lag > LAG_DAYS:
                warnings.append({"rule": "S3", "line": lineno, "patent_ref": ref,
                                 "message": f"状态可能滞后：query_date={qdate_raw} 距 today={today.isoformat()} "
                                            f"已 {lag} 天（>{LAG_DAYS} 天）"})
        # S6: status_effective_date 必须存在且为 ISO 或显式 null
        if "status_effective_date" not in rec:
            violations.append({"rule": "S6", "line": lineno, "patent_ref": ref,
                               "message": "缺少 status_effective_date 键（允许显式 null，但不允许省略）"})
        else:
            eff = rec.get("status_effective_date")
            if eff is not None and parse_iso(eff) is None:
                violations.append({"rule": "S6", "line": lineno, "patent_ref": ref,
                                   "message": f"status_effective_date={eff!r} 不是 ISO YYYY-MM-DD，也不是显式 null"})

        records.append({"line": lineno, "patent_ref": ref, "asserted_status": status,
                        "source_id": sid, "tier": tier, "query_date": qdate_raw})

    # S5: 冲突检测与头条裁决（双保留 + 登记级优先 + 披露）
    by_ref = {}
    for r in records:
        if r["patent_ref"] and r["asserted_status"] in STATUS_ENUM:
            by_ref.setdefault(r["patent_ref"], []).append(r)

    conflicts, headlines = [], {}
    for ref, group in sorted(by_ref.items()):
        distinct = sorted({g["asserted_status"] for g in group})
        group_sorted = sorted(group, key=lambda g: (TIER_PRIORITY.get(g["tier"], 4),
                                                    str(g["query_date"] or "")))
        # 登记级优先；同层级取较新 query_date（倒序重排一次）
        best_tier = min(TIER_PRIORITY.get(g["tier"], 4) for g in group_sorted)
        best_group = [g for g in group_sorted if TIER_PRIORITY.get(g["tier"], 4) == best_tier]
        headline_rec = sorted(best_group, key=lambda g: str(g["query_date"] or ""), reverse=True)[0]
        has_conflict = len(distinct) > 1
        if has_conflict:
            conflicts.append({
                "patent_ref": ref,
                "assertions": [{"asserted_status": g["asserted_status"], "source_id": g["source_id"],
                                "tier": g["tier"], "query_date": g["query_date"], "line": g["line"]}
                               for g in group],
                "headline": {"asserted_status": headline_rec["asserted_status"],
                             "source_id": headline_rec["source_id"], "tier": headline_rec["tier"]},
                "resolution": "双方断言均保留；登记级（register > official_gazette > 其他）来源优先作为头条状态，冲突已披露。",
                "conflict_disclosed": True,
            })
        headlines[ref] = {"status": headline_rec["asserted_status"],
                          "source_id": headline_rec["source_id"],
                          "tier": headline_rec["tier"],
                          "query_date": headline_rec["query_date"],
                          "conflict_disclosed": has_conflict}

    report = {
        "report": "status_ledger_validation",
        "ledger": str(ledger_path),
        "sources": str(sources_path),
        "today": today.isoformat() if today else None,
        "lines_checked": len(records) + sum(1 for v in violations if v["rule"] == "S0"),
        "ok": not violations,
        "violations": violations,
        "warnings": warnings,
        "conflicts": conflicts,
        "headline_statuses": headlines,
    }
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description="法律状态台账校验器（登记优先协议）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pv = sub.add_parser("validate", help="校验台账")
    pv.add_argument("--ledger", required=True)
    pv.add_argument("--sources", required=True)
    pv.add_argument("--today", default=None, help="YYYY-MM-DD，默认取系统当前日期")
    args = ap.parse_args(argv)

    if args.cmd == "validate":
        if args.today:
            today = parse_iso(args.today)
            if today is None:
                print(f"[输入错误] --today 格式非法: {args.today!r}", file=sys.stderr)
                return 2
        else:
            today = date.today()
        try:
            report = validate(args.ledger, args.sources, today)
        except SystemExit as exc:
            print(exc, file=sys.stderr)
            return 2
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
