#!/usr/bin/env python3
"""Graded relevance adjudication engine for graded-relevance-bench.

Turns a local candidate pool (organizer-provided Crossref / EuropePMC /
OpenAlex-shaped JSON snapshots, plus any raw responses the agent saved) into
defensible 0-3 graded relevance labels. Every point of every grade is backed
by an inspectable per-facet score decomposition with evidence snippets, and
borderline records are routed into an explicit adjudication queue instead of
being silently included or dropped.

Fully offline, Python 3 stdlib only. No network calls anywhere.

Usage:
  grade_relevance.py --case /input/case.json --input /input \
      [--corpus /app/work/corpus] [--work /app/work] --out /app/output \
      [--adjudicate /app/work/adjudications.json]

Exit codes: 0 = ran to completion, 2 = candidate pool empty,
3 = adjudication file invalid (unknown record ids or unreadable).
"""
import argparse
import hashlib
import json
import math
import os
import re
import sys

# ---------------------------------------------------------------- constants

QUESTION_KEYS = ("research_question", "researchQuestion", "question",
                 "query", "task", "prompt")

SKIP_BASENAMES = {"case.json", "result.json", "facets.json",
                  "adjudications.json", "borderline_queue.json",
                  "graded_candidates.json"}

STOPWORDS = frozenset("""
a an the and or of for to in on with without by from at as is are was were be
been being this that these those it its their his her our your we you they he
she which who whom what when where why how not no nor but if then than so such
into over under between about against during before after above below up down
out off again further once here there all any both each few more most other
some only own same too very can will just should could would may might must
shall do does did done have has had having i me my mine ours yours theirs
find search retrieve literature paper papers study studies review article
articles publication publications report reports relevant related using use
used based via within across among per
""".split())

CJK_RE = re.compile(r"[一-鿿]+")
TOKEN_RE = re.compile(r"[a-z][a-z0-9-]*")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+")
TAG_RE = re.compile(r"<[^>]+>")

# Contribution weights per facet status (see references/methodology.md).
W_TITLE_HIT = 1.0     # >=1 facet term found in the title
W_ABSTRACT_HIT = 0.6  # >=2 distinct facet terms found in the abstract
W_WEAK_HIT = 0.2      # exactly 1 facet term, abstract only
W_MISS = 0.0


# ---------------------------------------------------------------- io helpers

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


# ------------------------------------------------------- case & facet intake

def extract_question(case):
    for key in QUESTION_KEYS:
        val = case.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def content_terms(text):
    """Stopword-filtered content terms: lowercase alphabetic tokens (len > 2)
    plus bigrams of every CJK run (handles Chinese questions offline)."""
    terms = []
    seen = set()
    for tok in TOKEN_RE.findall(text.lower()):
        if len(tok) > 2 and tok not in STOPWORDS and tok not in seen:
            seen.add(tok)
            terms.append(tok)
    for run in CJK_RE.findall(text):
        for i in range(len(run) - 1):
            bg = run[i:i + 2]
            if bg not in seen:
                seen.add(bg)
                terms.append(bg)
    return terms


def load_facets(work_dir, question, notes):
    """Preferred: agent-authored <work>/facets.json with 2-5 conceptual facets
    ({"facets": [{"name": ..., "terms": [...]}, ...]}). Fallback: one facet
    per content term of the research question. Returns (facets, source)."""
    agent_path = os.path.join(work_dir, "facets.json") if work_dir else None
    if agent_path and os.path.isfile(agent_path):
        try:
            raw = read_json(agent_path)
            facets = []
            for f in raw.get("facets", []):
                name = str(f.get("name", "")).strip() or "facet%d" % len(facets)
                terms = sorted({str(t).strip().lower()
                                for t in f.get("terms", []) if str(t).strip()})
                if terms:
                    facets.append({"name": name, "terms": terms})
            if facets:
                if len(facets) > 5:
                    notes.append("facets.json has %d facets; only the first 5 "
                                 "are used" % len(facets))
                    facets = facets[:5]
                return facets, "agent-file:%s" % agent_path
            notes.append("facets.json contained no usable facets; fell back "
                         "to automatic extraction")
        except Exception as exc:  # malformed agent file -> fallback, noted
            notes.append("facets.json unreadable (%s); fell back to automatic "
                         "extraction" % exc)
    if not question:
        return [], "unavailable (no research question found in case.json)"
    facets = [{"name": t, "terms": [t]} for t in content_terms(question)]
    return facets, "fallback-auto (single-term facets from question; write " \
                   "%s to control facets and synonyms)" % (agent_path or
                                                           "facets.json")


