#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""facsimile_register.py - inventory input material files and extract text layers.

For every file under --input-dir this script records path, sha256, size and a
kind guessed from magic bytes / extension. For PDFs it extracts the text layer
per page: it prefers poppler's pdftotext when available on PATH (unless
--no-poppler is given), otherwise it falls back to a minimal stdlib extractor
that parses uncompressed or FlateDecode content streams and reads Tj/TJ
strings. If neither works it records extraction_degraded: true with a reason
and NEVER guesses content.

Outputs (into --out-dir):
  facsimile_inventory.json         - one entry per file
  extracted/<sha256>.pages.json    - per-page text for pdf/text files

Exit codes: 0 ok, 1 check/violation, 2 usage error.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zlib

CHUNK = 65536


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def guess_kind(path, head):
    if head.startswith(b"%PDF"):
        return "pdf"
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return "pdf"
    try:
        head.decode("utf-8")
        if ext in (".txt", ".md", ".json", ".csv", ".xml", ".html", ".htm", ""):
            return "text"
        # decodable head: still treat as text (patent record dumps often lack extensions)
        return "text"
    except UnicodeDecodeError:
        return "binary"


# ---------------------------------------------------------------------------
# minimal stdlib PDF text-layer extractor
# ---------------------------------------------------------------------------

_ESCAPES = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12,
            ord("("): 40, ord(")"): 41, ord("\\"): 92}


def _unescape_pdf_string(raw):
    out = bytearray()
    i, n = 0, len(raw)
    while i < n:
        c = raw[i]
        if c == 0x5C and i + 1 < n:  # backslash
            c2 = raw[i + 1]
            if c2 in _ESCAPES:
                out.append(_ESCAPES[c2]); i += 2
            elif 48 <= c2 <= 55:  # octal, up to 3 digits
                j = i + 1
                digits = b""
                while j < n and len(digits) < 3 and 48 <= raw[j] <= 55:
                    digits += bytes([raw[j]]); j += 1
                out.append(int(digits, 8) & 0xFF); i = j
            elif c2 in (10, 13):  # line continuation
                i += 2
                if c2 == 13 and i < n and raw[i] == 10:
                    i += 1
            else:
                out.append(c2); i += 2
        else:
            out.append(c); i += 1
    return out.decode("latin-1")


def _tokenize(data):
    tokens = []
    i, n = 0, len(data)
    delims = b" \t\r\n\x0c\x00"
    while i < n:
        c = data[i]
        if c in delims:
            i += 1; continue
        if c == 0x25:  # % comment
            while i < n and data[i] not in b"\r\n":
                i += 1
            continue
        if c == 0x28:  # ( literal string
            depth, j, buf = 1, i + 1, bytearray()
            while j < n and depth > 0:
                ch = data[j]
                if ch == 0x5C:
                    buf.append(ch); j += 1
                    if j < n:
                        buf.append(data[j]); j += 1
                elif ch == 0x28:
                    depth += 1; buf.append(ch); j += 1
                elif ch == 0x29:
                    depth -= 1
                    if depth > 0:
                        buf.append(ch)
                    j += 1
                else:
                    buf.append(ch); j += 1
            tokens.append(("str", _unescape_pdf_string(bytes(buf)))); i = j; continue
        if c == 0x3C and i + 1 < n and data[i + 1] == 0x3C:
            tokens.append(("op", "<<")); i += 2; continue
        if c == 0x3E and i + 1 < n and data[i + 1] == 0x3E:
            tokens.append(("op", ">>")); i += 2; continue
        if c == 0x3C:  # < hex string
            j = data.find(b">", i + 1)
            if j == -1:
                break
            hexs = re.sub(rb"\s+", b"", data[i + 1:j])
            if len(hexs) % 2:
                hexs += b"0"
            try:
                tokens.append(("str", bytes.fromhex(hexs.decode("ascii")).decode("latin-1")))
            except ValueError:
                pass
            i = j + 1; continue
        if c in b"[]":
            tokens.append(("op", chr(c))); i += 1; continue
        if c == 0x2F:  # / name
            j = i + 1
            while j < n and data[j] not in delims + b"()[]<>{}/%":
                j += 1
            tokens.append(("name", data[i:j].decode("latin-1"))); i = j; continue
        j = i
        while j < n and data[j] not in delims + b"()[]<>{}/%":
            j += 1
        tokens.append(("tok", data[i:j].decode("latin-1"))); i = j
    return tokens


