#!/usr/bin/env python3
"""coverage_ledger.py - build the citation coverage ledger for a case.

Part of the citation-coverage-auditor skill. Pure Python 3 stdlib.

Computes, from case.json + bib.json + the draft:
  * cited vs uncited references;
  * distinct citation count vs constraints.min_distinct_citations;
  * each constraints.must_cover_topics phrase mapped to >=1 cited ref via
    content-word overlap between the topic phrase and ref title+abstract
    (the mapping, or the gap, is reported);
  * recency profile: histogram of cited-ref years; flags when the most recent
    bibliography entries are ignored;
  * "closest work" identification: refs ranked by content-word overlap with the
    problem statement in the manuscript facts (path read from
    case.json material.manuscript_facts); any top-2 closest ref left uncited
    is flagged;
  * decorative-citation lint (warning): bibliography-tail refs cited exactly
    once, inside a cluster of 3+ markers, with no sentence-level role.

Hard failures (-> exit 1): min_distinct_citations not met; a mandated topic
with no cited candidate ref; a top-2 closest ref uncited.
Warnings (never exit 1 alone): recency gap, decorative citations, uncited refs.

NOTE: all coverage judgments here are LEXICAL OVERLAP heuristics. A human or
model writer must confirm semantic relevance; this script only flags.

Exit codes: 0 pass, 1 findings, 2 usage error.
"""
import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

MARKER_RE = re.compile(r"\[(\d+(?:\s*[,\-]\s*\d+)*)\]")

STOPWORDS = set("""
a an the and or of to in on for with by from at as is are was were be been being
it its this that these those we our their his her they them he she over under
between across per vs into using use used using based via within without each
such than then when where which who whom whose what how why not no nor but if
can could may might shall should will would do does did done have has had
only also more most other others some any all both few many much less least
""".split())


def stem(w):
    if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def content_words(text):
    """Lowercase content-word set; hyphenated words contribute their parts."""
    out = set()
    for w in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.lower()):
        for p in w.split("-"):
            if len(p) > 2 and p not in STOPWORDS:
                out.add(stem(p))
    return out


def expand_marker(body):
    nums = []
    for part in body.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            nums.extend(range(int(a), int(b) + 1))
        else:
            nums.append(int(part))
    return nums


SENT_END_RE = re.compile(r"[.!?](?=\s+[A-Z(]|$)")


def sentence_spans(text):
    """Naive sentence segmentation robust to decimals like 0.55."""
    spans, start = [], 0
    for m in SENT_END_RE.finditer(text):
        spans.append((start, m.end()))
        start = m.end()
    if start < len(text):
        spans.append((start, len(text)))
    return [(a, b, text[a:b]) for a, b in spans if text[a:b].strip()]


def sentence_for_offset(spans, offset):
    for a, b, s in spans:
        if a <= offset < b:
            return s
    return ""


