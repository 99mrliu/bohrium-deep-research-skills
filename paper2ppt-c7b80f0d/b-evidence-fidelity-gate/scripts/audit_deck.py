#!/usr/bin/env python3
"""audit_deck.py -- deterministic auditor for the finished .pptx (the GATE).

Stdlib only: the deck is read by parsing the pptx zip/XML directly, so the
audit never depends on python-pptx. Extracts every <a:t> text run from
ppt/slides/slideN.xml and ppt/notesSlides/notesSlideN.xml (namespaces handled
via fully qualified tags).

Checks per slide (and per notes slide):
  1. unbacked_number  -- every number token carrying a unit on the deck must
     match (value + normalized unit) a token extracted from the paper text.
     Fuzzy numeric match: values are compared as floats after canonicalizing
     commas and scientific notation, so "92.3" == "92.30" and "3.2 x 10^5"
     == "3.2e5". Benign integers are ignored (documented heuristic):
       - bare integers in 1900..2099 (years);
       - bare integers with |v| <= 20 (slide numbers, small ordinals,
         "Top-5", list indices) when no unit is attached;
       - integers embedded in figure/table references ("Figure 2").
  2. unknown_ref      -- every "Figure N"/"Table M" cited on slides must
     exist in evidence_index.json.
  3. caption_mismatch -- a slide line shaped like a caption ("Figure 2: ...")
     must match the indexed caption of that id (content-word overlap >= 0.4)
     and must not be a different figure's caption (heuristic).
  4. quote_not_verbatim -- when --plan is given, every plan quote must be a
     whitespace-normalized verbatim substring of paper.txt.
Notes text is audited with the same number rules (no unbacked numbers in
speaker notes either).

Every finding gets a stable id and a null `disposition`. Unresolved findings
make the audit exit 1. To accept a deviation, pass --dispositions FILE with
[{"finding_id": "...", "action": "fixed|downgraded|labeled-unsupported|accepted",
  "reason": "..."}] -- each dispositioned finding is marked resolved and kept
in the report for reviewers.

Usage:
  python3 audit_deck.py --deck /app/output/deck.pptx \
      --index /app/work/evidence_index.json --paper /app/work/paper.txt \
      --report /app/output/audit_report.json [--plan /app/work/slide_plan.json] \
      [--dispositions /app/work/dispositions.json]

Exit codes: 0 pass; 1 unresolved failures; 2 bad inputs.
"""
import argparse
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

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
REF_RE = re.compile(r"(?<![\w])(?P<kind>Fig\.?|Figure|FIG\.?|Table|TABLE)\s*(?P<num>\d+)")
CAPTION_LINE_RE = re.compile(
    r"^\s*(?:Figure|Fig\.?|FIG\.?|Table|TABLE)\s*(?P<num>\d+)\s*[:.]\s*(?P<cap>.+)$")
A_T = "{http://schemas.openxmlformats.org/drawingml/2006/main}t"
STOP = {"the", "and", "for", "with", "from", "over", "are", "was", "were", "this",
        "that", "show", "shows", "shown", "figure", "table", "fig", "vs", "per", "all"}


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
    s = numstr.replace(",", "").replace(" ", "")
    s = re.sub(r"[×xX]10\^?", "e", s)
    try:
        return float(s)
    except ValueError:
        return None


def content_words(text):
    return {w for w in re.findall(r"[a-z0-9]+", text.lower())
            if len(w) >= 3 and w not in STOP}


