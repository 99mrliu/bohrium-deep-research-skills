#!/usr/bin/env python3
"""evidence-offset-verifier engine.

Center of gravity: explainability engineering and anti-fabrication checking.
Every screening decision must carry a verbatim evidence quote that is anchored
by character offsets into the record's own title or abstract. The engine
recomputes every anchor; a fabricated or misquoted "evidence" string cannot
survive: it lands in the rejected_register (with the best near-match so the
agent can repair in one pass) and its decision is downgraded to pending. The
deliverable product is the verified rationale (result.json + rationale cards),
not the bare label.

Stdlib only (Python 3). Subcommands:
  anchor   --case CASE.json [--decisions decisions.json] --out anchored.json
  cards    --case CASE.json --anchored anchored.json --out result.json
           [--cards-md rationale_cards.md]
  validate --case CASE.json --result result.json
Exit code 0 on success/PASS, 1 on validation FAIL, 2 on usage/IO error.
"""
import argparse
import difflib
import json
import sys
from pathlib import Path

CANDIDATE_KEYS = ("candidates", "records", "papers", "references", "pool",
                  "items")
CONTRACT_KEYS = ("output_contract", "outputContract", "output_contract_fields",
                 "contract", "expected_output", "expected_outputs")
ID_KEYS = ("case_id", "caseId", "id", "name")
REC_ID_KEYS = ("record_id", "recordId", "id", "paper_id", "doi")
LABELS = ("keep", "pending", "exclude")
LABEL_ORDER = {"keep": 0, "pending": 1, "exclude": 2}
RELEVANCES = ("direct", "indirect", "none")
ANCHOR_FAIL_REASON = "evidence anchor failed verification"
NOT_JUDGED_REASON = "not judged"
DOWNGRADE_NOTE = "label downgraded to pending: " + ANCHOR_FAIL_REASON


# --------------------------------------------------------------------------- io

def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise SystemExit("error: cannot parse %s as UTF-8 JSON: %s" % (path, exc))


def dump_json(obj, path):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8")


# ------------------------------------------------------------------ discovery

def find_case_id(case, case_path):
    if isinstance(case, dict):
        for k in ID_KEYS:
            v = case.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return Path(case_path).stem


def looks_like_record(obj):
    return isinstance(obj, dict) and isinstance(obj.get("title"), str)


def find_candidates(case):
    """Return (list_of_records, key_path) for the most plausible pool."""
    best, best_key = [], None
    if isinstance(case, dict):
        for k in CANDIDATE_KEYS:
            v = case.get(k)
            if isinstance(v, list) and v and all(looks_like_record(r) for r in v):
                if len(v) > len(best):
                    best, best_key = v, k
        if not best:  # fallback: largest top-level list of title-bearing dicts
            for k, v in case.items():
                if (isinstance(v, list) and v
                        and all(looks_like_record(r) for r in v)):
                    if len(v) > len(best):
                        best, best_key = v, k
    return best, best_key


def record_id_of(rec, idx):
    for k in REC_ID_KEYS:
        v = rec.get(k)
        if isinstance(v, (str, int)) and str(v).strip():
            return str(v).strip()
    return "rec-%03d" % (idx + 1)


def find_contract_fields(case):
    """Normalize whatever output_contract shape the case declares.

    Supports: dict field->spec, list of names/specs, JSON-schema-ish
    {"properties": {...}}, or a single string. Returns list of names.
    """
    raw = None
    if isinstance(case, dict):
        for k in CONTRACT_KEYS:
            if k in case:
                raw = case[k]
                break
    names = []
    if isinstance(raw, dict):
        props = raw.get("properties") if isinstance(raw.get("properties"), dict) else None
        src = props if props is not None else raw
        names = [str(n) for n in src]
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict) and item.get("name"):
                names.append(str(item["name"]))
    elif isinstance(raw, str):
        names = [raw]
    seen, uniq = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            uniq.append(n)
    return uniq


# ------------------------------------------------------------------ anchoring

