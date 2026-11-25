#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
timeline_build.py — 构建每记录有序时间轴；检测事件顺序冲突；核查观测同族优先权一致性。

常规先后顺序（仅作为冲突检测基线，非法律推定）:
  priority ≤ filing ≤ publication ≤ grant

冲突一律生成为结构化 conflict 记录，绝不静默修正/取舍。

用法:
  python3 timeline_build.py --events EV1.json [EV2.json ...] [-o OUT.json]
  python3 timeline_build.py --events GX1001.json GX1003.json --family [-o OUT.json]

输入为 event_extract.py 的输出 JSON（{"records": [...]}）。

--family: 将传入的全部记录视为“观测到的、主张同一优先权的同族成员”。
  成员间优先权日不同 → family_priority_conflict；相同 → family_priority_consistent。
  注意：观测链接不构成完整同族，一致性结论仅限观测范围。

退出码: 0 正常且无冲突 / 1 检测到冲突（冲突已写入输出） / 2 用法错误
"""
import argparse
import json
import os
import sys

KIND_ORDER = {"priority": 0, "filing": 1, "publication": 2, "grant": 3}
PRECISION_RANK = {"day": 3, "month": 2, "year": 1}


def _coarser_key(ev, min_rank):
    """按双方较低精度截断 iso 字符串，用于跨精度比较。"""
    iso = ev["iso"]
    if min_rank >= 3:
        return iso
    if min_rank == 2:
        return iso[:7]
    return iso[:4]


def build_timeline(record):
    events = record.get("events", [])
    placed, unplaced, warnings = [], [], []
    for ev in events:
        if ev.get("iso"):
            placed.append(ev)
        else:
            unplaced.append(ev)
            warnings.append("UNPLACED_EVENT: 事件 %s（raw=%r）无可解析日期，未进入排序。"
                            % (ev.get("event_id"), ev.get("raw")))
    placed.sort(key=lambda e: (e["iso"], KIND_ORDER.get(e["kind"], 9)))
    for ev in placed:
        if len(ev.get("interpretations", [])) > 1:
            warnings.append(
                "AMBIGUOUS_EVENT_ORDERED_BY_PRIMARY: 事件 %s（raw=%r）存在多个解释，"
                "排序暂按首个解释 %s，未做静默取舍，需人工判定。"
                % (ev.get("event_id"), ev.get("raw"), ev["iso"]))
        if ev.get("kind") == "unknown":
            warnings.append(
                "UNKNOWN_KIND_NOT_ORDER_CHECKED: 事件 %s 口径未知，"
                "仅按日期放入时间轴，不参与顺序冲突检测。" % ev.get("event_id"))
    timeline = [{
        "event_id": e["event_id"], "kind": e["kind"], "iso": e["iso"],
        "precision": e["precision"], "format_tag": e["format_tag"],
        "quote": e["quote"], "span": e["span"],
        "interpretations": e.get("interpretations", []),
        "warnings": e.get("warnings", []),
    } for e in placed]
    return {
        "record_id": record.get("record_id"),
        "timeline": timeline,
        "unplaced": [{
            "event_id": e["event_id"], "kind": e["kind"], "raw": e["raw"],
            "quote": e["quote"], "span": e["span"], "warnings": e.get("warnings", []),
        } for e in unplaced],
        "warnings": warnings,
    }


def detect_order_violations(record, timeline_entry):
    """对同一记录内 priority/filing/publication/grant 事件两两核查常规先后顺序。"""
    conflicts = []
    by_kind = {}
    for e in timeline_entry["timeline"]:
        if e["kind"] in KIND_ORDER:
            by_kind.setdefault(e["kind"], []).append(e)
    kinds = sorted(by_kind, key=lambda k: KIND_ORDER[k])
    for i in range(len(kinds)):
        for j in range(i + 1, len(kinds)):
            ki, kj = kinds[i], kinds[j]
            for ei in by_kind[ki]:
                for ej in by_kind[kj]:
                    rank = min(PRECISION_RANK.get(ei["precision"], 3),
                               PRECISION_RANK.get(ej["precision"], 3))
                    vi, vj = _coarser_key(ei, rank), _coarser_key(ej, rank)
                    if vi > vj:
                        conf = {
                            "type": "order_violation",
                            "record_id": record.get("record_id"),
                            "expected": "%s <= %s" % (ki, kj),
                            "observed": "%s(%s) 晚于 %s(%s)" % (ki, vi, kj, vj),
                            "events": [ei["event_id"], ej["event_id"]],
                            "detail": "记录 %s 中 %s 日期 %s 晚于 %s 日期 %s，违反常规"
                                      "先后顺序 %s ≤ %s。" % (record.get("record_id"),
                                                            ki, vi, kj, vj, ki, kj),
                            "resolution": "none — 未做任何静默修正，须人工回查来源原文。",
                        }
                        if rank < 3:
                            conf["precision_note"] = (
                                "比较按双方较低精度（%s 级）截断进行。" %
                                {2: "月", 1: "年"}[rank])
                        conflicts.append(conf)
    return conflicts


def family_priority_check(records):
    """观测同族优先权一致性核查：优先权日集合不同 → 冲突；相同 → 一致。"""
    members = {}
    for rec in records:
        dates = sorted({ev["iso"] for ev in rec.get("events", [])
                        if ev.get("kind") == "priority" and ev.get("iso")})
        if dates:
            members[rec.get("record_id")] = dates
    note = ("观测链接不构成完整同族（observed links are not exhaustive families）；"
            "本核查结论仅限所给观测成员，不外推。")
    if not members:
        return {"type": "family_priority_unknown",
                "members": {},
                "note": note,
                "warning": "观测成员中未找到任何可解析的 priority 事件，无法核查。"}
    distinct = sorted({d for ds in members.values() for d in ds})
    if len(distinct) == 1:
        return {"type": "family_priority_consistent",
                "priority_date": distinct[0],
                "members": members,
                "note": note}
    return {"type": "family_priority_conflict",
            "distinct_priority_dates": distinct,
            "members": members,
            "detail": "观测同族成员主张同一优先权，但观测到的优先权日不一致：%s。"
                      "可能原因：OCR 错误、著录错误、优先权链不同或成员归属错误。"
                      % "、".join(distinct),
            "resolution": "none — 未做任何静默取舍，须人工回查各成员原文。",
            "note": note}


def load_event_files(paths):
    records = []
    for p in paths:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        for rec in data.get("records", []):
            records.append(rec)
    return records


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="构建每记录时间轴、检测顺序冲突、核查观测同族优先权一致性。")
    ap.add_argument("--events", nargs="+", required=True,
                    help="event_extract.py 输出 JSON（可多个）")
    ap.add_argument("--family", action="store_true",
                    help="将传入记录视为观测同族，执行优先权一致性核查")
    ap.add_argument("-o", "--output", help="输出 JSON 路径（缺省打印到 stdout）")
    args = ap.parse_args(argv)

    try:
        records = load_event_files(args.events)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2
    if not records:
        print("ERROR: 未从输入文件读到任何记录。", file=sys.stderr)
        return 2

    timelines, conflicts = [], []
    for rec in records:
        tl = build_timeline(rec)
        timelines.append(tl)
        conflicts.extend(detect_order_violations(rec, tl))

    family_check = None
    if args.family:
        family_check = family_priority_check(records)
        if family_check["type"] == "family_priority_conflict":
            conflicts.append(family_check)

    result = {
        "timelines": timelines,
        "conflicts": conflicts,
        "family_check": family_check,
        "order_baseline": "priority <= filing <= publication <= grant",
        "note": "冲突一律以结构化记录呈现，未做静默修正；"
                "unknown 口径事件不参与顺序冲突检测。",
    }
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
    else:
        print(payload)
    return 1 if conflicts else 0


if __name__ == "__main__":
    sys.exit(main())
