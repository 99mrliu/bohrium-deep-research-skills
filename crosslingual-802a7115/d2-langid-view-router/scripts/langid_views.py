#!/usr/bin/env python3
"""langid_views.py — language identification and view-type routing for
cross-lingual known-item retrieval.

Two jobs over a set of candidate records (JSON/JSONL/CSV/TSV/TXT/MD, PDF via
pdftotext):

1. LANGUAGE ID: identify the actual body language of every record from real
   text (stopword profiles, diacritic signatures, CJK/kana counts), with
   confidence and inspectable evidence. Declared labels are kept for
   comparison only, never trusted blindly.
2. VIEW ROUTING: cluster records into works (shared DOI or near-identical
   normalized title) and classify each view as original / translation /
   bilingual / abstract_only / duplicate, then emit a routing table saying
   which query languages apply to which view and how each view may be
   counted (dedupe rules).

Stdlib only, fully offline. Exit code always 0; problems go into the report.
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

STOPWORDS = {
    "en": {"the", "of", "and", "in", "is", "are", "was", "were", "with",
           "this", "that", "for", "from", "study", "results", "methods"},
    "pt": {"de", "da", "do", "das", "dos", "em", "uma", "um", "para",
           "com", "os", "as", "não", "são", "esta", "estudo", "resultados"},
    "es": {"el", "la", "los", "las", "una", "para", "con", "estudio",
           "resultados", "del", "por", "esta", "son", "como", "entre"},
    "de": {"der", "die", "das", "und", "ist", "mit", "für", "eine", "den",
           "dem", "nicht", "sind", "studie", "wurde", "werden", "auf"},
    "fr": {"le", "la", "les", "des", "une", "et", "est", "avec", "pour",
           "dans", "sur", "sont", "étude", "résultats", "par", "qui"},
}
DIACRITIC_HINT = {"pt": "ãõç", "es": "ñ¿¡", "de": "äöüß",
                  "fr": "àâèéêëîïôùû"}
TRANSLATION_MARKERS = [
    r"translated from", r"translation of", r"english version",
    r"tradu[cç][ãa]o de", r"traduzido do", r"vers[ãa]o em portugu[êe]s",
    r"versi[oó]n en espa[ñn]ol", r"traducci[oó]n de", r"[üu]bersetzung",
    r"deutsche [üu]bersetzung", r"traduit de", r"version fran[cç]aise",
]
ABSTRACT_HINTS = [r"^abstract\b", r"^resumo\b", r"^resumen\b",
                  r"^zusammenfassung\b", r"summary only", r"abstract only"]


def fold(text):
    nfkd = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def detect_language(text):
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
    for lang, words in STOPWORDS.items():
        scores[lang] = sum(1 for t in tokens if t in words)
    low = sample.lower()
    for lang, chars in DIACRITIC_HINT.items():
        scores[lang] += min(sum(low.count(c) for c in chars), 15)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top, top_score = ranked[0]
    second = ranked[1][1]
    if top_score == 0:
        return "und", 0.0, {"reason": "no stopword evidence", "scores": scores}
    conf = min(0.99, 0.4 + 0.6 * (top_score - second) / (top_score + 1))
    return top, round(conf, 3), {"scores": scores, "margin": top_score - second}


def norm_text(t):
    return re.sub(r"\s+", " ", fold(t)).strip()


def norm_title(t):
    return " ".join(re.findall(r"[a-z0-9]+", fold(t)))


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
            notes.append(f"pdftotext failed for {path}: {r.stderr.decode('utf-8','replace')[:200]}")
            return ""
        with open(out, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except FileNotFoundError:
        notes.append("pdftotext not found; PDF bodies unextracted")
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
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".pdf":
            yield None, extract_pdf(path, notes)
            return
        with open(path, encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
    except OSError as exc:
        notes.append(f"unreadable {path}: {exc}")
        return
    if ext == ".json":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            notes.append(f"JSON error {path}: {exc}")
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
            notes.append(f"CSV/TSV error {path}: {exc}")
        return
    yield None, raw


def collect(roots, notes):
    files = []
    for root in roots:
        if os.path.isfile(root):
            files.append(root)
        elif os.path.isdir(root):
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                for fn in sorted(filenames):
                    if os.path.splitext(fn)[1].lower() in (
                            TEXT_EXT | set(TAB_EXT) | {".json", ".jsonl", ".pdf"}):
                        files.append(os.path.join(dirpath, fn))
        else:
            notes.append(f"root not found: {root}")
    records = []
    for path in sorted(set(files)):
        for rec, raw in iter_records(path, notes):
            rec = rec or {}
            title = first_key(rec, ("title", "titulo", "título", "headline"))
            abstract = first_key(rec, ("abstract", "resumo", "resumen", "summary"))
            body = first_key(rec, ("body", "fulltext", "full_text", "text", "content"))
            text = body or (raw if not rec else "")
            probe = " ".join(x for x in (title, abstract, text) if x)
            if not probe.strip():
                continue
            lang, conf, ev = detect_language(probe)
            rid = first_key(rec, ("id", "record_id", "uid", "pmid")) or os.path.basename(path)
            records.append({
                "record_id": rid,
                "source_file": os.path.abspath(path),
                "title": title,
                "declared_language": first_key(rec, ("language", "lang", "body_language")) or None,
                "detected_language": lang, "lang_confidence": conf, "lang_evidence": ev,
                "doi": first_key(rec, ("doi", "DOI")) or None,
                "has_abstract": bool(abstract.strip()),
                "body_chars": len(text or ""),
                "declared_type": first_key(rec, ("type", "view", "version_type")) or None,
                "_probe": probe,
            })
    return records


def classify_views(records):
    """Cluster into works, then classify each view with evidence."""
    works = []
    for rec in records:
        placed = False
        for w in works:
            same_doi = rec["doi"] and w["doi"] and \
                rec["doi"].lower() == w["doi"].lower()
            title_sim = jaccard(set(norm_title(rec["title"]).split()),
                                set(norm_title(w["title"]).split())) \
                if rec["title"] and w["title"] else 0.0
            if same_doi or title_sim >= 0.6:
                w["members"].append(rec)
                rec["doi"] = rec["doi"] or w["doi"]
                w["doi"] = w["doi"] or rec["doi"]
                placed = True
                break
        if not placed:
            works.append({"work_id": f"W{len(works)+1:03d}",
                          "doi": rec["doi"], "title": rec["title"],
                          "members": [rec]})
    shingles = {r["record_id"]: shingle_fp(r["_probe"]) for r in records}
    for w in works:
        for idx, m in enumerate(w["members"]):
            probe_low = fold(m["_probe"])
            marker_hit = [p for p in TRANSLATION_MARKERS
                          if re.search(p, probe_low)]
            abstract_hint = any(re.search(p, probe_low.strip()[:200])
                                for p in ABSTRACT_HINTS)
            dup_of = None
            for other in w["members"][:idx]:  # only earlier members: the first
                if other["detected_language"] == m["detected_language"] and \
                        jaccard(shingles[m["record_id"]],
                                shingles[other["record_id"]]) >= 0.9:
                    dup_of = other["record_id"]
                    break
            has_full = m["body_chars"] >= 1500
            langs_in_work = {x["detected_language"] for x in w["members"]}
            if dup_of:
                view, why = "duplicate", f"near-identical text to {dup_of} (Jaccard≥0.9)"
            elif marker_hit:
                view, why = "translation", f"explicit marker: {marker_hit[0]}"
            elif not has_full and (m["has_abstract"] or abstract_hint):
                view, why = "abstract_only", \
                    f"no full body ({m['body_chars']} chars) but abstract present"
            elif len(langs_in_work) > 1 and m["detected_language"] != w["members"][0]["detected_language"]:
                view, why = "translation", \
                    "same work cluster, different body language, no explicit marker"
            elif len(langs_in_work) > 1 and m["detected_language"] == "und":
                view, why = "bilingual_or_undetermined", "language undetermined inside multi-language work"
            else:
                view, why = "original", "fullest body of its language in the work cluster"
            m["view_type"] = view
            m["view_evidence"] = why
            if m["declared_type"] and m["declared_type"] != view:
                m["view_note"] = (f"declared '{m['declared_type']}' kept for reference; "
                                  f"classification follows body evidence")
    return works


def routing_table(works):
    rows = []
    for w in works:
        langs = sorted({m["detected_language"] for m in w["members"]
                        if m["detected_language"] != "und"})
        count_once = len(w["members"]) > 1
        for m in w["members"]:
            rows.append({
                "work_id": w["work_id"],
                "record_id": m["record_id"],
                "detected_language": m["detected_language"],
                "view_type": m["view_type"],
                "query_languages": langs,
                "countable": m["view_type"] not in ("duplicate",),
                "count_note": ("count once per work across language views"
                               if count_once else "single view"),
                "evidence": m["view_evidence"],
            })
    return rows


def render_report(works, routing, notes):
    lines = ["# Language ID & view routing report", ""]
    for w in works:
        lines.append(f"## {w['work_id']} — {w['title'] or '(untitled)'} "
                     f"(DOI: {w['doi'] or '—'})")
        lines.append("| record | declared | detected | conf | view | evidence |")
        lines.append("|-|-|-|-|-|-|")
        for m in w["members"]:
            lines.append("| {rid} | {dl} | {det} | {cf} | {vt} | {ev} |".format(
                rid=m["record_id"], dl=m["declared_language"] or "—",
                det=m["detected_language"], cf=m["lang_confidence"],
                vt=m["view_type"], ev=m["view_evidence"]))
        lines.append("")
    lines.append("## Routing table")
    lines.append("| work | record | lang | view | query languages | countable |")
    lines.append("|-|-|-|-|-|-|")
    for r in routing:
        lines.append("| {w} | {r} | {l} | {v} | {q} | {c} |".format(
            w=r["work_id"], r=r["record_id"], l=r["detected_language"],
            v=r["view_type"], q=", ".join(r["query_languages"]) or "—",
            c="yes" if r["countable"] else "no (dedupe)"))
    if notes:
        lines += ["", "## Parse notes"] + [f"- {n}" for n in notes]
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--roots", nargs="*", default=["/input", "/app/work"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--exclude", nargs="*", default=[])
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    notes = []
    roots = [r for r in args.roots if os.path.exists(r)]
    records = collect(roots, notes)
    if args.exclude:
        excl = tuple(args.exclude)
        records = [r for r in records
                   if not any(e in r["source_file"] for e in excl)]
    works = classify_views(records)
    routing = routing_table(works)
    for r in records:
        r.pop("_probe", None)
    payload = {
        "status": "ok",
        "works": [{k: v for k, v in w.items()} for w in works],
        "routing": routing,
        "parse_notes": notes,
        "counts": {"records": len(records), "works": len(works)},
    }
    with open(os.path.join(args.out, "views.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "routing_report.md"), "w", encoding="utf-8") as fh:
        fh.write(render_report(works, routing, notes))
    print(json.dumps({"status": "ok", "records": len(records),
                      "works": len(works)}, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