def normalize_with_map(text):
    """Collapse whitespace runs to single spaces.

    Returns (normalized_text, norm_to_orig) where norm_to_orig[i] is the
    original char index that produced normalized char i, so offsets found in
    the normalized text can be mapped back to the original string.
    """
    norm_chars, norm_to_orig = [], []
    i, n = 0, len(text)
    while i < n:
        if text[i].isspace():
            j = i
            while j < n and text[j].isspace():
                j += 1
            norm_chars.append(" ")
            norm_to_orig.append(i)
            i = j
        else:
            norm_chars.append(text[i])
            norm_to_orig.append(i)
            i += 1
    return "".join(norm_chars), norm_to_orig


def normalize_quote(quote):
    norm, _ = normalize_with_map(quote)
    return norm


def locate_quote(quote, record):
    """Locate quote in title first, then abstract.

    Returns an anchor dict {field, start, end, surface_form, match_type} or
    None. Exact match is tried first, then a whitespace-normalized fallback
    whose offsets are mapped back to the original string.
    """
    if not isinstance(quote, str) or not quote.strip():
        return None
    norm_quote = normalize_quote(quote)
    for field in ("title", "abstract"):
        text = record.get(field)
        if not isinstance(text, str) or not text:
            continue
        idx = text.find(quote)
        if idx >= 0:
            return {"field": field, "start": idx, "end": idx + len(quote),
                    "surface_form": text[idx:idx + len(quote)],
                    "match_type": "exact"}
        norm_text, norm_to_orig = normalize_with_map(text)
        nidx = norm_text.find(norm_quote)
        if nidx >= 0 and norm_quote:
            start = norm_to_orig[nidx]
            end = norm_to_orig[nidx + len(norm_quote) - 1] + 1
            return {"field": field, "start": start, "end": end,
                    "surface_form": text[start:end],
                    "match_type": "whitespace-normalized"}
    return None


def best_near_match(quote, record):
    """Best near-match of quote against title/abstract, for repair hints.

    Candidate substrings are windows of len(quote) around the matching blocks
    reported by difflib; the best-scoring actual substring is returned with
    its ratio so the agent can repair the quote in one pass. Deterministic:
    title before abstract, ascending window start, replace only on strictly
    greater ratio.
    """
    if not quote:
        return None
    best = None
    L = len(quote)
    for field in ("title", "abstract"):
        text = record.get(field)
        if not isinstance(text, str) or not text:
            continue
        sm = difflib.SequenceMatcher(None, quote, text, autojunk=False)
        starts = set()
        for m in sm.get_matching_blocks():
            if m.size == 0:
                continue
            b = m.b
            starts.add(max(0, b))
            starts.add(max(0, b - (L - m.size) // 2))
            starts.add(max(0, min(len(text) - 1, b - L + m.size)))
        for s in sorted(starts):
            sub = text[s:s + L]
            if not sub:
                continue
            r = difflib.SequenceMatcher(None, quote, sub,
                                        autojunk=False).ratio()
            if best is None or r > best["ratio"]:
                best = {"field": field, "ratio": round(r, 4),
                        "substring": sub}
    return best


def coerce_label(value):
    return value if value in LABELS else "pending"


def coerce_relevance(value):
    return value if value in RELEVANCES else "none"


def coerce_confidence(value):
    try:
        c = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, c))


# --------------------------------------------------------------------- anchor

