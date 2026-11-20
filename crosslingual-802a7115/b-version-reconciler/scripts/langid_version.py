#!/usr/bin/env python3
"""Language identification and version-type determination for scholarly records.

Stdlib only (Python 3.8+). Deterministic, offline, fault-tolerant, fully
evidence-logged. Stage 1 of the xlang-version-reconciler skill.

What it does
------------
1. Discovers candidate record files under /input, /app/work and the current
   directory (override/extend with --roots). Handles .json / .jsonl / .ndjson /
   .csv / .tsv record files AND .txt / .md files (the latter are treated as
   extracted full text, e.g. output of the platform pdf-text-tool / ocr-tool).
   Every record keeps a source locator (file + JSON path / line / row).
2. For each record, samples the actual body text (head/middle/tail slices of
   the fulltext field, or the abstract / title when no fulltext exists) and
   computes Unicode-range statistics (Latin basic + Latin Extended diacritics,
   CJK Unified, Hiragana, Katakana, Hangul, Cyrillic, Arabic) plus function-word
   (stopword) scoring for Latin-script languages (en/pt/es/fr/de/it) with
   distinctive-diacritic tie-breaking (ã/õ -> pt, ñ -> es, ä/ö/ü/ß -> de ...).
3. Combines the TEXT-based language with metadata language fields and
   publisher/relation fields to decide the version type of each record:
   original / publisher-translation / abstract-only-english / bilingual /
   exact-duplicate / undetermined. TEXT OVERRIDES METADATA LABELS on conflict;
   every conflict is recorded.
4. Flags explicit exact duplicates (same DOI-or-title fingerprint AND identical
   normalized text hash, or an explicit duplicate_of field).
5. Writes /app/work/langid_report.json with, for every record: the decision,
   its confidence, the sampled-text statistics, the metadata evidence, the
   decision path (which rule fired) and a back-pointer to the raw record.
   A human/agent-readable run log goes to /app/work/langid_run_log.json.

Nothing is inferred from file names or labels alone: labels are evidence, the
actual text is decisive. Records with insufficient text AND missing metadata
are marked body_language=undetermined / version_type=undetermined, never
guessed.

Usage
-----
    python3 langid_version.py [--roots /input,/app/work,.] \
        [--out /app/work/langid_report.json] [--workdir /app/work] \
        [--max-chars 12000] [--min-fulltext 300]

Exit code is 0 even when some files fail to parse; parse problems are recorded
in the report's parse_notes and run log.
"""
import argparse
import csv
import hashlib
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

# ----------------------------------------------------------------------------- config

DEFAULT_ROOTS = ["/input", "/app/work", "."]
RECORD_EXTS = (".json", ".jsonl", ".ndjson", ".csv", ".tsv")
TEXT_EXTS = (".txt", ".md")
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "output",
             ".claude"}
SKIP_FILES = {"result.json", "langid_report.json", "reconcile_report.json",
              "run_log.json", "langid_run_log.json", "reconcile_run_log.json",
              "verify_report.json", "case.json", "task.md", "SKILL.md",
              "README.md"}
MAX_FILE_BYTES = 60 * 1024 * 1024
MAX_FILES = 400
MIN_TEXT_CHARS = 40          # below this a sample is "insufficient text"
MIN_FULLTEXT_CHARS = 300     # fulltext field shorter than this counts as absent
ABSTRACT_MIN_CHARS = 80      # abstract shorter than this counts as unusable
SAMPLE_SLICE = 4000          # head/middle/tail slice size for fulltext sampling

# ISO 639 normalization (small table covering common bibliographic codes)
LANG_CODE_MAP = {
    "en": "en", "eng": "en", "english": "en",
    "pt": "pt", "por": "pt", "portuguese": "pt", "pt-br": "pt",
    "es": "es", "spa": "es", "spanish": "es",
    "fr": "fr", "fra": "fr", "fre": "fr", "french": "fr",
    "de": "de", "deu": "de", "ger": "de", "german": "de",
    "it": "it", "ita": "it", "italian": "it",
    "ja": "ja", "jpn": "ja", "japanese": "ja",
    "zh": "zh", "zho": "zh", "chi": "zh", "chinese": "zh", "zh-cn": "zh",
    "ru": "ru", "rus": "ru", "russian": "ru",
    "ko": "ko", "kor": "ko", "korean": "ko",
    "ar": "ar", "ara": "ar", "arabic": "ar",
    "la": "la", "lat": "la", "latin": "la",
    "nl": "nl", "nld": "nl", "dut": "nl",
    "pl": "pl", "pol": "pl",
    "uk": "uk", "ukr": "uk",
    "tr": "tr", "tur": "tr",
    "und": "undetermined", "unknown": "undetermined", "": None,
}

