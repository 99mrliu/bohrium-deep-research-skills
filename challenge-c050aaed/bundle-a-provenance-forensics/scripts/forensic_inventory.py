#!/usr/bin/env python3
"""Forensic inventory of a materials directory.

Walks a directory and emits a deterministic JSON manifest recording, per file:
relpath, sha256, size, mtime, permission bits, readability, magic-byte sniff
vs. extension mismatch flag, PDF /Encrypt detection, and an empty-file flag.
Also groups byte-identical duplicates and clusters version-suspect files
(same normalized name stem, different content hash).

Determinism: no wall-clock timestamps are emitted; files are sorted by
relpath. mtime values come from the input files themselves.

Exit codes: 0 success, 2 usage error, 3 verification/processing failure.
Python 3 standard library only.
"""

import argparse
import hashlib
import json
import os
import re
import stat
import sys

TOOL_VERSION = "1.0.0"
GENERATED_BY = "provenance-forensics/scripts/forensic_inventory.py"

# How many leading bytes to scan for a raw "/Encrypt" marker in PDFs.
ENCRYPT_SCAN_BYTES = 65536
# How many leading bytes to use for magic-byte sniffing.
SNIFF_BYTES = 8192

# Extension -> expected sniffed type. Extensions not listed are not checked.
EXT_EXPECTED = {
    ".pdf": "pdf",
    ".zip": "zip",
    ".png": "png",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".txt": "utf8_text",
    ".md": "utf8_text",
    ".json": "utf8_text",
    ".csv": "utf8_text",
}


def sniff_magic(head):
    """Classify leading bytes into a small set of content types."""
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"PK\x03\x04"):
        return "zip"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    try:
        head.decode("utf-8")
        return "utf8_text"
    except UnicodeDecodeError:
        return "binary_unknown"