def cmd_anchor(args):
    case = load_json(args.case)
    case_id = find_case_id(case, args.case)
    cands, pool_key = find_candidates(case)
    records = {record_id_of(r, i): r for i, r in enumerate(cands)}
    order = [record_id_of(r, i) for i, r in enumerate(cands)]

    decisions = []
    decisions_source = None
    if args.decisions and Path(args.decisions).exists():
        decisions_source = args.decisions
        raw = load_json(args.decisions)
        if isinstance(raw, dict):
            decisions = raw.get("decisions") or []
        elif isinstance(raw, list):
            decisions = raw
        decisions = [d for d in decisions if isinstance(d, dict)]

    rejected_register = []
    by_id = {}
    for di, d in enumerate(decisions):
        rid = str(d.get("record_id") or "").strip()
        if not rid or rid not in records:
            rejected_register.append({
                "decision_index": di, "record_id": rid or None,
                "quote": d.get("evidence_quote"),
                "reason": "record_id not in candidate pool",
                "nearest_match": None})
            continue
        if rid in by_id:
            rejected_register.append({
                "decision_index": di, "record_id": rid,
                "quote": d.get("evidence_quote"),
                "reason": "duplicate decision for record; first decision kept",
                "nearest_match": None})
            continue
        by_id[rid] = (di, d)

    anchored_decisions = []
    for rid in order:
        entry = by_id.get(rid)
        if entry is None:
            anchored_decisions.append({
                "record_id": rid, "label": "pending", "original_label": None,
                "relevance": "none", "confidence": 0.0,
                "criterion_hit": None, "evidence_quote": None, "anchor": None,
                "verification": "not_judged",
                "reason": NOT_JUDGED_REASON})
            continue
        di, d = entry
        label = coerce_label(d.get("label"))
        quote = d.get("evidence_quote")
        anchor = locate_quote(quote, records[rid]) if isinstance(quote, str) else None
        if anchor is not None:
            anchored_decisions.append({
                "record_id": rid, "label": label, "original_label": label,
                "relevance": coerce_relevance(d.get("relevance")),
                "confidence": coerce_confidence(d.get("confidence")),
                "criterion_hit": (d.get("criterion_hit")
                                  if isinstance(d.get("criterion_hit"), str) else None),
                "evidence_quote": quote, "anchor": anchor,
                "verification": "verified", "reason": None})
        else:
            rejected_register.append({
                "decision_index": di, "record_id": rid, "quote": quote,
                "reason": ANCHOR_FAIL_REASON,
                "nearest_match": best_near_match(quote, records[rid])
                if isinstance(quote, str) else None})
            anchored_decisions.append({
                "record_id": rid, "label": "pending", "original_label": label,
                "relevance": coerce_relevance(d.get("relevance")),
                "confidence": coerce_confidence(d.get("confidence")),
                "criterion_hit": (d.get("criterion_hit")
                                  if isinstance(d.get("criterion_hit"), str) else None),
                "evidence_quote": quote, "anchor": None,
                "verification": "rejected",
                "reason": DOWNGRADE_NOTE})

    undecided = [a["record_id"] for a in anchored_decisions
                 if a["verification"] == "not_judged"]
    verified = sum(1 for a in anchored_decisions if a["verification"] == "verified")
    rejected = sum(1 for a in anchored_decisions if a["verification"] == "rejected")
    out = {
        "case_id": case_id,
        "candidate_pool_key": pool_key,
        "decisions_source": decisions_source,
        "decisions": anchored_decisions,
        "rejected_register": rejected_register,
        "coverage": {"total_records": len(order), "decided": verified + rejected,
                     "undecided_record_ids": undecided},
        "notes": [
            "anchors are character offsets into the record's own title/abstract",
            "rejected quotes are downgraded to pending; a decision whose "
            "evidence cannot be verified is never kept",
            "fixture_note fields are input provenance only, never ground truth",
        ],
    }
    dump_json(out, args.out)
    print("anchor: case_id=%s records=%d verified=%d rejected=%d undecided=%d -> %s"
          % (case_id, len(order), verified, rejected, len(undecided), args.out))


# ---------------------------------------------------------------------- cards

def rank_decisions(decisions):
    """Deterministic order: keep < pending < exclude, confidence desc, id."""
    ordered = sorted(decisions,
                     key=lambda a: (LABEL_ORDER.get(a["label"], 1),
                                    -a["confidence"], a["record_id"]))
    for i, a in enumerate(ordered):
        a["rank"] = i + 1
    return ordered


def render_context(text, start, end, width=40):
    before = text[max(0, start - width):start]
    surface = text[start:end]
    after = text[end:end + width]
    return before, surface, after


