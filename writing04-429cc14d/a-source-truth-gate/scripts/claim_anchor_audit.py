#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claim_anchor_audit.py — 论断-来源锚点审计器。

仅依赖 Python 3.10+ 标准库；无网络访问；确定性输出。

对 claims.jsonl 中每条论断台账记录执行：
  1. source 文件存在性检查（缺失 -> ERROR）；
  2. 将 quote 与来源文本分别做 NFKC + 空白折叠归一化，
     检查 quote 是否为来源文本的子串：
       是 -> PASS（附 char_offset，相对归一化后来源文本）；
       否 -> FAIL，并给出诊断：
         - paraphrase_or_minor_alteration  转述/细微改动冒充逐字引文
         - cross_segment_splice            跨段拼接
         - source_mismatch                 来源中无相近文本（疑似记错出处）

用法：
  python3 claim_anchor_audit.py --sources DIR --ledger claims.jsonl --out DIR

退出码：
  1  存在任何 FAIL / ERROR / 输入级缺陷；
  0  全部 PASS。
"""
import argparse
import difflib
import json
import os
import sys
import unicodedata
from datetime import datetime, timezone

TOOL_NAME = "claim_anchor_audit"
TOOL_VERSION = "1.0.0"
DEFAULT_TIMESTAMP = "1970-01-01T00:00:00Z"

PARAPHRASE_RATIO_THRESHOLD = 0.80
MIN_HALF_LEN = 12

DIAGNOSIS_LABELS = {
    "paraphrase_or_minor_alteration": "转述或细微改动冒充逐字引文",
    "cross_segment_splice": "跨段拼接：引文片段来自来源中不相邻的位置",
    "source_mismatch": "来源中不存在相近文本，疑似记错出处",
}

BASIS_NOTE = (
    "本审计仅依据 --sources 目录中的来源文本文件，未进行任何联网核实；"
    "FAIL 的论断必须修复为逐字引文、改为明确转述，或降级标注为证据不足。"
)


def resolve_timestamp() -> str:
    raw = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
    if not raw:
        return DEFAULT_TIMESTAMP
    if raw.isdigit():
        return datetime.fromtimestamp(int(raw), tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    return raw


def normalize(s: str) -> str:
    """NFKC + 全部空白折叠为单个空格 + 去首尾。"""
    s = unicodedata.normalize("NFKC", s)
    return " ".join(s.split())


def best_window(quote: str, source: str):
    """返回 (window, offset, ratio)：来源中与引文最相似的等长窗口。"""
    if not quote or not source:
        return "", 0, 0.0
    sm = difflib.SequenceMatcher(None, quote, source, autojunk=False)
    m = sm.find_longest_match(0, len(quote), 0, len(source))
    # 以最长公共块为锚，对齐引文起点，截取与引文等长的窗口。
    start = m.b - m.a
    start = max(0, min(start, max(0, len(source) - len(quote))))
    window = source[start:start + len(quote)]
    ratio = difflib.SequenceMatcher(None, quote, window, autojunk=False).ratio()
    return window, start, ratio


def splice_check(quote: str, source: str) -> bool:
    """引文前后两半分别命中来源中相距甚远的位置 -> 疑似跨段拼接。"""
    if len(quote) < 2 * MIN_HALF_LEN:
        return False
    mid = len(quote) // 2
    # 尽量在空格处切分，避免切断词语
    cut = quote.rfind(" ", MIN_HALF_LEN, len(quote) - MIN_HALF_LEN)
    if cut == -1:
        cut = mid
    first, second = quote[:cut].strip(), quote[cut:].strip()
    if len(first) < MIN_HALF_LEN or len(second) < MIN_HALF_LEN:
        return False
    p1, p2 = source.find(first), source.find(second)
    if p1 == -1 or p2 == -1:
        return False
    gap = (p2 - (p1 + len(first))) if p2 >= p1 else (p1 - (p2 + len(second)))
    return gap > 10


def diagnose(quote: str, source: str):
    """FAIL 诊断：返回 (diagnosis, evidence_dict)。"""
    window, offset, ratio = best_window(quote, source)
    evidence = {
        "best_window_offset": offset,
        "best_window_similarity": round(ratio, 4),
        "closest_window_60": window[:60] + ("…" if len(window) > 60 else ""),
    }
    if ratio >= PARAPHRASE_RATIO_THRESHOLD:
        return "paraphrase_or_minor_alteration", evidence
    if splice_check(quote, source):
        return "cross_segment_splice", evidence
    return "source_mismatch", evidence


def audit_record(rec: dict, sources_dir: str, cache: dict) -> dict:
    out = {
        "id": rec.get("id"),
        "claim": rec.get("claim"),
        "source": rec.get("source"),
        "status": None,
        "char_offset": None,
        "diagnosis": None,
        "evidence": {},
    }
    src_name = rec.get("source")
    quote = rec.get("quote")
    if not isinstance(src_name, str) or not src_name.strip():
        out["status"] = "ERROR"
        out["diagnosis"] = "missing_source_field"
        return out
    if not isinstance(quote, str) or not quote.strip():
        out["status"] = "ERROR"
        out["diagnosis"] = "missing_quote_field"
        return out

    # 防止路径逃逸：仅允许 --sources 目录内的相对文件名
    safe_rel = os.path.normpath(src_name).lstrip(os.sep)
    if safe_rel.startswith(".."):
        out["status"] = "ERROR"
        out["diagnosis"] = "source_path_escapes_sources_dir"
        return out
    src_path = os.path.join(sources_dir, safe_rel)
    if not os.path.isfile(src_path):
        out["status"] = "ERROR"
        out["diagnosis"] = "source_file_not_found"
        return out

    if src_path not in cache:
        try:
            with open(src_path, "r", encoding="utf-8") as f:
                cache[src_path] = f.read()
        except (OSError, UnicodeDecodeError) as exc:
            out["status"] = "ERROR"
            out["diagnosis"] = f"source_unreadable: {exc}"
            return out
    norm_source = normalize(cache[src_path])
    norm_quote = normalize(quote)

    idx = norm_source.find(norm_quote)
    if idx != -1:
        out["status"] = "PASS"
        out["char_offset"] = idx
        locator = rec.get("locator")
        if isinstance(locator, str) and locator.strip():
            out["evidence"]["locator"] = locator
            out["evidence"]["locator_found_in_source"] = \
                normalize(locator) in norm_source
        return out

    out["status"] = "FAIL"
    diagnosis, evidence = diagnose(norm_quote, norm_source)
    out["diagnosis"] = diagnosis
    out["evidence"] = evidence
    out["evidence"]["diagnosis_label"] = DIAGNOSIS_LABELS.get(diagnosis, diagnosis)
    return out


def render_markdown(report: dict) -> str:
    lines = []
    lines.append("# 论断-来源锚点审计报告（claim_anchor_audit）")
    lines.append("")
    lines.append(f"- 生成时间（UTC）：{report['generated_utc']}")
    lines.append(f"- 来源目录：`{report['sources_dir']}`")
    lines.append(f"- 台账文件：`{report['ledger_file']}`")
    lines.append(f"- 审计依据：{BASIS_NOTE}")
    lines.append("")
    s = report["summary"]
    lines.append(f"## 汇总：PASS {s['pass']} / FAIL {s['fail']} / ERROR {s['error']}（共 {s['total']} 条）")
    lines.append("")
    lines.append("| id | 状态 | 诊断 | char_offset |")
    lines.append("| --- | --- | --- | --- |")
    for r in report["results"]:
        lines.append(
            f"| {r['id']} | {r['status']} | {r.get('diagnosis') or ''} "
            f"| {r['char_offset'] if r['char_offset'] is not None else ''} |")
    lines.append("")
    lines.append("## 逐条明细")
    lines.append("")
    for r in report["results"]:
        lines.append(f"### {r['id']} — {r['status']}")
        lines.append("")
        lines.append(f"- 论断：{r.get('claim')}")
        lines.append(f"- 来源文件：`{r.get('source')}`")
        if r["status"] == "PASS":
            lines.append(f"- 锚点偏移（归一化文本）：{r['char_offset']}")
            ev = r.get("evidence") or {}
            if "locator_found_in_source" in ev:
                lines.append(f"- 定位符 `{ev.get('locator')}` 是否见于来源："
                             f"{ev['locator_found_in_source']}")
        else:
            lines.append(f"- 诊断：{r.get('diagnosis')}"
                         f"（{(r.get('evidence') or {}).get('diagnosis_label', '')}）")
            ev = r.get("evidence") or {}
            if "closest_window_60" in ev:
                lines.append(f"- 最接近窗口（前 60 字符）：{ev['closest_window_60']}")
                lines.append(f"- 窗口相似度：{ev.get('best_window_similarity')}"
                             f"（偏移 {ev.get('best_window_offset')}）")
        lines.append("")
    lines.append("---")
    lines.append("免责声明：FAIL/ERROR 记录对应的论断-引用关系不得原样进入成品；"
                 "必须修复为逐字引文、改写为明确转述，或标注证据不足。")
    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="审计论断台账中每条引文是否逐字锚定于来源文本（仅标准库）。")
    parser.add_argument("--sources", required=True, help="纯文本来源文件目录")
    parser.add_argument("--ledger", required=True, help="claims.jsonl 路径")
    parser.add_argument("--out", required=True, help="输出目录")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.sources):
        print(f"[claim_anchor_audit] ERROR: --sources 不是有效目录: {args.sources}",
              file=sys.stderr)
        return 1
    if not os.path.isfile(args.ledger):
        print(f"[claim_anchor_audit] ERROR: --ledger 文件不存在: {args.ledger}",
              file=sys.stderr)
        return 1

    results = []
    cache = {}
    with open(args.ledger, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                results.append({
                    "id": f"__line_{lineno}", "claim": None, "source": None,
                    "status": "ERROR",
                    "diagnosis": f"json_decode_error: {exc}",
                    "char_offset": None, "evidence": {"raw_line": line[:200]}})
                continue
            if not isinstance(rec, dict):
                results.append({
                    "id": f"__line_{lineno}", "claim": None, "source": None,
                    "status": "ERROR", "diagnosis": "ledger_line_not_an_object",
                    "char_offset": None, "evidence": {}})
                continue
            results.append(audit_record(rec, args.sources, cache))

    n_pass = sum(1 for r in results if r["status"] == "PASS")
    n_fail = sum(1 for r in results if r["status"] == "FAIL")
    n_err = sum(1 for r in results if r["status"] == "ERROR")
    report = {
        "tool": TOOL_NAME,
        "version": TOOL_VERSION,
        "generated_utc": resolve_timestamp(),
        "audit_basis": BASIS_NOTE,
        "sources_dir": args.sources,
        "ledger_file": args.ledger,
        "summary": {"total": len(results), "pass": n_pass,
                    "fail": n_fail, "error": n_err},
        "results": results,
    }

    try:
        os.makedirs(args.out, exist_ok=True)
        jpath = os.path.join(args.out, "anchor_report.json")
        mpath = os.path.join(args.out, "anchor_report.md")
        with open(jpath, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
            f.write("\n")
        with open(mpath, "w", encoding="utf-8") as f:
            f.write(render_markdown(report))
    except OSError as exc:
        print(f"[claim_anchor_audit] ERROR: 无法写出报告: {exc}", file=sys.stderr)
        return 1

    print(
        f"[claim_anchor_audit] 共 {len(results)} 条：PASS={n_pass} "
        f"FAIL={n_fail} ERROR={n_err} -> {args.out}"
    )
    if n_fail or n_err:
        print(f"[claim_anchor_audit] 检出 {n_fail + n_err} 条未通过锚点审计的记录，退出码 1。",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