# Function-word lists for Latin-script language scoring. Kept short and
# high-frequency; scoring is a count of token hits, not a classifier.
STOPWORDS = {
    "en": {"the", "of", "and", "in", "to", "was", "were", "is", "are", "for",
           "with", "as", "by", "on", "that", "this", "from", "an", "be",
           "has", "have", "had", "been", "we", "it", "at", "or", "not",
           "their", "but", "they", "these", "which", "between", "using",
           "than", "its", "after", "during", "study", "results"},
    "pt": {"de", "a", "o", "que", "e", "do", "da", "em", "um", "para",
           "com", "uma", "os", "no", "se", "na", "por", "mais", "as", "dos",
           "como", "mas", "foi", "ao", "ele", "das", "tem", "seu", "sua",
           "ou", "ser", "nos", "está", "também", "pelo", "pela", "isso",
           "entre", "depois", "sem", "mesmo", "são", "estudo", "foram",
           "essa", "esse", "num", "numa", "às", "não", "é", "à", "há"},
    "es": {"de", "la", "que", "el", "en", "y", "a", "los", "del", "se",
           "las", "por", "un", "para", "con", "no", "una", "su", "al", "es",
           "lo", "como", "más", "pero", "sus", "le", "ya", "o", "este",
           "esta", "entre", "cuando", "muy", "sin", "sobre", "también",
           "hasta", "hay", "donde", "desde", "todo", "nos", "está", "son",
           "fue", "estudio", "ser", "han", "han", "puede", "estos", "estas"},
    "fr": {"le", "la", "les", "de", "des", "et", "en", "un", "une", "du",
           "est", "dans", "pour", "que", "qui", "au", "sur", "par", "pas",
           "plus", "avec", "ce", "se", "son", "sont", "aux", "il", "elle",
           "nous", "vous", "leur", "ses", "ces", "ou", "comme", "mais",
           "aussi", "entre", "après", "sans", "sous", "cette", "étude",
           "ont", "été", "être", "d'une", "d'un", "ne", "sa"},
    "de": {"der", "die", "das", "und", "in", "den", "von", "zu", "mit",
           "ist", "für", "auf", "ein", "eine", "dem", "des", "an", "im",
           "als", "auch", "bei", "oder", "nach", "wie", "aus", "durch",
           "über", "nicht", "sind", "war", "werden", "wurde", "sich", "es",
           "sie", "wir", "er", "zur", "zum", "zwischen", "unter", "vor",
           "einer", "einem", "einen", "kann", "studie", "bei"},
    "it": {"di", "e", "il", "la", "che", "in", "un", "una", "per", "del",
           "della", "con", "le", "non", "si", "da", "dei", "delle", "al",
           "lo", "alla", "nel", "sono", "come", "più", "anche", "questo",
           "questa", "gli", "ai", "ma", "tra", "cui", "ha", "hanno", "dopo",
           "molto", "è", "studio", "stato", "essere", "una", "sul", "nei"},
}

# Distinctive characters used only (or overwhelmingly) in one language;
# used as tie-breakers when stopword scores are close.
DISTINCTIVE_CHARS = {
    "pt": "ãõ",
    "es": "ñ¿¡",
    "de": "äöüß",
    "fr": "œ",
    "it": "ìò",
}

FULLTEXT_KEYS = ("fulltext", "full_text", "fullText", "body", "text",
                 "content", "pdf_text", "extracted_text", "plaintext",
                 "plain_text", "ocr_text")
ABSTRACT_KEYS = ("abstract", "Abstract", "resumo", "summary", "description")
TITLE_KEYS = ("title", "Title", "article-title", "article_title",
              "display_name", "dc_title", "original_title")
LANG_KEYS = ("language", "lang", "language_code", "dc_language",
             "text_language", "languages")
TRANSLATION_KEYS = ("translation_of", "is_translation_of", "isTranslationOf",
                    "original_doi", "translated_from", "translationOf")
DUP_KEYS = ("duplicate_of", "is_duplicate_of", "duplicateOf", "same_as")
AUTHOR_KEYS = ("author", "authors", "authorString", "authorships",
               "creators", "dc_creator")

# ----------------------------------------------------------------------------- utils


def norm_doi(value):
    if not value:
        return None
    v = str(value).strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:"):
        if v.startswith(prefix):
            v = v[len(prefix):]
    v = v.rstrip(".;,")
    return v or None


def fold_diacritics(value):
    """NFKD-fold accented Latin letters and lowercase: title/author matching."""
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value))
    stripped = "".join(c for c in decomposed
                       if unicodedata.category(c) != "Mn")
    return stripped.lower()


def norm_text(value):
    """Whitespace-collapsed, case-folded text used for duplicate hashing."""
    return " ".join(fold_diacritics(value).split())


def text_hash(value):
    return hashlib.sha1(norm_text(value)[:4000].encode("utf-8")).hexdigest()


def norm_lang_code(value):
    if value is None:
        return None
    v = str(value).strip().lower().replace("_", "-")
    v = v.split(";")[0].strip()
    if v in LANG_CODE_MAP:
        return LANG_CODE_MAP[v]
    if v[:2] in LANG_CODE_MAP:
        return LANG_CODE_MAP[v[:2]]
    if v[:3] in LANG_CODE_MAP:
        return LANG_CODE_MAP[v[:3]]
    return "undetermined"


