#!/usr/bin/env python3
"""forensic_scan.py — 上游数据真实性取证扫描（bundle 1 核心脚本，确定性，stdlib-only）。

对输入资料库逐文件取证：SHA-256、大小、mtime、类型、可读性、文本抽取状态，
识别字节级重复（同哈希）与不可读文件，生成机器可核验的编目 catalog.json。
编目是后续一切问答/版本判断的唯一事实来源（gold basis）。

退出码：永远为 0（灾难性错误也写入 catalog 的 fatal 字段），绝不因单个文件失败而崩溃。
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

TEXT_SUFFIX = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".jsonl",
               ".xml", ".yaml", ".yml", ".log", ".tex", ".bib", ".rst", ".py",
               ".sh", ".html", ".htm", ".ini", ".cfg", ".conf"}
PDF_SUFFIX = {".pdf"}
SKIP_NAMES = {"case.json", "task.md"}  # 任务说明文件不是库材料
MAX_TEXT_CHARS = 2_000_000


def sha256_of(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def extract_text(path, suffix, extracted_path):
    """返回 (status, n_lines)。status ∈ ok / unreadable / no_text_layer /
    unsupported_type / extraction_tool_missing / extraction_failed / empty"""
    try:
        if suffix in TEXT_SUFFIX:
            with open(path, "rb") as f:
                raw = f.read(MAX_TEXT_CHARS + 1)
            text = raw.decode("utf-8", errors="replace")
        elif suffix in PDF_SUFFIX:
            if not shutil.which("pdftotext"):
                return "extraction_tool_missing", 0
            tmp = extracted_path + ".raw"
            r = subprocess.run(["pdftotext", "-layout", path, tmp],
                               capture_output=True, timeout=120)
            if r.returncode != 0 or not os.path.exists(tmp):
                return "extraction_failed", 0
            with open(tmp, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            os.remove(tmp)
            if not text.strip():
                return "no_text_layer", 0
        else:
            return "unsupported_type", 0
    except PermissionError:
        return "unreadable", 0
    except (OSError, subprocess.TimeoutExpired):
        return "unreadable", 0
    lines = text.splitlines()
    if not any(l.strip() for l in lines):
        return "empty", 0
    numbered = "".join("L%d: %s\n" % (i + 1, l) for i, l in enumerate(lines))
    with open(extracted_path, "w", encoding="utf-8") as f:
        f.write(numbered)
    return "ok", len(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    os.makedirs(a.out, exist_ok=True)
    ext_dir = os.path.join(a.work, "extracted")
    os.makedirs(ext_dir, exist_ok=True)

    catalog = {
        "schema": "kbqa-ingest-forensics/catalog/v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "input_root": os.path.abspath(a.input),
        "files": [], "byte_duplicate_groups": [], "skipped": [],
        "stats": {}, "fatal": None,
    }
    input_root = os.path.abspath(a.input)
    files = []
    try:
        for root, dirs, names in os.walk(input_root):
            dirs.sort()
            for n in sorted(names):
                if n in SKIP_NAMES and os.path.abspath(root) == input_root:
                    continue
                if n.startswith("."):
                    continue
                p = os.path.join(root, n)
                if os.path.islink(p) or not os.path.isfile(p):
                    catalog["skipped"].append(
                        {"path": os.path.relpath(p, a.input),
                         "reason": "symlink_or_not_regular_file"})
                    continue
                files.append(p)
    except OSError as e:
        catalog["fatal"] = "walk_failed: %s" % e

    by_hash = {}
    for i, p in enumerate(files):
        rel = os.path.relpath(p, a.input)
        fid = "F%03d" % (i + 1)
        entry = {"file_id": fid, "relpath": rel, "suffix": os.path.splitext(p)[1].lower(),
                 "size": None, "mtime": None, "sha256": None,
                 "text_status": None, "n_lines": 0, "extracted": None,
                 "byte_duplicate_of": None}
        try:
            st = os.stat(p)
            entry["size"] = st.st_size
            entry["mtime"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime))
            entry["sha256"] = sha256_of(p)
        except (OSError, PermissionError) as e:
            entry["text_status"] = "unreadable"
            entry["error"] = str(e)
            catalog["files"].append(entry)
            continue
        ext_path = os.path.join(ext_dir, fid + ".txt")
        status, nlines = extract_text(p, entry["suffix"], ext_path)
        entry["text_status"] = status
        entry["n_lines"] = nlines
        if status == "ok":
            entry["extracted"] = os.path.relpath(ext_path, a.work)
        if entry["sha256"] in by_hash:
            entry["byte_duplicate_of"] = by_hash[entry["sha256"]]
        else:
            by_hash[entry["sha256"]] = fid
        catalog["files"].append(entry)

    groups = {}
    for e in catalog["files"]:
        if e["sha256"]:
            groups.setdefault(e["sha256"], []).append(e["file_id"])
    catalog["byte_duplicate_groups"] = [
        {"sha256": h, "members": sorted(m)} for h, m in sorted(groups.items()) if len(m) > 1]
    st = {}
    for e in catalog["files"]:
        st[e["text_status"] or "unknown"] = st.get(e["text_status"] or "unknown", 0) + 1
    st["total_files"] = len(catalog["files"])
    st["unique_contents"] = len(groups)
    catalog["stats"] = st

    for dest in (os.path.join(a.work, "catalog.json"), os.path.join(a.out, "catalog.json")):
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(catalog, f, ensure_ascii=False, indent=2)
    print(json.dumps({"files": len(catalog["files"]),
                      "unique_contents": len(groups),
                      "byte_duplicate_groups": len(catalog["byte_duplicate_groups"]),
                      "skipped": len(catalog["skipped"]),
                      "stats": st}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
