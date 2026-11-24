#!/usr/bin/env python3
"""phase_segment.py — segment the corpus time span into evolution phases.

Usage:
    python3 phase_segment.py --work DIR [--synonyms FILE]

Boundary rule (fully documented and replayable via phases.json meta):
  1. per-year term-frequency (doc-count) vectors from year_vectors.json
  2. cosine distance between ADJACENT years: d[i] = 1 - cos(v[i], v[i+1])
     (empty vs non-empty vector -> distance 1; both empty -> 0)
  3. smooth with the 1-2-1 kernel: s[i] = (d[i-1] + 2*d[i] + d[i+1]) / 4
     (edge values replicated)
  4. candidate boundaries = local maxima of s (s[i] > s[i-1] and
     s[i] >= s[i+1]) strictly above threshold = median(s) + 1.0 * MAD(s),
     where MAD = median(|s - median(s)|). If MAD == 0 the plain median is
     used as threshold.
  A boundary between years[i] and years[i+1] ends the current phase at
  years[i]. If nothing passes the threshold, one phase spans the corpus
  and the caller must treat phase claims as exploratory.

Phase contents:
  dominant_terms   top-10 by within-phase share of all term counts
  emerging_terms   first seen inside this phase, phase doc-freq >= 2,
                   top-10 by within-phase share
  declining_terms  active in this phase (phase doc-freq >= 2) whose last
                   corpus appearance falls in the phase's final two years;
                   omitted for the LAST phase because of corpus-end
                   censoring (decline is then unknowable, not zero)

drift_report.json (the "术语换了说法 ≠ 新主题" detector):
  for each canonical term in the synonyms map, per-variant yearly document
  counts from LITERAL substring matching on raw title+abstract+keywords,
  plus the merged canonical cohort's yearly counts. A vocabulary shift
  shows as: variant A counts early, variant B counts late, merged cohort
  continuous. Without the map (or --synonyms) the report is emitted empty
  with an explicit note.
"""
import argparse
import json
import os
import statistics
import sys
from collections import defaultdict


def cosine_dist(a, b):
    if not a and not b:
        return 0.0
    if not a or not b:
        return 1.0
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    na = sum(v * v for v in a.values()) ** 0.5
    nb = sum(v * v for v in b.values()) ** 0.5
    if na == 0 or nb == 0:
        return 1.0
    return round(1.0 - dot / (na * nb), 6)


