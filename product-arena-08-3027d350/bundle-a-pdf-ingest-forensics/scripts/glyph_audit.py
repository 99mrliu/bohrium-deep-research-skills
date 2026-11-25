#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
glyph_audit.py — audit extracted text files for glyph corruption (stdlib only).

A PDF text layer can be present yet useless: CID fonts with broken ToUnicode
maps yield Private-Use-Area glyphs, failed decodes yield U+FFFD, and UTF-8
bytes misread as Latin-1 yield classic mojibake. This script measures, per
file and globally:

  * U+FFFD replacement chars            (failed decode)
  * Unicode Private-Use-Area chars      (unmapped CID / custom encoding)
  * unusual control chars               (Cc except \\t \\n \\r)
  * UTF-8-as-Latin-1 mojibake           (e.g. "â€", "ç±»"-style pairs)
  * CJK<->Latin transition churn        (scrambled-encoding heuristic)

Usage:
  python3 glyph_audit.py PATH [--glob "*.txt"] [--out OUTDIR]
PATH may be a single file or a directory (searched recursively).

Output: OUTDIR/glyph_audit.json + one-line JSON summary on stdout.
Exit codes: 0 = clean, 2 = suspect/corrupt files found.

Severity rules (see references/method.md):
  high   : any U+FFFD run > 2, or PUA ratio > 0.5%, or mojibake chars > 3%
  medium : any U+FFFD, any PUA, >=3 mojibake hits, or any stray control char
  low    : 1-2 mojibake hits only
  none   : nothing fired
