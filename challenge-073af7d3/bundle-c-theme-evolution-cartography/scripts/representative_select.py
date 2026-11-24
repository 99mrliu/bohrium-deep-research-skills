#!/usr/bin/env python3
"""representative_select.py — auditable per-phase representative selection.

Usage:
    python3 representative_select.py --work DIR [--per-phase K]
                                     [--baseline top-citations] [--out FILE]

Multi-criteria mode (default). For each phase from phases.json every record
in the phase is scored (exact rubric in references/selection_rubric.md):

  total = 0.5 * citation_percentile      (within-phase rank by
                                          (citations asc, id asc); rank/n)
        + 0.3 * term_centrality          (sum of the record's terms'
                                          within-phase shares, divided by
                                          the phase maximum -> [0,1])
        + 0.2 * method_first_bonus       (1.0 iff record.year <=
                                          phase_start + 1 AND the record is
                                          among the earliest documents
                                          containing at least one of the
                                          phase's emerging_terms; else 0.0)

Top-K per phase are selected. The FULL score table for EVERY candidate is
written to representatives.json — the selection caliber is auditable and
explainable, not a black box.

GATE (coverage check, both modes): coverage = phases with >= 1 selected
representative / total phases. Multi-criteria mode prints a WARNING when a
phase selects zero (corpus hole) but still exits 0 (the hole is reported,
not hidden). --baseline top-citations mode mimics the raw global citation
top-N anti-pattern (N = K * n_phases, ties broken by id asc) and then runs
the same coverage check; it EXITS 1 when coverage < 1.0, naming the
uncovered phases — proving the anti-pattern check fires.
"""
import argparse
import json
import os
import sys
from collections import defaultdict

W_CIT, W_CENT, W_BONUS = 0.5, 0.3, 0.2


