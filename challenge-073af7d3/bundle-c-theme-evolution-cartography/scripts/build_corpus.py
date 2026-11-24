#!/usr/bin/env python3
"""build_corpus.py — normalize heterogeneous literature exports into canon.jsonl.

Usage:
    python3 build_corpus.py --work DIR --inputs FILE_OR_DIR [FILE_OR_DIR ...]

Supported input formats (by extension):
    .json  (list of objects, or dict wrapping a record list, or a single object)
    .jsonl (one object per line)
    .csv   (header row; case-insensitive column names)
    .bib   (minimal BibTeX: @type{key, field = {value}, ...})
    .ris   (RIS tagged format: TY/TI/AB/PY/Y1/KW/ID/ER)
    .txt/.md (blocks separated by blank lines with "Title:/Year:/Abstract:/
              Keywords:/Citations:/Id:" prefixes; if no prefixed block exists,
              the whole file becomes one record: first non-empty line = title)

Output (DIR/canon.jsonl), one record per line, sorted by (year, id):
    {"id", "title", "year", "abstract", "keywords", "citations", "source_file"}
    - year is an int or null when no 4-digit year 19xx/20xx can be found
    - citations defaults to 0; keywords defaults to []
    - records are never dropped for missing keys; nothing is fabricated

Deterministic: stdlib only, no network, no wall-clock, stable ordering.
"""
import argparse
import csv
import json
import os
import re
import sys

YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
KNOWN_EXT = {".json", ".jsonl", ".csv", ".bib", ".ris", ".txt", ".md"}

TITLE_KEYS = ["title", "name", "headline"]
ABSTRACT_KEYS = ["abstract", "summary", "description"]
KEYWORD_KEYS = ["keywords", "keyword", "tags", "subjects", "mesh_terms"]
CITATION_KEYS = ["citations", "citation_count", "cited_by", "citedby",
                 "n_citations", "num_citations", "times_cited"]
YEAR_KEYS = ["year", "date", "published", "pubdate", "publication_year", "py"]
ID_KEYS = ["id", "doi", "key", "eprint", "uid", "pmid", "arxiv_id"]


def as_str(v):
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, list):
        return "; ".join(as_str(x) for x in v if as_str(x))
    return str(v).strip()


def norm_year(v):
    if v is None:
        return None
    m = YEAR_RE.search(str(v))
    return int(m.group(1)) if m else None


def norm_citations(v):
    if v is None:
        return 0
    m = re.search(r"-?\d+", str(v).replace(",", ""))
    if not m:
        return 0
    try:
        return max(0, int(m.group(0)))
    except ValueError:
        return 0


def norm_keywords(v):
    if v is None:
        return []
    if isinstance(v, list):
        return [as_str(x) for x in v if as_str(x)]
    parts = re.split(r"[;,|]", str(v))
    return [p.strip() for p in parts if p.strip()]


def first_key(d, keys):
    low = {str(k).lower(): v for k, v in d.items()}
    for k in keys:
        if k in low and low[k] not in (None, "", []):
            return low[k]
    return None


def canon_record(d, source_file, seq):
    rid = as_str(first_key(d, ID_KEYS))
    if not rid:
        rid = "rec-%s-%04d" % (re.sub(r"[^A-Za-z0-9]+", "-",
                               os.path.basename(source_file))[:24], seq)
    return {
        "id": rid,
        "title": as_str(first_key(d, TITLE_KEYS)),
        "year": norm_year(first_key(d, YEAR_KEYS)),
        "abstract": as_str(first_key(d, ABSTRACT_KEYS)),
        "keywords": norm_keywords(first_key(d, KEYWORD_KEYS)),
        "citations": norm_citations(first_key(d, CITATION_KEYS)),
        "source_file": os.path.basename(source_file),
    }


# ---------------------------------------------------------------- parsers

def parse_json(path, text):
    obj = json.loads(text)
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in ("records", "papers", "results", "data", "items", "entries"):
            if isinstance(obj.get(k), list):
                return obj[k]
        return [obj]
    return []


def parse_jsonl(path, text):
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            v = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(v, dict):
            out.append(v)
    return out


def parse_csv(path, text):
    out = []
    reader = csv.DictReader(text.splitlines())
    for row in reader:
        out.append({(k or "").strip().lower(): v for k, v in row.items()})
    return out


def split_top(s, sep=","):
    parts, cur, depth, in_q = [], [], 0, False
    for ch in s:
        if ch == '"':
            in_q = not in_q
        if not in_q:
            if ch in "{(":
                depth += 1
            elif ch in "})":
                depth -= 1
            if ch == sep and depth == 0:
                parts.append("".join(cur))
                cur = []
                continue
        cur.append(ch)
    parts.append("".join(cur))
    return parts