def build_cards_md(ordered, records_by_id, verification_report):
    lines = ["# Rationale cards (verified evidence anchors)", "",
             "case verification: %d/%d anchors verified (rate %.4f), "
             "%d rejected and downgraded to pending" % (
                 verification_report["anchors_verified"],
                 verification_report["total_decisions"],
                 verification_report["verification_rate"],
                 verification_report["downgrades"]), ""]
    for a in ordered:
        rec = records_by_id.get(a["record_id"]) or {}
        title = rec.get("title") or "(no title)"
        lines.append("## %d. %s — %s (confidence %.2f, relevance %s)"
                     % (a["rank"], a["record_id"], a["label"],
                        a["confidence"], a["relevance"]))
        lines.append("- **Title**: %s" % title)
        if a.get("criterion_hit"):
            lines.append("- **Criterion hit**: %s" % a["criterion_hit"])
        anchor = a.get("anchor")
        if anchor:
            text = rec.get(anchor["field"]) or ""
            before, surface, after = render_context(
                text, anchor["start"], anchor["end"])
            lines.append("- **Evidence anchor**: %s [%d:%d] (%s match), "
                         "verification: verified" % (
                             anchor["field"], anchor["start"], anchor["end"],
                             anchor["match_type"]))
            lines.append("  > …%s**%s**%s…" % (before, surface, after))
        elif a["verification"] == "rejected":
            lines.append("- **Evidence anchor**: none — quote %r failed "
                         "verification (see rejected_register)" %
                         (a.get("evidence_quote") or ""))
        else:
            lines.append("- **Evidence anchor**: none — record not judged")
        lines.append("- **Verification status**: %s%s" % (
            a["verification"],
            (" — " + a["reason"]) if a.get("reason") else ""))
        lines.append("")
    return "\n".join(lines)


