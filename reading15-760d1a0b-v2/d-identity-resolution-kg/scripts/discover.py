#!/usr/bin/env python3
"""discover.py — tolerant input discovery and corpus normalization.

Scans --input for case.json, task.md, material.json, *-material.json full texts
and corpus-manifest.json, tolerating missing secondary material, extra files
(e.g. secondary-publisher.xml is only registered, never parsed) and the list /
{"materials": [...]} / mapping shapes of material.json.

Writes <work>/corpus.json:
  {case_id, output_contract, query_specs, sources: [{source_id, role, doi,
   title, authors, sha256_ok, paragraphs: [{paragraph_id, section, text}]}],
   registered_files, warnings}

Usage: python3 discover.py --input /input --work /app/work
"""
import argparse
import glob
import json
import os
import sys

import kgcommon as K


def _iter_material_index(obj):
    """Yield (source_id-ish, entry) pairs from a tolerant material.json shape."""
    if isinstance(obj, list):
        for entry in obj:
            if isinstance(entry, dict):
                yield entry.get("source_id"), entry
    elif isinstance(obj, dict):
        items = obj.get("materials", obj.get("sources"))
        if isinstance(items, list):
            for entry in items:
                if isinstance(entry, dict):
                    yield entry.get("source_id"), entry
        elif isinstance(items, dict):
            for key in sorted(items):
                yield key, items[key]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, help="input directory (e.g. /input)")
    ap.add_argument("--work", required=True, help="work directory (e.g. /app/work)")
    args = ap.parse_args(argv)

    warnings = []
    registered = []
    if not os.path.isdir(args.input):
        print("ERROR: input directory not found: %s" % args.input, file=sys.stderr)
        return 2
    os.makedirs(args.work, exist_ok=True)

    def reg(fname):
        registered.append(fname)

    # --- case.json ---------------------------------------------------------
    case = {}
    case_path = os.path.join(args.input, "case.json")
    if os.path.isfile(case_path):
        reg("case.json")
        try:
            case = K.load_json(case_path)
        except Exception as exc:  # tolerate unparsable case.json
            warnings.append("case.json unparsable: %s" % exc)
            case = {}
    else:
        warnings.append("case.json missing; using empty contract")

    # --- corpus manifest ---------------------------------------------------
    manifest = {}
    man_path = os.path.join(args.input, "corpus-manifest.json")
    if os.path.isfile(man_path):
        reg("corpus-manifest.json")
        try:
            manifest = K.load_json(man_path)
        except Exception as exc:
            warnings.append("corpus-manifest.json unparsable: %s" % exc)
    man_by_id = {}
    for entry in manifest.get("sources", []) if isinstance(manifest, dict) else []:
        if isinstance(entry, dict) and entry.get("source_id"):
            man_by_id[entry["source_id"]] = entry

    # --- full text files ----------------------------------------------------
    fulltext_files = sorted(
        os.path.basename(p)
        for p in glob.glob(os.path.join(args.input, "*-material.json"))
    )
    if not fulltext_files and os.path.isfile(os.path.join(args.input, "material.json")):
        # maybe material.json itself carries full text
        fulltext_files = ["material.json"]

    sources = []
    for fname in fulltext_files:
        reg(fname)
        try:
            doc = K.load_json(os.path.join(args.input, fname))
        except Exception as exc:
            warnings.append("%s unparsable: %s" % (fname, exc))
            continue
        if not isinstance(doc, dict) or not isinstance(doc.get("paragraphs"), list):
            warnings.append("%s has no paragraph list; skipped" % fname)
            continue
        source_id = doc.get("source_id") or os.path.splitext(fname)[0]
        entry = man_by_id.get(source_id, {})
        role = entry.get("role")
        if not role:
            role = "primary" if "primary" in fname else (
                "secondary" if "secondary" in fname else "unknown")
        sha_ok = None
        if entry.get("sha256"):
            actual = K.sha256_file(os.path.join(args.input, fname))
            sha_ok = (actual == entry["sha256"])
            if not sha_ok:
                warnings.append("sha256 mismatch for %s" % fname)
        paragraphs = []
        seen_ids = set()
        for idx, para in enumerate(doc["paragraphs"]):
            if not isinstance(para, dict) or "text" not in para:
                warnings.append("%s paragraph %d malformed; skipped" % (fname, idx))
                continue
            pid = str(para.get("paragraph_id") or "%s-auto-%03d" % (source_id, idx))
            if pid in seen_ids:
                warnings.append("duplicate paragraph_id %s in %s" % (pid, fname))
                continue
            seen_ids.add(pid)
            paragraphs.append({
                "paragraph_id": pid,
                "section": str(para.get("section") or ""),
                "text": str(para["text"]),
            })
        sources.append({
            "source_id": source_id,
            "role": role,
            "doi": doc.get("doi") or entry.get("doi"),
            "title": doc.get("title") or entry.get("title"),
            "authors": doc.get("authors") or entry.get("authors") or [],
            "sha256_ok": sha_ok,
            "paragraphs": paragraphs,
        })

    if not sources:
        warnings.append("no full-text sources discovered")
    roles = [s["role"] for s in sources]
    if roles.count("primary") > 1:
        warnings.append("more than one primary source; check manifest roles")

    # --- material.json index (tolerant, cross-check only) -------------------
    mat_index = []
    mat_path = os.path.join(args.input, "material.json")
    if os.path.isfile(mat_path) and "material.json" not in fulltext_files:
        reg("material.json")
        try:
            mat_doc = K.load_json(mat_path)
            for sid, entry in _iter_material_index(mat_doc):
                mat_index.append({"source_id": sid, "role": entry.get("role")})
        except Exception as exc:
            warnings.append("material.json unparsable: %s" % exc)

    # --- register any other files without parsing them ----------------------
    for fname in sorted(os.listdir(args.input)):
        if fname not in registered and os.path.isfile(os.path.join(args.input, fname)):
            reg(fname)
            if fname.endswith(".xml"):
                warnings.append("%s registered but never parsed (per runtime contract)" % fname)

    corpus = {
        "notice": K.NOTICE,
        "case_id": case.get("case_id"),
        "output_contract": case.get("output_contract") or {},
        "query_specs": case.get("query_specs") or [],
        "case_root_metadata": {
            "doi": case.get("doi"),
            "title": case.get("title"),
            "authors": case.get("authors") or [],
            "attribution": "primary paper only",
        },
        "material_index": mat_index,
        "registered_files": sorted(registered),
        "sources": sources,
        "warnings": sorted(warnings),
    }
    out_path = os.path.join(args.work, "corpus.json")
    K.dump_json(corpus, out_path)
    print("discover: %d source(s), %d paragraph(s), %d warning(s) -> %s" % (
        len(sources),
        sum(len(s["paragraphs"]) for s in sources),
        len(warnings), out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
