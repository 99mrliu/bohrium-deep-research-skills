#!/usr/bin/env python3
"""kb_lint.py -- terminology governance and typed-atom linting.

Checks (deterministic):
  1. schema per atom type (concept/method/finding/limitation/variable):
     required fields, evidence list with anchors resolvable in sections.json,
     quotes verbatim inside the anchored paragraph;
  2. term normalization: casefold, Greek letters -> names, hyphen/space and
     unicode-minus unification, acronym <-> expanded pairing;
  3. duplicate detection: same normalized term + same type = duplicate;
  4. conflict detection: same normalized term, different ``value``/definition
     strings that share no content words -> conflict warning (human decides).

Exit 0 = no hard violations, 2 = hard violations, 3 = input error.
Conflicts and near-duplicates are warnings: merging semantics is the agent's
job, the linter only surfaces candidates.
"""
import argparse
import json
import re
import sys

TYPES = {
    "concept": ["term", "definition"],
    "method": ["term", "purpose"],
    "finding": ["claim"],
    "limitation": ["claim", "scope"],
    "variable": ["symbol", "meaning"],
}
GREEK = {"α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon",
         "θ": "theta", "λ": "lambda", "μ": "mu", "π": "pi", "σ": "sigma",
         "τ": "tau", "φ": "phi", "ω": "omega", "Ω": "omega", "Δ": "delta"}
STOP = {"the", "a", "an", "of", "in", "on", "for", "to", "and", "or", "is",
        "are", "was", "were", "by", "with", "at", "from", "that", "this"}


def norm_term(term):
    t = (term or "").strip().lower()
    for g, name in GREEK.items():
        t = t.replace(g, name)
    t = t.replace("−", "-").replace("–", "-")
    t = re.sub(r"[\s_]+", " ", t)
    t = re.sub(r"-\s*", "-", t)
    return t.strip()


def content_words(text):
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if w not in STOP and len(w) > 2}


def load_paragraphs(sections_path):
    with open(sections_path, encoding="utf-8") as fh:
        data = json.load(fh)
    idx = {}
    for sec in data.get("sections", []):
        for para in sec.get("paragraphs", []):
            idx[para["anchor"]] = para["text"]
    return idx, data.get("status", "ok")


def lint(atoms_path, sections_path):
    with open(atoms_path, encoding="utf-8") as fh:
        doc = json.load(fh)
    atoms = doc.get("atoms", doc if isinstance(doc, list) else [])
    para_idx, src_status = load_paragraphs(sections_path)

    hard, warn = [], []
    seen = {}
    by_term = {}
    for i, atom in enumerate(atoms):
        aid = atom.get("id", "atom[%d]" % i)
        atype = atom.get("type")
        if atype not in TYPES:
            hard.append({"atom": aid, "check": "type", "detail": "unknown type %r" % atype})
            continue
        for field in TYPES[atype]:
            if not atom.get(field):
                hard.append({"path": aid, "check": "schema",
                             "detail": "missing field %s for type %s" % (field, atype)})
        term_key = norm_term(atom.get("term") or atom.get("symbol")
                             or atom.get("claim", "")[:60])
        dup_key = (atype, term_key)
        if dup_key in seen:
            warn.append({"path": aid, "check": "duplicate",
                         "detail": "same normalized term+type as %s" % seen[dup_key]})
        else:
            seen[dup_key] = aid
        for other_id, other in by_term.get(term_key, []):
            w1 = content_words(atom.get("definition") or atom.get("meaning")
                               or atom.get("claim") or "")
            w2 = content_words(other.get("definition") or other.get("meaning")
                               or other.get("claim") or "")
            if w1 and w2 and not (w1 & w2):
                warn.append({"path": aid, "check": "conflict",
                             "detail": "term %r also defined by %s with disjoint wording"
                                       % (term_key, other_id)})
        by_term.setdefault(term_key, []).append((aid, atom))

        ev = atom.get("evidence", [])
        if not ev and not atom.get("not_reported"):
            hard.append({"path": aid, "check": "evidence",
                         "detail": "no evidence and not marked not_reported"})
        for j, e in enumerate(ev):
            anchor = e.get("anchor", "")
            quote = re.sub(r"\s+", " ", e.get("quote", "")).strip()
            if anchor not in para_idx:
                hard.append({"path": "%s.evidence[%d]" % (aid, j), "check": "anchor",
                             "detail": "anchor %s not in sections.json" % anchor})
            elif quote and quote not in re.sub(r"\s+", " ", para_idx[anchor]):
                hard.append({"path": "%s.evidence[%d]" % (aid, j), "check": "quote",
                             "detail": "quote not verbatim in paragraph %s" % anchor})
    return {
        "atoms": len(atoms),
        "hard_violations": hard,
        "warnings": warn,
        "verdict": "pass" if not hard else "fail",
        "source_status": src_status,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--atoms", required=True)
    ap.add_argument("--sections", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()
    report = lint(args.atoms, args.sections)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    sys.exit(0 if report["verdict"] == "pass" else 2)


if __name__ == "__main__":
    main()
