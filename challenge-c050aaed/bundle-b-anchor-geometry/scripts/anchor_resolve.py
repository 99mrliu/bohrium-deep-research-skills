#!/usr/bin/env python3
"""anchor_resolve.py -- resolve raw annotation marks to exact page text by geometry.

Inputs:
  --annotations  annotations.jsonl  (one JSON object per line; see references/anchor_schema.json)
  --pages-dir    pages/             (pages/<file>/page-NNN.words.tsv word boxes)
  --out          resolved.jsonl

WORD-INSIDE-QUAD RULE (the single documented rule, strict):
  A word belongs to a quad iff  area(word_box INTERSECT quad_bbox) / area(word_box) > 0.5.
  Exactly 0.5 is EXCLUDED. Each quad is reduced to its axis-aligned bounding rect
  (min/max of its 4 points), so PDF quad point order does not matter.

MULTI-QUAD: quads are processed in file order; matched words are concatenated in
quad order (a word already claimed by an earlier quad is not repeated).

TWO-COLUMN REPAIR: column gutters are detected from the x-projection of ALL word
boxes on the page (a zero-coverage horizontal band >= MIN_GUTTER units wide, with
covered words on both sides, is a column gutter). Words are grouped into lines
within each column and sorted (column, line_y, x0) before joining, so marked text
reads in correct reading order even when the words file is stored interleaved.

MARKS WITHOUT QUADS (e.g. FreeText margin notes): anchored to the nearest text
block (line) by euclidean distance from the mark rect center; anchor_kind is
"nearest_block" and the distance is recorded.

Exit codes: 0 = ran to completion (per-anchor problems are recorded in-band),
            2 = fatal (unreadable inputs / bad arguments).
Python 3 stdlib only. Deterministic.
"""

import argparse
import json
import math
import os
import sys

MIN_GUTTER = 8.0          # min zero-coverage band width (coordinate units) = column gutter
LINE_TOL_FACTOR = 0.6     # line grouping tolerance = factor * median word height


# ---------------------------------------------------------------- words TSV --

def load_words(path):
    """Load page-NNN.words.tsv: word \t x0 \t y0 \t x1 \t y1 [\t origin \t confidence]."""
    words = []
    with open(path, encoding="utf-8") as fh:
        for ln, raw in enumerate(fh, 1):
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 5:
                raise ValueError("%s:%d: need >= 5 tab-separated fields" % (path, ln))
            try:
                x0, y0, x1, y1 = (float(v) for v in parts[1:5])
            except ValueError:
                raise ValueError("%s:%d: non-numeric coordinates" % (path, ln))
            origin = parts[5].strip() if len(parts) > 5 and parts[5].strip() else "text"
            conf = None
            if len(parts) > 6 and parts[6].strip():
                try:
                    conf = float(parts[6])
                except ValueError:
                    conf = None
            words.append({"i": len(words), "w": parts[0], "x0": x0, "y0": y0,
                          "x1": x1, "y1": y1, "origin": origin, "conf": conf})
    return words


def page_file(pages_dir, fname, page):
    return os.path.join(pages_dir, fname, "page-%03d.words.tsv" % page)


# ------------------------------------------------------------- geometry -----

def inter_area(a, b):
    dx = min(a[2], b[2]) - max(a[0], b[0])
    dy = min(a[3], b[3]) - max(a[1], b[1])
    return dx * dy if dx > 0 and dy > 0 else 0.0


def bbox_of(words):
    return [min(w["x0"] for w in words), min(w["y0"] for w in words),
            max(w["x1"] for w in words), max(w["y1"] for w in words)]


def wbox(w):
    return (w["x0"], w["y0"], w["x1"], w["y1"])


def median(xs):
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def column_splits(words, min_gutter=MIN_GUTTER):
    """Return x-coordinates of column gutters via the x-projection profile.

    A gutter is a run of x with zero word coverage, at least min_gutter wide,
    that has covered words on BOTH sides (page margins are ignored).
    """
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
    splits = []
    run = None
    for k in range(first, last + 1):
        if cov[k] == 0:
            if run is None:
                run = k
        else:
            if run is not None and (k - run) >= min_gutter:
                splits.append(lo + (run + k) / 2.0)
            run = None
    return splits


