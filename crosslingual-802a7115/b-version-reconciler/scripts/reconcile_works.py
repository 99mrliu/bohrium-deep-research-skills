#!/usr/bin/env python3
"""Cross-language work reconciliation and deduplicated counting.

Stdlib only (Python 3.8+). Deterministic, offline. Stage 2 of the
xlang-version-reconciler skill.

What it does
------------
1. Reads the stage-1 report (langid_report.json, auto-located or via
   --report), which embeds per-record features extracted from the original
   records (DOI, folded title tokens, folded author surnames, year/volume/
   issue/first-page fingerprint, language + version-type decisions, text
   hash, source locators). Optionally re-scans the original record files
   (--roots, same discovery rules as stage 1) to enrich explicit relation
   fields (translation_of / duplicate_of / relation[].type) keyed by DOI.
2. Merges records into WORKS across languages using a transparent additive
   score over independent signals (weights and thresholds live in
   rules/version_policy.md):
     explicit translation/duplicate relation ....... +1.00 (decisive)
     identical normalized DOI ....................... +0.90 (decisive)
     same DOI prefix + suffix similarity >= 0.80 .... +0.35
     folded title token Jaccard >= 0.80 / >= 0.50 ... +0.50 / +0.25
     numeric-token Jaccard >= 0.50 .................. +0.15
     first-author surname match + surname J >= 0.60 . +0.30
     surname set Jaccard >= 0.60 .................... +0.20
     year+volume+first-page all equal ............... +0.35
     year+volume equal .............................. +0.15
     year equal ..................................... +0.05
     conflicting volume or first page ............... -0.30
     year differs by > 1 ............................ -0.30
   Score >= 0.75  -> merge (confidence high if a decisive signal fired,
   else medium). 0.55 <= score < 0.75 -> NOT merged: listed as a rejected
   candidate pair in the decision log and in uncertainty (evidence
   insufficient; records stay separate rather than guessed together).
3. Inside each work, collapses exact-duplicate records (stage-1
   duplicate_of) into a single VERSION view carrying every source locator.
4. Emits work groups (each with its version views: source locator, DOI,
   version type, body language), the full merge decision log (signals +
   weights + confidence), deduplicated counts (raw records vs distinct
   versions vs distinct works, per language), and the orphan list (records
   that merged with nothing, with the reason).
5. With --case, assembles /app/output/result.json mirroring the case
   output_contract, with honest status (ok/partial/failed), sources,
   uncertainty and change_records. Also writes a human-readable
   version_table.md.

Nothing is fabricated: a merge happens only on logged evidence, and any
pair with insufficient evidence stays split.

Usage
-----
    python3 reconcile_works.py [--report /app/work/langid_report.json] \
        [--roots /input,/app/work,.] [--case /input/case.json] \
        [--out /app/output] [--workdir /app/work]

Exit code is 0 even for partial results; the status field carries the truth.
"""
import argparse
import difflib
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

# ----------------------------------------------------------------------------- config

REPORT_CANDIDATES = ["/app/work/langid_report.json", "./langid_report.json",
                     "langid_report.json"]
MERGE_THRESHOLD = 0.75
CANDIDATE_THRESHOLD = 0.55
DOI_SUFFIX_SIM = 0.80

W_EXPLICIT_RELATION = 1.00
W_SAME_DOI = 0.90
W_DOI_SUFFIX = 0.35
W_TITLE_HIGH = 0.50
W_TITLE_MID = 0.25
W_NUMERIC_TOKENS = 0.15
W_FIRST_AUTHOR_SET = 0.30
W_AUTHOR_SET = 0.20
W_BIBLIO_FULL = 0.35
W_BIBLIO_YEAR_VOL = 0.15
W_YEAR_ONLY = 0.05
PEN_VOLUME_CONFLICT = -0.30
PEN_YEAR_GAP = -0.30

TITLE_BONUS_HIGH = 0.80
TITLE_BONUS_MID = 0.50
AUTHOR_SET_MIN = 0.60

STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "in", "on", "for", "to", "with",
    "by", "from", "at", "as", "is", "are", "was", "were", "be", "been",
    "de", "la", "el", "los", "las", "del", "una", "uno", "dos", "das",
    "des", "les", "der", "die", "und", "ou", "em", "no", "na", "nos",
    "um", "uma", "en", "et", "au", "aux", "du", "le", "il", "di", "da",
}

# ----------------------------------------------------------------------------- utils


def norm_doi(value):
    if not value:
        return None
    v = str(value).strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:"):
        if v.startswith(prefix):
            v = v[len(prefix):]
    return v.rstrip(".;,") or None


def doi_parts(doi):
    if not doi or "/" not in doi:
        return None, None
    prefix, suffix = doi.split("/", 1)
    return prefix, suffix


def fold(value):
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value))
    return "".join(c for c in decomposed
                   if unicodedata.category(c) != "Mn").lower()


def title_tokens(value):
    folded = fold(value)
    toks = re.findall(r"[a-z0-9]+", folded)
    return {t for t in toks if t and t not in STOPWORDS}


def numeric_tokens(value):
    return {t for t in re.findall(r"[a-z0-9]+", fold(value))
            if any(ch.isdigit() for ch in t)}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))

# ------------------------------------------------------------------------- union-find


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)

# ------------------------------------------------------------- relation enrichment


def enrich_relations(roots, records_by_doi, log):
    """Best-effort re-scan of original JSON/JSONL files for explicit relation
    fields (translation_of / duplicate_of / relation[].type) keyed by DOI.
    Returns {doi: {"translation_of": ..., "duplicate_of": ...}}."""
    found = {}
    if not roots:
        return found
    exts = (".json", ".jsonl", ".ndjson")
    files = []
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        stack = [(root, 0)]
        while stack and len(files) < 400:
            node, depth = stack.pop()
            try:
                if node.is_dir():
                    if node.name.startswith(".") or node.name in (
                            "node_modules", "__pycache__", "output"):
                        continue
                    if depth <= 6:
                        for child in sorted(node.iterdir()):
                            stack.append((child, depth + 1))
                elif node.suffix.lower() in exts and node.name not in (
                        "result.json", "langid_report.json",
                        "reconcile_report.json", "case.json"):
                    files.append(node)
            except (OSError, PermissionError):
                continue

    def scan_obj(obj):
        if not isinstance(obj, dict):
            return
        doi = norm_doi(obj.get("DOI") or obj.get("doi"))
        if doi and doi in records_by_doi:
            entry = found.setdefault(doi, {})
            for k in ("translation_of", "is_translation_of", "isTranslationOf",
                      "original_doi", "translated_from"):
                v = obj.get(k)
                if isinstance(v, str) and v.strip():
                    entry.setdefault("translation_of",
                                     norm_doi(v) or v.strip())
            for k in ("duplicate_of", "is_duplicate_of", "duplicateOf"):
                v = obj.get(k)
                if isinstance(v, str) and v.strip():
                    entry.setdefault("duplicate_of", norm_doi(v) or v.strip())
            rel = obj.get("relation")
            items = []
            if isinstance(rel, dict):
                items = list(rel.items())
            elif isinstance(rel, list):
                for it in rel:
                    if isinstance(it, dict):
                        items.append((it.get("type") or "",
                                      it.get("doi") or it.get("id")
                                      or it.get("value") or ""))
            for typ, val in items:
                tval = norm_doi(val) or (str(val).strip() if val else None)
                if not tval:
                    continue
                if "translat" in str(typ).lower():
                    entry.setdefault("translation_of", tval)
                if "duplicat" in str(typ).lower():
                    entry.setdefault("duplicate_of", tval)

    def walk(o, depth=0):
        if depth > 12:
            return
        if isinstance(o, dict):
            scan_obj(o)
            for v in o.values():
                walk(v, depth + 1)
        elif isinstance(o, list):
            for v in o[:20000]:
                walk(v, depth + 1)

    for path in files:
        try:
            if path.suffix.lower() == ".json":
                with open(path, encoding="utf-8", errors="replace") as fh:
                    walk(json.load(fh))
            else:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            try:
                                walk(json.loads(line))
                            except json.JSONDecodeError:
                                continue
        except (OSError, json.JSONDecodeError):
            continue
    if found:
        log.append("relation enrichment: %d DOI(s) gained explicit "
                   "translation/duplicate relations from original files"
                   % len(found))
    return found

