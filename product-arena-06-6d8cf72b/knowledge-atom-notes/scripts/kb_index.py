#!/usr/bin/env python3
"""kb_index.py -- build the searchable index from linted atoms.

Outputs:
  index.jsonl   one JSON object per line: {id, type, term, aliases, summary,
                anchors} -- greppable, diff-able, importable;
  terms.md      human table of terminology: canonical term, aliases, type,
                first anchor, one-line gloss.

The index is a derived view; atoms.json stays the source of truth. Every
alias in every atom is normalized the same way as kb_lint so downstream
search can rely on the canonical form.
"""
import argparse
import json
import re

GREEK = {"α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon",
         "θ": "theta", "λ": "lambda", "μ": "mu", "π": "pi", "σ": "sigma",
         "τ": "tau", "φ": "phi", "ω": "omega", "Ω": "omega", "Δ": "delta"}


def norm_term(term):
    t = (term or "").strip().lower()
    for g, name in GREEK.items():
        t = t.replace(g, name)
    t = t.replace("−", "-").replace("–", "-")
    t = re.sub(r"[\s_]+", " ", t)
    return re.sub(r"-\s*", "-", t).strip()


def summarize(atom):
    for key in ("definition", "claim", "purpose", "meaning"):
        if atom.get(key):
            text = re.sub(r"\s+", " ", atom[key]).strip()
            return text[:180] + ("…" if len(text) > 180 else "")
    return ""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--atoms", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    with open(args.atoms, encoding="utf-8") as fh:
        doc = json.load(fh)
    atoms = doc.get("atoms", doc if isinstance(doc, list) else [])

    import os
    os.makedirs(args.out, exist_ok=True)
    lines, rows = [], []
    for i, atom in enumerate(atoms):
        aid = atom.get("id", "atom-%03d" % (i + 1))
        term = atom.get("term") or atom.get("symbol") or ""
        aliases = sorted({norm_term(a) for a in atom.get("aliases", []) if a})
        anchors = [e.get("anchor", "") for e in atom.get("evidence", [])]
        rec = {"id": aid, "type": atom.get("type"), "term": term,
               "canonical": norm_term(term), "aliases": aliases,
               "summary": summarize(atom), "anchors": anchors,
               "unit": atom.get("unit"), "value": atom.get("value")}
        rows.append(rec)
        lines.append(json.dumps(rec, ensure_ascii=False))
    with open(args.out + "/index.jsonl", "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + ("\n" if lines else ""))

    md = ["# Terminology index (derived view; atoms.json is the source of truth)",
          "", "| canonical term | aliases | type | first anchor | gloss |",
          "|---|---|---|---|---|"]
    for rec in sorted(rows, key=lambda r: (r["canonical"] or "", r["type"] or "")):
        md.append("| %s | %s | %s | %s | %s |" % (
            rec["canonical"] or "—", ", ".join(rec["aliases"]) or "—",
            rec["type"] or "—", rec["anchors"][0] if rec["anchors"] else "—",
            (rec["summary"] or "").replace("|", "\\|")[:120]))
    with open(args.out + "/terms.md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    print(json.dumps({"atoms": len(rows), "index": args.out + "/index.jsonl"}))


if __name__ == "__main__":
    main()