def column_of(w, splits):
    cx = 0.5 * (w["x0"] + w["x1"])
    return sum(1 for s in splits if cx > s)


def build_lines(words, splits):
    """Group words into (column, y) lines; return list of line dicts."""
    if not words:
        return []
    mh = median([w["y1"] - w["y0"] for w in words]) or 1.0
    tol = LINE_TOL_FACTOR * mh
    lines = []
    for w in sorted(words, key=lambda a: (column_of(a, splits), a["y0"], a["x0"])):
        c = column_of(w, splits)
        if lines and lines[-1]["col"] == c and abs(w["y0"] - lines[-1]["y0"]) <= tol:
            L = lines[-1]
            L["words"].append(w)
            L["x0"] = min(L["x0"], w["x0"]); L["x1"] = max(L["x1"], w["x1"])
            L["y0"] = min(L["y0"], w["y0"]); L["y1"] = max(L["y1"], w["y1"])
        else:
            lines.append({"col": c, "words": [w],
                          "x0": w["x0"], "y0": w["y0"], "x1": w["x1"], "y1": w["y1"]})
    for L in lines:
        L["words"].sort(key=lambda a: a["x0"])
    return lines


def reading_order(words, splits):
    """Sort words into (column, line_y, x0) reading order."""
    lines = build_lines(words, splits)
    lines.sort(key=lambda L: (L["col"], L["y0"]))
    out = []
    for L in lines:
        out.extend(L["words"])
    return out


def quads_from(ann):
    """Return list of quad bounding rects from quadpoints (flat, multiple of 8)
    or from a single rect [x0,y0,x1,y1]. None if the mark has no area geometry."""
    q = ann.get("quadpoints")
    if q:
        if len(q) % 8 != 0:
            raise ValueError("quadpoints length %d is not a multiple of 8" % len(q))
        rects = []
        for k in range(0, len(q), 8):
            xs = [q[k], q[k + 2], q[k + 4], q[k + 6]]
            ys = [q[k + 1], q[k + 3], q[k + 5], q[k + 7]]
            rects.append((min(xs), min(ys), max(xs), max(ys)))
        return rects
    r = ann.get("rect")
    if r and ann.get("type") not in ("FreeText",):
        return [(r[0], r[1], r[2], r[3])]
    return None


def page_origin(words):
    origins = {w["origin"] for w in words}
    if origins == {"text"}:
        return "text"
    if origins == {"ocr"}:
        return "ocr"
    return "mixed"


# ---------------------------------------------------------------- resolve ---

def resolve_quad_mark(ann, words, splits, quads):
    matched, seen = [], set()
    for q in quads:
        qm = [w for w in words
              if inter_area(wbox(w), q) / ((w["x1"] - w["x0"]) * (w["y1"] - w["y0"]) or 1e-9) > 0.5]
        for w in reading_order(qm, splits):
            if w["i"] not in seen:
                seen.add(w["i"])
                matched.append(w)
    quad_area = sum((q[2] - q[0]) * (q[3] - q[1]) for q in quads) or 1e-9
    cov_num = sum(inter_area(wbox(w), q) for w in matched for q in quads)
    coverage = min(1.0, cov_num / quad_area)
    return matched, coverage


def resolve_nearest_block(ann, words, splits):
    r = ann.get("rect")
    if not r:
        return None
    cx, cy = 0.5 * (r[0] + r[2]), 0.5 * (r[1] + r[3])
    best, best_d = None, None
    for L in build_lines(words, splits):
        dx = max(L["x0"] - cx, 0.0, cx - L["x1"])
        dy = max(L["y0"] - cy, 0.0, cy - L["y1"])
        d = math.hypot(dx, dy)
        if best_d is None or d < best_d:
            best, best_d = L, d
    return best, best_d