# ---------------------------------------------------------------- pair scoring


def score_pair(a, b, relations):
    """Compute the additive merge score for a record pair. Returns
    (score, signals, decisive) where signals is a list of
    {signal, weight, detail}."""
    signals = []

    def add(name, weight, detail):
        signals.append({"signal": name, "weight": weight, "detail": detail})

    decisive = False
    doi_a, doi_b = norm_doi(a.get("doi")), norm_doi(b.get("doi"))

    # explicit relations (stage-1 fields enriched by original-file rescan)
    rel_a = relations.get(doi_a, {}) if doi_a else {}
    rel_b = relations.get(doi_b, {}) if doi_b else {}
    explicit = None
    for src, tgt, kind in (
            (a.get("translation_of"), doi_b, "translation_of"),
            (b.get("translation_of"), doi_a, "translation_of"),
            (rel_a.get("translation_of"), doi_b, "translation_of(enriched)"),
            (rel_b.get("translation_of"), doi_a, "translation_of(enriched)"),
    ):
        if src and norm_doi(src) == tgt:
            explicit = kind
            break
    dup_pair = (a.get("duplicate_of") == b.get("record_id")
                or b.get("duplicate_of") == a.get("record_id"))
    if explicit:
        add("explicit_relation", W_EXPLICIT_RELATION,
            "%s declares %s -> other record's DOI"
            % (a["record_id"] if a.get("translation_of") or
               rel_a.get("translation_of") else b["record_id"], explicit))
        decisive = True
    elif dup_pair:
        add("explicit_duplicate", W_EXPLICIT_RELATION,
            "stage-1 exact-duplicate linkage")
        decisive = True

    if doi_a and doi_b and doi_a == doi_b:
        add("same_doi", W_SAME_DOI,
            "identical normalized DOI %s (same work; differing body languages "
            "are versions, not different works)" % doi_a)
        decisive = True
    elif doi_a and doi_b:
        pa, sa = doi_parts(doi_a)
        pb, sb = doi_parts(doi_b)
        if pa and pa == pb and sa and sb:
            sim = difflib.SequenceMatcher(None, sa, sb).ratio()
            if sim >= DOI_SUFFIX_SIM and sa != sb:
                add("doi_prefix_suffix_relation", W_DOI_SUFFIX,
                    "same DOI prefix %s, suffix similarity %.2f (%s vs %s)"
                    % (pa, sim, sa, sb))

    ta, tb = title_tokens(a.get("title")), title_tokens(b.get("title"))
    tj = jaccard(ta, tb)
    if tj >= TITLE_BONUS_HIGH:
        add("title_token_jaccard_high", W_TITLE_HIGH,
            "folded title token Jaccard %.2f >= %.2f" % (tj, TITLE_BONUS_HIGH))
    elif tj >= TITLE_BONUS_MID:
        add("title_token_jaccard_mid", W_TITLE_MID,
            "folded title token Jaccard %.2f >= %.2f" % (tj, TITLE_BONUS_MID))
    nj = jaccard(numeric_tokens(a.get("title")), numeric_tokens(b.get("title")))
    if nj >= 0.5 and tj < TITLE_BONUS_MID:
        add("numeric_title_tokens", W_NUMERIC_TOKENS,
            "numeric/proper token Jaccard %.2f (helps translated titles "
            "sharing numerals)" % nj)

    sa_list = a.get("author_surnames_folded") or []
    sb_list = b.get("author_surnames_folded") or []
    set_a, set_b = set(sa_list), set(sb_list)
    aj = jaccard(set_a, set_b)
    first_match = bool(sa_list and sb_list and sa_list[0] == sb_list[0])
    if first_match and aj >= AUTHOR_SET_MIN:
        add("first_author_and_surname_set", W_FIRST_AUTHOR_SET,
            "first-author surname '%s' matches and surname-set Jaccard %.2f"
            % (sa_list[0], aj))
    elif aj >= AUTHOR_SET_MIN:
        add("surname_set_jaccard", W_AUTHOR_SET,
            "surname-set Jaccard %.2f >= %.2f" % (aj, AUTHOR_SET_MIN))

    ya, yb = a.get("year"), b.get("year")
    va = str(a.get("volume") or "").strip()
    vb = str(b.get("volume") or "").strip()
    pa_ = str(a.get("first_page") or "").strip()
    pb_ = str(b.get("first_page") or "").strip()
    if ya and yb and va and vb and pa_ and pb_ \
            and ya == yb and va == vb and pa_ == pb_:
        add("biblio_fingerprint_full", W_BIBLIO_FULL,
            "year=%s volume=%s first_page=%s all equal" % (ya, va, pa_))
    elif ya and yb and ya == yb and va and vb and va == vb:
        add("biblio_year_volume", W_BIBLIO_YEAR_VOL,
            "year=%s volume=%s equal" % (ya, va))
    elif ya and yb and ya == yb:
        add("year_equal", W_YEAR_ONLY, "year=%s equal" % ya)
    if ya and yb and abs(int(ya) - int(yb)) > 1:
        add("year_gap_penalty", PEN_YEAR_GAP,
            "year gap %s vs %s > 1" % (ya, yb))
    if va and vb and va != vb:
        add("volume_conflict_penalty", PEN_VOLUME_CONFLICT,
            "volume %s vs %s conflict" % (va, vb))
    if pa_ and pb_ and pa_ != pb_ and not (va and vb and va != vb):
        add("first_page_conflict_penalty", PEN_VOLUME_CONFLICT,
            "first page %s vs %s conflict" % (pa_, pb_))

    score = round(sum(s["weight"] for s in signals), 3)
    return score, signals, decisive

