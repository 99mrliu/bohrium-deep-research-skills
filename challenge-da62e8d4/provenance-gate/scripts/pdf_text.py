#!/usr/bin/env python3
"""Extract physical-page text from a PDF into pages.jsonl.

Output lines have the form {"page": n, "text": "..."}; page numbers start
at 1 and are physical PDF pages, not printed article page labels.

Normalization is intentionally performed by gate.py, not here.  Its rules are:
Unicode NFKC (including common ligatures and full-width digits/percent), a
unified ASCII minus sign, rejoining words broken by a line-ending hyphen, and
collapsing all whitespace runs to one ASCII space.  Keeping this extractor's
text unchanged preserves a faithful evidence trail.

Fallback chain for PDFs: pdftotext (one subprocess per page, using -f/-l) ->
pypdf -> PyMuPDF/fitz.  A .txt or .md input is read directly as one page.
If every applicable backend fails, the command prints all backend errors and
exits with status 2.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable


class BackendError(RuntimeError):
    pass


def _pdfinfo_page_count(path: Path) -> int | None:
    if shutil.which("pdfinfo") is None:
        return None
    proc = subprocess.run(
        ["pdfinfo", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        if line.startswith("Pages:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                return None
    return None


def _page_count_with_python_backend(path: Path) -> int | None:
    try:
        from pypdf import PdfReader  # type: ignore

        return len(PdfReader(str(path)).pages)
    except Exception:
        pass
    try:
        import fitz  # type: ignore

        with fitz.open(str(path)) as document:
            return document.page_count
    except Exception:
        return None


def _page_count_by_pdftotext_probe(path: Path, executable: str) -> int | None:
    """Find the last valid page using only pdftotext's -f/-l interface."""

    def page_exists(page: int) -> bool:
        proc = subprocess.run(
            [executable, "-f", str(page), "-l", str(page), str(path), "-"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
            check=False,
        )
        return proc.returncode == 0

    if not page_exists(1):
        return None
    low = 1
    high = 2
    max_pages = 10000
    while high <= max_pages and page_exists(high):
        low = high
        high *= 2
    if low >= max_pages:
        raise BackendError(f"PDF appears to exceed the {max_pages}-page probe limit")
    while low + 1 < high:
        middle = (low + high) // 2
        if page_exists(middle):
            low = middle
        else:
            high = middle
    return low


def extract_with_pdftotext(path: Path) -> list[str]:
    executable = shutil.which("pdftotext")
    if executable is None:
        raise BackendError("pdftotext executable not found")
    page_count = _pdfinfo_page_count(path)
    if page_count is None:
        page_count = _page_count_with_python_backend(path)
    if page_count is None:
        page_count = _page_count_by_pdftotext_probe(path, executable)
    if page_count is None or page_count < 1:
        raise BackendError("could not determine PDF page count for pdftotext")

    pages: list[str] = []
    for page in range(1, page_count + 1):
        proc = subprocess.run(
            [executable, "-f", str(page), "-l", str(page), str(path), "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
            check=False,
        )
        if proc.returncode != 0:
            raise BackendError(f"pdftotext failed on page {page}: {proc.stderr.strip()}")
        pages.append(proc.stdout)
    return pages


def extract_with_pypdf(path: Path) -> list[str]:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as exc:
        raise BackendError(f"pypdf is not importable: {exc}") from exc
    try:
        reader = PdfReader(str(path))
        return [(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:
        raise BackendError(f"pypdf extraction failed: {exc}") from exc


def extract_with_fitz(path: Path) -> list[str]:
    try:
        import fitz  # type: ignore
    except Exception as exc:
        raise BackendError(f"PyMuPDF/fitz is not importable: {exc}") from exc
    try:
        with fitz.open(str(path)) as document:
            return [page.get_text("text") for page in document]
    except Exception as exc:
        raise BackendError(f"PyMuPDF/fitz extraction failed: {exc}") from exc


def write_pages(pages: list[str], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as handle:
        for index, text in enumerate(pages, start=1):
            handle.write(json.dumps({"page": index, "text": text}, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="PDF, TXT, or MD input")
    parser.add_argument("--out", required=True, type=Path, help="pages.jsonl output path")
    args = parser.parse_args(argv)

    source = args.input.resolve()
    try:
        if not source.is_file():
            raise BackendError(f"input file does not exist: {source}")
        if source.suffix.lower() in {".txt", ".md"}:
            pages = [source.read_text(encoding="utf-8")]
            backend = "direct-text"
        elif source.suffix.lower() == ".pdf":
            backends: list[tuple[str, Callable[[Path], list[str]]]] = [
                ("pdftotext", extract_with_pdftotext),
                ("pypdf", extract_with_pypdf),
                ("fitz", extract_with_fitz),
            ]
            errors: list[str] = []
            pages = []
            backend = ""
            for name, extractor in backends:
                try:
                    pages = extractor(source)
                    backend = name
                    break
                except (BackendError, subprocess.SubprocessError, OSError) as exc:
                    errors.append(f"{name}: {exc}")
            else:
                details = "; ".join(errors)
                raise BackendError(
                    "all PDF text extraction backends failed; use the platform "
                    f"pdf-render/OCR tool for scanned PDFs. Details: {details}"
                )
        else:
            raise BackendError(f"unsupported input extension: {source.suffix or '(none)'}")

        write_pages(pages, args.out.resolve())
        print(f"backend={backend} pages={len(pages)} out={args.out.resolve()}")
        return 0
    except (BackendError, OSError, UnicodeError) as exc:
        print(f"pdf_text error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
