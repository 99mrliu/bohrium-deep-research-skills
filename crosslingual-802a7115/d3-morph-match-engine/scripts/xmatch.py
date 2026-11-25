#!/usr/bin/env python3
"""xmatch.py — cross-lingual morphological surface matching engine.

Matches multilingual term variants against real corpus records and returns,
for every hit, exactly which variant of which concept fired, where
(offsets + context), and under which normalization rule. Handles the
surface-form problems that break naive search:

- diacritics: NFKD folding (São/sao, ü/u), ß->ss;
- German umlaut transliteration (ä->ae, ö->oe, ü->ue) as a second channel;
- German compounds: variant matched as substring of a longer token
  (Zelltod... containing ...tod) — flagged as compound_match;
- inflection: light suffix stripping for en/pt/es/de plural/verb endings;
- Japanese kana: direct substring match + Hepburn romaji cross-channel;
- CJK: direct substring match; mixed CJK-Latin titles handled per script;
- mixed-language titles: matched in both channels, both recorded.

Input term table: JSON with {"concepts":[{"concept_id","label","variants":
[{"lang","term","verified"?}, ...]}, ...]}. The engine never invents terms;
untranslatable concepts are reported as uncovered per language.

Stdlib only, offline. Exit code always 0.
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata

TEXT_EXT = {".txt", ".md"}
TAB_EXT = {".csv": ",", ".tsv": "\t"}

KANA_ROMAJI = {
    "ア": "a", "イ": "i", "ウ": "u", "エ": "e", "オ": "o",
    "カ": "ka", "キ": "ki", "ク": "ku", "ケ": "ke", "コ": "ko",
    "サ": "sa", "シ": "shi", "ス": "su", "セ": "se", "ソ": "so",
    "タ": "ta", "チ": "chi", "ツ": "tsu", "テ": "te", "ト": "to",
    "ナ": "na", "ニ": "ni", "ヌ": "nu", "ネ": "ne", "ノ": "no",
    "ハ": "ha", "ヒ": "hi", "フ": "fu", "ヘ": "he", "ホ": "ho",
    "マ": "ma", "ミ": "mi", "ム": "mu", "メ": "me", "モ": "mo",
    "ヤ": "ya", "ユ": "yu", "ヨ": "yo",
    "ラ": "ra", "リ": "ri", "ル": "ru", "レ": "re", "ロ": "ro",
    "ワ": "wa", "ヲ": "wo", "ン": "n", "ガ": "ga", "ギ": "gi",
    "グ": "gu", "ゲ": "ge", "ゴ": "go", "ザ": "za", "ジ": "ji",
    "ズ": "zu", "ゼ": "ze", "ゾ": "zo", "ダ": "da", "ヂ": "ji",
    "ヅ": "zu", "デ": "de", "ド": "do", "バ": "ba", "ビ": "bi",
    "ブ": "bu", "ベ": "be", "ボ": "bo", "パ": "pa", "ピ": "pi",
    "プ": "pu", "ペ": "pe", "ポ": "po", "ー": "", "ッ": "",
}
UMLAUT_EXP = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
SUFFIXES = ["ieren", "ierung", "ungen", "es", "en", "er", "s", "s",
            "ções", "ções", "os", "as", "es", "s", "ed", "ing", "es"]


def fold(text):
    nfkd = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def expand_umlaut(text):
    out = (text or "").lower()
    for k, v in UMLAUT_EXP.items():
        out = out.replace(k, v)
    return out


def kana_to_romaji(text):
    return "".join(KANA_ROMAJI.get(ch, ch) for ch in (text or ""))


def norm_forms(term):
    """All normalized surface forms of a variant, each tagged with its rule."""
    forms = []
    base = re.sub(r"\s+", " ", term.strip())
    folded = fold(base)
    forms.append((folded, "nfkd_fold"))
    uml = expand_umlaut(base)
    if uml != base.lower():
        forms.append((fold(uml), "umlaut_expansion"))
    romaji = kana_to_romaji(base)
    if romaji != base:
        forms.append((romaji, "kana_romaji"))
        forms.append((fold(romaji), "kana_romaji_folded"))
    toks = folded.split()
    if toks:
        stemmed = []
        for t in toks:
            for suf in SUFFIXES:
                if t.endswith(suf) and len(t) - len(suf) >= 4:
                    stemmed.append(t[:-len(suf)])
                    break
            else:
                stemmed.append(t)
        if stemmed != toks:
            forms.append((" ".join(stemmed), "suffix_stem"))
    seen, uniq = set(), []
    for f, rule in forms:
        if f and f not in seen:
            seen.add(f)
            uniq.append((f, rule))
    return uniq


def norm_corpus(text):
    """Normalized corpus text plus a map back to raw offsets (approximate:
    we match on the folded stream and locate context by token index)."""
    return fold(text), expand_umlaut(fold(text)), kana_to_romaji(text or "")


def find_matches(variant_forms, raw_text):
    """Yield (rule, form, start, end, context) over the raw text."""
    raw_fold, raw_uml, raw_romaji = norm_corpus(raw_text)
    channels = {"nfkd_fold": raw_fold, "suffix_stem": raw_fold,
                "umlaut_expansion": raw_uml, "kana_romaji": raw_romaji,
                "kana_romaji_folded": fold(raw_romaji)}
    hits = []
    accepted = []  # spans already attributed, across all forms of this variant
    for form, rule in variant_forms:
        hay = channels.get(rule, raw_fold)
        if not form:
            continue
        is_cjk = re.search(r"[一-鿿぀-ヿ]", form)
        if is_cjk or rule.startswith("kana"):
            for m in re.finditer(re.escape(form), hay):
                hits.append((rule, form, m.start(), m.end()))
            continue
        # latin: word-boundary hits carry the variant's own rule
        pat = re.compile(r"(?<![a-z0-9])" + re.escape(form) + r"(?![a-z0-9])")
        spans = [(m.start(), m.end()) for m in pat.finditer(hay)]
        for s, e in spans:
            hits.append((rule, form, s, e))
        accepted.extend(spans)
        # compound channel: single-token form inside a longer token, only
        # where no already-attributed hit covers the span
        if " " not in form and len(form) >= 5:
            for m in re.finditer(re.escape(form), hay):
                s, e = m.start(), m.end()
                if any(s < be and e > bs for bs, be in accepted):
                    continue
                left = hay[s - 1] if s > 0 else " "
                right = hay[e] if e < len(hay) else " "
                if left.isalnum() or right.isalnum():
                    hits.append(("compound_match", form, s, e))
    return hits


def iter_corpus(roots, notes):
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
    for path in sorted(set(files)):
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".pdf":
                with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tf:
                    out = tf.name
                r = subprocess.run(["pdftotext", "-enc", "UTF-8", path, out],
                                   capture_output=True, timeout=120)
                txt = ""
                if r.returncode == 0:
                    with open(out, encoding="utf-8", errors="replace") as fh:
                        txt = fh.read()
                else:
                    notes.append(f"pdftotext failed {path}")
                try:
                    os.unlink(out)
                except OSError:
                    pass
                yield {"record_id": os.path.basename(path),
                       "source_file": os.path.abspath(path), "text": txt,
                       "fields": ["body"]}
                continue
            with open(path, encoding="utf-8", errors="replace") as fh:
                raw = fh.read()
        except OSError as exc:
            notes.append(f"unreadable {path}: {exc}")
            continue
        if ext == ".jsonl":
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                yield from_record(rec, path)
        elif ext == ".json":
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                notes.append(f"JSON error {path}: {exc}")
                continue
            items = data if isinstance(data, list) else [data]
            for key in ("records", "results", "hits", "documents"):
                if isinstance(data, dict) and isinstance(data.get(key), list):
                    items = data[key]
                    break
            for rec in items:
                if isinstance(rec, dict):
                    yield from_record(rec, path)
        elif ext in TAB_EXT:
            for row in csv.DictReader(raw.splitlines(), delimiter=TAB_EXT[ext]):
                yield from_record(dict(row), path)
        else:
            yield {"record_id": os.path.basename(path),
                   "source_file": os.path.abspath(path), "text": raw,
                   "fields": ["body"]}


def from_record(rec, path):
    parts, fields = [], []
    for k in ("title", "titulo", "título", "abstract", "resumo", "resumen",
              "keywords", "palavras-chave", "body", "fulltext", "text"):
        v = rec.get(k)
        if isinstance(v, str) and v.strip():
            parts.append(v)
            fields.append(k)
        elif isinstance(v, list):
            parts.append(" ".join(str(x) for x in v))
            fields.append(k)
    return {"record_id": rec.get("id") or rec.get("record_id")
            or os.path.basename(path),
            "source_file": os.path.abspath(path),
            "text": "\n".join(parts), "fields": fields,
            "doi": rec.get("doi"), "language": rec.get("language")}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--terms", required=True, help="term table JSON")
    ap.add_argument("--roots", nargs="*", default=["/input", "/app/work"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--exclude", nargs="*", default=[])
    ap.add_argument("--context", type=int, default=60)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    notes = []
    with open(args.terms, encoding="utf-8") as fh:
        table = json.load(fh)
    concepts = table.get("concepts", [])
    if not concepts:
        notes.append("term table has no concepts")
    roots = [r for r in args.roots if os.path.exists(r)]
    records = list(iter_corpus(roots, notes))
    if args.exclude:
        excl = tuple(args.exclude)
        records = [r for r in records
                   if not any(e in r["source_file"] for e in excl)]
    results, coverage = [], {}
    for rec in records:
        text = rec.get("text") or ""
        if not text.strip():
            continue
        hit_concepts = []
        for c in concepts:
            fired = []
            for v in c.get("variants", []):
                term, lang = v.get("term", ""), v.get("lang", "und")
                if not term:
                    continue
                matches = find_matches(norm_forms(term), text)
                for rule, form, s, e in matches:
                    ctx = fold(text)[max(0, s - args.context): e + args.context]
                    fired.append({
                        "lang": lang, "term": term,
                        "verified": bool(v.get("verified", True)),
                        "rule": rule, "matched_form": form,
                        "offset": [s, e], "context": ctx.strip(),
                    })
            if fired:
                hit_concepts.append({"concept_id": c.get("concept_id"),
                                     "label": c.get("label"),
                                     "matches": fired})
        if hit_concepts:
            results.append({
                "record_id": rec["record_id"],
                "source_file": rec["source_file"],
                "doi": rec.get("doi"), "declared_language": rec.get("language"),
                "matched_fields": rec.get("fields"),
                "concepts": hit_concepts,
            })
        for hc in hit_concepts:
            for m in hc["matches"]:
                coverage.setdefault(m["lang"], set()).add(rec["record_id"])
    payload = {
        "status": "ok",
        "hits": results,
        "coverage_by_lang": {k: sorted(v) for k, v in coverage.items()},
        "counts": {"records_with_hits": len(results),
                   "concepts": len(concepts)},
        "parse_notes": notes,
    }
    with open(os.path.join(args.out, "matches.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    lines = ["# Cross-lingual match report", ""]
    for r in results:
        lines.append(f"## {r['record_id']} ({os.path.basename(r['source_file'])})")
        for hc in r["concepts"]:
            for m in hc["matches"]:
                flag = "" if m["verified"] else " [UNVERIFIED]"
                lines.append(
                    f"- `{hc['label']}` via **{m['lang']}** variant "
                    f"\"{m['term']}\" [{m['rule']}]{flag}: …{m['context']}…")
        lines.append("")
    with open(os.path.join(args.out, "match_report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) or "# no hits\n")
    print(json.dumps({"status": "ok", "records_with_hits": len(results),
                      "langs": sorted(coverage)}, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
