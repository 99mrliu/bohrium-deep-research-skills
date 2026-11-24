#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wording_guard.py — 结论措辞守门器。

用法:
    python3 wording_guard.py --conclusions FILE.md --ledger status.jsonl --out report.json

纪律:
    1. 对台账中状态为 unknown、或未经 register/official_gazette 级来源核验的专利，
       禁止出现确定性法律状态措辞（如「有效专利」「已失效」「仍受保护」「可以自由实施」等）。
       未在台账中出现的专利一律视为未核验。
    2. FTO / 侵权类结论（如「自由实施」「不构成侵权」「无侵权风险」）一律禁止，
       无论状态是否已核验——本技能不作自由实施与侵权结论（超出范围）。

退出码: 0 = 通过; 1 = 存在违规措辞（报告含行号）; 2 = 用法/输入错误。
"""
import argparse
import json
import sys
from pathlib import Path

# 确定性法律状态措辞（仅当涉及专利未经登记级核验时违规）
DEFINITIVE_PHRASES = [
    "有效专利", "已失效", "已经失效", "仍受保护", "仍有效", "仍然有效",
    "保护期内", "已过保护期", "专利权稳定", "权利稳定", "确定有效", "确定无效",
]
# FTO / 侵权结论措辞（一律违规，超出本技能范围）
FTO_PHRASES = [
    "自由实施", "FTO", "不构成侵权", "构成侵权", "无侵权风险", "侵权风险为零",
    "可放心使用", "可以放心使用",
]


def load_ledger_refs(ledger_path):
    """返回 {patent_ref: verified_bool}；verified = 存在 register/official_gazette 级来源的非 unknown 断言。"""
    try:
        lines = Path(ledger_path).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        raise SystemExit(f"[输入错误] ledger 文件不存在: {ledger_path}")
    refs = {}
    register_tiers = {"register", "official_gazette"}
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict):
            continue
        ref = rec.get("patent_ref")
        if not ref:
            continue
        refs.setdefault(ref, False)
        tier = rec.get("_tier")  # 台账本身不含 tier 时由 sources 决定；此处接受可选内联 tier
        if tier in register_tiers and rec.get("asserted_status") not in (None, "unknown"):
            refs[ref] = True
    return refs


def load_ledger_refs_with_sources(ledger_path, sources_path=None):
    """如提供 sources.json，则按来源 tier 判定核验等级；否则退回内联 _tier 字段。"""
    refs = load_ledger_refs(ledger_path)
    if not sources_path:
        return refs
    try:
        raw = json.loads(Path(sources_path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return refs
    entries = raw.get("sources") if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        return refs
    tiers = {}
    for e in entries:
        if isinstance(e, dict) and e.get("source_id"):
            tiers[str(e["source_id"])] = e.get("tier", "unknown")
    register_tiers = {"register", "official_gazette"}
    for raw_line in Path(ledger_path).read_text(encoding="utf-8").splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            rec = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict) or not rec.get("patent_ref"):
            continue
        tier = tiers.get(str(rec.get("source_id")), "unknown")
        if tier in register_tiers and rec.get("asserted_status") not in (None, "unknown"):
            refs[rec["patent_ref"]] = True
    return refs


def find_spans(line, phrase):
    spans, start = [], 0
    while True:
        idx = line.find(phrase, start)
        if idx < 0:
            break
        spans.append((idx, idx + len(phrase)))
        start = idx + 1
    return spans


def scan_phrases(line, phrases):
    """返回命中的措辞列表；短措辞若完全落在已命中的长措辞区间内则去重（如「不构成侵权」吸收「构成侵权」）。"""
    hits, covered = [], []
    for phrase in sorted(phrases, key=len, reverse=True):
        spans = find_spans(line, phrase)
        new_spans = [s for s in spans
                     if not any(s[0] >= c[0] and s[1] <= c[1] for c in covered)]
        if new_spans:
            hits.append(phrase)
            covered.extend(new_spans)
    return hits


def scan(conclusions_path, refs):
    try:
        text = Path(conclusions_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SystemExit(f"[输入错误] conclusions 文件不存在: {conclusions_path}")
    violations = []
    lines = text.splitlines()
    for lineno, line in enumerate(lines, start=1):
        mentioned = [ref for ref in refs if ref in line]
        for phrase in scan_phrases(line, FTO_PHRASES):
            violations.append({
                "line": lineno,
                "text": line.strip(),
                "phrase": phrase,
                "patent_refs": mentioned,
                "kind": "fto_out_of_scope",
                "message": f"FTO/侵权类结论一律禁止（超出本技能范围）：命中「{phrase}」",
            })
        # 确定性措辞：任一涉及专利未核验（或行内无可识别专利号，视为未核验）即违规
        unverified = [r for r in mentioned if not refs.get(r)]
        if not mentioned or unverified:
            for phrase in scan_phrases(line, DEFINITIVE_PHRASES):
                violations.append({
                    "line": lineno,
                    "text": line.strip(),
                    "phrase": phrase,
                    "patent_refs": mentioned,
                    "kind": "definitive_on_unverified",
                    "message": (f"对未在登记级来源核验（或状态为 unknown）的专利使用确定性法律状态措辞："
                                f"命中「{phrase}」"),
                })
    return violations, len(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="结论措辞守门器")
    ap.add_argument("--conclusions", required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--sources", default=None, help="可选：sources.json，用于按来源 tier 判定核验等级")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    try:
        refs = load_ledger_refs_with_sources(args.ledger, args.sources)
        violations, checked = scan(args.conclusions, refs)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 2

    report = {
        "report": "wording_guard",
        "conclusions": args.conclusions,
        "ledger": args.ledger,
        "checked_lines": checked,
        "ledger_refs": {k: ("register_verified" if v else "unverified_or_unknown")
                        for k, v in sorted(refs.items())},
        "ok": not violations,
        "violations": violations,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