# ------------------------------------------------------------- pool loading

def classify_payload(obj):
    """Return (shape, raw_records) for known snapshot shapes, else (None, [])."""
    if not isinstance(obj, dict):
        return None, []
    msg = obj.get("message")
    if isinstance(msg, dict) and isinstance(msg.get("items"), list):
        return "crossref", msg["items"]
    rl = obj.get("resultList")
    if isinstance(rl, dict) and isinstance(rl.get("result"), list):
        return "europepmc", rl["result"]
    if isinstance(obj.get("results"), list):
        return "openalex", obj["results"]
    if isinstance(obj.get("records"), list):
        return "generic", obj["records"]
    return None, []


def first_str(val):
    if isinstance(val, list):
        for v in val:
            if isinstance(v, str) and v.strip():
                return v.strip()
        return None
    if isinstance(val, str) and val.strip():
        return val.strip()
    return None


def clean_doi(doi):
    if not isinstance(doi, str):
        return None
    d = doi.strip().lower()
    for pre in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.startswith(pre):
            d = d[len(pre):]
    return d or None


def openalex_abstract(inv_index):
    if not isinstance(inv_index, dict):
        return None
    positions = []
    for word, poss in inv_index.items():
        for p in poss:
            positions.append((p, word))
    return " ".join(w for _p, w in sorted(positions)) or None


def normalize_record(raw, shape):
    """Shape-tolerant field extraction; missing metadata stays None."""
    rec = {"title": None, "authors": [], "year": None, "venue": None,
           "doi": None, "abstract": None}
    if not isinstance(raw, dict):
        return rec
    if shape == "crossref":
        rec["title"] = first_str(raw.get("title"))
        for a in raw.get("author") or []:
            if isinstance(a, dict):
                nm = " ".join(x for x in (a.get("given"), a.get("family")) if x)
                if nm.strip():
                    rec["authors"].append(nm.strip())
        try:
            rec["year"] = int(raw["issued"]["date-parts"][0][0])
        except Exception:
            rec["year"] = None
        rec["venue"] = first_str(raw.get("container-title"))
        rec["doi"] = clean_doi(raw.get("DOI"))
        abs_raw = raw.get("abstract")
        if isinstance(abs_raw, str):
            rec["abstract"] = TAG_RE.sub(" ", abs_raw).strip() or None
    elif shape == "europepmc":
        rec["title"] = first_str(raw.get("title"))
        astr = raw.get("authorString")
        if isinstance(astr, str):
            rec["authors"] = [a.strip() for a in astr.split(",") if a.strip()]
        try:
            rec["year"] = int(raw.get("pubYear"))
        except Exception:
            rec["year"] = None
        jinfo = raw.get("journalInfo")
        if isinstance(jinfo, dict) and isinstance(jinfo.get("journal"), dict):
            rec["venue"] = first_str(jinfo["journal"].get("title"))
        rec["venue"] = rec["venue"] or first_str(raw.get("journalTitle"))
        rec["doi"] = clean_doi(raw.get("doi"))
        rec["abstract"] = first_str(raw.get("abstractText"))
    elif shape == "openalex":
        rec["title"] = first_str(raw.get("title") or raw.get("display_name"))
        for a in raw.get("authorships") or []:
            if isinstance(a, dict) and isinstance(a.get("author"), dict):
                nm = a["author"].get("display_name")
                if nm:
                    rec["authors"].append(nm)
        try:
            rec["year"] = int(raw.get("publication_year"))
        except Exception:
            rec["year"] = None
        loc = raw.get("primary_location")
        if isinstance(loc, dict) and isinstance(loc.get("source"), dict):
            rec["venue"] = first_str(loc["source"].get("display_name"))
        rec["doi"] = clean_doi(raw.get("doi"))
        rec["abstract"] = openalex_abstract(raw.get("abstract_inverted_index"))
    else:  # generic records shape
        rec["title"] = first_str(raw.get("title"))
        au = raw.get("authors")
        if isinstance(au, list):
            rec["authors"] = [str(a) for a in au if str(a).strip()]
        elif isinstance(au, str):
            rec["authors"] = [a.strip() for a in au.split(",") if a.strip()]
        try:
            rec["year"] = int(raw.get("year"))
        except Exception:
            rec["year"] = None
        rec["venue"] = first_str(raw.get("venue"))
        rec["doi"] = clean_doi(raw.get("doi"))
        rec["abstract"] = first_str(raw.get("abstract"))
    return rec


