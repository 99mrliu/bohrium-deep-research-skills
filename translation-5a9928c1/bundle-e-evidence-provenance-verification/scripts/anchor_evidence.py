#!/usr/bin/env python3
"""anchor_evidence.py — 机器核验每段证据（quote+offset）并统计源文覆盖。

用法: anchor_evidence.py --source source.md --translations translations.json --out evidence_map.json
verdict: verified | offset_mismatch | quote_not_found | overlapping
coverage: 源文本未被任何 quote 覆盖的区间（潜在漏译区，gap）。
exit 0 = 全部 verified 且无 gap；1 = 存在核验失败；2 = 存在 gap（仍输出完整报告）。
"""
import argparse, hashlib, json, sys

def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--translations", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    source = open(a.source, encoding="utf-8", errors="replace").read()
    tr = json.load(open(a.translations, encoding="utf-8"))
    items = tr["segments"] if isinstance(tr, dict) else tr

    segments, intervals = [], []
    for it in items:
        sid = it.get("id")
        ev = it.get("evidence") or {}
        quote = ev.get("quote", "")
        start = ev.get("start")
        verdict, found_at = "quote_not_found", None
        if quote:
            if start is not None:
                if 0 <= start <= len(source) and source[start:start + len(quote)] == quote:
                    verdict, found_at = "verified", start
                else:
                    pos = source.find(quote)
                    if pos >= 0:
                        verdict, found_at = "offset_mismatch", pos
            else:
                pos = source.find(quote)
                if pos >= 0:
                    verdict, found_at = "verified", pos
        segments.append({"id": sid, "verdict": verdict, "quote_sha256": sha(quote) if quote else None,
                         "declared_start": start, "resolved_start": found_at,
                         "span": [found_at, found_at + len(quote)] if found_at is not None else None,
                         "basis": ev.get("basis"), "note": ev.get("note"),
                         "uncertainty": it.get("uncertainty")})
        if found_at is not None:
            intervals.append((found_at, found_at + len(quote), sid))

    # 覆盖区间分析
    intervals.sort()
    overlaps, covered, gaps = [], [], []
    cur = None
    for s, e, sid in intervals:
        if cur and s < cur[1]:
            overlaps.append({"segments": [cur[2], sid], "span": [s, min(e, cur[1])]})
        if cur is None or s > cur[1]:
            if cur:
                covered.append(cur[:2])
            cur = [s, e, sid]
        else:
            cur[1] = max(cur[1], e)
    if cur:
        covered.append(cur[:2])
    prev_end = 0
    for s, e in covered:
        if s > prev_end:
            seg = source[prev_end:s]
            if seg.strip():
                gaps.append({"span": [prev_end, s], "preview": seg.strip()[:120]})
        prev_end = max(prev_end, e)
    if prev_end < len(source):
        seg = source[prev_end:]
        if seg.strip():
            gaps.append({"span": [prev_end, len(source)], "preview": seg.strip()[:120]})

    bad = [s for s in segments if s["verdict"] != "verified"]
    out = {"source_chars": len(source), "source_sha256": sha(source),
           "segments": segments,
           "coverage": {"gaps": gaps, "overlaps": overlaps,
                        "covered_chars": sum(e - s for s, e in covered)},
           "counts": {"verified": len(segments) - len(bad), "failed": len(bad),
                      "gaps": len(gaps), "overlaps": len(overlaps)}}
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"evidence: verified={out['counts']['verified']}/{len(segments)}, "
          f"failed={len(bad)}, gaps={len(gaps)}, overlaps={len(overlaps)} -> {a.out}")
    if bad:
        sys.exit(1)
    if gaps:
        sys.exit(2)
    sys.exit(0)

if __name__ == "__main__":
    main()