# --------------------------------------------------------------------------
def extract_deck_text(deck_path):
    """Return (slides, notes): lists of (index, joined_text) sorted by number."""
    try:
        zf = zipfile.ZipFile(deck_path)
    except (zipfile.BadZipFile, OSError) as e:
        sys.stderr.write("ERROR: cannot open deck '%s': %s\n" % (deck_path, e))
        sys.exit(2)
    names = zf.namelist()

    def collect(pattern):
        out = []
        rx = re.compile(pattern)
        for n in names:
            m = rx.fullmatch(n)
            if m:
                out.append((int(m.group(1)), n))
        out.sort()
        res = []
        for idx, n in out:
            try:
                root = ET.fromstring(zf.read(n))
                texts = [el.text or "" for el in root.iter(A_T)]
            except ET.ParseError as e:
                sys.stderr.write("WARNING: XML parse failed for %s: %s\n" % (n, e))
                texts = []
            res.append((idx, "\n".join(t for t in texts if t)))
        return res

    slides = collect(r"ppt/slides/slide(\d+)\.xml")
    raw_notes = collect(r"ppt/notesSlides/notesSlide(\d+)\.xml")
    if not slides:
        sys.stderr.write("ERROR: no ppt/slides/slideN.xml found in %s\n" % deck_path)
        sys.exit(2)
    # Map notes to their owning slide via slide relationship files: the number
    # in notesSlideN.xml is a creation-order artifact and does NOT necessarily
    # equal the slide number.
    notes_by_part = {("ppt/notesSlides/notesSlide%d.xml" % i): (i, t) for i, t in raw_notes}
    notes, used = [], set()
    rel_re = re.compile(r'Target="\.\./notesSlides/(notesSlide\d+)\.xml"')
    for idx, _ in slides:
        rel_name = "ppt/slides/_rels/slide%d.xml.rels" % idx
        if rel_name in names:
            try:
                rel_xml = zf.read(rel_name).decode("utf-8", "replace")
            except KeyError:
                rel_xml = ""
            for m in rel_re.finditer(rel_xml):
                part = "ppt/notesSlides/%s.xml" % m.group(1)
                if part in notes_by_part:
                    notes.append((idx, notes_by_part[part][1]))
                    used.add(part)
    for part, (i, t) in notes_by_part.items():   # orphan notes keep own index
        if part not in used:
            notes.append((i, t))
    notes.sort()
    zf.close()
    return slides, notes


def benign_bare_integer(v, raw):
    """Documented heuristic for context-free integers (no unit attached)."""
    if v is None or v != int(v):
        return False
    iv = int(v)
    if 1900 <= iv <= 2099:          # years
        return True
    if abs(iv) <= 20:               # slide numbers, small ordinals, Top-N
        return True
    if re.fullmatch(r"[-+]?\d+", raw) and abs(iv) <= 20:
        return True
    return False


