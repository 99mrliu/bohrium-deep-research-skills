"""verify_fidelity.py — THE SPIKE of source-veritas-deck.

Gate executed in `finish` BEFORE any slide is built. For every slide bullet
and claim in slide_plan.json:

  (a) every numeric token (percentages, decimals, units) must appear VERBATIM
      in the text of the evidence-anchored corpus entries. If it only appears
      elsewhere in the corpus the token is flagged "loose"; if nowhere, the
      bullet is UNVERIFIED.
  (b) every evidence ref (page / figure / table / section) must resolve to an
      existing corpus entry or figure file.
  (c) every figure path must exist and its sha256 must match the corpus
      ledger (byte-identical provenance — no silent re-render/substitution).
  (d) quoted snippets must be verbatim substrings of source text
      (whitespace-normalized).

Verdicts: verified | loose | unverified.  Any unverified bullet is either
DROPPED automatically (default; logged into change_log and
fidelity_report.json) or fails the gate (--strict).  Unverified numbers are
NEVER silently kept on slides.

Usage:
  python3 verify_fidelity.py --plan slide_plan.json --corpus-dir /app/work/corpus \
      --report /app/output/fidelity_report.json [--out-plan plan.verified.json] \
      [--strict] [--change-log /app/work/change_log.json]
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

PAGE_REF_RE = re.compile(r"(?:p\.?|page)\s*(\d+)", re.IGNORECASE)
FIG_REF_RE = re.compile(r"(?:figure|fig\.?)\s*(\d+)", re.IGNORECASE)


class Verdict:
    VERIFIED = "verified"
    LOOSE = "loose"
    UNVERIFIED = "unverified"


def _anchor_entries(slide: dict, text_entries: list[dict],
                    figures: list[dict]) -> list[dict]:
    """Corpus text entries anchored by this slide's evidence refs."""
    anchored = []
    pages = set()
    for ev in slide.get("evidence", []) or []:
        ref = str(ev.get("ref", ""))
        for m in PAGE_REF_RE.finditer(ref):
            pages.add(int(m.group(1)))
        for m in FIG_REF_RE.finditer(ref):
            n = m.group(1)
            for fig in figures:
                if fig.get("label") and re.search(rf"\b{n}\b", fig["label"]):
                    pages.add(fig["page"])
        if ev.get("type") == "page":
            try:
                pages.add(int(re.sub(r"\D", "", ref) or 0))
            except ValueError:
                pass
    for fig_spec in slide.get("figures", []) or []:
        ref = str(fig_spec.get("ref", ""))
        m = FIG_REF_RE.search(ref)
        if m:
            for fig in figures:
                if fig.get("label") and re.search(rf"\b{m.group(1)}\b", fig["label"]):
                    pages.add(fig["page"])
    if pages:
        anchored = [e for e in text_entries if e["page"] in pages]
    return anchored


def _check_number(tok: dict, anchored_text: str, full_text: str) -> tuple[str, str]:
    core = tok["core"]
    if common.core_in_text(core, anchored_text):
        return Verdict.VERIFIED, f"'{tok['raw']}' verbatim in anchored evidence"
    if common.core_in_text(core, full_text):
        return Verdict.LOOSE, f"'{tok['raw']}' found in corpus but NOT in anchored evidence"
    return Verdict.UNVERIFIED, f"numeric token '{tok['raw']}' absent from corpus"


def _check_quote(quote: str, full_text: str) -> tuple[bool, str]:
    q = common.norm_ws(quote)
    if not q:
        return True, "empty quote"
    if q in full_text:
        return True, "quote is verbatim substring of source"
    return False, "quote is NOT a verbatim substring of source text"


def _resolve_figure(fig_spec: dict, figures: list[dict],
                    corpus_dir: str) -> tuple[str, str]:
    """Check figure file existence + sha256 against ledger."""
    path = fig_spec.get("path", "")
    ref = str(fig_spec.get("ref", ""))
    entry = None
    for fig in figures:
        ledger_path = os.path.join(corpus_dir, fig["file"])
        if os.path.abspath(ledger_path) == os.path.abspath(path):
            entry = fig
            break
        m = FIG_REF_RE.search(ref)
        if m and fig.get("label") and re.search(rf"\b{m.group(1)}\b", fig["label"]):
            entry = fig
            break
    if entry is None:
        return Verdict.UNVERIFIED, f"figure '{ref or path}' not in corpus ledger"
    ledger_path = os.path.join(corpus_dir, entry["file"])
    if not os.path.exists(path):
        return Verdict.UNVERIFIED, f"figure file missing: {path}"
    actual = common.sha256_file(path)
    if actual != entry["sha256"]:
        return Verdict.UNVERIFIED, (
            f"figure '{ref}' sha256 mismatch (ledger {entry['sha256'][:12]}… "
            f"vs file {actual[:12]}…): byte-identical provenance violated")
    if os.path.abspath(path) != os.path.abspath(ledger_path):
        return Verdict.LOOSE, "figure bytes match ledger but path differs from ledger file"
    return Verdict.VERIFIED, f"figure '{ref or entry['fig_id']}' byte-identical to ledger"