def load_json(path, default):
    if not os.path.isfile(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--synonyms", default=None)
    ap.add_argument("--top-n", type=int, default=10)
    args = ap.parse_args()

    year_vec = load_json(os.path.join(args.work, "year_vectors.json"), {})
    term_year = load_json(os.path.join(args.work, "term_year_matrix.json"), {})
    rec_terms = load_json(os.path.join(args.work, "record_terms.json"), {})
    canon_path = os.path.join(args.work, "canon.jsonl")
    records = [json.loads(l) for l in open(canon_path, encoding="utf-8")
               if l.strip()] if os.path.isfile(canon_path) else []

    years = sorted(int(y) for y in year_vec)
    meta = {
        "rule": ("boundary = local maximum of 1-2-1-smoothed adjacent-year "
                 "cosine distance strictly above median + 1.0*MAD"),
        "kernel": [1, 2, 1],
        "years": years,
    }

    boundaries = []
    dists, smooth = [], []
    if len(years) >= 2:
        vecs = [year_vec[str(y)] for y in years]
        dists = [cosine_dist(vecs[i], vecs[i + 1]) for i in range(len(vecs) - 1)]
        for i in range(len(dists)):
            lo = dists[i - 1] if i > 0 else dists[i]
            hi = dists[i + 1] if i + 1 < len(dists) else dists[i]
            smooth.append(round((lo + 2 * dists[i] + hi) / 4.0, 6))
        med = statistics.median(smooth)
        mad = statistics.median([abs(x - med) for x in smooth])
        thr = med + 1.0 * mad if mad > 0 else med
        meta.update({
            "raw_distances": dists,
            "smoothed_distances": smooth,
            "median": med,
            "mad": mad,
            "threshold": thr,
            "distance_between": ["%d-%d" % (years[i], years[i + 1])
                                 for i in range(len(dists))],
        })
        for i in range(len(smooth)):
            left = smooth[i - 1] if i > 0 else float("-inf")
            right = smooth[i + 1] if i + 1 < len(smooth) else float("inf")
            if smooth[i] > left and smooth[i] >= right and smooth[i] > thr:
                boundaries.append(years[i])  # boundary AFTER this year
    else:
        meta["note"] = "fewer than 2 years; phase segmentation impossible"
    meta["boundaries_after_year"] = boundaries

    # phase spans
    spans = []
    prev = years[0] if years else None
    for b in boundaries:
        spans.append((prev, b))
        prev = b + 1
    if years:
        spans.append((prev, years[-1]))

    # per-record year and phase doc-frequency
    rec_year = {r["id"]: r.get("year") for r in records}
    first_year, last_year = {}, {}
    for t, yc in term_year.items():
        ys = [int(y) for y, c in yc.items() if c > 0]
        if ys:
            first_year[t], last_year[t] = min(ys), max(ys)

    phases = []
    for idx, (start, end) in enumerate(spans, 1):
        pid = "P%d" % idx
        phase_recs = [rid for rid, y in rec_year.items()
                      if y is not None and start <= y <= end]
        phase_df = defaultdict(int)
        phase_counts = defaultdict(int)
        for t, yc in term_year.items():
            c = sum(cnt for y, cnt in yc.items() if start <= int(y) <= end)
            if c:
                phase_counts[t] = c
        for rid in phase_recs:
            for t in rec_terms.get(rid, []):
                phase_df[t] += 1
        total = sum(phase_counts.values()) or 1
        share = {t: c / total for t, c in phase_counts.items()}

        dominant = sorted(phase_counts, key=lambda t: (-share[t], t))[:args.top_n]
        emerging = sorted(
            [t for t in phase_counts
             if first_year.get(t, -1) >= start and phase_df.get(t, 0) >= 2],
            key=lambda t: (-share[t], t))[:args.top_n]
        if idx < len(spans):
            declining = sorted(
                [t for t in phase_counts
                 if phase_df.get(t, 0) >= 2
                 and end - 1 <= last_year.get(t, 0) <= end],
                key=lambda t: (-share[t], t))[:args.top_n]
            dnote = None
        else:
            declining = []
            dnote = ("final phase: decline unknowable due to corpus-end "
                     "censoring; not reported")
        entry = {
            "phase_id": pid,
            "start": start,
            "end": end,
            "n_records": len(phase_recs),
            "dominant_terms": dominant,
            "emerging_terms": emerging,
            "declining_terms": declining,
        }
        if dnote:
            entry["declining_note"] = dnote
        phases.append(entry)

    if not phases:
        meta["note"] = "no year-labeled records; no phases"

    with open(os.path.join(args.work, "phases.json"), "w", encoding="utf-8") as fh:
        json.dump({"meta": meta, "phases": phases}, fh,
                  ensure_ascii=False, sort_keys=True, indent=1)

    # ---------------- drift report (literal per-variant yearly counts) ----
    syn = {}
    if args.synonyms and os.path.isfile(args.synonyms):
        raw = json.load(open(args.synonyms, encoding="utf-8"))
        syn = {str(k).strip().lower(): str(v).strip().lower()
               for k, v in raw.items() if not str(k).startswith("_")}
    canon_terms = {}
    if syn:
        raw_text = {}
        for r in records:
            t = " ".join([r.get("title") or "", r.get("abstract") or "",
                          " ".join(r.get("keywords") or [])]).lower()
            raw_text[r["id"]] = t
        by_canon = defaultdict(set)
        for variant, canonical in syn.items():
            by_canon[canonical].add(variant)
        for canonical, variants in sorted(by_canon.items()):
            probes = sorted(variants | {canonical})
            vcounts = {}
            for v in probes:
                yc = defaultdict(int)
                for r in records:
                    y = r.get("year")
                    if y is not None and v in raw_text[r["id"]]:
                        yc[str(y)] += 1
                vcounts[v] = dict(sorted(yc.items()))
            merged = term_year.get(canonical, {})
            canon_terms[canonical] = {
                "variants": vcounts,
                "merged_cohort_year_counts": dict(sorted(merged.items())),
                "reading": ("vocabulary shift = one variant rises as another "
                            "falls while the merged cohort stays continuous; "
                            "this is renaming, NOT a new topic"),
            }
    drift = {
        "note": ("per-variant LITERAL substring document counts per year "
                 "(before synonym merge)" if syn else
                 "no synonyms map provided; drift detection disabled"),
        "canonical_terms": canon_terms,
    }
    with open(os.path.join(args.work, "drift_report.json"), "w",
              encoding="utf-8") as fh:
        json.dump(drift, fh, ensure_ascii=False, sort_keys=True, indent=1)

    print("phase_segment: %d years, boundaries after %s -> %d phase(s): %s"
          % (len(years), boundaries, len(phases),
             ["%d-%d" % (p["start"], p["end"]) for p in phases]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
