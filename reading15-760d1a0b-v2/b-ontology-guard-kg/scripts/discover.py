#!/usr/bin/env python3
"""discover.py — tolerant discovery of /input files for bundle b-ontology-guard-kg.

Finds case.json / task.md / material.json / primary-material.json /
secondary-material.json / corpus-manifest.json (any may be missing except that
at least one *-material.json must exist), normalizes all paragraphs into a
single corpus index, and cross-checks source attribution against
corpus-manifest.json (sha256, role, doi) when the manifest is present.

Usage:
    python3 discover.py --input /input --work /app/work

Outputs (deterministic, sorted):
    <work>/corpus.json       normalized paragraphs keyed by (source_id, paragraph_id)
    <work>/discovery.json    file inventory + manifest cross-check + warnings

Python 3 standard library only.
"""
import argparse
import hashlib
import json
import os
import sys

CASE_FILES = ["case.json", "task.md", "material.json",
              "primary-material.json", "secondary-material.json",
              "corpus-manifest.json", "secondary-publisher.xml"]


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def paragraphs_from_material(doc, fallback_source_id):
    """Yield (source_id, paragraph_id, section, text) from a JATS-like material doc."""
    source_id = str(doc.get("source_id") or fallback_source_id)
    paras = doc.get("paragraphs")
    if not isinstance(paras, list):
        return source_id, []
    out = []
    for idx, para in enumerate(paras):
        if not isinstance(para, dict):
            continue
        pid = str(para.get("paragraph_id") or "p%d" % (idx + 1))
        out.append({
            "source_id": source_id,
            "paragraph_id": pid,
            "section": str(para.get("section") or ""),
            "text": str(para.get("text") or ""),
        })
    return source_id, out


def aggregate_material_index(obj):
    """Tolerate list / {'materials': [...]} / mapping shapes for material.json."""
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        if isinstance(obj.get("materials"), list):
            return obj["materials"]
        # mapping shape: {name: {...}} — return values that look like dicts
        return [v for v in obj.values() if isinstance(v, dict)]
    return []


