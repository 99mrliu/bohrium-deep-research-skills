"""Shared helpers for the structure-refs-cartographer scripts.

Python 3 standard library only.

Page-text format (produced upstream from PDF, e.g. with `pdftotext -layout`
or any extractor, then split per page):

    === page 1 ===
    <lines of page 1>
    === page 2 ===
    <lines of page 2>

Optional size hints TSV (one hint per line, '#' comments allowed):
    page<TAB>line_number_1based<TAB>font_size
"""

import json
import re
from pathlib import Path

PAGE_RE = re.compile(r"^===\s*page\s+(\d+)\s*===\s*$", re.IGNORECASE)


def read_pages(path):
    """Read a per-page text file.

    Returns (pages, warnings) where pages is a list of
    {"page": int, "lines": [str, ...]}.
    Text appearing before the first page marker is assigned to page 1
    and reported in warnings.
    """
    pages = []
    current = None
    warnings = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh.read().splitlines():
            m = PAGE_RE.match(raw.strip())
            if m:
                current = {"page": int(m.group(1)), "lines": []}
                pages.append(current)
                continue
            if current is None:
                current = {"page": 1, "lines": []}
                pages.append(current)
                warnings.append("text before first page marker assigned to page 1")
            current["lines"].append(raw)
    if not pages:
        warnings.append("no page markers found; input treated as empty")
    return pages, warnings


def iter_lines(pages):
    """Yield (page_number, line_number_1based, line_text) for every line."""
    for pg in pages:
        for i, line in enumerate(pg["lines"], 1):
            yield pg["page"], i, line


def read_sizes(path):
    """Read optional size-hint TSV into {(page, line_no): font_size}."""
    hints = {}
    with open(path, encoding="utf-8") as fh:
        for row in fh:
            row = row.rstrip("\n")
            if not row or row.startswith("#"):
                continue
            parts = row.split("\t")
            if len(parts) != 3:
                continue
            try:
                hints[(int(parts[0]), int(parts[1]))] = float(parts[2])
            except ValueError:
                continue
    return hints


def median(values):
    vals = sorted(values)
    if not vals:
        return None
    n = len(vals)
    mid = n // 2
    if n % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0


def write_json(obj, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def slugify(text, maxlen=40):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug or "untitled")[:maxlen]
