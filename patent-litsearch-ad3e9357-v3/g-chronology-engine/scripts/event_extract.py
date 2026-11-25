#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
event_extract.py — 从专利记录文本（或 JSON）中抽取带口径类型标注的日期事件。

类型（date-kind）严格区分：priority / filing / publication / grant / unknown。
每个事件携带：逐字引文 quote、字符区间 span、归一化结果（iso/precision/format_tag/
interpretations）与警告。无法归类的日期字符串 → kind=unknown 并附警告，绝不猜测。

用法:
  python3 event_extract.py RECORD.txt [-o OUT.json]
  python3 event_extract.py RECORDS.json [-o OUT.json]
  python3 event_extract.py RECORD.txt --ocr-policy fix-digit-confusion
  python3 event_extract.py RECORD.txt --kind-keywords my_keywords.json

输入 JSON 形式（任选）:
  {"record_id": "...", "text": "..."}
  [{"record_id": "...", "text": "..."}, ...]
  {"records": [{"record_id": "...", "text": "..."}, ...]}

类型关键词可用 --kind-keywords 指定 JSON 文件覆盖，格式: {"kind": ["kw1","kw2",...]}。

退出码: 0 正常完成（含 unknown 事件与警告） / 1 输入读取或解析失败 / 2 用法错误
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import date_norm  # noqa: E402

KINDS = ["priority", "filing", "publication", "grant", "unknown"]

# 默认类型关键词（英文 + 中文）。同一关键词只属于一个口径；就近匹配判定。
DEFAULT_KIND_KEYWORDS = {
    "priority": ["priority date", "claim of priority", "priority claimed",
                 "priority", "优先权日", "优先日", "优先权"],
    "filing": ["filing date", "application filed", "date of filing", "filed",
               "filing", "申请日", "申请"],
    "publication": ["publication date", "date of publication", "published",
                    "publication", "pub. date", "公开日", "公布日", "公开", "公布"],
    "grant": ["date of patent", "grant date", "date of grant", "granted",
              "grant", "issue date", "issued", "授权公告日", "授权日", "授权", "颁证"],
}

BEFORE_WINDOW = 120   # 日期前向上下文窗口（字符）
AFTER_WINDOW = 30     # 日期后向上下文窗口
AFTER_PENALTY = 2     # 后向命中的距离惩罚，等距时优先前向证据
BOUNDARY_CHARS = "\n。.!?；;"  # 句/行边界：前向窗口在最近的边界处截断，防止跨句串扰


def _before_window(text, s):
    w = text[max(0, s - BEFORE_WINDOW):s]
    idx = max(w.rfind(c) for c in BOUNDARY_CHARS)
    if idx >= 0:
        w = w[idx + 1:]
    return w


def _after_window(text, e):
    w = text[e:e + AFTER_WINDOW]
    idxs = [w.find(c) for c in BOUNDARY_CHARS if w.find(c) >= 0]
    if idxs:
        w = w[:min(idxs)]
    return w


def load_kind_keywords(path):
    if not path:
        return DEFAULT_KIND_KEYWORDS
    with open(path, "r", encoding="utf-8") as f:
        custom = json.load(f)
    if not isinstance(custom, dict):
        raise ValueError("kind-keywords 文件必须是 {kind: [keywords...]} 的 JSON 对象")
    merged = {k: list(v) for k, v in DEFAULT_KIND_KEYWORDS.items()}
    for kind, kws in custom.items():
        if kind not in KINDS and kind != "unknown":
            merged[kind] = list(kws)
        else:
            merged[kind] = list(kws)
    return merged


def classify(text, s, e, kind_keywords):
    """依据日期邻近文本判定事件口径。返回 (kind, evidence_keyword 或 None)。

    规则：在前向窗口（默认 120 字符，且在最近的句/行边界处截断，避免跨句串扰）与
    后向窗口（默认 30 字符）内检索各口径关键词，取距日期最近的一次命中；
    等距时取关键词更长者；后向命中附加距离惩罚。
    """
    before = _before_window(text, s)
    after = _after_window(text, e)
    best = None  # (distance, -len(kw), kind, kw)
    for kind, kws in kind_keywords.items():
        for kw in kws:
            if not kw:
                continue
            for m in re.finditer(re.escape(kw), before, re.IGNORECASE):
                cand = (len(before) - m.end(), -len(kw), kind, kw)
                if best is None or cand < best:
                    best = cand
            for m in re.finditer(re.escape(kw), after, re.IGNORECASE):
                cand = (m.start() + AFTER_PENALTY, -len(kw), kind, kw)
                if best is None or cand < best:
                    best = cand
    if best is None:
        return ("unknown", None)
    return (best[2], best[3])


