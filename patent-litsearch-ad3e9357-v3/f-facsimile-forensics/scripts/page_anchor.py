#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""page_anchor.py - locate verbatim occurrences of a field value in extracted text
and emit anchor records {file, file_sha256, page, line_span, byte_span, quote}.

Subcommands:
  locate  --pages PAGES_JSON --field NAME --value STRING [--policy POLICY_JSON] [--out OUT.json]
  verify  --pages PAGES_JSON --anchor ANCHOR_JSON

Tolerance policy: any non-verbatim matching must be declared up-front in a
policy JSON:
  {"allow_whitespace_collapse": true, "allow_page_boundary_merge": true}
Undeclared fuzzy matching is refused with exit 1 and a clear message.
Multiple candidate locations are ALL listed; one is never silently picked.

Exit codes: 0 ok, 1 check/violation (not found / undeclared tolerance / forged quote),
2 usage error.
"""
import argparse
import json
import os
import sys


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print("usage error: cannot load JSON %r: %s" % (path, e), file=sys.stderr)
        sys.exit(2)


def load_policy(path):
    if not path:
        return {}
    pol = load_json(path)
    if not isinstance(pol, dict):
        print("usage error: policy JSON must be an object", file=sys.stderr)
        sys.exit(2)
    return pol


def _collapse_map(text):
    """Return (collapsed_text, index_map) where index_map[i] is the original
    offset of collapsed character i. Whitespace runs become one space."""
    collapsed = []
    imap = []
    prev_ws = True  # strip leading whitespace
    for i, ch in enumerate(text):
        if ch.isspace():
            if not prev_ws:
                collapsed.append(" ")
                imap.append(i)
            prev_ws = True
        else:
            collapsed.append(ch)
            imap.append(i)
            prev_ws = False
    if collapsed and collapsed[-1] == " ":
        collapsed.pop(); imap.pop()
    return "".join(collapsed), imap


def _collapse(text):
    return _collapse_map(text)[0]


def _line_span(text, start, end):
    start_line = text.count("\n", 0, start) + 1
    end_line = text.count("\n", 0, max(end - 1, start)) + 1
    return [start_line, end_line]


def _mk_anchor(pages_obj, page_label, text, ostart, oend, match_type, field,
               span_basis="page"):
    quote = text[ostart:oend]
    byte_start = len(text[:ostart].encode("utf-8"))
    byte_end = byte_start + len(quote.encode("utf-8"))
    return {
        "field": field,
        "file": pages_obj["file"],
        "file_sha256": pages_obj["file_sha256"],
        "page": page_label,
        "line_span": _line_span(text, ostart, oend) if span_basis == "page" else None,
        "byte_span": [byte_start, byte_end],
        "byte_span_basis": "page_text_utf8" if span_basis == "page" else "joined_pages_text_utf8",
        "quote": quote,
        "match_type": match_type,
    }


def find_anchors(pages_obj, field, value, policy):
    """Return (anchors, violations). anchors is a list (possibly many candidates);
    violations is a list of human-readable refusals (undeclared tolerances)."""
    anchors = []
    for p in pages_obj["pages"]:
        text = p["text"]
        start = 0
        while True:
            idx = text.find(value, start)
            if idx == -1:
                break
            anchors.append(_mk_anchor(pages_obj, p["page"], text, idx, idx + len(value),
                                      "exact", field))
            start = idx + 1
    if anchors:
        return anchors, []

    violations = []

    # --- whitespace-collapsed matching within one page ---
    ws_hits = []
    cval = _collapse(value)
    for p in pages_obj["pages"]:
        text = p["text"]
        ctext, imap = _collapse_map(text)
        start = 0
        while True:
            idx = ctext.find(cval, start)
            if idx == -1:
                break
            ostart = imap[idx]
            oend = imap[idx + len(cval) - 1] + 1
            ws_hits.append(_mk_anchor(pages_obj, p["page"], text, ostart, oend,
                                      "whitespace_collapsed", field))
            start = idx + 1
    if ws_hits:
        if policy.get("allow_whitespace_collapse"):
            return ws_hits, []
        violations.append(
            "value %r matches only with whitespace collapsing (e.g. across a line "
            "break), but the policy does not declare allow_whitespace_collapse" % field)

    # --- page-boundary merged matching (exact, on joined pages) ---
    pages = pages_obj["pages"]
    joined_parts, page_of = [], []
    cursor = 0
    for p in pages:
        joined_parts.append(p["text"])
        page_of.append((cursor, cursor + len(p["text"]), p["page"]))
        cursor += len(p["text"]) + 1  # +1 for the "\n" join
    joined = "\n".join(joined_parts)
    boundary_hits = []
    start = 0
    while True:
        idx = joined.find(value, start)
        if idx == -1:
            break
        end = idx + len(value)
        touched = [pg for (s, e, pg) in page_of if s < end and idx < e]
        if len(touched) > 1:
            boundary_hits.append(_mk_anchor(
                pages_obj, "%s-%s" % (touched[0], touched[-1]), joined, idx, end,
                "page_boundary_merged", field, span_basis="joined"))
        start = idx + 1
    if boundary_hits:
        if policy.get("allow_page_boundary_merge"):
            return boundary_hits, []
        violations.append(
            "value %r matches only across a page boundary (pages %s), but the policy "
            "does not declare allow_page_boundary_merge"
            % (field, boundary_hits[0]["page"]))

    # --- whitespace-collapsed AND page-boundary merged ---
    if policy.get("allow_whitespace_collapse") and policy.get("allow_page_boundary_merge"):
        ctext, imap = _collapse_map(joined)
        combo_hits = []
        start = 0
        while True:
            idx = ctext.find(cval, start)
            if idx == -1:
                break
            ostart = imap[idx]
            oend = imap[idx + len(cval) - 1] + 1
            touched = [pg for (s, e, pg) in page_of if s < oend and ostart < e]
            if len(touched) > 1:
                combo_hits.append(_mk_anchor(
                    pages_obj, "%s-%s" % (touched[0], touched[-1]), joined, ostart, oend,
                    "page_boundary_merged+whitespace_collapsed", field, span_basis="joined"))
            start = idx + 1
        if combo_hits:
            return combo_hits, []

    return [], violations


def cmd_locate(args):
    pages_obj = load_json(args.pages)
    policy = load_policy(args.policy)
    anchors, violations = find_anchors(pages_obj, args.field, args.value, policy)
    result = {
        "generated_by": "page_anchor.py locate",
        "field": args.field,
        "value": args.value,
        "file": pages_obj.get("file"),
        "file_sha256": pages_obj.get("file_sha256"),
        "policy_applied": {
            "allow_whitespace_collapse": bool(policy.get("allow_whitespace_collapse")),
            "allow_page_boundary_merge": bool(policy.get("allow_page_boundary_merge")),
        },
        "candidate_count": len(anchors),
        "anchors": anchors,
        "violations": violations,
    }
    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out + "\n")
        print("anchors written: %s (candidates=%d)" % (args.out, len(anchors)))
    else:
        print(out)
    if violations:
        for v in violations:
            print("REFUSED: %s" % v, file=sys.stderr)
        return 1
    if not anchors:
        print("NOT FOUND: value for field %r does not occur in %s (file_sha256=%s)"
              % (args.field, pages_obj.get("file"), pages_obj.get("file_sha256")),
              file=sys.stderr)
        return 1
    return 0


def _verify_one(pages_obj, anchor):
    """Return None if the anchor verifies, else an error string."""
    if anchor.get("file_sha256") != pages_obj.get("file_sha256"):
        return "file_sha256 mismatch: anchor=%s pages=%s" % (
            anchor.get("file_sha256"), pages_obj.get("file_sha256"))
    quote = anchor.get("quote")
    page = anchor.get("page")
    if isinstance(page, int):
        match = [p for p in pages_obj["pages"] if p["page"] == page]
        if not match:
            return "page %r not present in pages file" % (page,)
        text = match[0]["text"]
    else:  # "N-M" page span -> verify against joined pages
        text = "\n".join(p["text"] for p in pages_obj["pages"])
    idx = text.find(quote) if quote else -1
    if idx == -1:
        return "quote does NOT occur verbatim in the stated source text (forged or stale anchor)"
    span = anchor.get("byte_span")
    if span:
        raw = text.encode("utf-8")
        if raw[span[0]:span[1]].decode("utf-8", errors="replace") != quote:
            return "byte_span %s does not slice out the quote" % (span,)
    return None


def cmd_verify(args):
    pages_obj = load_json(args.pages)
    anchor_doc = load_json(args.anchor)
    anchors = anchor_doc.get("anchors", [anchor_doc]) if isinstance(anchor_doc, dict) else anchor_doc
    failures = []
    for i, a in enumerate(anchors):
        err = _verify_one(pages_obj, a)
        if err:
            failures.append("anchor[%d] field=%r: %s" % (i, a.get("field"), err))
    if failures:
        for f in failures:
            print("VERIFY FAILED: %s" % f, file=sys.stderr)
        return 1
    print("verify OK: %d anchor(s) check out against %s" % (len(anchors), args.pages))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("locate", help="locate a field value and emit anchors")
    pl.add_argument("--pages", required=True, help="pages JSON from facsimile_register.py")
    pl.add_argument("--field", required=True)
    pl.add_argument("--value", required=True)
    pl.add_argument("--policy", help="anchor tolerance policy JSON")
    pl.add_argument("--out", help="write result JSON here instead of stdout")
    pv = sub.add_parser("verify", help="verify anchor quote(s) against the source text")
    pv.add_argument("--pages", required=True)
    pv.add_argument("--anchor", required=True, help="anchor JSON (single anchor or locate output)")
    args = ap.parse_args(argv)
    if args.cmd == "locate":
        return cmd_locate(args)
    return cmd_verify(args)


if __name__ == "__main__":
    sys.exit(main())