def resolve_annotation(ann, pages_dir, cache):
    rec = dict(ann)  # preserve ALL original metadata (type, category, color_rgb, ...)
    fname, page = ann.get("file"), ann.get("page")
    if fname is None or page is None:
        rec.update(status="failed", error="annotation missing 'file' or 'page'")
        return rec
    key = (fname, page)
    if key not in cache:
        path = page_file(pages_dir, fname, page)
        if os.path.isfile(path):
            cache[key] = load_words(path)
        else:
            cache[key] = None
    words = cache[key]
    if words is None:
        rec.update(status="no_words_file", anchor_kind=None, anchored_text=None,
                   error="words TSV not found: %s" % page_file(pages_dir, fname, page))
        return rec
    if not words:
        rec.update(status="failed", error="words TSV is empty")
        return rec

    splits = column_splits(words)
    rec["column_count"] = len(splits) + 1
    if splits:
        rec["column_gutters_x"] = [round(s, 3) for s in splits]
    rec["page_origin"] = page_origin(words)

    try:
        quads = quads_from(ann)
    except ValueError as exc:
        rec.update(status="failed", error=str(exc))
        return rec

    if quads:
        matched, coverage = resolve_quad_mark(ann, words, splits, quads)
        rec["anchor_kind"] = "quad" if ann.get("quadpoints") else "rect"
        rec["quad_count"] = len(quads)
        rec["bbox"] = [min(q[0] for q in quads), min(q[1] for q in quads),
                       max(q[2] for q in quads), max(q[3] for q in quads)]
        rec["coverage"] = round(coverage, 6)
        rec["word_indices"] = [w["i"] for w in matched]
        rec["anchored_text"] = " ".join(w["w"] for w in matched)
        rec["drift_suspected"] = bool(matched) and coverage < 0.5
        rec["status"] = "resolved" if matched else "empty_match"
        if not matched:
            rec["error"] = "no word box passed the >0.5 overlap rule for any quad"
    else:
        nb = resolve_nearest_block(ann, words, splits)
        if nb is None:
            rec.update(status="failed", anchor_kind=None,
                       error="mark has neither quadpoints nor rect; cannot anchor")
            return rec
        L, d = nb
        rec["anchor_kind"] = "nearest_block"
        rec["anchor_distance"] = round(d, 3)
        rec["bbox"] = [L["x0"], L["y0"], L["x1"], L["y1"]]
        rec["word_indices"] = [w["i"] for w in L["words"]]
        rec["anchored_text"] = " ".join(w["w"] for w in L["words"])
        rec["coverage"] = None
        rec["status"] = "resolved"
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Resolve annotation marks to exact page text via quad/word geometry, "
                    "with two-column reading-order repair. Rule: a word is marked iff "
                    ">0.5 of its box area lies inside a quad rect.")
    ap.add_argument("--annotations", required=True, help="annotations.jsonl input")
    ap.add_argument("--pages-dir", required=True, help="pages/ directory with words TSVs")
    ap.add_argument("--out", required=True, help="resolved.jsonl output")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.annotations):
        print("FATAL: annotations file not found: %s" % args.annotations, file=sys.stderr)
        return 2
    if not os.path.isdir(args.pages_dir):
        print("FATAL: pages dir not found: %s" % args.pages_dir, file=sys.stderr)
        return 2

    cache, results, counts = {}, [], {}
    try:
        with open(args.annotations, encoding="utf-8") as fh:
            for ln, raw in enumerate(fh, 1):
                if not raw.strip():
                    continue
                try:
                    ann = json.loads(raw)
                except json.JSONDecodeError as exc:
                    results.append({"status": "failed", "error": "bad JSON line %d: %s" % (ln, exc)})
                    continue
                rec = resolve_annotation(ann, args.pages_dir, cache)
                results.append(rec)
                counts[rec.get("status", "?")] = counts.get(rec.get("status", "?"), 0) + 1
    except (OSError, ValueError) as exc:
        print("FATAL: %s" % exc, file=sys.stderr)
        return 2

    try:
        with open(args.out, "w", encoding="utf-8") as fh:
            for rec in results:
                fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError as exc:
        print("FATAL: cannot write %s: %s" % (args.out, exc), file=sys.stderr)
        return 2

    print("anchor_resolve: %d annotations -> %s" % (len(results), args.out))
    for k in sorted(counts):
        print("  status=%s: %d" % (k, counts[k]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
