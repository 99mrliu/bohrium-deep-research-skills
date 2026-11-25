#!/usr/bin/env python3
"""permutation-stability-ranker engine.

Center of gravity: process quality control via ranking stability. A ranking
that flips when candidate input order or feature weights are slightly
perturbed is not trustworthy; this engine quantifies that trust. All scoring
is deterministic and interpretable — no model call is required for the score
path. An optional judgments file (one batched model call in real runs) can
supply a semantic_score per record, which becomes just one more weighted
feature.

Pipeline:
  featurize  interpretable per-record features (documented in meta)
  score      base weighted score + N seeded robustness runs
             (shuffle input order + jitter every weight by ±10%),
             per-record rank min/max/mean, flip counts, Kendall's W
  assemble   final delivery: fragile records moved into a pending_review
             band (never silently excluded), output_contract fields mirrored
  validate   delivery conformance check (PASS/FAIL + exit code)

Stdlib only (Python 3). Subcommands:
  featurize --case CASE.json --out features.json
  score     --case CASE.json --features features.json --weights weights.json
            [--judgments J.json] [--runs N] --out stability.json
  assemble  --case CASE.json --stability stability.json --out result.json
  validate  --case CASE.json --result result.json
Exit code 0 on success/PASS, 1 on validation FAIL, 2 on usage/IO error.
"""
import argparse
import json
import random
import re
import sys
from pathlib import Path

SEED = 20261125
DEFAULT_RUNS = 50
JITTER = 0.10  # each weight is multiplied by 1 + U(-0.10, +0.10), seeded

CANDIDATE_KEYS = ("candidates", "records", "papers", "references", "pool",
                  "items", "works", "documents")
CONTRACT_KEYS = ("output_contract", "outputContract", "output_contract_fields",
                 "contract", "expected_output", "expected_outputs")
ID_KEYS = ("case_id", "caseId", "id", "name")
REC_ID_KEYS = ("record_id", "recordId", "id", "paper_id", "doi")
SCOPE_KEYS = ("retrieval_scope", "retrievalScope", "scope", "search_scope")

TOKEN_RE = re.compile(r"[a-z0-9]+|[一-鿿]")
STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "in", "on", "for", "to", "with",
    "by", "is", "are", "was", "were", "do", "does", "did", "from", "as",
    "at", "we", "this", "that", "its", "it", "be", "been", "their", "our",
}

PREPRINT_MARKERS = ("arxiv", "biorxiv", "bioRxiv".lower(), "medrxiv", "ssrn",
                    "preprint", "chemrxiv", "research square", "osf")
JOURNAL_MARKERS = ("journal", "proceedings", "conference", "nature",
                   "science", "letters", "review", "transactions", "annals",
                   "lancet", "bulletin", "archives", "quarterly", "press")

# Neutral imputation for a feature whose value is null: it contributes
# weight * 0.5. Documented here and in features.json meta so scores are
# reproducible by hand.
NEUTRAL = 0.5

FEATURE_DEFS = {
    "title_overlap": ("|tokens(research_question + queries) ∩ tokens(title)| / "
                      "|tokens(research_question + queries)|, in [0,1]; "
                      "null when the query token set is empty"),
    "abstract_overlap": ("same ratio against tokens(abstract); null when the "
                         "record has no abstract (imputed neutral %.1f)" % NEUTRAL),
    "year_in_scope": ("1.0 when record year is inside retrieval_scope years, "
                      "0.0 when outside; null when scope or year is unparseable "
                      "(imputed neutral %.1f)" % NEUTRAL),
    "has_abstract": "1.0 when a non-empty abstract string is present, else 0.0",
    "has_doi": "1.0 when a non-empty doi string is present, else 0.0",
    "venue_tier": ("HEURISTIC (heuristic:true): venue string contains preprint "
                   "markers (arxiv/biorxiv/medrxiv/ssrn/preprint/...) -> 0.3; "
                   "contains journal-ish markers (journal/proceedings/letters/"
                   "review/transactions/...) -> 1.0; otherwise 0.7; null when "
                   "venue absent (imputed neutral %.1f)" % NEUTRAL),
    "recency_norm": ("(year - min_year) / (max_year - min_year) across the "
                     "candidate pool; null when year missing; 0.5 for all when "
                     "every year is identical"),
    "semantic_score": ("OPTIONAL: per-record semantic relevance in [0,1] from "
                       "the judgments file (one batched model call in real "
                       "runs). Absent without judgments; present-but-null "
                       "values are imputed neutral %.1f" % NEUTRAL),
}


