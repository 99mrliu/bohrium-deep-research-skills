#!/usr/bin/env python3
"""corpus_audit.py — upstream data-authenticity audit for cross-lingual
literature corpora.

Discovers corpus material under given roots (JSON/JSONL/CSV/TSV/TXT/MD and
PDF via `pdftotext` when available), extracts real body text, fingerprints
every document, cross-checks declared metadata against the actual body
(language label vs detected language, missing DOI, exact duplicates), and
writes a provenance ledger plus a human-readable audit report.

The script NEVER invents metadata: every finding cites the file it came
from; fields absent from the record stay absent and are reported as gaps.

Stdlib only. Exit code is always 0; failures are recorded in the ledger.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata

TEXT_EXT = {".txt", ".md"}
TAB_EXT = {".csv": ",", ".tsv": "\t"}
RECORD_KEYS_TITLE = ("title", "titulo", "título", "headline", "name")
RECORD_KEYS_ABS = ("abstract", "resumo", "resumen", "summary", "description")
RECORD_KEYS_BODY = ("body", "fulltext", "full_text", "text", "content")
RECORD_KEYS_DOI = ("doi", "DOI")
RECORD_KEYS_LANG = ("language", "lang", "body_language", "idioma")
RECORD_KEYS_ID = ("id", "record_id", "uid", "pmid", "source_id")

STOPWORDS = {
    "en": {"the", "of", "and", "in", "is", "are", "was", "were", "with",
           "this", "that", "for", "from", "study", "results", "methods",
           "between", "which", "these", "were", "have", "has"},
    "pt": {"de", "da", "do", "das", "dos", "em", "uma", "um", "para",
           "com", "os", "as", "não", "são", "esta", "este", "estudo",
           "resultados", "métodos", "entre", "foi", "ser", "pelo", "pela"},
    "es": {"el", "la", "los", "las", "una", "uno", "para", "con", "estudio",
           "resultados", "métodos", "entre", "fue", "ser", "del", "por",
           "esta", "este", "son", "como"},
    "de": {"der", "die", "das", "und", "ist", "mit", "für", "eine", "einer",
           "eines", "den", "dem", "des", "nicht", "sind", "war", "studie",
           "zwischen", "wurde", "werden", "auf"},
    "fr": {"le", "la", "les", "des", "une", "un", "et", "est", "avec",
           "pour", "dans", "sur", "sont", "étude", "résultats", "entre",
           "par", "qui", "au", "aux"},
}
DIACRITIC_HINT = {
    "pt": "ãõç",
    "es": "ñ¿¡",
    "de": "äöüß",
    "fr": "àâçèéêëîïôùû",
}


def fold(text):
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def detect_language(text):
    """Stopword/diacritic/script heuristic. Returns (lang, confidence, evidence)."""
    if not text or len(text.strip()) < 20:
        return "und", 0.0, {"reason": "text too short (<20 chars)"}
    sample = text[:20000]
    han = len(re.findall(r"[一-鿿]", sample))
    kana = len(re.findall(r"[぀-ヿ]", sample))
    if kana >= 5:
        return "ja", min(0.99, 0.5 + kana / 200.0), {"kana_chars": kana}
    if han >= 10:
        return "zh", min(0.99, 0.5 + han / 400.0), {"han_chars": han}
    tokens = re.findall(r"[a-zA-ZÀ-ɏ]+", fold(sample))
    if not tokens:
        return "und", 0.0, {"reason": "no latin tokens"}
    scores = {lang: 0 for lang in STOPWORDS}
    tok_set = tokens
    for lang, words in STOPWORDS.items():
        scores[lang] = sum(1 for t in tok_set if t in words)
    low = sample.lower()
    for lang, chars in DIACRITIC_HINT.items():
        bonus = sum(low.count(c) for c in chars)
        scores[lang] = scores.get(lang, 0) + min(bonus, 15)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    if top_score == 0:
        return "und", 0.0, {"reason": "no stopword evidence", "scores": scores}
    conf = min(0.99, 0.4 + 0.6 * (top_score - second_score) / (top_score + 1))
    ev = {"scores": scores, "top": top, "margin": top_score - second_score}
    return top, round(conf, 3), ev


def norm_text(t):
    return re.sub(r"\s+", " ", fold(t or "")).strip()


def fingerprint(text):
    return hashlib.sha256(norm_text(text).encode("utf-8")).hexdigest()


def shingle_fp(text, k=5):
    toks = norm_text(text).split()
    if len(toks) < k:
        return set(toks)
    return {" ".join(toks[i:i + k]) for i in range(len(toks) - k + 1)}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def extract_pdf(path, notes):
    try:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tf:
            out = tf.name
        r = subprocess.run(["pdftotext", "-enc", "UTF-8", path, out],
                           capture_output=True, timeout=120)
        if r.returncode != 0:
            notes.append(f"pdftotext failed for {path}: {r.stderr.decode('utf-8', 'replace')[:200]}")
            return ""
        with open(out, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except FileNotFoundError:
        notes.append("pdftotext not found on PATH; PDF bodies unextracted")
        return ""
    except Exception as exc:  # noqa: BLE001
        notes.append(f"PDF extraction error for {path}: {exc}")
        return ""
    finally:
        try:
            os.unlink(out)
        except Exception:
            pass


def first_key(rec, keys):
    for k in keys:
        if k in rec and isinstance(rec[k], str) and rec[k].strip():
            return rec[k]
    return ""


def iter_records(path, notes):
    """Yield (record_dict_or_None, raw_text) from a file."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".pdf":
            yield None, extract_pdf(path, notes)
            return
        with open(path, encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
    except OSError as exc:
        notes.append(f"unreadable file {path}: {exc}")
        return
    if ext == ".json":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            notes.append(f"JSON parse error {path}: {exc}")
            return
        items = data if isinstance(data, list) else [data]
        for key in ("records", "results", "hits", "documents", "papers"):
            if isinstance(data, dict) and isinstance(data.get(key), list):
                items = data[key]
                break
        for it in items:
            if isinstance(it, dict):
                yield it, json.dumps(it, ensure_ascii=False)
        return
    if ext == ".jsonl":
        for ln, line in enumerate(raw.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                it = json.loads(line)
                if isinstance(it, dict):
                    yield it, line
            except json.JSONDecodeError:
                notes.append(f"JSONL line {ln} unparsable in {path}")
        return
    if ext in TAB_EXT:
        try:
            for row in csv.DictReader(raw.splitlines(), delimiter=TAB_EXT[ext]):
                yield dict(row), json.dumps(row, ensure_ascii=False)
        except csv.Error as exc:
            notes.append(f"CSV/TSV parse error {path}: {exc}")
        return
    yield None, raw  # plain text / markdown: whole file is one document


def audit(roots, extra_files):
    notes, docs = [], []
    seen_files = set()
    files = []
    for root in roots:
        if os.path.isfile(root):
            files.append(root)
        elif os.path.isdir(root):
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if not d.startswith(".")
                               and d not in ("node_modules", "__pycache__")]
                for fn in sorted(filenames):
                    if os.path.splitext(fn)[1].lower() in (
                            TEXT_EXT | set(TAB_EXT) | {".json", ".jsonl", ".pdf"}):
                        files.append(os.path.join(dirpath, fn))
        else:
            notes.append(f"root not found: {root}")
    files.extend(extra_files or [])
    for path in sorted(set(files)):
        if path in seen_files:
            continue
        seen_files.add(path)
        for rec, raw in iter_records(path, notes):
            if rec is None and not (raw or "").strip():
                continue
            title = first_key(rec or {}, RECORD_KEYS_TITLE)
            abstract = first_key(rec or {}, RECORD_KEYS_ABS)
            body = first_key(rec or {}, RECORD_KEYS_BODY)
            text = body or (raw if rec is None else "")
            probe = " ".join(x for x in (title, abstract, text) if x)
            if not probe.strip():
                notes.append(f"empty record skipped in {path}")
                continue
            lang, conf, ev = detect_language(probe)
            declared = first_key(rec or {}, RECORD_KEYS_LANG)
            doi = first_key(rec or {}, RECORD_KEYS_DOI)
            rid = first_key(rec or {}, RECORD_KEYS_ID) or os.path.basename(path)
            docs.append({
                "record_id": rid,
                "source_file": os.path.abspath(path),
                "title": title,
                "declared_language": declared or None,
                "detected_language": lang,
                "lang_confidence": conf,
                "lang_evidence": ev,
                "doi": doi or None,
                "has_abstract": bool(abstract.strip()),
                "has_body": bool((text or "").strip()),
                "body_chars": len(text or ""),
                "declared_fields": sorted((rec or {}).keys()),
                "content_sha256": fingerprint(probe),
                "_shingles": shingle_fp(probe),
            })
    findings, duplicates = [], []
    for d in docs:
        decl = (d["declared_language"] or "").lower()[:2]
        det = d["detected_language"]
        if decl and det != "und" and decl != det:
            findings.append({
                "kind": "language_label_mismatch",
                "record_id": d["record_id"], "source_file": d["source_file"],
                "declared": decl, "detected": det,
                "confidence": d["lang_confidence"],
                "action": "trust body text over label; record both",
            })
        if not d["doi"]:
            findings.append({
                "kind": "missing_doi",
                "record_id": d["record_id"], "source_file": d["source_file"],
                "action": "do not fabricate; mark DOI as unavailable",
            })
        if det == "und":
            findings.append({
                "kind": "language_undetermined",
                "record_id": d["record_id"], "source_file": d["source_file"],
                "action": "flag for manual inspection; exclude from per-language counts",
            })
    for i in range(len(docs)):
        for j in range(i + 1, len(docs)):
            a, b = docs[i], docs[j]
            sim = 1.0 if a["content_sha256"] == b["content_sha256"] else \
                jaccard(a["_shingles"], b["_shingles"])
            if sim >= 0.9:
                duplicates.append({
                    "kind": "near_duplicate",
                    "record_a": a["record_id"], "record_b": b["record_id"],
                    "file_a": a["source_file"], "file_b": b["source_file"],
                    "similarity": round(sim, 4),
                    "action": "count once; keep both attributions",
                })
    for d in docs:
        d.pop("_shingles", None)
    ledger = {
        "status": "ok",
        "documents": docs,
        "findings": findings,
        "duplicate_pairs": duplicates,
        "counts": {
            "documents": len(docs),
            "findings": len(findings),
            "duplicate_pairs": len(duplicates),
        },
        "parse_notes": notes,
    }
    if findings or duplicates:
        ledger["status"] = "ok_with_findings"
    return ledger


def render_report(ledger):
    lines = ["# Corpus authenticity audit (上游数据真实性核验)", ""]
    c = ledger["counts"]
    lines.append(f"- documents: {c['documents']}; findings: {c['findings']}; "
                 f"duplicate pairs: {c['duplicate_pairs']}")
    lines.append("")
    lines.append("| record | file | declared lang | detected lang | conf | DOI | body chars |")
    lines.append("|-|-|-|-|-|-|-|")
    for d in ledger["documents"]:
        lines.append("| {record_id} | {sf} | {dl} | {det} | {cf} | {doi} | {bc} |".format(
            record_id=d["record_id"], sf=os.path.basename(d["source_file"]),
            dl=d["declared_language"] or "—", det=d["detected_language"],
            cf=d["lang_confidence"], doi=d["doi"] or "—", bc=d["body_chars"]))
    if ledger["findings"]:
        lines += ["", "## Findings", ""]
        for f in ledger["findings"]:
            lines.append("- **{kind}** `{record_id}`: {extra} → {action}".format(
                kind=f["kind"], record_id=f["record_id"], action=f["action"],
                extra=" ".join(f"{k}={v}" for k, v in f.items()
                               if k not in ("kind", "record_id", "source_file", "action"))))
    if ledger["duplicate_pairs"]:
        lines += ["", "## Duplicate / near-duplicate pairs", ""]
        for p in ledger["duplicate_pairs"]:
            lines.append(f"- `{p['record_a']}` ≡ `{p['record_b']}` "
                         f"(similarity {p['similarity']}) → {p['action']}")
    if ledger["parse_notes"]:
        lines += ["", "## Parse notes", ""]
        lines += [f"- {n}" for n in ledger["parse_notes"]]
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--roots", nargs="*", default=["/input", "/app/work", "."],
                    help="corpus roots (dirs or files)")
    ap.add_argument("--files", nargs="*", default=[], help="extra explicit files")
    ap.add_argument("--out", required=True, help="output directory for ledger+report")
    ap.add_argument("--exclude", nargs="*", default=[],
                    help="path substrings to skip (e.g. examples data of this skill)")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    roots = [r for r in args.roots if os.path.exists(r)]
    ledger = audit(roots, args.files)
    if args.exclude:
        excl = tuple(args.exclude)
        ledger["documents"] = [d for d in ledger["documents"]
                               if not any(e in d["source_file"] for e in excl)]
    with open(os.path.join(args.out, "provenance_ledger.json"), "w",
              encoding="utf-8") as fh:
        json.dump(ledger, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "audit_report.md"), "w", encoding="utf-8") as fh:
        fh.write(render_report(ledger))
    print(json.dumps({"status": ledger["status"], "counts": ledger["counts"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