def strip_bib_value(v):
    v = v.strip()
    for _ in range(3):
        if (v.startswith("{") and v.endswith("}")) or \
           (v.startswith('"') and v.endswith('"')):
            v = v[1:-1].strip()
        else:
            break
    return re.sub(r"\s+", " ", v)


def parse_bib(path, text):
    out = []
    for m in re.finditer(r"@\w+\s*\{\s*", text):
        start, depth, i = m.end(), 1, m.end()
        while i < len(text) and depth > 0:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        body = text[start:i - 1]
        key, _, fields = body.partition(",")
        rec = {"id": key.strip()}
        for part in split_top(fields):
            if "=" not in part:
                continue
            name, _, val = part.partition("=")
            rec[name.strip().lower()] = strip_bib_value(val)
        out.append(rec)
    return out


def parse_ris(path, text):
    out, cur = [], None
    tagmap = {"TI": "title", "T1": "title", "AB": "abstract", "N2": "abstract",
              "PY": "year", "Y1": "year", "ID": "id", "KW": "keywords"}
    for line in text.splitlines():
        if len(line) < 6 or line[2:6] != "  - ":
            continue
        tag, val = line[:2], line[6:].strip()
        if tag == "TY":
            cur = {}
        elif tag == "ER" and cur is not None:
            out.append(cur)
            cur = None
        elif cur is not None and tag in tagmap:
            k = tagmap[tag]
            if k == "keywords":
                cur.setdefault("keywords", []).append(val)
            elif k in cur and cur[k]:
                cur[k] = cur[k] + " " + val
            else:
                cur[k] = val
    if cur is not None:
        out.append(cur)
    return out


FIELD_PREFIX = re.compile(
    r"(?im)^\s*(?:[#>*-]*\s*)?(title|year|abstract|keywords|citations|id)"
    r"\s*[:：]\s*(.+?)\s*$")


def parse_txt_md(path, text):
    out = []
    blocks = re.split(r"\n\s*\n", text)
    for block in blocks:
        fields = {m.group(1).lower(): m.group(2) for m in FIELD_PREFIX.finditer(block)}
        if fields:
            out.append(fields)
    if not out and text.strip():
        lines = [l.strip().lstrip("#").strip() for l in text.splitlines() if l.strip()]
        out.append({
            "title": lines[0] if lines else "",
            "year": (YEAR_RE.search(text) or [None])[0] if YEAR_RE.search(text) else None,
            "abstract": text[:4000],
        })
    return out


PARSERS = {".json": parse_json, ".jsonl": parse_jsonl, ".csv": parse_csv,
           ".bib": parse_bib, ".ris": parse_ris, ".txt": parse_txt_md,
           ".md": parse_txt_md}


def collect_files(inputs):
    files = []
    for p in inputs:
        if os.path.isdir(p):
            for root, _dirs, names in os.walk(p):
                for n in sorted(names):
                    if os.path.splitext(n)[1].lower() in KNOWN_EXT:
                        files.append(os.path.join(root, n))
        elif os.path.isfile(p):
            files.append(p)
        else:
            print("WARN: input not found, skipped: %s" % p, file=sys.stderr)
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--inputs", nargs="+", required=True)
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)

    records, seq = [], 0
    for path in collect_files(args.inputs):
        ext = os.path.splitext(path)[1].lower()
        parser = PARSERS.get(ext)
        if parser is None:
            print("WARN: unsupported extension, skipped: %s" % path, file=sys.stderr)
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            print("WARN: unreadable file %s: %s" % (path, exc), file=sys.stderr)
            continue
        try:
            raw = parser(path, text)
        except Exception as exc:  # never let one bad file kill the build
            print("WARN: parse failed %s: %s" % (path, exc), file=sys.stderr)
            continue
        for d in raw:
            if not isinstance(d, dict):
                continue
            seq += 1
            records.append(canon_record(d, path, seq))

    seen = {}
    for r in records:
        if r["id"] in seen:
            seen[r["id"]] += 1
            r["id"] = "%s#%d" % (r["id"], seen[r["id"]])
        else:
            seen[r["id"]] = 1

    records.sort(key=lambda r: (r["year"] is None, r["year"] or 0, r["id"]))
    out_path = os.path.join(args.work, "canon.jsonl")
    with open(out_path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    n_year = sum(1 for r in records if r["year"] is not None)
    print("build_corpus: %d records (%d with year) -> %s" %
          (len(records), n_year, out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
