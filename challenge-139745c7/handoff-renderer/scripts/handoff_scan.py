#!/usr/bin/env python3
"""Scan the library and answer case questions (deliberately simple: the
center of gravity of this skill is the handoff package, not recall).

Writes to WORK_DIR: scan.json (per-file metadata + version tags),
answers.json (keyword answers or honest no_match).

Usage: handoff_scan.py CASE_JSON WORK_DIR
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

LIB_KEYS = ["library", "library_root", "data_dir", "files_dir", "root",
            "documents_dir", "doc_root", "materials", "corpus"]
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]{1,}|[一-鿿]+")
STOP = set("的了和是在有与及或其对这那中上个一为以于哪些哪个什么哪份")
VERSION_WORDS = ["终稿", "正式版", "定稿", "修订", "初稿", "草稿",
                 "final", "revised", "draft"]
VNUM = re.compile(r"[vV](\d+)")


def tokens(text):
    out = []
    for t in TOKEN.findall(text or ""):
        t = t.lower()
        if re.match(r"^[a-z0-9]", t):
            if len(t) > 1 and t not in STOP:
                out.append(t)
        else:
            run = "".join(c for c in t if c not in STOP)
            out.extend(run[i:i + 2] for i in range(len(run) - 1))
    return out


def find_root(case, case_dir):
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if str(k).lower() in LIB_KEYS and isinstance(v, str):
                    yield v
                yield from walk(v)
        elif isinstance(o, list):
            for v in o:
                yield from walk(v)
    for v in walk(case):
        for p in (v, os.path.join("/input", v), os.path.join(case_dir, v)):
            if p and os.path.isdir(p):
                return os.path.abspath(p)
    return None


def find_questions(case):
    for key in ("searches", "questions", "queries", "tasks"):
        v = case.get(key)
        if isinstance(v, list) and v:
            return [q if isinstance(q, dict) else {"id": "q%d" % i, "text": str(q)}
                    for i, q in enumerate(v)]
        if isinstance(v, str):
            return [{"id": "q0", "text": v}]
    return []


def version_tag(name):
    for w in VERSION_WORDS:
        if w in name:
            return w
    m = VNUM.search(name)
    return ("v" + m.group(1)) if m else ""


def extract_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md", ".csv", ".tsv", ".log", ".json", ".tex"):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return ""
    if ext == ".pdf" and shutil.which("pdftotext"):
        try:
            p = subprocess.run(["pdftotext", path, "-"], capture_output=True,
                               timeout=120)
            return p.stdout.decode("utf-8", "replace") if p.returncode == 0 else ""
        except Exception:
            return ""
    return ""


def main():
    case_p, work = sys.argv[1], sys.argv[2]
    os.makedirs(work, exist_ok=True)
    case = json.load(open(case_p, encoding="utf-8"))
    root = find_root(case, os.path.dirname(os.path.abspath(case_p)))
    files = []
    if root:
        for base, dirs, names in os.walk(root):
            dirs.sort()
            for name in sorted(names):
                path = os.path.join(base, name)
                rel = os.path.relpath(path, root)
                entry = {"path": rel, "ext": os.path.splitext(name)[1].lower(),
                         "version_tag": version_tag(name)}
                try:
                    st = os.stat(path)
                    entry["size"] = st.st_size
                    entry["mtime"] = time.strftime("%Y-%m-%d",
                                                   time.localtime(st.st_mtime))
                    h = hashlib.sha256()
                    with open(path, "rb") as f:
                        for chunk in iter(lambda: f.read(1 << 20), b""):
                            h.update(chunk)
                    entry["sha16"] = h.hexdigest()[:16]
                    entry["status"] = "ok"
                except OSError as e:
                    entry.update(size=None, mtime=None, sha16=None,
                                 status="unreadable: %s" % e)
                files.append(entry)
    with open(os.path.join(work, "scan.json"), "w", encoding="utf-8") as f:
        json.dump({"library_root": root, "case_id":
                   case.get("case_id") or case.get("id"), "files": files},
                  f, ensure_ascii=False, indent=2)

    answers = []
    texts = {e["path"]: extract_text(os.path.join(root, e["path"]))
             for e in files if root and e["status"] == "ok"}
    for q in find_questions(case):
        qt = tokens(q.get("text", ""))
        hits = []
        for rel, text in texts.items():
            hay = (rel + " " + text).lower()
            matched = [t for t in qt if t in hay]
            if matched:
                snippet = ""
                for line in text.splitlines():
                    if any(t in line.lower() for t in matched):
                        snippet = line.strip()[:160]
                        break
                hits.append({"file": rel, "matched_terms": matched,
                             "snippet": snippet})
        answers.append({"question_id": q.get("id"), "question": q.get("text"),
                        "status": "answered" if hits else "no_match",
                        "hits": hits[:5],
                        "searched_terms": qt if not hits else None})
    with open(os.path.join(work, "answers.json"), "w", encoding="utf-8") as f:
        json.dump({"answers": answers}, f, ensure_ascii=False, indent=2)
    print(json.dumps({"n_files": len(files), "n_questions": len(answers)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
