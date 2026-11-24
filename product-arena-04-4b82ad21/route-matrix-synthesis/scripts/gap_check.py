#!/usr/bin/env python3
"""gap_check.py -- check that a draft Introduction's gap follows from the
filled comparison matrix.

Checks (hard failures, exit 1):
  a. Gap coverage: each sentence of the gap paragraph must share >=3
     content tokens (after stopword removal and light stemming) with at
     least one stated_limitation cell quote in the matrix -- i.e. the gap
     is derivable from documented limitations.
  b. Counterexample lint: for every reference whose non-limitation matrix
     cells claim a capability sharing >=3 content tokens with the gap
     paragraph, the gap paragraph must mention that reference (citation
     number, author surname, method name or key) -- otherwise it is an
     unhandled counterexample.
  c. Contribution anchors: every contribution bullet must contain an
     anchor from case.json constraints.available_anchors (e.g. "Fig 1").
  d. Citations: every Vancouver citation number used in the draft must map
     to a reference of the filled matrix (via each reference's
     citation_number field).

Draft conventions (documented in SKILL.md): the gap lives in a section
whose heading contains "gap"; contributions are bullets under a heading
containing "contribution". Fallbacks: a paragraph starting with "Gap:"
and any bullet lines in the document.

Pure Python 3 stdlib. Exit codes: 0 = pass, 1 = findings, 2 = usage/IO error.
"""

import argparse
import json
import re
import sys

STOPWORDS = set("""
a an the and or but of to in on for with without by is are was were be been
it its this that these those from as at which who whom whose when where what
how not no than then so such into over under across per each same most more
less up down out about between using use used via all any both can could may
might will would should has have had do does did we our they their them he
she his her also based because while there only own other another however
thus therefore if after before during within among through what is missing
method methods approach approaches prediction predictions predict predicts
predicted result results best remain remains open show shows shown present
work field study paper novel new technique techniques tool tools model models
""".split())

CAPABILITY_AXES = [
    "problem_setting",
    "inputs_required",
    "scoring_or_integration_stage",
    "evaluation_setting",
    "decisive_comparison",
]


def norm_ws(text):
    return re.sub(r"\s+", " ", text or "").strip()


def stem(token):
    if (len(token) > 3 and token.endswith("s")
            and not token.endswith(("ss", "us"))):
        return token[:-1]
    return token


def content_tokens(text):
    return {
        stem(t)
        for t in re.findall(r"[a-z0-9]+", text.lower())
        if len(t) >= 3 and t not in STOPWORDS
    }


def load_json(path, what):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        sys.stderr.write("error: %s not found: %s\n" % (what, path))
        sys.exit(2)
    except json.JSONDecodeError as exc:
        sys.stderr.write("error: invalid JSON in %s (%s): %s\n"
                         % (path, what, exc))
        sys.exit(2)


def load_text(path, what):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        sys.stderr.write("error: %s not found: %s\n" % (what, path))
        sys.exit(2)


def split_sections(md):
    """Return list of (header, [body lines]). Header '' = preamble."""
    sections = []
    header, body = "", []
    for line in md.splitlines():
        m = re.match(r"^#{1,6}\s+(.*)", line)
        if m:
            sections.append((header, body))
            header, body = m.group(1).strip(), []
        else:
            body.append(line)
    sections.append((header, body))
    return sections


def extract_gap_text(md):
    sections = split_sections(md)
    for header, body in sections:
        if "gap" in header.lower():
            text = norm_ws(" ".join(
                l for l in body
                if l.strip() and not l.lstrip().startswith(("-", "*"))))
            if text:
                return text
    # fallback: paragraph starting with "Gap:" / "Research gap:"
    m = re.search(r"(?:^|\n)\s*(?:research\s+)?gap\s*:\s*(.+?)(?:\n\s*\n|\Z)",
                  md, re.IGNORECASE | re.DOTALL)
    return norm_ws(m.group(1)) if m else ""


def collect_bullets(lines):
    """Collect bullet items, joining wrapped continuation lines."""
    bullets, current = [], None
    for line in lines:
        m = re.match(r"\s*(?:[-*]|\d+[.)])\s+(.*)", line)
        if m:
            if current:
                bullets.append(norm_ws(current))
            current = m.group(1)
        elif current is not None and line.strip():
            current += " " + line.strip()
        elif current is not None and not line.strip():
            bullets.append(norm_ws(current))
            current = None
    if current:
        bullets.append(norm_ws(current))
    return [b for b in bullets if b]


