#!/usr/bin/env python3
"""Execute compiled queries against the library with strict hard filters.

Every filter leaves an elimination trace (kept/dropped/undecidable). Concept
scoring only ranks the survivors; it never eliminates. If filters empty the
candidate set, the answer is an honest no_match naming the zeroing filter.

Usage: forge_run.py CASE_JSON QUERIES_JSON OUT_JSON
"""
import json
import os
import re
import shutil
import subprocess
import sys

LIB_KEYS = ["library", "library_root", "data_dir", "files_dir", "root",
            "documents_dir", "doc_root", "materials", "corpus"]
YEAR_IN_NAME = re.compile(r"(19\d{2}|20\d{2})")
DATE_IN_NAME = re.compile(r"(19|20)\d{2}[-_.年]\d{1,2}[-_.月]\d{1,2}")
VERSION_TAGS = [("终稿", "final"), ("正式版", "final"), ("定稿", "final"),
                ("初稿", "draft"), ("草稿", "draft"),
                ("修订", "revised"), ("修改", "revised"),
                ("final", "final"), ("draft", "draft"), ("revised", "revised")]
VNUM = re.compile(r"[vV](\d+)")


def find_root(case):
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
        for p in (v, os.path.join("/input", v)):
            if os.path.isdir(p):
                return os.path.abspath(p)
    for base, _d, files in os.walk("/input"):
        if files:
            return base
    return None


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


def version_of(name):
    low = name.lower()
    for word, tag in VERSION_TAGS:
        if word in name:
            return tag, "filename_marker:%s" % word
    m = VNUM.search(name)
    if m:
        return "v" + m.group(1), "filename_vnum"
    return None, None


def build_candidates(root):
    cands = []
    for base, dirs, names in os.walk(root):
        dirs.sort()
        for name in sorted(names):
            path = os.path.join(base, name)
            rel = os.path.relpath(path, root)
            ext = os.path.splitext(name)[1].lower().lstrip(".")
            year = None
            m = YEAR_IN_NAME.search(name)
            if m:
                year = int(m.group(1))
            version, vev = version_of(name)
            text, tstatus = extract_text(path)
            if year is None:
                m2 = YEAR_IN_NAME.search(text[:2000])
                if m2:
                    year = int(m2.group(1))
            cands.append({"path": rel, "ext": ext, "year_in_name": year,
                          "version": version, "version_evidence": vev,
                          "text": text.lower(), "text_status": tstatus,
                          "name_lower": name.lower(), "rel_lower": rel.lower()})
    return cands


def apply_filter(cands, key, value):
    kept, dropped, undecidable = [], [], []
    for c in cands:
        if key == "year":
            if c["year_in_name"] is None:
                undecidable.append(c)
            elif c["year_in_name"] == value:
                kept.append(c)
            else:
                dropped.append(c)
        elif key in ("date_after", "date_before"):
            kept.append(c)  # coarse year filter already applied
        elif key == "batch":
            if value.lower() in c["rel_lower"] or value.lower() in c["text"]:
                kept.append(c)
            else:
                dropped.append(c)
        elif key == "project":
            if value.lower() in c["rel_lower"] or value.lower() in c["text"][:500]:
                kept.append(c)
            else:
                dropped.append(c)
        elif key == "file_type":
            (kept if c["ext"] in value else dropped).append(c)
        elif key == "version":
            if c["version"] is None:
                undecidable.append(c)
            elif c["version"] == value:
                kept.append(c)
            else:
                dropped.append(c)
        elif key == "path_contains":
            (kept if str(value).lower() in c["rel_lower"] else dropped).append(c)
        else:
            kept.append(c)
    return kept, dropped, undecidable


def score(cand, concepts):
    hits = []
    for t in concepts:
        n = 0
        if t in cand["name_lower"]:
            n += 3
        if t in cand["text"]:
            n += 1
        if n:
            hits.append((t, n))
    return sum(n for _t, n in hits), sorted(t for t, _n in hits)


def main():
    case_p, queries_p, out_p = sys.argv[1], sys.argv[2], sys.argv[3]
    case = json.load(open(case_p, encoding="utf-8"))
    queries = json.load(open(queries_p, encoding="utf-8"))["queries"]
    root = find_root(case)
    cands = build_candidates(root) if root else []
    results = []
    for q in queries:
        remaining = list(cands)
        trace = {}
        zeroing = None
        for key, value in q["hard_filters"].items():
            kept, dropped, undec = apply_filter(remaining, key, value)
            trace[key] = {"value": value, "kept": len(kept),
                          "dropped": len(dropped), "undecidable": len(undec)}
            if not kept and zeroing is None and (dropped or undec):
                zeroing = key
            remaining = kept
        q["filter_trace"] = trace
        entry = {"question_id": q["question_id"], "question": q["question"],
                 "hard_filters": q["hard_filters"], "filter_trace": trace,
                 "unparsed_constraints": q.get("unparsed_constraints", [])}
        if not root:
            entry["status"] = "no_library"
            entry["note"] = "未能定位文档库根目录"
        elif not remaining:
            entry["status"] = "no_match"
            entry["note"] = ("硬过滤后候选为 0；%s。未放宽任何条件。"
                             % ("最后存活数被条件 %r 清零" % zeroing if zeroing
                                else "库为空"))
            entry["hits"] = []
        else:
            scored = []
            for c in remaining:
                s, matched = score(c, q["concepts"])
                if s:
                    line_hits = [i + 1 for i, l in enumerate(c["text"].splitlines())
                                 if any(t in l for t in matched)][:10]
                    scored.append({"file": c["path"], "score": s,
                                   "matched_terms": matched,
                                   "lines": line_hits,
                                   "version": c["version"],
                                   "version_evidence": c["version_evidence"],
                                   "content": "metadata_only" if not c["text"]
                                              else "full_text"})
            scored.sort(key=lambda h: -h["score"])
            if scored:
                entry["status"] = "matched"
                entry["hits"] = scored[:5]
            else:
                entry["status"] = "no_match"
                entry["note"] = ("硬过滤后剩 %d 个候选但概念词均无命中；"
                                 "未放宽条件" % len(remaining))
                entry["hits"] = []
        results.append(entry)
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump({"case_id": case.get("case_id") or case.get("id"),
                   "library_root": root, "n_candidates": len(cands),
                   "results": results}, f, ensure_ascii=False, indent=2)
    print(json.dumps({"n_candidates": len(cands),
                      "n_matched": sum(1 for r in results
                                       if r["status"] == "matched")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
