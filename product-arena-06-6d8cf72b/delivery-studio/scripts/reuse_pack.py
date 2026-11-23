#!/usr/bin/env python3
"""reuse_pack.py -- package the notes for reuse by the next reader.

Outputs into the delivery directory:
  notes.jsonl        one record per knowledge point / card field / section
                     {kind, id, text, anchors} -- greppable and diff-able;
  manifest.json      sha256 of every input consumed and output produced;
  change_records.md  the change log (from notes.json change_records).

The manifest is the anti-drift device: anyone reusing the notes can verify
which source bytes the notes were derived from and whether the artifacts on
disk still match.
"""
import argparse
import hashlib
import json
import os


def sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--notes", required=True)
    ap.add_argument("--inputs", nargs="*", default=[],
                    help="source files that were read (paper, exports)")
    ap.add_argument("--artifacts", nargs="*", default=[],
                    help="output files to hash (result.json, notes.md, ...)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    with open(args.notes, encoding="utf-8") as fh:
        notes = json.load(fh)
    os.makedirs(args.out, exist_ok=True)

    records = []
    for field, value in (notes.get("card") or {}).items():
        anchors = []
        if isinstance(value, dict):
            anchors = [value["anchor"]] if value.get("anchor") else []
            value = value.get("value")
        records.append({"kind": "card-field", "id": field, "text": str(value),
                        "anchors": anchors})
    for i, sec in enumerate(notes.get("sections", []), start=1):
        records.append({"kind": "section-note", "id": "sec-%02d" % i,
                        "text": sec.get("heading", "") + ": " + sec.get("body", ""),
                        "anchors": sec.get("anchors", [])})
    for i, q in enumerate(notes.get("open_questions", []), start=1):
        records.append({"kind": "open-question", "id": "oq-%02d" % i,
                        "text": q, "anchors": []})
    with open(os.path.join(args.out, "notes.jsonl"), "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    manifest = {
        "inputs": [{"path": p, "sha256": sha256_file(p)} for p in args.inputs
                   if os.path.exists(p)],
        "artifacts": [{"path": p, "sha256": sha256_file(p)} for p in args.artifacts
                      if os.path.exists(p)],
        "missing": [p for p in list(args.inputs) + list(args.artifacts)
                    if not os.path.exists(p)],
    }
    with open(os.path.join(args.out, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    changes = notes.get("change_records", [])
    lines = ["# Change records", ""]
    if changes:
        for c in changes:
            if isinstance(c, dict):
                lines.append("- %s → %s（%s）" % (c.get("before"), c.get("after"),
                                                  c.get("why", "")))
            else:
                lines.append("- %s" % c)
    else:
        lines.append("- （无修正记录）")
    with open(os.path.join(args.out, "change_records.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(json.dumps({"records": len(records), "missing": manifest["missing"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