def load_json(path, default):
    if not os.path.isfile(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--per-phase", type=int, default=2)
    ap.add_argument("--baseline", choices=["top-citations"], default=None)
    ap.add_argument("--out", default="representatives.json")
    args = ap.parse_args()

    canon_path = os.path.join(args.work, "canon.jsonl")
    phases_path = os.path.join(args.work, "phases.json")
    if not (os.path.isfile(canon_path) and os.path.isfile(phases_path)):
        print("ERROR: need canon.jsonl and phases.json in --work; run "
              "build_corpus/term_cohorts/phase_segment first", file=sys.stderr)
        return 2

    records = [json.loads(l) for l in open(canon_path, encoding="utf-8")
               if l.strip()]
    phases_doc = load_json(phases_path, {})
    phases = phases_doc.get("phases", [])
    if not phases:
        print("ERROR: phases.json contains no phases", file=sys.stderr)
        return 2
    term_year = load_json(os.path.join(args.work, "term_year_matrix.json"), {})
    rec_terms = load_json(os.path.join(args.work, "record_terms.json"), {})

    first_year = {}
    for t, yc in term_year.items():
        ys = [int(y) for y, c in yc.items() if c > 0]
        if ys:
            first_year[t] = min(ys)

    rec_by_id = {r["id"]: r for r in records}

    def phase_of(year):
        if year is None:
            return None
        for p in phases:
            if p["start"] <= year <= p["end"]:
                return p
        return None

    warnings, candidates = [], []

    if args.baseline == "top-citations":
        # anti-pattern baseline: raw global citation top-N
        n = args.per_phase * len(phases)
        ranked = sorted(records,
                        key=lambda r: (-r.get("citations", 0), r["id"]))
        selected_ids = {r["id"] for r in ranked[:n]}
        for r in ranked:
            p = phase_of(r.get("year"))
            candidates.append({
                "record_id": r["id"],
                "title": r.get("title", ""),
                "year": r.get("year"),
                "phase_id": p["phase_id"] if p else None,
                "citations": r.get("citations", 0),
                "citation_percentile": None,
                "term_centrality": None,
                "method_first_bonus": None,
                "total_score": None,
                "selected": r["id"] in selected_ids,
            })
        mode, scoring = "baseline_top-citations", \
            "global raw citation top-N (anti-pattern baseline); N=K*n_phases"
    else:
        for p in phases:
            pid, start, end = p["phase_id"], p["start"], p["end"]
            members = [r for r in records
                       if r.get("year") is not None and start <= r["year"] <= end]
            if not members:
                warnings.append("phase %s (%d-%d) has zero records: corpus hole"
                                % (pid, start, end))
                continue
            n = len(members)
            by_rank = sorted(members,
                             key=lambda r: (r.get("citations", 0), r["id"]))
            pct = {r["id"]: (i + 1) / n for i, r in enumerate(by_rank)}
            # within-phase term shares
            counts = defaultdict(int)
            for t, yc in term_year.items():
                c = sum(v for y, v in yc.items() if start <= int(y) <= end)
                if c:
                    counts[t] = c
            total = sum(counts.values()) or 1
            share = {t: c / total for t, c in counts.items()}
            raw_cent = {r["id"]: sum(share.get(t, 0.0)
                                     for t in rec_terms.get(r["id"], []))
                        for r in members}
            cmax = max(raw_cent.values()) or 1.0
            # method-first: earliest docs introducing an emerging term
            introducers = set()
            for t in p.get("emerging_terms", []):
                fy = first_year.get(t)
                if fy is None:
                    continue
                for r in members:
                    if r["year"] == fy and t in rec_terms.get(r["id"], []):
                        introducers.add(r["id"])
            rows = []
            for r in members:
                bonus = 1.0 if (r["year"] <= start + 1
                                and r["id"] in introducers) else 0.0
                cent = round(raw_cent[r["id"]] / cmax, 6)
                score = round(W_CIT * pct[r["id"]] + W_CENT * cent
                              + W_BONUS * bonus, 6)
                rows.append({
                    "record_id": r["id"],
                    "title": r.get("title", ""),
                    "year": r.get("year"),
                    "phase_id": pid,
                    "citations": r.get("citations", 0),
                    "citation_percentile": round(pct[r["id"]], 6),
                    "term_centrality": cent,
                    "method_first_bonus": bonus,
                    "total_score": score,
                    "selected": False,
                })
            rows.sort(key=lambda x: (-x["total_score"], x["record_id"]))
            for row in rows[:max(args.per_phase, 0)]:
                row["selected"] = True
            if not any(row["selected"] for row in rows):
                warnings.append("phase %s (%d-%d): zero representatives "
                                "selected" % (pid, start, end))
            candidates.extend(rows)
        mode = "multi-criteria"
        scoring = ("total = 0.5*within_phase_citation_percentile + "
                   "0.3*term_centrality(phase-max-normalized) + "
                   "0.2*method_first_bonus(year<=phase_start+1 and earliest "
                   "doc of an emerging term)")

    selected = [c for c in candidates if c["selected"]]
    covered = sorted({c["phase_id"] for c in selected if c["phase_id"]})
    total_phases = [p["phase_id"] for p in phases]
    uncovered = [p for p in total_phases if p not in covered]
    coverage = round(len(covered) / len(total_phases), 6) if total_phases else 0.0

    candidates.sort(key=lambda c: (c.get("phase_id") or "",
                                   -(c["total_score"] or 0)
                                   if c["total_score"] is not None else 0,
                                   c["record_id"]))
    out = {
        "mode": mode,
        "per_phase": args.per_phase,
        "scoring": scoring,
        "weights": {"citation_percentile": W_CIT, "term_centrality": W_CENT,
                    "method_first_bonus": W_BONUS},
        "coverage": {
            "phases_covered": len(covered),
            "phases_total": len(total_phases),
            "coverage": coverage,
            "covered_phase_ids": covered,
            "uncovered_phase_ids": uncovered,
        },
        "warnings": warnings,
        "candidates": candidates,
    }
    out_path = os.path.join(args.work, args.out)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, sort_keys=True, indent=1)

    for w in warnings:
        print("WARNING: %s" % w, file=sys.stderr)
    print("representative_select[%s]: selected %d, coverage %d/%d = %.3f, "
          "uncovered=%s -> %s" % (mode, len(selected), len(covered),
                                  len(total_phases), coverage, uncovered,
                                  out_path))
    if args.baseline and coverage < 1.0:
        print("COVERAGE VIOLATION: raw citation top-N leaves phases %s "
              "uncovered" % uncovered, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
