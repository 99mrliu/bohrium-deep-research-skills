#!/usr/bin/env python3
"""render_scan.py — 交接渲染第 1 步：轻量编目 + 问题解析 + 保底骨架（确定性）。

为下游渲染准备素材：编目（file_id、路径、哈希、类型、可读性、行号化文本）、
版本角色粗判（同哈希副本、文件名版本标记）、case.json 的问题与
output_contract，并立即落保底 result.json。
退出码恒 0。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

TEXT_SUFFIX = {".txt", ".md", ".csv", ".tsv", ".json", ".log", ".tex", ".rst",
               ".markdown", ".xml", ".yaml", ".yml", ".bib"}
SKIP_NAMES = {"case.json", "task.md"}
VER_PAT = re.compile(r"(?i)(?:^|[_\-\s\(])v(\d+(?:\.\d+)*)")


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


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

    try:
        with open(os.path.join(a.input, "case.json"), encoding="utf-8") as f:
            case = json.load(f)
    except (OSError, json.JSONDecodeError):
        case = {}
    questions = []
    for k in ("questions", "searches", "queries", "tasks", "items"):
        v = case.get(k)
        if isinstance(v, list) and v:
            for i, it in enumerate(v, 1):
                if isinstance(it, dict):
                    questions.append({"question_id": str(it.get("question_id") or it.get("id") or "q%d" % i),
                                      "question": str(it.get("question") or it.get("query") or it.get("task") or "")})
                else:
                    questions.append({"question_id": "q%d" % i, "question": str(it)})
            break
    contract = case.get("output_contract") or {}
    fields = contract.get("fields") if isinstance(contract, dict) else None
    if not fields and isinstance(contract, dict):
        fields = list(contract.keys())
    fields = [f for f in (fields or []) if f != "fields"]

    entries, by_hash = [], {}
    i = 0
    input_root = os.path.abspath(a.input)
    for root, dirs, names in os.walk(input_root):
        dirs.sort()
        for n in sorted(names):
            if n.startswith(".") or (n in SKIP_NAMES and os.path.abspath(root) == input_root):
                continue
            p = os.path.join(root, n)
            if os.path.islink(p) or not os.path.isfile(p):
                continue
            i += 1
            fid = "F%03d" % i
            suffix = os.path.splitext(p)[1].lower()
            e = {"file_id": fid, "relpath": os.path.relpath(p, input_root),
                 "suffix": suffix, "sha256": None, "size": None,
                 "text_status": None, "n_lines": 0, "extracted": None,
                 "duplicate_of": None, "version_tag": None}
            try:
                st = os.stat(p)
                e["size"] = st.st_size
                e["sha256"] = sha256_of(p)
            except OSError:
                e["text_status"] = "unreadable"
                entries.append(e)
                continue
            m = VER_PAT.search(os.path.basename(p))
            if m:
                e["version_tag"] = "v" + m.group(1)
            text = None
            try:
                if suffix in TEXT_SUFFIX:
                    with open(p, "rb") as f:
                        text = f.read(2_000_000).decode("utf-8", errors="replace")
                elif suffix == ".pdf" and shutil.which("pdftotext"):
                    tmp = os.path.join(ext_dir, fid + ".raw")
                    r = subprocess.run(["pdftotext", "-layout", p, tmp],
                                       capture_output=True, timeout=120)
                    if r.returncode == 0 and os.path.exists(tmp):
                        with open(tmp, encoding="utf-8", errors="replace") as f:
                            text = f.read()
                        os.remove(tmp)
            except (OSError, subprocess.TimeoutExpired):
                pass
            if text is None:
                e["text_status"] = "unreadable" if suffix in TEXT_SUFFIX or suffix == ".pdf" \
                    else "unsupported_type"
            elif not text.strip():
                e["text_status"] = "empty"
            else:
                lines = text.splitlines()
                xp = os.path.join(ext_dir, fid + ".txt")
                with open(xp, "w", encoding="utf-8") as f:
                    f.write("".join("L%d: %s\n" % (k + 1, l) for k, l in enumerate(lines)))
                e.update(text_status="ok", n_lines=len(lines),
                         extracted=os.path.relpath(xp, a.work))
            if e["sha256"] in by_hash:
                e["duplicate_of"] = by_hash[e["sha256"]]
            else:
                by_hash[e["sha256"]] = fid
            entries.append(e)

    catalog = {"schema": "kbqa-kb-renderer/catalog/v1",
               "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "files": entries}
    with open(os.path.join(a.work, "render_catalog.json"), "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    with open(os.path.join(a.work, "questions.json"), "w", encoding="utf-8") as f:
        json.dump({"questions": questions, "output_contract_fields": fields},
                  f, ensure_ascii=False, indent=2)
    skeleton = {"case_id": case.get("case_id") or case.get("id") or "unknown",
                "status": "partial",
                "answers": [{"question_id": q["question_id"], "answer": None}
                            for q in questions],
                "sources": [], "uncertainty": ["skeleton at init"], "change_log": []}
    for fld in fields:
        skeleton.setdefault(fld, None)
    with open(os.path.join(a.out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(skeleton, f, ensure_ascii=False, indent=2)
    print(json.dumps({"files": len(entries), "questions": len(questions),
                      "ok": sum(1 for e in entries if e["text_status"] == "ok")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