def extract_events(text, record_id, ocr_policy="keep-raw", kind_keywords=None):
    kw = kind_keywords or DEFAULT_KIND_KEYWORDS
    events = []
    for i, cand in enumerate(date_norm.iter_date_candidates(text, ocr_policy)):
        s, e = cand["span"]
        kind, kw_hit = classify(text, s, e, kw)
        ev = {
            "event_id": "%s-evt-%02d" % (record_id, i + 1),
            "kind": kind,
            "raw": cand["raw"],
            "iso": cand["iso"],
            "precision": cand["precision"],
            "format_tag": cand["format_tag"],
            "interpretations": cand["interpretations"],
            "warnings": list(cand["warnings"]),
            "quote": text[s:e],
            "span": [s, e],
            "context": text[max(0, s - 40):min(len(text), e + 40)],
        }
        if kind == "unknown":
            ev["warnings"].append(
                "UNKNOWN_EVENT_KIND: 无法从邻近文本判定该日期的口径"
                "（priority/filing/publication/grant），已标记为 unknown，未做猜测。")
        else:
            ev["kind_evidence"] = kw_hit
        events.append(ev)
    return events


def load_records(path):
    """读取输入文件，返回 [{record_id, text, source_path}]。"""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if path.lower().endswith(".json"):
        data = json.loads(content)
        if isinstance(data, dict) and "records" in data:
            items = data["records"]
        elif isinstance(data, dict) and "text" in data:
            items = [data]
        elif isinstance(data, list):
            items = data
        else:
            raise ValueError("JSON 输入必须含 text 字段或 records 列表")
        out = []
        for i, it in enumerate(items):
            if not isinstance(it, dict) or "text" not in it:
                raise ValueError("records[%d] 缺少 text 字段" % i)
            out.append({"record_id": it.get("record_id") or "rec-%d" % (i + 1),
                        "text": it["text"], "source_path": path})
        return out
    stem = os.path.splitext(os.path.basename(path))[0]
    return [{"record_id": stem, "text": content, "source_path": path}]


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="从专利记录文本/JSON 抽取带口径类型标注的日期事件。")
    ap.add_argument("input", help="记录文件：.txt（单条记录）或 .json（单条/多条）")
    ap.add_argument("-o", "--output", help="输出 JSON 路径（缺省打印到 stdout）")
    ap.add_argument("--record-id", help="覆盖文本输入的 record_id")
    ap.add_argument("--ocr-policy", choices=["keep-raw", "fix-digit-confusion"],
                    default="keep-raw")
    ap.add_argument("--kind-keywords", help="自定义类型关键词 JSON 文件")
    args = ap.parse_args(argv)

    try:
        kind_keywords = load_kind_keywords(args.kind_keywords)
        records = load_records(args.input)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1

    out_records = []
    for rec in records:
        rid = args.record_id or rec["record_id"]
        events = extract_events(rec["text"], rid, args.ocr_policy, kind_keywords)
        warns = []
        n_unknown = sum(1 for e in events if e["kind"] == "unknown")
        if n_unknown:
            warns.append("RECORD_HAS_UNKNOWN_KIND_EVENTS: 本记录含 %d 个口径未判定事件，"
                         "见各事件 warnings。" % n_unknown)
        out_records.append({"record_id": rid, "source_path": rec["source_path"],
                            "ocr_policy": args.ocr_policy,
                            "events": events, "warnings": warns})

    result = {"records": out_records,
              "kinds": KINDS,
              "note": "kind 口径严格区分：priority≠filing≠publication≠grant；"
                      "无法判定者一律 unknown，绝不静默归类。"}
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
