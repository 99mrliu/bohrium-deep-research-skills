#!/usr/bin/env python3
"""suff_index.py — inventory + text extraction for the sufficiency workflow.

Deterministic, stdlib-only. Emits <out>/artifacts/suff_index.json with per-file
record: doc_id, path, sha256, size, mtime, readable, extract_status, and a
plain-text extraction under <work>/extracted/<doc_id>.txt when possible.

Unreadable/unextractable files are kept in the index (marked) and in
`inaccessible` — they may still be *relevant* to a question, which maps to
the INACCESSIBLE verdict. Exit code always 0.
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
    ".ini", ".cfg", ".toml", ".sh", ".org",
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
    if ext == ".pdf":
        tool = shutil.which("pdftotext")
        if not tool:
            return "unavailable:pdftotext-missing", 0
        try:
            r = subprocess.run([tool, "-layout", p, dest],
                               capture_output=True, timeout=120)
            if r.returncode != 0 or not os.path.exists(dest):
                return "unavailable:pdftotext-rc%d" % r.returncode, 0
            with open(dest, encoding="utf-8", errors="replace") as f:
                return "ok", sum(1 for _ in f)
        except Exception as e:  # noqa: BLE001
            return "unavailable:%s" % e.__class__.__name__, 0
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
            return "unavailable:docx:%s" % e.__class__.__name__, 0
    if ext in TEXT_EXTS:
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            with open(dest, "w", encoding="utf-8") as f:
                f.write(text)
            return "ok", text.count("\n") + 1
        except Exception as e:  # noqa: BLE001
            return "unavailable:%s" % e.__class__.__name__, 0
    return "unavailable:unsupported_type", 0


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

    docs, inaccessible = [], []
    n = 0
    for root, dirs, names in os.walk(a.input, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(names):
            if name.startswith("."):
                continue
            p = os.path.join(root, name)
            rel = os.path.relpath(p, a.input)
            if root == a.input and name in ("case.json", "task.md"):
                continue
            n += 1
            ext = os.path.splitext(name)[1].lower()
            rec = {"doc_id": "D%03d" % n, "path": rel, "name": name, "ext": ext,
                   "size": None, "mtime": None, "sha256": None,
                   "readable": os.access(p, os.R_OK),
                   "extract_status": "pending", "extract_path": None,
                   "n_lines": 0}
            try:
                st = os.stat(p)
                rec["size"], rec["mtime"] = st.st_size, st.st_mtime
            except OSError:
                pass
            if not rec["readable"]:
                rec["extract_status"] = "no_permission"
            else:
                digest, err = sha256_of(p)
                if err:
                    rec["extract_status"] = err
                else:
                    rec["sha256"] = digest
                    dest = os.path.join(ext_dir, rec["doc_id"] + ".txt")
                    stt, nl = extract(p, ext, dest)
                    rec["extract_status"] = stt
                    if stt == "ok":
                        rec["extract_path"], rec["n_lines"] = dest, nl
            if rec["extract_status"] != "ok":
                inaccessible.append({"doc_id": rec["doc_id"], "path": rel,
                                     "name": name, "reason": rec["extract_status"]})
            docs.append(rec)

    index = {"input_dir": a.input, "doc_count": len(docs),
             "extracted_count": sum(1 for d in docs if d["extract_status"] == "ok"),
             "docs": docs, "inaccessible": inaccessible}
    with open(os.path.join(art_dir, "suff_index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)

    case_path = os.path.join(a.input, "case.json")
    if os.path.exists(case_path):
        try:
            case = json.load(open(case_path, encoding="utf-8"))
            contract = case.get("output_contract") or {}
            skeleton = {"case_id": case.get("case_id"), "status": "partial",
                        "answers": [], "sources": [], "uncertainty": [],
                        "change_log": ["suff_index: %d docs, %d extracted, "
                                       "%d inaccessible"
                                       % (len(docs), index["extracted_count"],
                                          len(inaccessible))],
                        "skipped_files": inaccessible}
            if isinstance(contract, dict):
                for k in contract:
                    skeleton.setdefault(k, [] if isinstance(contract[k], (list, dict)) else "")
            with open(os.path.join(a.out, "result.json"), "w", encoding="utf-8") as f:
                json.dump(skeleton, f, ensure_ascii=False, indent=1)
        except Exception as e:  # noqa: BLE001
            sys.stderr.write("checkpoint skipped: %s\n" % e)

    print("index docs=%d extracted=%d inaccessible=%d"
          % (len(docs), index["extracted_count"], len(inaccessible)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
