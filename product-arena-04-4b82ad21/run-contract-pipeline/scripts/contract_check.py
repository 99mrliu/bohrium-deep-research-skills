#!/usr/bin/env python3
"""contract_check.py -- verify result.json against the case contract and constraints.

Two families of checks:

1. STRUCTURE (result.json vs the case's output_contract). The descriptor
   strings are re-parsed with the same rules as init_run.py (duplicated here
   so this script is standalone):

     * leading "str"            -> value must be a string
     * "object: f1, f2[], f3{}" -> value must be an object; each
                                   clean-identifier subfield must be present
                                   and of the right type ([] -> array,
                                   {} -> object, bare -> string)
     * "array of X objects (...)" -> value must be an array; every item must
                                   carry each clean-identifier subfield
     * "enum: a | b | c"        -> value must be one of the allowed values
     * unparseable descriptors or prose subfields (e.g. "pass/fail/not_verifiable
       counts") are marked needs_manual_review and checked as
       NOT_VERIFIABLE, never as failures. Max nesting depth 3.

   Plus: case_id in result must equal case_id in case.json, and a
   status_consistency check (status "complete" requires every top-level
   contract field to be populated).

2. CONSTRAINTS (case.constraints vs the actual draft Markdown file):
     * max_words_introduction     total word count of the draft
     * max_words_related_work     words under headings matching the
                                  related-work keyword list
     * min_distinct_citations     distinct [n] Vancouver markers in the draft
     * sections_required          each rhetorical part found via a keyword
                                  list (defaults below; override with
                                  --sections-json FILE mapping part -> [kw])
     * must_cover_topics          each topic present as a case-insensitive
                                  phrase, or via its main content words
                                  (>= 70% of words of length >= 4 present)

   If --draft is given but the file does not exist, draft_file_present is a
   hard FAIL and all draft-dependent checks become not_verifiable.

Every check records pass / fail / not_verifiable with an evidence string.
Writes REPORT.json and prints a human-readable summary.
Exit codes: 0 all good (no hard fail), 1 at least one hard fail, 2 usage error.
Pure Python 3 standard library; no hardcoded harness paths.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

MAX_DEPTH = 3

DEFAULT_SECTION_KEYWORDS = {
    "background": ["background", "introduction", "motivation"],
    "related_work": ["related work", "prior work", "previous work", "related studies"],
    "gap": ["gap", "limitation", "limitations", "open problem", "remains", "unaddressed"],
    "contributions": ["contribution", "contributions", "we present", "we propose",
                      "we introduce", "our work", "this work"],
}
RELATED_WORK_HEADING_KEYWORDS = ["related work", "prior work", "previous work"]

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ARRAY_OF_RE = re.compile(r"array\s+of\s+(.+?)\s+objects?\s*\(([^)]*)\)", re.IGNORECASE | re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_CIT_RE = re.compile(r"\[(\d+(?:\s*[-,]\s*\d+)*)\]")


# ---------------------------------------------------------------------------
# Descriptor parsing (kept in sync with init_run.py -- duplicated on purpose
# so each shipped script is standalone).
# ---------------------------------------------------------------------------

def _note(node, msg):
    node.setdefault("notes", []).append(msg)


def _needs_review(node):
    return any("needs_manual_review" in n for n in node.get("notes", []))


def parse_field_token(token, depth):
    token = token.strip()
    if not token:
        return None, None
    suffix = None
    base = token
    if token.endswith("[]"):
        base, suffix = token[:-2].strip(), "[]"
    elif token.endswith("{}"):
        base, suffix = token[:-2].strip(), "{}"
    if not _IDENT_RE.match(base):
        node = {"raw": token, "type": "unknown", "placeholder": None}
        _note(node, "needs_manual_review: subfield token is not a clean identifier")
        return token, node
    if suffix == "[]":
        return base, {"raw": token, "type": "array", "placeholder": []}
    if suffix == "{}":
        return base, {"raw": token, "type": "object", "placeholder": {}}
    return base, {"raw": token, "type": "str", "placeholder": ""}


def parse_descriptor(desc, depth=0):
    node = {"raw": desc}
    if not isinstance(desc, str):
        node.update({"type": "unknown", "placeholder": None})
        _note(node, "needs_manual_review: descriptor is not a string")
        return node
    if depth >= MAX_DEPTH:
        node.update({"type": "unknown", "placeholder": None})
        _note(node, "needs_manual_review: maximum nesting depth exceeded")
        return node
    text = desc.strip()
    lower = text.lower()
    if lower.startswith("enum:"):
        values = [v.strip() for v in text.split(":", 1)[1].split("|") if v.strip()]
        node.update({"type": "enum", "allowed": values,
                     "placeholder": values[0] if values else None})
        if not values:
            _note(node, "needs_manual_review: enum descriptor has no values")
        return node
    if lower.startswith("array of"):
        m = _ARRAY_OF_RE.search(text)
        if m:
            subfields = {}
            for tok in m.group(2).split(","):
                key, sub = parse_field_token(tok, depth + 1)
                if key is not None:
                    subfields[key] = sub
            node.update({"type": "array", "item_kind": m.group(1).strip(),
                         "placeholder": [], "subfields": subfields})
        else:
            node.update({"type": "array", "placeholder": [], "subfields": {}})
            _note(node, "needs_manual_review: 'array of' descriptor without a "
                        "parseable item field list")
        return node
    if lower.startswith("object:"):
        subfields = {}
        for tok in text.split(":", 1)[1].split(","):
            key, sub = parse_field_token(tok, depth + 1)
            if key is not None:
                subfields[key] = sub
        node.update({"type": "object", "placeholder": {}, "subfields": subfields})
        return node
    if lower.startswith("str"):
        node.update({"type": "str", "placeholder": ""})
        return node
    if lower.startswith("int") or lower.startswith("num"):
        node.update({"type": "number", "placeholder": 0})
        return node
    node.update({"type": "unknown", "placeholder": None})
    _note(node, "needs_manual_review: descriptor does not match any known pattern")
    return node


# ---------------------------------------------------------------------------
# Check helpers
# ---------------------------------------------------------------------------

class Report:
    def __init__(self):
        self.checks = []

    def add(self, cid, status, evidence):
        assert status in ("pass", "fail", "not_verifiable")
        self.checks.append({"check": cid, "status": status, "evidence": evidence})

    def counts(self):
        out = {"pass": 0, "fail": 0, "not_verifiable": 0}
        for c in self.checks:
            out[c["status"]] += 1
        return out


def type_ok(node, value):
    t = node.get("type")
    if t == "str":
        return isinstance(value, str)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "array":
        return isinstance(value, list)
    if t == "object":
        return isinstance(value, dict)
    if t == "enum":
        return value in node.get("allowed", [])
    return None  # unknown -> caller decides


def is_populated(value):
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, dict):
        return any(is_populated(v) for v in value.values())
    return False


def check_node(rep, path, node, value, present):
    cid = "contract:%s" % path
    if _needs_review(node):
        rep.add(cid, "not_verifiable",
                "descriptor needs manual review: %r" % (node.get("raw"),))
        return
    if not present:
        rep.add(cid, "fail", "field missing from result.json")
        return
    ok = type_ok(node, value)
    if ok is None:
        rep.add(cid, "not_verifiable", "unknown descriptor type")
        return
    if not ok:
        rep.add(cid, "fail", "wrong type: expected %s, got %s"
                % (node.get("type"), type(value).__name__))
        return
    rep.add(cid, "pass", "type %s ok" % node.get("type"))
    # recurse one level into subfields
    subfields = node.get("subfields") or {}
    if not subfields:
        return
    if node["type"] == "object" and isinstance(value, dict):
        for key, sub in subfields.items():
            check_node(rep, "%s.%s" % (path, key), sub, value.get(key), key in value)
    elif node["type"] == "array" and isinstance(value, list):
        if not value:
            rep.add("%s:items" % cid, "pass",
                    "empty array; item shape vacuously satisfied")
            return
        clean = {k: s for k, s in subfields.items() if not _needs_review(s)}
        prose = {k: s for k, s in subfields.items() if _needs_review(s)}
        for k in prose:
            rep.add("%s.%s" % (cid, k), "not_verifiable",
                    "prose item subfield; verify by hand")
        for i, item in enumerate(value):
            if not isinstance(item, dict):
                rep.add("%s:item[%d]" % (cid, i), "fail", "item is not an object")
                continue
            missing = [k for k in clean if k not in item]
            wrong = [k for k in clean
                     if k in item and type_ok(clean[k], item[k]) is False]
            if missing or wrong:
                rep.add("%s:item[%d]" % (cid, i), "fail",
                        "missing=%s wrong_type=%s" % (missing, wrong))
            else:
                rep.add("%s:item[%d]" % (cid, i), "pass",
                        "all %d item subfields present with right types" % len(clean))


# ---------------------------------------------------------------------------
# Draft/constraint helpers
# ---------------------------------------------------------------------------

def word_count(text):
    return sum(1 for tok in text.split() if re.search(r"[A-Za-z0-9]", tok))


def section_word_counts(lines):
    """heading -> words until the next heading; plus list of headings."""
    sections, counts, current, buf = [], {}, None, []

    def flush():
        if current is not None:
            counts[current] = counts.get(current, 0) + word_count("\n".join(buf))

    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            flush()
            current = m.group(2).strip()
            if current not in sections:
                sections.append(current)
            buf = []
        else:
            buf.append(line)
    flush()
    return sections, counts


def distinct_citations(text):
    found = set()
    for m in _CIT_RE.finditer(text):
        for part in re.split(r"\s*,\s*", m.group(1)):
            if "-" in part:
                a, b = part.split("-", 1)
                found.update(range(int(a), int(b) + 1))
            elif part.strip():
                found.add(int(part))
    return found


def topic_present(topic, text_lower):
    if topic.lower() in text_lower:
        return True, "exact phrase found"
    words = [w for w in re.findall(r"[a-z0-9-]+", topic.lower()) if len(w) >= 4]
    if not words:
        return False, "topic has no content words of length >= 4"
    hits = [w for w in words if w in text_lower]
    ratio = len(hits) / len(words)
    return ratio >= 0.7, "content words present: %d/%d (%s)" % (len(hits), words and len(words), ", ".join(hits))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check result.json against the case contract.")
    ap.add_argument("--case", required=True, help="path to case.json")
    ap.add_argument("--result", required=True, help="path to result.json")
    ap.add_argument("--draft", default=None, help="path to the draft manuscript (Markdown)")
    ap.add_argument("--out", required=True, help="path for the JSON check report")
    ap.add_argument("--sections-json", default=None,
                    help="optional JSON mapping rhetorical part -> [keywords]")
    args = ap.parse_args(argv)

    try:
        with open(args.case, "r", encoding="utf-8") as fh:
            case = json.load(fh)
        with open(args.result, "r", encoding="utf-8") as fh:
            result = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print("ERROR: cannot read inputs: %s" % exc, file=sys.stderr)
        return 2

    section_keywords = dict(DEFAULT_SECTION_KEYWORDS)
    if args.sections_json:
        try:
            with open(args.sections_json, "r", encoding="utf-8") as fh:
                section_keywords.update(json.load(fh))
        except (OSError, json.JSONDecodeError) as exc:
            print("ERROR: cannot read --sections-json: %s" % exc, file=sys.stderr)
            return 2

    rep = Report()
    contract = case.get("output_contract") or {}

    # --- 1. structure ------------------------------------------------------
    for name, desc in contract.items():
        node = parse_descriptor(desc)
        check_node(rep, name, node, result.get(name), name in result)

    if result.get("case_id") == case.get("case_id"):
        rep.add("contract:case_id_matches_input", "pass",
                "case_id %r copied verbatim" % case.get("case_id"))
    else:
        rep.add("contract:case_id_matches_input", "fail",
                "result case_id %r != case case_id %r"
                % (result.get("case_id"), case.get("case_id")))

    status = result.get("status")
    if status == "complete":
        empty = [f for f in contract if not is_populated(result.get(f))]
        if empty:
            rep.add("contract:status_consistency", "fail",
                    "status=complete but fields empty: %s" % ", ".join(empty))
        else:
            rep.add("contract:status_consistency", "pass",
                    "status=complete and all top-level fields populated")
    else:
        rep.add("contract:status_consistency", "pass",
                "status=%s; empty fields allowed for honest partial/blocked" % status)

    # --- 2. constraints vs the draft ----------------------------------------
    constraints = case.get("constraints") or {}
    draft_text = None
    if args.draft and os.path.isfile(args.draft):
        rep.add("draft:file_present", "pass", "draft found: %s" % args.draft)
        with open(args.draft, "r", encoding="utf-8") as fh:
            draft_text = fh.read()
    else:
        rep.add("draft:file_present", "fail",
                "draft not found: %s" % (args.draft or "(no --draft given)"))

    def need_draft(cid):
        if draft_text is None:
            rep.add(cid, "not_verifiable", "no readable draft file")
            return True
        return False

    if draft_text is not None:
        lines = draft_text.splitlines()
        sections, counts = section_word_counts(lines)
        total_words = word_count(draft_text)
        text_lower = draft_text.lower()

    if "max_words_introduction" in constraints:
        cid = "constraint:max_words_introduction"
        if not need_draft(cid):
            lim = constraints["max_words_introduction"]
            ok = total_words <= lim
            rep.add(cid, "pass" if ok else "fail",
                    "total words %d vs limit %d" % (total_words, lim))

    if "max_words_related_work" in constraints:
        cid = "constraint:max_words_related_work"
        if not need_draft(cid):
            lim = constraints["max_words_related_work"]
            rw = [s for s in sections
                  if any(k in s.lower() for k in RELATED_WORK_HEADING_KEYWORDS)]
            if not rw:
                rep.add(cid, "not_verifiable",
                        "no heading matches related-work keywords %s"
                        % RELATED_WORK_HEADING_KEYWORDS)
            else:
                n = sum(counts.get(s, 0) for s in rw)
                ok = n <= lim
                rep.add(cid, "pass" if ok else "fail",
                        "related-work words %d (sections %s) vs limit %d" % (n, rw, lim))

    if "min_distinct_citations" in constraints:
        cid = "constraint:min_distinct_citations"
        if not need_draft(cid):
            lim = constraints["min_distinct_citations"]
            found = sorted(distinct_citations(draft_text))
            ok = len(found) >= lim
            rep.add(cid, "pass" if ok else "fail",
                    "distinct [n] citations %d %s vs minimum %d" % (len(found), found, lim))

    for part in constraints.get("sections_required", []):
        cid = "constraint:sections_required:%s" % part
        if need_draft(cid):
            continue
        kws = section_keywords.get(part, [part.replace("_", " ")])
        hits = [k for k in kws if k.lower() in text_lower]
        rep.add(cid, "pass" if hits else "fail",
                ("part %r signalled by keyword(s): %s" % (part, hits)) if hits
                else "no keyword of %s found for part %r" % (kws, part))

    for topic in constraints.get("must_cover_topics", []):
        cid = "constraint:must_cover_topics:%s" % topic
        if need_draft(cid):
            continue
        ok, how = topic_present(topic, text_lower)
        rep.add(cid, "pass" if ok else "fail", "%s (%s)" % (topic, how))

    # --- report ---------------------------------------------------------------
    counts = rep.counts()
    report = {
        "case_id": case.get("case_id"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "result_checked": os.path.abspath(args.result),
        "draft_checked": os.path.abspath(args.draft) if args.draft else None,
        "checks": rep.checks,
        "summary": counts,
    }
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print("contract_check report for case '%s'" % case.get("case_id"))
    for c in rep.checks:
        mark = {"pass": "PASS", "fail": "FAIL", "not_verifiable": "N/V "}[c["status"]]
        print("  [%s] %s -- %s" % (mark, c["check"], c["evidence"]))
    print("summary: pass=%(pass)d fail=%(fail)d not_verifiable=%(not_verifiable)d" % counts)
    print("  wrote %s" % args.out)
    return 1 if counts["fail"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
