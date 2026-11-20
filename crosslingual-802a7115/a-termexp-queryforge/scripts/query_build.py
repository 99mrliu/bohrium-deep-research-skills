#!/usr/bin/env python3
"""Per-language boolean query builder + hit-to-term alignment.

Stdlib only (Python 3.8+). Fully offline. Deterministic, provenance-logged.

What it does
------------
1. Reads the terminology table produced by term_table.py and emits ONE
   boolean query per declared language: OR over a concept's variants of
   that language, AND across concepts. Unverified (downgraded) variants are
   included but individually flagged; a language whose query lacks any
   concept is marked completeness=partial with the uncovered concepts
   named. Every query records its generation basis (which variants, from
   which sources).
2. Discovers local search-result records (.json/.jsonl/.csv) under /input,
   /app/work and the current directory; parses heterogeneous scholarly
   record shapes. Each record keeps a source locator and its ORIGINAL
   attribution fields (doi, language, version, translation_of, source) —
   the script passes them through and never infers a language or version
   the record does not state.
3. Aligns every hit back to the terminology table: surface-form matching
   of the record's title/abstract/keywords against each language query's
   variants. Matching is diacritic-folding for Latin scripts (pt/es/fr/de
   accents, German umlauts and sharp-s) and exact substring for CJK and
   Japanese kana. A hit is "recalled by" a language query iff every
   concept in that query has at least one variant matching.
4. Coverage accounting: for each declared language, the number of hits
   recalled by its query; a language with zero hits gets an explicit
   evidence-based missing explanation (query-not-emittable / query-partial
   / no-record-matched), never silence.
5. Assembles /app/output/result.json (mirroring the case output_contract),
   plus query_log.json and a human-readable hit_alignment.md.

Nothing is fabricated: a hit appears only if parsed from a real local
record; unmatched languages and unverified variants are reported, not
hidden.

Usage
-----
    python3 query_build.py --case /input/case.json \
        --term-table /app/work/term_table.json \
        --out /app/output [--workdir /app/work] [--langs en,zh,pt,es,ja,de]

Exit code is 0 even for partial results; the status field carries the truth.
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

# ----------------------------------------------------------------------------- config

DEFAULT_ROOTS = ["/input", "/app/work", "."]
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv"}
SKIP_FILE_NAMES = {"result.json", "run_log.json", "term_table_runlog.json",
                   "query_log.json", "case.json"}
MAX_FILE_BYTES = 40 * 1024 * 1024
MAX_FILES = 400
MAX_HITS = 2000

RECORD_EXTS = (".json", ".jsonl", ".ndjson", ".csv", ".tsv")

# The skill's own install directory (parent of scripts/) is never scanned.
SKILL_DIR = str(Path(__file__).resolve().parents[1])
TITLE_KEYS = ("title", "display_name", "article-title")
ABSTRACT_KEYS = ("abstract", "summary", "resumo", "resumen")
KEYWORD_KEYS = ("keywords", "keyword", "author_keywords", "mesh_terms",
                "decs_terms")
ATTR_PASSTHROUGH = {
    "doi": ("doi", "DOI"),
    "language": ("language", "lang", "text_language", "dc.language"),
    "version": ("version", "record_version", "version_type"),
    "translation_of": ("translation_of", "original_doi", "is_translation_of"),
    "relation": ("relation", "relationship"),
    "record_type": ("record_type", "type", "pubType"),
    "source": ("source", "database", "provider", "origin"),
    "url": ("url", "URL", "link"),
    "year": ("year", "pubYear", "publication_year"),
}

# ----------------------------------------------------------------------------- matching


def strip_diacritics(text):
    if not text:
        return ""
    text = text.replace("ß", "ss").replace("ẞ", "SS")
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def norm_text(text):
    t = strip_diacritics(str(text)).lower()
    t = re.sub(r"[^0-9a-z぀-ヿ㐀-䶿一-鿿]+", " ", t)
    return " " + " ".join(t.split()) + " "


def norm_term(term):
    return norm_text(term).strip()


def is_cjk(term):
    return bool(re.search(r"[぀-ヿ㐀-䶿一-鿿]", term))


def term_matches(term, haystack_norm):
    """Surface match of one variant against normalized record text.

    Latin terms: padded substring on the diacritic-folded normal form
    (word-boundary safe because both sides are space-padded token streams).
    CJK / kana terms: plain substring (no word boundaries exist).
    """
    t = norm_term(term)
    if not t:
        return False
    if is_cjk(term):
        return t in haystack_norm.replace(" ", "") or t in haystack_norm
    return (" " + t + " ") in haystack_norm

# ----------------------------------------------------------------------------- queries


def build_queries(table, langs, log):
    """One boolean query per language. Returns {lang: query_dict}."""
    queries = {}
    concepts = table.get("concepts") or []
    for lang in langs:
        clauses = []
        uncovered = []
        used_variants = []
        for c in concepts:
            variants = [v for v in (c.get("variants") or [])
                        if v.get("lang") == lang and v.get("term")]
            if not variants:
                uncovered.append({"concept_id": c.get("concept_id"),
                                  "label_en": c.get("label_en")})
                continue
            # verified first; unverified kept but flagged (downgrade rule)
            variants.sort(key=lambda v: (not v.get("verified"),
                                         -float(v.get("confidence") or 0)))
            terms = []
            for v in variants:
                terms.append('"%s"' % v["term"])
                used_variants.append({
                    "concept_id": c.get("concept_id"),
                    "term": v["term"], "type": v.get("type"),
                    "source": v.get("source"),
                    "verified": bool(v.get("verified")),
                    "confidence": v.get("confidence"),
                })
            clauses.append("(" + " OR ".join(terms) + ")")
        if not clauses:
            queries[lang] = None
            log.append("query NOT emitted for %s: no concept has a %s variant"
                       % (lang, lang))
            continue
        q = {
            "lang": lang,
            "query": " AND ".join(clauses),
            "template": "(concept1: variant OR ...) AND (concept2: ...) "
                        "[per-language, OR within concept, AND across]",
            "completeness": "partial" if uncovered else "full",
            "uncovered_concepts": uncovered,
            "variants_used": used_variants,
            "generation_basis": {
                "term_table": "term_table.json",
                "n_concepts": len(concepts),
                "n_variants": len(used_variants),
                "n_unverified_variants": sum(1 for v in used_variants
                                             if not v["verified"]),
            },
        }
        queries[lang] = q
        log.append("query for %s: %d concepts, %d variants (%d unverified), "
                   "completeness=%s"
                   % (lang, len(clauses), len(used_variants),
                      q["generation_basis"]["n_unverified_variants"],
                      q["completeness"]))
    return queries

# ----------------------------------------------------------------------------- records


def discover_record_files(roots, skip_abs):
    seen, out = set(skip_abs), []
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        stack = [(root, 0)]
        while stack and len(out) < MAX_FILES:
            node, depth = stack.pop()
            try:
                if node.is_dir():
                    if node.name in SKIP_DIRS or node.name.startswith("."):
                        continue
                    if depth <= 6:
                        for child in sorted(node.iterdir()):
                            stack.append((child, depth + 1))
                elif node.suffix.lower() in RECORD_EXTS \
                        and node.name not in SKIP_FILE_NAMES:
                    rp = str(node.resolve())
                    if rp in seen or rp.startswith(SKILL_DIR + os.sep) \
                            or node.stat().st_size > MAX_FILE_BYTES:
                        continue
                    seen.add(rp)
                    out.append(node)
            except (OSError, PermissionError):
                continue
    return out


def _as_str(v):
    if isinstance(v, list):
        return " ".join(str(x) for x in v if isinstance(x, (str, int, float)))
    if isinstance(v, (str, int, float)):
        return str(v)
    return ""


def record_from_obj(obj, locator):
    """Interpret one dict as a search-result record; None if not plausible."""
    if not isinstance(obj, dict):
        return None
    lower = {str(k).lower(): k for k in obj.keys()}

    def pick(keys):
        for k in keys:
            if k.lower() in lower:
                v = obj[lower[k.lower()]]
                s = _as_str(v)
                if s:
                    return s
        return ""

    title = pick(TITLE_KEYS)
    abstract = pick(ABSTRACT_KEYS)
    keywords = pick(KEYWORD_KEYS)
    if not (title or abstract or keywords):
        return None
    rec = {"title": title, "abstract": abstract, "keywords": keywords,
           "locator": locator}
    for out_key, candidates in ATTR_PASSTHROUGH.items():
        val = pick(candidates)
        if val:
            rec[out_key] = val
    return rec


def collect_records(files, log):
    records, parse_notes = [], []

    def walk(obj, path, file_path, depth=0):
        if len(records) >= MAX_HITS or depth > 12:
            return
        if isinstance(obj, dict):
            rec = record_from_obj(obj, {"file": file_path,
                                        "pointer": path or "$"})
            if rec is not None:
                records.append(rec)
                return
            for k, v in obj.items():
                if str(k).lower() in ("output_contract", "concepts",
                                      "variants"):
                    continue
                walk(v, "%s/%s" % (path, k), file_path, depth + 1)
        elif isinstance(obj, list):
            for i, v in enumerate(obj[:20000]):
                walk(v, "%s/%d" % (path, i), file_path, depth + 1)

    for path in files:
        file_path = str(path)
        suffix = path.suffix.lower()
        try:
            if suffix == ".json":
                with open(path, encoding="utf-8", errors="replace") as fh:
                    walk(json.load(fh), "$", file_path)
            elif suffix in (".jsonl", ".ndjson"):
                with open(path, encoding="utf-8", errors="replace") as fh:
                    for i, line in enumerate(fh):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            walk(json.loads(line), "$/%d" % i, file_path)
                        except json.JSONDecodeError:
                            parse_notes.append("bad JSONL line %s:%d"
                                               % (file_path, i + 1))
            else:  # csv / tsv
                with open(path, newline="", encoding="utf-8",
                          errors="replace") as fh:
                    sample = fh.read(4096)
                    fh.seek(0)
                    try:
                        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;") \
                            if sample.strip() else csv.excel
                    except csv.Error:
                        dialect = csv.excel
                    reader = csv.DictReader(fh, dialect=dialect)
                    if not reader.fieldnames:
                        continue
                    for i, row in enumerate(reader):
                        rec = record_from_obj(
                            {k: v for k, v in row.items() if v},
                            {"file": file_path, "pointer": "row/%d" % (i + 2)})
                        if rec is not None:
                            records.append(rec)
        except (OSError, UnicodeError, json.JSONDecodeError, csv.Error) as exc:
            parse_notes.append("skipped %s: %s" % (file_path, exc))
    log.append("collected %d candidate records from %d files (%d parse notes)"
               % (len(records), len(files), len(parse_notes)))
    return records, parse_notes

# ----------------------------------------------------------------------------- alignment


def align_hits(records, queries, table, log):
    """Match every record against every language query.

    A hit is recalled by language L iff for every concept in L's query at
    least one variant surface-matches the record's title/abstract/keywords.
    """
    concept_ids = {c.get("concept_id") for c in table.get("concepts") or []}
    hits = []
    for idx, rec in enumerate(records):
        hay = norm_text(" ".join([rec.get("title", ""),
                                  rec.get("abstract", ""),
                                  rec.get("keywords", "")]))
        if not hay.strip():
            continue
        recalled_by = []
        for lang, q in queries.items():
            if q is None:
                continue
            matched = []
            all_concepts_hit = True
            for c in table.get("concepts") or []:
                variants = [v for v in (c.get("variants") or [])
                            if v.get("lang") == lang]
                if not variants:
                    # concept uncovered in this language -> query cannot
                    # recall on this concept; per policy the partial query
                    # still runs over the covered concepts only
                    continue
                mv = [v for v in variants if term_matches(v["term"], hay)]
                if not mv:
                    all_concepts_hit = False
                    break
                matched.append({
                    "concept_id": c.get("concept_id"),
                    "matched_variants": [
                        {"term": v["term"], "type": v.get("type"),
                         "source": v.get("source"),
                         "verified": bool(v.get("verified"))}
                        for v in mv],
                })
            if all_concepts_hit and matched:
                recalled_by.append({"lang": lang,
                                    "completeness": q["completeness"],
                                    "matched_concepts": matched})
        if not recalled_by:
            continue
        hit = {
            "hit_id": "h%04d" % (idx + 1),
            "title": rec.get("title") or None,
            "attribution": {k: rec[k] for k in
                            ("doi", "language", "version", "translation_of",
                             "relation", "record_type", "source", "url",
                             "year") if rec.get(k)},
            "attribution_note": ("attribution fields are passed through "
                                 "verbatim from the source record; absent "
                                 "fields were NOT stated by the source"),
            "recalled_by": recalled_by,
            "locator": rec["locator"],
        }
        hits.append(hit)
    log.append("alignment: %d records matched by >= 1 language query "
               "(out of %d)" % (len(hits), len(records)))
    return hits


def coverage_stats(queries, hits, langs, log):
    coverage = {}
    for lang in langs:
        q = queries.get(lang)
        n = sum(1 for h in hits
                if any(r["lang"] == lang for r in h["recalled_by"]))
        entry = {"lang": lang, "n_hits": n}
        if q is None:
            entry["status"] = "missing"
            entry["explanation"] = ("no query could be emitted: no concept "
                                    "has a %s variant in the term table "
                                    "(see to_translate)" % lang)
        elif n == 0:
            entry["status"] = "missing"
            entry["explanation"] = (
                "query emitted (completeness=%s) but no local record "
                "surface-matched all covered concepts" % q["completeness"])
            if q["completeness"] == "partial":
                entry["explanation"] += (
                    "; uncovered concepts: %s"
                    % ", ".join(c["concept_id"] or "?"
                                for c in q["uncovered_concepts"]))
        else:
            entry["status"] = "ok"
            if q["completeness"] == "partial":
                entry["caveat"] = ("query partial: concepts %s had no %s "
                                   "variant and were dropped from the query"
                                   % (", ".join(c["concept_id"] or "?"
                                                for c in q["uncovered_concepts"]),
                                      lang))
        coverage[lang] = entry
        log.append("coverage %s: %s (n_hits=%d)" % (lang, entry["status"], n))
    return coverage

# ----------------------------------------------------------------------------- output


def write_alignment_md(path, hits, coverage):
    lines = ["# 命中—术语对齐表（自动生成）", "",
             "每条命中列出：召回它的语种查询、逐概念命中的术语变体、",
             "以及记录自带的语种/版本归因（原样转写，未推断）。", ""]
    lines.append("## 语种覆盖统计")
    lines += ["", "| 语种 | 命中数 | 状态 | 说明 |", "|-|-|-|-|"]
    for lang, e in coverage.items():
        lines.append("| %s | %d | %s | %s |"
                     % (lang, e["n_hits"], e["status"],
                        (e.get("explanation") or e.get("caveat") or "-")
                        .replace("|", "\\|")))
    lines += ["", "## 逐条命中", ""]
    for h in hits:
        attr = h["attribution"]
        lines.append("### %s  %s" % (h["hit_id"], (h.get("title") or "(无标题)")[:100]))
        lines.append("- 定位: `%s` `%s`" % (h["locator"].get("file"),
                                            h["locator"].get("pointer")))
        lines.append("- 归因: doi=%s | language=%s | version=%s | "
                     "translation_of=%s | source=%s"
                     % (attr.get("doi"), attr.get("language"),
                        attr.get("version"), attr.get("translation_of"),
                        attr.get("source")))
        for r in h["recalled_by"]:
            lines.append("- 召回语种 **%s** (query completeness=%s):"
                         % (r["lang"], r["completeness"]))
            for mc in r["matched_concepts"]:
                vs = "; ".join('"%s"[%s%s]'
                               % (v["term"], v.get("type") or "?",
                                  "" if v["verified"] else ", UNVERIFIED")
                               for v in mc["matched_variants"])
                lines.append("  - 概念 %s ← %s" % (mc["concept_id"], vs))
        lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def load_case(case_path):
    with open(case_path, encoding="utf-8") as fh:
        return json.load(fh)

# ----------------------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(
        description="Per-language query building and hit-term alignment.")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--term-table", default="/app/work/term_table.json")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--workdir", default="/app/work")
    ap.add_argument("--roots", default=None,
                    help="comma-separated extra roots for hit records")
    ap.add_argument("--langs", default=None,
                    help="override declared languages (comma-separated)")
    args = ap.parse_args()

    started = time.time()
    out_dir, work_dir = Path(args.out), Path(args.workdir)
    for d in (out_dir, work_dir):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    log = ["query_build started " + time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                  time.gmtime())]

    # -- case ----------------------------------------------------------------
    try:
        case = load_case(args.case)
    except (OSError, json.JSONDecodeError) as exc:
        log.append("FATAL: cannot read case file %s: %s" % (args.case, exc))
        result = {"case_id": "unknown_case",
                  "skill": "xlang-termexpansion-queryforge",
                  "status": "failed", "queries": {}, "hits": [],
                  "coverage": {}, "sources": [], "evidence_records": log,
                  "uncertainty": ["case file unreadable: %s" % exc],
                  "change_records": []}
        (out_dir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": "failed", "reason": str(exc)},
                         ensure_ascii=False))
        return 0
    case_id = case.get("case_id") or case.get("id") or "unknown_case"

    # -- term table -----------------------------------------------------------
    try:
        table = json.loads(Path(args.term_table).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        table = None
        log.append("WARNING: term table unreadable (%s); falling back to "
                   "case-provided table if any" % exc)
    if table and not table.get("concepts"):
        log.append("WARNING: term table has zero concepts")
    concepts = (table or {}).get("concepts") or []
    langs = ([l.strip() for l in args.langs.split(",") if l.strip()]
             if args.langs else None) \
        or (table or {}).get("languages_declared") \
        or ["en", "zh", "pt", "es", "ja", "de"]

    # -- queries ---------------------------------------------------------------
    queries = build_queries({"concepts": concepts}, langs, log)

    # -- records -----------------------------------------------------------------
    roots = [r for r in DEFAULT_ROOTS if r]
    if args.roots:
        roots += [r.strip() for r in args.roots.split(",") if r.strip()]
    case_dir = str(Path(args.case).resolve().parent)
    if case_dir not in roots:
        roots.insert(0, case_dir)
    skip_abs = {str(Path(args.term_table).resolve()),
                str((out_dir / "result.json").resolve()),
                str((out_dir / "query_log.json").resolve())}
    files = discover_record_files(roots, skip_abs)
    records, parse_notes = collect_records(files, log)

    # -- alignment + coverage -----------------------------------------------------
    hits = align_hits(records, queries, {"concepts": concepts}, log) \
        if concepts else []
    coverage = coverage_stats(queries, hits, langs, log)

    # -- status ---------------------------------------------------------------------
    uncertainty = []
    if table is None:
        uncertainty.append("term table unreadable; queries may be empty")
    if not concepts:
        uncertainty.append("no concepts in term table; no query emitted; "
                           "run term_table.py first")
    if table and table.get("to_translate"):
        uncertainty.append("%d concept-language pairs lack a variant "
                           "(see term_table.to_translate); affected "
                           "language queries are degraded"
                           % len(table["to_translate"]))
    rt = (table or {}).get("roundtrip") or {}
    if rt.get("downgraded"):
        uncertainty.append("%d controlled translations failed round-trip "
                           "verification and were downgraded (kept, flagged "
                           "UNVERIFIED)" % rt["downgraded"])
    for lang, e in coverage.items():
        if e["status"] == "missing":
            uncertainty.append("language %s has no valid hits: %s"
                               % (lang, e["explanation"]))
    if parse_notes:
        uncertainty.append("parse notes: " + "; ".join(parse_notes[:5]))
    n_unverified_used = sum(
        q["generation_basis"]["n_unverified_variants"]
        for q in queries.values() if q)
    if n_unverified_used:
        uncertainty.append("%d unverified term variants participate in "
                           "queries (downgrade rule applied); treat hits "
                           "recalled solely through them as candidates for "
                           "manual check" % n_unverified_used)

    if not concepts:
        status = "failed"
    elif all(e["status"] == "ok" for e in coverage.values()) and hits:
        status = "ok"
    elif hits or any(e["status"] == "ok" for e in coverage.values()):
        status = "partial"
    else:
        status = "partial" if any(queries.values()) else "failed"

    query_log = {lang: q for lang, q in queries.items()}
    term_table_summary = {
        "concept_count": len(concepts),
        "variant_count": sum(len(c.get("variants") or []) for c in concepts),
        "languages_declared": langs,
        "roundtrip": rt,
        "to_translate_count": len((table or {}).get("to_translate") or []),
    }
    result = {
        "case_id": case_id,
        "skill": "xlang-termexpansion-queryforge",
        "status": status,
        "term_table_summary": term_table_summary,
        "queries": query_log,
        "hits": hits,
        "coverage": coverage,
        "sources": [{"file": str(f)} for f in files],
        "evidence_records": log,
        "uncertainty": uncertainty,
        "change_records": [],
    }
    contract = case.get("output_contract")
    if isinstance(contract, dict):
        for field in contract:
            if field not in result:
                result[field] = None
        result["output_contract_fields"] = sorted(contract.keys())

    log.append("finished in %.1fs: %d queries, %d hits, status=%s"
               % (time.time() - started,
                  sum(1 for q in queries.values() if q),
                  len(hits), status))
    result["evidence_records"] = log

    try:
        (out_dir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / "query_log.json").write_text(
            json.dumps(query_log, ensure_ascii=False, indent=2),
            encoding="utf-8")
        write_alignment_md(out_dir / "hit_alignment.md", hits, coverage)
    except OSError as exc:
        log.append("WARNING: could not write to %s: %s" % (out_dir, exc))
        (work_dir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        (work_dir / "run_log.json").write_text(
            json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    print(json.dumps({"status": status,
                      "queries": sum(1 for q in queries.values() if q),
                      "hits": len(hits),
                      "coverage": {l: e["n_hits"]
                                   for l, e in coverage.items()}},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
