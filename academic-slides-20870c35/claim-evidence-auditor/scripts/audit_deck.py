#!/usr/bin/env python3
"""Audit a delivered PPTX against a source index and claim ledger.

Implements gates 1-4 of references/audit-playbook.md:
  1. number gate    -- slide/notes numeric tokens must appear in the source text
  2. citation gate  -- exhibit references on slides must exist in the registry
  3. strength gate  -- slide wording must not exceed bound claims' strength
  4. coverage gate  -- coverage ledger must disposition every registry exhibit

Usage:
  python3 audit_deck.py deck.pptx --index source_index.json
          [--claims claims.json] [--coverage coverage.json] [--out audit_report.json]

Needs python-pptx. Exit 0 with a report; the report's `summary.blocking`
tells whether delivery should proceed, exit code stays 0 so the report is
always written -- the agent decides, nothing is hidden.
"""
import argparse
import json
import re
import sys

NUM_RE = re.compile(r"(?<![\w.])(\d[\d,]*\.?\d*(?:[eE][-+]?\d+)?)\s*(%|‰|×|x)?")
EXHIBIT_REF_RE = re.compile(
    r"\b(Figure|Fig\.?|Table|Section|Sec\.?)\s*(S?\d+[A-Za-z]?)", re.IGNORECASE)
STRENGTH_ORDER = ["speculative", "contextual", "preliminary", "established"]
STRONG_WORDS = {
    "established": [r"\bprove[ds]?\b", r"\bdemonstrate[sd]?\b", r"\bconfirm[sd]?\b",
                    r"\bconclusive", r"\bguarantee", r"证实", r"证明"],
    "preliminary": [r"\bprove[ds]?\b", r"\bdemonstrate[sd]?\b", r"\bestablish(?:es|ed)?\b",
                    r"证实", r"证明"],
    "contextual": [r"\bprove[ds]?\b", r"\bdemonstrate[sd]?\b", r"\bsignificantly\b",
                   r"\boutperform", r"证实", r"显著优于", r"证明"],
    "speculative": [r"\bprove[ds]?\b", r"\bdemonstrate[sd]?\b", r"\bshow[sd]?\s+that\b",
                    r"\bis\b", r"\bare\b", r"表明", r"证实", r"证明"],
}
WHITELIST_CONTEXT = re.compile(
    r"^(19|20)\d\d$")  # years are presentation furniture, not data


def norm_num(tok):
    return tok.replace(",", "").rstrip(".")