def first_surname(authors):
    if not authors:
        return None
    a = authors[0]
    if isinstance(a, dict):
        name = a.get("family") or a.get("name") or ""
    else:
        name = str(a)
    name = fold_diacritics(name).split(",")[0].strip().split()
    return name[-1] if name else None


def author_surnames(authors):
    out = []
    for a in authors or []:
        if isinstance(a, dict):
            name = a.get("family") or a.get("name") or ""
        else:
            name = str(a)
        name = fold_diacritics(name).split(",")[0].strip().split()
        if name:
            out.append(name[-1])
    return out

# --------------------------------------------------------------------- unicode stats


def script_stats(text):
    """Count characters per Unicode script range."""
    counts = {"latin_basic": 0, "latin_ext": 0, "cjk": 0, "hiragana": 0,
              "katakana": 0, "hangul": 0, "cyrillic": 0, "arabic": 0,
              "other": 0}
    for ch in text:
        cp = ord(ch)
        if 0x41 <= cp <= 0x5A or 0x61 <= cp <= 0x7A:
            counts["latin_basic"] += 1
        elif 0x00C0 <= cp <= 0x024F or 0x1E00 <= cp <= 0x1EFF:
            counts["latin_ext"] += 1
        elif 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF:
            counts["cjk"] += 1
        elif 0x3040 <= cp <= 0x309F:
            counts["hiragana"] += 1
        elif 0x30A0 <= cp <= 0x30FF or 0xFF66 <= cp <= 0xFF9D:
            counts["katakana"] += 1
        elif 0xAC00 <= cp <= 0xD7AF or 0x1100 <= cp <= 0x11FF:
            counts["hangul"] += 1
        elif 0x0400 <= cp <= 0x04FF:
            counts["cyrillic"] += 1
        elif 0x0600 <= cp <= 0x06FF or 0x0750 <= cp <= 0x077F:
            counts["arabic"] += 1
        elif ch.isalpha():
            counts["other"] += 1
    return counts


def latin_language_scores(text):
    """Score Latin-script candidate languages by function-word hits."""
    raw_tokens = re.findall(r"[a-zà-öø-ÿ']+", str(text).lower())
    # fold diacritics so that "não"->"nao", "está"->"esta" etc. match the
    # (equally folded) stopword sets
    tokens = [fold_diacritics(t) for t in raw_tokens]
    total = max(1, len(tokens))
    scores = {}
    for lang, words in STOPWORDS.items():
        folded_words = {fold_diacritics(w) for w in words}
        hits = sum(1 for t in tokens if t in folded_words)
        scores[lang] = {"hits": hits, "ratio": round(hits / total, 4)}
    return scores, len(tokens)


def distinctive_hits(text):
    lowered = str(text).lower()
    return {lang: sum(lowered.count(c) for c in chars)
            for lang, chars in DISTINCTIVE_CHARS.items()}


def detect_language(text, max_chars):
    """Detect the language of a text sample.

    Returns a dict with code/confidence and the full evidence (script counts,
    latin scores, distinctive-char hits). Never raises."""
    result = {"code": "undetermined", "confidence": "low",
              "script_counts": {}, "latin_scores": {},
              "distinctive_hits": {}, "basis_detail": ""}
    if not text:
        result["basis_detail"] = "no text available"
        return result
    sample = text[:max_chars]
    counts = script_stats(sample)
    result["script_counts"] = counts
    letters = sum(counts.values())
    if letters < MIN_TEXT_CHARS:
        result["basis_detail"] = ("insufficient alphabetic text (%d chars)"
                                  % letters)
        return result
    frac = {k: v / letters for k, v in counts.items()}

    # Non-Latin scripts: script identity is decisive.
    kana = counts["hiragana"] + counts["katakana"]
    if kana >= 3 and (kana / letters) > 0.01:
        result.update(code="ja", confidence="high",
                      basis_detail="hiragana/katakana present (%d kana chars, "
                                   "%.1f%% of letters)" % (kana, 100 * kana / letters))
        return result
    if frac["hangul"] > 0.10:
        result.update(code="ko", confidence="high",
                      basis_detail="hangul share %.1f%%" % (100 * frac["hangul"]))
        return result
    if frac["cjk"] > 0.20:
        result.update(code="zh", confidence="high",
                      basis_detail="CJK share %.1f%% without kana"
                      % (100 * frac["cjk"]))
        return result
    if frac["cyrillic"] > 0.30:
        result.update(code="ru", confidence="high",
                      basis_detail="cyrillic share %.1f%%"
                      % (100 * frac["cyrillic"]))
        return result
    if frac["arabic"] > 0.30:
        result.update(code="ar", confidence="high",
                      basis_detail="arabic share %.1f%%" % (100 * frac["arabic"]))
        return result

    # Latin-script: function-word scoring + distinctive-char tie-break.
    latin = counts["latin_basic"] + counts["latin_ext"]
    if latin / letters < 0.5:
        result["basis_detail"] = ("mixed script, latin share %.1f%%; cannot "
                                  "decide" % (100 * latin / letters))
        return result
    scores, n_tokens = latin_language_scores(sample)
    result["latin_scores"] = scores
    result["distinctive_hits"] = distinctive_hits(sample)
    ranked = sorted(scores.items(), key=lambda kv: kv[1]["hits"], reverse=True)
    top_lang, top = ranked[0]
    second_lang, second = ranked[1]
    if top["hits"] < 3:
        result["basis_detail"] = ("too few function-word hits (%d over %d "
                                  "tokens)" % (top["hits"], n_tokens))
        return result
    tiebreak = ""
    if second["hits"] > 0 and (top["hits"] - second["hits"]) <= max(2, 0.15 * top["hits"]):
        # close call: distinctive characters decide; else undetermined-ish
        hits = result["distinctive_hits"]
        cand = {top_lang: hits.get(top_lang, 0), second_lang: hits.get(second_lang, 0)}
        winner = max(cand, key=cand.get)
        if cand[winner] > 0 and cand[winner] > cand[min(cand, key=cand.get)]:
            tiebreak = ("; close stopword scores (%s=%d vs %s=%d), decided by "
                        "distinctive characters (%s=%d)"
                        % (top_lang, top["hits"], second_lang, second["hits"],
                           winner, cand[winner]))
            result.update(code=winner, confidence="medium",
                          basis_detail="latin function-word scoring" + tiebreak)
            return result
        result.update(code=top_lang, confidence="low",
                      basis_detail=("latin function-word scoring, close scores "
                                    "(%s=%d vs %s=%d), no distinctive-character "
                                    "tiebreak; treat as tentative"
                                    % (top_lang, top["hits"], second_lang,
                                       second["hits"])))
        return result
    conf = "high" if top["hits"] >= 8 and top["hits"] >= 2 * max(1, second["hits"]) \
        else "medium"
    result.update(code=top_lang, confidence=conf,
                  basis_detail=("latin function-word scoring: %s %d hits vs "
                                "runner-up %s %d hits over %d tokens"
                                % (top_lang, top["hits"], second_lang,
                                   second["hits"], n_tokens)))
    return result

