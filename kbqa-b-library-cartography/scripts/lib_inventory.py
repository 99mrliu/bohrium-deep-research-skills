#!/usr/bin/env python3
"""lib_inventory.py — byte-level inventory of the input library.

Deterministic, stdlib-only. For every file: relative path, size, mtime,
SHA-256, extension/type, read permission, and (when possible) a plain-text
extraction under the work dir. Emits inventory.json plus a partial
result.json checkpoint when the case contract is available.

Exit code is always 0; per-file failures are recorded, never raised.
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

TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".jsonl", ".yaml",
    ".yml", ".xml", ".html", ".htm", ".log", ".tex", ".bib", ".ris", ".py",
    ".ini", ".cfg", ".toml", ".r", ".jl", ".sh", ".org",
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


def extract(p, ext, dest):
    """Returns (status, n_lines)."""
    if ext == ".pdf":
        tool = shutil.which("pdftotext")
        if not tool:
            return "text_unavailable:pdftotext-missing", 0
        try:
            r = subprocess.run([tool, "-layout", p, dest],
                               capture_output=True, timeout=120)
            if r.returncode != 0 or not os.path.exists(dest):
                return "text_unavailable:pdftotext-rc%d" % r.returncode, 0
            with open(dest, encoding="utf-8", errors="replace") as f:
                return "ok", sum(1 for _ in f)
        except Exception as e:  # noqa: BLE001
            return "text_unavailable:%s" % e.__class__.__name__, 0
    if ext == ".docx":
        try:
            with zipfile.ZipFile(p) as z:
                xml = z.read("word/document.xml").decode("utf-8", errors="replace")
            text = re.sub(r"</w:p>", "\n", xml)
            text = re.sub(r"<[^>]+>", "", text)
            with open(dest, "w", encoding="utf-8") as f:
                f.write(text)
            return "ok", text.count("\n") + 1
        except Exception as e:  # noqa: BLE001
            return "text_unavailable:docx:%s" % e.__class__.__name__, 0
    if ext in TEXT_EXTS:
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            with open(dest, "w", encoding="utf-8") as f:
                f.write(text)
            return "ok", text.count("\n") + 1
        except Exception as e:  # noqa: BLE001
            return "text_unavailable:%s" % e.__class__.__name__, 0
    return "text_unavailable:unsupported_type", 0


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

    files, skipped = [], []
    n = 0
    for root, dirs, names in os.walk(a.input, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(names):
            if name.startswith("."):
                continue
            p = os.path.join(root, name)
            rel = os.path.relpath(p, a.input)
            if root == a.input and name in ("case.json", "task.md"):
                continue  # workorder files are not library material
            n += 1
            ext = os.path.splitext(name)[1].lower()
            rec = {"entry_id": "E%03d" % n, "path": rel, "name": name,
                   "ext": ext, "size": None, "mtime": None, "sha256": None,
                   "readable": os.access(p, os.R_OK),
                   "extract_status": "pending", "extract_path": None,
                   "n_lines": 0}
            try:
                st = os.stat(p)
                rec["size"], rec["mtime"] = st.st_size, st.st_mtime
            except OSError as e:
                rec["size"], rec["mtime"] = None, None
            if not rec["readable"]:
                rec["extract_status"] = "no_permission"
                skipped.append({"entry_id": rec["entry_id"], "path": rel,
                                "reason": "no_read_permission"})
                files.append(rec)
                continue
            digest, err = sha256_of(p)
            if err:
                rec["extract_status"] = err
                skipped.append({"entry_id": rec["entry_id"], "path": rel,
                                "reason": err})
                files.append(rec)
                continue
            rec["sha256"] = digest
            dest = os.path.join(ext_dir, rec["entry_id"] + ".txt")
            stt, nl = extract(p, ext, dest)
            rec["extract_status"] = stt
            if stt == "ok":
                rec["extract_path"], rec["n_lines"] = dest, nl
            else:
                skipped.append({"entry_id": rec["entry_id"], "path": rel,
                                "reason": stt})
            files.append(rec)

    inv = {"input_dir": a.input, "file_count": len(files),
           "extracted_count": sum(1 for r in files if r["extract_status"] == "ok"),
           "skipped": skipped, "files": files}
    with open(os.path.join(art_dir, "inventory.json"), "w", encoding="utf-8") as f:
        json.dump(inv, f, ensure_ascii=False, indent=1)

    case_path = os.path.join(a.input, "case.json")
    if os.path.exists(case_path):
        try:
            case = json.load(open(case_path, encoding="utf-8"))
            contract = case.get("output_contract") or {}
            skeleton = {"case_id": case.get("case_id"), "status": "partial",
                        "catalog_summary": {}, "answers": [],
                        "sources": [], "uncertainty": [],
                        "change_log": ["lib_inventory: %d files, %d extracted, "
                                       "%d skipped"
                                       % (len(files), inv["extracted_count"],
                                          len(skipped))],
                        "skipped_files": skipped}
            if isinstance(contract, dict):
                for k in contract:
                    skeleton.setdefault(k, [] if "list" in str(type(contract[k]))
                                        else "")
            with open(os.path.join(a.out, "result.json"), "w", encoding="utf-8") as f:
                json.dump(skeleton, f, ensure_ascii=False, indent=1)
        except Exception as e:  # noqa: BLE001
            sys.stderr.write("checkpoint skipped: %s\n" % e)

    print("inventory files=%d extracted=%d skipped=%d"
          % (len(files), inv["extracted_count"], len(skipped)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