def _check_evidence_ref(ev: dict, text_entries: list[dict], figures: list[dict],
                        sections: list[dict], full_text: str) -> tuple[str, str]:
    etype = ev.get("type", "page")
    ref = str(ev.get("ref", ""))
    if etype == "page":
        m = PAGE_REF_RE.search(ref) or re.search(r"(\d+)", ref)
        if not m:
            return Verdict.UNVERIFIED, f"unparsable page ref '{ref}'"
        p = int(m.group(1))
        if any(e["page"] == p for e in text_entries):
            return Verdict.VERIFIED, f"page {p} exists in corpus"
        return Verdict.UNVERIFIED, f"page {p} not in corpus"
    if etype == "figure":
        m = FIG_REF_RE.search(ref)
        if m and any(f.get("label") and re.search(rf"\b{m.group(1)}\b", f["label"])
                     for f in figures):
            return Verdict.VERIFIED, f"figure ref '{ref}' resolves to ledger figure"
        return Verdict.UNVERIFIED, f"figure ref '{ref}' resolves to no ledger figure"
    if etype == "section":
        r = common.norm_ws(ref).lower()
        if any(r in s["heading"].lower() or s["heading"].lower() in r
               for s in sections):
            return Verdict.VERIFIED, f"section '{ref}' detected in corpus"
        return Verdict.UNVERIFIED, f"section '{ref}' not detected in corpus"
    # table or other: fall back to quote check
    quote = ev.get("quote", "")
    if quote:
        ok, msg = _check_quote(quote, full_text)
        return (Verdict.VERIFIED if ok else Verdict.UNVERIFIED), msg
    return Verdict.LOOSE, f"evidence type '{etype}' weakly checked"


def verify_plan(plan: dict, corpus_dir: str,
                change_log: list | None = None) -> dict:
    entries = common.read_corpus(os.path.join(corpus_dir, "corpus.jsonl"))
    text_entries = [e for e in entries if e.get("kind") == "text"]
    figures = [e for e in entries if e.get("kind") == "figure"]
    sections = [e for e in entries if e.get("kind") == "section"]
    full_text = common.corpus_full_text(entries)

    report = {"corpus_dir": os.path.abspath(corpus_dir),
              "slides": [], "summary": {"verified": 0, "loose": 0,
                                        "unverified": 0, "dropped": 0},
              "gate": "pass"}
    order = {Verdict.VERIFIED: 0, Verdict.LOOSE: 1, Verdict.UNVERIFIED: 2}

    for sidx, slide in enumerate(plan.get("slides", [])):
        anchored = _anchor_entries(slide, text_entries, figures)
        anchored_text = common.norm_ws(" ".join(e["text"] for e in anchored)) \
            if anchored else ""
        srec = {"slide": sidx, "title": slide.get("title", ""),
                "bullets": [], "figures": [], "evidence": [],
                "verdict": Verdict.VERIFIED}
        worst = Verdict.VERIFIED

        items = []
        if slide.get("claim"):
            items.append(("claim", slide["claim"]))
        for b in slide.get("bullets", []) or []:
            items.append(("bullet", b))

        for kind, text in items:
            bverdict = Verdict.VERIFIED
            details = []
            if not anchored:
                bverdict = Verdict.LOOSE
                details.append("no evidence anchors on slide: corpus-wide check")
            for tok in common.extract_number_tokens(text):
                v, msg = _check_number(tok, anchored_text or full_text, full_text)
                if not anchored and v == Verdict.VERIFIED:
                    v = Verdict.LOOSE
                    msg += " (loose: no anchor)"
                details.append(msg)
                if order[v] > order[bverdict]:
                    bverdict = v
            rec = {"kind": kind, "text": text, "verdict": bverdict,
                   "detail": "; ".join(details) or "no numeric tokens",
                   "anchor_pages": sorted({e["page"] for e in anchored})}
            srec["bullets"].append(rec)
            report["summary"][bverdict] += 1
            if order[bverdict] > order[worst]:
                worst = bverdict

        for fig_spec in slide.get("figures", []) or []:
            v, msg = _resolve_figure(fig_spec, figures, corpus_dir)
            srec["figures"].append({"ref": fig_spec.get("ref", ""),
                                    "path": fig_spec.get("path", ""),
                                    "verdict": v, "detail": msg})
            report["summary"][v] += 1
            if order[v] > order[worst]:
                worst = v

        for ev in slide.get("evidence", []) or []:
            v, msg = _check_evidence_ref(ev, text_entries, figures, sections,
                                         full_text)
            quote = ev.get("quote", "")
            if quote:
                qok, qmsg = _check_quote(quote, full_text)
                if not qok:
                    v, msg = Verdict.UNVERIFIED, msg + "; " + qmsg
            srec["evidence"].append({"type": ev.get("type"), "ref": ev.get("ref"),
                                     "verdict": v, "detail": msg})
            report["summary"][v] += 1
            if order[v] > order[worst]:
                worst = v

        srec["verdict"] = worst
        report["slides"].append(srec)

    return report


