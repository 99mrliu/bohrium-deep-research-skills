#!/usr/bin/env python3
"""Extract real PDF methods text with installed pdftotext; never fabricate OCR or text layers."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess

from hashlib import sha256

SCRIPT_DIR = Path(__file__).resolve().parent


def script_path(value):
    path = Path(value)
    return path.resolve() if path.is_absolute() else (SCRIPT_DIR / path).resolve()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--output", required=True, help="UTF-8 text with form-feed page separators")
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    pdf = script_path(args.pdf)
    output = script_path(args.output)
    report = script_path(args.report)
    if not pdf.is_file():
        parser.error("PDF not found: %s" % pdf)
    if pdf.suffix.lower() != ".pdf":
        parser.error("Input must have .pdf suffix; inspect actual materials rather than relabeling")
    executable = shutil.which("pdftotext")
    if not executable:
        parser.error("pdftotext is not installed; no install/OCR fallback is attempted. Use an environment-provided PDF tool or declare missing text.")
    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run([executable, "-layout", "-enc", "UTF-8", str(pdf), str(output)], capture_output=True)
    if completed.returncode != 0:
        if output.exists():
            output.unlink()
        report.write_text('{"extraction":"failed","returncode":%d,"stderr":%s}\n' % (completed.returncode, __import__("json").dumps(completed.stderr.decode("utf-8", "replace"))), encoding="utf-8")
        return completed.returncode or 2
    data = output.read_bytes()
    if not data.strip():
        report.write_text('{"extraction":"failed","reason":"empty text layer"}\n', encoding="utf-8")
        return 3
    text = data.decode("utf-8")
    payload = {
        "extraction": "success", "tool": "pdftotext -layout -enc UTF-8",
        "pdf_sha256": sha256(pdf.read_bytes()).hexdigest(),
        "text_sha256": sha256(data).hexdigest(), "bytes": len(data),
        "page_count_from_form_feeds": text.count("\f") + (0 if text.endswith("\f") else 1),
        "page_locator_note": "Form-feed-derived page numbers are extraction pages. If they differ from printed PDF page labels, record original_pdf_page_offset and verify against the actual PDF page view.",
        "ocr": False,
    }
    import json
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
