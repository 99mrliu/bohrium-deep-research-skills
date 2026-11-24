#!/usr/bin/env python3
"""drift_correct.py -- fuzzy re-anchoring for OCR-origin pages or drifted anchors.

Which anchors are processed:
  * anchor_kind is "quad" or "rect" (quote-type marks; FreeText/nearest_block
    margin notes are NOT quotes of page text and are skipped), AND
  * the page has any ocr-origin words (page_origin "ocr"/"mixed") OR the record
    carries drift_suspected=true (coverage < 0.5 from anchor_resolve).

How it works per processed anchor:
  1. Target text = the annotation's recorded `contents` (the quote the user
     intended) if non-empty, else the recorded anchored_text.
  2. Re-clip the recorded bbox (word-center-inside rule). If the normalized
     re-clip equals the normalized target, the anchor is fine: status "ok".
  3. Otherwise slide a best-match search: candidate windows of (n-1, n, n+1)
     consecutive words (n = target word count) over the page's words in
     column-aware reading order, scored by difflib.SequenceMatcher ratio on
     normalized strings (NFKC + quote/dash folding + whitespace collapse).
  4. best ratio >= 0.75  -> re-anchor: bbox/word_indices/anchored_text are
     replaced by the winning window; correction.status = "corrected" with
     old_bbox, new_bbox and ratio recorded.
     best ratio <  0.75  -> correction.status = "unrecoverable". The record is
     left untouched. This is an honest dead end; the text is NEVER guessed.

Every input record is written to the output, processed or not, with a
"correction" object appended (audit trail). Original metadata is preserved.

Exit codes: 0 = no unrecoverable anchor, 2 = fatal, 3 = >=1 unrecoverable.
Python 3 stdlib only. Deterministic (ties broken by first window in scan order).
"""

import argparse
import difflib
import json
import math
import os
import sys
import unicodedata

REANCHOR_THRESHOLD = 0.75
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
    n = int(math.ceil(hi - lo)) + 2
    cov = [0] * n
    for w in words:
        a = int(math.floor(w["x0"] - lo))
        b = int(math.ceil(w["x1"] - lo))
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


def reclip(words, splits, rects):
    sel, seen = [], set()
    for r in rects:
        hit = [w for w in words
               if r[0] <= 0.5 * (w["x0"] + w["x1"]) <= r[2]
               and r[1] <= 0.5 * (w["y0"] + w["y1"]) <= r[3]]
        for w in reading_order(hit, splits):
            if w["i"] not in seen:
                seen.add(w["i"])
                sel.append(w)
    return sel


def process(rec, words):
    """Return (correction dict, possibly-updated record)."""
    splits = column_splits(words)
    ordered = reading_order(words, splits)
    target = (rec.get("contents") or "").strip()
    target_source = "contents"
    if not target:
        target = (rec.get("anchored_text") or "").strip()
        target_source = "anchored_text"
    if not target:
        return {"status": "unrecoverable", "reason": "no contents or anchored_text "
                "to use as re-anchor target"}, rec
    current = reclip(words, splits, mark_rects(rec))
    current_text = " ".join(w["w"] for w in current)
    if norm(current_text) == norm(target):
        return {"status": "ok", "ratio": 1.0, "target_source": target_source}, rec

    n = max(1, len(target.split()))
    sizes = sorted({max(1, n - 1), n, n + 1})
    best_r, best_win = -1.0, None
    ntarget = norm(target)
    for size in sizes:
        for start in range(0, len(ordered) - size + 1):
            win = ordered[start:start + size]
            cand = norm(" ".join(w["w"] for w in win))
            r = difflib.SequenceMatcher(None, ntarget, cand).ratio()
            if r > best_r:
                best_r, best_win = r, win
    if best_r >= REANCHOR_THRESHOLD and best_win:
        old_bbox = list(rec["bbox"])
        new_bbox = [min(w["x0"] for w in best_win), min(w["y0"] for w in best_win),
                    max(w["x1"] for w in best_win), max(w["y1"] for w in best_win)]
        out = dict(rec)
        out["bbox"] = new_bbox
        # keep the mark geometry consistent with the new anchor
        out["quadpoints"] = [new_bbox[0], new_bbox[1], new_bbox[2], new_bbox[1],
                             new_bbox[2], new_bbox[3], new_bbox[0], new_bbox[3]]
        out["word_indices"] = [w["i"] for w in best_win]
        out["anchored_text"] = " ".join(w["w"] for w in best_win)
        out["drift_suspected"] = False
        corr = {"status": "corrected", "ratio": round(best_r, 6),
                "old_bbox": old_bbox, "new_bbox": new_bbox,
                "old_anchored_text": rec.get("anchored_text"),
                "target_source": target_source}
        return corr, out
    corr = {"status": "unrecoverable", "best_ratio": round(best_r, 6),
            "threshold": REANCHOR_THRESHOLD, "target_source": target_source,
            "reason": "best fuzzy window below threshold; not re-anchored (never guess)"}
    return corr, rec


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Fuzzy re-anchor OCR/drifted anchors: slide difflib-scored word "
                    "windows; re-anchor at ratio>=0.75, else honestly mark unrecoverable. "
                    "Exit 3 if any anchor stays unrecoverable.")
    ap.add_argument("--resolved", required=True, help="resolved.jsonl input")
    ap.add_argument("--pages-dir", required=True, help="pages/ directory with words TSVs")
    ap.add_argument("--out", required=True, help="corrected.jsonl output")
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

    cache, out_recs, counts = {}, [], {}
    try:
        for rec in recs:
            out = dict(rec)
            corr = None
            if rec.get("status") != "resolved":
                corr = {"status": "skipped", "reason": "upstream status=%s" % rec.get("status")}
            elif rec.get("anchor_kind") not in ("quad", "rect"):
                corr = {"status": "skipped",
                        "reason": "anchor_kind=%s is not a page-text quote" % rec.get("anchor_kind")}
            elif not (rec.get("page_origin") in ("ocr", "mixed") or rec.get("drift_suspected")):
                corr = {"status": "not_checked",
                        "reason": "born-digital text layer, no drift suspected"}
            else:
                key = (rec.get("file"), rec.get("page"))
                if key not in cache:
                    path = page_file(args.pages_dir, *key)
                    cache[key] = load_words(path) if os.path.isfile(path) else None
                words = cache[key]
                if not words:
                    corr = {"status": "unrecoverable", "reason": "page words unavailable"}
                else:
                    corr, out = process(rec, words)
            out["correction"] = corr
            counts[corr["status"]] = counts.get(corr["status"], 0) + 1
            out_recs.append(out)
    except (OSError, ValueError) as exc:
        print("FATAL: %s" % exc, file=sys.stderr)
        return 2

    try:
        with open(args.out, "w", encoding="utf-8") as fh:
            for rec in out_recs:
                fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError as exc:
        print("FATAL: cannot write %s: %s" % (args.out, exc), file=sys.stderr)
        return 2

    print("drift_correct: %d records -> %s" % (len(out_recs), args.out))
    for k in sorted(counts):
        print("  correction=%s: %d" % (k, counts[k]))
    for rec in out_recs:
        c = rec["correction"]
        if c["status"] in ("corrected", "unrecoverable"):
            print("  %s: %s ratio=%s old_bbox=%s new_bbox=%s"
                  % (rec.get("annotation_id"), c["status"],
                     c.get("ratio", c.get("best_ratio")),
                     c.get("old_bbox", rec.get("bbox")), c.get("new_bbox")))
    return 3 if counts.get("unrecoverable") else 0


if __name__ == "__main__":
    sys.exit(main())