def read_problem_statement(facts_path):
    """Extract the problem statement line from the manuscript facts markdown."""
    if not facts_path or not Path(facts_path).is_file():
        return ""
    for line in Path(facts_path).read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*-\s*Problem:\s*(.+)$", line)
        if m:
            return m.group(1).strip()
    # fall back: the '## Present work' block's first 3 bullet lines
    bullets = [ln.strip("- ").strip() for ln in
               Path(facts_path).read_text(encoding="utf-8").splitlines()
               if ln.strip().startswith("- ")]
    return " ".join(bullets[:3])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the citation coverage ledger.")
    ap.add_argument("--case", required=True, help="case.json path")
    ap.add_argument("--bib", required=True, help="bib.json produced by bib_parse.py")
    ap.add_argument("--draft", required=True, help="manuscript draft markdown")
    ap.add_argument("--out-dir", required=True, help="directory for coverage_ledger.{json,md}")
    args = ap.parse_args(argv)

    case_path, bib_path, draft_path = Path(args.case), Path(args.bib), Path(args.draft)
    for p, flag in ((case_path, "--case"), (bib_path, "--bib"), (draft_path, "--draft")):
        if not p.is_file():
            print("error: %s file not found: %s" % (flag, p), file=sys.stderr)
            return 2
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    case = json.loads(case_path.read_text(encoding="utf-8"))
    bib = json.loads(bib_path.read_text(encoding="utf-8"))
    text = draft_path.read_text(encoding="utf-8")
    constraints = case.get("constraints", {})

    markers = [(m.start(), expand_marker(m.group(1))) for m in MARKER_RE.finditer(text)]
    spans = sentence_spans(text)
    cited_numbers = sorted({n for _, nums in markers for n in nums})
    n_bib = len(bib)
    key_of = {i + 1: e.get("key", "ref%02d" % (i + 1)) for i, e in enumerate(bib)}
    cited_keys = [key_of[n] for n in cited_numbers if 1 <= n <= n_bib]
    cited_set = set(cited_keys)
    uncited = [{"number": i + 1, "key": key_of[i + 1], "title": bib[i].get("title", "")}
               for i in range(n_bib) if key_of[i + 1] not in cited_set]

    failures, warnings = [], []

    # 1. distinct citation count
    min_req = constraints.get("min_distinct_citations")
    distinct = len(cited_keys)
    min_ok = True if min_req is None else distinct >= min_req
    if not min_ok:
        failures.append("distinct citations %d below required minimum %d" % (distinct, min_req))

    # 2. must_cover_topics
    ref_words = {e.get("key", key_of[i + 1]): content_words(
        e.get("title", "") + " " + e.get("abstract", "")) for i, e in enumerate(bib)}
    topic_reports = []
    for topic in constraints.get("must_cover_topics", []):
        tw = content_words(topic)
        scored = sorted(
            ({"key": k, "overlap": len(tw & rw), "shared": sorted(tw & rw)}
             for k, rw in ref_words.items()),
            key=lambda d: (-d["overlap"], d["key"]))
        candidates = [d for d in scored if d["overlap"] > 0]
        cited_candidates = [d for d in candidates if d["key"] in cited_set]
        covered = bool(cited_candidates)
        if not covered:
            failures.append("mandated topic not covered by any cited reference: %r" % topic)
        topic_reports.append({
            "topic": topic,
            "covered": covered,
            "covered_by": [d["key"] for d in cited_candidates[:3]],
            "candidates": candidates[:3],
            "note": "lexical-overlap heuristic; confirm semantic relevance by reading",
        })

    # 3. recency profile
    year_of = {}
    for i, e in enumerate(bib):
        y = e.get("year")
        if isinstance(y, int):
            year_of[key_of[i + 1]] = y
    hist = Counter(str(year_of[k]) for k in cited_keys if k in year_of)
    newest_year = max(year_of.values()) if year_of else None
    ignored_recent = [k for k, y in year_of.items()
                      if y == newest_year and k not in cited_set] if newest_year else []
    if ignored_recent:
        warnings.append("most recent bibliography entries ignored: %s (year %s)"
                        % (", ".join(ignored_recent), newest_year))

    # 4. closest-work identification
    facts_rel = case.get("material", {}).get("manuscript_facts")
    facts_path = (case_path.parent / facts_rel) if facts_rel else None
    problem = read_problem_statement(facts_path)
    pw = content_words(problem)
    closest_ranking = sorted(
        ({"key": k, "overlap": len(pw & rw), "shared": sorted(pw & rw)}
         for k, rw in ref_words.items()),
        key=lambda d: (-d["overlap"], d["key"]))
    top2 = [d for d in closest_ranking[:2] if d["overlap"] > 0]
    top2_uncited = [d for d in top2 if d["key"] not in cited_set]
    for d in top2_uncited:
        failures.append("top-2 closest work to the problem statement is uncited: %s "
                        "(overlap %d)" % (d["key"], d["overlap"]))

    # 5. decorative-citation lint
    tail_start = n_bib - max(1, math.ceil(n_bib / 3)) + 1  # last third of the list
    cite_counts = Counter(n for _, nums in markers for n in nums)
    decorative = []
    for n in range(tail_start, n_bib + 1):
        if cite_counts.get(n, 0) != 1:
            continue
        for off, nums in markers:
            if n in nums and len(nums) >= 3:
                sent = sentence_for_offset(spans, off)
                sent_wo = MARKER_RE.sub(" ", sent)
                e = bib[n - 1]
                role_words = content_words(e.get("title", "")) | {
                    a.split(",")[0].strip().lower() for a in e.get("authors", [])}
                if not (content_words(sent_wo) & role_words):
                    decorative.append({
                        "number": n, "key": key_of[n], "cluster_size": len(nums),
                        "sentence": re.sub(r"\s+", " ", sent).strip()[:160],
                        "note": "tail reference cited exactly once, inside a %d-marker "
                                "cluster, with no sentence-level role (heuristic warning)"
                                % len(nums),
                    })
    for d in decorative:
        warnings.append("decorative-citation lint: [%d] (%s)" % (d["number"], d["key"]))

    status = "fail" if failures else ("pass_with_warnings" if warnings else "pass")
    ledger = {
        "case_id": case.get("case_id"),
        "status": status,
        "cited_refs": cited_keys,
        "uncited_refs": uncited,
        "distinct_citations": distinct,
        "min_distinct_citations": min_req,
        "min_distinct_ok": min_ok,
        "must_cover_topics": topic_reports,
        "recency": {
            "cited_year_histogram": dict(sorted(hist.items())),
            "newest_bibliography_year": newest_year,
            "most_recent_entries_ignored": ignored_recent,
        },
        "closest_work": {
            "problem_statement": problem,
            "ranking": closest_ranking,
            "top2": top2,
            "top2_uncited": [d["key"] for d in top2_uncited],
            "note": "lexical-overlap heuristic over the problem statement; "
                    "confirm the closest works by reading",
        },
        "decorative_citation_warnings": decorative,
        "failures": failures,
        "warnings": warnings,
    }
    (out_dir / "coverage_ledger.json").write_text(
        json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # readable ledger with checklist table
    lines = [
        "# Coverage ledger — %s" % case.get("case_id"),
        "",
        "Status: **%s**" % status,
        "",
        "## Coverage checklist",
        "",
        "| # | check | result | detail |",
        "|---|---|---|---|",
        "| 1 | distinct citations >= %s | %s | %d distinct refs cited: %s |" % (
            min_req, "PASS" if min_ok else "FAIL", distinct,
            ", ".join(cited_keys) or "(none)"),
    ]
    for i, t in enumerate(topic_reports, start=2):
        lines.append("| %d | topic covered: \"%s\" | %s | %s |" % (
            i, t["topic"], "PASS" if t["covered"] else "FAIL",
            ("cited candidates: " + ", ".join(t["covered_by"]))
            if t["covered_by"] else
            ("candidates exist but uncited: "
             + ", ".join(d["key"] for d in t["candidates"]) if t["candidates"]
             else "no candidate ref in bibliography")))
    row = 1 + len(topic_reports)
    lines.append("| %d | top-2 closest works cited | %s | ranking: %s |" % (
        row + 1, "PASS" if not top2_uncited else "FAIL",
        ", ".join("%s(%d)" % (d["key"], d["overlap"]) for d in closest_ranking[:4])))
    lines.append("| %d | recency | %s | cited years: %s%s |" % (
        row + 2, "WARN" if ignored_recent else "PASS",
        ", ".join("%s x%d" % (y, c) for y, c in sorted(hist.items())) or "(none)",
        ("; newest year %s ignored: %s" % (newest_year, ", ".join(ignored_recent)))
        if ignored_recent else ""))
    lines.append("| %d | no decorative citations | %s | %s |" % (
        row + 3, "WARN" if decorative else "PASS",
        ("%d warning(s)" % len(decorative)) if decorative else "no suspicious clusters"))
    lines.append("| %d | no uncited bibliography entries | %s | %s |" % (
        row + 4, "WARN" if uncited else "PASS",
        ("uncited: " + ", ".join(u["key"] for u in uncited)) if uncited else "all entries cited"))
    lines += ["", "## Closest-work ranking (overlap with problem statement)", ""]
    for d in closest_ranking:
        lines.append("- %s: overlap %d %s" % (d["key"], d["overlap"],
                                              ("shared: " + ", ".join(d["shared"]))
                                              if d["shared"] else ""))
    if decorative:
        lines += ["", "## Decorative-citation warnings", ""]
        for d in decorative:
            lines.append("- [%d] (%s): %s" % (d["number"], d["key"], d["note"]))
    lines += ["", "Heuristic notice: topic mapping, closest-work ranking and the",
              "decorative lint use lexical overlap only; the writer must confirm",
              "semantic relevance by reading the provided reference texts.", ""]
    (out_dir / "coverage_ledger.md").write_text("\n".join(lines), encoding="utf-8")

    print("coverage ledger: %s | distinct %d/%s | topics %d/%d covered | "
          "top-2 closest uncited: %d | warnings: %d"
          % (status, distinct, min_req, sum(1 for t in topic_reports if t["covered"]),
             len(topic_reports), len(top2_uncited), len(warnings)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
