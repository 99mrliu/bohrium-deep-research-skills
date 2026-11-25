#!/usr/bin/env python3
"""table_mine.py - mine printed tables from a paper PDF into provenance-carrying CSVs.

Pipeline
--------
1. `pdftotext -layout <pdf> -` (page breaks recorded as form feeds) -> work/paper.txt
2. Caption lines matching ^Table\\s*\\d+ are located (page number tracked).
3. For each caption, parse the FOLLOWING aligned block: lines after the caption
   until a blank-line gap or the next caption/figure-caption. The header row
   gives column boundaries from runs of 2+ spaces (boundary = gap midpoint);
   data rows are split at those boundaries; cells keep unit suffixes verbatim
   ("%", "+/-", sci-notation stay untouched).
4. Conservative guard: if a block resists parsing (irregular columns, header
   with < 2 columns, empty cells count mismatch), NO csv is guessed; instead a
   work/tables/table-N.worksheet.md is written with the raw block plus a CSV
   schema header, marked "manual-transcribe". The agent transcribes it
   verbatim into table-N.csv; number_audit will check the numbers later.

Outputs
-------
work/paper.txt                       full layout text (input for number_audit)
work/tables/table-N.csv              mined table (status "mined")
work/tables/table-N.worksheet.md     raw block for manual transcription (status "manual")
work/tables.json                     [{table_id, caption, page, rows, cols, csv_path, status}]

Pure stdlib. No network. Invocation:
    python3 /skills/weekly-skill/scripts/table_mine.py --pdf /input/paper.pdf
Env: CASE_INPUT_DIR, CASE_WORK_DIR, CASE_OUTPUT_DIR (defaults /input, /app/work, /app/output)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys

CAPTION_RE = re.compile(r"^\s*Table\s*(\d+)\b\s*[:.]?\s*(.*)$")
FIGCAP_RE = re.compile(r"^\s*(Figure|Fig\.?)\s*\d+", re.IGNORECASE)
GAP_RE = re.compile(r"\s{2,}")


def fail(msg: str, code: int = 1) -> "None":
    print(f"[table_mine] ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def column_bounds(header_line: str):
    """Boundary x-offsets between columns: midpoints of 2+ space runs that lie
    INSIDE the stripped span of the header (leading/trailing whitespace is
    indentation, not a column)."""
    stripped = header_line.strip()
    if not stripped:
        return [0]
    span_lo = header_line.index(stripped[0])
    span_hi = len(header_line.rstrip())
    gaps = [g for g in GAP_RE.finditer(header_line)
            if g.start() >= span_lo and g.end() <= span_hi]
    bounds = [0] + [(g.start() + g.end()) // 2 for g in gaps]
    return bounds  # ncols = len(bounds); last column runs to end of line


def split_row(line: str, bounds):
    cells = []
    for i in range(len(bounds)):
        s = bounds[i]
        e = bounds[i + 1] if i + 1 < len(bounds) else len(line)
        cells.append(line[s:e].strip() if s < len(line) else "")
    return cells


def worksheet_md(table_id, caption, page, raw_block, header_cells):
    cols = header_cells if header_cells else ["col_1", "col_2", "col_3"]
    schema = ",".join(c.strip() or f"col_{i+1}" for i, c in enumerate(cols))
    return (
        f"# MANUAL-TRANSCRIBE worksheet: {table_id}\n\n"
        f"- caption: {caption}\n- page: {page}\n- status: manual-transcribe\n\n"
        f"This table block resisted automatic column parsing. Transcribe the raw "
        f"block VERBATIM into `{table_id}.csv` (same directory) using the schema "
        f"header below. Keep every character of every cell (%, +/-, sci-notation). "
        f"Never estimate values; number_audit will check them against the paper.\n\n"
        f"## CSV schema header\n\n```\n{schema}\n```\n\n"
        f"## Raw block (pdftotext -layout, page {page})\n\n```\n{raw_block}\n```\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Mine printed tables from a paper PDF.")
    ap.add_argument("--pdf", required=True, help="path to the paper PDF")
    args = ap.parse_args()

    work = os.environ.get("CASE_WORK_DIR", "/app/work")
    tables_dir = os.path.join(work, "tables")
    os.makedirs(tables_dir, exist_ok=True)

    if not os.path.isfile(args.pdf):
        fail(f"pdf not found: {args.pdf}", 2)
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        fail("pdftotext not found in PATH; cannot mine tables", 2)

    proc = subprocess.run(
        [pdftotext, "-layout", args.pdf, "-"], capture_output=True, text=True
    )
    if proc.returncode != 0:
        fail(f"pdftotext failed: {proc.stderr.strip()}", 2)
    text = proc.stdout

    paper_path = os.path.join(work, "paper.txt")
    with open(paper_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"[table_mine] wrote {paper_path} ({len(text)} chars)")

    pages = text.split("\f")
    captions = []  # (num, caption_text, page_no, page_lines, line_idx)
    for pi, page in enumerate(pages, start=1):
        lines = page.split("\n")
        for li, line in enumerate(lines):
            m = CAPTION_RE.match(line)
            if m:
                captions.append((m.group(1), line.strip(), pi, lines, li))

    if not captions:
        print("[table_mine] no table captions found; tables.json will be empty")

    records = []
    seen_ids = set()
    for num, caption, page_no, lines, li in captions:
        table_id = f"table-{num}"
        if table_id in seen_ids:
            print(f"[table_mine] WARNING: duplicate caption '{caption}', skipping")
            continue
        seen_ids.add(table_id)

        # Following aligned block: until blank-line gap or next caption.
        block = []
        for line in lines[li + 1 :]:
            if not line.strip():
                break
            if CAPTION_RE.match(line) or FIGCAP_RE.match(line):
                break
            block.append(line.rstrip())

        status, rows, cols, csv_path = "manual", 0, 0, ""
        header_cells, data_rows, reason = [], [], ""
        if len(block) < 2:
            reason = f"block too short ({len(block)} line(s))"
        else:
            header_line, data_lines = block[0], block[1:]
            bounds = column_bounds(header_line)
            ncols = len(bounds)
            header_cells = split_row(header_line, bounds)
            if ncols < 2:
                reason = f"header has < 2 columns: {header_line!r}"
            elif any(not c for c in header_cells):
                reason = f"empty header cell(s) in {header_line!r}"
            else:
                for dl in data_lines:
                    cells = split_row(dl, bounds)
                    if sum(1 for c in cells if c) != ncols:
                        reason = (
                            f"irregular columns: row {dl!r} yields "
                            f"{sum(1 for c in cells if c)} non-empty cells, "
                            f"expected {ncols}"
                        )
                        data_rows = []
                        break
                    data_rows.append(cells)
                if data_rows:
                    status = "mined"

        if status == "mined":
            csv_path = os.path.join(tables_dir, f"{table_id}.csv")
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(header_cells)
                w.writerows(data_rows)
            rows, cols = len(data_rows), len(header_cells)
            print(f"[table_mine] {table_id} (p.{page_no}) mined: "
                  f"{rows} rows x {cols} cols -> {csv_path}")
        else:
            ws_path = os.path.join(tables_dir, f"{table_id}.worksheet.md")
            with open(ws_path, "w", encoding="utf-8") as f:
                f.write(worksheet_md(table_id, caption, page_no,
                                     "\n".join(block), header_cells))
            cols = len(header_cells)
            print(f"[table_mine] {table_id} (p.{page_no}) MANUAL-TRANSCRIBE "
                  f"({reason}) -> {ws_path}")

        records.append({
            "table_id": table_id,
            "caption": caption,
            "page": page_no,
            "rows": rows,
            "cols": cols,
            "csv_path": csv_path,
            "status": status,
        })

    out = os.path.join(work, "tables.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    print(f"[table_mine] wrote {out} ({len(records)} table(s))")


if __name__ == "__main__":
    main()