def cmd_cards(args):
    case = load_json(args.case)
    anchored = load_json(args.anchored)
    case_id = anchored.get("case_id") or find_case_id(case, args.case)
    cands, pool_key = find_candidates(case)
    records_by_id = {record_id_of(r, i): r for i, r in enumerate(cands)}

    decisions = anchored.get("decisions") or []
    ordered = rank_decisions(decisions)
    rejected_register = anchored.get("rejected_register") or []

    verified = sum(1 for a in decisions if a["verification"] == "verified")
    rejected = sum(1 for a in decisions if a["verification"] == "rejected")
    undecided = [a["record_id"] for a in decisions
                 if a["verification"] == "not_judged"]
    total_decisions = verified + rejected
    rate = round(verified / total_decisions, 6) if total_decisions else 0.0
    verification_report = {
        "total_decisions": total_decisions,
        "anchors_verified": verified,
        "anchors_rejected": rejected,
        "verification_rate": rate,
        "downgrades": rejected,
    }

    screened_records = []
    for a in ordered:
        screened_records.append({
            "record_id": a["record_id"],
            "title": (records_by_id.get(a["record_id"]) or {}).get("title"),
            "rank": a["rank"],
            "label": a["label"],
            "relevance": a["relevance"],
            "confidence": a["confidence"],
            "criterion_hit": a.get("criterion_hit"),
            "evidence": {
                "quote": a.get("evidence_quote"),
                "anchor": a.get("anchor"),
                "verification": a["verification"],
            },
            "reason": a.get("reason"),
        })
    ranking = [{"rank": a["rank"], "record_id": a["record_id"],
                "label": a["label"], "confidence": a["confidence"]}
               for a in ordered]

    change_records = []
    for a in ordered:
        if a["verification"] == "rejected":
            change_records.append({
                "record_id": a["record_id"],
                "change": "label %s -> pending" % (a.get("original_label") or "?"),
                "reason": ANCHOR_FAIL_REASON})
    if not anchored.get("decisions_source"):
        change_records.append({
            "record_id": None, "change": "degraded path",
            "reason": "no decisions file provided; all records pending "
                      "(not judged)"})

    incomplete, limits = [], []
    if rejected:
        incomplete.append({
            "part": "evidence anchors",
            "reason": "%d of %d issued decisions failed anchor verification "
                      "and were downgraded to pending" % (rejected, total_decisions)})
    if undecided:
        incomplete.append({
            "part": "decisions",
            "reason": "%d of %d records have no decision (pending: not judged)"
                      % (len(undecided), len(ordered)),
            "record_ids": undecided})

    result = {
        "case_id": case_id,
        "screened_records": screened_records,
        "ranking": ranking,
        "verification_report": verification_report,
        "rejected_register": rejected_register,
        "summary": {
            "total_records": len(ordered),
            "keep": sum(1 for a in ordered if a["label"] == "keep"),
            "pending": sum(1 for a in ordered if a["label"] == "pending"),
            "exclude": sum(1 for a in ordered if a["label"] == "exclude"),
            "text": "Screened %d records with evidence-offset verification: "
                    "%d keep, %d pending, %d exclude; anchor verification "
                    "rate %.4f over %d issued decisions." % (
                        len(ordered),
                        sum(1 for a in ordered if a["label"] == "keep"),
                        sum(1 for a in ordered if a["label"] == "pending"),
                        sum(1 for a in ordered if a["label"] == "exclude"),
                        rate, total_decisions),
        },
        "status": {
            "state": "complete",  # may be downgraded below
            "completed": ["candidate location", "evidence anchoring",
                          "deterministic ranking", "rationale cards"],
            "incomplete": incomplete,
            "limits": limits,
        },
        "uncertainty": [
            "labels rest on title/abstract evidence only; no full text was "
            "consulted, so indirect relevance may be under- or over-called",
            "fixture_note / fixture fields are input provenance labels only "
            "and were never used as ground truth",
        ],
        "change_records": change_records,
    }

    # Mirror every declared contract field; never drop one silently.
    contract_fields = find_contract_fields(case)
    if not contract_fields:
        limits.append("case declares no output_contract; emitted the standard "
                      "payload keys only")
    for name in contract_fields:
        if name in result:
            continue
        if (isinstance(case, dict) and name in case and name != pool_key
                and name not in CONTRACT_KEYS):
            result[name] = case[name]  # echo real same-named input field
        elif any(t in name.lower() for t in ("omission", "coverage", "note")):
            parts = [
                "Candidate pool is a finite snapshot of %d records; no live "
                "database was queried, so recall beyond the snapshot cannot "
                "be claimed." % len(ordered)]
            no_abs = [a["record_id"] for a in ordered
                      if not (records_by_id.get(a["record_id"]) or {}).get("abstract")]
            if no_abs:
                parts.append("Records without an abstract (title-only "
                             "evidence): %s." % ", ".join(no_abs))
            if undecided:
                parts.append("Records not judged: %s." % ", ".join(undecided))
            if rejected:
                parts.append("Decisions downgraded after failed anchor "
                             "verification: see rejected_register and "
                             "change_records.")
            result[name] = " ".join(parts)
        else:
            result[name] = None
            result["status"]["incomplete"].append({
                "part": "contract field '%s'" % name,
                "reason": "declared by output_contract but not producible "
                          "from available input; emitted as explicit null"})

    if result["status"]["incomplete"] or rate < 1.0:
        result["status"]["state"] = "partial"
        if rate < 1.0 and not any(i["part"] == "evidence anchors"
                                  for i in result["status"]["incomplete"]):
            if total_decisions == 0:
                result["status"]["incomplete"].append({
                    "part": "evidence anchors",
                    "reason": "no decisions were issued; verification_rate is "
                              "0.0 (nothing verified)"})

    dump_json(result, args.out)
    if args.cards_md:
        Path(args.cards_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.cards_md).write_text(
            build_cards_md(ordered, records_by_id, verification_report),
            encoding="utf-8")
    print("cards: state=%s verification_rate=%.4f records=%d -> %s%s"
          % (result["status"]["state"], rate, len(ordered), args.out,
             (" (+ %s)" % args.cards_md) if args.cards_md else ""))


# ------------------------------------------------------------------- validate