def main():
    ap = argparse.ArgumentParser(description="Audit a .pptx against the paper evidence index.")
    ap.add_argument("--deck", required=True)
    ap.add_argument("--index", required=True)
    ap.add_argument("--paper", required=True)
    ap.add_argument("--report", default="/app/output/audit_report.json")
    ap.add_argument("--plan", default=None, help="optional slide_plan.json for quote checks")
    ap.add_argument("--dispositions", default=None,
                    help="optional JSON list resolving findings by id")
    args = ap.parse_args()

    for p in (args.deck, args.index, args.paper):
        if not os.path.isfile(p):
            sys.stderr.write("ERROR: file not found: %s\n" % p)
            sys.exit(2)
    index = json.load(open(args.index, encoding="utf-8"))
    paper_norm = norm_text(open(args.paper, encoding="utf-8", errors="replace").read())

    # paper-side token pool: (value, normalized unit) pairs and bare values
    paper_pair, paper_vals = set(), []
    for m in TOKEN_RE.finditer(paper_norm):
        v = norm_value(m.group("num"))
        if v is None:
            continue
        paper_vals.append(v)
        paper_pair.add((v, norm_unit(m.group("unit"))))

    fig_ids = {str(f.get("id")) for f in index.get("figures", [])}
    tab_ids = {str(t.get("id")) for t in index.get("tables", [])}
    cap_by_id = {}
    for f in index.get("figures", []):
        cap_by_id[("figure", str(f.get("id")))] = f.get("caption", "")
    for t in index.get("tables", []):
        cap_by_id[("table", str(t.get("id")))] = t.get("caption", "")

    slides, notes = extract_deck_text(args.deck)
    findings = []
    counter = [0]

    def add(slide_no, where, kind, detail):
        counter[0] += 1
        findings.append({"id": "F%03d" % counter[0], "slide": slide_no,
                         "where": where, "kind": kind, "detail": detail,
                         "disposition": None})

    def audit_text(text, slide_no, where):
        # 1. number tokens
        for m in TOKEN_RE.finditer(text):
            v = norm_value(m.group("num"))
            u = norm_unit(m.group("unit"))
            if not u:
                if benign_bare_integer(v, m.group("num")):
                    continue
                # bare non-trivial number: pass if the value appears in paper
                if any(abs(v - p) <= 1e-9 * max(1.0, abs(v), abs(p)) for p in paper_vals):
                    continue
                add(slide_no, where, "unbacked_number",
                    "bare number '%s' does not match any number in the paper" % m.group(0))
                continue
            # with unit: require value+unit match (unit-agnostic value match is
            # NOT enough -- a mutated unit is exactly what this gate catches)
            hit = any(abs(v - pv) <= 1e-9 * max(1.0, abs(v), abs(pv)) and u == pu
                      for pv, pu in paper_pair)
            if not hit:
                add(slide_no, where, "unbacked_number",
                    "token '%s' (value+unit) not found in the paper fact pool" % m.group(0))
        # 2. figure/table references
        for m in REF_RE.finditer(text):
            kind = "table" if m.group("kind").lower().startswith("table") else "figure"
            num = m.group("num")
            if num not in (tab_ids if kind == "table" else fig_ids):
                add(slide_no, where, "unknown_ref",
                    "cited '%s %s' does not exist in evidence_index" % (m.group("kind"), num))
        # 3. caption-shaped lines must match the indexed caption (heuristic)
        for line in text.splitlines():
            cm = CAPTION_LINE_RE.match(line)
            if not cm:
                continue
            num, cap = cm.group("num"), cm.group("cap")
            kind = "table" if line.strip().lower().startswith("table") else "figure"
            indexed = cap_by_id.get((kind, num))
            if indexed is None:
                continue  # unknown_ref already reported
            iw, sw = content_words(indexed), content_words(cap)
            if iw and len(iw & sw) / len(iw) < 0.4:
                other = [k for k, c in cap_by_id.items()
                         if k != (kind, num) and content_words(c) and
                         len(content_words(c) & sw) / max(1, len(content_words(c))) >= 0.6]
                hint = ("; text instead resembles %s %s" % (other[0][0], other[0][1])) if other else ""
                add(slide_no, where, "caption_mismatch",
                    "caption text for %s %s does not match the paper's indexed caption%s"
                    % (kind, num, hint))

    for idx, text in slides:
        audit_text(text, idx, "slide")
    for idx, text in notes:
        audit_text(text, idx, "notes")

    # 4. plan quotes verbatim (optional)
    plan_quotes = 0
    if args.plan:
        plan = json.load(open(args.plan, encoding="utf-8"))
        for sidx, slide in enumerate(plan.get("slides", [])):
            sid = slide.get("id", "slide-%d" % (sidx + 1))
            for bidx, b in enumerate(slide.get("bullets", []) or []):
                q = b.get("quote")
                if q is None:
                    continue
                plan_quotes += 1
                if norm_text(q) not in paper_norm:
                    add(sid if isinstance(sid, int) else -(sidx + 1), "plan.bullet[%d]" % bidx,
                        "quote_not_verbatim",
                        "plan quote is not a verbatim substring of paper.txt")

    # dispositions: agent-accepted deviations with reasons
    unresolved = []
    disp = []
    if args.dispositions:
        disp = json.load(open(args.dispositions, encoding="utf-8"))
    by_id = {d.get("finding_id"): d for d in disp if isinstance(d, dict)}
    for f in findings:
        d = by_id.get(f["id"])
        if d and d.get("action") in ("fixed", "downgraded", "labeled-unsupported", "accepted") \
                and d.get("reason"):
            f["disposition"] = {"action": d["action"], "reason": d["reason"]}
        else:
            unresolved.append(f)

    per_slide = {}
    for f in findings:
        per_slide.setdefault(str(f["slide"]), []).append(f["id"])

    report = {
        "deck": os.path.abspath(args.deck),
        "n_slides": len(slides),
        "n_notes_slides": len(notes),
        "n_plan_quotes_checked": plan_quotes,
        "verdict": "pass" if not unresolved else "fail",
        "summary": {
            "findings_total": len(findings),
            "unresolved": len(unresolved),
            "dispositioned": len(findings) - len(unresolved),
            "by_kind": {k: sum(1 for f in findings if f["kind"] == k)
                        for k in sorted({f["kind"] for f in findings})},
        },
        "per_slide": per_slide,
        "findings": findings,
        "heuristics": "bare integers 1900-2099 treated as years; bare integers "
                      "|v|<=20 ignored as slide numbers/ordinals; numeric match "
                      "is float equality within 1e-9 relative tolerance after "
                      "comma/scientific-notation canonicalization; units are "
                      "compared after micro/plural/case normalization",
    }
    report_dir = os.path.dirname(os.path.abspath(args.report))
    os.makedirs(report_dir, exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    sys.stdout.write("audit: %s -- %d finding(s), %d unresolved -> %s\n"
                     % (report["verdict"].upper(), len(findings), len(unresolved), args.report))
    sys.exit(0 if not unresolved else 1)


if __name__ == "__main__":
    main()
