#!/usr/bin/env python3
"""Cross-source field aligner (multi-source-aligner skill).

  propose: reads target-fields.json + sources.jsonl, gathers candidate
      readings per field from ALL sources/regions, groups them by value,
      classifies corroborated|single_source|conflict|none, writes a draft
      result.json (valid honest partial; statuses are PROPOSALS).
  check:   contract + alignment integrity validation of the final
      result.json (exit 0 PASS).

Scalar parsing is deliberately simple: the aligner proposes, the human/
model adjudicates (see SKILL.md step 3). Never delete readings.
"""
import argparse
import json
import os
import re
import sys

NUM_RE = re.compile(
    r"(?<![A-Za-z])([-+]?\d[\d,]*(?:\.\d+)?(?:\s*[–—]\s*\d[\d,]*(?:\.\d+)?)?"
    r"(?:\s*[<>≥≤]\s*\d[\d,]*(?:\.\d+)?)?)\s*"
    r"(%|‰|ppm|mAh\s*g\S*|Wh\s*kg\S*|mg\s*cm\S*|mV|kV|V|mA|A|W|kW|MPa|GPa|Pa"
    r"|°C|deg C|K|s|min|h|Hz|mol|mM|M|J|kJ|mL|L|cycles?|nm|mm|cm|kg|mg|g)?")
STOP = {"the", "a", "an", "of", "in", "at", "for", "and", "or", "after",
        "with", "from", "by", "is", "was", "are", "were", "to", "on", "its"}


def tokens(label):
    return [t for t in re.findall(r"[A-Za-z0-9%-]+", (label or "").lower())
            if t not in STOP and len(t) > 1]


def norm_unit(u):
    return re.sub(r"[\s.]+$", "", (u or "").lower().replace(" ", ""))


def parse_pairs(text):
    """All (scalar, unit) pairs in a record, units cleaned."""
    pairs = []
    for m in NUM_RE.finditer(text):
        scalar = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(".")
        units = (m.group(2) or "").strip().rstrip(".")
        pairs.append((scalar, units or None))
    return pairs


def representative(pairs, expect_unit):
    """Choose the (scalar, unit) pair that answers the field: prefer a unit
    matching expect_unit, else any unit, else None (unresolved reading)."""
    exp = norm_unit(expect_unit)
    if exp:
        for s, u in pairs:
            nu = norm_unit(u)
            if nu and (nu in exp or exp in nu):
                return s, u
        return None, None  # field expects a unit this record does not carry
    for s, u in pairs:
        if u:
            return s, u
    return pairs[0] if pairs else (None, None)


BENCH_CUE = re.compile(
    r"\b(target|requirement|threshold|benchmark|typical|common)\b|"
    r"目标|要求|阈值", re.IGNORECASE)


