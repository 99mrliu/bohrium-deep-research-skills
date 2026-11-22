#!/usr/bin/env python3
"""check_plan.py -- quote-gate validation of the agent-written slide plan.

Runs BEFORE deck building (end of PASS 2). The plan format is specified in
references/plan_format.md. Stdlib only.

Checks (failures are written to plan_check.json and cause exit code 1):
  * every bullet whose text contains a number+unit token carries a `quote`;
  * every `quote` is a verbatim substring of paper.txt after whitespace and
    ligature normalization (copy from paper.txt, never retype);
  * every figure/table reference (in bullets, locators, figure_ref) exists in
    evidence_index.json;
  * every bullet status is in the allowed taxonomy
    {established, supported, preliminary, inferred, unsupported};
  * number+unit tokens appearing in slide notes or slide claims are backed by
    at least one number token in the paper (fuzzy value match, see code).

Usage:
  python3 check_plan.py --plan /app/work/slide_plan.json \
      --index /app/work/evidence_index.json --paper /app/work/paper.txt \
      [--out /app/work/plan_check.json]

Exit codes: 0 pass; 1 validation failures; 2 bad inputs.
"""
import argparse
import json
import os
import re
import sys

# --- number/unit machinery: keep consistent with extract_evidence.py --------
UNITS = [
    "percent", "%", "°C", "K",
    "ms", "μs", "µs", "us", "ns", "ps", "sec", "s", "min", "h", "hr",
    "eV", "keV", "MeV", "GeV", "TeV",
    "nm", "μm", "µm", "um", "mm", "cm", "km", "m",
    "mM", "μM", "µM", "uM", "nM", "pM", "mol", "mmol", "μmol", "umol",
    "mg", "μg", "µg", "ug", "kg", "g",
    "THz", "GHz", "MHz", "kHz", "Hz",
    "mL", "μL", "µL", "uL", "L", "dB",
    "mV", "kV", "V", "mA", "μA", "uA", "A", "mW", "kW", "MW", "W",
    "kPa", "MPa", "GPa", "Pa", "bar", "atm", "rpm",
    "KB", "MB", "GB", "TB", "dpi", "fps", "bp", "kb", "Mb",
    "epochs", "epoch", "samples", "sample", "subjects", "subject",
    "patients", "patient", "layers", "layer", "folds", "fold",
    "trials", "trial", "runs", "run", "GPUs", "GPU",
]
_UNIT_ALT = "|".join(re.escape(u) for u in sorted(set(UNITS), key=len, reverse=True))
_NUMBER = r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?(?:\s*[×x]\s*10\^?[-+]?\d+|[eE][-+]?\d+)?"
TOKEN_RE = re.compile(
    r"(?<![\w.])(?P<num>" + _NUMBER + r")(?:\s*(?P<unit>" + _UNIT_ALT + r"))?(?![\w%])"
)
LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "–": "-", "−": "-"}
ALLOWED_STATUS = {"established", "supported", "preliminary", "inferred", "unsupported"}
REF_RE = re.compile(r"(?<![\w])(?P<kind>Fig\.?|Figure|FIG\.?|Table|TABLE)\s*(?P<num>\d+)")


def norm_text(s):
    for k, v in LIGATURES.items():
        s = s.replace(k, v)
    return " ".join(s.split())


def norm_unit(u):
    if u is None:
        return ""
    u = u.replace("μ", "u").replace("µ", "u")
    if u == "percent":
        return "%"
    if u not in ("%", "°C", "K"):
        u = u.lower()
    if len(u) > 2 and u.endswith("s") and u[:-1] in {x.lower() for x in UNITS}:
        u = u[:-1]
    return u


def norm_value(numstr):
    """Canonical float for '92.3', '92.30', '1,024', '3.2 x 10^5', '1e-4'.

    Formatting differences collapse to the same float; comparison uses a
    small relative tolerance downstream (fuzzy numeric match).
    """
    s = numstr.replace(",", "").replace(" ", "")
    s = re.sub(r"[×xX]10\^?", "e", s)
    try:
        return float(s)
    except ValueError:
        return None


def paper_values(paper_norm):
    """All numeric values mentioned anywhere in the paper (unit-agnostic)."""
    vals = []
    for m in TOKEN_RE.finditer(paper_norm):
        v = norm_value(m.group("num"))
        if v is not None:
            vals.append(v)
    return vals


def value_backed(token_num, vals, rel_tol=1e-9):
    v = norm_value(token_num)
    if v is None:
        return False
    return any(abs(v - p) <= rel_tol * max(1.0, abs(v), abs(p)) for p in vals)


def has_number_with_unit(text):
    return any(m.group("unit") for m in TOKEN_RE.finditer(text))