# --------------------------------------------------------------------- record parsing


def _authors_from(value):
    out = []
    if isinstance(value, list):
        for a in value[:25]:
            if isinstance(a, dict):
                if "family" in a or "given" in a:
                    out.append({"given": a.get("given"), "family": a.get("family")})
                elif "name" in a:
                    out.append({"name": a.get("name")})
                elif isinstance(a.get("author"), dict):
                    out.append({"name": a["author"].get("display_name")})
            elif isinstance(a, str):
                out.append({"name": a})
    elif isinstance(value, str):
        for part in value.split(",")[:25]:
            part = part.strip()
            if part:
                out.append({"name": part})
    return out


def _year_from(obj):
    for k in ("year", "pubYear", "publication_year", "publishedYear"):
        v = obj.get(k)
        if v:
            try:
                return int(str(v)[:4])
            except ValueError:
                pass
    for k in ("issued", "published", "published-print", "published-online",
              "created", "publication_date"):
        v = obj.get(k)
        if isinstance(v, dict) and "date-parts" in v:
            try:
                return int(v["date-parts"][0][0])
            except (TypeError, IndexError, ValueError):
                pass
        elif isinstance(v, str):
            m = re.match(r"(\d{4})", v)
            if m:
                return int(m.group(1))
    return None


def _pick_str(obj, keys):
    for k in keys:
        v = obj.get(k)
        if isinstance(v, list):
            v = v[0] if v else None
        if isinstance(v, dict):
            v = v.get("value") or v.get("display_name")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _languages_from(obj):
    langs = []
    for k in LANG_KEYS:
        v = obj.get(k)
        vals = v if isinstance(v, list) else [v]
        for item in vals:
            code = norm_lang_code(item)
            if code and code != "undetermined" and code not in langs:
                langs.append(code)
    return langs


def _relation_from(obj):
    """Extract explicit translation/duplicate relations from a record."""
    rel = {"translation_of": None, "duplicate_of": None}
    for k in TRANSLATION_KEYS:
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            rel["translation_of"] = norm_doi(v) or v.strip()
    for k in DUP_KEYS:
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            rel["duplicate_of"] = norm_doi(v) or v.strip()
    relation = obj.get("relation")
    items = []
    if isinstance(relation, dict):
        for k, v in relation.items():
            items.append((k, v))
    elif isinstance(relation, list):
        for it in relation:
            if isinstance(it, dict):
                items.append((it.get("type") or it.get("relation") or "",
                              it.get("doi") or it.get("id") or it.get("value")
                              or it.get("target") or ""))
            elif isinstance(it, str):
                items.append(("", it))
    for typ, val in items:
        tval = norm_doi(val) or (str(val).strip() if val else None)
        if not tval:
            continue
        t = str(typ).lower()
        if "translat" in t and not rel["translation_of"]:
            rel["translation_of"] = tval
        if ("duplicat" in t or "same" in t) and not rel["duplicate_of"]:
            rel["duplicate_of"] = tval
    return rel