"""
import argparse
import glob as globmod
import json
import os
import re
import sys
import unicodedata

REPORT_SCHEMA = "pdf-ingest-forensics/glyph_audit/v1"

PUA_RANGES = ((0xE000, 0xF8FF), (0xF0000, 0xFFFFD), (0x100000, 0x10FFFD))
CJK_RANGES = ((0x4E00, 0x9FFF), (0x3400, 0x4DBF), (0x3000, 0x303F),
              (0xFF00, 0xFFEF), (0x3000, 0x30FF))
# UTF-8 multibyte sequences mis-decoded as Latin-1: a lead byte 0xC0-0xFF
# (renders as À-ÿ) followed by a continuation byte 0x80-0xBF (renders as
# control/punctuation like \x80-\xbf). "â€" and "ç±»" are the classic shapes.
MOJIBAKE_RE = re.compile("(?:[\u00c0-\u00ff][\u0080-\u00bf])+")
# well-known literal signatures seen in the wild (informational, not scored twice)
KNOWN_SIGNATURES = ("â€", "Ã©", "Ã¨", "ç±", "å¼", "æ–")

PUA_RATIO_HIGH = 0.005     # > 0.5% PUA chars => corrupt page
MOJIBAKE_RATIO_MED = 0.01  # > 1% mojibake chars => suspect
MOJIBAKE_RATIO_HIGH = 0.03
FFFD_RUN_HIGH = 2          # runs of >2 replacement chars => high


def _in_ranges(ch, ranges):
    o = ord(ch)
    return any(lo <= o <= hi for lo, hi in ranges)


def audit_text(text):
    total = len(text)
    n_fffd = text.count("�")
    fffd_maxrun = 0
    run = 0
    n_pua = 0
    n_ctrl = 0
    n_cjk = 0
    n_latin = 0
    flips = 0
    prev_class = None
    for ch in text:
        if ch == "�":
            run += 1
            fffd_maxrun = max(fffd_maxrun, run)
        else:
            run = 0
        if _in_ranges(ch, PUA_RANGES):
            n_pua += 1
        cat = unicodedata.category(ch)
        if cat == "Cc" and ch not in "\t\n\r":
            n_ctrl += 1
        if _in_ranges(ch, CJK_RANGES):
            n_cjk += 1
            cls = "cjk"
        elif ("a" <= ch.lower() <= "z"):
            n_latin += 1
            cls = "latin"
        else:
            cls = None
        if cls and prev_class and cls != prev_class:
            flips += 1
        if cls:
            prev_class = cls

    hits = MOJIBAKE_RE.findall(text)
    mojibake_chars = sum(len(h) for h in hits)
    known_hits = sum(text.count(sig) for sig in KNOWN_SIGNATURES)

    letters = max(1, n_cjk + n_latin + n_pua)  # denominator: real letter-ish chars
    pua_ratio = n_pua / letters
    moji_ratio = mojibake_chars / max(1, total)

    reasons = []
    severity = "none"
    def bump(level):
        nonlocal severity
        order = ["none", "low", "medium", "high"]
        if order.index(level) > order.index(severity):
            severity = level

    if fffd_maxrun > FFFD_RUN_HIGH:
        bump("high"); reasons.append("U+FFFD run of %d (failed decode)" % fffd_maxrun)
    elif n_fffd > 0:
        bump("medium"); reasons.append("%d U+FFFD replacement chars" % n_fffd)
    if pua_ratio > PUA_RATIO_HIGH:
        bump("high"); reasons.append(
            "PUA ratio %.2f%% > 0.5%% (unmapped CID/custom encoding)" % (pua_ratio * 100))
    elif n_pua > 0:
        bump("medium"); reasons.append("%d private-use-area chars" % n_pua)
    if moji_ratio > MOJIBAKE_RATIO_HIGH:
        bump("high"); reasons.append("mojibake chars %.2f%% of file" % (moji_ratio * 100))
    elif moji_ratio > MOJIBAKE_RATIO_MED or len(hits) >= 3:
        bump("medium"); reasons.append("%d UTF-8-as-Latin-1 mojibake hits" % len(hits))
    elif hits:
        bump("low"); reasons.append("%d possible mojibake hit(s)" % len(hits))
    if n_ctrl > 0:
        bump("medium"); reasons.append("%d stray control chars" % n_ctrl)
    if not reasons:
        reasons.append("no glyph corruption signals")

    return {
        "chars_total": total,
        "fffd_count": n_fffd,
        "fffd_max_run": fffd_maxrun,
        "pua_count": n_pua,
        "pua_ratio": round(pua_ratio, 6),
        "control_count": n_ctrl,
        "mojibake_hits": len(hits),
        "mojibake_chars": mojibake_chars,
        "mojibake_ratio": round(moji_ratio, 6),
        "known_signature_hits": known_hits,
        "cjk_chars": n_cjk,
        "latin_chars": n_latin,
        "cjk_latin_flips": flips,
        "severity": severity,
        "reasons": reasons,
    }


def collect_files(path, pattern):
    if os.path.isfile(path):
        return [path]
    found = globmod.glob(os.path.join(path, "**", pattern), recursive=True)
    return sorted(f for f in found if os.path.isfile(f))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Audit extracted text files for glyph corruption.")
    ap.add_argument("path", help=".txt file or directory of .txt files")
    ap.add_argument("--glob", default="*.txt", help="filename pattern in "
                                                  "directory mode (default: *.txt)")
    ap.add_argument("--out", default=".", help="output directory for glyph_audit.json")
    args = ap.parse_args(argv)

    files = collect_files(args.path, args.glob)
    os.makedirs(args.out, exist_ok=True)

    file_reports = []
    order = ["none", "low", "medium", "high"]
    worst = "none"
    for f in files:
        try:
            with open(f, "r", encoding="utf-8", errors="strict") as fh:
                text = fh.read()
            decode_note = None
        except UnicodeDecodeError as exc:
            with open(f, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            decode_note = "file itself is not valid UTF-8: %s" % exc
        rep = audit_text(text)
        if decode_note:
            rep["severity"] = "high"
            rep["reasons"].insert(0, decode_note)
        rep["file"] = os.path.relpath(f, args.path) if os.path.isdir(args.path) \
            else os.path.basename(f)
        file_reports.append(rep)
        if order.index(rep["severity"]) > order.index(worst):
            worst = rep["severity"]

    if not file_reports:
        report = {
            "schema": REPORT_SCHEMA,
            "tool": "glyph_audit.py",
            "input": os.path.abspath(args.path),
            "status": "clean",
            "global_severity": "none",
            "reasons": ["no text files matched; nothing to audit"],
            "files": [],
            "flagged_files": [],
        }
        code = 0
    else:
        status = "clean" if worst == "none" else ("suspect" if worst in ("low", "medium")
                                                  else "corrupt")
        report = {
            "schema": REPORT_SCHEMA,
            "tool": "glyph_audit.py",
            "input": os.path.abspath(args.path),
            "status": status,
            "global_severity": worst,
            "reasons": sorted({r for fr in file_reports for r in fr["reasons"]
                               if not r.startswith("no glyph")}),
            "files": file_reports,
            "flagged_files": [fr["file"] for fr in file_reports
                              if fr["severity"] != "none"],
        }
        code = 0 if status == "clean" else 2

    out_path = os.path.join(args.out, "glyph_audit.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(json.dumps({
        "status": report["status"],
        "global_severity": report["global_severity"],
        "files_audited": len(report["files"]),
        "flagged_files": report["flagged_files"],
        "report": out_path,
    }, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
