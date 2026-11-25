#!/usr/bin/env python3
"""retrieval-coverage-ledger engine.

Center of gravity: upstream data authenticity and source/omission auditing.
The deliverable is not just labels but an accounting system over the finite
retrieval snapshot shipped with the case:

* source attribution — which ACTUAL query surfaced which record, with strict
  precedence (explicit per-record source field, recorded verbatim with a
  source_field pointer > inferred term overlap, marked inferred:true with the
  matched tokens > honest unattributed_register; nothing is silently dropped);
* per-query yield — {query, records, count} for every declared query;
* exact all-record accounting — every input record_id appears EXACTLY ONCE
  across keep/pending/exclude; violations (unknown ids, missing ids,
  duplicate decisions, invalid buckets, non-verbatim quotes) are repaired
  deterministically and logged in change_records;
* a conservative duplicate/version register — exact DOI match or
  normalized-title exact match merges (canonical = published venue over
  preprint, else newer year, else first); fixture_note labels are recorded
  verbatim as provenance, never treated as ground truth; fuzzy suspected
  pairs are queued for human review and never auto-merged;
* an explicit omission statement — the snapshot is finite, no live database
  exists, recall beyond the snapshot can never be claimed.

Stdlib only. Subcommands:
  map       --case CASE.json --out coverage.json
  account   --case CASE.json --coverage coverage.json [--decisions D.json] --out result.json
  validate  --case CASE.json --result result.json
Exit code 0 on success/PASS, 1 on validation FAIL or IO/parse error.
"""
import argparse
import json
import re
import sys
from pathlib import Path

CANDIDATE_KEYS = ("candidates", "records", "papers", "references", "pool",
                  "items")
QUERY_KEYS = ("queries", "query_inputs", "search_queries", "actual_queries")
CONTRACT_KEYS = ("output_contract", "outputContract", "output_contract_fields",
                 "contract", "expected_output", "expected_outputs")
ID_KEYS = ("case_id", "caseId", "id", "name")
REC_ID_KEYS = ("record_id", "recordId", "id", "paper_id", "doi")
SOURCE_FIELD_KEYS = ("source_query", "surfaced_by", "retrieved_by",
                     "found_by", "via_query", "query_string", "source",
                     "query")
BUCKETS = ("keep", "pending", "exclude")
PREPRINT_HINTS = ("preprint", "arxiv", "biorxiv", "medrxiv", "ssrn",
                  "chemrxiv", "osf preprints")
STOPWORDS = frozenset(
    "the a an and or of in on for to with by from at as is are was were be "
    "been we our their its this that these those study studies results "
    "between using use based effects effect trial participants data via "
    "among within during after before into".split())
SUSPECT_JACCARD = 0.6  # fuzzy pairs at/above this go to review queue, never merged


# ---------------------------------------------------------------------------
# generic helpers
# ---------------------------------------------------------------------------

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
    """Tolerant candidate-pool location.

    Prefer named keys (candidates/records/papers/references/pool/items);
    otherwise fall back to the largest top-level list whose members are
    dicts carrying a title.
    """
    best, best_key = [], None
    if isinstance(case, dict):
        for k in CANDIDATE_KEYS:
            v = case.get(k)
            if isinstance(v, list) and v and all(looks_like_record(r) for r in v):
                if len(v) > len(best):
                    best, best_key = v, k
        if not best:
            for k, v in case.items():
                if (isinstance(v, list) and v
                        and sum(looks_like_record(r) for r in v) >= len(v) * 0.8):
                    if len(v) > len(best):
                        best, best_key = v, k
    return best, best_key


def find_queries(case):
    if isinstance(case, dict):
        for k in QUERY_KEYS:
            v = case.get(k)
            if isinstance(v, list):
                return [q if isinstance(q, str) else json.dumps(q, ensure_ascii=False)
                        for q in v]
    return []


def find_contract_fields(case):
    """Normalize whatever output_contract shape the case declares."""
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


def record_id_of(rec, idx):
    for k in REC_ID_KEYS:
        v = rec.get(k)
        if isinstance(v, (str, int)) and str(v).strip():
            return str(v).strip()
    return "rec-%03d" % (idx + 1)


def content_tokens(text):
    """Lowercase alnum tokens, len>=3, minus stopwords."""
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower())
            if len(t) >= 3 and t not in STOPWORDS}


def normalize_title(title):
    """Lowercase, strip ALL punctuation and whitespace."""
    return re.sub(r"[^a-z0-9]", "", (title or "").lower())