def extract_contributions(md):
    sections = split_sections(md)
    for header, body in sections:
        if "contribution" in header.lower():
            bullets = collect_bullets(body)
            if bullets:
                return bullets
    # fallback: all bullets in the document
    return collect_bullets(md.splitlines())


def split_sentences(text):
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if len(p.strip()) > 1]


def ref_aliases(ref):
    """Acceptable mention forms inside the gap paragraph."""
    aliases = set()
    key = ref.get("key", "")
    if key:
        aliases.add(key.lower())
    for author in ref.get("authors", []) or []:
        surname = author.split(",")[0].split()[-1] if author else ""
        if len(surname) >= 3:
            aliases.add(surname.lower())
    title = ref.get("title", "") or ref.get("available_text", {}).get("title", "")
    if ":" in title:
        name = title.split(":")[0].strip()
        if 3 <= len(name) <= 40:
            aliases.add(name.lower())
    num = ref.get("citation_number")
    if isinstance(num, int):
        aliases.add("[%d]" % num)
    return aliases


def ref_mentioned(ref, gap_text_lower):
    return any(alias in gap_text_lower for alias in ref_aliases(ref))


def citation_numbers_used(md):
    nums = set()
    for group in re.findall(r"\[(\d+(?:\s*[,;-]\s*\d+)*)\]", md):
        for piece in re.split(r"[,;]\s*", group):
            piece = piece.strip()
            if piece.isdigit():
                nums.add(int(piece))
    return nums


def check(case, matrix, draft_md):
    failures = []
    warnings = []
    details = {}

    gap_text = extract_gap_text(draft_md)
    contributions = extract_contributions(draft_md)
    gap_sentences = split_sentences(gap_text)
    gap_tokens = content_tokens(gap_text)
    gap_lower = gap_text.lower()

    if not gap_text:
        failures.append("no_gap_paragraph: no section headed with 'gap' and "
                        "no 'Gap:' paragraph found in the draft")
    if not contributions:
        failures.append("no_contributions: no contribution bullets found "
                        "under a heading containing 'contribution'")

    refs = matrix.get("references", [])

    # (a) gap coverage against stated_limitation quotes
    limitation_quotes = []
    for ref in refs:
        cell = ref.get("cells", {}).get("stated_limitation", {})
        quote = norm_ws(cell.get("quote", "")) or norm_ws(cell.get("text", ""))
        if quote:
            limitation_quotes.append((ref.get("key", ""), quote,
                                      content_tokens(quote)))
    uncovered = []
    coverage = []
    for sent in gap_sentences:
        toks = content_tokens(sent)
        best_key, best_n = None, 0
        for key, _quote, qtoks in limitation_quotes:
            n = len(toks & qtoks)
            if n > best_n:
                best_key, best_n = key, n
        coverage.append({"sentence": sent, "best_match_ref": best_key,
                         "overlap_tokens": best_n})
        if best_n < 3:
            uncovered.append(sent)
    for sent in uncovered:
        failures.append(
            "uncovered_gap_sentence: shares <3 content tokens with every "
            "stated_limitation quote: \"%s\"" % sent[:120])
    details["gap_coverage"] = coverage

    # (b) counterexample lint
    # A reference is a candidate counterexample when its capability cells
    # share >=3 content tokens with the gap paragraph AND at least 2 of the
    # shared tokens are DISTINCTIVE (they appear in the capability text of at
    # most 2 references). The distinctiveness filter keeps generic field
    # vocabulary ("template", "target", "precision", ...) from flagging every
    # reference; it is a heuristic screen, not a semantic judgement.
    cap_tokens_by_ref = {}
    for ref in refs:
        cells = ref.get("cells", {})
        cap_text = " ".join(
            norm_ws(cells.get(axis, {}).get("text", "")) + " "
            + norm_ws(cells.get(axis, {}).get("quote", ""))
            for axis in CAPABILITY_AXES)
        cap_tokens_by_ref[ref.get("key", "")] = content_tokens(cap_text)
    doc_freq = {}
    for toks in cap_tokens_by_ref.values():
        for tok in toks:
            doc_freq[tok] = doc_freq.get(tok, 0) + 1

    counterexamples = []
    acknowledged = []
    for ref in refs:
        key = ref.get("key", "")
        shared = cap_tokens_by_ref.get(key, set()) & gap_tokens
        distinctive = sorted(t for t in shared if doc_freq.get(t, 0) <= 2)
        if len(shared) >= 3 and len(distinctive) >= 2:
            entry = {"ref": key, "shared_tokens": sorted(shared),
                     "distinctive_shared_tokens": distinctive}
            if ref_mentioned(ref, gap_lower):
                acknowledged.append(entry)
            else:
                counterexamples.append(entry)
                failures.append(
                    "unhandled_counterexample: `%s` claims capabilities on "
                    "the gap's axes (distinctive shared terms: %s) but the "
                    "gap paragraph never scopes or acknowledges it"
                    % (key, ", ".join(distinctive)))
    details["counterexamples_acknowledged"] = acknowledged
    details["counterexamples_unhandled"] = counterexamples

    # (c) contribution anchors
    anchors = (case.get("constraints", {}) or {}).get("available_anchors", [])
    if not anchors:
        warnings.append("no_available_anchors: case.json lists no "
                        "constraints.available_anchors; anchor check skipped")
    anchor_report = []
    for bullet in contributions:
        found = [a for a in anchors if a.lower() in bullet.lower()]
        anchor_report.append({"bullet": bullet, "anchors_found": found})
        if anchors and not found:
            failures.append(
                "contribution_without_anchor: contribution has no anchor "
                "from constraints.available_anchors (%s): \"%s\""
                % (", ".join(anchors), bullet[:100]))
    details["contribution_anchors"] = anchor_report

    # (d) citations only from the bibliography (via matrix citation_number)
    used = citation_numbers_used(draft_md)
    known = {r.get("citation_number"): r.get("key", "")
             for r in refs if isinstance(r.get("citation_number"), int)}
    if not known:
        warnings.append("citation_map_missing: no reference in the matrix "
                        "carries a citation_number; cannot verify that cited "
                        "numbers belong to the bibliography")
    bad = sorted(n for n in used if known and n not in known)
    for n in bad:
        failures.append("citation_not_in_bibliography: draft cites [%d], "
                        "which maps to no bibliography reference" % n)
    details["citations"] = {"used": sorted(used),
                            "known": {str(k): v for k, v in
                                      sorted(known.items())},
                            "unknown_cited": bad}

    return failures, warnings, details


