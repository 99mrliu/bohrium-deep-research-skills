#!/usr/bin/env python3
"""Execute retrieval under the custody chain.

For every question: extract library texts (registered with sha256), score
anchors, and register an evidence card per claim (file + sha256 + verbatim
quote + char interval). Nothing here decides admissibility -- the gate does.

Writes into WORK_DIR: sources_manifest.json, evidence_cards.json, and
appends to journal.jsonl.

Usage: custody_run.py CASE_JSON WORK_DIR
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import custody_journal  # noqa: E402

LIB_KEYS = ["library", "library_root", "data_dir", "files_dir", "root",
            "documents_dir", "doc_root", "materials", "corpus"]
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]{1,}|[一-鿿]+")
STOP = set("的了和是在有与及或其对这那中上个一为以于哪些哪个什么哪份")


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
    for base, _d, files in os.walk("/input"):
        if files:
            return base
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


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md", ".csv", ".tsv", ".log", ".json", ".tex"):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read(), "ok"
        except OSError as e:
            return "", "read_failed: %s" % e
    if ext == ".pdf":
        if not shutil.which("pdftotext"):
            return "", "no_pdf_tool"
        try:
            p = subprocess.run(["pdftotext", path, "-"], capture_output=True,
                               timeout=120)
            return (p.stdout.decode("utf-8", "replace") if p.returncode == 0
                    else ""), "ok" if p.returncode == 0 else "pdftotext_failed"
        except Exception as e:
            return "", "pdf_error: %s" % e
    if ext in (".docx", ".xlsx", ".pptx"):
        import zipfile
        try:
            with zipfile.ZipFile(path) as z:
                parts = [re.sub(r"<[^>]+>", " ",
                                z.read(n).decode("utf-8", "replace"))
                         for n in z.namelist() if n.endswith(".xml")]
                return "\n".join(parts), "ok"
        except Exception as e:
            return "", "office_failed: %s" % e
    return "", "unsupported_ext"


def sentences(text):
    parts = re.split(r"(?<=[。！？.!?\n])\s*", text)
    return [p.strip() for p in parts if p.strip()]


def main():
    case_p, work = sys.argv[1], sys.argv[2]
    os.makedirs(work, exist_ok=True)
    case = json.load(open(case_p, encoding="utf-8"))
    if not os.path.exists(os.path.join(work, "journal.jsonl")):
        custody_journal.append(work, "init", "custody chain created")
    root = find_root(case, os.path.dirname(os.path.abspath(case_p)))
    custody_journal.append(work, "locate_library", "library_root=%s" % root)

    manifest, cards = [], []
    corpus = []
    if root:
        for base, dirs, names in os.walk(root):
            dirs.sort()
            for name in sorted(names):
                path = os.path.join(base, name)
                rel = os.path.relpath(path, root)
                try:
                    digest = sha256_of(path)
                except OSError as e:
                    manifest.append({"file": rel, "sha256": None,
                                     "status": "read_failed: %s" % e})
                    continue
                text, st = extract_text(path)
                manifest.append({"file": rel, "sha256": digest, "status": st})
                corpus.append({"file": rel, "sha256": digest, "text": text})
    mpath = os.path.join(work, "sources_manifest.json")
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump({"library_root": root, "sources": manifest},
                  f, ensure_ascii=False, indent=2)
    custody_journal.append(work, "register_sources",
                           "%d sources registered" % len(manifest), mpath)

    for q in find_questions(case):
        qt = tokens(q.get("text", ""))
        custody_journal.append(work, "search",
                               "question %s terms=%s" % (q.get("id"), qt[:12]))
        best = None
        for c in corpus:
            if not c["text"]:
                continue
            for s in sentences(c["text"]):
                hit = [t for t in qt if t in s.lower()]
                if hit and (best is None or len(hit) > len(best[0])):
                    best = (hit, c, s)
        if best is None:
            cards.append({"question_id": q.get("id"),
                          "question": q.get("text"),
                          "status": "not_found",
                          "searched_terms": qt,
                          "coverage_files": len(corpus)})
            continue
        hit, c, s = best
        start = c["text"].find(s)
        cards.append({"question_id": q.get("id"),
                      "question": q.get("text"),
                      "claim": s,
                      "file": c["file"], "sha256": c["sha256"],
                      "quote": s[:200],
                      "char_start": start, "char_end": start + len(s),
                      "matched_terms": hit})
    cpath = os.path.join(work, "evidence_cards.json")
    with open(cpath, "w", encoding="utf-8") as f:
        json.dump({"cards": cards}, f, ensure_ascii=False, indent=2)
    custody_journal.append(work, "register_claims",
                           "%d evidence cards" % len(cards), cpath)
    print(json.dumps({"n_cards": len(cards), "n_sources": len(manifest)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