def gather(records, field):
    toks = sorted(set(tokens(field.get("label") or field.get("field_id", ""))))
    num_toks = [t for t in toks if re.fullmatch(r"\d+", t)]
    unit_hint = (field.get("expect_unit") or "").lower()
    need = max(2, -(-len(toks) // 2))  # ceil(0.5 * len(toks))
    hits = []
    for r in records:
        low = r["text"].lower()
        tscore = sum(1 for t in toks if t in low)
        unit_hit = bool(unit_hint) and unit_hint in low
        if tscore < need and not unit_hit:
            continue
        # condition binding: every numeric token in the label (e.g. cycle
        # count, temperature) must appear in the record
        if num_toks and not all(n in low for n in num_toks):
            continue
        risk = bool(BENCH_CUE.search(r["text"]))
        s, u = representative(parse_pairs(r["text"]),
                              field.get("expect_unit"))
        hits.append({"source": r["source"], "region": r["region"],
                     "page": r["page"], "rid": r["rid"],
                     "quote": r["text"], "scalar": s, "units": u,
                     "resolved": s is not None and not risk,
                     "benchmark_risk": risk,
                     "token_score": tscore, "unit_matched": unit_hit,
                     "match_score": tscore + (2 if unit_hit else 0)})
    return hits, need


def classify(readings, need):
    """Group token-strong resolved readings; if none are token-strong,
    fall back to unit-matched resolved readings (label wording may be
    arbitrary, the unit string is not). Weak/unresolved/benchmark lines
    stay listed for adjudication but do not create fake conflicts."""
    res = [r for r in readings if r["resolved"] and r["token_score"] >= need]
    if not res:
        res = [r for r in readings if r["resolved"] and r["unit_matched"]]
    vals = {(r["scalar"], norm_unit(r["units"])) for r in res}
    srcs = {r["source"] for r in res}
    if not res:
        return "none", []
    if len(vals) == 1:
        return ("corroborated" if len(srcs) >= 2 else "single_source",
                sorted(vals))
    return "conflict", sorted(vals)


def cmd_propose(a):
    tf = json.load(open(os.path.join(a.input_dir, "target-fields.json"),
                        encoding="utf-8"))
    case = json.load(open(os.path.join(a.input_dir, "case.json"),
                          encoding="utf-8"))
    records = [json.loads(l) for l in
               open(os.path.join(a.work_dir, "sources.jsonl"), encoding="utf-8")]
    frs = []
    for f in tf.get("fields", []):
        readings, need = gather(records, f)
        cls, vals = classify(readings, need)
        proposed = {"corroborated": "reported", "single_source": "reported",
                    "conflict": "source_conflict", "none": "not_reported"}[cls]
        best = None
        if readings:
            pr = {"table": 0, "body": 1, "caption": 2}
            readings.sort(key=lambda r: (
                0 if r["resolved"] else 1,
                0 if r["source"] == "MAIN" else 1,
                pr.get(r["region"], 3), -r["match_score"]))
            best = readings[0] if readings[0]["resolved"] else None
        note = "machine proposal (%s); adjudicate per SKILL.md step 3" % cls
        if cls == "none" and readings:
            note = ("readings exist but carry no unit-resolved value "
                    "(unresolved/table lines); adjudicate per SKILL.md step 3")
        frs.append({
            "field_id": f["field_id"], "status": proposed,
            "alignment": cls,
            "distinct_values": [list(v) for v in vals],
            "scalar": best["scalar"] if best and cls != "conflict" else None,
            "units": best["units"] if best and cls != "conflict" else None,
            "statistic": None, "condition": None, "comparator": None,
            "quote": best["quote"] if best else None,
            "page": best["page"] if best else None,
            "source_id": best["source"] if best else None,
            "readings": readings,
            "notes": note,
        })
    result = {"case_id": case.get("case_id"), "status": "partial",
              "result": {"field_results": frs}, "claims": [],
              "uncertainties": []}
    for k in (case.get("output_contract") or {}):
        result.setdefault(k, None)
    os.makedirs(os.path.dirname(os.path.abspath(a.output)), exist_ok=True)
    with open(a.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    for r in frs:
        print("  %-28s %-14s readings=%d values=%s" % (
            r["field_id"], r["alignment"], len(r["readings"]),
            r["distinct_values"]))
    print("propose -> %s (%d fields)" % (a.output, len(frs)))
    return 0


def cmd_check(a):
    d = json.load(open(a.output, encoding="utf-8"))
    errors = []
    records = [json.loads(l) for l in
               open(os.path.join(a.work_dir, "sources.jsonl"), encoding="utf-8")]
    corpus = {}
    for r in records:
        corpus.setdefault(r["source"], []).append(re.sub(r"\s+", " ", r["text"]))

    def in_source(src, quote):
        q = re.sub(r"\s+", " ", quote or "")
        return bool(q) and any(q in t for t in corpus.get(src, []))

    frs = (d.get("result") or {}).get("field_results") or []
    if not d.get("case_id"):
        errors.append("case_id missing")
    if not frs:
        errors.append("field_results empty")
    for r in frs:
        fid = r.get("field_id")
        st = r.get("status")
        if st == "reported":
            if not r.get("scalar") or r["scalar"] not in (r.get("quote") or ""):
                errors.append("%s: scalar not verbatim in quote" % fid)
            if not in_source(r.get("source_id") or "MAIN", r.get("quote")):
                errors.append("%s: quote not found in cited source scan" % fid)
            if not r.get("readings"):
                errors.append("%s: reported but readings list emptied "
                              "(never delete readings)" % fid)
            if not r.get("condition"):
                errors.append("%s: reported without condition" % fid)
        elif st == "source_conflict":
            vals = {tuple(v) for v in r.get("distinct_values", [])}
            if len(r.get("readings", [])) < 2 or len(vals) < 2:
                errors.append("%s: source_conflict needs >=2 divergent readings"
                              % fid)
        elif st == "not_reported":
            if not r.get("notes") or "proposal" in str(r.get("notes")):
                errors.append("%s: not_reported needs adjudicated notes "
                              "(searched terms / n.d. cell)" % fid)
        elif st == "extraction_failed":
            if r.get("page") is None and not r.get("readings"):
                errors.append("%s: extraction_failed needs a location" % fid)
        else:
            errors.append("%s: bad status %r" % (fid, st))
    unc = {u.get("field_id") for u in d.get("uncertainties", [])}
    for r in frs:
        if r.get("status") != "reported" and r.get("field_id") not in unc:
            errors.append("%s not mirrored in uncertainties" % r.get("field_id"))
    for e in errors:
        print("ERROR: %s" % e)
    print("check: %s (%d fields, %d errors)" % (
        "PASS" if not errors else "FAIL", len(frs), len(errors)))
    return 0 if not errors else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("propose")
    p.add_argument("--work-dir", required=True)
    p.add_argument("--input-dir", required=True)
    p.add_argument("--output", required=True)
    p = sub.add_parser("check")
    p.add_argument("--output", required=True)
    p.add_argument("--work-dir", required=True)
    a = ap.parse_args()
    return {"propose": cmd_propose, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