def _cjkish_chars(text, cap=20000):
    return sum(1 for ch in text[:cap]
               if 0x3040 <= ord(ch) <= 0x30FF      # kana
               or 0x3400 <= ord(ch) <= 0x9FFF      # CJK unified + ext A
               or 0xAC00 <= ord(ch) <= 0xD7AF)     # hangul syllables


def _counts_as_fulltext(text, min_chars):
    """A fulltext field counts as full text if it is long enough. CJK/kana/
    hangul characters carry roughly twice the information per character of
    Latin text, so they count double against the threshold."""
    if not text:
        return False
    if len(text) >= min_chars:
        return True
    return 2 * _cjkish_chars(text) >= min_chars


def record_from_object(obj, locator):
    """Interpret one JSON object / CSV row as a candidate scholarly record."""
    if not isinstance(obj, dict):
        return None
    title = _pick_str(obj, TITLE_KEYS)
    doi = norm_doi(obj.get("DOI") or obj.get("doi"))
    abstract = _pick_str(obj, ABSTRACT_KEYS)
    fulltext = None
    fulltext_key = None
    for k in FULLTEXT_KEYS:
        v = obj.get(k)
        if isinstance(v, str) and len(v.strip()) >= len(fulltext or ""):
            fulltext, fulltext_key = v.strip(), k
    if not (title or doi or fulltext):
        return None
    venue = _pick_str(obj, ("container-title", "journal", "journalTitle",
                            "venue", "bookTitle", "source"))
    rel = _relation_from(obj)
    rec = {
        "locator": locator,
        "doi": doi,
        "title": title,
        "authors": _authors_from(next((obj[k] for k in AUTHOR_KEYS
                                       if k in obj), None)),
        "year": _year_from(obj),
        "venue": venue,
        "publisher": _pick_str(obj, ("publisher", "dc_publisher")),
        "volume": obj.get("volume"),
        "issue": obj.get("issue"),
        "first_page": (str(obj.get("page") or obj.get("first_page")
                           or obj.get("pages") or "").split("-")[0] or None),
        "issn": obj.get("ISSN") or obj.get("issn"),
        "metadata_languages": _languages_from(obj),
        "abstract": abstract,
        "fulltext": fulltext
                    if _counts_as_fulltext(fulltext, MIN_FULLTEXT_CHARS)
                    else None,
        "fulltext_field": fulltext_key
                          if _counts_as_fulltext(fulltext, MIN_FULLTEXT_CHARS)
                          else None,
        "relation": rel,
    }
    if isinstance(obj.get("ISSN"), list):
        rec["issn"] = obj["ISSN"][0] if obj["ISSN"] else None
    return rec


def walk_json(obj, path, file_path, sink, depth=0):
    if depth > 12:
        return
    if isinstance(obj, dict):
        rec = record_from_object(obj, {"file": file_path, "pointer": path or "$"})
        if rec is not None:
            sink.append(rec)
            return
        for k, v in obj.items():
            if k in FULLTEXT_KEYS + ABSTRACT_KEYS + AUTHOR_KEYS:
                continue
            walk_json(v, "%s/%s" % (path, k), file_path, sink, depth + 1)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:20000]):
            walk_json(v, "%s/%d" % (path, i), file_path, sink, depth + 1)


def parse_csv_file(path, sink, notes):
    file_path = str(path)
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;") \
                if sample.strip() else csv.excel
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(fh, dialect=dialect)
        for i, row in enumerate(reader):
            rec = record_from_object({k: v for k, v in row.items() if v},
                                     {"file": file_path,
                                      "pointer": "row/%d" % (i + 2)})
            if rec:
                sink.append(rec)


DOI_IN_TEXT_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>\]]+")


def record_from_textfile(path):
    """Treat a .txt/.md file as extracted full text (e.g. pdf-text-tool /
    ocr-tool output). DOI/title are recovered from the text when present;
    the file is NEVER assumed to be a particular language from its name."""
    file_path = str(path)
    with open(path, encoding="utf-8", errors="replace") as fh:
        content = fh.read(MAX_FILE_BYTES)
    doi = None
    m = DOI_IN_TEXT_RE.search(content)
    if m:
        doi = norm_doi(m.group(0))
    first_line = next((ln.strip() for ln in content.splitlines()
                       if ln.strip()), None)
    title = first_line[:200] if first_line and len(first_line) < 200 else None
    return {
        "locator": {"file": file_path, "pointer": "file"},
        "doi": doi,
        "title": title,
        "authors": [],
        "year": None,
        "venue": None,
        "publisher": None,
        "volume": None,
        "issue": None,
        "first_page": None,
        "issn": None,
        "metadata_languages": [],
        "abstract": None,
        "fulltext": content.strip() or None,
        "fulltext_field": "file_content",
        "relation": {"translation_of": None, "duplicate_of": None},
    }


def discover_files(roots):
    seen, out = set(), []
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
                elif node.suffix.lower() in RECORD_EXTS + TEXT_EXTS \
                        and node.name not in SKIP_FILES:
                    rp = str(node.resolve())
                    if rp in seen or node.stat().st_size > MAX_FILE_BYTES:
                        continue
                    seen.add(rp)
                    out.append(node)
            except (OSError, PermissionError):
                continue
    return out