def dedup_key(rec):
    if rec["doi"]:
        return "doi:" + rec["doi"]
    if rec["title"]:
        return "title:" + re.sub(r"[^a-z0-9]+", "", rec["title"].lower())
    return None


def iter_pool_files(dirs, out_dir):
    """All *.json files under the given dirs, excluding our own outputs."""
    out_abs = os.path.abspath(out_dir)
    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        for dirpath, _sub, files in os.walk(d):
            for fn in sorted(files):
                if not fn.lower().endswith(".json"):
                    continue
                p = os.path.join(dirpath, fn)
                if os.path.abspath(p).startswith(out_abs + os.sep):
                    continue
                if fn in SKIP_BASENAMES:
                    continue
                yield p


def load_pool(paths, evidence):
    """Parse every snapshot file; return (unique_records, stats)."""
    records, seen_keys = [], {}
    stats = {"files_consulted": 0, "files_skipped": [], "records_loaded": 0,
             "duplicates_merged": 0}
    for path in paths:
        stats["files_consulted"] += 1
        digest = sha256_file(path)
        evidence.append({"path": os.path.abspath(path), "sha256": digest,
                         "sha256_12": digest[:12],
                         "bytes": os.path.getsize(path), "role": "snapshot"})
        try:
            obj = read_json(path)
        except Exception as exc:
            stats["files_skipped"].append(
                {"file": path, "reason": "unparseable JSON (%s)" % exc})
            continue
        shape, raw_records = classify_payload(obj)
        if shape is None:
            stats["files_skipped"].append(
                {"file": path, "reason": "no known snapshot shape "
                                         "(message.items / resultList.result "
                                         "/ results / records)"})
            continue
        for idx, raw in enumerate(raw_records):
            rec = normalize_record(raw, shape)
            stats["records_loaded"] += 1
            prov = {"file": path, "json_index": idx, "shape": shape,
                    "sha256_12": digest[:12]}
            key = dedup_key(rec)
            if key is None:
                stats["files_skipped"].append(
                    {"file": path, "reason": "record #%d has neither DOI nor "
                                             "title; cannot grade or dedup"
                                             % idx})
                continue
            if key in seen_keys:
                seen_keys[key]["also_in"].append(prov)
                stats["duplicates_merged"] += 1
                continue
            rec["id"] = key
            rec["provenance"] = prov
            rec["also_in"] = []
            seen_keys[key] = rec
            records.append(rec)
    stats["unique_records"] = len(records)
    return records, stats


# ------------------------------------------------------------------ grading

def sentence_with(text, term):
    """First sentence (or fragment) of text containing term; trimmed."""
    for sent in SENTENCE_SPLIT_RE.split(text):
        if term in sent.lower():
            s = sent.strip()
            if len(s) > 240:
                pos = s.lower().find(term)
                lo = max(0, pos - 100)
                hi = min(len(s), pos + len(term) + 100)
                s = ("..." if lo else "") + s[lo:hi] + ("..." if hi < len(s)
                                                        else "")
            return s
    return None


