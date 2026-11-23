#!/usr/bin/env python3
"""extract_terms.py -- extract candidate domain terms from a source text (EN) into a termbase draft.

Usage:
    python3 extract_terms.py --src <file-or-dir> --out termbase_draft.json

--src accepts .txt/.md files directly, a directory of them, or a .pdf
(converted with `pdftotext -layout` into a temp file; honest error if pdftotext
is missing).

Stdlib only. Deterministic output.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter

ACRONYM_RE = re.compile(r"([A-Z][A-Za-z][A-Za-z\- ]{2,60}?)\s*\(([A-Z]{2,8})\)")
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z\-]*")
SECTION_HEAD_RE = re.compile(r"^(abstract|introduction|reference|conclusion)s?\b", re.IGNORECASE)
CAPTION_RE = re.compile(r"^(figure|fig\.|table)\b", re.IGNORECASE)
MD_HEAD_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def pdf_to_text(path):
    """Convert PDF via pdftotext -layout to a temp file; return its path."""
    fd, tmp = tempfile.mkstemp(suffix=".txt", prefix="extract_terms_")
    os.close(fd)
    try:
        proc = subprocess.run(
            ["pdftotext", "-layout", path, tmp],
            capture_output=True, text=True, timeout=300,
        )
    except FileNotFoundError:
        os.unlink(tmp)
        sys.exit(
            "ERROR: `pdftotext` not found. Install poppler (e.g. `brew install poppler` / "
            "`apt-get install poppler-utils`), or convert the PDF to .txt yourself and pass that."
        )
    if proc.returncode != 0:
        os.unlink(tmp)
        sys.exit(f"ERROR: pdftotext failed on {path}: {proc.stderr.strip()}")
    return tmp


def collect_sources(src):
    """Return list of (path, is_temp) text files to read."""
    files = []
    if os.path.isdir(src):
        for name in sorted(os.listdir(src)):
            p = os.path.join(src, name)
            if os.path.isfile(p) and name.lower().endswith((".txt", ".md", ".pdf")):
                files.append(p)
        if not files:
            sys.exit(f"ERROR: no .txt/.md/.pdf files found in directory {src}")
    elif os.path.isfile(src):
        files.append(src)
    else:
        sys.exit(f"ERROR: --src path does not exist: {src}")

    out = []
    for p in files:
        if p.lower().endswith(".pdf"):
            out.append((pdf_to_text(p), True, p))
        else:
            out.append((p, False, p))
    return out


def is_allcaps_short(line):
    words = line.split()
    if not (1 <= len(words) <= 8):
        return False
    letters = [c for c in line if c.isalpha()]
    if len(letters) < 3:
        return False
    return all(c.isupper() for c in letters)


def split_sections(text):
    """Yield (section_name, line) for each content line."""
    section = "title"
    for i, raw in enumerate(text.splitlines()):
        line = raw.strip()
        if not line:
            continue
        m = MD_HEAD_RE.match(line)
        if m:
            section = m.group(1).strip().lower().replace(" ", "_")[:40]
            continue
        hm = SECTION_HEAD_RE.match(line)
        if hm:
            section = hm.group(1).lower()
            if section == "reference":
                section = "references"
            remainder = line[hm.end():].strip(" :.-")
            if remainder:
                yield section, remainder
            continue
        if is_allcaps_short(line):
            section = line.lower().replace(" ", "_")[:40]
            continue
        if i < 3 and section == "title":
            yield "title", line
            continue
        if CAPTION_RE.match(line):
            yield "caption", line
            continue
        yield section, line


def token_ok(tok):
    """Candidate-phrase token: Capitalized or contains a hyphen."""
    return tok[0].isupper() or "-" in tok


def normalize_term(term):
    t = term.lower().replace("-", " ")
    return re.sub(r"\s+", " ", t).strip()


def occurrence_regex(term):
    """Case-insensitive, hyphen/space equivalent, optional trailing plural 's'."""
    parts = normalize_term(term).split(" ")
    body = r"[ \-]".join(re.escape(p) for p in parts)
    if parts and not parts[-1].endswith("s"):
        body += r"s?"
    return re.compile(r"(?<![a-z0-9])" + body + r"(?![a-z0-9])", re.IGNORECASE)


def extract(path, text):
    sections_lines = list(split_sections(text))
    acronym_entries = []  # [full_name, acronym, definition_sections]
    seen_acr = set()

    for section, line in sections_lines:
        for m in ACRONYM_RE.finditer(line):
            full = m.group(1).strip()
            acr = m.group(2)
            # tidy trailing words like "a"/"the" are impossible here due to regex, but strip stray spaces
            full = re.sub(r"\s+", " ", full)
            key = (full.lower(), acr)
            if key not in seen_acr:
                seen_acr.add(key)
                acronym_entries.append([full, acr, set()])
            for e in acronym_entries:
                if e[0].lower() == full.lower() and e[1] == acr:
                    e[2].add(section)

    # n-gram phrases
    ngram_counts = Counter()
    ngram_sections = {}
    for section, line in sections_lines:
        toks = TOKEN_RE.findall(line)
        seen_in_line = set()
        for n in (2, 3, 4):
            for i in range(len(toks) - n + 1):
                window = toks[i:i + n]
                if not all(token_ok(t) for t in window):
                    continue
                ng = " ".join(window)
                ngram_counts[ng] += 1
                if ng not in seen_in_line:
                    ngram_sections.setdefault(ng, set()).add(section)
                    seen_in_line.add(ng)

    # keep freq >= 2, drop n-grams fully contained in a longer kept n-gram of equal frequency
    kept = {ng: c for ng, c in ngram_counts.items() if c >= 2}
    drop = set()
    kept_items = sorted(kept.items(), key=lambda kv: (-len(kv[0].split()), kv[0]))
    for ng, c in kept_items:
        if ng in drop:
            continue
        for other, oc in kept_items:
            if other == ng or other in drop:
                continue
            if len(other.split()) < len(ng.split()):
                continue
            if oc == c and re.search(r"(?<![A-Za-z\-])" + re.escape(ng) + r"(?![A-Za-z\-])", other):
                drop.add(ng)
                break
    phrases = [(ng, c, ngram_sections[ng]) for ng, c in kept.items() if ng not in drop]

    entries = []
    for full, acr, secs in acronym_entries:
        entries.append({
            "source_term": full,
            "acronym": acr,
            "kind": "acronym",
            "frequency": 0,
            "sections": [],
        })
    for ng, c, secs in phrases:
        entries.append({
            "source_term": ng,
            "acronym": None,
            "kind": "phrase",
            "frequency": 0,
            "sections": [],
        })

    # frequency & sections: count real occurrences (case-insensitive, hyphen/space
    # equivalent, plural s) of the full term plus, for acronym kind, the acronym.
    for e in entries:
        rx = occurrence_regex(e["source_term"])
        acr_rx = (re.compile(r"\b" + re.escape(e["acronym"]) + r"\b")
                  if e.get("acronym") else None)
        freq = 0
        secs = set()
        for section, line in sections_lines:
            n = len(rx.findall(line))
            if acr_rx:
                n += len(acr_rx.findall(line))
            if n:
                freq += n
                secs.add(section)
        e["frequency"] = max(freq, 1)
        e["sections"] = sorted(secs)

    entries.sort(key=lambda e: (-e["frequency"], e["source_term"].lower()))
    for idx, e in enumerate(entries, 1):
        e_ordered = {"id": f"T{idx:03d}"}
        e_ordered.update(e)
        e_ordered["target"] = None
        e_ordered["forbidden_variants"] = []
        entries[idx - 1] = e_ordered
    return entries


def main():
    ap = argparse.ArgumentParser(description="Extract candidate domain terms into a termbase draft.")
    ap.add_argument("--src", required=True, help="source .txt/.md/.pdf file or directory")
    ap.add_argument("--out", required=True, help="output termbase_draft.json path")
    args = ap.parse_args()

    sources = collect_sources(args.src)
    all_entries = []
    source_files = []
    for text_path, is_temp, orig_path in sources:
        with open(text_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        if not text.strip():
            print(f"WARNING: no text extracted from {orig_path} (scanned PDF or empty file?)", file=sys.stderr)
        source_files.append({"path": orig_path, "sha256": sha256_file(orig_path)})
        all_entries.extend(extract(orig_path, text))
        if is_temp:
            os.unlink(text_path)

    # merge duplicates across files
    merged = {}
    for e in all_entries:
        key = (e["source_term"].lower(), e["kind"])
        if key in merged:
            m = merged[key]
            m["frequency"] += e["frequency"]
            m["sections"] = sorted(set(m["sections"]) | set(e["sections"]))
        else:
            merged[key] = e
    entries = sorted(merged.values(), key=lambda e: (-e["frequency"], e["source_term"].lower()))
    for idx, e in enumerate(entries, 1):
        e["id"] = f"T{idx:03d}"

    draft = {
        "source_files": source_files,
        "entries": entries,
        "stats": {
            "files": len(source_files),
            "entries": len(entries),
            "acronyms": sum(1 for e in entries if e["kind"] == "acronym"),
            "phrases": sum(1 for e in entries if e["kind"] == "phrase"),
        },
    }
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")

    print(f"extract_terms: {len(source_files)} file(s) -> {len(entries)} candidate entries "
          f"({draft['stats']['acronyms']} acronym, {draft['stats']['phrases']} phrase)")
    for e in entries[:15]:
        acr = f" [{e['acronym']}]" if e["acronym"] else ""
        print(f"  {e['id']}  freq={e['frequency']:<3d} {e['kind']:<7s} {e['source_term']}{acr}  sections={','.join(e['sections'])}")
    if len(entries) > 15:
        print(f"  ... and {len(entries) - 15} more (see {args.out})")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