# ---------------------------------------------------------------------------
# attribution
# ---------------------------------------------------------------------------

def explicit_source(rec):
    """Return (field_name, verbatim_value) for the first explicit source/query
    field present on the record, else (None, None)."""
    for k in SOURCE_FIELD_KEYS:
        if k not in rec:
            continue
        v = rec.get(k)
        if isinstance(v, str) and v.strip():
            return k, v.strip()
        if isinstance(v, dict):
            for kk in ("query", "text", "value"):
                if isinstance(v.get(kk), str) and v[kk].strip():
                    return k, v[kk].strip()
    return None, None


def attribute_record(rec, rid, queries, q_tokens):
    """Map one record to its surfacing query.

    Precedence: explicit per-record source field (verbatim, with pointer)
    > inferred term overlap (>=1 shared content token, matched tokens kept)
    > None (caller places the record in the unattributed register).
    """
    field, raw = explicit_source(rec)
    if raw is not None:
        matched = None
        for q in queries:
            if raw == q or raw.casefold() == q.casefold():
                matched = q
                break
        att = {"record_id": rid, "method": "explicit", "inferred": False,
               "source_field": field, "source_value": raw,
               "query": matched if matched is not None else raw}
        if matched is None:
            att["declared_query_match"] = False
            att["note"] = ("explicit source value does not match any declared "
                           "query; recorded verbatim")
        return att
    rec_tokens = content_tokens("%s %s" % (rec.get("title") or "",
                                           rec.get("abstract") or ""))
    best_q, best_overlap = None, set()
    for q, qt in zip(queries, q_tokens):
        overlap = rec_tokens & qt
        if len(overlap) > len(best_overlap):
            best_q, best_overlap = q, overlap
    if best_q is not None and best_overlap:
        return {"record_id": rid, "method": "inferred", "inferred": True,
                "query": best_q, "matched_tokens": sorted(best_overlap),
                "note": "heuristic term-overlap attribution; review matched_tokens"}
    return None


def cmd_map(args):
    case = load_json(args.case)
    case_id = find_case_id(case, args.case)
    cands, pool_key = find_candidates(case)
    queries = find_queries(case)
    q_tokens = [content_tokens(q) for q in queries]
    records, attributions, unattributed, missing_meta = [], [], [], []
    yield_map = {q: [] for q in queries}
    extra_yield = {}
    for i, r in enumerate(cands):
        rid = record_id_of(r, i)
        records.append({"record_id": rid,
                        "title": (r.get("title") or "")[:200],
                        "year": r.get("year"),
                        "doi": r.get("doi"),
                        "venue": r.get("venue"),
                        "has_fixture_note": bool(r.get("fixture_note"))})
        gaps = [k for k in ("title", "abstract", "year", "authors", "doi", "venue")
                if not r.get(k)]
        if gaps:
            missing_meta.append({"record_id": rid, "missing": gaps})
        att = attribute_record(r, rid, queries, q_tokens)
        if att is None:
            unattributed.append({
                "record_id": rid,
                "reason": "no explicit source field and zero content-token "
                          "overlap with any actual query; kept in this register, "
                          "never silently dropped"})
        else:
            attributions.append(att)
            if att["query"] in yield_map:
                yield_map[att["query"]].append(rid)
            else:
                extra_yield.setdefault(att["query"], []).append(rid)
    per_query_yield = [{"query": q, "records": ids, "count": len(ids),
                        "declared_query": True}
                       for q, ids in yield_map.items()]
    for q, ids in extra_yield.items():
        per_query_yield.append({"query": q, "records": ids, "count": len(ids),
                                "declared_query": False})
    coverage = {
        "case_id": case_id,
        "candidate_pool_key": pool_key,
        "queries": queries,
        "record_ids": [r["record_id"] for r in records],
        "records": records,
        "attributions": attributions,
        "unattributed_register": unattributed,
        "per_query_yield": per_query_yield,
        "stats": {
            "total_records": len(records),
            "query_count": len(queries),
            "attributed_explicit": sum(1 for a in attributions
                                       if a["method"] == "explicit"),
            "attributed_inferred": sum(1 for a in attributions
                                       if a["method"] == "inferred"),
            "unattributed": len(unattributed),
        },
        "missing_metadata": missing_meta,
        "notes": [
            "attribution precedence: explicit source field > inferred overlap "
            "> unattributed register",
            "inferred attributions are heuristic; matched_tokens are the audit "
            "trail",
            "a finite snapshot: records never retrieved by any query cannot "
            "appear here at all",
        ],
    }
    dump_json(coverage, args.out)
    print("map: case_id=%s records=%d queries=%d explicit=%d inferred=%d "
          "unattributed=%d missing_meta=%d -> %s"
          % (case_id, len(records), len(queries),
             coverage["stats"]["attributed_explicit"],
             coverage["stats"]["attributed_inferred"],
             len(unattributed), len(missing_meta), args.out))