def deck_texts(path):
    try:
        from pptx import Presentation
    except ImportError:
        sys.exit("python-pptx not available; record the audit as unverified")
    prs = Presentation(path)
    slides = []
    for idx, slide in enumerate(prs.slides, 1):
        texts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                texts.append(shape.text_frame.text)
            if shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        texts.append(cell.text)
        notes = ""
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text
        slides.append({"index": idx, "text": "\n".join(texts), "notes": notes})
    return slides


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("deck")
    ap.add_argument("--index", required=True)
    ap.add_argument("--claims")
    ap.add_argument("--coverage")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.index, encoding="utf-8") as fh:
        index = json.load(fh)
    claims = []
    if args.claims:
        with open(args.claims, encoding="utf-8") as fh:
            claims = json.load(fh).get("claims", [])
    coverage = None
    if args.coverage:
        with open(args.coverage, encoding="utf-8") as fh:
            coverage = json.load(fh)

    source_text = "\n".join(p["text"] for p in index["pages"])
    source_norm = source_text.replace(",", "").replace("−", "-")
    anchors = {norm_num(n) for c in claims for n in
               NUM_RE.findall(c.get("anchor", "")) for n in [n[0]] if n}

    registry = {re.sub(r"\s+", " ", e["id"]).lower(): e for e in index["exhibits"]}
    slides = deck_texts(args.deck)

    findings = {"number_gate": [], "citation_gate": [],
                "strength_gate": [], "coverage_gate": []}

    # Gate 1: numbers
    for sl in slides:
        blob = sl["text"] + "\n" + sl["notes"]
        for tok, unit in NUM_RE.findall(blob):
            n = norm_num(tok)
            if not n or n in ("0", "1") or WHITELIST_CONTEXT.match(n):
                continue
            if n in anchors or n in source_norm:
                continue
            findings["number_gate"].append({
                "slide": sl["index"], "value": tok + (unit or ""),
                "class": "not_in_source",
                "detail": "numeric token not found in source index or claim anchors"})

    # Gate 2: exhibit citations
    for sl in slides:
        blob = sl["text"] + "\n" + sl["notes"]
        for kind, num in EXHIBIT_REF_RE.findall(blob):
            if kind.lower().startswith(("sec",)):
                continue
            label = f"{'table' if kind.lower().startswith('tab') else 'figure'} {num}".lower()
            if not any(label == key or key.startswith(f"{label}") or
                       key.replace("fig.", "figure").startswith(label)
                       for key in registry):
                findings["citation_gate"].append({
                    "slide": sl["index"], "reference": f"{kind} {num}",
                    "class": "unresolved",
                    "detail": "exhibit reference matches no registry caption"})

    # Gate 3: strength wording
    claim_by_slide = {}
    # optional mapping when claims carry slide bindings via page plan annotations
    for c in claims:
        for sl_idx in c.get("slides", []):
            claim_by_slide.setdefault(sl_idx, []).append(c)
    for sl in slides:
        bound = claim_by_slide.get(sl["index"], [])
        if not bound:
            continue
        max_strength = max(STRENGTH_ORDER.index(c["strength"]) for c in bound)
        allowed_ceiling = STRENGTH_ORDER[max_strength]
        blob = sl["text"]
        for level in STRENGTH_ORDER[max_strength::-1]:
            for pat in STRONG_WORDS[level]:
                if re.search(pat, blob, re.IGNORECASE):
                    findings["strength_gate"].append({
                        "slide": sl["index"], "pattern": pat,
                        "bound_strength": allowed_ceiling,
                        "class": "strength_upgrade",
                        "detail": f"wording matches '{pat}' but bound claims are at most '{allowed_ceiling}'"})

    # Gate 4: coverage
    if coverage is not None:
        dispositioned = {}
        for entry in coverage.get("exhibits", []):
            key = re.sub(r"\s+", " ", entry.get("exhibit", "")).lower()
            if key in dispositioned:
                findings["coverage_gate"].append({
                    "exhibit": entry.get("exhibit"), "class": "duplicate_disposition",
                    "detail": "exhibit dispositioned twice"})
            dispositioned[key] = entry.get("disposition", "")
        for key in registry:
            if key not in dispositioned:
                findings["coverage_gate"].append({
                    "exhibit": key, "class": "missing_disposition",
                    "detail": "registry exhibit absent from coverage ledger"})
        for key, disp in dispositioned.items():
            if disp.startswith("omitted") and ":" not in disp:
                findings["coverage_gate"].append({
                    "exhibit": key, "class": "omission_without_reason",
                    "detail": "omission must carry a reason after a colon"})

    blocking = (len(findings["citation_gate"]) + len(findings["coverage_gate"]) +
                sum(1 for f in findings["number_gate"] if f["class"] == "not_in_source") +
                len(findings["strength_gate"]))
    report = {
        "deck": args.deck,
        "slides_checked": len(slides),
        "gates": findings,
        "visual_gate": "agent-performed; record verdicts here before delivery",
        "summary": {"blocking_findings": blocking,
                    "verdict": "clean" if blocking == 0 else "findings_open"},
        "open_findings": []
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    print(f"audit: {len(slides)} slides, blocking findings: {blocking} -> {args.out}")
    for gate, items in findings.items():
        if items:
            print(f"  {gate}: {len(items)} finding(s); first: {items[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