# --------------------------------------------------------------------------
# generic helpers (same tolerant conventions as the platform harness)
# --------------------------------------------------------------------------

def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise SystemExit("error: cannot parse %s as UTF-8 JSON: %s" % (path, exc))


def dump_json(obj, path):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8")


def find_case_id(case, case_path):
    if isinstance(case, dict):
        for k in ID_KEYS:
            v = case.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return Path(case_path).stem


def looks_like_record(obj):
    return isinstance(obj, dict) and isinstance(obj.get("title"), str)


def find_candidates(case):
    """Return (list_of_records, key_path) for the largest plausible pool."""
    best, best_key = [], None
    if isinstance(case, dict):
        for k in CANDIDATE_KEYS:
            v = case.get(k)
            if isinstance(v, list) and v and all(looks_like_record(r) for r in v):
                if len(v) > len(best):
                    best, best_key = v, k
        if not best:  # fallback: largest top-level list of title-bearing dicts
            for k, v in case.items():
                if (isinstance(v, list) and v
                        and sum(looks_like_record(r) for r in v) >= len(v) * 0.8):
                    if len(v) > len(best):
                        best, best_key = v, k
    return best, best_key


def record_id_of(rec, idx):
    for k in REC_ID_KEYS:
        v = rec.get(k)
        if isinstance(v, (str, int)) and str(v).strip():
            return str(v).strip()
    return "rec-%03d" % (idx + 1)


def find_queries(case):
    if isinstance(case, dict):
        for k in ("queries", "query_inputs", "search_queries", "actual_queries"):
            v = case.get(k)
            if isinstance(v, list):
                return [q if isinstance(q, str) else json.dumps(q, ensure_ascii=False)
                        for q in v]
    return []


def find_contract_fields(case):
    """Normalize whatever output_contract shape the case declares.

    Returns list of {"name", "hint"}. Supports: dict field->spec, list of
    names/specs, JSON-schema-ish {"properties": {...}}, or a single string.
    """
    raw = None
    if isinstance(case, dict):
        for k in CONTRACT_KEYS:
            if k in case:
                raw = case[k]
                break
    fields = []
    if isinstance(raw, dict):
        props = raw.get("properties") if isinstance(raw.get("properties"), dict) else None
        src = props if props is not None else raw
        for name, spec in src.items():
            hint = spec if isinstance(spec, str) else json.dumps(spec, ensure_ascii=False)
            fields.append({"name": str(name), "hint": hint[:200]})
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                fields.append({"name": item, "hint": ""})
            elif isinstance(item, dict) and item.get("name"):
                fields.append({"name": str(item["name"]),
                               "hint": json.dumps(item, ensure_ascii=False)[:200]})
    elif isinstance(raw, str):
        fields.append({"name": raw, "hint": ""})
    seen, uniq = set(), []
    for f in fields:
        if f["name"] not in seen:
            seen.add(f["name"])
            uniq.append(f)
    return uniq


def tokenize(text):
    if not isinstance(text, str):
        return set()
    return {t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS}