def drop_unverified(plan: dict, report: dict, change_log: list) -> dict:
    """Return a copy of plan with unverified bullets/figures/evidence removed."""
    import copy
    clean = copy.deepcopy(plan)
    for srec, slide in zip(report["slides"], clean.get("slides", [])):
        # bullets: drop unverified (claim kept only if verified/loose)
        bad_texts = {b["text"] for b in srec["bullets"]
                     if b["verdict"] == Verdict.UNVERIFIED}
        if bad_texts:
            kept = []
            for b in slide.get("bullets", []) or []:
                if b in bad_texts:
                    change_log.append({
                        "action": "drop-bullet", "slide": srec["slide"],
                        "title": srec["title"], "bullet": b,
                        "reason": "unverified by fidelity gate "
                                  "(number/quote absent from source corpus)"})
                    report["summary"]["dropped"] += 1
                else:
                    kept.append(b)
            slide["bullets"] = kept
            if slide.get("claim") in bad_texts:
                change_log.append({
                    "action": "drop-claim", "slide": srec["slide"],
                    "claim": slide["claim"],
                    "reason": "unverified by fidelity gate"})
                slide["claim"] = ""
        bad_figs = {f["path"] for f in srec["figures"]
                    if f["verdict"] == Verdict.UNVERIFIED}
        if bad_figs:
            kept = []
            for fg in slide.get("figures", []) or []:
                if fg.get("path") in bad_figs:
                    change_log.append({
                        "action": "drop-figure", "slide": srec["slide"],
                        "ref": fg.get("ref"), "path": fg.get("path"),
                        "reason": "figure failed ledger provenance check"})
                    report["summary"]["dropped"] += 1
                else:
                    kept.append(fg)
            slide["figures"] = kept
        bad_ev = {e["ref"] for e in srec["evidence"]
                  if e["verdict"] == Verdict.UNVERIFIED}
        if bad_ev:
            slide["evidence"] = [e for e in slide.get("evidence", []) or []
                                 if e.get("ref") not in bad_ev]
    return clean


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--corpus-dir", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--out-plan", default=None,
                    help="write cleaned plan (unverified dropped) here")
    ap.add_argument("--strict", action="store_true",
                    help="fail the gate instead of dropping unverified bullets")
    ap.add_argument("--change-log", default=None)
    args = ap.parse_args(argv)

    plan = common.load_json(args.plan)
    if plan is None:
        print(f"[verify_fidelity] ERROR: plan not found: {args.plan}")
        return 2
    change_log = common.load_json(args.change_log, []) if args.change_log else []

    report = verify_plan(plan, args.corpus_dir, change_log)
    n_unv = report["summary"]["unverified"]

    if n_unv and args.strict:
        report["gate"] = "fail"
        report["instructions"] = (
            "Unverified content found. Fix slide_plan.json: every number must "
            "appear verbatim in the cited corpus entries; every figure path "
            "must byte-match the ledger; every quote must be a verbatim "
            "substring of the source. Re-run finish afterwards.")
        common.dump_json(report, args.report)
        print(f"[verify_fidelity] GATE FAIL: {n_unv} unverified item(s). "
              f"See {args.report}")
        return 1

    if n_unv and args.out_plan:
        clean = drop_unverified(plan, report, change_log)
        common.dump_json(clean, args.out_plan)
        report["gate"] = "pass-with-drops"
        report["cleaned_plan"] = os.path.abspath(args.out_plan)
    elif args.out_plan:
        common.dump_json(plan, args.out_plan)
        report["cleaned_plan"] = os.path.abspath(args.out_plan)

    if args.change_log:
        common.dump_json(change_log, args.change_log)
    common.dump_json(report, args.report)
    s = report["summary"]
    print(f"[verify_fidelity] gate={report['gate']} verified={s['verified']} "
          f"loose={s['loose']} unverified={s['unverified']} dropped={s['dropped']}")
    print(f"[verify_fidelity] report -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