def collect_records(roots, log):
    records, sources, notes = [], [], []
    files = discover_files(roots)
    for path in files:
        file_path = str(path)
        suffix = path.suffix.lower()
        try:
            if suffix == ".json":
                with open(path, encoding="utf-8", errors="replace") as fh:
                    walk_json(json.load(fh), "$", file_path, records)
                sources.append(file_path)
            elif suffix in (".jsonl", ".ndjson"):
                with open(path, encoding="utf-8", errors="replace") as fh:
                    for i, line in enumerate(fh):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            walk_json(json.loads(line), "$/%d" % i,
                                      file_path, records)
                        except json.JSONDecodeError:
                            notes.append("bad JSONL line %s:%d"
                                         % (file_path, i + 1))
                sources.append(file_path)
            elif suffix in (".csv", ".tsv"):
                parse_csv_file(path, records, notes)
                sources.append(file_path)
            elif suffix in TEXT_EXTS:
                rec = record_from_textfile(path)
                if rec["fulltext"]:
                    records.append(rec)
                    sources.append(file_path)
        except (OSError, UnicodeError, json.JSONDecodeError, csv.Error) as exc:
            notes.append("skipped %s: %s" % (file_path, exc))
    log.append("discovered %d files, collected %d candidate records"
               % (len(sources), len(records)))
    return records, sources, notes

# --------------------------------------------------------------------- classification