def parse_scope_years(case):
    """Return (start_year, end_year) or (None, None) if unparseable."""
    scope = None
    if isinstance(case, dict):
        for k in SCOPE_KEYS:
            if k in case:
                scope = case[k]
                break
    years = []
    if isinstance(scope, dict):
        for k, v in scope.items():
            if "year" in str(k).lower():
                if isinstance(v, (int, float)):
                    years.append(int(v))
                elif isinstance(v, str):
                    years += [int(m) for m in re.findall(r"(19|20)\d{2}", v)]
        if not years:
            years = [int(m) for m in
                     re.findall(r"(?:19|20)\d{2}", json.dumps(scope))]
    elif isinstance(scope, str):
        years = [int(m) for m in re.findall(r"(?:19|20)\d{2}", scope)]
    years = [y for y in years if 1900 <= y <= 2100]
    if not years:
        return None, None
    return min(years), max(years)


# --------------------------------------------------------------------------
# featurize
# --------------------------------------------------------------------------

def cmd_featurize(args):
    case = load_json(args.case)
    case_id = find_case_id(case, args.case)
    cands, pool_key = find_candidates(case)
    queries = find_queries(case)
    rq = case.get("research_question") or case.get("question") or ""
    q_tokens = tokenize(rq) | set().union(*[tokenize(q) for q in queries]) \
        if queries else tokenize(rq)
    start_y, end_y = parse_scope_years(case)

    raw = []
    for i, rec in enumerate(cands):
        rid = record_id_of(rec, i)
        title = rec.get("title") or ""
        abstract = rec.get("abstract") if isinstance(rec.get("abstract"), str) else ""
        venue = rec.get("venue") if isinstance(rec.get("venue"), str) else ""
        year = rec.get("year")
        try:
            year = int(year) if year is not None and str(year).strip() else None
        except (TypeError, ValueError):
            year = None
        feats = {}
        feats["title_overlap"] = (round(len(q_tokens & tokenize(title)) / len(q_tokens), 4)
                                  if q_tokens else None)
        if abstract.strip():
            feats["abstract_overlap"] = (round(len(q_tokens & tokenize(abstract))
                                               / len(q_tokens), 4)
                                         if q_tokens else None)
        else:
            feats["abstract_overlap"] = None
        if start_y is not None and year is not None:
            feats["year_in_scope"] = 1.0 if start_y <= year <= end_y else 0.0
        else:
            feats["year_in_scope"] = None
        feats["has_abstract"] = 1.0 if abstract.strip() else 0.0
        feats["has_doi"] = 1.0 if str(rec.get("doi") or "").strip() else 0.0
        if venue.strip():
            vlow = venue.lower()
            if any(m in vlow for m in PREPRINT_MARKERS):
                feats["venue_tier"] = 0.3
            elif any(m in vlow for m in JOURNAL_MARKERS):
                feats["venue_tier"] = 1.0
            else:
                feats["venue_tier"] = 0.7
        else:
            feats["venue_tier"] = None
        raw.append({"record_id": rid, "title": title[:160], "year": year,
                    "features": feats})

    years = [r["year"] for r in raw if r["year"] is not None]
    for r in raw:
        if r["year"] is None or not years:
            r["features"]["recency_norm"] = None
        elif max(years) == min(years):
            r["features"]["recency_norm"] = 0.5
        else:
            r["features"]["recency_norm"] = round(
                (r["year"] - min(years)) / (max(years) - min(years)), 4)

    out = {
        "case_id": case_id,
        "meta": {
            "engine": "stability_engine.py featurize",
            "seed": SEED,
            "candidate_pool_key": pool_key,
            "feature_definitions": FEATURE_DEFS,
            "heuristic_features": ["venue_tier"],
            "tokenization": ("lowercase; tokens match [a-z0-9]+ or single CJK "
                             "chars; English stopwords removed: "
                             + ", ".join(sorted(STOPWORDS))),
            "neutral_imputation": ("null feature values contribute "
                                   "weight * %.1f (neutral midpoint)" % NEUTRAL),
            "query_token_count": len(q_tokens),
            "retrieval_scope_years": [start_y, end_y]
                                     if start_y is not None else None,
        },
        "records": raw,
    }
    dump_json(out, args.out)
    print("featurize: case_id=%s records=%d scope_years=%s -> %s"
          % (case_id, len(raw), [start_y, end_y] if start_y else None, args.out))


