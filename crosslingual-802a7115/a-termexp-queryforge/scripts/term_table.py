#!/usr/bin/env python3
"""Terminology table builder for multilingual controlled query expansion.

Stdlib only (Python 3.8+). Fully offline. Deterministic, provenance-logged.

What it does
------------
1. Discovers the input material: scans /input, /app/work and the current
   directory for .json / .jsonl / .csv / .txt / .md files and extracts text
   (case.json fields, task text, and title/abstract/keyword fields of local
   scholarly records). Every extracted text span keeps a source locator
   (file + JSON path / line no).
2. Extracts candidate concepts with bilingual heuristics:
   - Latin-alphabet technical terms (1-3 word phrases, hyphenated terms);
   - acronyms (ALL-CAPS tokens, e.g. DENV, GSDMD);
   - CJK term runs (Chinese / Japanese surface forms);
   - Latin-script runs with diacritics (pt/es/fr/de words).
3. Loads and merges terminology tables: the seed table shipped with the
   skill (--seed, default resources/term_table_seed.json), any term-table
   JSON found in the inputs (detected by a "concepts" key), and an optional
   Agent-supplied controlled-translation file (--translations).
4. Round-trip (back-translation) verification: for a variant whose source
   is "controlled-translation", a "back_translation" that normalizes to the
   concept's English label or an existing English variant marks it
   verified; a mismatching back-translation downgrades it to
   verified=false / status "unverified" with halved confidence (never
   deleted); without back-translation evidence the declared flag is kept
   and annotated round-trip:no-evidence.
5. Coverage check: for every concept x every declared language, emits the
   list of missing language variants (the "to_translate" list). Nothing is
   auto-translated: the script never invents a translation.

Output: term_table.json (default /app/work/term_table.json) plus a run log.

Usage
-----
    python3 term_table.py --case /input/case.json \
        --out /app/work/term_table.json [--workdir /app/work] \
        [--seed resources/term_table_seed.json] [--translations FILE] \
        [--langs en,zh,pt,es,ja,de]

Exit code is 0 even on partial failures; the log carries the truth.
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
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "output"}
SKIP_FILES = {"result.json", "run_log.json", "term_table_runlog.json",
              "query_log.json", "hit_alignment.md"}
MAX_FILE_BYTES = 40 * 1024 * 1024
MAX_FILES = 400

TEXT_EXTS = (".json", ".jsonl", ".ndjson", ".csv", ".tsv", ".txt", ".md")

LATIN_STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "in", "on", "for", "to", "with",
    "by", "from", "at", "as", "is", "are", "was", "were", "be", "been",
    "via", "using", "based", "study", "studies", "analysis", "review",
    "new", "its", "their", "we", "this", "that", "these", "those",
    "between", "into", "over", "results", "methods", "conclusion",
    "conclusions", "background", "objective", "purpose", "abstract",
    "introduction", "keywords", "article", "journal", "doi", "http",
    "https", "www", "com", "org", "et", "al", "de", "da", "do", "dos",
    "das", "em", "no", "na", "nos", "nas", "um", "uma", "para", "com",
    "por", "que", "se", "su", "el", "la", "los", "las", "en", "un",
    "una", "y", "o", "del", "al", "es", "son", "der", "die", "das",
    "und", "mit", "auf", "ein", "eine", "des", "den", "dem", "ist",
}

# CJK run: CJK unified ideographs + hiragana + katakana
CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿]{2,24}")
CJK_SPLIT_RE = re.compile(r"[的之和与及或におけるについてによる]")

# Latin word token incl. diacritics (pt/es/fr/de) and hyphens inside words
LATIN_TOKEN_RE = re.compile(r"[A-Za-zÀ-ɏ][A-Za-zÀ-ɏ\-']*")
ACRONYM_RE = re.compile(r"\b[A-Z][A-Z0-9\-]{1,11}\b")

RECORD_TEXT_KEYS = ("title", "abstract", "keywords", "keyword",
                    "display_name", "summary", "resumo", "resumen")

# The skill's own install directory (parent of scripts/) is never scanned:
# the bundled demo resources must not leak into a real case run.
SKILL_DIR = str(Path(__file__).resolve().parents[1])

# ----------------------------------------------------------------------------- text utils


def strip_diacritics(text):
    """NFKD + drop combining marks; map German sharp-s. CJK passes through."""
    if not text:
        return ""
    text = text.replace("ß", "ss").replace("ẞ", "SS")
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def norm_term(text):
    """Normal form used for term identity: diacritic-folded, case-folded."""
    t = strip_diacritics(str(text)).lower()
    t = re.sub(r"[^0-9a-z぀-ヿ㐀-䶿一-鿿]+", " ", t)
    return " ".join(t.split())


def lang_of_term(term):
    """Rough surface-form language guess for a single variant term."""
    if re.search(r"[぀-ヿ]", term):
        return "ja"
    if re.search(r"[㐀-䶿一-鿿]", term):
        return "zh"
    return None  # Latin-script terms are not auto-assigned a language

# ----------------------------------------------------------------------------- input discovery


def discover_files(roots, extra_skip=()):
    seen, out = set(), []
    skip = SKIP_FILES | set(extra_skip)
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
                elif node.suffix.lower() in TEXT_EXTS and node.name not in skip:
                    rp = str(node.resolve())
                    if rp in seen or rp.startswith(SKILL_DIR + os.sep) \
                            or node.stat().st_size > MAX_FILE_BYTES:
                        continue
                    seen.add(rp)
                    out.append(node)
            except (OSError, PermissionError):
                continue
    return out


def collect_texts(files, log):
    """Return list of {text, locator}; heterogeneous parsing, nothing fatal."""
    texts = []
    parse_notes = []

    def add(text, loc):
        if text and isinstance(text, str) and text.strip():
            texts.append({"text": text, "locator": loc})

    def walk_json(obj, path, file_path, depth=0):
        if depth > 12:
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.lower() in RECORD_TEXT_KEYS:
                    if isinstance(v, str):
                        add(v, {"file": file_path, "pointer": "%s/%s" % (path, k)})
                    elif isinstance(v, list):
                        for i, item in enumerate(v[:50]):
                            if isinstance(item, str):
                                add(item, {"file": file_path,
                                           "pointer": "%s/%s/%d" % (path, k, i)})
                elif k.lower() in ("output_contract",):
                    continue
                else:
                    walk_json(v, "%s/%s" % (path, k), file_path, depth + 1)
        elif isinstance(obj, list):
            for i, v in enumerate(obj[:20000]):
                walk_json(v, "%s/%d" % (path, i), file_path, depth + 1)
        elif isinstance(obj, str):
            # top-level prose strings inside case/task JSON
            if len(obj) > 3:
                add(obj, {"file": file_path, "pointer": path or "$"})

    for path in files:
        file_path = str(path)
        suffix = path.suffix.lower()
        try:
            if suffix == ".json":
                with open(path, encoding="utf-8", errors="replace") as fh:
                    walk_json(json.load(fh), "$", file_path)
            elif suffix in (".jsonl", ".ndjson"):
                with open(path, encoding="utf-8", errors="replace") as fh:
                    for i, line in enumerate(fh):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            walk_json(json.loads(line), "$/%d" % i, file_path)
                        except json.JSONDecodeError:
                            parse_notes.append("bad JSONL line %s:%d"
                                               % (file_path, i + 1))
            elif suffix in (".csv", ".tsv"):
                with open(path, newline="", encoding="utf-8", errors="replace") as fh:
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
                    cols = {c.lower().strip(): c for c in reader.fieldnames}
                    for i, row in enumerate(reader):
                        for key in RECORD_TEXT_KEYS:
                            if key in cols and row.get(cols[key]):
                                add(row[cols[key]], {"file": file_path,
                                                     "pointer": "row/%d/%s"
                                                                % (i + 2, key)})
            else:  # .txt / .md (task.md lives here)
                with open(path, encoding="utf-8", errors="replace") as fh:
                    add(fh.read(), {"file": file_path, "pointer": "$"})
        except (OSError, UnicodeError, json.JSONDecodeError, csv.Error) as exc:
            parse_notes.append("skipped %s: %s" % (file_path, exc))
    log.append("collected %d text spans from %d files (%d parse notes)"
               % (len(texts), len(files), len(parse_notes)))
    return texts, parse_notes

# ----------------------------------------------------------------------------- candidate extraction


def extract_candidates(texts, known_terms, max_candidates=60):
    """Bilingual heuristic candidate-concept extraction.

    Returns list of {surface, kind, freq, example_locator}. Candidates that
    already appear (normalized) in known_terms are dropped.
    """
    freq = {}
    first_loc = {}

    def bump(surface, kind, loc):
        key = (norm_term(surface), kind)
        if not key[0]:
            return
        freq[key] = freq.get(key, 0) + 1
        first_loc.setdefault(key, loc)

    for span in texts:
        text, loc = span["text"], span["locator"]
        # 1. acronyms
        for m in ACRONYM_RE.finditer(text):
            bump(m.group(0), "acronym", loc)
        # 2. Latin 1-3 word technical phrases
        tokens = [(m.group(0), m.start(), m.end())
                  for m in LATIN_TOKEN_RE.finditer(text)]

        def keep_token(tok):
            base = strip_diacritics(tok).lower()
            return (len(base) >= 4
                    and base not in LATIN_STOPWORDS
                    and tok != tok.upper())  # acronyms handled separately

        for n in (1, 2, 3):
            for i in range(0, max(0, len(tokens) - n + 1)):
                gram = tokens[i:i + n]
                if not all(keep_token(g[0]) for g in gram):
                    continue
                # adjacency: consecutive tokens separated by <= 2 raw chars
                if n > 1 and not all(gram[j + 1][1] - gram[j][2] <= 2
                                     for j in range(n - 1)):
                    continue
                bump(" ".join(g[0] for g in gram),
                     "latin-term" if n == 1 else "latin-phrase", loc)
        # 3. CJK runs
        for m in CJK_RE.finditer(text):
            run = m.group(0)
            bump(run, "cjk-term", loc)
            for part in CJK_SPLIT_RE.split(run):
                if 2 <= len(part) <= 12 and part != run:
                    bump(part, "cjk-term", loc)

    out = []
    for (surface_norm, kind), f in freq.items():
        if surface_norm in known_terms:
            continue
        # need one original surface: recover from first locator text is
        # costly; store normalized surface (kind already signals script)
        score = f + (2 if kind == "acronym" else 0)
        out.append({"surface": surface_norm, "kind": kind, "freq": f,
                    "score": score, "example_locator": first_loc[(surface_norm, kind)]})
    out.sort(key=lambda c: (-c["score"], c["surface"]))
    return out[:max_candidates]

# ----------------------------------------------------------------------------- term table


def empty_table():
    return {"term_table_format": "1.0", "languages_declared": [], "concepts": []}


def load_table_file(path, log):
    """Load a term-table JSON (skill seed, case-provided, or --translations).

    Accepted shapes:
      A) {"concepts": [...]}                       -> full table
      B) {"translations": [ {concept_id, lang, term, source?, confidence?,
                             back_translation?}, ... ]}  -> patch entries
    Returns (concepts_added, entries, note).
    """
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        log.append("WARNING: cannot load table file %s: %s" % (path, exc))
        return [], [], "load-failed: %s" % exc
    if isinstance(data, dict) and isinstance(data.get("concepts"), list):
        return data["concepts"], data.get("translations") or [], "table"
    if isinstance(data, dict) and isinstance(data.get("translations"), list):
        return [], data["translations"], "translations"
    if isinstance(data, list):
        return [], data, "translations"
    return [], [], "unrecognized-shape"


def merge_concept(table, concept, source_file, log):
    """Merge one concept dict into the table by concept_id or label_en."""
    cid = concept.get("concept_id") or concept.get("id")
    label = concept.get("label_en") or ""
    target = None
    for c in table["concepts"]:
        if cid and c.get("concept_id") == cid:
            target = c
            break
        if label and norm_term(c.get("label_en") or "") == norm_term(label) and label:
            target = c
            break
    if target is None:
        target = {"concept_id": cid or "c%d" % (len(table["concepts"]) + 1),
                  "label_en": label, "variants": []}
        table["concepts"].append(target)
    seen = {(v.get("lang"), norm_term(v.get("term", "")))
            for v in target["variants"]}
    for v in concept.get("variants") or []:
        term = str(v.get("term", "")).strip()
        lang = v.get("lang") or lang_of_term(term)
        if not term or not lang:
            log.append("WARNING: variant skipped (missing lang/term) in %s: %r"
                       % (source_file, v))
            continue
        sig = (lang, norm_term(term))
        if sig in seen:
            continue
        seen.add(sig)
        target["variants"].append({
            "lang": lang,
            "term": term,
            "type": v.get("type") or "synonym",
            "source": v.get("source") or ("file:" + source_file),
            "confidence": v.get("confidence", 0.5),
            "verified": bool(v.get("verified", False)),
            "back_translation": v.get("back_translation"),
            "provenance": {"file": source_file},
        })
    return target


def apply_translation_entries(table, entries, source_file, log):
    """Apply Agent-supplied controlled translations as new variants.

    Every entry lands with source 'controlled-translation' and starts
    unverified unless the concept already attests the same surface form.
    Round-trip verification runs in verify_roundtrip().
    """
    applied = 0
    for e in entries:
        if not isinstance(e, dict):
            continue
        cid = e.get("concept_id")
        term = str(e.get("term", "")).strip()
        lang = e.get("lang") or lang_of_term(term)
        if not (cid and term and lang):
            log.append("WARNING: translation entry incomplete, skipped: %r" % e)
            continue
        concept = None
        for c in table["concepts"]:
            if c.get("concept_id") == cid:
                concept = c
                break
        if concept is None:
            concept = {"concept_id": cid,
                       "label_en": e.get("label_en") or "",
                       "variants": []}
            table["concepts"].append(concept)
            log.append("translation introduced new concept %s (%s)"
                       % (cid, e.get("label_en") or term))
        seen = {(v.get("lang"), norm_term(v.get("term", "")))
                for v in concept["variants"]}
        if (lang, norm_term(term)) in seen:
            continue
        concept["variants"].append({
            "lang": lang, "term": term,
            "type": e.get("type") or "controlled-translation",
            "source": "controlled-translation",
            "translation_basis": e.get("translation_basis") or e.get("basis"),
            "confidence": e.get("confidence", 0.5),
            "verified": False,
            "back_translation": e.get("back_translation"),
            "provenance": {"file": source_file},
        })
        applied += 1
    log.append("applied %d controlled-translation entries from %s"
               % (applied, source_file))


def verify_roundtrip(table, log):
    """Round-trip check for controlled-translation variants.

    Rule (see rules/term_expansion_policy.md §4):
      - back_translation present and normalizes to the concept's English
        label or an existing en variant  -> verified=true;
      - back_translation present and mismatches -> verified=false,
        status=unverified, confidence halved (downgraded, never deleted);
      - no back_translation -> the variant's declared verified flag is
        kept as-is (its source annotation is the only evidence) and the
        variant is annotated round-trip:no-evidence so a reviewer knows
        no round-trip check was possible.
    """
    checked = passed = downgraded = 0
    for c in table["concepts"]:
        en_norms = {norm_term(c.get("label_en") or "")}
        en_norms |= {norm_term(v["term"]) for v in c["variants"]
                     if v.get("lang") == "en"}
        en_norms.discard("")
        for v in c["variants"]:
            if v.get("source") != "controlled-translation":
                continue
            if v.get("lang") == "en":
                continue
            bt = norm_term(v.get("back_translation") or "")
            if not bt:
                v["verification"] = ("round-trip:no-evidence"
                                     if v.get("verified")
                                     else "round-trip:no-evidence-unverified")
                continue
            checked += 1
            if bt in en_norms:
                v["verified"] = True
                v["verification"] = "round-trip:back-translation-match"
                passed += 1
            else:
                v["verified"] = False
                v["status"] = "unverified"
                v["confidence"] = round(v.get("confidence", 0.5) * 0.5, 3)
                v["verification"] = "round-trip:failed"
                downgraded += 1
    log.append("round-trip verification: %d with back-translation evidence, "
               "%d passed, %d downgraded to unverified"
               % (checked, passed, downgraded))
    return checked, passed


def coverage_check(table, langs, log):
    """List missing (concept, language) pairs: the honest to_translate list."""
    missing = []
    for c in table["concepts"]:
        have = {v.get("lang") for v in c["variants"]}
        for lang in langs:
            if lang not in have:
                missing.append({"concept_id": c.get("concept_id"),
                                "label_en": c.get("label_en"),
                                "lang": lang,
                                "action": "needs controlled translation "
                                          "(Agent must supply term + "
                                          "back_translation evidence)"})
    log.append("coverage: %d concepts x %d languages; %d missing variants"
               % (len(table["concepts"]), len(langs), len(missing)))
    return missing

# ----------------------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(
        description="Build / merge the multilingual terminology table.")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/work/term_table.json")
    ap.add_argument("--workdir", default="/app/work")
    ap.add_argument("--roots", default=None,
                    help="comma-separated extra input roots")
    ap.add_argument("--seed", default=None,
                    help="seed terminology table JSON (e.g. a case-adapted "
                         "copy of resources/term_table_seed.json; the "
                         "built-in demo table is NOT loaded automatically "
                         "because its demo concepts would pollute queries)")
    ap.add_argument("--translations", default=None,
                    help="optional JSON file with Agent-supplied controlled "
                         "translations (entries need concept_id, lang, term; "
                         "back_translation recommended for verification)")
    ap.add_argument("--langs", default=None,
                    help="comma-separated declared target languages; default "
                         "comes from the seed table or en,zh,pt,es,ja,de")
    ap.add_argument("--max-candidates", type=int, default=60)
    args = ap.parse_args()

    started = time.time()
    work_dir = Path(args.workdir)
    try:
        work_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    log = ["term_table started " + time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                 time.gmtime())]

    roots = [r for r in DEFAULT_ROOTS if r]
    if args.roots:
        roots += [r.strip() for r in args.roots.split(",") if r.strip()]
    case_dir = str(Path(args.case).resolve().parent)
    if case_dir not in roots:
        roots.insert(0, case_dir)

    # -- load seed + discovered tables --------------------------------------
    table = empty_table()
    seed_path = Path(args.seed) if args.seed else None
    if seed_path is None:
        log.append("no --seed given: starting from an empty table; only "
                   "case-provided term tables and --translations are merged")
    elif seed_path.exists():
        concepts, _, note = load_table_file(str(seed_path), log)
        for c in concepts:
            merge_concept(table, c, str(seed_path), log)
        try:
            seed_data = json.loads(seed_path.read_text(encoding="utf-8"))
            table["languages_declared"] = list(
                seed_data.get("languages_declared") or [])
        except (OSError, json.JSONDecodeError):
            pass
        log.append("seed table loaded: %s (%d concepts)"
                   % (seed_path, len(concepts)))
    else:
        log.append("WARNING: seed table not found at %s" % seed_path)

    extra_skip = [Path(args.seed).name] if args.seed else []
    if args.translations:
        extra_skip.append(Path(args.translations).name)
    files = discover_files(roots, extra_skip=extra_skip)

    # case-provided term tables (any JSON with a "concepts" key) merge in
    for path in files:
        if path.suffix.lower() != ".json":
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                head = json.load(fh)
        except (OSError, json.JSONDecodeError, UnicodeError):
            continue
        if isinstance(head, dict) and isinstance(head.get("concepts"), list) \
                and str(path.resolve()) != str(Path(args.out).resolve()):
            for c in head["concepts"]:
                if isinstance(c, dict):
                    merge_concept(table, c, str(path), log)
            log.append("merged case-provided term table: %s" % path)

    # -- text collection + candidate extraction ------------------------------
    texts, parse_notes = collect_texts(files, log)
    known = set()
    for c in table["concepts"]:
        for v in c["variants"]:
            known.add(norm_term(v.get("term", "")))
    candidates = extract_candidates(texts, known, args.max_candidates)
    log.append("candidate extraction: %d candidate concepts/variants "
               "(top by frequency; NOT auto-added to the table)"
               % len(candidates))

    # -- controlled translations (Agent-supplied) ----------------------------
    if args.translations:
        _, entries, note = load_table_file(args.translations, log)
        apply_translation_entries(table, entries, args.translations, log)
    else:
        log.append("no --translations file: concepts not covered by the seed/"
                   "case tables remain in to_translate (no auto-translation)")

    # -- verification + coverage ---------------------------------------------
    n_checked, n_passed = verify_roundtrip(table, log)
    langs = ([l.strip() for l in args.langs.split(",") if l.strip()]
             if args.langs else None) \
        or table.get("languages_declared") \
        or ["en", "zh", "pt", "es", "ja", "de"]
    table["languages_declared"] = langs
    to_translate = coverage_check(table, langs, log)

    # concepts from candidates that are not yet in the table at all
    table_concepts_norm = {norm_term(c.get("label_en") or "")
                           for c in table["concepts"]}
    new_candidates = [c for c in candidates
                      if c["surface"] not in table_concepts_norm
                      and c["surface"] not in known]

    out = {
        "term_table_format": "1.0",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "languages_declared": langs,
        "concepts": table["concepts"],
        "concept_count": len(table["concepts"]),
        "variant_count": sum(len(c["variants"]) for c in table["concepts"]),
        "roundtrip": {"checked": n_checked, "passed": n_passed,
                      "downgraded": n_checked - n_passed},
        "to_translate": to_translate,
        "candidate_concepts": new_candidates,
        "parse_notes": parse_notes,
        "run_log": log + ["finished in %.1fs" % (time.time() - started)],
    }
    out_path = Path(args.out)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    except OSError as exc:
        fallback = work_dir / "term_table.json"
        fallback.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        log.append("WARNING: could not write %s (%s); wrote %s"
                   % (out_path, exc, fallback))
        out_path = fallback
    try:
        (work_dir / "term_table_runlog.json").write_text(
            json.dumps(out["run_log"], ensure_ascii=False, indent=2),
            encoding="utf-8")
    except OSError:
        pass
    print(json.dumps({"term_table": str(out_path),
                      "concepts": out["concept_count"],
                      "variants": out["variant_count"],
                      "to_translate": len(to_translate),
                      "roundtrip": out["roundtrip"],
                      "candidates": len(new_candidates)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