def grade_record(rec, facets):
    """The full rubric lives in references/methodology.md; this is a direct
    transcription. Returns (grade, decomposition, counters)."""
    title_l = (rec["title"] or "").lower()
    abstract_l = (rec["abstract"] or "").lower()
    decomp, hits, weak, title_hit_facets = [], 0, 0, 0
    for facet in facets:
        t_hit = [t for t in facet["terms"] if t in title_l]
        a_hit = [t for t in facet["terms"] if t in abstract_l]
        fields, evidence = [], []
        if t_hit:
            fields.append("title")
            evidence.append("title: " + (rec["title"] or ""))
        if a_hit:
            fields.append("abstract")
            for t in a_hit:
                snip = sentence_with(rec["abstract"] or "", t)
                entry = "abstract: " + snip if snip else None
                if entry and entry not in evidence:
                    evidence.append(entry)
        if t_hit or len(a_hit) >= 2:
            status = "hit"
            contribution = W_TITLE_HIT if t_hit else W_ABSTRACT_HIT
            hits += 1
            if t_hit:
                title_hit_facets += 1
        elif a_hit:
            status = "weak"
            contribution = W_WEAK_HIT
            weak += 1
        else:
            status = "miss"
            contribution = W_MISS
        decomp.append({"facet": facet["name"],
                       "matched_terms": {"title": t_hit, "abstract": a_hit},
                       "fields": fields, "status": status,
                       "contribution": contribution, "evidence": evidence})
    n = len(facets)
    if n > 0 and hits == n:
        grade = 3                       # every facet hit
    elif n > 0 and hits > n / 2.0:
        grade = 2                       # strict majority of facets hit
    elif hits >= 1 or weak >= 1:
        grade = 1                       # minority hit, or weak-only evidence
    else:
        grade = 0                       # nothing matched at all
    counters = {"facet_hits": hits, "weak_hits": weak,
                "title_hit_facets": title_hit_facets,
                "coverage": round(hits / float(n), 4) if n else 0.0}
    return grade, decomp, counters


def assign_tier(grade, counters):
    if grade == 0:
        return "clear-exclude"
    if grade == 1:
        return "borderline"
    # grade >= 2: defensible only if at least one facet is evidenced in the
    # title; purely abstract-mention grades go back to the agent.
    return "clear-include" if counters["title_hit_facets"] > 0 else "borderline"


def rank_key(rec, grade_field):
    c = rec["_counters"]
    return (-rec[grade_field], -c["coverage"], -c["weak_hits"],
            rec["year"] is None, -(rec["year"] or 0),
            (rec["title"] or "").lower())


# ------------------------------------------------------------ adjudication

def normalize_adj_key(key):
    k = str(key).strip().lower()
    for pre in ("https://doi.org/", "http://doi.org/"):
        if k.startswith(pre):
            k = k[len(pre):]
    if k.startswith("doi:"):
        k = k[4:]
    return k


