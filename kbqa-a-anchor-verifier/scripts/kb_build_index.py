#!/usr/bin/env python3
"""kb_build_index.py — inventory the input library and build a hash + line-index.

Deterministic, stdlib-only. Reads the real files under --input; never invents
content. For every file it records: file_id, relative path, size, mtime,
SHA-256, readability, extraction status, and (when possible) a line-numbered
plain-text extraction under the work dir.

Outputs:
  <out>/artifacts/kb_index.json   index of all files + extraction records
  <work>/extracted/<file_id>.txt  extracted plain text (when extractable)
  <out>/result.json               PARTIAL checkpoint skeleton (if case.json exists)

Exit code is always 0; failures are recorded in the index, not raised.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone

TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".jsonl", ".yaml",
    ".yml", ".xml", ".html", ".htm", ".log", ".tex", ".bib", ".ris", ".py",
    ".ini", ".cfg", ".toml", ".r", ".jl", ".sh", ".org", ".rtf",
}


def sha256_of(path, chunk=1 << 20):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for blk in iter(lambda: f.read(chunk), b""):
                h.update(blk)
        return h.hexdigest(), None
    except OSError as e:
        return None, "read_error:%s" % e.__class__.__name__


def extract_pdf(path, dest):
    """pdftotext if available; else mark unavailable. Returns (status, n_lines)."""
    tool = shutil.which("pdftotext")
    if not tool:
        return "extraction_unavailable:pdftotext-missing", 0
    try:
        r = subprocess.run([tool, "-layout", path, dest],
                           capture_output=True, timeout=120)
        if r.returncode != 0 or not os.path.exists(dest):
            return "extraction_failed:pdftotext-rc%d" % r.returncode, 0
        return "ok", sum(1 for _ in open(dest, "r", encoding="utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001 - record, never raise
        return "extraction_error:%s" % e.__class__.__name__, 0


def extract_docx(path, dest):
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
        text = re.sub(r"</w:p>", "\n", xml)
        text = re.sub(r"<[^>]+>", "", text)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(text)
        return "ok", text.count("\n") + 1
    except Exception as e:  # noqa: BLE001
        return "extraction_unavailable:docx:%s" % e.__class__.__name__, 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    a = ap.parse_args()

    ext_dir = os.path.join(a.work, "extracted")
    art_dir = os.path.join(a.out, "artifacts")
    os.makedirs(ext_dir, exist_ok=True)
    os.makedirs(art_dir, exist_ok=True)

    files = []
    skipped = []
    n = 0
    for root, dirs, names in os.walk(a.input, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(names):
            if name.startswith("."):
                continue
            p = os.path.join(root, name)
            rel = os.path.relpath(p, a.input)
            is_meta = (root == a.input and name in ("case.json", "task.md"))
            if is_meta:
                continue  # workorder files are not library material
            n += 1
            fid = "F%03d" % n
            ext = os.path.splitext(name)[1].lower()
            rec = {
                "file_id": fid,
                "path": rel,
                "abs_path": p,
                "name": name,
                "ext": ext,
                "readable": os.access(p, os.R_OK),
                "size": os.path.getsize(p) if os.path.isfile(p) else None,
                "sha256": None,
                "extract_status": "pending",
                "extract_path": None,
                "n_lines": 0,
                "n_chars": 0,
            }
            if not rec["readable"]:
                rec["extract_status"] = "unreadable:no_permission"
                skipped.append({"file_id": fid, "path": rel,
                                "reason": "no_read_permission"})
                files.append(rec)
                continue
            digest, err = sha256_of(p)
            if err:
                rec["extract_status"] = "unreadable:%s" % err
                skipped.append({"file_id": fid, "path": rel, "reason": err})
                files.append(rec)
                continue
            rec["sha256"] = digest
            dest = os.path.join(ext_dir, fid + ".txt")
            if ext == ".pdf":
                st, nl = extract_pdf(p, dest)
            elif ext == ".docx":
                st, nl = extract_docx(p, dest)
            elif ext in TEXT_EXTS:
                try:
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        text = f.read()
                    with open(dest, "w", encoding="utf-8") as f:
                        f.write(text)
                    st, nl = "ok", text.count("\n") + 1
                except Exception as e:  # noqa: BLE001
                    st, nl = "extraction_error:%s" % e.__class__.__name__, 0
            else:
                st, nl = "extraction_unavailable:unsupported_type", 0
            rec["extract_status"] = st
            if st == "ok":
                rec["extract_path"] = dest
                rec["n_lines"] = nl
                rec["n_chars"] = os.path.getsize(dest)
            else:
                skipped.append({"file_id": fid, "path": rel, "reason": st})
            files.append(rec)

    index = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "input_dir": a.input,
        "file_count": len(files),
        "extracted_count": sum(1 for r in files if r["extract_status"] == "ok"),
        "skipped_count": len(skipped),
        "files": files,
        "skipped": skipped,
    }
    with open(os.path.join(art_dir, "kb_index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)

    # partial checkpoint of result.json (only if the case contract is available)
    case_path = os.path.join(a.input, "case.json")
    if os.path.exists(case_path):
        try:
            case = json.load(open(case_path, encoding="utf-8"))
            contract = case.get("output_contract") or {}
            skeleton = {"case_id": case.get("case_id"), "status": "partial",
                        "answers": [], "sources": [], "uncertainty": [],
                        "change_log": ["kb_build_index: indexed %d files, "
                                       "%d extracted, %d skipped"
                                       % (len(files), index["extracted_count"],
                                          len(skipped))],
                        "skipped_files": skipped}
            if isinstance(contract, dict):
                for k, v in contract.items():
                    skeleton.setdefault(k, "" if not isinstance(v, (list, dict)) else v)
            with open(os.path.join(a.out, "result.json"), "w", encoding="utf-8") as f:
                json.dump(skeleton, f, ensure_ascii=False, indent=1)
        except Exception as e:  # noqa: BLE001
            sys.stderr.write("checkpoint skipped: %s\n" % e)

    print("indexed=%d extracted=%d skipped=%d" %
          (len(files), index["extracted_count"], len(skipped)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
