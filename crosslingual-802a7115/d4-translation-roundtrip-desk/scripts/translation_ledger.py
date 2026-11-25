#!/usr/bin/env python3
"""translation_ledger.py — controlled-translation ledger with round-trip QC.

Manages translation entries for cross-lingual query terms. Every entry is
Agent-supplied (this tool NEVER translates on its own) and carries:
concept_id, source_lang, target_lang, term, back_translation, service,
service_version, evidence. The tool:

1. validates ledger schema and normalizes entries;
2. runs ROUND-TRIP QC: compares back_translation against the concept label
   and same-language variants (NFKD-folded token overlap) and marks each
   entry verified / degraded / no-evidence with an explicit reason;
3. flags "surface-match but semantic-drift" risk: term is lexically close
   to the label in the target script but the back-translation disagrees —
   the classic mistranslation false-positive pattern;
4. emits the to_translate list (concept x language gaps against the
   declared target languages) and per-entry usage policy
   (full-weight / half-weight / hold-for-review).

Stdlib only, offline. Exit code always 0.
"""
import argparse
import json
import os
import re
import sys
import unicodedata

REQUIRED = ("concept_id", "target_lang", "term")


def fold(text):
    nfkd = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def tokens(text):
    return set(re.findall(r"[a-z0-9一-鿿぀-ヿ]+", fold(text)))


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def load_entries(path, notes):
    if not path or not os.path.exists(path):
        notes.append(f"translations file not found: {path}")
        return []
    with open(path, encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as exc:
            notes.append(f"JSON error in {path}: {exc}")
            return []
    entries = data.get("translations") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        notes.append(f"{path}: expected a list or {{'translations': [...]}}")
        return []
    return [e for e in entries if isinstance(e, dict)]


def qc_entries(entries, concepts, notes):
    by_concept = {}
    for c in concepts:
        by_concept[c.get("concept_id")] = c
    report = []
    for i, e in enumerate(entries):
        eid = e.get("entry_id") or f"E{i+1:03d}"
        missing = [k for k in REQUIRED if not str(e.get(k, "")).strip()]
        rec = {"entry_id": eid, "concept_id": e.get("concept_id"),
               "target_lang": e.get("target_lang"), "term": e.get("term"),
               "back_translation": e.get("back_translation"),
               "service": e.get("service"), "service_version": e.get("service_version"),
               "evidence": e.get("evidence")}
        if missing:
            rec.update(status="invalid", usage="hold-for-review",
                       reason=f"missing required fields: {', '.join(missing)}")
            report.append(rec)
            continue
        concept = by_concept.get(e["concept_id"], {})
        label = concept.get("label") or ""
        same_lang = [v.get("term", "") for v in concept.get("variants", [])
                     if v.get("lang") == e["target_lang"]]
        bt = (e.get("back_translation") or "").strip()
        term_toks, label_toks = tokens(e["term"]), tokens(label)
        bt_toks = tokens(bt)
        bt_vs_label = jaccard(bt_toks, label_toks)
        bt_vs_variants = max([jaccard(bt_toks, tokens(v)) for v in same_lang]
                             or [0.0])
        term_vs_label = jaccard(term_toks, label_toks)
        if not bt:
            rec.update(status="no-evidence", usage="half-weight",
                       roundtrip_score=None,
                       reason="no back_translation supplied; keep source-declared "
                              "confidence and mark round-trip:no-evidence")
        else:
            score = max(bt_vs_label, bt_vs_variants)
            rec["roundtrip_score"] = round(score, 3)
            if score >= 0.5 or (bt_toks & label_toks):
                rec.update(status="verified", usage="full-weight",
                           reason="back-translation overlaps concept label or "
                                  "same-language variant")
            else:
                surface_close = term_vs_label >= 0.5
                rec.update(
                    status="degraded", usage="half-weight",
                    risk=("surface-match-semantic-drift" if surface_close
                          else "roundtrip-mismatch"),
                    reason=f"back-translation '{bt}' does not overlap label "
                           f"'{label}' (score {score:.2f})" +
                           ("; term is lexically close to the label — "
                            "classic false-positive pattern" if surface_close
                            else ""))
        if not e.get("service"):
            rec.setdefault("notes", []).append(
                "translation service not declared; record it for reproducibility")
        report.append(rec)
    return report


def to_translate(concepts, entries, target_langs):
    have = {(e.get("concept_id"), e.get("target_lang"))
            for e in entries
            if str(e.get("term", "")).strip()}
    gaps = []
    for c in concepts:
        existing = {v.get("lang") for v in c.get("variants", [])}
        for lang in target_langs:
            if lang in existing:
                continue
            if (c.get("concept_id"), lang) not in have:
                gaps.append({"concept_id": c.get("concept_id"),
                             "label": c.get("label"), "missing_lang": lang})
    return gaps


def render_report(report, gaps):
    lines = ["# Translation round-trip QC report", ""]
    lines.append("| entry | concept | lang | term | back-translation | status | usage | reason |")
    lines.append("|-|-|-|-|-|-|-|-|")
    for r in report:
        lines.append("| {eid} | {cid} | {lang} | {term} | {bt} | {st} | {use} | {why} |".format(
            eid=r["entry_id"], cid=r.get("concept_id"), lang=r.get("target_lang"),
            term=r.get("term"), bt=r.get("back_translation") or "—",
            st=r.get("status"), use=r.get("usage"),
            why=(r.get("reason") or "").replace("|", "/")))
    if gaps:
        lines += ["", "## to_translate (concept × language gaps)", ""]
        for g in gaps:
            lines.append(f"- `{g['concept_id']}` ({g['label']}): missing **{g['missing_lang']}**")
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--concepts", required=True,
                    help="concept table JSON ({concepts:[{concept_id,label,variants}]})")
    ap.add_argument("--translations", required=False, default=None,
                    help="Agent-supplied translation entries JSON")
    ap.add_argument("--langs", default="en,pt,es,de,ja,zh",
                    help="comma-separated target languages")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    notes = []
    with open(args.concepts, encoding="utf-8") as fh:
        concepts = json.load(fh).get("concepts", [])
    entries = load_entries(args.translations, notes) if args.translations else []
    report = qc_entries(entries, concepts, notes)
    langs = [x.strip() for x in args.langs.split(",") if x.strip()]
    gaps = to_translate(concepts, entries, langs)
    counts = {}
    for r in report:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    payload = {
        "status": "ok",
        "entries": report,
        "to_translate": gaps,
        "counts": {"entries": len(report), "by_status": counts,
                   "gaps": len(gaps)},
        "parse_notes": notes,
    }
    with open(os.path.join(args.out, "ledger.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "roundtrip_report.md"), "w", encoding="utf-8") as fh:
        fh.write(render_report(report, gaps))
    print(json.dumps({"status": "ok", "entries": len(report),
                      "by_status": counts, "gaps": len(gaps)},
                     ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