def load_adjudications(path, records, evidence):
    """Accepts {"<doi-or-id>": 0|1|2|3} or {"<doi-or-id>": {"grade": g,
    "rationale": "..."}}. Unknown ids are rejected with the valid id list."""
    try:
        raw = read_json(path)
    except Exception as exc:
        sys.stderr.write("ADJUDICATION ERROR: cannot read %s (%s)\n"
                         % (path, exc))
        sys.exit(3)
    if not isinstance(raw, dict):
        sys.stderr.write("ADJUDICATION ERROR: %s must be a JSON object\n"
                         % path)
        sys.exit(3)
    lookup = {}
    for rec in records:
        lookup[normalize_adj_key(rec["id"])] = rec
        if rec["doi"]:
            lookup[rec["doi"]] = rec
    valid_ids = sorted({rec["id"] for rec in records} |
                       {rec["doi"] for rec in records if rec["doi"]})
    out, unknown = {}, []
    for key, val in raw.items():
        if str(key).startswith("_"):  # metadata keys like "_note" are ignored
            continue
        rec = lookup.get(normalize_adj_key(key))
        if rec is None:
            unknown.append(key)
            continue
        if isinstance(val, dict):
            grade, rationale = val.get("grade"), val.get("rationale")
        else:
            grade, rationale = val, None
        if not (isinstance(grade, int) and 0 <= grade <= 3):
            sys.stderr.write("ADJUDICATION ERROR: grade for %r must be an "
                             "integer 0-3, got %r\n" % (key, grade))
            sys.exit(3)
        out[rec["id"]] = {"grade": grade, "rationale": rationale,
                          "as_given": key}
    if unknown:
        sys.stderr.write("ADJUDICATION ERROR: unknown record ids: %s\n"
                         % ", ".join(sorted(unknown)))
        sys.stderr.write("valid ids:\n  %s\n" % "\n  ".join(valid_ids))
        sys.exit(3)
    digest = sha256_file(path)
    evidence.append({"path": os.path.abspath(path), "sha256": digest,
                     "sha256_12": digest[:12],
                     "bytes": os.path.getsize(path), "role": "adjudication"})
    return out


def ndcg_at_k(engine_order, gain_of, k=10):
    """DCG with 2^g-1 gains over the engine's own ranking; IDCG from the same
    grades sorted descending. Agreement measure, not a benchmark score."""
    def dcg(grades):
        total = 0.0
        for i, g in enumerate(grades[:k]):
            total += ((2 ** g) - 1) / math.log(i + 2, 2)
        return total
    gains = [gain_of(r) for r in engine_order]
    ideal = sorted(gains, reverse=True)
    idcg = dcg(ideal)
    if idcg == 0:
        return None
    return round(dcg(gains) / idcg, 4)


# ---------------------------------------------------------------- rendering

def md_escape(s):
    return (s or "").replace("|", "\\|")


