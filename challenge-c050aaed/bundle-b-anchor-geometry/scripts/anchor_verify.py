#!/usr/bin/env python3
"""anchor_verify.py -- independent second-pass verification of resolved anchors.

For every resolved anchor this script RE-CLIPS the recorded bbox against the raw
word boxes using a DIFFERENT rule than anchor_resolve.py (word-center-inside-bbox
instead of >0.5 area overlap), rebuilds the text in column-aware reading order,
and string-compares it against the recorded anchored_text after normalization
(Unicode NFKC + curly-quote/dash folding + whitespace collapse; case preserved)
using difflib.SequenceMatcher ratio.

Classification per anchor:
  exact       ratio >= 0.99
  normalized  ratio >= 0.90
  drifted     ratio >= 0.60
  failed      ratio <  0.60
  skipped     anchor has no geometry result to check (empty_match, no_words_file,
              failed upstream, missing page words)

Outputs verify_report.json: per-anchor table + overall counts and rates.
Rates are computed over classified (non-skipped) anchors.

Exit codes: 0 = no failed anchor, 2 = fatal, 3 = at least one anchor failed.
Python 3 stdlib only. Deterministic.
"""

import argparse
import difflib
import json
import os
import sys
import unicodedata

# Reuse the same page-geometry conventions as anchor_resolve (kept in-file so
# this script stays self-contained): MIN_GUTTER, column_splits, reading_order.
MIN_GUTTER = 8.0
LINE_TOL_FACTOR = 0.6

_FOLD = {ord("\u2018"): "'", ord("\u2019"): "'", ord("\u201c"): '"',
         ord("\u201d"): '"', ord("\u2013"): "-", ord("\u2014"): "-",
         ord("\u2026"): "..."}


def norm(s):
    s = unicodedata.normalize("NFKC", s or "")
    s = s.translate(_FOLD)
    return " ".join(s.split())


def load_words(path):
    words = []
    with open(path, encoding="utf-8") as fh:
        for ln, raw in enumerate(fh, 1):
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 5:
                raise ValueError("%s:%d: need >= 5 tab-separated fields" % (path, ln))
            x0, y0, x1, y1 = (float(v) for v in parts[1:5])
            origin = parts[5].strip() if len(parts) > 5 and parts[5].strip() else "text"
            words.append({"i": len(words), "w": parts[0], "x0": x0, "y0": y0,
                          "x1": x1, "y1": y1, "origin": origin})
    return words


def page_file(pages_dir, fname, page):
    return os.path.join(pages_dir, fname, "page-%03d.words.tsv" % page)


def median(xs):
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def column_splits(words, min_gutter=MIN_GUTTER):
    lo = min(w["x0"] for w in words)
    hi = max(w["x1"] for w in words)
    n = int(hi - lo) + 3
    cov = [0] * n
    for w in words:
        a = int(w["x0"] - lo)
        b = int(w["x1"] - lo) + 1
        for k in range(max(a, 0), min(b, n)):
            cov[k] += 1
    covered = [k for k in range(n) if cov[k] > 0]
    if not covered:
        return []
    first, last = covered[0], covered[-1]
    splits, run = [], None
    for k in range(first, last + 1):
        if cov[k] == 0:
            if run is None:
                run = k
        else:
            if run is not None and (k - run) >= min_gutter:
                splits.append(lo + (run + k) / 2.0)
            run = None
    return splits


def reading_order(words, splits):
    if not words:
        return []
    mh = median([w["y1"] - w["y0"] for w in words]) or 1.0
    tol = LINE_TOL_FACTOR * mh

    def col(w):
        cx = 0.5 * (w["x0"] + w["x1"])
        return sum(1 for s in splits if cx > s)

    lines = []
    for w in sorted(words, key=lambda a: (col(a), a["y0"], a["x0"])):
        c = col(w)
        if lines and lines[-1][0] == c and abs(w["y0"] - lines[-1][1]) <= tol:
            lines[-1][2].append(w)
        else:
            lines.append([c, w["y0"], [w]])
    lines.sort(key=lambda L: (L[0], L[1]))
    out = []
    for _, _, ws in lines:
        out.extend(sorted(ws, key=lambda a: a["x0"]))
    return out


def mark_rects(rec):
    """The mark's per-quad rects (from recorded quadpoints) or its single bbox."""
    q = rec.get("quadpoints")
    if q and len(q) % 8 == 0:
        rects = []
        for k in range(0, len(q), 8):
            xs = [q[k], q[k + 2], q[k + 4], q[k + 6]]
            ys = [q[k + 1], q[k + 3], q[k + 5], q[k + 7]]
            rects.append((min(xs), min(ys), max(xs), max(ys)))
        return rects
    return [tuple(rec["bbox"])] if rec.get("bbox") else []


