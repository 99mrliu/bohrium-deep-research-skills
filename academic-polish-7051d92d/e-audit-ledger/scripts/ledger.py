#!/usr/bin/env python3
"""ledger.py -- audit-ledger core for the audit-trail-polish skill.

Commands:
  prepare  --source <file> --job <dir>
      Freeze the source text into stable sentence units s0001... with offsets
      and separators preserved. Merging, dropping or reordering sentences is
      forbidden; export re-fills sentence-by-sentence and verifies (gate C01).
  intake   --job <dir> --edits <file|dir> --out <intake-report.json>
      Merge edit batches in filename order (one corrupt batch never sinks the
      others). Every edit must carry sid / original (anchored to the frozen
      sentence) / revised / types (14-type vocabulary) / reason (>=12 chars,
      non-vacuous) / basis. Failing entries are rejected with per-entry
      explanations (gates C02 / C07; protected-token loss also rejects, C03).
  review   --job <dir> --edits <file|dir> --review <review.json>
      Review records are MANDATORY. decision in {accept, reject, query} with a
      concrete reason. Unreviewed or stale (hash-mismatched) edits are rolled
      back -- this rollback can NOT be skipped (gate C04). Protected tokens are
      re-verified at apply time; any loss forces rollback and is recorded (C03).

Deterministic: no timestamps, no randomness; identical input -> identical bytes.
Python 3 standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

EDIT_TYPES = [
    "grammar", "syntax", "tense-voice", "agreement", "article-preposition",
    "punctuation", "terminology", "register", "conciseness", "hedging",
    "consistency", "structure", "translation", "other",
]

# Vacuous-reason blacklist (normalized: lowercase, alnum only). A reason whose
# normalized form matches any entry is rejected under gate C07.
VACUOUS_REASONS = {
    "improvefluency", "improverefluency", "improvereadability",
    "enhanceexpression", "enhancetheexpression", "polishlanguage",
    "polishthesentence", "polishthetext", "makeitbetter", "betterwording",
    "betterexpression", "languagepolishing", "improveexpression",
    "optimizetheexpression", "makeitmorefluent", "makeitmorenatural",
    "提升流畅性", "优化表达", "提升可读性", "改善表达", "润色语言",
    "使表达更流畅", "语言润色", "表达优化", "提升语言质量",
}

MIN_REASON_CHARS = 12
MIN_BASIS_CHARS = 8
MIN_REVIEW_REASON_CHARS = 8

# ---------------------------------------------------------------------------
# Sentence freezing (prepare)
# ---------------------------------------------------------------------------

# Abbreviations whose trailing period does NOT end a sentence.
ABBR = {
    "fig", "figs", "eq", "eqs", "al", "vs", "cf", "no", "dr", "mr", "mrs",
    "ms", "prof", "st", "approx", "ca", "e.g", "i.e", "etc", "inc", "ltd",
    "dept", "univ", "ref", "refs", "sec", "secs", "ed", "eds", "vol", "pp",
}

BOUNDARY_RE = re.compile(r"[.!?]+[\"')\]]*(\s+)")
WORD_BEFORE_RE = re.compile(r"([A-Za-z][A-Za-z.]*|[A-Za-z])$")


def split_sentences(text):
    """Split text into sentence units, preserving separators exactly.

    Returns a list of dicts {sid, text, sep, start, end} such that
    ''.join(text + sep) reproduces the input byte-for-byte.
    """
    units = []
    pos = 0
    for m in BOUNDARY_RE.finditer(text):
        ws = m.group(1)
        cut = m.end() - len(ws)
        before = text[pos:m.start()].rstrip()
        wm = WORD_BEFORE_RE.search(before)
        if wm:
            w = wm.group(1)
            if w.lower() in ABBR or (len(w) == 1 and w.isupper()):
                continue  # abbreviation or initial: not a sentence boundary
        units.append({"text": text[pos:cut], "sep": ws})
        pos = m.end()
    if pos < len(text):
        tail = text[pos:]
        stripped = tail.rstrip()
        units.append({"text": stripped, "sep": tail[len(stripped):]})
    out = []
    cursor = 0
    for i, u in enumerate(units, 1):
        start = text.index(u["text"], cursor)
        out.append({
            "sid": "s%04d" % i,
            "text": u["text"],
            "sep": u["sep"],
            "start": start,
            "end": start + len(u["text"]),
        })
        cursor = start + len(u["text"]) + len(u["sep"])
    # C01 self-check at freeze time: reconstruction must be exact.
    if "".join(u["text"] + u["sep"] for u in out) != text:
        raise SystemExit("C01 freeze failure: sentence reconstruction mismatch")
    return out


# ---------------------------------------------------------------------------
# Protected tokens (gate C03)
# ---------------------------------------------------------------------------

TOKEN_PATTERNS = [
    ("number-unit", re.compile(
        r"\d+(?:\.\d+)?\s?(?:°C|°F|K\b|nm|mm|cm|km|μm|µm|mL|μL|µL|nL|L\b|"
        r"h\b|hr\b|min\b|s\b|ms\b|kg|mg|μg|µg|ng|pg|g\b|mol|mmol|mM|μM|µM|"
        r"nM|M\b|rpm|kDa|Da\b|mV|V\b|mA|A\b|mW|W\b|Hz|kHz|MHz|GHz|bp\b|kb\b|"
        r"×\s?g\b|x\s?g\b)")),
    ("percentage", re.compile(r"\d+(?:\.\d+)?\s?%")),
    ("p-value", re.compile(r"[pP]\s*[<>=≤≥]\s*\d*\.?\d+")),
    ("confidence-interval", re.compile(
        r"\b\d+(?:\.\d+)?\s?%\s?CI\b|\bCI\s*[:=]?\s*[\[\(][^\]\)]*[\]\)]")),
    ("numeric-citation", re.compile(r"\[\d+(?:\s?[-,]\s?\d+)*\]")),
    ("author-year-citation", re.compile(
        r"\([A-Z][A-Za-zÀ-ÿ'\-]+(?:\s+et\s+al\.?)?"
        r"(?:\s+(?:and|&)\s+[A-Z][A-Za-z'\-]+)?,\s*\d{4}[a-z]?\)")),
    ("float-ref", re.compile(
        r"\b(?:Figs?|Figures?|Tables?|Eqs?|Equations?|Sections?|Secs?|"
        r"Appendix|Suppl\.?)\.?\s*\(?\d+[a-z]?(?:\.\d+)?\)?")),
    ("url", re.compile(r"https?://[^\s)>\]]+")),
    ("doi", re.compile(r"(?:doi:\s?|https?://doi\.org/)?10\.\d{4,9}/[^\s)>\]]+")),
    ("email", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
]


def _norm(tok):
    return re.sub(r"\s+", " ", tok).strip()


def protected_tokens(text):
    """Return a sorted list of (kind, normalized_token) found in text."""
    found = []
    for kind, pat in TOKEN_PATTERNS:
        for m in pat.finditer(text):
            found.append((kind, _norm(m.group(0))))
    return sorted(found)


def token_violations(original, revised):
    """Return (missing, added) protected tokens between original and revised."""
    from collections import Counter
    co = Counter(protected_tokens(original))
    cr = Counter(protected_tokens(revised))
    missing = sorted((co - cr).elements())
    added = sorted((cr - co).elements())
    return missing, added


# ---------------------------------------------------------------------------
# Edit identity / state
# ---------------------------------------------------------------------------

def edit_hash(sid, original, revised):
    return hashlib.sha1(
        ("%s|%s|%s" % (sid, original, revised)).encode("utf-8")
    ).hexdigest()[:10]


def edit_id(sid, original, revised):
    return "%s-%s" % (sid, edit_hash(sid, original, revised))


def state_path(job):
    return Path(job) / "state.json"


def load_state(job):
    p = state_path(job)
    if not p.exists():
        raise SystemExit("no frozen state in %s -- run prepare first" % job)
    return json.loads(p.read_text(encoding="utf-8"))


def save_state(job, state):
    state_path(job).write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")


def normalize_reason(s):
    return re.sub(r"[^0-9A-Za-z一-鿿]+", "", s).lower()


# ---------------------------------------------------------------------------
# prepare
# ---------------------------------------------------------------------------

def cmd_prepare(args):
    text = Path(args.source).read_text(encoding="utf-8")
    units = split_sentences(text)
    state = {
        "version": 1,
        "source_sha1": hashlib.sha1(text.encode("utf-8")).hexdigest(),
        "sentence_count": len(units),
        "sentences": units,
        "edits": [],
        "reviews": [],
        "finalized": False,
    }
    Path(args.job).mkdir(parents=True, exist_ok=True)
    save_state(args.job, state)
    print("prepare: froze %d sentence units (s0001..s%04d) into %s"
          % (len(units), len(units), state_path(args.job)))
    print("prepare: source sha1 %s" % state["source_sha1"])
    return 0


# ---------------------------------------------------------------------------
# intake
# ---------------------------------------------------------------------------

def gather_batch_files(edits):
    p = Path(edits)
    if p.is_dir():
        return sorted(p.glob("*.json"), key=lambda x: x.name)
    return [p]


def validate_edit(entry, frozen_by_sid, accepted_sids):
    """Return list of rejection reasons (empty list = accepted)."""
    reasons = []
    if not isinstance(entry, dict):
        return ["entry is not a JSON object"]
    # C02: required fields.
    for key in ("sid", "original", "revised", "types", "reason", "basis"):
        if key not in entry:
            reasons.append("missing required field '%s'" % key)
    if reasons:
        return reasons
    sid = entry["sid"]
    frozen = frozen_by_sid.get(sid)
    if frozen is None:
        reasons.append("unknown sid '%s'" % sid)
    elif entry["original"] != frozen["text"]:
        reasons.append(
            "anchor mismatch: 'original' does not equal frozen sentence %s "
            "(got %d chars, frozen has %d)"
            % (sid, len(entry["original"]), len(frozen["text"])))
    # types against the 14-type vocabulary.
    types = entry["types"]
    if not isinstance(types, list) or not types:
        reasons.append("'types' must be a non-empty list from the 14-type vocabulary")
    else:
        bad = [t for t in types if t not in EDIT_TYPES]
        if bad:
            reasons.append("unknown edit type(s): %s" % ", ".join(map(str, bad)))
    # C07: reason quality.
    reason = entry["reason"]
    if not isinstance(reason, str) or len(reason.strip()) < MIN_REASON_CHARS:
        reasons.append("reason too short (<%d chars)" % MIN_REASON_CHARS)
    elif normalize_reason(reason) in VACUOUS_REASONS:
        reasons.append("vacuous reason blacklisted: '%s'" % reason.strip())
    basis = entry["basis"]
    if not isinstance(basis, str) or len(basis.strip()) < MIN_BASIS_CHARS:
        reasons.append("basis too short (<%d chars): must cite a style rule, "
                       "termbase entry or grammar rule" % MIN_BASIS_CHARS)
    if entry["original"] == entry["revised"]:
        reasons.append("revised text identical to original")
    if sid in accepted_sids:
        reasons.append("conflict: an accepted edit for %s already exists in "
                       "this intake" % sid)
    # C03 (intake stage): protected-token conservation.
    if isinstance(entry["revised"], str) and frozen is not None:
        missing, added = token_violations(entry["original"], entry["revised"])
        if missing:
            reasons.append("protected token(s) lost in revision: %s"
                           % "; ".join("%s '%s'" % m for m in missing))
        if added:
            reasons.append("protected token(s) introduced in revision: %s"
                           % "; ".join("%s '%s'" % a for a in added))
    return reasons


def cmd_intake(args):
    state = load_state(args.job)
    frozen_by_sid = {u["sid"]: u for u in state["sentences"]}
    report = {"batches": [], "accepted": [], "rejected": []}
    accepted_sids = set()
    new_edits = []
    for batch_file in gather_batch_files(args.edits):
        brec = {"file": batch_file.name, "status": "ok",
                "received": 0, "accepted": 0, "rejected": 0, "errors": []}
        try:
            data = json.loads(batch_file.read_text(encoding="utf-8"))
            entries = data["edits"] if isinstance(data, dict) else data
            if not isinstance(entries, list):
                raise ValueError("batch is neither a list nor an object with 'edits'")
        except Exception as exc:  # one corrupt batch must not sink the others
            brec["status"] = "corrupt"
            brec["errors"].append("batch unreadable: %s" % exc)
            report["batches"].append(brec)
            continue
        for idx, entry in enumerate(entries):
            brec["received"] += 1
            reasons = validate_edit(entry, frozen_by_sid, accepted_sids)
            if reasons:
                brec["rejected"] += 1
                report["rejected"].append({
                    "batch": batch_file.name, "index": idx,
                    "sid": entry.get("sid") if isinstance(entry, dict) else None,
                    "edit": entry, "reasons": reasons,
                })
                continue
            eid = edit_id(entry["sid"], entry["original"], entry["revised"])
            rec = {
                "edit_id": eid,
                "sid": entry["sid"],
                "original": entry["original"],
                "revised": entry["revised"],
                "types": entry["types"],
                "reason": entry["reason"].strip(),
                "basis": entry["basis"].strip(),
                "batch": batch_file.name,
                "status": "accepted_pending_review",
                "status_detail": None,
                "review": None,
            }
            accepted_sids.add(entry["sid"])
            new_edits.append(rec)
            brec["accepted"] += 1
            report["accepted"].append({
                "edit_id": eid, "sid": entry["sid"], "types": entry["types"],
                "reason": rec["reason"], "basis": rec["basis"],
                "original": entry["original"], "revised": entry["revised"],
                "batch": batch_file.name,
            })
        report["batches"].append(brec)
    state["edits"] = new_edits
    state["finalized"] = False
    save_state(args.job, state)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print("intake: %d batch file(s), %d accepted, %d rejected -> %s"
          % (len(report["batches"]), len(report["accepted"]),
             len(report["rejected"]), out))
    for r in report["rejected"]:
        print("  REJECTED %s[%d] sid=%s: %s"
              % (r["batch"], r["index"], r["sid"], " | ".join(r["reasons"])))
    return 0


# ---------------------------------------------------------------------------
# review (mandatory; rollback is not skippable)
# ---------------------------------------------------------------------------

def cmd_review(args):
    state = load_state(args.job)
    if not state["edits"]:
        print("review: no accepted edits to review (nothing to do)")
        state["finalized"] = True
        save_state(args.job, state)
        return 0
    review_data = json.loads(Path(args.review).read_text(encoding="utf-8"))
    raw_reviews = review_data["reviews"] if isinstance(review_data, dict) else review_data

    # Validate review records themselves.
    valid_reviews = {}
    invalid_reviews = []
    for i, rv in enumerate(raw_reviews):
        problems = []
        if not isinstance(rv, dict):
            invalid_reviews.append({"index": i, "review": rv,
                                    "problems": ["review is not a JSON object"]})
            continue
        if not rv.get("edit_id"):
            problems.append("missing edit_id")
        if rv.get("decision") not in ("accept", "reject", "query"):
            problems.append("decision must be accept|reject|query")
        rsn = rv.get("reason", "")
        if not isinstance(rsn, str) or len(rsn.strip()) < MIN_REVIEW_REASON_CHARS:
            problems.append("review reason missing or <%d chars"
                            % MIN_REVIEW_REASON_CHARS)
        if problems:
            invalid_reviews.append({"index": i, "review": rv, "problems": problems})
        else:
            valid_reviews[rv["edit_id"]] = {
                "decision": rv["decision"], "reason": rv["reason"].strip()}

    # Staleness: recompute edit ids from the batch files; an accepted edit whose
    # id is no longer reproduced by the batches is stale and must roll back.
    live_ids = set()
    for batch_file in gather_batch_files(args.edits):
        try:
            data = json.loads(batch_file.read_text(encoding="utf-8"))
            entries = data["edits"] if isinstance(data, dict) else data
        except Exception:
            continue
        for e in entries:
            if isinstance(e, dict) and all(k in e for k in ("sid", "original", "revised")):
                live_ids.add(edit_id(e["sid"], e["original"], e["revised"]))

    outcomes = []
    n_applied = n_rolled = 0
    for edit in state["edits"]:
        eid = edit["edit_id"]
        if eid not in live_ids:
            edit["status"] = "rolled_back_stale"
            edit["status_detail"] = ("edit content no longer matches the batch "
                                     "files (hash mismatch); rolled back")
        elif eid not in valid_reviews:
            # C04: no review record -> rollback. This branch is NOT skippable.
            edit["status"] = "rolled_back_unreviewed"
            edit["status_detail"] = ("no review record for this edit; mandatory "
                                     "review gate rolls it back")
        else:
            rv = valid_reviews[eid]
            edit["review"] = rv
            if rv["decision"] == "accept":
                # C03 re-check at apply time; any token loss forces rollback.
                missing, added = token_violations(edit["original"], edit["revised"])
                if missing or added:
                    edit["status"] = "rolled_back_token_violation"
                    edit["status_detail"] = (
                        "protected-token mismatch at apply time: missing=%s added=%s"
                        % (["%s '%s'" % m for m in missing],
                           ["%s '%s'" % a for a in added]))
                else:
                    edit["status"] = "applied"
                    edit["status_detail"] = "reviewed and applied"
            elif rv["decision"] == "reject":
                edit["status"] = "rolled_back_review_rejected"
                edit["status_detail"] = "reviewer rejected: %s" % rv["reason"]
            else:  # query
                edit["status"] = "rolled_back_review_query"
                edit["status_detail"] = ("reviewer raised a query; edit held back "
                                         "pending clarification: %s" % rv["reason"])
        if edit["status"] == "applied":
            n_applied += 1
        else:
            n_rolled += 1
        outcomes.append({"edit_id": eid, "sid": edit["sid"],
                         "status": edit["status"],
                         "detail": edit["status_detail"]})
    state["reviews"] = sorted(
        ({"edit_id": k, **v} for k, v in valid_reviews.items()),
        key=lambda r: r["edit_id"])
    state["finalized"] = True
    save_state(args.job, state)
    report = {
        "applied": n_applied,
        "rolled_back": n_rolled,
        "invalid_review_records": invalid_reviews,
        "outcomes": outcomes,
    }
    rp = Path(args.job) / "review-report.json"
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                             sort_keys=True) + "\n", encoding="utf-8")
    print("review: %d applied, %d rolled back -> %s" % (n_applied, n_rolled, rp))
    for o in outcomes:
        if o["status"] != "applied":
            print("  ROLLED BACK %s (%s): %s" % (o["edit_id"], o["status"], o["detail"]))
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="audit-ledger core: freeze / intake / review with "
                    "non-skippable rollback gates")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare", help="freeze source into sentence units")
    p.add_argument("--source", required=True)
    p.add_argument("--job", required=True)
    p.set_defaults(fn=cmd_prepare)

    p = sub.add_parser("intake", help="merge and validate edit batches")
    p.add_argument("--job", required=True)
    p.add_argument("--edits", required=True, help="batch file or directory")
    p.add_argument("--out", required=True, help="intake report JSON path")
    p.set_defaults(fn=cmd_intake)

    p = sub.add_parser("review", help="apply mandatory review records")
    p.add_argument("--job", required=True)
    p.add_argument("--edits", required=True, help="batch file or directory")
    p.add_argument("--review", required=True, help="review records JSON")
    p.set_defaults(fn=cmd_review)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
