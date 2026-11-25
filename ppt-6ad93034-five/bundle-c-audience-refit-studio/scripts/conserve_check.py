#!/usr/bin/env python3
"""conserve_check.py — numeric-conservation + terminology audit for refits.

Verifies, between the before model and the after deck:
  (a) NUMERIC CONSERVATION — deck-wide multiset of numeric tokens (decimals,
      thousands separators, %, scientific x10^n, e-notation, glued unit
      symbols).  Every NEW token must appear verbatim in the paper text or
      be declared in an op's "introduced_numbers".  Every DROPPED token must
      be declared in an op's "dropped_numbers" or occur only on slides that
      an op deleted.
  (b) TERMINOLOGY — every locked term's total deck occurrences before vs
      after; loss must be explained by deleted slides or op-declared
      "dropped_terms".  Also flags edit-distance-1 misspellings of locked
      terms (normalised) as fabrication suspects.
  (c) SURGICAL SCOPE — slides not named by any op must be byte-identical in
      text (sha256 of slide text from the before model vs the re-read after
      deck).
  (d) SLIDE COUNT — vs target_slides from the ops file or the work order.

Exit code 0 iff every check PASSes; exit 1 otherwise.  The full audit is
always written to --out.

Usage:
  conserve_check.py --before work/model.json --after out/presentation.pptx \
      --terms work/terms.json --paper-text work/paper.txt \
      --ops work/refit_ops.json --out /app/output/refit_audit.json
"""

import argparse
import collections
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deck_io  # noqa: E402

NUM_RE = re.compile(
    r"\d+(?:,\d{3})*(?:\.\d+)?"
    r"(?:[eE][-+]?\d+)?"
    r"(?:\s*[×xX]\s*10\^?[-+]?\d+)?"
    r"(?:%|°|[µμa-zA-Z]{1,3}|%[a-zA-Z]{1,2})?%?")


def numbers_of(text):
    return [m.group(0).strip() for m in NUM_RE.finditer(text) if m.group(0).strip()]


def deck_number_counter(model):
    c = collections.Counter()
    for s in model["slides"]:
        c.update(numbers_of("\n".join(p["text"] for p in s["paras"])))
    return c


def norm_token(tok):
    return re.sub(r"\s+", "", tok)


def _lev(a, b):
    if abs(len(a) - len(b)) > 1:
        return 2
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (0 if ca == cb else 1)))
        prev = cur
    return prev[-1]


def norm_surface(s):
    return re.sub(r"[^0-9a-z]+", "", s.lower())


def simulate_ops(before_model, ops):
    """Replay ops over part names to learn: which parts each op names, which
    parts get deleted, and the expected final part list (new slides named
    ppt/slides/slideN.xml with the same numbering rule as deck_io.write)."""
    state = [s["part"] for s in before_model["slides"]]
    named = set()
    deleted = []
    max_num = max([int(re.search(r"slide(\d+)\.xml$", p).group(1))
                   for p in state] + [0])
    seq = 0
    for op in ops:
        kind = op.get("op")
        if kind in ("rewrite_paras", "set_notes"):
            i = op["slide"]
            if 0 <= i < len(state):
                named.add(state[i])
        elif kind == "delete_slide":
            i = op["slide"]
            if 0 <= i < len(state):
                named.add(state[i])
                deleted.append(state[i])
                state.pop(i)
        elif kind == "move_slide":
            if 0 <= op["from"] < len(state) and 0 <= op["to"] < len(state):
                named.add(state[op["from"]])
                state.insert(op["to"], state.pop(op["from"]))
        elif kind == "add_slide":
            if 0 <= op["donor"] < len(state):
                seq += 1
                newp = "ppt/slides/slide%d.xml" % (max_num + seq)
                named.add(newp)
                pos = (state.index(state[op["after"]]) + 1
                       if 0 <= op.get("after", -1) < len(state) else 0)
                state.insert(pos, newp)
    return named, deleted, state


