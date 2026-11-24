#!/usr/bin/env python3
"""build_corpus.py -- normalize heterogeneous literature files into canon.jsonl.

Usage:
    python3 build_corpus.py --work DIR --inputs FILE_OR_DIR_OR_GLOB [ ... ]

Supported input formats (by extension):
    .json   list of records | {"records": [...]} / {"items": [...]} | single object
    .jsonl  one JSON record per line
    .csv    header row; columns matched case-insensitively
    .bib    BibTeX entries (@type{key, title={...}, year=..., abstract=..., keywords=...})
    .ris    RIS tagged lines (TY/TI/AB/PY/ID/DO/KW/ER)
    .txt/.md whole file becomes one record (title = first heading/first non-empty line)

Output: <work>/canon.jsonl -- one record per line, keys:
    id, title, year, abstract, keywords, source_file

Stdlib only. Deterministic (records sorted by id, keys sorted). Never invents
content: missing fields stay empty/None. Unknown keys are ignored.
"""
import argparse
import csv
import glob as globmod
import json
import os
import re
import sys

EXTS = {".json", ".jsonl", ".csv", ".bib", ".ris", ".txt", ".md"}

YEAR_RE = re.compile(r"\b(1[5-9]\d{2}|20\d{2})\b")


def extract_year(value):
    if value is None:
        return None
    if isinstance(value, int):
        return value if 1500 <= value <= 2100 else None
    m = YEAR_RE.search(str(value))
    return int(m.group(1)) if m else None


def split_keywords(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(k).strip() for k in value if str(k).strip()]
    return [p.strip() for p in re.split(r"[;,|]", str(value)) if p.strip()]


def pick(raw, *names):
    """Case-insensitive first-non-empty lookup over several candidate keys."""
    lower = {}
    for k, v in raw.items():
        lk = str(k).strip().lower()
        if lk not in lower:
            lower[lk] = v
    for n in names:
        if n in lower and lower[n] not in (None, ""):
            return lower[n]
    return None


def normalize_record(raw, source_file, idx):
    if not isinstance(raw, dict):
        raw = {"abstract": str(raw)}
    rid = pick(raw, "id", "record_id", "doi", "key", "uid")
    if not rid:
        stem = os.path.splitext(os.path.basename(source_file))[0]
        rid = "%s#%03d" % (stem, idx)
    title = pick(raw, "title", "ti", "name") or ""
    year = extract_year(pick(raw, "year", "date", "published", "py", "y1"))
    abstract = pick(raw, "abstract", "summary", "description", "ab") or ""
    keywords = split_keywords(pick(raw, "keywords", "keyword", "kw", "tags"))
    return {
        "id": str(rid).strip(),
        "title": str(title).strip(),
        "year": year,
        "abstract": str(abstract).strip(),
        "keywords": keywords,
        "source_file": source_file,
    }