# ------------------------------------------------------------------- main logic


def load_report(path):
    with open(path, encoding="utf-8") as fh:
        report = json.load(fh)
    if not isinstance(report.get("records"), list):
        raise ValueError("report has no records list")
    return report


def find_report(explicit):
    if explicit:
        return explicit
    for cand in REPORT_CANDIDATES:
        if Path(cand).exists():
            return cand
    return None


def reconcile(records, relations, log):
    uf = UnionFind()
    by_id = {r["record_id"]: r for r in records}

    # candidate blocking: DOI prefix, first surname+year, year+venue
    blocks = {}
    for r in records:
        keys = set()
        doi = norm_doi(r.get("doi"))
        if doi:
            prefix, _ = doi_parts(doi)
            keys.add("doi:" + doi)
            if prefix:
                keys.add("doiprefix:" + prefix)
        surs = r.get("author_surnames_folded") or []
        if surs and r.get("year"):
            keys.add("suryr:%s|%s" % (surs[0], r["year"]))
        if r.get("year") and r.get("venue"):
            keys.add("yrven:%s|%s" % (r["year"], fold(r["venue"])[:40]))
        for k in keys:
            blocks.setdefault(k, []).append(r["record_id"])

    candidate_pairs = set()
    for ids in blocks.values():
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                candidate_pairs.add(tuple(sorted((ids[i], ids[j]))))
    # exact-duplicate pairs are always candidates
    for r in records:
        if r.get("duplicate_of") and r["duplicate_of"] in by_id:
            candidate_pairs.add(tuple(sorted((r["record_id"],
                                              r["duplicate_of"]))))

    merge_decisions, rejected = [], []
    for ida, idb in sorted(candidate_pairs):
        a, b = by_id[ida], by_id[idb]
        score, signals, decisive = score_pair(a, b, relations)
        if score >= MERGE_THRESHOLD:
            uf.union(ida, idb)
            confidence = "high" if decisive else "medium"
            merge_decisions.append({
                "pair": [ida, idb],
                "decision": "merged",
                "score": score,
                "confidence": confidence,
                "signals": signals,
            })
        elif score >= CANDIDATE_THRESHOLD:
            rejected.append({
                "pair": [ida, idb],
                "decision": "kept_separate",
                "score": score,
                "reason": ("score %.2f in [%.2f, %.2f): evidence insufficient; "
                           "records stay split rather than guessed together"
                           % (score, CANDIDATE_THRESHOLD, MERGE_THRESHOLD)),
                "signals": signals,
            })

    groups = {}
    for r in records:
        groups.setdefault(uf.find(r["record_id"]), []).append(r)

    works, orphans = [], []
    for root_id, members in sorted(groups.items(),
                                   key=lambda kv: kv[0]):
        members.sort(key=lambda r: r["record_id"])
        # canonical representative: prefer original + most metadata
        def completeness(r):
            return sum(1 for k in ("doi", "title", "year", "venue",
                                   "authors") if r.get(k))
        originals = [r for r in members
                     if r.get("version_type") == "original"]
        canon = (sorted(originals, key=completeness, reverse=True)
                 or sorted(members, key=completeness, reverse=True))[0]

        # collapse exact duplicates into single version views
        versions = []
        dup_target = {r["record_id"]: r.get("duplicate_of")
                      for r in members if r.get("duplicate_of")}
        absorbed = set(dup_target.keys())
        for r in members:
            if r["record_id"] in absorbed:
                continue
            locs = [r["locator"]]
            dup_ids = []
            for did, tgt in dup_target.items():
                if tgt == r["record_id"]:
                    d = by_id[did]
                    locs.append(d["locator"])
                    dup_ids.append(did)
            versions.append({
                "version_id": "%s/v%d" % (root_id, len(versions) + 1),
                "record_ids": [r["record_id"]] + dup_ids,
                "doi": r.get("doi"),
                "title": r.get("title"),
                "version_type": r.get("version_type"),
                "version_confidence": r.get("version_confidence"),
                "body_language": r.get("body_language"),
                "metadata_languages": r.get("metadata_languages"),
                "text_availability": r.get("text_availability"),
                "sources": locs,
                "duplicate_locators_absorbed": len(dup_ids),
                "conflicts": r.get("conflicts") or [],
            })
        works.append({
            "work_id": "work:%s" % root_id,
            "canonical": {
                "doi": canon.get("doi"),
                "title": canon.get("title"),
                "year": canon.get("year"),
                "venue": canon.get("venue"),
                "author_surnames_folded": canon.get("author_surnames_folded"),
            },
            "n_versions": len(versions),
            "languages": sorted({(v.get("body_language") or {}).get("code")
                                 or "undetermined" for v in versions}),
            "version_types": sorted({v.get("version_type") or "undetermined"
                                     for v in versions}),
            "versions": versions,
        })
        if len(members) == 1:
            only = members[0]
            reason_bits = []
            if not norm_doi(only.get("doi")):
                reason_bits.append("no DOI")
            if not (only.get("author_surnames_folded") and only.get("year")):
                reason_bits.append("no author+year blocking key")
            related_rej = [rj for rj in rejected
                           if only["record_id"] in rj["pair"]]
            if related_rej:
                reason_bits.append(
                    "%d candidate pair(s) below merge threshold (see "
                    "rejected_candidates)" % len(related_rej))
            else:
                reason_bits.append("no candidate pair exceeded the "
                                   "candidate threshold %.2f"
                                   % CANDIDATE_THRESHOLD)
            orphans.append({"record_id": only["record_id"],
                            "doi": only.get("doi"),
                            "title": only.get("title"),
                            "locator": only.get("locator"),
                            "reason": "; ".join(reason_bits)})

    log.append("reconciled %d records into %d works (%d merge decisions, "
               "%d rejected candidate pairs, %d orphans)"
               % (len(records), len(works), len(merge_decisions),
                  len(rejected), len(orphans)))
    return works, merge_decisions, rejected, orphans