def load_after(path):
    if path.lower().endswith(".pptx"):
        return deck_io.read_deck(path)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main(argv=None):
    ap = argparse.ArgumentParser(description="refit conservation audit")
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--terms", required=True)
    ap.add_argument("--paper-text", required=True)
    ap.add_argument("--ops", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    with open(args.before, encoding="utf-8") as f:
        before = json.load(f)
    after = load_after(args.after)
    with open(args.terms, encoding="utf-8") as f:
        terms = json.load(f)
    with open(args.paper_text, encoding="utf-8") as f:
        paper = f.read()
    with open(args.ops, encoding="utf-8") as f:
        ops_data = json.load(f)
    ops = ops_data.get("ops", []) if isinstance(ops_data, dict) else ops_data

    named, deleted_parts, expected_parts = simulate_ops(before, ops)
    after_parts = [s["part"] for s in after["slides"]]
    introduced = set()
    dropped_declared = set()
    terms_dropped_declared = set()
    for op in ops:
        introduced.update(norm_token(str(x)) for x in op.get("introduced_numbers", []))
        dropped_declared.update(norm_token(str(x)) for x in op.get("dropped_numbers", []))
        terms_dropped_declared.update(op.get("dropped_terms", []))

    failures = []
    checks = {}

    # ------------------------------------------------------------------ (a)
    before_c = deck_number_counter(before)
    after_c = deck_number_counter(after)
    deleted_c = collections.Counter()
    for s in before["slides"]:
        if s["part"] in deleted_parts:
            deleted_c.update(numbers_of("\n".join(p["text"] for p in s["paras"])))

    new_unjustified, new_justified = {}, {}
    for tok, cnt in (after_c - before_c).items():
        if norm_token(tok) in introduced or tok in paper:
            new_justified[tok] = cnt
        else:
            new_unjustified[tok] = cnt
    dropped_unjustified = {}
    for tok, cnt in (before_c - after_c).items():
        if norm_token(tok) in dropped_declared:
            continue
        if deleted_c.get(tok, 0) >= cnt:
            continue
        dropped_unjustified[tok] = {"count": cnt,
                                    "on_deleted_slides": deleted_c.get(tok, 0)}

    numeric_failures = []
    for tok, cnt in sorted(new_unjustified.items()):
        numeric_failures.append(
            "NEW number '%s' (x%d) not found in paper text and not declared "
            "in any op's introduced_numbers" % (tok, cnt))
    for tok, info in sorted(dropped_unjustified.items()):
        numeric_failures.append(
            "DROPPED number '%s' (x%d, only x%d on deleted slides) not "
            "declared in any op's dropped_numbers"
            % (tok, info["count"], info["on_deleted_slides"]))
    checks["numeric_conservation"] = {
        "verdict": "FAIL" if numeric_failures else "PASS",
        "before_tokens": sum(before_c.values()),
        "after_tokens": sum(after_c.values()),
        "new_justified": new_justified,
        "dropped_on_deleted_slides": dict(deleted_c),
        "failures": numeric_failures,
    }
    failures += numeric_failures

    # ------------------------------------------------------------------ (b)
    before_text = "\n".join(p["text"] for s in before["slides"]
                            for p in s["paras"])
    after_text = "\n".join(p["text"] for s in after["slides"]
                           for p in s["paras"])
    term_failures, term_losses = [], []
    for e in terms.get("locked", []):
        surf = e["surface"]
        b = before_text.count(surf)
        a = after_text.count(surf)
        if a >= b:
            continue
        loss = b - a
        on_deleted = sum(s["part"] in deleted_parts and
                         "\n".join(p["text"] for p in s["paras"]).count(surf)
                         for s in before["slides"])
        explained = on_deleted >= loss or surf in terms_dropped_declared
        term_losses.append({"term": surf, "before": b, "after": a,
                            "on_deleted_slides": on_deleted,
                            "declared_dropped": surf in terms_dropped_declared})
        if not explained:
            term_failures.append(
                "LOCKED term '%s' lost %d occurrence(s) (before=%d after=%d, "
                "%d on deleted slides, not in any op's dropped_terms)"
                % (surf, loss, b, a, on_deleted))
    locked_norms = {norm_surface(e["surface"]) for e in terms.get("locked", [])}
    after_words = re.findall(r"[A-Za-zµμ][A-Za-z0-9µμ\-]*", after_text)
    misspellings = {}
    for e in terms.get("locked", []):
        tn = norm_surface(e["surface"])
        if len(tn) < 4:
            continue
        for w in set(after_words):
            wn = norm_surface(w)
            if len(wn) >= 4 and wn not in locked_norms and _lev(wn, tn) == 1:
                misspellings.setdefault(e["surface"], []).append(w)
    for surf, cands in sorted(misspellings.items()):
        term_failures.append(
            "possible MISSPELLING of locked term '%s': %s"
            % (surf, ", ".join(sorted(cands))))
    checks["terminology"] = {
        "verdict": "FAIL" if term_failures else "PASS",
        "locked_terms": len(terms.get("locked", [])),
        "losses": term_losses,
        "misspellings": misspellings,
        "failures": term_failures,
    }
    failures += term_failures

    # ------------------------------------------------------------------ (c)
    after_by_part = {s["part"]: s for s in after["slides"]}
    scope_failures = []
    untouched = 0
    for s in before["slides"]:
        if s["part"] in named:
            continue
        untouched += 1
        aft = after_by_part.get(s["part"])
        if aft is None:
            scope_failures.append(
                "untouched slide %s (%s) missing from output deck"
                % (s["index"], s["part"]))
        elif aft["text_hash"] != s["text_hash"]:
            scope_failures.append(
                "untouched slide %s (%s) TEXT CHANGED without an op naming it"
                % (s["index"], s["part"]))
    structural_ok = (set(after_parts) == set(expected_parts))
    if not structural_ok:
        scope_failures.append(
            "output slide part set != expected after ops (missing: %s; "
            "unexpected: %s)" % (sorted(set(expected_parts) - set(after_parts)),
                                 sorted(set(after_parts) - set(expected_parts))))
    checks["surgical_scope"] = {
        "verdict": "FAIL" if scope_failures else "PASS",
        "untouched_slides": untouched,
        "ops_named_parts": sorted(named),
        "deleted_parts": sorted(deleted_parts),
        "failures": scope_failures,
    }
    failures += scope_failures

    # ------------------------------------------------------------------ (d)
    target = ops_data.get("target_slides") if isinstance(ops_data, dict) else None
    if target is None:
        wdir = os.environ.get("CASE_WORK_DIR") or os.path.dirname(args.ops)
        for cand in (os.path.join(wdir, "workorder.json"),
                     os.path.join(wdir, "artifacts", "slide-workorder.json")):
            if os.path.exists(cand):
                with open(cand, encoding="utf-8") as f:
                    wo = json.load(f)
                target = wo.get("target_slides")
                if target is not None:
                    break
    actual = len(after["slides"])
    if target is None:
        checks["slide_count"] = {"verdict": "PASS", "target": None,
                                 "actual": actual, "note": "no target given"}
    elif actual != target:
        checks["slide_count"] = {"verdict": "FAIL", "target": target,
                                 "actual": actual,
                                 "failures": ["slide count %d != target %d"
                                              % (actual, target)]}
        failures.append("slide count %d != workorder target %d" % (actual, target))
    else:
        checks["slide_count"] = {"verdict": "PASS", "target": target,
                                 "actual": actual}

    verdict = "FAIL" if failures else "PASS"
    audit = {
        "tool": "conserve_check",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "verdict": verdict,
        "checks": checks,
        "failures": failures,
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=1)

    print("conserve_check verdict: %s (%d checks failed)" % (verdict, len(failures)))
    for line in failures:
        print("  FAIL: %s" % line)
    print("wrote", args.out)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