def _pop_str(stack):
    for k in range(len(stack) - 1, -1, -1):
        if stack[k][0] == "str":
            return stack.pop(k)[1]
    return ""


def _pop_arr(stack):
    for k in range(len(stack) - 1, -1, -1):
        if stack[k][0] == "arr":
            return stack.pop(k)[1]
    return None


def _is_number(s):
    return re.fullmatch(r"-?\d+(\.\d+)?", s) is not None


def extract_text_from_stream(data):
    """Interpret a content stream: collect Tj/TJ strings, newline on T*/Td/Tm/'/"."""
    out, stack, cur_array = [], [], None
    for typ, val in _tokenize(data):
        if typ == "str":
            if cur_array is not None:
                cur_array.append(val)
            else:
                stack.append(("str", val))
        elif typ == "op":
            if val == "[":
                cur_array = []
            elif val == "]":
                stack.append(("arr", cur_array or [])); cur_array = None
        elif typ == "tok":
            if cur_array is not None:
                continue  # kerning numbers inside TJ arrays: ignored
            if val == "Tj":
                out.append(_pop_str(stack))
            elif val == "TJ":
                arr = _pop_arr(stack)
                if arr:
                    out.append("".join(x for x in arr if isinstance(x, str)))
            elif val in ("'", '"'):
                out.append("\n"); out.append(_pop_str(stack))
            elif val in ("T*", "Td", "TD", "Tm"):
                out.append("\n")
            elif val == "ET":
                out.append("\n")
    return "".join(out)


_OBJ_RE = re.compile(rb"(\d+)\s+(\d+)\s+obj\b(.*?)endobj", re.S)


def extract_pdf_pages_stdlib(pdf_bytes):
    """Return list of per-page text strings; raise ValueError on failure."""
    if b"/Encrypt" in pdf_bytes:
        raise ValueError("encrypted PDF (dictionary contains /Encrypt)")
    objs = {}
    for m in _OBJ_RE.finditer(pdf_bytes):
        objs[int(m.group(1))] = m.group(3)
    if not objs:
        raise ValueError("no indirect objects found; not a parseable PDF")
    page_ids = []
    for oid, body in objs.items():
        if re.search(rb"/Type\s*/Pages\b", body):
            kids = re.search(rb"/Kids\s*\[(.*?)\]", body, re.S)
            if kids:
                page_ids = [int(x) for x in re.findall(rb"(\d+)\s+\d+\s+R", kids.group(1))]
            break
    if not page_ids:
        page_ids = sorted(
            oid for oid, body in objs.items()
            if re.search(rb"/Type\s*/Page\b", body)
        )
    if not page_ids:
        raise ValueError("no page objects found")
    pages = []
    for pid in page_ids:
        body = objs.get(pid, b"")
        refs = re.findall(rb"(\d+)\s+\d+\s+R",
                          re.search(rb"/Contents\s*(\[.*?\]|\d+\s+\d+\s+R)", body, re.S).group(1)
                          if re.search(rb"/Contents\s*(\[.*?\]|\d+\s+\d+\s+R)", body, re.S) else b"")
        text_parts = []
        for r in refs:
            cbody = objs.get(int(r), b"")
            sm = re.search(rb"stream\r?\n(.*?)\r?\nendstream", cbody, re.S) or \
                 re.search(rb"stream\r?\n(.*?)endstream", cbody, re.S)
            if not sm:
                continue
            data = sm.group(1)
            if re.search(rb"/FlateDecode", cbody):
                data = zlib.decompress(data)
            elif re.search(rb"/Filter", cbody):
                raise ValueError("unsupported content-stream filter (not FlateDecode)")
            text_parts.append(extract_text_from_stream(data))
        pages.append("".join(text_parts))
    return pages


# ---------------------------------------------------------------------------
# poppler path
# ---------------------------------------------------------------------------

def extract_pdf_pages_poppler(path):
    txt = subprocess.run(
        ["pdftotext", "-layout", path, "-"],
        check=True, capture_output=True,
    ).stdout.decode("utf-8", errors="replace")
    pages = txt.split("\f")
    if pages and pages[-1].strip() == "":
        pages = pages[:-1]
    return pages if pages else [""]


