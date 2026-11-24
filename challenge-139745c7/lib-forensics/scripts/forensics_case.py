#!/usr/bin/env python3
"""Profile a case.json: locate the library root and the questions without
assuming fixed key names. Writes case_profile.json.

Usage: forensics_case.py CASE_JSON OUT_JSON
"""
import json
import os
import sys

LIB_KEYS = ["library", "library_root", "data_dir", "files_dir", "root",
            "documents_dir", "doc_root", "materials", "corpus"]
QUERY_KEYS = ["searches", "questions", "queries", "tasks", "asks"]


def walk_strings(obj, hits):
    if isinstance(obj, dict):
        for k, v in obj.items():
            lk = str(k).lower()
            if lk in LIB_KEYS and isinstance(v, str):
                hits.setdefault("library_candidates", []).append((k, v))
            if lk in QUERY_KEYS:
                hits.setdefault("question_candidates", []).append((k, v))
            walk_strings(v, hits)
    elif isinstance(obj, list):
        for v in obj:
            walk_strings(v, hits)


def find_library_root(case, candidates, case_dir=""):
    for _k, v in candidates:
        for p in (v, os.path.join("/input", v),
                  os.path.join(case_dir, v) if case_dir else v):
            if p and os.path.isdir(p):
                return os.path.abspath(p)
    # fallback: any directory under /input that contains files
    for base, _dirs, files in os.walk("/input"):
        if files:
            return base
    return None


def main():
    case_path, out_path = sys.argv[1], sys.argv[2]
    with open(case_path, encoding="utf-8") as f:
        case = json.load(f)
    hits = {}
    walk_strings(case, hits)
    lib_root = find_library_root(case, hits.get("library_candidates", []),
                                 os.path.dirname(os.path.abspath(case_path)))
    questions = []
    for _k, v in hits.get("question_candidates", []):
        if isinstance(v, list):
            for i, q in enumerate(v):
                questions.append(q if isinstance(q, dict) else {"id": "q%d" % i, "text": str(q)})
        elif isinstance(v, str):
            questions.append({"id": "q0", "text": v})
    profile = {
        "case_id": case.get("case_id") or case.get("id") or "unknown",
        "output_contract": case.get("output_contract") or case.get("outputContract") or {},
        "library_root": lib_root,
        "library_candidates": hits.get("library_candidates", []),
        "questions": questions,
        "raw_keys": sorted(case.keys()) if isinstance(case, dict) else [],
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    print(json.dumps({"library_root": lib_root, "n_questions": len(questions),
                      "case_id": profile["case_id"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