def read_json_file(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("records", "items", "data", "papers", "entries"):
            if isinstance(data.get(k), list):
                return data[k]
        return [data]
    return []


def read_jsonl_file(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                print("WARN: skipping malformed JSONL line in %s" % path,
                      file=sys.stderr)
    return out


def read_csv_file(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _parse_bib_fields(body):
    fields = {}
    i, n = 0, len(body)
    while i < n:
        m = re.match(r"\s*,?\s*([A-Za-z][\w-]*)\s*=", body[i:])
        if not m:
            i += 1
            continue
        name = m.group(1).lower()
        i += m.end()
        while i < n and body[i] in " \t\n":
            i += 1
        if i < n and body[i] == "{":
            depth, start = 0, i
            while i < n:
                if body[i] == "{":
                    depth += 1
                elif body[i] == "}":
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
            val = body[start + 1:i - 1]
        elif i < n and body[i] == '"':
            j = i + 1
            while j < n and body[j] != '"':
                j += 1
            val = body[i + 1:j]
            i = j + 1
        else:
            j = i
            while j < n and body[j] not in ",\n":
                j += 1
            val = body[i:j]
            i = j
        val = re.sub(r"\s+", " ", val).strip()
        if val.startswith("{") and val.endswith("}") and len(val) >= 2:
            val = val[1:-1].strip()
        fields[name] = val
    return fields


def read_bib_file(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    records = []
    for m in re.finditer(r"@\w+\s*\{", text):
        # entry key
        km = re.match(r"\s*([^,\s]+)\s*,", text[m.end():])
        key = km.group(1) if km else ""
        body_start = m.end() + (km.end() if km else 0)
        # find matching closing brace of the entry
        depth, j = 1, m.end() - 1
        j += 1
        while j < len(text) and depth > 0:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
            j += 1
        body = text[body_start:j - 1]
        fields = _parse_bib_fields(body)
        fields["key"] = key
        records.append(fields)
    return records


RIS_TAGMAP = {
    "TI": "title", "T1": "title",
    "AB": "abstract", "N2": "abstract",
    "PY": "year", "Y1": "year",
    "ID": "id", "DO": "doi",
}


def read_ris_file(path):
    records, cur = [], None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if len(line) >= 6 and line[2:6] == "  - ":
                tag, val = line[:2], line[6:].strip()
                if tag == "TY":
                    cur = {}
                elif tag == "ER":
                    if cur is not None:
                        records.append(cur)
                    cur = None
                elif cur is not None:
                    if tag == "KW":
                        cur.setdefault("keywords", []).append(val)
                    elif tag in RIS_TAGMAP and RIS_TAGMAP[tag] not in cur:
                        cur[RIS_TAGMAP[tag]] = val
            elif cur is not None and line.strip():
                if "abstract" in cur:
                    cur["abstract"] += " " + line.strip()
    if cur is not None:
        records.append(cur)
    return records


def read_text_file(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    title = ""
    for line in text.splitlines():
        s = line.strip().lstrip("#").strip()
        if s:
            title = s
            break
    stem = os.path.splitext(os.path.basename(path))[0]
    return [{
        "id": stem,
        "title": title,
        "year": extract_year(text),
        "abstract": text.strip(),
    }]


READERS = {
    ".json": read_json_file,
    ".jsonl": read_jsonl_file,
    ".csv": read_csv_file,
    ".bib": read_bib_file,
    ".ris": read_ris_file,
    ".txt": read_text_file,
    ".md": read_text_file,
}


def iter_files(inputs):
    seen = []
    for item in inputs:
        matches = []
        if os.path.isdir(item):
            for name in sorted(os.listdir(item)):
                p = os.path.join(item, name)
                if os.path.isfile(p) and os.path.splitext(name)[1].lower() in EXTS:
                    matches.append(p)
        elif any(ch in item for ch in "*?["):
            matches.extend(sorted(globmod.glob(item)))
        elif os.path.isfile(item):
            matches.append(item)
        else:
            print("WARN: input not found: %s" % item, file=sys.stderr)
        for p in matches:
            if p not in seen:
                seen.append(p)
    return seen


def main():
    ap = argparse.ArgumentParser(description="Normalize literature files to canon.jsonl")
    ap.add_argument("--work", required=True, help="working dir; canon.jsonl is written here")
    ap.add_argument("--inputs", nargs="+", required=True,
                    help="input files, directories, or globs")
    args = ap.parse_args()

    os.makedirs(args.work, exist_ok=True)
    records, seen_ids, dropped = [], set(), 0
    for path in iter_files(args.inputs):
        ext = os.path.splitext(path)[1].lower()
        reader = READERS.get(ext)
        if reader is None:
            print("WARN: unsupported extension, skipped: %s" % path, file=sys.stderr)
            continue
        try:
            raws = reader(path)
        except Exception as exc:  # robust: one bad file must not kill the run
            print("WARN: failed to read %s: %s" % (path, exc), file=sys.stderr)
            continue
        for idx, raw in enumerate(raws, 1):
            rec = normalize_record(raw, path, idx)
            if rec["id"] in seen_ids:
                dropped += 1
                continue
            seen_ids.add(rec["id"])
            records.append(rec)

    records.sort(key=lambda r: r["id"])
    out_path = os.path.join(args.work, "canon.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    print("canon: %d records -> %s (%d duplicate ids dropped)"
          % (len(records), out_path, dropped))
    if not records:
        print("WARN: canon is empty; downstream checks will report unknown records",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
