#!/usr/bin/env python3
"""mini_pipeline.py — small deterministic reference pipeline for frontier-run-gates.

Purpose: give the stage gates (gate_check.py) something real to check and give
replay_diff.py something deterministic to re-run. It is NOT the final analysis;
the agent must replace the placeholders with real judgment (see SKILL.md).

Stages (each writes an artifact under --work and updates manifest.json):
  1. normalize       -> canon.jsonl        (id/title/year/abstract per record)
  2. slices          -> slices.json        (annual counts, count closure)
  3. cohorts         -> cohorts.json       (top keyword-ish tokens per year,
                                            stopworded, min_df 2)
  4. representatives -> representatives.json (phases = equal thirds of the year
                                            span; top-cited-per-phase PLACEHOLDER
                                            with an explicit note that final
                                            selection is the agent's job)
  5. gaps            -> gaps.json          (none-with-reason placeholder)
  6. evidence matrix -> evidence_matrix.jsonl (one seed row per canon record)
  7. draft result    -> result_draft.json  (case_id + every output_contract field
                                            with structured placeholders,
                                            status="partial", provenance with
                                            input sha256s from the manifest)

Determinism: no wall-clock, no set/dict iteration leaks into output, sort_keys
everywhere, stable tie-breaks. Stdlib only. No network.

Usage:
  mini_pipeline.py --work DIR --corpus FILE --case FILE
Corpus formats: .jsonl / .json (list or {"records": [...]}) / .csv
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_manifest as rm  # noqa: E402

TOKEN_RE = re.compile(r"[a-z][a-z0-9\-]{2,}")

STOPWORDS = frozenset("""
a an the and or of to in for on with by from as at is are was were be been being
we our this that these those it its their his her he she they them which who whom
whose what when where how why between into over under more most other others some
such no nor not only own same so than too very can could will would should just
also however thus therefore furthermore moreover
study studies paper papers work works propose proposes proposed present presents
presented show shows shown demonstrate demonstrates demonstrated based using use
used via new novel approach approaches method methods technique techniques result
results finding findings analysis analyses analyze analyze performance effect effects
high low two three first second et al
synthetic abstract abstracts
""".split())

TOP_K_TERMS = 10
MIN_DF = 2
TOP_K_REPS = 3

ARTIFACTS = [
    "canon.jsonl",
    "slices.json",
    "cohorts.json",
    "representatives.json",
    "gaps.json",
    "evidence_matrix.jsonl",
    "result_draft.json",
]


# ---------------------------------------------------------------- io helpers

def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def load_corpus(path):
    """Load corpus records from .jsonl / .json / .csv. Never trust labels."""
    if not os.path.isfile(path):
        raise FileNotFoundError("corpus not found: %s" % path)
    lower = path.lower()
    records = []
    if lower.endswith(".json") and not lower.endswith(".jsonl"):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            records = data.get("records", [])
    elif lower.endswith(".csv"):
        import csv
        with open(path, encoding="utf-8", newline="") as fh:
            records = list(csv.DictReader(fh))
    else:  # default: jsonl
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    if not isinstance(records, list):
        records = []
    return [r for r in records if isinstance(r, dict)]


def normalize_record(rec, idx):
    rid = rec.get("id") or rec.get("record_id") or rec.get("doi") \
        or rec.get("uid") or ("REC-%04d" % (idx + 1))
    title = rec.get("title") or ""
    year_raw = rec.get("year") or rec.get("publication_year") or rec.get("date")
    year = None
    if year_raw is not None:
        m = re.search(r"(\d{4})", str(year_raw))
        if m:
            year = int(m.group(1))
    abstract = rec.get("abstract") or rec.get("summary") or ""
    citations = rec.get("citations", rec.get("cited_by", 0))
    try:
        citations = int(citations)
    except (TypeError, ValueError):
        citations = 0
    keywords = rec.get("keywords") or []
    if isinstance(keywords, str):
        keywords = [k.strip() for k in re.split(r"[;,]", keywords) if k.strip()]
    return {
        "id": str(rid),
        "title": str(title),
        "year": year,
        "abstract": str(abstract),
        "citations": citations,
        "keywords": [str(k) for k in keywords],
    }


def tokens(text):
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


# ---------------------------------------------------------------- the stages

def run(work, corpus_path, case_path):
    corpus_path = os.path.abspath(corpus_path)
    case_path = os.path.abspath(case_path)

    manifest = rm.load(work) or rm.new_manifest()

    # --- G0: contract read -------------------------------------------------
    with open(case_path, encoding="utf-8") as fh:
        case = json.load(fh)
    case_id = str(case.get("case_id") or "UNKNOWN_CASE")
    contract = case.get("output_contract") or {}
    fields = list(contract.get("fields") or [])
    manifest["case"] = {
        "path": case_path,
        "case_id": case_id,
        "output_contract_fields": fields,
    }
    manifest["pipeline"] = {"corpus": corpus_path, "case": case_path}
    for p in (corpus_path, case_path):
        if os.path.isfile(p):
            rm.add_input(manifest, p)
    rm.set_stage(manifest, "G0_contract_read", "ok", [case_path])
    rm.save(work, manifest)

    # --- normalize ---------------------------------------------------------
    raw = load_corpus(corpus_path)
    canon = [normalize_record(r, i) for i, r in enumerate(raw)]
    canon.sort(key=lambda r: r["id"])
    canon_path = os.path.join(work, "canon.jsonl")
    write_jsonl(canon_path, [
        {"abstract": r["abstract"], "id": r["id"],
         "title": r["title"], "year": r["year"]}
        for r in canon
    ])
    rm.set_stage(manifest, "normalize", "ok", [canon_path])
    rm.save(work, manifest)

    # --- slices (annual counts, closure) ------------------------------------
    with_year = [r for r in canon if isinstance(r["year"], int)]
    years_sorted = sorted({r["year"] for r in with_year})
    annual = []
    if years_sorted:
        lo, hi = years_sorted[0], years_sorted[-1]
        counts = {y: 0 for y in range(lo, hi + 1)}
        for r in with_year:
            counts[r["year"]] += 1
        annual = [{"year": y, "count": counts[y]} for y in range(lo, hi + 1)]
    slices = {
        "years": annual,
        "records_total": len(canon),
        "records_with_year": len(with_year),
        "records_without_year": len(canon) - len(with_year),
        "closure": sum(a["count"] for a in annual) == len(with_year),
        "caveats": [
            "annual counts are noisy (Poisson scale ~sqrt(n))",
            "final-year count is right-censored (incomplete indexing)",
            "date caliber (print/online/preprint) must be stated by the agent",
        ],
    }
    slices_path = os.path.join(work, "slices.json")
    write_json(slices_path, slices)
    rm.set_stage(manifest, "slices", "ok", [slices_path])
    rm.save(work, manifest)

    # --- cohorts (top terms per year) ---------------------------------------
    doc_tokens = {r["id"]: set(tokens(r["title"] + " " + r["abstract"]))
                  for r in canon}
    df = {}
    for tid_set in doc_tokens.values():
        for t in tid_set:
            df[t] = df.get(t, 0) + 1
    vocab = {t for t, d in df.items() if d >= MIN_DF}
    cohort_years = []
    for y in sorted({r["year"] for r in canon if isinstance(r["year"], int)}):
        per = {}
        for r in canon:
            if r["year"] != y:
                continue
            for t in doc_tokens[r["id"]]:
                if t in vocab:
                    per[t] = per.get(t, 0) + 1
        ranked = sorted(per.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_K_TERMS]
        cohort_years.append({
            "year": y,
            "terms": [{"term": t, "df": df[t], "count": c} for t, c in ranked],
        })
    cohorts = {
        "min_df": MIN_DF,
        "top_k": TOP_K_TERMS,
        "unit": "document count within year (title+abstract tokens, stopworded)",
        "years": cohort_years,
        "note": "naive lexical cohorts; agent must do phase segmentation and "
                "mark why-change claims as inference (SKILL.md G3)",
    }
    cohorts_path = os.path.join(work, "cohorts.json")
    write_json(cohorts_path, cohorts)
    rm.set_stage(manifest, "cohorts", "ok", [cohorts_path])
    rm.save(work, manifest)

    # --- representatives (PLACEHOLDER: top-cited per phase) -----------------
    phases = []
    if years_sorted:
        lo, hi = years_sorted[0], years_sorted[-1]
        n_years = hi - lo + 1
        bounds = [lo + (n_years * i) // 3 for i in range(4)]
        bounds[-1] = hi + 1
        for i in range(3):
            ys, ye = bounds[i], bounds[i + 1] - 1
            members = [r for r in canon
                       if isinstance(r["year"], int) and ys <= r["year"] <= ye]
            members.sort(key=lambda r: (-r["citations"], r["id"]))
            phases.append({
                "phase": i + 1,
                "year_start": ys,
                "year_end": ye,
                "records_in_phase": len(members),
                "candidates": [
                    {"record_id": r["id"], "title": r["title"], "year": r["year"],
                     "citations": r["citations"],
                     "selection": "placeholder_top_cited"}
                    for r in members[:TOP_K_REPS]
                ],
            })
    representatives = {
        "note": "PLACEHOLDER ONLY. Candidates are raw top-cited per phase. The "
                "final representative works MUST be re-selected by the agent with "
                "multi-criteria scoring (within-phase citation percentile + term "
                "centrality + method-first), never raw global citation top-N. "
                "See SKILL.md G4.",
        "phases": phases,
    }
    reps_path = os.path.join(work, "representatives.json")
    write_json(reps_path, representatives)
    rm.set_stage(manifest, "representatives", "ok", [reps_path])
    rm.save(work, manifest)

    # --- gaps (none-with-reason placeholder) --------------------------------
    gaps = {
        "status": "none_recorded",
        "gaps": [],
        "reason": "placeholder: gap claims require agent judgment with exclusion "
                  "evidence (retrieval scope + near-miss analysis). Pipeline "
                  "records none-with-reason; a fabricated gap is worse than an "
                  "honest none. See SKILL.md G5.",
    }
    gaps_path = os.path.join(work, "gaps.json")
    write_json(gaps_path, gaps)
    rm.set_stage(manifest, "gaps", "ok", [gaps_path])
    rm.save(work, manifest)

    # --- evidence matrix (seed: one row per canon record) -------------------
    em_rows = []
    for r in canon:
        avail = ["abstract", "id", "title"]
        if isinstance(r["year"], int):
            avail.append("year")
        if r["citations"]:
            avail.append("citations")
        if r["keywords"]:
            avail.append("keywords")
        em_rows.append({
            "record_id": r["id"],
            "title": r["title"],
            "year": r["year"],
            "fields_available": sorted(avail),
        })
    em_path = os.path.join(work, "evidence_matrix.jsonl")
    write_jsonl(em_path, em_rows)
    rm.set_stage(manifest, "evidence_matrix", "ok", [em_path])
    rm.save(work, manifest)

    # --- result draft (partial-first skeleton) ------------------------------
    prov_inputs = [{"path": e["path"], "sha256": e["sha256"]}
                   for e in manifest["inputs"]]
    prov_inputs.sort(key=lambda e: e["path"])
    draft = {
        "case_id": case_id,
        "status": "partial",
        "provenance": {
            "generator": "mini_pipeline.py (frontier-run-gates)",
            "inputs": prov_inputs,
            "note": "skeleton draft; placeholders MUST be replaced by agent "
                    "analysis and backfilled into result.json after every stage",
        },
        "notes": [
            "DRAFT generated by mini_pipeline; all analytic fields are "
            "structured placeholders pending agent judgment (SKILL.md G2-G7)."
        ],
    }
    for f in fields:
        if "uncertainty" in f:
            continue  # handled below
        if "evidence" in f:
            draft[f] = {
                "note": "seed evidence matrix; every claim must back-link "
                        "record_id values resolvable in this file (G6)",
                "file": "evidence_matrix.jsonl",
                "rows": len(em_rows),
            }
        else:
            draft[f] = {
                "note": "PLACEHOLDER - pending agent analysis (see SKILL.md "
                        "stage for this field)"
            }
    uncertainty_items = [{
        "item": "draft_placeholder",
        "detail": "all analytic fields are pipeline placeholders; content, "
                  "conflicts and coverage limits pending agent review (G7)",
    }]
    n_missing_year = len(canon) - len(with_year)
    if canon and n_missing_year / len(canon) > 0.2:
        uncertainty_items.append({
            "item": "year_coverage",
            "detail": "%d/%d records lack a usable year (>20%%); time-trend "
                      "coverage is uncertain" % (n_missing_year, len(canon)),
        })
    unc_field = next((f for f in fields if "uncertainty" in f), "uncertainty")
    draft[unc_field] = uncertainty_items
    draft_path = os.path.join(work, "result_draft.json")
    write_json(draft_path, draft)
    rm.set_stage(manifest, "result_draft", "ok", [draft_path])
    rm.save(work, manifest)

    return {
        "work": os.path.abspath(work),
        "case_id": case_id,
        "contract_fields": fields,
        "records": len(canon),
        "artifacts": ARTIFACTS,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deterministic mini reference pipeline.")
    ap.add_argument("--work", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--case", required=True)
    args = ap.parse_args(argv)
    try:
        summary = run(args.work, args.corpus, args.case)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"error": type(exc).__name__, "detail": str(exc)},
                         ensure_ascii=False))
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
