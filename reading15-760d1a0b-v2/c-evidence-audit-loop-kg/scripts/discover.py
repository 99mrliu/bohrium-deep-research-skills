#!/usr/bin/env python3
"""discover.py — tolerant input discovery + normalized corpus build (stage 0).

Scans an input directory (e.g. /input), tolerates missing/extra files and
several material.json shapes, and writes a single normalized corpus file that
all later stages read. Never hard-codes case content.

Usage:
    python3 discover.py --input /input --work /app/work [--output /app/output]

Outputs (under --work):
    corpus.json           normalized corpus: sources, paragraphs, root metadata
If --output is given, an early honest-partial result.json stub is written there
(status="partial", stage="discover") so a graded artifact always exists.

Python 3.9+, standard library only. Deterministic output (sorted keys).
"""
import argparse
import hashlib
import json
import os
import sys


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(obj, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_paragraph_list(raw):
    """Accept list of paragraph dicts; return sorted list of normalized dicts."""
    out = []
    if not isinstance(raw, list):
        return out
    for i, p in enumerate(raw):
        if not isinstance(p, dict):
            continue
        pid = p.get("paragraph_id") or p.get("id") or "auto-%03d" % (i + 1)
        out.append({
            "paragraph_id": str(pid),
            "section": str(p.get("section") or ""),
            "text": str(p.get("text") or ""),
        })
    out.sort(key=lambda d: d["paragraph_id"])
    return out


def extract_material_doc(obj):
    """Tolerate shapes: dict with 'paragraphs', bare list, {'materials': [...]}, mapping."""
    if isinstance(obj, dict):
        if isinstance(obj.get("paragraphs"), list):
            return obj
        if isinstance(obj.get("materials"), list) and obj["materials"]:
            first = obj["materials"][0]
            if isinstance(first, dict):
                return first
        # mapping of source_id -> doc
        for key in sorted(obj.keys()):
            val = obj[key]
            if isinstance(val, dict) and isinstance(val.get("paragraphs"), list):
                return val
    return {}


def main():
    ap = argparse.ArgumentParser(description="Discover input files, build normalized corpus.json")
    ap.add_argument("--input", required=True, help="input directory (e.g. /input)")
    ap.add_argument("--work", required=True, help="work directory (e.g. /app/work)")
    ap.add_argument("--output", default=None, help="optional output dir for early partial result.json")
    args = ap.parse_args()

    indir = args.input
    work = args.work
    os.makedirs(work, exist_ok=True)
    warnings = []

    if not os.path.isdir(indir):
        print("ERROR: input directory not found: %s" % indir, file=sys.stderr)
        return 2

    present = sorted(os.listdir(indir))

    # --- case.json (required) ---
    case_path = os.path.join(indir, "case.json")
    if not os.path.isfile(case_path):
        print("ERROR: case.json missing in %s" % indir, file=sys.stderr)
        return 2
    case = load_json(case_path)
    case_id = str(case.get("case_id") or "unknown-case")
    output_contract = case.get("output_contract") or {}
    query_specs = case.get("query_specs") or []
    root_metadata = {
        "doi": case.get("doi"),
        "title": case.get("title"),
        "authors": case.get("authors") or [],
    }

    # --- material files ---
    sources = {}
    role_by_file = [("primary-material.json", "primary"), ("secondary-material.json", "secondary")]
    for fname, role in role_by_file:
        path = os.path.join(indir, fname)
        if not os.path.isfile(path):
            if role == "primary":
                print("ERROR: primary-material.json missing in %s" % indir, file=sys.stderr)
                return 2
            warnings.append("optional file missing: %s (single-paper case tolerated)" % fname)
            continue
        doc = extract_material_doc(load_json(path))
        sid = str(doc.get("source_id") or role)
        paras = normalize_paragraph_list(doc.get("paragraphs"))
        if not paras:
            warnings.append("%s: no paragraphs parsed" % fname)
        sources[sid] = {
            "source_id": sid,
            "role": role,
            "doi": doc.get("doi"),
            "title": doc.get("title"),
            "authors": doc.get("authors") or [],
            "file": fname,
            "paragraphs": paras,
        }

    # --- material.json aggregate index (optional; cross-check only) ---
    mat_path = os.path.join(indir, "material.json")
    material_index_note = "absent"
    if os.path.isfile(mat_path):
        raw = load_json(mat_path)
        if isinstance(raw, dict) and isinstance(raw.get("materials"), list):
            entries = raw["materials"]
        elif isinstance(raw, list):
            entries = raw
        elif isinstance(raw, dict):
            entries = [raw[k] for k in sorted(raw.keys()) if isinstance(raw[k], dict)]
        else:
            entries = []
        material_index_note = "parsed %d aggregate entries (cross-check only)" % len(entries)
    else:
        warnings.append("material.json absent; proceeding with per-source files only")

    # --- corpus-manifest.json (optional; attribution cross-check) ---
    manifest_check = {"status": "absent", "details": []}
    man_path = os.path.join(indir, "corpus-manifest.json")
    if os.path.isfile(man_path):
        manifest = load_json(man_path)
        entries = manifest.get("sources") if isinstance(manifest, dict) else None
        if entries is None and isinstance(manifest, list):
            entries = manifest
        entries = entries or []
        details = []
        for ent in entries:
            if not isinstance(ent, dict):
                continue
            sid = str(ent.get("source_id") or ent.get("role") or "?")
            row = {"source_id": sid, "role_declared": ent.get("role")}
            src = sources.get(sid)
            if src is None:
                row["match"] = "no-loaded-source"
            else:
                ok = True
                for field in ("doi", "title"):
                    if ent.get(field) and src.get(field) and ent.get(field) != src.get(field):
                        ok = False
                        row["mismatch_" + field] = True
                declared_hash = ent.get("sha256")
                if declared_hash:
                    actual = sha256_file(os.path.join(indir, src["file"]))
                    if actual != declared_hash:
                        ok = False
                        row["sha256_mismatch"] = True
                row["match"] = "ok" if ok else "MISMATCH"
            details.append(row)
        details.sort(key=lambda r: r["source_id"])
        manifest_check = {"status": "checked", "details": details}
        for row in details:
            if row.get("match") != "ok":
                warnings.append("corpus-manifest cross-check: %s -> %s" % (row["source_id"], row.get("match")))

    # --- secondary-publisher.xml: register presence only, never parse ---
    publisher_xml_present = os.path.isfile(os.path.join(indir, "secondary-publisher.xml"))

    n_para = sum(len(s["paragraphs"]) for s in sources.values())
    corpus = {
        "case_id": case_id,
        "root_metadata": root_metadata,
        "output_contract": output_contract,
        "query_specs": query_specs,
        "sources": sources,
        "material_index_note": material_index_note,
        "manifest_check": manifest_check,
        "publisher_xml_present": publisher_xml_present,
        "input_files_present": present,
        "discovery_warnings": sorted(warnings),
        "stats": {
            "source_count": len(sources),
            "paragraph_count": n_para,
            "query_spec_count": len(query_specs),
        },
    }
    out_path = os.path.join(work, "corpus.json")
    dump_json(corpus, out_path)

    if args.output:
        contract_keys = sorted(output_contract.keys()) if isinstance(output_contract, dict) else []
        stub = {"case_id": case_id, "status": "partial",
                "status_reason": "pipeline at discover stage; extraction/audit/build not yet run",
                "sources": sorted(sources.keys())}
        for key in contract_keys:
            stub.setdefault(key, None)
        stub["run_meta"] = {"stage": "discover"}
        dump_json(stub, os.path.join(args.output, "result.json"))

    print("discover: case_id=%s sources=%d paragraphs=%d queries=%d" %
          (case_id, len(sources), n_para, len(query_specs)))
    for w in warnings:
        print("discover WARNING: %s" % w)
    print("discover: wrote %s" % out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