# --------------------------------------------------------------------------
# score
# --------------------------------------------------------------------------

def load_weights(obj):
    """Accept {"weights": {...}} with optional _comment keys, or a flat dict."""
    src = obj.get("weights") if isinstance(obj, dict) and "weights" in obj else obj
    if not isinstance(src, dict):
        raise SystemExit("error: weights file must be a JSON object")
    out = {}
    for k, v in src.items():
        if str(k).startswith("_"):
            continue
        if isinstance(v, (int, float)) and v >= 0:
            out[str(k)] = float(v)
    if not out or sum(out.values()) <= 0:
        raise SystemExit("error: no positive numeric weights found")
    return out


def load_semantic_scores(obj):
    """Accept {"judgments": [...]}, a bare list, or {record_id: score}."""
    items = obj.get("judgments") if isinstance(obj, dict) else obj
    out = {}
    if isinstance(items, list):
        for j in items:
            if isinstance(j, dict) and j.get("record_id") is not None:
                v = j.get("semantic_score", j.get("score"))
                if isinstance(v, (int, float)):
                    out[str(j["record_id"])] = float(v)
    elif isinstance(items, dict):
        for k, v in items.items():
            if isinstance(v, (int, float)):
                out[str(k)] = float(v)
    normed = {}
    for k, v in out.items():
        if v > 1.0:  # tolerate 0..100 scales
            v = v / 100.0
        normed[k] = max(0.0, min(1.0, v))
    return normed


def compute_scores(records, weights):
    """Deterministic weighted sum, normalized by total active weight.

    A feature named in weights but absent from every record is skipped;
    a null value on a present feature is imputed NEUTRAL (documented).
    """
    used = {f: w for f, w in weights.items()
            if any(f in r["features"] for r in records)}
    total_w = sum(used.values())
    scores = {}
    for r in records:
        acc = 0.0
        for f, w in used.items():
            v = r["features"].get(f)
            acc += w * (float(v) if isinstance(v, (int, float)) else NEUTRAL)
        scores[r["record_id"]] = round(acc / total_w, 6)
    return scores, used