def reclip_text(words, splits, rects):
    """Independent rule: a word counts iff its box CENTER lies inside a mark rect.
    Multi-rect marks are concatenated in rect order (mirrors quad order)."""
    sel, seen = [], set()
    for r in rects:
        hit = [w for w in words
               if r[0] <= 0.5 * (w["x0"] + w["x1"]) <= r[2]
               and r[1] <= 0.5 * (w["y0"] + w["y1"]) <= r[3]]
        for w in reading_order(hit, splits):
            if w["i"] not in seen:
                seen.add(w["i"])
                sel.append(w)
    return " ".join(w["w"] for w in sel), len(sel)


def classify(ratio):
    if ratio >= 0.99:
        return "exact"
    if ratio >= 0.90:
        return "normalized"
    if ratio >= 0.60:
        return "drifted"
    return "failed"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Independently re-verify every resolved anchor: re-clip the recorded "
                    "bbox with a center-inside rule and difflib-compare against the "
                    "recorded anchored_text. Exit 3 if any anchor classifies 'failed'.")
    ap.add_argument("--resolved", required=True, help="resolved.jsonl (or corrected.jsonl)")
    ap.add_argument("--pages-dir", required=True, help="pages/ directory with words TSVs")
    ap.add_argument("--out", required=True, help="verify_report.json output")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.resolved):
        print("FATAL: resolved file not found: %s" % args.resolved, file=sys.stderr)
        return 2
    if not os.path.isdir(args.pages_dir):
        print("FATAL: pages dir not found: %s" % args.pages_dir, file=sys.stderr)
        return 2

    try:
        recs = [json.loads(raw) for raw in open(args.resolved, encoding="utf-8") if raw.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        print("FATAL: cannot read %s: %s" % (args.resolved, exc), file=sys.stderr)
        return 2

    cache, rows, counts = {}, [], {"exact": 0, "normalized": 0, "drifted": 0,
                                   "failed": 0, "skipped": 0}
    try:
        for rec in recs:
            row = {"annotation_id": rec.get("annotation_id"), "file": rec.get("file"),
                   "page": rec.get("page"), "anchor_kind": rec.get("anchor_kind"),
                   "resolve_status": rec.get("status")}
            if (rec.get("status") != "resolved" or not rec.get("bbox")
                    or not rec.get("word_indices")):
                row.update(cls="skipped", ratio=None, note="nothing to re-verify")
                counts["skipped"] += 1
                rows.append(row)
                continue
            key = (rec.get("file"), rec.get("page"))
            if key not in cache:
                path = page_file(args.pages_dir, *key)
                cache[key] = load_words(path) if os.path.isfile(path) else None
            words = cache[key]
            if not words:
                row.update(cls="skipped", ratio=None, note="page words unavailable")
                counts["skipped"] += 1
                rows.append(row)
                continue
            splits = column_splits(words)
            text, n = reclip_text(words, splits, mark_rects(rec))
            ratio = difflib.SequenceMatcher(
                None, norm(rec.get("anchored_text", "")), norm(text)).ratio()
            cls = classify(ratio)
            row.update(cls=cls, ratio=round(ratio, 6),
                       recorded_text=rec.get("anchored_text"), reclip_text=text,
                       n_words_recorded=len(rec.get("word_indices")), n_words_reclip=n)
            counts[cls] += 1
            rows.append(row)
    except (OSError, ValueError) as exc:
        print("FATAL: %s" % exc, file=sys.stderr)
        return 2

    classified = sum(counts[k] for k in ("exact", "normalized", "drifted", "failed"))
    rates = {k: (round(counts[k] / classified, 4) if classified else None)
             for k in ("exact", "normalized", "drifted", "failed")}
    report = {"input": os.path.basename(args.resolved),
              "summary": dict({"total": len(rows), "classified": classified}, **counts,
                              **{"%s_rate" % k: v for k, v in rates.items()}),
              "anchors": rows}
    try:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
    except OSError as exc:
        print("FATAL: cannot write %s: %s" % (args.out, exc), file=sys.stderr)
        return 2

    print("%-12s %-6s %-8s %s" % ("annotation", "page", "ratio", "class"))
    for r in rows:
        print("%-12s %-6s %-8s %s" % (r.get("annotation_id"), r.get("page"),
                                      r.get("ratio"), r.get("cls")))
    print("summary: %s" % json.dumps(report["summary"], sort_keys=True))
    return 3 if counts["failed"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