def main(argv=None):
    parser = argparse.ArgumentParser(description="Discover and normalize /input corpus.")
    parser.add_argument("--input", required=True, help="input directory (the /input mount)")
    parser.add_argument("--work", required=True, help="work directory (e.g. /app/work)")
    args = parser.parse_args(argv)

    in_dir, work_dir = args.input, args.work
    os.makedirs(work_dir, exist_ok=True)
    warnings = []
    inventory = {}

    for name in CASE_FILES:
        path = os.path.join(in_dir, name)
        inventory[name] = "present" if os.path.isfile(path) else "missing"

    if inventory["secondary-publisher.xml"] == "present":
        # Register presence only; never parse it (runtime contract).
        warnings.append("secondary-publisher.xml present: registered only, not parsed")

    # --- case.json ---
    case = {}
    case_path = os.path.join(in_dir, "case.json")
    if inventory["case.json"] == "present":
        try:
            case = load_json(case_path)
        except (OSError, ValueError) as exc:
            warnings.append("case.json unparsable: %s" % exc)
            inventory["case.json"] = "unparsable"
    else:
        warnings.append("case.json missing: output_contract mirroring will be empty")

    # --- per-source material files ---
    sources = {}
    paragraphs = []
    for fname, role in (("primary-material.json", "primary"),
                        ("secondary-material.json", "secondary")):
        path = os.path.join(in_dir, fname)
        if inventory[fname] != "present":
            if role == "secondary":
                warnings.append("secondary material missing: single-paper mode")
            continue
        try:
            doc = load_json(path)
        except (OSError, ValueError) as exc:
            warnings.append("%s unparsable: %s" % (fname, exc))
            inventory[fname] = "unparsable"
            continue
        if not isinstance(doc, dict):
            warnings.append("%s is not a JSON object: skipped" % fname)
            continue
        source_id, paras = paragraphs_from_material(doc, fname)
        sources[source_id] = {
            "role": role,
            "doi": doc.get("doi"),
            "title": doc.get("title"),
            "authors": doc.get("authors") if isinstance(doc.get("authors"), list) else [],
            "file": fname,
            "paragraph_count": len(paras),
        }
        paragraphs.extend(paras)

    # --- aggregate material.json: only used to fill gaps, never to duplicate ---
    if inventory["material.json"] == "present":
        try:
            agg = aggregate_material_index(load_json(os.path.join(in_dir, "material.json")))
            known = {(p["source_id"], p["paragraph_id"]) for p in paragraphs}
            added = 0
            for entry in agg:
                sid, paras = paragraphs_from_material(entry, "aggregate")
                for p in paras:
                    if (p["source_id"], p["paragraph_id"]) not in known:
                        paragraphs.append(p)
                        known.add((p["source_id"], p["paragraph_id"]))
                        added += 1
                if sid not in sources and paras:
                    sources[sid] = {"role": "aggregate", "doi": entry.get("doi"),
                                    "title": entry.get("title"),
                                    "authors": entry.get("authors") or [],
                                    "file": "material.json",
                                    "paragraph_count": len(paras)}
            if added:
                warnings.append("material.json contributed %d paragraphs not in per-source files" % added)
        except (OSError, ValueError) as exc:
            warnings.append("material.json unparsable (ignored): %s" % exc)

    if not paragraphs:
        warnings.append("FATAL: no paragraphs discovered in any material file")

    # --- corpus-manifest.json cross-check ---
    manifest_check = []
    man_path = os.path.join(in_dir, "corpus-manifest.json")
    if inventory["corpus-manifest.json"] == "present":
        try:
            manifest = load_json(man_path)
            entries = manifest.get("sources") if isinstance(manifest, dict) else manifest
            if not isinstance(entries, list):
                entries = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                sid = str(entry.get("source_id") or "")
                rec = {"source_id": sid, "checks": []}
                src = sources.get(sid)
                if src is None:
                    rec["checks"].append("source_id not among discovered materials")
                else:
                    if entry.get("role") and entry["role"] != src["role"]:
                        rec["checks"].append("role mismatch: manifest=%s file=%s"
                                             % (entry["role"], src["role"]))
                    if entry.get("doi") and src.get("doi") and entry["doi"] != src["doi"]:
                        rec["checks"].append("doi mismatch: manifest=%s file=%s"
                                             % (entry["doi"], src["doi"]))
                    fname = src.get("file")
                    if entry.get("sha256") and fname and fname != "material.json":
                        actual = sha256_of(os.path.join(in_dir, fname))
                        if actual != entry["sha256"]:
                            rec["checks"].append("sha256 mismatch for %s" % fname)
                        else:
                            rec["checks"].append("sha256 ok")
                    if not rec["checks"]:
                        rec["checks"].append("ok")
                manifest_check.append(rec)
        except (OSError, ValueError) as exc:
            warnings.append("corpus-manifest.json unparsable: %s" % exc)

    # Root bibliographic metadata of case.json belongs ONLY to the primary paper.
    root_meta_note = None
    if isinstance(case, dict) and any(k in case for k in ("doi", "title", "authors")):
        root_meta_note = ("case.json root metadata (doi/title/authors) attributed to "
                          "PRIMARY paper only, never to secondary")

    # deterministic ordering
    paragraphs.sort(key=lambda p: (p["source_id"], p["paragraph_id"]))
    address_index = {}
    duplicates = []
    for p in paragraphs:
        key = p["source_id"] + "/" + p["paragraph_id"]
        if key in address_index:
            duplicates.append(key)
        address_index[key] = {"section": p["section"], "char_len": len(p["text"])}
    if duplicates:
        warnings.append("duplicate paragraph addresses: %s" % ", ".join(sorted(duplicates)))

    corpus = {
        "sources": {sid: sources[sid] for sid in sorted(sources)},
        "paragraphs": paragraphs,
        "address_index": {k: address_index[k] for k in sorted(address_index)},
        "root_metadata_note": root_meta_note,
    }
    discovery = {
        "inventory": {k: inventory[k] for k in sorted(inventory)},
        "manifest_check": manifest_check,
        "paragraph_total": len(paragraphs),
        "source_count": len(sources),
        "warnings": sorted(warnings),
    }
    for name, obj in (("corpus.json", corpus), ("discovery.json", discovery),
                      ("case_snapshot.json", case if isinstance(case, dict) else {})):
        with open(os.path.join(work_dir, name), "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")

    print("discover: %d sources, %d paragraphs, %d warnings -> %s"
          % (len(sources), len(paragraphs), len(warnings), work_dir))
    for w in sorted(warnings):
        print("  warning: %s" % w)
    return 0 if paragraphs else 1


if __name__ == "__main__":
    sys.exit(main())