def render_candidates_md(records, path, adjudicated):
    lines = ["# Graded candidates (ranked)", ""]
    lines.append("Ranking: final grade desc, facet coverage desc, weak hits "
                 "desc, year desc (missing last), title asc. Grades follow "
                 "the rubric in references/methodology.md; every grade below "
                 "carries its full per-facet decomposition with evidence.")
    lines.append("")
    hdr = "| rank | grade | tier | coverage | year | title | doi |"
    lines += [hdr, "|-|-|-|-|-|-|-|"]
    for i, r in enumerate(records, 1):
        lines.append("| %d | %d | %s | %.2f | %s | %s | %s |" % (
            i, r["final_grade"], r["tier"], r["_counters"]["coverage"],
            r["year"] if r["year"] is not None else "—",
            md_escape(r["title"]), r["doi"] or "—"))
    lines.append("")
    for i, r in enumerate(records, 1):
        lines.append("## %d. %s" % (i, r["title"] or "(no title)"))
        lines.append("")
        lines.append("- id: `%s`  doi: `%s`  year: %s  venue: %s" % (
            r["id"], r["doi"] or "—",
            r["year"] if r["year"] is not None else "—", r["venue"] or "—"))
        auth = "; ".join(r["authors"][:6]) or "—"
        lines.append("- authors: %s" % auth)
        lines.append("- engine grade: %d | final grade: %d | tier: %s | "
                     "facets hit: %d | weak: %d" % (
                         r["engine_grade"], r["final_grade"], r["tier"],
                         r["_counters"]["facet_hits"],
                         r["_counters"]["weak_hits"]))
        if adjudicated and r["id"] in adjudicated:
            adj = adjudicated[r["id"]]
            lines.append("- adjudication: %s -> %d%s" % (
                r["engine_grade"], adj["grade"],
                " — " + adj["rationale"] if adj.get("rationale") else ""))
        lines.append("- score decomposition:")
        for d in r["score_decomposition"]:
            mt = []
            if d["matched_terms"]["title"]:
                mt.append("title=" + ",".join(d["matched_terms"]["title"]))
            if d["matched_terms"]["abstract"]:
                mt.append("abstract=" + ",".join(
                    d["matched_terms"]["abstract"]))
            lines.append("  - facet `%s`: **%s** (contribution %.1f; %s)" % (
                d["facet"], d["status"], d["contribution"],
                "; ".join(mt) if mt else "no terms matched"))
            for ev in d["evidence"]:
                lines.append("    - evidence: %s" % ev)
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def render_ledger_md(records, adjudicated, ndcg, path):
    lines = ["# Adjudication ledger", ""]
    lines.append("Engine grade vs the agent's final grade for every "
                 "adjudicated record. Changes are ledgered here, never "
                 "applied silently.")
    lines.append("")
    lines += ["| record | engine grade | final grade | changed | rationale |",
              "|-|-|-|-|-|"]
    for r in records:
        adj = adjudicated.get(r["id"])
        if not adj:
            continue
        changed = "yes" if adj["grade"] != r["engine_grade"] else "no"
        lines.append("| %s | %d | %d | %s | %s |" % (
            r["id"], r["engine_grade"], adj["grade"], changed,
            md_escape(adj.get("rationale")) or "—"))
    lines.append("")
    n_changed = sum(1 for r in records
                    if adjudicated.get(r["id"]) and
                    adjudicated[r["id"]]["grade"] != r["engine_grade"])
    lines.append("Adjudications applied: %d (%d changed the engine grade)."
                 % (len(adjudicated), n_changed))
    if ndcg is not None:
        lines.append("")
        lines.append("Engine-vs-adjudication agreement: **nDCG@10 = %.4f** "
                     "(DCG with 2^g-1 gains over the engine ranking against "
                     "the adjudicated grades; ideal DCG from the same grades "
                     "sorted descending). This is a self-consistency measure "
                     "of the engine ranking, not a benchmark score." % ndcg)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# -------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", required=True, help="/input/case.json")
    ap.add_argument("--input", required=True, help="organizer snapshot dir")
    ap.add_argument("--corpus", action="append", default=[],
                    help="extra dir of raw agent-saved responses (repeatable)")
    ap.add_argument("--work", default="/app/work",
                    help="work dir; facets.json is looked up here")
    ap.add_argument("--out", required=True, help="output dir, e.g. /app/output")
    ap.add_argument("--adjudicate", default=None,
                    help="JSON {record-id: 0|1|2|3} with the agent's final grades")
    args = ap.parse_args()

    notes, findings, evidence = [], [], []
    case = read_json(args.case)
    evidence.append({"path": os.path.abspath(args.case),
                     "sha256": sha256_file(args.case),
                     "sha256_12": sha256_file(args.case)[:12],
                     "bytes": os.path.getsize(args.case), "role": "case"})
    question = extract_question(case)

    facets, facets_source = load_facets(args.work, question, notes)
    if facets_source.startswith("fallback"):
        findings.append("facets auto-extracted from the question (no agent "
                        "facets.json); single-term facets, no synonyms")

    pool_files = sorted(set(iter_pool_files([args.input] + args.corpus,
                                            args.out)))
    records, stats = load_pool(pool_files, evidence)

    os.makedirs(args.out, exist_ok=True)
    os.makedirs(os.path.join(args.out, "evidence"), exist_ok=True)
    write_json(os.path.join(args.out, "evidence", "evidence_index.json"),
               {"files": evidence})

    digest = {"ENGINE_STATUS": "success", "question": question,
              "facets_source": facets_source,
              "n_facets": len(facets),
              "facets": [{"name": f["name"], "terms": f["terms"]}
                         for f in facets]}

    if not records:
        digest.update({"ENGINE_STATUS": "partial",
                       "finding": "empty candidate pool",
                       "files_consulted": stats["files_consulted"],
                       "files_skipped": stats["files_skipped"],
                       "records_loaded": stats["records_loaded"],
                       "unique_records": 0})
        report = ["# Ranking report", "",
                  "ENGINE_STATUS: partial — the candidate pool is empty.", "",
                  "```json", json.dumps(digest, ensure_ascii=False, indent=1),
                  "```", "",
                  "Files consulted: %d; records loaded: %d." % (
                      stats["files_consulted"], stats["records_loaded"]),
                  "No grades were produced. Check that snapshot files under "
                  "--input/--corpus carry a known shape (message.items / "
                  "resultList.result / results / records) and that records "
                  "have a DOI or title."]
        with open(os.path.join(args.out, "ranking_report.md"), "w",
                  encoding="utf-8") as f:
            f.write("\n".join(report) + "\n")
        print(json.dumps(digest, ensure_ascii=False))
        sys.exit(2)

    # ---- grade everything
    for rec in records:
        grade, decomp, counters = grade_record(rec, facets)
        rec["engine_grade"] = grade
        rec["score_decomposition"] = decomp
        rec["_counters"] = counters
        rec["tier"] = assign_tier(grade, counters)

    engine_order = sorted(records, key=lambda r: rank_key(r, "engine_grade"))

    # ---- optional adjudication (validated BEFORE any output is written)
    adjudicated = None
    if args.adjudicate:
        adjudicated = load_adjudications(args.adjudicate, records, evidence)
        write_json(os.path.join(args.out, "evidence", "evidence_index.json"),
                   {"files": evidence})
    for rec in records:
        adj = adjudicated.get(rec["id"]) if adjudicated else None
        rec["final_grade"] = adj["grade"] if adj else rec["engine_grade"]
        if adj:
            rec["adjudication"] = {"engine_grade": rec["engine_grade"],
                                   "final_grade": adj["grade"],
                                   "changed": adj["grade"] != rec["engine_grade"],
                                   "rationale": adj.get("rationale")}
        rec["tier"] = assign_tier(rec["final_grade"], rec["_counters"])

    final_order = sorted(records, key=lambda r: rank_key(r, "final_grade"))

    ndcg = None
    if adjudicated:
        gain_of = lambda r: (adjudicated.get(r["id"], {}).get("grade",
                                                              r["engine_grade"]))
        ndcg = ndcg_at_k(engine_order, gain_of, k=10)

    # ---- borderline queue (against final grades; adjudicated records are
    # already decided, so they leave the queue and appear in the ledger)
    queue = []
    for rec in final_order:
        if rec["tier"] != "borderline":
            continue
        if adjudicated and rec["id"] in adjudicated:
            continue
        questions = []
        for d in rec["score_decomposition"]:
            if d["status"] == "weak":
                for t in d["matched_terms"]["abstract"]:
                    questions.append(
                        "Does the term '%s' appearing only in the abstract "
                        "satisfy facet '%s' for the research question: %s"
                        % (t, d["facet"], question))
            elif (d["status"] == "hit" and not d["matched_terms"]["title"]
                  and rec["engine_grade"] >= 2):
                questions.append(
                    "Are abstract-only mentions of terms %s sufficient "
                    "evidence that this record addresses facet '%s' for the "
                    "research question?" % (d["matched_terms"]["abstract"],
                                            d["facet"]))
        if not questions:
            questions.append("Confirm or override the borderline grade %d for "
                             "this record given the research question: %s"
                             % (rec["final_grade"], question))
        queue.append({"id": rec["id"], "doi": rec["doi"],
                      "title": rec["title"], "year": rec["year"],
                      "engine_grade": rec["engine_grade"],
                      "final_grade": rec["final_grade"],
                      "score_decomposition": rec["score_decomposition"],
                      "questions_for_adjudicator": questions})

    # ---- histograms, gaps, findings
    hist = {str(g): sum(1 for r in records if r["final_grade"] == g)
            for g in (3, 2, 1, 0)}
    tiers = {}
    for r in records:
        tiers[r["tier"]] = tiers.get(r["tier"], 0) + 1
    zero_hit_facets = []
    for i, facet in enumerate(facets):
        if all(rec["score_decomposition"][i]["status"] == "miss"
               for rec in records):
            zero_hit_facets.append(facet["name"])
    if zero_hit_facets:
        findings.append("facets with zero hits across the whole pool "
                        "(honest coverage gaps): %s"
                        % ", ".join(zero_hit_facets))
    if hist["3"] == 0 and hist["2"] == 0 and hist["1"] == 0:
        findings.append("ALL records graded 0 — either the facets do not "
                        "describe the pool or the pool is off-topic; review "
                        "facets before trusting any ranking")

    # ---- write artifacts
    public_records = []
    for r in final_order:
        pr = {k: r[k] for k in ("id", "doi", "title", "authors", "year",
                                "venue", "abstract", "engine_grade",
                                "final_grade", "tier", "score_decomposition",
                                "provenance", "also_in")}
        pr.update(r["_counters"])
        if "adjudication" in r:
            pr["adjudication"] = r["adjudication"]
        public_records.append(pr)
    write_json(os.path.join(args.out, "graded_candidates.json"),
               {"question": question, "facets": digest["facets"],
                "facets_source": facets_source,
                "unique_records": len(records),
                "duplicates_merged": stats["duplicates_merged"],
                "records": public_records})
    render_candidates_md(final_order,
                         os.path.join(args.out, "graded_candidates.md"),
                         adjudicated or {})
    write_json(os.path.join(args.out, "borderline_queue.json"),
               {"question": question, "borderline_count": len(queue),
                "records": queue})
    if adjudicated:
        render_ledger_md(final_order, adjudicated, ndcg,
                         os.path.join(args.out, "adjudication_ledger.md"))

    digest.update({
        "files_consulted": stats["files_consulted"],
        "files_skipped": len(stats["files_skipped"]),
        "records_loaded": stats["records_loaded"],
        "unique_records": stats["unique_records"],
        "duplicates_merged": stats["duplicates_merged"],
        "grade_histogram": hist,
        "tiers": tiers,
        "borderline_count": len(queue),
        "zero_hit_facets": zero_hit_facets,
        "findings": findings + notes,
    })
    if adjudicated:
        digest["adjudications_applied"] = len(adjudicated)
        digest["grades_changed"] = sum(
            1 for r in records if r.get("adjudication", {}).get("changed"))
        digest["borderline_resolved_by_adjudication"] = sum(
            1 for r in records if r["id"] in adjudicated
            and r["tier"] == "borderline")
        digest["ndcg_at_10_engine_vs_adjudication"] = ndcg

    report = ["# Ranking report", "",
              "Self-contained digest of the grading run. Machine-readable "
              "candidates: `graded_candidates.json`; human-verifiable "
              "decomposition: `graded_candidates.md`.", "",
              "```json", json.dumps(digest, ensure_ascii=False, indent=1),
              "```", ""]
    if notes:
        report.append("## Intake notes")
        report += ["- " + n for n in notes] + [""]
    if stats["files_skipped"]:
        report.append("## Skipped files / records (nothing hidden)")
        report += ["- %s" % s for s in stats["files_skipped"]] + [""]
    if zero_hit_facets:
        report.append("## Honest coverage gaps")
        report.append("These facets matched NO record in the pool; a ranked "
                      "list cannot evidence them: %s. Widen the corpus or "
                      "enrich facet terms (synonyms in facets.json)."
                      % ", ".join(zero_hit_facets))
        report.append("")
    if findings:
        report.append("## Findings")
        report += ["- " + f for f in findings] + [""]
    if adjudicated:
        report.append("## Adjudication")
        report.append("Applied %d adjudications (%d changed an engine grade);"
                      " see `adjudication_ledger.md`. Engine-vs-adjudication "
                      "nDCG@10 = %s (self-consistency, not a benchmark "
                      "score)." % (len(adjudicated),
                                   digest["grades_changed"],
                                   "%.4f" % ndcg if ndcg is not None
                                   else "n/a (all grades 0)"))
        report.append("")
    with open(os.path.join(args.out, "ranking_report.md"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")

    print(json.dumps(digest, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