def cmd_validate(args):
    case = load_json(args.case)
    result = load_json(args.result)
    case_id = find_case_id(case, args.case)
    cands, _ = find_candidates(case)
    records_by_id = {record_id_of(r, i): r for i, r in enumerate(cands)}
    known_ids = list(records_by_id)
    problems = []

    if result.get("case_id") != case_id:
        problems.append("case_id mismatch: result=%r expected=%r"
                        % (result.get("case_id"), case_id))

    for name in find_contract_fields(case):
        if name not in result:
            problems.append("contract field missing from result: %s" % name)

    screened = result.get("screened_records") or []
    seen = [s.get("record_id") for s in screened]
    dup = sorted({r for r in seen if seen.count(r) > 1})
    if dup:
        problems.append("duplicate record_ids in screened_records: %s" % dup)
    missing = [r for r in known_ids if r not in seen]
    extra = [r for r in seen if r not in known_ids]
    if missing:
        problems.append("records not covered: %s" % missing)
    if extra:
        problems.append("unknown record_ids in output: %s" % extra)

    anchors_verified = 0
    anchors_rejected = 0
    for s in screened:
        rid = s.get("record_id")
        if s.get("label") not in LABEL_ORDER:
            problems.append("bad label for %s: %r" % (rid, s.get("label")))
        c = s.get("confidence")
        if not isinstance(c, (int, float)) or isinstance(c, bool) \
                or not (0.0 <= c <= 1.0):
            problems.append("bad confidence for %s: %r" % (rid, c))
        ev = s.get("evidence") or {}
        anchor = ev.get("anchor")
        if anchor:
            rec = records_by_id.get(rid) or {}
            field = anchor.get("field")
            text = rec.get(field)
            ok = (field in ("title", "abstract")
                  and isinstance(text, str)
                  and isinstance(anchor.get("start"), int)
                  and isinstance(anchor.get("end"), int)
                  and 0 <= anchor["start"] < anchor["end"] <= len(text)
                  and text[anchor["start"]:anchor["end"]]
                  == anchor.get("surface_form"))
            if ok:
                anchors_verified += 1
            else:
                problems.append(
                    "anchor for %s does NOT recompute: surface_form %r != "
                    "%s[%s:%s] of the case record (fabricated or misquoted "
                    "evidence)" % (rid, anchor.get("surface_form"), field,
                                   anchor.get("start"), anchor.get("end")))
        elif ev.get("verification") == "rejected":
            anchors_rejected += 1
            if s.get("label") == "keep":
                problems.append(
                    "record %s has a rejected anchor but label 'keep' — a "
                    "decision whose evidence failed verification must be "
                    "downgraded to pending" % rid)

    report = result.get("verification_report") or {}
    total = anchors_verified + anchors_rejected
    rate = round(anchors_verified / total, 6) if total else 0.0
    if report.get("anchors_verified") != anchors_verified:
        problems.append("verification_report.anchors_verified=%r but %d "
                        "anchors recompute successfully"
                        % (report.get("anchors_verified"), anchors_verified))
    if report.get("anchors_rejected") != anchors_rejected:
        problems.append("verification_report.anchors_rejected=%r but %d "
                        "screened records carry verification=rejected"
                        % (report.get("anchors_rejected"), anchors_rejected))
    if report.get("total_decisions") != total:
        problems.append("verification_report.total_decisions=%r but "
                        "verified+rejected=%d"
                        % (report.get("total_decisions"), total))
    if abs((report.get("verification_rate") or 0.0) - rate) > 1e-6:
        problems.append("verification_report.verification_rate=%r but "
                        "recomputed rate is %.6f"
                        % (report.get("verification_rate"), rate))

    status = result.get("status")
    if not isinstance(status, dict) or status.get("state") not in ("complete", "partial"):
        problems.append("status.state missing or not complete/partial")
    elif status["state"] == "complete":
        if status.get("incomplete"):
            problems.append("status.state=complete but status.incomplete is "
                            "non-empty")
        if rate < 1.0:
            problems.append("status.state=complete but recomputed "
                            "verification_rate=%.6f < 1.0" % rate)

    if problems:
        print("VALIDATE FAIL")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    print("VALIDATE PASS: case_id=%s records=%d contract_fields=%d "
          "verification_rate=%s state=%s"
          % (case_id, len(seen), len(find_contract_fields(case)),
             ("%.4f" % rate), status["state"]))


# ----------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("anchor", help="anchor evidence quotes into title/abstract offsets")
    p.add_argument("--case", required=True)
    p.add_argument("--decisions")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_anchor)
    p = sub.add_parser("cards", help="build result.json and rationale cards")
    p.add_argument("--case", required=True)
    p.add_argument("--anchored", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--cards-md", dest="cards_md")
    p.set_defaults(fn=cmd_cards)
    p = sub.add_parser("validate", help="recompute every anchor from result.json")
    p.add_argument("--case", required=True)
    p.add_argument("--result", required=True)
    p.set_defaults(fn=cmd_validate)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
