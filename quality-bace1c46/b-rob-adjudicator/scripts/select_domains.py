#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""select_domains.py -- heuristic document-type detection and domain-set
selection. Purely local heuristics; consumes no model budget.

Reads docs.jsonl + pages/*.jsonl, writes domain_plan.json.
Low-confidence classifications are flagged with uncertain=true so the
operator can spend one batched model request to confirm them.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common_utils as cu
import domain_specs as ds

SCRIPT_VERSION = "select_domains/1.0"


def main():
    ap = argparse.ArgumentParser(description="Select bias domains per document")
    ap.add_argument("--workdir", default="/app/work")
    args = ap.parse_args()

    docs = cu.read_jsonl(os.path.join(args.workdir, "docs.jsonl"))
    plan = {"version": SCRIPT_VERSION, "documents": []}
    for row in docs:
        doc_id = row.get("doc_id")
        entry = {"doc_id": doc_id, "grade": row.get("grade"),
                 "type": "other", "type_hits": [], "uncertain": True,
                 "domains": [], "notes": []}
        if row.get("grade") == "failed":
            entry["notes"].append("extraction failed; no domains selected")
            plan["documents"].append(entry)
            continue
        pages = cu.load_pages(args.workdir, doc_id)
        # use the first two pages (title/abstract/intro) plus the tail
        # (funding/COI often at the end) for type detection
        head = " ".join(p.get("text", "") for p in pages[:2])
        tail = " ".join(p.get("text", "") for p in pages[-1:])
        doc_type, hits, confident = ds.detect_type(head + "\n" + tail)
        entry["type"] = doc_type
        entry["type_hits"] = hits
        entry["uncertain"] = not confident
        if row.get("grade") == "abstract_only":
            entry["uncertain"] = True
            entry["notes"].append(
                "abstract_only: type detection from abstract; "
                "most domains will be insufficient")
        sel = ds.domains_for_type(doc_type)
        entry["domains"] = [
            {"id": d["id"], "name": d["name"], "core": d["core"],
             "questions": [{"id": q["id"], "text": q["text"]}
                           for q in d["questions"]]}
            for d in sel]
        plan["documents"].append(entry)

    out_path = os.path.join(args.workdir, "domain_plan.json")
    cu.write_json(out_path, plan)
    n_unc = sum(1 for d in plan["documents"] if d["uncertain"])
    print({"domain_plan": out_path, "docs": len(plan["documents"]),
           "uncertain": n_unc})


if __name__ == "__main__":
    main()