def count_table(records, works):
    n_records = len(records)
    n_versions = sum(w["n_versions"] for w in works)
    n_works = len(works)
    ver_lang, work_lang = {}, {}
    for w in works:
        for v in w["versions"]:
            code = (v.get("body_language") or {}).get("code") or "undetermined"
            ver_lang[code] = ver_lang.get(code, 0) + 1
        for code in w["languages"]:
            work_lang[code] = work_lang.get(code, 0) + 1
    return {
        "raw_records": n_records,
        "distinct_versions_after_exact_dedup": n_versions,
        "distinct_works_after_xlang_merge": n_works,
        "note": ("every metric must be counted at the WORK level; counting "
                 "raw records or versions inflates metrics when a work has "
                 "several language versions"),
        "by_body_language": {"version_level": ver_lang,
                             "work_level": work_lang},
    }

# ------------------------------------------------------------------------ main


def main():
    global MERGE_THRESHOLD, CANDIDATE_THRESHOLD
    ap = argparse.ArgumentParser(
        description="Cross-language work reconciliation and deduplicated "
                    "counting (stdlib only, offline).")
    ap.add_argument("--report", default=None,
                    help="path to langid_report.json (default: auto-locate "
                         "in /app/work or .)")
    ap.add_argument("--roots", default=None,
                    help="comma-separated roots of ORIGINAL record files for "
                         "best-effort relation enrichment (optional)")
    ap.add_argument("--case", default=None,
                    help="path to case.json; when given, result.json is "
                         "assembled under --out mirroring output_contract")
    ap.add_argument("--out", default="/app/output",
                    help="output directory for result.json (with --case)")
    ap.add_argument("--workdir", default="/app/work",
                    help="work directory for reconcile_report.json and logs")
    ap.add_argument("--merge-threshold", type=float, default=MERGE_THRESHOLD)
    ap.add_argument("--candidate-threshold", type=float,
                    default=CANDIDATE_THRESHOLD)
    args = ap.parse_args()
    MERGE_THRESHOLD = args.merge_threshold
    CANDIDATE_THRESHOLD = args.candidate_threshold

    started = time.time()
    work_dir = Path(args.workdir)
    try:
        work_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    log = ["reconcile_works started "
           + time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())]

    report_path = find_report(args.report)
    uncertainty = []
    if not report_path or not Path(report_path).exists():
        log.append("FATAL: langid_report.json not found (%s); run "
                   "langid_version.py first"
                   % (args.report or "auto-locate failed"))
        payload = {"status": "failed",
                   "uncertainty": ["stage-1 report langid_report.json not "
                                   "found; run scripts/langid_version.py "
                                   "first"],
                   "works": [], "merge_decisions": [], "sources": [],
                   "change_records": []}
        (work_dir / "reconcile_report.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": "failed",
                          "reason": "langid_report.json not found"}))
        return 0

    try:
        report = load_report(report_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        log.append("FATAL: cannot load report %s: %s" % (report_path, exc))
        payload = {"status": "failed",
                   "uncertainty": ["stage-1 report unreadable: %s" % exc],
                   "works": [], "merge_decisions": [], "sources": [],
                   "change_records": []}
        (work_dir / "reconcile_report.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": "failed", "reason": str(exc)}))
        return 0
    records = report.get("records", [])
    log.append("loaded %d records from %s" % (len(records), report_path))

    roots = [r.strip() for r in args.roots.split(",")] if args.roots else []
    by_doi = {norm_doi(r.get("doi")): r for r in records if r.get("doi")}
    relations = enrich_relations(roots, by_doi, log) if roots else {}

    works, merge_decisions, rejected, orphans = reconcile(records, relations,
                                                          log)
    counts = count_table(records, works)

    undetermined = [r["record_id"] for r in records
                    if (r.get("body_language") or {}).get("code")
                    == "undetermined"]
    conflicts = [(r["record_id"], c) for r in records
                 for c in (r.get("conflicts") or [])]
    if undetermined:
        uncertainty.append("%d record(s) have body_language=undetermined: %s "
                           "(insufficient text and metadata; NOT guessed)"
                           % (len(undetermined), ", ".join(undetermined[:10])))
    if conflicts:
        uncertainty.append("%d language-label conflict(s) resolved in favour "
                           "of the actual text; see per-record conflicts"
                           % len(conflicts))
    if rejected:
        uncertainty.append("%d candidate pair(s) scored in [%.2f, %.2f) and "
                           "were kept separate (evidence insufficient); see "
                           "rejected_candidates"
                           % (len(rejected), CANDIDATE_THRESHOLD,
                              MERGE_THRESHOLD))
    if report.get("parse_notes"):
        uncertainty.append("stage-1 parse notes: "
                           + "; ".join(report["parse_notes"][:5]))
    if orphans:
        uncertainty.append("%d orphan record(s) merged with nothing; listed "
                           "with reasons in orphans" % len(orphans))

    status = "ok"
    if undetermined or rejected or report.get("parse_notes"):
        status = "partial"

    reconcile_report = {
        "skill": "xlang-version-reconciler",
        "stage": "reconcile_works",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "parameters": {"merge_threshold": MERGE_THRESHOLD,
                       "candidate_threshold": CANDIDATE_THRESHOLD,
                       "report": report_path,
                       "roots_for_relation_enrichment": roots},
        "status": status,
        "counts": counts,
        "works": works,
        "merge_decisions": merge_decisions,
        "rejected_candidates": rejected,
        "orphans": orphans,
        "sources": report.get("sources", []),
        "uncertainty": uncertainty,
        "change_records": [],
    }
    (work_dir / "reconcile_report.json").write_text(
        json.dumps(reconcile_report, ensure_ascii=False, indent=2),
        encoding="utf-8")

    # human-readable version table
    lines = ["# 跨语种版本归并表（自动生成）", "",
             "| work | 版本 | DOI | 版本类型 | 正文语种 | 来源定位 |",
             "|-|-|-|-|-|-|"]
    for w in works:
        for v in w["versions"]:
            locs = "; ".join("%s %s" % (s.get("file", "?"), s.get("pointer", ""))
                             for s in v["sources"])
            lines.append("| %s | %s | %s | %s | %s | %s |" % (
                w["work_id"], v["version_id"], v.get("doi") or "-",
                v.get("version_type") or "?",
                (v.get("body_language") or {}).get("code") or "?",
                locs.replace("|", "\\|")))
    (work_dir / "version_table.md").write_text("\n".join(lines),
                                               encoding="utf-8")

    # optional Harbor result.json assembly
    if args.case:
        case = {}
        try:
            with open(args.case, encoding="utf-8") as fh:
                case = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            uncertainty.append("case file unreadable: %s" % exc)
            status = "partial"
        result = {
            "case_id": case.get("case_id") or case.get("id") or "unknown_case",
            "skill": "xlang-version-reconciler",
            "status": status,
            "counts": counts,
            "works": works,
            "merge_decisions": merge_decisions,
            "rejected_candidates": rejected,
            "orphans": orphans,
            "sources": report.get("sources", []),
            "evidence_records": log,
            "uncertainty": uncertainty,
            "change_records": [],
        }
        contract = case.get("output_contract")
        if isinstance(contract, dict):
            for field in contract:
                if field not in result:
                    result[field] = None
                    if not any(field in u for u in uncertainty):
                        uncertainty.append(
                            "output_contract field '%s' has no stage-2 "
                            "content; mirrored as null" % field)
            result["output_contract_fields"] = sorted(contract.keys())
        out_dir = Path(args.out)
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8")
            (out_dir / "version_table.md").write_text(
                "\n".join(lines), encoding="utf-8")
        except OSError as exc:
            log.append("WARNING: cannot write to %s: %s" % (out_dir, exc))
            (work_dir / "result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8")

    log.append("finished in %.1fs: works=%d versions=%d records=%d status=%s"
               % (time.time() - started, counts["distinct_works_after_xlang_merge"],
                  counts["distinct_versions_after_exact_dedup"],
                  counts["raw_records"], status))
    (work_dir / "reconcile_run_log.json").write_text(
        json.dumps({"log": log}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(json.dumps({"status": status,
                      "works": counts["distinct_works_after_xlang_merge"],
                      "versions": counts["distinct_versions_after_exact_dedup"],
                      "raw_records": counts["raw_records"],
                      "merges": len(merge_decisions),
                      "orphans": len(orphans)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
