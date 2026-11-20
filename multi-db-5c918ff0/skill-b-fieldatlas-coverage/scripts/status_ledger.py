#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""status_ledger.py — 失败降级台账：从材料与中间产物中提取并分类异常状态。

类别与处置（详见 references/gap_taxonomy.md）：
  empty_result        某查询/某来源零命中                     → 写入 uncertainty
  http_error          材料中含 HTTP 4xx/5xx 错误响应痕迹      → 该库降级 partial
  timeout             材料中含超时痕迹                        → 该库降级 partial
  rate_limited        材料中含限流/配额痕迹（429/quota 等）   → 该库降级 partial
  schema_drift        字段结构与映射表不符（map_report 漂移日志）→ 写入 uncertainty
  withdrawn_retracted 记录含 retracted/withdrawn/correction 标记
                      → 单列入结果并标记 status，人工确认是否纳入
  unparsed_file       无法解析/嗅探失败的文件（逐名列出）      → 降级 partial
  parse_drop          记录级解析丢弃（逐条留原因）             → 写入 uncertainty

输出 /app/work/status_ledger.json 与 /app/work/uncertainty_draft.json
（供组装 result.json.uncertainty 时合并）。

退出码：0=台账生成（可以为空台账）；2=case_summary 缺失（材料不足）；3=输入非法。
"""
import argparse
import json
import os
import re
import sys

HTTP_ERR_RE = re.compile(
    r"HTTP/1\.[01]\"?\s+[45]\d\d|\"(?:status|code)\"\s*:\s*[45]\d\d|"
    r"\bstatus\s*=\s*[45]\d\d\b", re.I)
RATE_RE = re.compile(r"rate.?limit|too many requests|quota exceeded|"
                     r"x-ratelimit-remaining[\"']?\s*[:=]\s*[\"']?0\b", re.I)
TIMEOUT_RE = re.compile(r"timed?[ -]?out|timeout|deadline exceeded|"
                        r"connection (?:reset|refused)", re.I)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def read_cards(path):
    cards = []
    if not os.path.isfile(path):
        return cards
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                try:
                    cards.append(json.loads(ln))
                except json.JSONDecodeError:
                    pass
    return cards


def detect_empty_result(mat, text):
    """按来源类型判定该响应载荷是否为零命中。返回 evidence 字符串或 None。"""
    sniff = mat.get("sniff")
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if sniff == "crossref" and isinstance(obj, dict):
        msg = obj.get("message") or {}
        if msg.get("total-results") == 0 or msg.get("items") == []:
            return "crossref total-results=%s, items=%s" % (
                msg.get("total-results"), len(msg.get("items") or []))
    if sniff == "europepmc" and isinstance(obj, dict):
        rl = obj.get("resultList") or {}
        if obj.get("hitCount") == 0 or rl.get("result") == []:
            return "europepmc hitCount=%s, result=%s" % (
                obj.get("hitCount"), len(rl.get("result") or []))
    if sniff in ("publisher", "recordlist") :
        if isinstance(obj, list) and not obj:
            return "%s 载荷为空列表" % sniff
        if isinstance(obj, dict):
            for k in ("records", "items", "results"):
                if obj.get(k) == []:
                    return "%s.%s 为空数组" % (sniff, k)
    return None


def main():
    ap = argparse.ArgumentParser(
        description="失败降级台账：分类异常状态并给出处置（exit 0/2/3）。")
    ap.add_argument("--summary", default="/app/work/case_summary.json")
    ap.add_argument("--map-report", default="/app/work/map_report.json")
    ap.add_argument("--cards", default="/app/work/field_cards.jsonl")
    ap.add_argument("--out", default="/app/work/status_ledger.json")
    ap.add_argument("--uncertainty-out", default="/app/work/uncertainty_draft.json")
    args = ap.parse_args()

    if not os.path.isfile(args.summary):
        print("ERROR: case_summary.json 不存在（材料不足，exit 2）: %s"
              % args.summary, file=sys.stderr)
        return 2
    try:
        summary = load_json(args.summary)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print("ERROR: case_summary.json 非法（校验失败，exit 3）: %s" % e,
              file=sys.stderr)
        return 3

    entries = []

    def add(category, file, evidence, disposition, note):
        entries.append({"category": category, "file": file, "evidence": evidence,
                        "disposition": disposition, "note": note})

    # 1) 材料级：零结果 / HTTP 错误 / 超时 / 限流 / 不可解析
    for mat in summary.get("materials", []):
        path = mat.get("path")
        sniff = mat.get("sniff")
        if sniff == "unknown":
            add("unparsed_file", path, "; ".join(mat.get("notes") or []),
                "partial", "该文件不产出字段卡片，覆盖统计按其余来源计算；"
                           "若其为唯一来源证据，须人工确认。")
            continue
        if sniff in ("reference_graph", "import_state"):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            add("unparsed_file", path, "读取失败: %s" % e, "partial",
                "文件不可读，按库不可用处置。")
            continue
        ev = detect_empty_result(mat, text)
        if ev:
            add("empty_result", path, ev, "uncertainty",
                "该来源本次响应零命中：计入覆盖矩阵但该库记录数为 0，"
                "不据此推断文献不存在。")
        m = HTTP_ERR_RE.search(text)
        if m:
            add("http_error", path, "匹配 %r: ...%s..." % (
                m.group(0), text[max(0, m.start() - 40):m.end() + 40].replace("\n", " ")),
                "partial", "材料含 HTTP 错误响应痕迹：该来源本次数据视为不可用快照，"
                           "相应字段覆盖按缺失处理。")
        if RATE_RE.search(text):
            add("rate_limited", path, "匹配限流/配额模式", "partial",
                "材料含限流痕迹：该来源结果可能不完整（截断），覆盖结论注明下限性质。")
        if TIMEOUT_RE.search(text):
            add("timeout", path, "匹配超时模式", "partial",
                "材料含超时痕迹：该来源响应不完整，覆盖结论注明下限性质。")

    # 2) map_report：schema 漂移 / 记录丢弃 / 跳过文件
    if os.path.isfile(args.map_report):
        try:
            mrep = load_json(args.map_report)
        except (json.JSONDecodeError, UnicodeDecodeError):
            mrep = {}
        for d in mrep.get("drift_log", []):
            add("schema_drift", d.get("file"),
                "record[%s] %s" % (d.get("record_index"), d.get("detail")),
                "uncertainty", "字段结构与 references/field_map_*.md 映射表不符，"
                               "已按漂移日志降级处理，必要时人工核对原始载荷。")
        for d in mrep.get("dropped_records", []):
            add("parse_drop", d.get("file"),
                "record[%s] %s" % (d.get("index"), d.get("reason")),
                "uncertainty", "记录级解析失败，未进入覆盖统计；库间对账已计入丢弃数。")
        for s in mrep.get("skipped_files", []):
            if s.get("sniff") not in ("reference_graph", "import_state"):
                add("unparsed_file", s.get("path"), s.get("reason"),
                    "partial", "文件装载失败，逐名留痕。")

    # 3) 撤回/更正标记：单列入结果并标记 status
    cards = read_cards(args.cards)
    seen_clusters = set()
    for c in cards:
        if not c.get("retracted"):
            continue
        ck = c.get("cluster_key")
        if ck in seen_clusters:
            continue
        seen_clusters.add(ck)
        st = (c.get("fields", {}).get("status") or {})
        add("withdrawn_retracted", c.get("source_file"),
            "cluster=%s 标记=%s（来源 %s, item %s）" % (
                ck, st.get("value"), c.get("source"), c.get("item_index")),
            "manual_review",
            "记录含 retracted/withdrawn/correction 标记：在结果中单列并置 "
            "status 字段，是否纳入分析集由人工确认，不得静默剔除。")

    summary_counts = {}
    for e in entries:
        summary_counts[e["category"]] = summary_counts.get(e["category"], 0) + 1

    ledger = {
        "entries": entries,
        "summary": summary_counts,
        "disposition_vocab": {
            "partial": "相应库/文件降级为部分覆盖，status 注明原因",
            "uncertainty": "写入 result.json.uncertainty 供复核",
            "manual_review": "进入人工确认队列，不自动处置",
        },
    }
    uncertainty_draft = [
        "[%s] %s (%s) — %s" % (e["category"], e["note"], e["file"], e["evidence"])
        for e in entries if e["disposition"] in ("uncertainty", "manual_review")
    ]

    for out, payload in ((args.out, ledger), (args.uncertainty_out, uncertainty_draft)):
        d = os.path.dirname(os.path.abspath(out))
        os.makedirs(d, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    print("OK: 状态台账 -> %s (条目=%d, 分类=%s); uncertainty 草稿 %d 条"
          % (args.out, len(entries),
             ",".join("%s=%d" % kv for kv in sorted(summary_counts.items())) or "无",
             len(uncertainty_draft)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("ERROR: status_ledger 未捕获异常（诚实降级，exit 2）: %r" % e,
              file=sys.stderr)
        sys.exit(2)