def sample_fulltext(text):
    """Head/middle/tail sampling of a long fulltext; returns (sample, spec)."""
    if len(text) <= 3 * SAMPLE_SLICE:
        return text, {"slices": [{"offset": 0, "chars": len(text)}]}
    mid = max(0, (len(text) - SAMPLE_SLICE) // 2)
    tail = max(0, len(text) - SAMPLE_SLICE)
    parts = [text[:SAMPLE_SLICE], text[mid:mid + SAMPLE_SLICE],
             text[tail:tail + SAMPLE_SLICE]]
    spec = {"slices": [{"offset": 0, "chars": SAMPLE_SLICE},
                       {"offset": mid, "chars": SAMPLE_SLICE},
                       {"offset": tail, "chars": SAMPLE_SLICE}]}
    return "\n".join(parts), spec


def classify_record(rec, args):
    """Decide body_language + text_availability + version_type for one record.

    Returns (annotated detection dict, conflicts list, notes list)."""
    conflicts, notes = [], []
    det = {"sampled_field": None, "sample": None, "detection": None,
           "abstract_detection": None, "title_detection": None}

    fulltext = rec.get("fulltext")
    abstract = rec.get("abstract")
    title = rec.get("title")
    meta_langs = rec.get("metadata_languages") or []
    meta_lang = meta_langs[0] if meta_langs else None

    if fulltext:
        text_availability = "fulltext"
    elif abstract and len(abstract) >= ABSTRACT_MIN_CHARS:
        text_availability = "abstract-only"
    else:
        text_availability = "metadata-only"

    body_lang = {"code": "undetermined", "confidence": "low",
                 "basis": "none"}
    if fulltext:
        sample, spec = sample_fulltext(fulltext)
        detection = detect_language(sample, args.max_chars)
        det.update(sampled_field=rec.get("fulltext_field") or "fulltext",
                   sample=spec, detection=detection)
        body_lang = {"code": detection["code"],
                     "confidence": detection["confidence"],
                     "basis": "fulltext"}
    elif abstract and len(abstract) >= ABSTRACT_MIN_CHARS:
        detection = detect_language(abstract, args.max_chars)
        det.update(sampled_field="abstract",
                   sample={"slices": [{"offset": 0,
                                       "chars": min(len(abstract),
                                                    args.max_chars)}]},
                   detection=detection)
        body_lang = {"code": detection["code"],
                     "confidence": "medium"
                     if detection["confidence"] == "high" else "low",
                     "basis": "abstract"}
    if abstract:
        det["abstract_detection"] = detect_language(abstract, args.max_chars)
    if title:
        det["title_detection"] = detect_language(title, args.max_chars)

    # Text overrides metadata labels; record every conflict. Only fulltext
    # evidence can conflict with the label: an English ABSTRACT under a
    # non-English label is not a conflict but the defining pattern of
    # abstract-only-english records (handled by rules R4a/R4b below).
    if text_availability == "fulltext" and meta_lang \
            and body_lang["code"] != "undetermined" \
            and meta_lang != body_lang["code"]:
        conflicts.append({
            "kind": "language_label_conflict",
            "metadata_language": meta_lang,
            "text_language": body_lang["code"],
            "resolution": "text wins (actual sampled text is decisive)",
            "basis": body_lang["basis"]})
        notes.append("metadata language '%s' conflicts with detected text "
                     "language '%s'; text wins" % (meta_lang,
                                                   body_lang["code"]))

    # ---- version type decision (priority order, see rules/version_policy.md)
    vtype, vconf, rule = None, "low", None
    rel = rec.get("relation") or {}

    if rel.get("duplicate_of"):
        vtype, vconf, rule = "exact-duplicate", "high", "R1-explicit-duplicate-field"
    elif rel.get("translation_of"):
        vtype, vconf, rule = "publisher-translation", "high", \
            "R2-explicit-translation-relation"
    elif len(meta_langs) >= 2:
        vtype, vconf, rule = "bilingual", "medium", \
            "R3-multiple-metadata-languages"
    elif text_availability == "abstract-only":
        abs_code = (det.get("abstract_detection") or {}).get("code")
        title_code = (det.get("title_detection") or {}).get("code")
        if abs_code == "en" and meta_lang and meta_lang != "en":
            vtype, vconf, rule = "abstract-only-english", "high", \
                "R4a-english-abstract-nonenglish-metadata"
            body_lang = {"code": meta_lang, "confidence": "medium",
                         "basis": "metadata (fulltext unavailable; abstract "
                                  "is English)"}
        elif abs_code == "en" and not meta_lang and title_code not in (None, "en", "undetermined"):
            vtype, vconf, rule = "abstract-only-english", "medium", \
                "R4b-english-abstract-nonenglish-title"
            body_lang = {"code": title_code, "confidence": "low",
                         "basis": "title text (fulltext unavailable; "
                                  "abstract is English)"}
        elif abs_code == "en" and not meta_lang:
            vtype, vconf, rule = "undetermined", "low", \
                "R4c-english-abstract-no-body-evidence"
        elif abs_code and abs_code != "undetermined":
            vtype, vconf, rule = "original", "low", \
                "R4d-nonenglish-abstract-only"
        else:
            vtype, vconf, rule = "undetermined", "low", \
                "R4e-abstract-language-undetermined"
    elif text_availability == "fulltext":
        if body_lang["code"] == "undetermined":
            vtype, vconf, rule = "undetermined", "low", \
                "R5a-fulltext-language-undetermined"
        elif conflicts:
            # text says one language, label another, no translation declared:
            # cannot prove original vs translation -> honest undetermined
            vtype, vconf, rule = "undetermined", "medium", \
                "R5b-language-conflict-no-translation-declaration"
        else:
            vtype, vconf, rule = "original", \
                ("high" if body_lang["confidence"] == "high" else "medium"), \
                "R5c-fulltext-no-translation-flags"
    else:  # metadata-only
        if meta_lang:
            vtype, vconf, rule = "undetermined", "low", \
                "R6a-metadata-only (language inferred, text unavailable)"
            body_lang = {"code": meta_lang, "confidence": "low",
                         "basis": "metadata only; NO text available, "
                                  "unverified"}
        else:
            vtype, vconf, rule = "undetermined", "low", \
                "R6b-no-text-no-metadata"

    det["decision_rule"] = rule
    return det, body_lang, text_availability, vtype, vconf, conflicts, notes

# --------------------------------------------------------------------- duplicates


def fingerprint(rec):
    if rec.get("doi"):
        return "doi:" + rec["doi"]
    if rec.get("title"):
        sur = first_surname(rec.get("authors"))
        return "t:%s|%s|%s" % (norm_text(rec["title"])[:80], sur or "",
                               rec.get("year") or "")
    return None


def flag_exact_duplicates(records, log):
    """Group records that are explicit full copies: same fingerprint AND
    identical normalized text hash (or explicit duplicate_of field)."""
    by_fp = {}
    groups = []
    for rec in records:
        fp = fingerprint(rec)
        rec["_fp"] = fp
        body = rec.get("fulltext") or rec.get("abstract") or ""
        rec["_th"] = text_hash(body) if body else None
        by_fp.setdefault(fp, []).append(rec)
    for fp, group in by_fp.items():
        if fp is None or len(group) < 2:
            continue
        keeper = group[0]
        for other in group[1:]:
            same_text = (other["_th"] and keeper["_th"]
                         and other["_th"] == keeper["_th"]) \
                or (not other["_th"] and not keeper["_th"]
                    and fp.startswith("doi:"))
            explicit = (other.get("relation") or {}).get("duplicate_of")
            if same_text or explicit:
                other["_dup_of"] = keeper["record_id"]
                other["_dup_basis"] = ("explicit duplicate_of field" if explicit
                                       else "identical fingerprint (%s) and "
                                            "identical normalized text hash"
                                            % fp)
                groups.append({"record": other["record_id"],
                               "duplicate_of": keeper["record_id"],
                               "basis": other["_dup_basis"]})
    # explicit duplicate_of pointing at a record outside the same fingerprint
    ids = {r["record_id"]: r for r in records}
    doi_idx = {r["doi"]: r["record_id"] for r in records if r.get("doi")}
    for rec in records:
        target = (rec.get("relation") or {}).get("duplicate_of")
        if target and "_dup_of" not in rec:
            tid = doi_idx.get(norm_doi(target))
            if tid and tid != rec["record_id"]:
                rec["_dup_of"] = tid
                rec["_dup_basis"] = "explicit duplicate_of field -> %s" % tid
                groups.append({"record": rec["record_id"],
                               "duplicate_of": tid,
                               "basis": rec["_dup_basis"]})
            else:
                rec.setdefault("_notes", []).append(
                    "duplicate_of target '%s' not found among records; kept "
                    "separate" % target)
    if groups:
        log.append("flagged %d exact-duplicate record(s)" % len(groups))
    return groups

# ----------------------------------------------------------------------------- main


def main():
    global MIN_FULLTEXT_CHARS
    ap = argparse.ArgumentParser(
        description="Language identification and version-type determination "
                    "for scholarly records (stdlib only, offline).")
    ap.add_argument("--roots", default=None,
                    help="comma-separated search roots "
                         "(default: /input,/app/work,.)")
    ap.add_argument("--out", default="/app/work/langid_report.json",
                    help="report output path")
    ap.add_argument("--workdir", default="/app/work",
                    help="work directory for the run log")
    ap.add_argument("--max-chars", type=int, default=12000,
                    help="max characters sampled per text for statistics")
    ap.add_argument("--min-fulltext", type=int, default=MIN_FULLTEXT_CHARS,
                    help="minimum chars for a fulltext field to count as "
                         "full text (shorter -> treated as absent)")
    args = ap.parse_args()
    MIN_FULLTEXT_CHARS = args.min_fulltext

    started = time.time()
    work_dir = Path(args.workdir)
    try:
        work_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    log = ["langid_version started "
           + time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())]

    roots = [r.strip() for r in args.roots.split(",")] if args.roots \
        else list(DEFAULT_ROOTS)
    records, sources, notes = collect_records(roots, log)

    for i, rec in enumerate(records, 1):
        rec["record_id"] = "r%04d" % i

    dup_groups = flag_exact_duplicates(records, log)

    by_lang, by_vtype = {}, {}
    out_records = []
    for rec in records:
        det, body_lang, availability, vtype, vconf, conflicts, rnotes = \
            classify_record(rec, args)
        if "_dup_of" in rec:
            vtype, vconf = "exact-duplicate", "high"
            det["decision_rule"] = "R0-exact-duplicate (%s)" % rec["_dup_basis"]
            rnotes.append("exact duplicate of %s: %s"
                          % (rec["_dup_of"], rec["_dup_basis"]))
        for n in rec.get("_notes", []):
            rnotes.append(n)
        entry = {
            "record_id": rec["record_id"],
            "locator": rec["locator"],
            "doi": rec.get("doi"),
            "title": rec.get("title"),
            "authors": [a if isinstance(a, str) else
                        (a.get("name") or " ".join(
                            x for x in [a.get("given"), a.get("family")] if x))
                        for a in (rec.get("authors") or [])][:8],
            "author_surnames_folded": author_surnames(rec.get("authors")),
            "year": rec.get("year"),
            "venue": rec.get("venue"),
            "publisher": rec.get("publisher"),
            "volume": rec.get("volume"),
            "issue": rec.get("issue"),
            "first_page": rec.get("first_page"),
            "issn": rec.get("issn"),
            "metadata_languages": rec.get("metadata_languages"),
            "text_availability": availability,
            "body_language": body_lang,
            "version_type": vtype,
            "version_confidence": vconf,
            "evidence": det,
            "translation_of": (rec.get("relation") or {}).get("translation_of"),
            "duplicate_of": rec.get("_dup_of"),
            "fingerprint": rec.get("_fp"),
            "text_hash": rec.get("_th"),
            "conflicts": conflicts,
            "notes": rnotes,
        }
        by_lang[body_lang["code"]] = by_lang.get(body_lang["code"], 0) + 1
        by_vtype[vtype] = by_vtype.get(vtype, 0) + 1
        out_records.append(entry)
        # drop heavy fields from the report
        rec.pop("fulltext", None)
        rec.pop("abstract", None)

    report = {
        "skill": "xlang-version-reconciler",
        "stage": "langid_version",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "parameters": {"roots": roots, "max_chars": args.max_chars,
                       "min_fulltext": MIN_FULLTEXT_CHARS},
        "summary": {"files_scanned": len(sources),
                    "records": len(out_records),
                    "by_body_language": by_lang,
                    "by_version_type": by_vtype,
                    "exact_duplicate_pairs": len(dup_groups)},
        "records": out_records,
        "duplicates": dup_groups,
        "sources": [{"file": f} for f in sources],
        "parse_notes": notes,
    }

    out_path = Path(args.out)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    except OSError as exc:
        log.append("WARNING: cannot write %s: %s" % (out_path, exc))
        out_path = work_dir / "langid_report.json"
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                            encoding="utf-8")

    log.append("classified %d records: languages=%s version_types=%s"
               % (len(out_records), by_lang, by_vtype))
    log.append("finished in %.1fs" % (time.time() - started))
    try:
        (work_dir / "langid_run_log.json").write_text(
            json.dumps({"log": log, "parse_notes": notes},
                       ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    print(json.dumps({"records": len(out_records),
                      "by_body_language": by_lang,
                      "by_version_type": by_vtype,
                      "report": str(out_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