# ---------------------------------------------------------------------------
# duplicate / version register
# ---------------------------------------------------------------------------

def is_preprint(rec):
    v = rec.get("venue")
    if isinstance(v, str) and any(h in v.lower() for h in PREPRINT_HINTS):
        return True
    t = rec.get("type") or rec.get("publication_type")
    return isinstance(t, str) and "preprint" in t.lower()


def choose_canonical(member_triples):
    """member_triples: list of (rid, rec, idx). Published venue over preprint,
    else newer year, else first."""
    def keyf(m):
        _rid, rec, idx = m
        year = rec.get("year")
        year = year if isinstance(year, int) else 0
        return (1 if is_preprint(rec) else 0, -year, idx)
    return sorted(member_triples, key=keyf)[0][0]


def build_duplicate_register(cands, known_ids):
    """Conservative register. Returns (entries, suspected_pairs).

    Merge basis: exact DOI match OR normalized-title exact match. Fuzzy
    suspected pairs (title-token Jaccard >= SUSPECT_JACCARD) are NOT merged;
    they go to the review queue.
    """
    pairs = [(known_ids[i], cands[i]) for i in range(len(cands))]
    index = {rid: i for i, (rid, _r) in enumerate(pairs)}
    keys, basis = {}, {}
    for rid, rec in pairs:
        doi = rec.get("doi")
        if isinstance(doi, str) and doi.strip():
            k = "doi:" + doi.strip().lower()
            keys.setdefault(k, []).append(rid)
            basis[k] = "exact DOI match"
        nt = normalize_title(rec.get("title") or "")
        if nt:
            k = "title:" + nt
            keys.setdefault(k, []).append(rid)
            basis[k] = "normalized-title exact match"
    parent = {rid: rid for rid in known_ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for k, ids in keys.items():
        if len(ids) > 1:
            for other in ids[1:]:
                union(ids[0], other)
    comp, comp_keys = {}, {}
    for k, ids in keys.items():
        if len(ids) > 1:
            root = find(ids[0])
            comp.setdefault(root, set()).update(ids)
            comp_keys.setdefault(root, []).append(k)
    rec_of = dict(pairs)
    entries, canonical_of = [], {}
    for root, members in sorted(comp.items(),
                                key=lambda kv: min(index[m] for m in kv[1])):
        members_sorted = sorted(members, key=lambda m: index[m])
        triples = [(m, rec_of[m], index[m]) for m in members_sorted]
        canonical = choose_canonical(triples)
        entries.append({
            "type": "merged",
            "canonical": canonical,
            "members": members_sorted,
            "merged_from": [m for m in members_sorted if m != canonical],
            "match_basis": sorted({basis[k] for k in comp_keys[root]}),
            "canonical_rule": "published venue over preprint, else newer year, "
                              "else first",
        })
        for m in members_sorted:
            canonical_of[m] = canonical
    for rid, rec in pairs:
        fn = rec.get("fixture_note") or rec.get("fixture")
        if isinstance(fn, str) and fn.strip():
            entries.append({
                "type": "fixture_declared",
                "record_id": rid,
                "fixture_note": fn.strip(),
                "provenance_only": True,
                "note": "input fixture label quoted verbatim as provenance; "
                        "never treated as ground truth",
                "linked_merged_group_canonical": canonical_of.get(rid),
            })
    tok = {rid: content_tokens(rec.get("title") or "") for rid, rec in pairs}
    suspected = []
    ids = [rid for rid, _r in pairs]
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            if a in canonical_of and b in canonical_of:
                continue  # already handled by an exact merge
            ta, tb = tok[a], tok[b]
            if not ta or not tb:
                continue
            sim = len(ta & tb) / len(ta | tb)
            if sim >= SUSPECT_JACCARD:
                suspected.append({
                    "type": "suspected_only",
                    "record_ids": [a, b],
                    "title_token_jaccard": round(sim, 3),
                    "action": "review queue only — NOT merged (below the "
                              "conservative exact-match threshold)"})
    return entries, suspected


# ---------------------------------------------------------------------------
# account
# ---------------------------------------------------------------------------

def omission_text(omission, summary):
    parts = [omission["finite_snapshot_disclaimer"]]
    if omission["missing_metadata"]:
        gaps = ["%s lacks %s" % (m["record_id"], "/".join(m["missing"]))
                for m in omission["missing_metadata"]]
        parts.append("Missing metadata: " + "; ".join(gaps) + ".")
    if omission["unattributed_records"]:
        parts.append("Records not attributable to any actual query: "
                     + ", ".join(omission["unattributed_records"]) + ".")
    if omission["suspected_duplicate_review_queue"]:
        pairs = ["%s~%s" % tuple(s["record_ids"])
                 for s in omission["suspected_duplicate_review_queue"]]
        parts.append("Suspected (not merged) duplicate pairs awaiting human "
                     "review: " + ", ".join(pairs) + ".")
    parts.append("Accounting: %d input records -> keep %d / pending %d / "
                 "exclude %d; every record accounted for exactly once."
                 % (summary["input_records"], summary["keep"],
                    summary["pending"], summary["exclude"]))
    return " ".join(parts)


def cmd_account(args):
    case = load_json(args.case)
    coverage = load_json(args.coverage)
    case_id = coverage.get("case_id") or find_case_id(case, args.case)
    cands, _ = find_candidates(case)
    known_ids = [record_id_of(r, i) for i, r in enumerate(cands)]
    known = set(known_ids)
    rec_by_id = {record_id_of(r, i): r for i, r in enumerate(cands)}
    att_by_id = {a["record_id"]: a for a in coverage.get("attributions", [])}
    change_records, rejected, incomplete, limits = [], [], [], []

    decisions_raw, decisions_provided = [], False
    if args.decisions:
        p = Path(args.decisions)
        if p.exists():
            decisions_provided = True
            raw = load_json(str(p))
            if isinstance(raw, dict):
                decisions_raw = raw.get("decisions") or []
            elif isinstance(raw, list):
                decisions_raw = raw
        else:
            limits.append("decisions file %s not found; degraded to "
                          "all-pending" % args.decisions)

    # ---- ingest decisions; enforce the accounting identity deterministically
    by_id, seen_dec = {}, set()
    for d in decisions_raw:
        if not isinstance(d, dict):
            rejected.append({"entry": str(d)[:120],
                             "reason": "decision entry is not an object"})
            change_records.append({
                "type": "repair", "action": "rejected_decision",
                "detail": str(d)[:120],
                "reason": "decision entry is not an object; moved to "
                          "rejected_register"})
            continue
        rid = d.get("record_id")
        if rid is None or str(rid) not in known:
            rejected.append({"record_id": rid, "bucket": d.get("bucket"),
                             "reason": "unknown record_id; no such record in "
                                       "the input snapshot"})
            change_records.append({
                "type": "repair", "action": "rejected_decision",
                "record_id": rid,
                "reason": "decision references an id not present in the input "
                          "snapshot; moved to rejected_register, bucket "
                          "unchanged for all real records"})
            continue
        rid = str(rid)
        if rid in seen_dec:
            change_records.append({
                "type": "repair", "action": "duplicate_decision_dropped",
                "record_id": rid,
                "reason": "second decision for the same record_id; first "
                          "occurrence kept, this one dropped"})
            continue
        seen_dec.add(rid)
        by_id[rid] = d

    screened = []
    for rid in known_ids:
        d = by_id.get(rid)
        rec = rec_by_id[rid]
        if d is None:
            entry = {"record_id": rid, "bucket": "pending",
                     "rationale": "not judged (honest pending; no decision "
                                  "fabricated)",
                     "quote": None}
            if decisions_provided:
                change_records.append({
                    "type": "repair", "action": "missing_decision_defaulted",
                    "record_id": rid,
                    "reason": "no decision supplied for this input record; "
                              "defaulted to pending 'not judged' to preserve "
                              "the accounting identity"})
        else:
            bucket = d.get("bucket")
            if bucket not in BUCKETS:
                change_records.append({
                    "type": "repair", "action": "invalid_bucket_defaulted",
                    "record_id": rid,
                    "reason": "bucket %r not in {keep,pending,exclude}; "
                              "defaulted to pending" % (bucket,)})
                bucket = "pending"
            quote = d.get("quote")
            if quote is not None:
                hay = "%s\n%s" % (rec.get("title") or "",
                                  rec.get("abstract") or "")
                if not isinstance(quote, str) or quote not in hay:
                    change_records.append({
                        "type": "repair", "action": "quote_nulled",
                        "record_id": rid,
                        "reason": "quote is not a verbatim substring of the "
                                  "record's title/abstract; set to null "
                                  "rather than risk fabrication"})
                    quote = None
            entry = {"record_id": rid, "bucket": bucket,
                     "rationale": d.get("rationale") or "", "quote": quote}
        entry["attribution"] = att_by_id.get(rid)
        screened.append(entry)

    counts = {b: sum(1 for s in screened if s["bucket"] == b) for b in BUCKETS}
    if not decisions_provided:
        incomplete.append({
            "part": "decisions",
            "reason": "no decisions file supplied (script-only degraded "
                      "path); all %d records are pending 'not judged' — an "
                      "honest partial, not a screening result"
                      % len(screened)})
    elif counts["pending"]:
        incomplete.append({
            "part": "decisions",
            "reason": "%d of %d records remain pending"
                      % (counts["pending"], len(screened))})
    if rejected:
        limits.append("%d decision(s) rejected (unknown ids / malformed "
                      "entries); see rejected_register and change_records"
                      % len(rejected))

    dup_register, suspected = build_duplicate_register(cands, known_ids)
    merged_groups = [e for e in dup_register if e["type"] == "merged"]

    omission = {
        "finite_snapshot_disclaimer":
            "The candidate pool is a finite snapshot of %d records shipped "
            "with the case. No live database was queried; recall beyond this "
            "snapshot cannot be claimed, and the set of relevant records the "
            "snapshot omits is unknown by construction." % len(screened),
        "per_query_yield": coverage.get("per_query_yield", []),
        "unattributed_records": [u["record_id"]
                                 for u in coverage.get("unattributed_register", [])],
        "missing_metadata": coverage.get("missing_metadata", []),
        "suspected_duplicate_review_queue": suspected,
    }

    summary = {
        "input_records": len(screened),
        "keep": counts["keep"],
        "pending": counts["pending"],
        "exclude": counts["exclude"],
        "accounted_total": sum(counts.values()),
        "accounting_identity_holds": sum(counts.values()) == len(known_ids),
        "queries": len(coverage.get("queries", [])),
        "duplicate_groups_merged": len(merged_groups),
        "fixture_declared_entries": sum(1 for e in dup_register
                                        if e["type"] == "fixture_declared"),
        "suspected_pairs_for_review": len(suspected),
        "rejected_decisions": len(rejected),
    }
    uncertainty = []
    n_inferred = sum(1 for a in coverage.get("attributions", [])
                     if a.get("inferred"))
    if n_inferred:
        uncertainty.append("%d record(s) attributed to queries by term "
                           "overlap (inferred:true); heuristic — review "
                           "matched_tokens before trusting per-query yield"
                           % n_inferred)
    if any(e["type"] == "fixture_declared" for e in dup_register):
        uncertainty.append("fixture_note labels are input provenance quoted "
                           "verbatim, never ground truth")
    uncertainty.append("finite snapshot: no recall beyond the supplied "
                       "records can be claimed")
    if counts["pending"]:
        uncertainty.append("%d record(s) are pending — undecided, not "
                           "screened out" % counts["pending"])

    completed = ["snapshot mapping (map)", "per-query yield",
                 "exact all-record accounting", "duplicate/version register",
                 "omission statement"]
    if decisions_provided and not counts["pending"]:
        completed.append("record decisions")

    result = {
        "case_id": case_id,
        "screened_records": screened,
        "query_coverage": {
            "queries": coverage.get("queries", []),
            "per_query_yield": coverage.get("per_query_yield", []),
            "stats": coverage.get("stats", {}),
            "unattributed_register": coverage.get("unattributed_register", []),
        },
        "duplicate_register": dup_register,
        "rejected_register": rejected,
        "omission_statement": omission,
        "summary": summary,
        "status": {
            "state": "partial" if incomplete else "complete",
            "completed": completed,
            "incomplete": incomplete,
            "limits": limits,
        },
        "uncertainty": uncertainty,
        "change_records": change_records,
    }

    # Mirror every declared contract field; never drop one silently.
    contract_fields = find_contract_fields(case)
    if not contract_fields:
        result["status"]["limits"].append(
            "case declares no output_contract; standard payload keys only")
    for f in contract_fields:
        name = f["name"]
        if name in result:
            continue
        if isinstance(case, dict) and name in case and name not in CANDIDATE_KEYS:
            result[name] = case[name]  # echo real same-named input field
        elif any(t in name.lower() for t in ("omission", "coverage", "note")):
            result[name] = omission_text(omission, summary)
        else:
            result[name] = None
            result["status"]["incomplete"].append({
                "part": "contract field '%s'" % name,
                "reason": "declared by output_contract but not producible "
                          "from available input; emitted as explicit null"})
            result["status"]["state"] = "partial"

    dump_json(result, args.out)
    print("account: state=%s records=%d keep=%d pending=%d exclude=%d "
          "merged_groups=%d suspected=%d rejected=%d repairs=%d -> %s"
          % (result["status"]["state"], len(screened), counts["keep"],
             counts["pending"], counts["exclude"], len(merged_groups),
             len(suspected), len(rejected), len(change_records), args.out))


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

def cmd_validate(args):
    case = load_json(args.case)
    result = load_json(args.result)
    case_id = find_case_id(case, args.case)
    cands, _ = find_candidates(case)
    known_ids = [record_id_of(r, i) for i, r in enumerate(cands)]
    known = set(known_ids)
    rec_by_id = {record_id_of(r, i): r for i, r in enumerate(cands)}
    problems = []

    if result.get("case_id") != case_id:
        problems.append("case_id mismatch: result=%r expected=%r"
                        % (result.get("case_id"), case_id))
    contract_fields = find_contract_fields(case)
    for f in contract_fields:
        if f["name"] not in result:
            problems.append("contract field missing from result: %s" % f["name"])

    screened = result.get("screened_records") or []
    seen = [s.get("record_id") for s in screened if isinstance(s, dict)]
    dup = sorted({x for x in seen if seen.count(x) > 1})
    if dup:
        problems.append("duplicate record_ids across buckets: %s" % dup)
    missing = [r for r in known_ids if r not in seen]
    extra = [r for r in seen if r not in known]
    if missing:
        problems.append("input records missing from buckets: %s" % missing)
    if extra:
        problems.append("unknown record_ids in buckets: %s" % extra)
    counts = {b: 0 for b in BUCKETS}
    for s in screened:
        b = s.get("bucket")
        if b not in counts:
            problems.append("bad bucket for %s: %r" % (s.get("record_id"), b))
        else:
            counts[b] += 1
    total = sum(counts.values())
    if total != len(known_ids):
        problems.append("accounting identity broken: |input|=%d but "
                        "keep+pending+exclude=%d" % (len(known_ids), total))
    for s in screened:
        q = s.get("quote")
        if q is None:
            continue
        rec = rec_by_id.get(s.get("record_id"))
        if rec is None:
            continue  # unknown id already reported above
        hay = "%s\n%s" % (rec.get("title") or "", rec.get("abstract") or "")
        if not isinstance(q, str) or q not in hay:
            problems.append("quote for %s is not a verbatim substring of that "
                            "record's title/abstract" % s.get("record_id"))
    for e in result.get("duplicate_register") or []:
        if not isinstance(e, dict):
            problems.append("duplicate_register entry is not an object: %r"
                            % (e,))
            continue
        for key in ("canonical", "record_id"):
            v = e.get(key)
            if v is not None and v not in known:
                problems.append("duplicate_register references unknown id "
                                "%r (field %s)" % (v, key))
        for key in ("members", "merged_from", "record_ids"):
            for v in e.get(key) or []:
                if v not in known:
                    problems.append("duplicate_register references unknown id "
                                    "%r (field %s)" % (v, key))
    if not isinstance(result.get("status"), dict) \
            or "state" not in result.get("status", {}):
        problems.append("status.state missing")

    if problems:
        print("VALIDATE FAIL")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    print("VALIDATE PASS: case_id=%s records=%d buckets=keep:%d/pending:%d/"
          "exclude:%d contract_fields=%d state=%s"
          % (case_id, len(seen), counts["keep"], counts["pending"],
             counts["exclude"], len(contract_fields),
             result["status"]["state"]))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("map", help="build source-attribution and coverage ledger")
    p.add_argument("--case", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_map)
    p = sub.add_parser("account", help="assemble result.json with accounting identity")
    p.add_argument("--case", required=True)
    p.add_argument("--coverage", required=True)
    p.add_argument("--decisions")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_account)
    p = sub.add_parser("validate", help="verify identity, quotes, register, contract")
    p.add_argument("--case", required=True)
    p.add_argument("--result", required=True)
    p.set_defaults(fn=cmd_validate)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
