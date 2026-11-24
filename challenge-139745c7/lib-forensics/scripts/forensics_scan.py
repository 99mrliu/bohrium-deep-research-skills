#!/usr/bin/env python3
"""Forensic audit of a document library. Trust nothing upstream.

Per file: sha256, size, mtime, magic-byte true type, extension-vs-content
mismatch, readability, zip encryption flag, PDF text-layer probe, duplicate
grouping, alias candidates. Writes to WORK_DIR:
  inventory.json        every file with verdict and evidence
  FORENSICS_REPORT.md   human-readable audit report
  recovery.jsonl        one line per excluded/quarantined file with recovery note

Usage: forensics_scan.py LIB_ROOT WORK_DIR
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

MAGIC = [
    (b"%PDF", "pdf"),
    (b"PK\x03\x04", "zip-container"),   # docx/xlsx/pptx/zip
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"GIF8", "gif"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "ole-compound"),  # doc/xls/ppt
    (b"{", "json-text?"),
]
TEXT_EXT = {".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".log", ".py", ".tex"}
OFFICE = {".docx": "word/", ".xlsx": "xl/", ".pptx": "ppt/"}
ALIAS_MARKERS = ("副本", "备份", "copy", "backup", "Copy", " - 副本", "（1）", "(1)")


def sniff(path, head):
    for sig, name in MAGIC:
        if head.startswith(sig):
            if name == "zip-container":
                try:
                    import zipfile
                    with zipfile.ZipFile(path) as z:
                        names = z.namelist()
                        for ext, prefix in OFFICE.items():
                            if any(n.startswith(prefix) for n in names):
                                return ext.lstrip(".")
                        return "zip"
                except Exception:
                    return "zip-unreadable"
            return name
    try:
        head.decode("utf-8")
        return "utf8-text"
    except UnicodeDecodeError:
        return "binary-unknown"


def sha256_of(path, limit=None):
    h = hashlib.sha256()
    n = 0
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
            n += len(b)
            if limit and n >= limit:
                break
    return h.hexdigest()


def zip_encrypted(path):
    try:
        import zipfile
        with zipfile.ZipFile(path) as z:
            return any(i.flag_bits & 0x1 for i in z.infolist())
    except Exception:
        return None


def pdf_text_probe(path):
    exe = shutil.which("pdftotext")
    if not exe:
        return "unavailable"
    try:
        p = subprocess.run([exe, "-l", "2", path, "-"], capture_output=True,
                           timeout=60)
        if p.returncode != 0:
            return "pdftotext_failed"
        return "has_text" if p.stdout.strip() else "needs_ocr"
    except Exception as e:
        return "probe_error: %s" % e


def norm_base(name):
    base = os.path.splitext(name)[0].lower()
    for m in ALIAS_MARKERS:
        base = base.replace(m.lower(), "")
    return base.strip("_- .（）()")


def main():
    lib_root, work = sys.argv[1], sys.argv[2]
    os.makedirs(work, exist_ok=True)
    files = []
    recovery = []
    for base, dirs, names in os.walk(lib_root):
        dirs.sort()
        for name in sorted(names):
            path = os.path.join(base, name)
            rel = os.path.relpath(path, lib_root)
            rec = {"path": rel, "size": None, "sha256": None,
                   "mtime": None, "ext": os.path.splitext(name)[1].lower(),
                   "status": "verified", "issues": []}
            try:
                st = os.stat(path)
                rec["size"] = st.st_size
                rec["mtime"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(st.st_mtime))
            except OSError as e:
                rec["status"] = "unreadable"
                rec["issues"].append("stat_failed: %s" % e)
                files.append(rec)
                recovery.append({"path": rel, "action": "quarantined",
                                 "reason": rec["issues"][-1],
                                 "recovery": "check filesystem permission; rerun audit after fix"})
                continue
            try:
                with open(path, "rb") as f:
                    head = f.read(4096)
            except OSError as e:
                rec["status"] = "unreadable"
                rec["issues"].append("read_failed: %s" % e)
                files.append(rec)
                recovery.append({"path": rel, "action": "quarantined",
                                 "reason": rec["issues"][-1],
                                 "recovery": "chmod/chown then rerun audit"})
                continue
            rec["sha256"] = sha256_of(path)
            true_type = sniff(path, head)
            rec["true_type"] = true_type
            ext_map = {".pdf": "pdf", ".png": "png", ".jpg": "jpeg",
                       ".jpeg": "jpeg", ".gif": "gif", ".zip": "zip",
                       ".docx": "docx", ".xlsx": "xlsx", ".pptx": "pptx",
                       ".doc": "ole-compound", ".xls": "ole-compound"}
            want = ext_map.get(rec["ext"])
            if want and true_type != want:
                rec["issues"].append("type_mismatch: ext=%s true=%s" % (rec["ext"], true_type))
                rec["status"] = "suspect"
            if not want and true_type not in ("utf8-text", "json-text?") \
                    and rec["ext"] not in TEXT_EXT:
                rec["issues"].append("unrecognized: ext=%s true=%s" % (rec["ext"], true_type))
                rec["status"] = "suspect"
            if true_type in ("zip", "docx", "xlsx", "pptx"):
                enc = zip_encrypted(path)
                if enc:
                    rec["status"] = "encrypted"
                    rec["issues"].append("zip_encrypted")
            if true_type == "pdf":
                rec["pdf_text_probe"] = pdf_text_probe(path)
            if true_type == "binary-unknown":
                rec["status"] = "unrecognized"
            if any(m in name for m in ALIAS_MARKERS):
                rec["issues"].append("alias_marker_in_name")
            rec["norm_base"] = norm_base(name)
            files.append(rec)
            if rec["status"] != "verified":
                recovery.append({"path": rel, "action": "flagged",
                                 "reason": "; ".join(rec["issues"]),
                                 "recovery": "inspect manually; excluded from answer evidence"})

    by_hash = {}
    for r in files:
        if r.get("sha256"):
            by_hash.setdefault(r["sha256"], []).append(r)
    for digest, group in by_hash.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: (any(m in r["path"] for m in ALIAS_MARKERS), r["path"]))
        canonical = group[0]
        for r in group:
            r["duplicate_group"] = digest[:16]
            r["canonical"] = (r is canonical)
            if r is not canonical:
                r["status"] = "duplicate"
                r["issues"].append("exact_copy_of: %s" % canonical["path"])
                recovery.append({"path": r["path"], "action": "deduplicated",
                                 "reason": "sha256 identical to %s" % canonical["path"],
                                 "recovery": "no data loss; canonical retained"})

    inv = {"library_root": os.path.abspath(lib_root),
           "audited_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "n_files": len(files),
           "n_verified": sum(1 for r in files if r["status"] == "verified"),
           "files": files}
    with open(os.path.join(work, "inventory.json"), "w", encoding="utf-8") as f:
        json.dump(inv, f, ensure_ascii=False, indent=2)
    with open(os.path.join(work, "recovery.jsonl"), "w", encoding="utf-8") as f:
        for r in recovery:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    lines = ["# 文档库法医审计报告（lib-forensics）", "",
             "- 库根目录：`%s`" % inv["library_root"],
             "- 文件总数：%d；通过审计：%d；被标记/隔离：%d" % (
                 inv["n_files"], inv["n_verified"], inv["n_files"] - inv["n_verified"]), "",
             "| 文件 | 真实类型 | sha256(前16) | 状态 | 问题 |", "|---|---|---|---|---|"]
    for r in files:
        lines.append("| %s | %s | %s | %s | %s |" % (
            r["path"], r.get("true_type", "?"), (r.get("sha256") or "-")[:16],
            r["status"], "; ".join(r["issues"]) or "-"))
    lines += ["", "被标记/隔离文件的全部恢复记录见 recovery.jsonl。"]
    with open(os.path.join(work, "FORENSICS_REPORT.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(json.dumps({"n_files": inv["n_files"], "n_verified": inv["n_verified"],
                      "n_flagged": inv["n_files"] - inv["n_verified"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
