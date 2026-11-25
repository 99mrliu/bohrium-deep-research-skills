#!/usr/bin/env python3
"""common.py — shared helpers for the formula-symbol-fidelity skill.

Word-level TSV loading (two dialects) and deterministic line grouping.
Python 3 standard library only.

Supported input dialects
------------------------
1. Simple word TSV (one header line optional):
       page  x0  y0  x1  y1  size  text
2. `pdftotext -tsv` output (header line required):
       level page_num par_num block_num line_num word_num
       left top width height conf text
   Only rows with level == 5 (words) are used; size is taken as height.

Coordinates follow the PDF / pdftotext convention: y grows DOWNWARD,
so a superscript has a SMALLER y-extent than the baseline it sits on.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


class InputError(Exception):
    """Raised for malformed / unreadable input. Callers map this to exit 2."""


@dataclass
class Word:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    size: float
    text: str

    @property
    def y_center(self) -> float:
        return 0.5 * (self.y0 + self.y1)


@dataclass
class Line:
    page: int
    words: List[Word] = field(default_factory=list)

    # ---- derived geometry -------------------------------------------------
    @property
    def bbox(self):
        return [
            min(w.x0 for w in self.words),
            min(w.y0 for w in self.words),
            max(w.x1 for w in self.words),
            max(w.y1 for w in self.words),
        ]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in sorted(self.words, key=lambda w: w.x0))

    @property
    def size(self) -> float:
        return statistics.median(w.size for w in self.words)

    @property
    def width(self) -> float:
        b = self.bbox
        return b[2] - b[0]

    @property
    def x_center(self) -> float:
        b = self.bbox
        return 0.5 * (b[0] + b[2])


def _float(row, idx, path, lineno):
    try:
        return float(row[idx])
    except (ValueError, IndexError):
        raise InputError(f"{path}:{lineno}: bad numeric field in row: {row!r}")


def load_words(path):
    """Load words from either supported TSV dialect. Returns list[Word]."""
    p = Path(path)
    if not p.is_file():
        raise InputError(f"input TSV not found: {path}")
    raw = p.read_text(encoding="utf-8", errors="replace").splitlines()
    words: List[Word] = []
    dialect = None
    for lineno, line in enumerate(raw, start=1):
        if not line.strip():
            continue
        row = line.rstrip("\n").split("\t")
        head = row[0].strip().lower()
        if lineno == 1 and head in ("page", "level"):
            dialect = "simple" if head == "page" else "pdftotext"
            continue
        if dialect is None:
            # No header: guess from column count.
            dialect = "pdftotext" if len(row) >= 12 else "simple"
        if dialect == "pdftotext":
            if len(row) < 12 or row[0].strip() != "5":
                continue  # only word-level rows
            page = int(_float(row, 1, path, lineno))
            left = _float(row, 6, path, lineno)
            top = _float(row, 7, path, lineno)
            width = _float(row, 8, path, lineno)
            height = _float(row, 9, path, lineno)
            text = row[11]
            words.append(Word(page, left, top, left + width, top + height,
                              height, text))
        else:
            if len(row) < 7:
                raise InputError(f"{path}:{lineno}: expected 7 columns, got {len(row)}")
            page = int(_float(row, 0, path, lineno))
            words.append(Word(
                page,
                _float(row, 1, path, lineno), _float(row, 2, path, lineno),
                _float(row, 3, path, lineno), _float(row, 4, path, lineno),
                _float(row, 5, path, lineno), row[6],
            ))
    return words


def group_lines(words, tol_factor: float = 0.6):
    """Group words into visual lines.

    Words are sorted by (page, y0, x0); a word joins the open line when it
    is on the same page and its y0 is within ``tol_factor * median_page_size``
    of the line's anchor y0. The factor 0.6 is deliberately generous so that
    sub/superscripts (offset by ~0.3-0.5 x-height) stay in their parent line.
    """
    if not words:
        return []
    sizes = {}
    for w in words:
        sizes.setdefault(w.page, []).append(w.size)
    page_med = {pg: statistics.median(s) for pg, s in sizes.items()}

    lines: List[Line] = []
    anchor_y0 = None
    for w in sorted(words, key=lambda w: (w.page, w.y0, w.x0)):
        tol = tol_factor * page_med[w.page]
        if (lines and lines[-1].page == w.page and anchor_y0 is not None
                and abs(w.y0 - anchor_y0) <= tol):
            lines[-1].words.append(w)
        else:
            lines.append(Line(w.page, [w]))
            anchor_y0 = w.y0
    # Sort words inside each line left-to-right.
    for ln in lines:
        ln.words.sort(key=lambda w: w.x0)
    return lines


def estimate_page_width(words, page):
    """Estimate page width assuming symmetric left/right margins."""
    xs0 = [w.x0 for w in words if w.page == page]
    xs1 = [w.x1 for w in words if w.page == page]
    if not xs0:
        return 0.0
    return max(xs1) + min(xs0)