def fail(msg):
    sys.stderr.write("ERROR: %s\n" % msg)
    sys.exit(2)


def main():
    ap = argparse.ArgumentParser(description="Validate slide plan against the quote gate.")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--index", required=True)
    ap.add_argument("--paper", required=True)
    ap.add_argument("--out", default=None, help="plan_check.json path (default: alongside --plan)")
    args = ap.parse_args()

    for p in (args.plan, args.index, args.paper):
        if not os.path.isfile(p):
            fail("file not found: %s" % p)
    try:
        plan = json.load(open(args.plan, encoding="utf-8"))
        index = json.load(open(args.index, encoding="utf-8"))
        paper_norm = norm_text(open(args.paper, encoding="utf-8", errors="replace").read())
    except (json.JSONDecodeError, OSError) as e:
        fail("could not load inputs: %s" % e)

    out_path = args.out or os.path.join(os.path.dirname(os.path.abspath(args.plan)), "plan_check.json")
    vals = paper_values(paper_norm)
    fig_ids = {str(f.get("id")) for f in index.get("figures", [])}
    tab_ids = {str(t.get("id")) for t in index.get("tables", [])}

    findings = []

    def check_ref(text, slide_id, where):
        for m in REF_RE.finditer(text):
            kind = m.group("kind").lower()
            num = m.group("num")
            ok = num in (tab_ids if kind.startswith("table") else fig_ids)
            if not ok:
                findings.append({"slide": slide_id, "where": where,
                                 "kind": "unknown_ref",
                                 "detail": "reference '%s %s' not found in evidence_index" % (m.group("kind"), num)})

    slides = plan.get("slides")
    if not isinstance(slides, list):
        fail("plan has no 'slides' list")

    for sidx, slide in enumerate(slides):
        sid = slide.get("id", "slide-%d" % (sidx + 1))
        # slide-level figure_ref
        fref = slide.get("figure_ref")
        if fref:
            check_ref(str(fref), sid, "figure_ref")
        # claim: numbers must exist in the paper (soft backing; bullets carry quotes)
        claim = slide.get("claim") or ""
        for m in TOKEN_RE.finditer(claim):
            if m.group("unit") and not value_backed(m.group("num"), vals):
                findings.append({"slide": sid, "where": "claim", "kind": "unbacked_number",
                                 "detail": "claim token '%s' not found in paper fact pool" % m.group(0)})
        check_ref(claim, sid, "claim")
        # bullets: the strict quote gate
        for bidx, b in enumerate(slide.get("bullets", []) or []):
            text = b.get("text", "") or ""
            quote = b.get("quote")
            status = b.get("status")
            where = "bullet[%d]" % bidx
            if status not in ALLOWED_STATUS:
                findings.append({"slide": sid, "where": where, "kind": "bad_status",
                                 "detail": "status '%s' not in %s" % (status, sorted(ALLOWED_STATUS))})
            needs_quote = has_number_with_unit(text)
            if needs_quote and not quote:
                findings.append({"slide": sid, "where": where, "kind": "missing_quote",
                                 "detail": "bullet states a number/unit but has no verbatim quote"})
            if quote is not None and norm_text(quote) not in paper_norm:
                findings.append({"slide": sid, "where": where, "kind": "quote_not_verbatim",
                                 "detail": "quote is not a verbatim substring of paper.txt "
                                           "(whitespace-normalized); copy it, do not retype it"})
            for m in TOKEN_RE.finditer(text):
                if m.group("unit") and not value_backed(m.group("num"), vals):
                    findings.append({"slide": sid, "where": where, "kind": "unbacked_number",
                                     "detail": "token '%s' not found in paper fact pool" % m.group(0)})
            check_ref(text, sid, where)
            loc = b.get("locator")
            if loc:
                check_ref(str(loc), sid, where + ".locator")
        # notes: no unbacked numbers in speaker notes either
        notes = slide.get("notes") or ""
        for m in TOKEN_RE.finditer(notes):
            if m.group("unit") and not value_backed(m.group("num"), vals):
                findings.append({"slide": sid, "where": "notes", "kind": "unbacked_number",
                                 "detail": "notes token '%s' not found in paper fact pool" % m.group(0)})
        check_ref(notes, sid, "notes")

    report = {
        "plan": os.path.abspath(args.plan),
        "n_slides": len(slides),
        "n_findings": len(findings),
        "verdict": "pass" if not findings else "fail",
        "findings": findings,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    sys.stdout.write("plan_check: %s (%d finding%s) -> %s\n"
                     % (report["verdict"].upper(), len(findings),
                        "" if len(findings) == 1 else "s", out_path))
    sys.exit(0 if not findings else 1)


if __name__ == "__main__":
    main()