def main():
    ap = argparse.ArgumentParser(
        description="Check that the draft gap follows from the matrix.")
    ap.add_argument("--case", required=True, help="case.json")
    ap.add_argument("--matrix", required=True, help="filled matrix.json")
    ap.add_argument("--draft", required=True,
                    help="draft introduction (Markdown)")
    ap.add_argument("--out", required=True, help="gap report JSON path")
    args = ap.parse_args()

    case = load_json(args.case, "case")
    matrix = load_json(args.matrix, "matrix")
    draft_md = load_text(args.draft, "draft")

    failures, warnings, details = check(case, matrix, draft_md)

    summary_lines = []
    cov = details.get("gap_coverage", [])
    summary_lines.append(
        "gap sentences: %d, all covered by limitation quotes: %s"
        % (len(cov), "yes" if cov and all(
            c["overlap_tokens"] >= 3 for c in cov) else "no"))
    summary_lines.append("counterexamples acknowledged: %d"
                         % len(details.get("counterexamples_acknowledged", [])))
    anchors_ok = all(a["anchors_found"] or not a
                     for a in details.get("contribution_anchors", []))
    summary_lines.append("contribution anchors present: %s"
                         % ("yes" if anchors_ok else "no"))
    summary_lines.append("unknown citations: %s"
                         % (details.get("citations", {})
                            .get("unknown_cited", []) or "none"))

    report = {
        "case_id": case.get("case_id", "unknown"),
        "draft": args.draft,
        "matrix": args.matrix,
        "status": "fail" if failures else "pass",
        "n_failures": len(failures),
        "n_warnings": len(warnings),
        "failures": failures,
        "warnings": warnings,
        "details": details,
        "summary": " | ".join(summary_lines),
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print("gap_check: %s (%d failures, %d warnings) -> %s"
          % (report["status"].upper(), len(failures), len(warnings), args.out))
    print("  " + report["summary"])
    for item in failures:
        print("  FAIL  " + item)
    for item in warnings:
        print("  warn  " + item)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
