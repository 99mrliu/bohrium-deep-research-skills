#!/usr/bin/env python3
"""pipeline.py -- freeze / apply-edits / export pipeline for genre-register-polish.

Subcommands:
  prepare     --text <f> [--doc id] --out prepared.json
      Freeze the source into sentence units with stable IDs (s0001, ...),
      paragraph indices, join separators, and per-unit protected tokens
      (numbers, citations, figure/table pointers).
  apply-edits --prepared <p.json> --edits <e.json> [--doc key] --out applied.json
      Apply a JSON batch of edits. Every edit MUST carry a review record
      (review.decision == "approve" plus a non-empty review.reason); unreviewed
      edits are reverted. Protected tokens of the original unit are compared
      against the new text; losing any token reverts the edit.
  export      --applied <a.json> [--applied ...] [--scorecard-md <f> ...]
              --outdir <dir>
      Write polished.md, changes.json, audit.json, and (when scorecard
      markdown is given) register-scorecard.md.

Edit entry schema:
  {"unit_id": "s0002", "new_text": "...", "type": "register/colloquial-fix",
   "reason": "why this change", "review": {"decision": "approve",
   "reason": "why the reviewer-agent accepts it"}}

Python 3 standard library only. Deterministic: no randomness, no timestamps.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter

EN_ABBREV = {
    "fig", "figs", "dr", "prof", "mr", "mrs", "ms", "st", "vs", "etc", "al",
    "cf", "ca", "approx", "no", "nos", "vol", "vols", "ed", "eds", "pp",
    "sec", "eq", "eqs", "ref", "refs", "inc", "ltd",
}


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _is_cjk(s):
    return any("一" <= c <= "鿿" for c in s)


# --------------------------------------------------------------------------
# prepare: freeze into sentence units
# --------------------------------------------------------------------------

def split_sentences(par):
    """Split one paragraph into (sentence, sep_after) pairs."""
    if _is_cjk(par):
        units, buf = [], ""
        for ch in par:
            buf += ch
            if ch in "。！？；":
                if buf.strip():
                    units.append((buf.strip(), ""))
                buf = ""
        if buf.strip():
            units.append((buf.strip(), ""))
        return units

    units = []
    i, n, start = 0, len(par), 0
    while i < n:
        c = par[i]
        if c in ".!?":
            nxt = par[i + 1] if i + 1 < n else ""
            prv = par[i - 1] if i > 0 else ""
            if c == ".":
                if prv.isdigit() and nxt.isdigit():  # decimal like 12.5
                    i += 1
                    continue
                m = re.search(r"([A-Za-z]+)$", par[:i])
                if m and m.group(1).lower() in EN_ABBREV:
                    i += 1
                    continue
            if nxt == "" or nxt in " \t\n":
                j = i + 1
                while j < n and par[j] in "\"')]":
                    j += 1
                sent = par[start:j].strip()
                k = j
                while k < n and par[k] in " \t\n":
                    k += 1
                if sent:
                    units.append((sent, " " if k > j else ""))
                start = k
                i = k
                continue
        i += 1
    tail = par[start:].strip()
    if tail:
        units.append((tail, ""))
    return units


PROT_PATTERNS = [
    r"\[\d+(?:\s*[-,]\s*\d+)*\]",                       # [7], [1-3], [2, 5]
    r"\([A-Z][A-Za-z\-]+(?:\s+et\s+al\.)?(?:\s+and\s+[A-Z][A-Za-z\-]+)?,?\s+\d{4}[a-z]?\)",
    r"\b(?:Fig(?:ure)?s?|Table|Equation|Eq|Section|Sec|Chapter)\.?\s*\d+(?:\.\d+)*\b",
    r"[图表式]\s*\d+(?:\.\d+)*",                          # 图2 表1 式(3)->式 3
    r"\d+(?:\.\d+)?\s*%",                                # 12.5%
]
BARE_NUM = re.compile(r"\b\d+(?:\.\d+)?\b")


def protected_tokens(text):
    spans, toks = [], []
    for pat in PROT_PATTERNS:
        for m in re.finditer(pat, text):
            spans.append(m.span())
            toks.append(m.group(0))
    for m in BARE_NUM.finditer(text):
        if any(s <= m.start() < e for s, e in spans):
            continue
        toks.append(m.group(0))
    return sorted(toks)


def cmd_prepare(args):
    text = _read(args.text).replace("\r\n", "\n").replace("\r", "\n")
    doc_id = args.doc or os.path.splitext(os.path.basename(args.text))[0]
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    units = []
    idx = 0
    for pi, par in enumerate(paras):
        flat = re.sub(r"\s*\n\s*", " ", par)
        for sent, sep in split_sentences(flat):
            idx += 1
            units.append({
                "id": "s%04d" % idx,
                "para": pi,
                "sep_after": sep,
                "text": sent,
                "protected": protected_tokens(sent),
            })
    out = {
        "doc_id": doc_id,
        "source_file": args.text,
        "source_sha256": _sha(text),
        "unit_count": len(units),
        "units": units,
        "note": "Source frozen into sentence units. Edits must reference unit "
                "IDs and pass the review + protected-token gates.",
    }
    _write_json(args.out, out)
    print("prepare: doc=%s units=%d sha256=%s"
          % (doc_id, len(units), out["source_sha256"][:12]))
    return 0


# --------------------------------------------------------------------------
# apply-edits: review gate + protected-token gate
# --------------------------------------------------------------------------

def _count_token(text, token):
    pat = re.escape(token).replace(r"\ ", r"\s+")
    return len(re.findall(pat, text))


def cmd_apply_edits(args):
    prepared = json.loads(_read(args.prepared))
    edits_data = json.loads(_read(args.edits))
    if isinstance(edits_data, dict):
        key = args.doc or prepared["doc_id"]
        edits = edits_data.get(key, [])
    else:
        edits = edits_data

    units = {u["id"]: u for u in prepared["units"]}
    current = {u["id"]: u["text"] for u in prepared["units"]}
    changes, reverted = [], []

    for e in edits:
        uid = e.get("unit_id", "")
        base = {"unit_id": uid, "type": e.get("type", ""),
                "reason": e.get("reason", "")}
        if uid not in units:
            reverted.append(dict(base, status="reverted-unknown-unit",
                                 detail="no such unit in prepared source"))
            continue
        rev = e.get("review") or {}
        if rev.get("decision") != "approve" or not str(rev.get("reason", "")).strip():
            reverted.append(dict(
                base, status="reverted-unreviewed",
                detail="review gate: every edit needs decision=approve plus a "
                       "non-empty review.reason; unreviewed edits are reverted"))
            continue
        new = str(e.get("new_text", "")).strip()
        if not new:
            reverted.append(dict(base, status="reverted-empty",
                                 detail="new_text is empty"))
            continue
        need = Counter(units[uid]["protected"])
        missing = [tok for tok, cnt in need.items()
                   if _count_token(new, tok) < cnt]
        if missing:
            reverted.append(dict(
                base, status="reverted-protected-token",
                detail="protected tokens lost: " + ", ".join(sorted(set(missing)))))
            continue
        before = current[uid]
        current[uid] = new
        changes.append(dict(base, before=before, after=new,
                            review_decision="approve",
                            review_reason=rev.get("reason", ""),
                            status="applied"))

    out_units = [{
        "id": u["id"], "para": u["para"], "sep_after": u["sep_after"],
        "original": u["text"], "final": current[u["id"]],
        "changed": current[u["id"]] != u["text"],
    } for u in prepared["units"]]
    out = {
        "doc_id": prepared["doc_id"],
        "source_sha256": prepared["source_sha256"],
        "units": out_units,
        "changes": changes,
        "reverted": reverted,
        "stats": {
            "units": len(out_units),
            "edits_submitted": len(edits),
            "applied": len(changes),
            "reverted": len(reverted),
        },
    }
    _write_json(args.out, out)
    print("apply-edits: doc=%s applied=%d reverted=%d"
          % (prepared["doc_id"], len(changes), len(reverted)))
    return 0


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------

def _polished_text(doc):
    paras = {}
    for u in doc["units"]:
        paras.setdefault(u["para"], []).append(u["final"] + u["sep_after"])
    return "\n\n".join("".join(paras[p]).rstrip() for p in sorted(paras))


def cmd_export(args):
    docs = [json.loads(_read(p)) for p in args.applied]
    os.makedirs(args.outdir, exist_ok=True)

    # polished.md
    parts = ["# Polished text (synthetic example output)\n"]
    polished_map = {}
    for d in docs:
        t = _polished_text(d)
        polished_map[d["doc_id"]] = t
        parts.append("\n## %s\n\n%s\n" % (d["doc_id"], t))
    with open(os.path.join(args.outdir, "polished.md"), "w", encoding="utf-8") as f:
        f.write("".join(parts))

    # changes.json
    changes_doc = {
        "docs": [{"doc_id": d["doc_id"],
                  "applied": d["changes"], "reverted": d["reverted"]}
                 for d in docs],
        "total_applied": sum(len(d["changes"]) for d in docs),
        "total_reverted": sum(len(d["reverted"]) for d in docs),
    }
    _write_json(os.path.join(args.outdir, "changes.json"), changes_doc)

    # audit.json
    audit_docs = []
    for d in docs:
        audit_docs.append({
            "doc_id": d["doc_id"],
            "source_sha256": d["source_sha256"],
            "units": d["stats"]["units"],
            "edits_submitted": d["stats"]["edits_submitted"],
            "applied": d["stats"]["applied"],
            "reverted": [{"unit_id": r["unit_id"], "status": r["status"],
                          "detail": r.get("detail", "")}
                         for r in d["reverted"]],
            "review_gate": ("enforced: every applied edit carries "
                            "decision=approve and a non-empty review reason"),
            "protected_token_gate": ("enforced: edits losing a number, "
                                     "citation or figure/table pointer were "
                                     "reverted"),
            "polished_sha256": _sha(polished_map[d["doc_id"]]),
        })
    audit = {
        "audit_version": "1.0",
        "docs": audit_docs,
        "determinism": ("no timestamps or random values; re-running the "
                        "pipeline on identical inputs yields byte-identical "
                        "outputs"),
    }
    _write_json(os.path.join(args.outdir, "audit.json"), audit)

    # register-scorecard.md
    if args.scorecard_md:
        lines = ["# Register scorecard (before / after)\n",
                 "Synthetic example output of genre-register-polish.\n"]
        for p in args.scorecard_md:
            lines.append("\n" + _read(p).strip() + "\n")
        with open(os.path.join(args.outdir, "register-scorecard.md"),
                  "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    print("export: outdir=%s docs=%d files=polished.md,changes.json,audit.json%s"
          % (args.outdir, len(docs),
             ",register-scorecard.md" if args.scorecard_md else ""))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Freeze / apply-edits / export pipeline.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare", help="freeze source into sentence units")
    p.add_argument("--text", required=True)
    p.add_argument("--doc", help="document id (default: file stem)")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_prepare)

    p = sub.add_parser("apply-edits", help="apply a reviewed edit batch")
    p.add_argument("--prepared", required=True)
    p.add_argument("--edits", required=True)
    p.add_argument("--doc", help="key when the edits file is keyed by document")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_apply_edits)

    p = sub.add_parser("export", help="write polished.md / changes.json / audit.json")
    p.add_argument("--applied", action="append", required=True)
    p.add_argument("--scorecard-md", action="append",
                   help="markdown from register.py scorecard --md")
    p.add_argument("--outdir", required=True)
    p.set_defaults(func=cmd_export)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