# ---------------------------------------------------------------------------
# main inventory logic
# ---------------------------------------------------------------------------

def process_file(path, rel, out_dir, use_poppler):
    with open(path, "rb") as f:
        head = f.read(4096)
    size = os.path.getsize(path)
    digest = sha256_of(path)
    kind = guess_kind(path, head)
    entry = {
        "path": rel,
        "sha256": digest,
        "size_bytes": size,
        "kind": kind,
        "extraction": {
            "method": "none",
            "degraded": False,
            "reason": None,
            "pages": [],
            "pages_file": None,
        },
    }
    pages = None
    if kind == "text":
        try:
            with open(path, "r", encoding="utf-8") as f:
                pages = [f.read()]
            entry["extraction"]["method"] = "plaintext"
        except UnicodeDecodeError as e:
            entry["extraction"]["degraded"] = True
            entry["extraction"]["reason"] = "text file not UTF-8 decodable: %s" % e
    elif kind == "pdf":
        if use_poppler and shutil.which("pdftotext"):
            try:
                pages = extract_pdf_pages_poppler(path)
                entry["extraction"]["method"] = "poppler-pdftotext"
            except subprocess.CalledProcessError as e:
                entry["extraction"]["degraded"] = True
                entry["extraction"]["reason"] = "pdftotext failed: %s" % e.stderr.decode(
                    "utf-8", errors="replace")[:200]
        else:
            try:
                with open(path, "rb") as f:
                    pages = extract_pdf_pages_stdlib(f.read())
                entry["extraction"]["method"] = "stdlib-fallback"
            except Exception as e:  # noqa: BLE001 - degrade, never guess
                entry["extraction"]["degraded"] = True
                entry["extraction"]["reason"] = "stdlib fallback failed: %s" % e
        if pages is not None and sum(len(p.strip()) for p in pages) == 0:
            entry["extraction"]["degraded"] = True
            entry["extraction"]["reason"] = ("zero-length text layer (scanned image or "
                                             "vector-only PDF); OCR is out of scope, "
                                             "content NOT guessed")
    else:
        entry["extraction"]["degraded"] = True
        entry["extraction"]["reason"] = "unsupported binary kind; no text extraction attempted"

    if pages is not None:
        pages_rel = os.path.join("extracted", digest + ".pages.json")
        pages_obj = {
            "file": rel,
            "file_sha256": digest,
            "kind": kind,
            "pages": [{"page": i + 1, "text": t} for i, t in enumerate(pages)],
        }
        with open(os.path.join(out_dir, pages_rel), "w", encoding="utf-8") as f:
            json.dump(pages_obj, f, ensure_ascii=False, indent=2)
        entry["extraction"]["pages_file"] = pages_rel
        entry["extraction"]["pages"] = [
            {"page": i + 1, "char_count": len(t)} for i, t in enumerate(pages)
        ]
    return entry


def main(argv=None):
    ap = argparse.ArgumentParser(description="Inventory input files and extract text layers.")
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--no-poppler", action="store_true",
                    help="force the stdlib fallback extractor even if pdftotext exists")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.input_dir):
        print("usage error: --input-dir %r is not a directory" % args.input_dir, file=sys.stderr)
        return 2
    os.makedirs(os.path.join(args.out_dir, "extracted"), exist_ok=True)

    use_poppler = not args.no_poppler
    entries = []
    for root, dirs, files in os.walk(args.input_dir):
        dirs.sort()
        for name in sorted(files):
            if name.startswith("."):
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, args.input_dir)
            entries.append(process_file(full, rel, args.out_dir, use_poppler))

    inventory = {
        "generated_by": "facsimile_register.py",
        "input_dir": os.path.abspath(args.input_dir),
        "poppler_pdftotext_on_path": bool(shutil.which("pdftotext")),
        "file_count": len(entries),
        "files": entries,
    }
    inv_path = os.path.join(args.out_dir, "facsimile_inventory.json")
    with open(inv_path, "w", encoding="utf-8") as f:
        json.dump(inventory, f, ensure_ascii=False, indent=2)
    degraded = [e["path"] for e in entries if e["extraction"]["degraded"]]
    print("inventory written: %s (%d files, %d degraded)" % (inv_path, len(entries), len(degraded)))
    for d in degraded:
        print("  degraded: %s" % d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