def sha256_of(path, block=1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(block)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


_TRAIL_PAT = re.compile(
    r"(?:\s*\(\d+\)|\s+copy|[-_]v\d+)$"
)
_WS_PAT = re.compile(r"\s+")


def normalize_stem(relpath):
    """Normalize a file's name stem for version-suspect clustering.

    Strips the extension, then repeatedly strips trailing markers such as
    ' (1)', ' (2024)', ' copy', '-v2', '_v10'; collapses whitespace; lowercases.
    """
    base = os.path.basename(relpath)
    stem = os.path.splitext(base)[0]
    s = _WS_PAT.sub(" ", stem.strip().lower())
    while True:
        new = _TRAIL_PAT.sub("", s).strip()
        if new == s:
            break
        s = new
    return s


def inspect_file(root, relpath, out_abs=None):
    """Build the manifest record for one file. Never raises."""
    abspath = os.path.join(root, relpath)
    rec = {
        "relpath": relpath,
        "sha256": None,
        "size": None,
        "mtime": None,
        "mode": None,
        "readable": False,
        "sniffed": None,
        "extension": os.path.splitext(relpath)[1].lower(),
        "extension_mismatch": False,
        "pdf_encrypted": False,
        "empty": False,
        "classification": None,
        "error": None,
    }
    try:
        st = os.stat(abspath)
        rec["size"] = st.st_size
        rec["mtime"] = st.st_mtime
        rec["mode"] = format(stat.S_IMODE(st.st_mode), "04o")
    except PermissionError as e:
        rec["classification"] = "permission_denied"
        rec["error"] = "stat: " + str(e)
        return rec
    except OSError as e:
        rec["classification"] = "unreadable"
        rec["error"] = "stat: " + str(e)
        return rec

    if out_abs and os.path.abspath(abspath) == out_abs:
        # Never include our own output manifest in the inventory.
        return None

    head = b""
    try:
        with open(abspath, "rb") as f:
            head = f.read(max(SNIFF_BYTES, ENCRYPT_SCAN_BYTES))
        rec["readable"] = True
    except PermissionError as e:
        rec["classification"] = "permission_denied"
        rec["error"] = "read: " + str(e)
        return rec
    except OSError as e:
        rec["classification"] = "unreadable"
        rec["error"] = "read: " + str(e)
        return rec

    rec["empty"] = rec["size"] == 0
    if rec["empty"]:
        rec["sha256"] = sha256_of(abspath)
        rec["sniffed"] = "empty"
        rec["classification"] = "empty"
        return rec

    rec["sha256"] = sha256_of(abspath)
    sniffed = sniff_magic(head[:SNIFF_BYTES])
    rec["sniffed"] = sniffed

    if sniffed == "pdf":
        rec["pdf_encrypted"] = b"/Encrypt" in head[:ENCRYPT_SCAN_BYTES]

    expected = EXT_EXPECTED.get(rec["extension"])
    if expected is not None and sniffed != expected:
        rec["extension_mismatch"] = True

    if rec["pdf_encrypted"]:
        rec["classification"] = "encrypted"
    elif rec["extension_mismatch"]:
        rec["classification"] = "mismatched_extension"
    else:
        rec["classification"] = "readable"
    return rec


def build_inventory(root, out_path=None):
    """Walk root and build the manifest dict. Deterministic ordering."""
    out_abs = os.path.abspath(out_path) if out_path else None
    relpaths = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in filenames:
            abspath = os.path.join(dirpath, name)
            rel = os.path.relpath(abspath, root)
            relpaths.append(rel)
    relpaths.sort()

    files = []
    for rel in relpaths:
        rec = inspect_file(root, rel, out_abs=out_abs)
        if rec is not None:
            files.append(rec)

    # Byte-identical duplicate groups (same sha256, >= 2 members).
    by_hash = {}
    for rec in files:
        if rec["sha256"] is not None:
            by_hash.setdefault(rec["sha256"], []).append(rec["relpath"])
    duplicate_groups = []
    for h, members in by_hash.items():
        if len(members) >= 2:
            duplicate_groups.append({
                "sha256": h,
                "size": next(r["size"] for r in files if r["sha256"] == h),
                "members": sorted(members),
            })
    duplicate_groups.sort(key=lambda g: g["members"][0])

    # Version-suspect clusters: same normalized stem, >= 2 distinct hashes.
    by_stem = {}
    for rec in files:
        by_stem.setdefault(normalize_stem(rec["relpath"]), []).append(rec)
    version_suspect_groups = []
    for stem, recs in by_stem.items():
        hashes = {r["sha256"] for r in recs if r["sha256"] is not None}
        if len(recs) >= 2 and len(hashes) >= 2:
            members = [
                {"relpath": r["relpath"], "sha256": r["sha256"]}
                for r in sorted(recs, key=lambda r: r["relpath"])
            ]
            version_suspect_groups.append({
                "normalized_stem": stem,
                "members": members,
            })
    version_suspect_groups.sort(key=lambda g: g["normalized_stem"])

    classification_counts = {}
    for rec in files:
        classification_counts[rec["classification"]] = (
            classification_counts.get(rec["classification"], 0) + 1
        )

    manifest = {
        "generated_by": GENERATED_BY,
        "tool_version": TOOL_VERSION,
        "root": os.path.abspath(root),
        "files": files,
        "duplicate_groups": duplicate_groups,
        "version_suspect_groups": version_suspect_groups,
        "summary": {
            "total_files": len(files),
            "classification_counts": dict(sorted(classification_counts.items())),
            "duplicate_groups": len(duplicate_groups),
            "version_suspect_groups": len(version_suspect_groups),
            "encrypted_files": sum(1 for r in files if r["pdf_encrypted"]),
            "empty_files": sum(1 for r in files if r["empty"]),
            "extension_mismatch_files": sum(
                1 for r in files if r["extension_mismatch"]
            ),
            "unreadable_or_denied_files": sum(
                1 for r in files
                if r["classification"] in ("unreadable", "permission_denied")
            ),
        },
    }
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build a tamper-evident forensic inventory manifest of a "
                    "materials directory (sha256, magic sniff, PDF /Encrypt "
                    "detection, duplicates, version suspects)."
    )
    parser.add_argument("--dir", required=True,
                        help="Materials directory to inventory.")
    parser.add_argument("--out", required=True,
                        help="Path to write the JSON manifest.")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.dir):
        print("error: not a directory: %s" % args.dir, file=sys.stderr)
        return 2

    manifest = build_inventory(args.dir, out_path=args.out)
    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")

    s = manifest["summary"]
    print("inventory written: %s" % args.out)
    print("total_files=%d readable=%d encrypted=%d empty=%d "
          "mismatched_extension=%d unreadable_or_denied=%d "
          "duplicate_groups=%d version_suspect_groups=%d" % (
              s["total_files"],
              s["classification_counts"].get("readable", 0),
              s["encrypted_files"],
              s["empty_files"],
              s["extension_mismatch_files"],
              s["unreadable_or_denied_files"],
              s["duplicate_groups"],
              s["version_suspect_groups"],
          ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