def rank_scores(scores, order_ids):
    """Competition ranking ('1224'): score desc, ties share one rank.

    `order_ids` gives the deterministic tie-break sequence (base run:
    record_id ascending; robustness runs: the shuffled input order, which
    is exactly the order sensitivity being measured).
    """
    pos = {rid: i for i, rid in enumerate(order_ids)}
    ordered = sorted(scores, key=lambda rid: (-scores[rid], pos[rid]))
    ranks, tie_groups = {}, {}
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and scores[ordered[j + 1]] == scores[ordered[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[ordered[k]] = i + 1
        if j > i:
            tie_groups[i + 1] = ordered[i:j + 1]
        i = j + 1
    return ranks, tie_groups


def kendalls_w(rankings):
    """Kendall's W concordance across m rankings of n items, tie-corrected.

    R_i = sum of ranks of item i; S = sum (R_i - m(n+1)/2)^2;
    T_j = sum over tie groups in ranking j of (t^3 - t);
    W = 12 S / (m^2 (n^3 - n) - m * sum_j T_j).  W=1 iff rankings identical.
    """
    m = len(rankings)
    ids = sorted({rid for r in rankings for rid in r})
    n = len(ids)
    if m == 0 or n < 2:
        return 1.0
    S = 0.0
    for rid in ids:
        R = sum(r.get(rid, n) for r in rankings)
        S += (R - m * (n + 1) / 2.0) ** 2
    tie_corr = 0.0
    for r in rankings:
        counts = {}
        for v in r.values():
            counts[v] = counts.get(v, 0) + 1
        tie_corr += sum(t ** 3 - t for t in counts.values() if t > 1)
    denom = m * m * (n ** 3 - n) - m * tie_corr
    if denom <= 0:
        return 1.0
    return round(max(0.0, min(1.0, 12.0 * S / denom)), 6)


def cmd_score(args):
    case = load_json(args.case)
    feats_doc = load_json(args.features)
    weights = load_weights(load_json(args.weights))
    case_id = feats_doc.get("case_id") or find_case_id(case, args.case)
    records = list(feats_doc.get("records") or [])
    if not records:
        raise SystemExit("error: features file has no records")
    ids = [r["record_id"] for r in records]

    semantic = {}
    if args.judgments and Path(args.judgments).exists():
        semantic = load_semantic_scores(load_json(args.judgments))
        for r in records:
            r["features"]["semantic_score"] = semantic.get(r["record_id"])

    base_scores, used = compute_scores(records, weights)
    base_order = sorted(ids)
    base_ranks, base_ties = rank_scores(base_scores, base_order)

    n_runs = int(args.runs)
    rng = random.Random(SEED)
    run_ranks, tie_tally = [], 0
    for _ in range(n_runs):
        shuffled = list(ids)
        rng.shuffle(shuffled)                       # (a) order permutation
        jw = {f: w * (1.0 + rng.uniform(-JITTER, JITTER))  # (b) ±10% jitter
              for f, w in weights.items()}
        sc, _ = compute_scores(records, jw)
        rk, tg = rank_scores(sc, shuffled)          # tie-break = input order
        run_ranks.append(rk)
        tie_tally += len(tg)

    rec_rows, pair_flips = [], 0
    for rid in ids:
        rr = [r[rid] for r in run_ranks]
        rmin, rmax = min(rr), max(rr)
        rng_span = rmax - rmin
        flips = sum(1 for v in rr if v != base_ranks[rid])
        cls = "stable" if rng_span <= 1 else ("fragile" if rng_span >= 3
                                              else "watch")
        rec_rows.append({
            "record_id": rid,
            "base_rank": base_ranks[rid],
            "base_score": base_scores[rid],
            "rank_min": rmin, "rank_max": rmax,
            "rank_mean": round(sum(rr) / len(rr), 3),
            "rank_range": rng_span,
            "flip_count": flips,
            "stability": cls,
        })
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            ra, rb = ids[a], ids[b]
            if base_ranks[ra] == base_ranks[rb]:
                continue
            base_ab = base_ranks[ra] < base_ranks[rb]
            for r in run_ranks:
                if r[ra] != r[rb] and (r[ra] < r[rb]) != base_ab:
                    pair_flips += 1

    W = kendalls_w(run_ranks)
    base_ranking = [{"rank": base_ranks[rid], "record_id": rid,
                     "score": base_scores[rid]} for rid in
                    sorted(ids, key=lambda r: (base_ranks[r], r))]
    for rank_no, grp in base_ties.items():
        for row in base_ranking:
            if row["rank"] == rank_no:
                row["tie_group"] = grp

    out = {
        "case_id": case_id,
        "seed": SEED,
        "runs": n_runs,
        "weight_jitter": {
            "spec": ("each weight multiplied by 1 + U(-%.2f, +%.2f), drawn "
                     "from random.Random(%d); input order re-shuffled per run "
                     "from the same seeded generator" % (JITTER, JITTER, SEED)),
            "jitter": JITTER,
        },
        "tie_rule": ("score desc, then record_id asc (base) / shuffled input "
                     "order (runs); equal scores share one rank (competition "
                     "ranking) and are listed in tie_group"),
        "neutral_imputation": NEUTRAL,
        "weights_used": used,
        "semantic_scores_loaded": len(semantic),
        "base": {"ranking": base_ranking, "scores": base_scores},
        "records": rec_rows,
        "kendalls_w": W,
        "kendalls_w_formula": ("W = 12S / (m^2(n^3-n) - m*sum(T_j)); S = sum of "
                               "(R_i - m(n+1)/2)^2 over items; T_j = sum of "
                               "(t^3 - t) over tie groups of ranking j"),
        "flip_counts": {
            "record_rank_flips_vs_base": sum(r["flip_count"] for r in rec_rows),
            "pairwise_order_flips_vs_base": pair_flips,
            "run_tie_groups": tie_tally,
        },
        "stability_classes": {
            "stable": sum(1 for r in rec_rows if r["stability"] == "stable"),
            "watch": sum(1 for r in rec_rows if r["stability"] == "watch"),
            "fragile": sum(1 for r in rec_rows if r["stability"] == "fragile"),
        },
        "thresholds": ("stable: rank_range <= 1; fragile: rank_range >= 3; "
                       "watch: otherwise (rank_range = max - min of the "
                       "record's rank across the N perturbation runs)"),
    }
    dump_json(out, args.out)
    print("score: case_id=%s records=%d runs=%d W=%.4f stable=%d watch=%d "
          "fragile=%d -> %s"
          % (case_id, len(rec_rows), n_runs, W,
             out["stability_classes"]["stable"],
             out["stability_classes"]["watch"],
             out["stability_classes"]["fragile"], args.out))


# --------------------------------------------------------------------------
# assemble
# --------------------------------------------------------------------------

def stability_is_usable(stab, ids):
    if not isinstance(stab, dict):
        return False
    rows = stab.get("records")
    if not isinstance(rows, list) or not rows:
        return False
    got = {r.get("record_id") for r in rows if isinstance(r, dict)}
    return got == set(ids) and isinstance(stab.get("base"), dict)


def cmd_assemble(args):
    case = load_json(args.case)
    case_id = find_case_id(case, args.case)
    cands, _ = find_candidates(case)
    ids = [record_id_of(r, i) for i, r in enumerate(cands)]
    fields = find_contract_fields(case)

    stab = None
    degraded_reasons = []
    if args.stability and Path(args.stability).exists():
        stab = load_json(args.stability)
    else:
        degraded_reasons.append("stability file missing: %s" % args.stability)
    if stab is not None and not stability_is_usable(stab, ids):
        degraded_reasons.append("stability file missing/incomplete for the "
                                "candidate pool; emitting all-pending partial")
        stab = None

    screened, ranking, change_records, incomplete = [], [], [], []
    if stab is not None:
        by_id = {r["record_id"]: r for r in stab["records"]}
        kept = sorted((r for r in stab["records"] if r["stability"] != "fragile"),
                      key=lambda r: (r["base_rank"], r["record_id"]))
        pending = sorted((r for r in stab["records"] if r["stability"] == "fragile"),
                         key=lambda r: (r["base_rank"], r["record_id"]))
        final = 0
        for band, rows in (("ranked", kept), ("pending_review", pending)):
            for r in rows:
                final += 1
                reason = None
                if band == "pending_review":
                    reason = ("rank unstable under perturbation (rank range %d)"
                              % r["rank_range"])
                    change_records.append({
                        "change": "moved_to_pending_review",
                        "record_id": r["record_id"],
                        "from_base_rank": r["base_rank"],
                        "reason": reason,
                    })
                screened.append({
                    "record_id": r["record_id"],
                    "base_rank": r["base_rank"],
                    "final_rank": final,
                    "band": band,
                    "stability": r["stability"],
                    "rank_range": r["rank_range"],
                    "rank_min": r["rank_min"], "rank_max": r["rank_max"],
                    "rank_mean": r["rank_mean"],
                    "flip_count": r["flip_count"],
                    "base_score": r["base_score"],
                    "reason": reason,
                })
                ranking.append({"final_rank": final, "record_id": r["record_id"],
                                "band": band, "stability": r["stability"],
                                "base_rank": r["base_rank"]})
        stability_report = {
            "kendalls_w": stab.get("kendalls_w"),
            "formula": stab.get("kendalls_w_formula"),
            "runs": stab.get("runs"),
            "seed": stab.get("seed"),
            "weight_jitter": stab.get("weight_jitter"),
            "tie_rule": stab.get("tie_rule"),
            "flip_counts": stab.get("flip_counts"),
            "stability_classes": stab.get("stability_classes"),
            "thresholds": stab.get("thresholds"),
        }
        completed = ["featurization", "deterministic base scoring",
                     "%d seeded perturbation runs" % (stab.get("runs") or 0),
                     "stability classification", "all-record coverage"]
        uncertainty = [
            "venue_tier is a string heuristic (heuristic:true), not verified "
            "venue metadata",
            "token-overlap features are lexical proxies for topical relevance",
        ]
        if not stab.get("semantic_scores_loaded"):
            uncertainty.append("no semantic_score judgments supplied; ranking "
                               "rests on lexical/metadata features only")
        if pending:
            uncertainty.append("%d fragile record(s) deferred to "
                               "pending_review rather than excluded" % len(pending))
        limits = []
    else:
        for i, rid in enumerate(ids):
            screened.append({
                "record_id": rid, "base_rank": None, "final_rank": i + 1,
                "band": "pending_review", "stability": "unknown",
                "rank_range": None, "rank_min": None, "rank_max": None,
                "rank_mean": None, "flip_count": None, "base_score": None,
                "reason": "stability analysis unavailable; honest pending, "
                          "no ranking fabricated",
            })
            ranking.append({"final_rank": i + 1, "record_id": rid,
                            "band": "pending_review", "stability": "unknown",
                            "base_rank": None})
        stability_report = None
        completed = ["candidate discovery", "all-record coverage"]
        incomplete.append({"part": "stability analysis",
                           "reason": "; ".join(degraded_reasons)})
        uncertainty = ["no record has been scored or stability-tested; every "
                       "record is pending_review"]
        limits = []

    counts = {"total": len(screened),
              "ranked": sum(1 for s in screened if s["band"] == "ranked"),
              "pending_review": sum(1 for s in screened
                                    if s["band"] == "pending_review")}
    result = {
        "case_id": case_id,
        "research_question": case.get("research_question")
                             or case.get("question") or None,
        "screened_records": screened,
        "ranking": ranking,
        "stability_report": stability_report,
        "summary": {
            "counts": counts,
            "stability_classes": (stab or {}).get("stability_classes"),
            "note": ("fragile records are moved into pending_review with an "
                     "explicit reason; they are deferred for human review, "
                     "never excluded"),
        },
        "status": {
            "state": "partial" if incomplete else "complete",
            "completed": completed,
            "incomplete": incomplete,
            "limits": limits,
        },
        "uncertainty": uncertainty,
        "change_records": change_records,
    }
    if not fields:
        result["status"]["limits"].append(
            "case declares no output_contract; emitted the standard payload "
            "keys only")

    # Mirror every declared contract field; never drop one silently.
    payload = dict(result)
    for f in fields:
        name = f["name"]
        if name in payload:
            continue
        if isinstance(case, dict) and name in case and name not in ("candidates",):
            result[name] = case[name]  # echo real same-named input field
        elif any(t in name.lower() for t in ("omission", "coverage", "note")):
            parts = ["Candidate pool is a finite snapshot of %d records; no "
                     "live database was queried, so recall beyond the snapshot "
                     "cannot be claimed." % len(screened)]
            pend = [s["record_id"] for s in screened
                    if s["band"] == "pending_review"]
            if pend:
                parts.append("Records deferred to pending_review (unstable or "
                             "unscored): " + ", ".join(pend) + ".")
            gaps = [record_id_of(r, i) for i, r in enumerate(cands)
                    if isinstance(r, dict)
                    and any(not r.get(k) for k in ("abstract", "doi", "venue"))]
            if gaps:
                parts.append("Records with incomplete metadata (abstract/doi/"
                             "venue): " + ", ".join(gaps) + ".")
            result[name] = " ".join(parts)
        else:
            result[name] = None
            result["status"]["incomplete"].append(
                {"part": "contract field '%s'" % name,
                 "reason": "declared by output_contract but not producible "
                           "from available input; emitted as explicit null"})
            result["status"]["state"] = "partial"
    dump_json(result, args.out)
    print("assemble: state=%s records=%d ranked=%d pending_review=%d -> %s"
          % (result["status"]["state"], counts["total"], counts["ranked"],
             counts["pending_review"], args.out))


# --------------------------------------------------------------------------
# validate
# --------------------------------------------------------------------------

def cmd_validate(args):
    case = load_json(args.case)
    result = load_json(args.result)
    case_id = find_case_id(case, args.case)
    cands, _ = find_candidates(case)
    known_ids = [record_id_of(r, i) for i, r in enumerate(cands)]
    problems = []

    if result.get("case_id") != case_id:
        problems.append("case_id mismatch: result=%r expected=%r"
                        % (result.get("case_id"), case_id))
    for f in find_contract_fields(case):
        if f["name"] not in result:
            problems.append("contract field missing from result: %s" % f["name"])

    screened = result.get("screened_records") or []
    ranking = result.get("ranking") or []
    seen = [s.get("record_id") for s in screened]
    dup = sorted({r for r in seen if seen.count(r) > 1})
    if dup:
        problems.append("duplicate record_ids in screened_records: %s" % dup)
    missing = [r for r in known_ids if r not in seen]
    extra = [r for r in seen if r not in known_ids]
    if missing:
        problems.append("records not covered: %s" % missing)
    if extra:
        problems.append("unknown record_ids in output: %s" % extra)
    rank_seen = [r.get("record_id") for r in ranking]
    if sorted(rank_seen) != sorted(seen):
        problems.append("ranking + pending_review band do not cover exactly "
                        "the screened_records set")

    ranks = [(s.get("final_rank"), s.get("record_id")) for s in screened]
    by_rank = {}
    for rk, rid in ranks:
        if rk is not None:
            by_rank.setdefault(rk, []).append(rid)
    for rk, rids in by_rank.items():
        if len(rids) > 1:
            ok = all(s.get("tie_group") for s in screened
                     if s.get("final_rank") == rk)
            if not ok:
                problems.append("duplicate final_rank %s without documented "
                                "tie_group: %s" % (rk, sorted(rids)))
    for s in screened:
        if s.get("band") not in ("ranked", "pending_review"):
            problems.append("bad band for %s: %r"
                            % (s.get("record_id"), s.get("band")))

    sr = result.get("stability_report")
    if sr is None:
        state = (result.get("status") or {}).get("state")
        if state != "partial":
            problems.append("stability_report null but status.state != partial")
    else:
        n = sr.get("runs")
        if not isinstance(n, int) or n < 1:
            problems.append("stability_report.runs must be an int >= 1: %r" % (n,))
        W = sr.get("kendalls_w")
        if not isinstance(W, (int, float)) or not (0.0 <= W <= 1.0):
            problems.append("kendalls_w out of [0,1]: %r" % (W,))
    if not isinstance(result.get("status"), dict) \
            or "state" not in result.get("status", {}):
        problems.append("status.state missing")

    if problems:
        print("VALIDATE FAIL")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    print("VALIDATE PASS: case_id=%s records=%d contract_fields=%d state=%s"
          % (case_id, len(seen), len(find_contract_fields(case)),
             result["status"]["state"]))


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("featurize")
    p.add_argument("--case", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_featurize)
    p = sub.add_parser("score")
    p.add_argument("--case", required=True)
    p.add_argument("--features", required=True)
    p.add_argument("--weights", required=True)
    p.add_argument("--judgments")
    p.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_score)
    p = sub.add_parser("assemble")
    p.add_argument("--case", required=True)
    p.add_argument("--stability", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_assemble)
    p = sub.add_parser("validate")
    p.add_argument("--case", required=True)
    p.add_argument("--result", required=True)
    p.set_defaults(fn=cmd_validate)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
