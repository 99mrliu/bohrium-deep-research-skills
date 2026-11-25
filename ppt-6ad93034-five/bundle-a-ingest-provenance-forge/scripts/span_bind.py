#!/usr/bin/env python3
"""Fail-closed binding of slide plans to verified ingest spans.

The agent writes plan.json:
  {"slides":[{"id","title",
              "bullets":[{"text","span_ids":[...],"quote":"verbatim substring"}],
              "notes","figure": optional fig_id}]}

Verification (ALL must pass, else exit 1 - fix the plan, not the checker):
  1. every span_id exists in spans.jsonl
  2. bullet "quote" is a verbatim substring (whitespace-normalized) of the
     whitespace-normalized concatenation of its spans' texts
  3. every numeric token in the bullet text appears in the spans' text
  4. slide "figure" (if present) exists in figures.json and (for figures)
     has a crop_path

Writes work/bindings.json: per-bullet verdicts + an evidence map
(bullet -> span ids, pages, quote) that build_deck.py consumes.

Usage:
    python3 span_bind.py --plan work/plan.json
"""
import argparse
import json
import os
import re
import sys

NUM_RE = re.compile(r"\d+(?:\.\d+)?%?")


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def log(msg):
    print(f"[span_bind] {msg}", flush=True)


def main():
    ap = argparse.ArgumentParser(description="Fail-closed plan-to-span binding verifier")
    ap.add_argument("--plan", default=None, help="plan.json (default: <work>/plan.json)")
    ap.add_argument("--input-dir", default=os.environ.get("CASE_INPUT_DIR", "/input"))
    ap.add_argument("--work-dir", default=os.environ.get("CASE_WORK_DIR", "/app/work"))
    ap.add_argument("--output-dir", default=os.environ.get("CASE_OUTPUT_DIR", "/app/output"))
    args = ap.parse_args()
    work = os.path.abspath(args.work_dir)
    plan_path = args.plan or os.path.join(work, "plan.json")

    spans = {}
    spans_path = os.path.join(work, "spans.jsonl")
    if os.path.isfile(spans_path):
        for line in open(spans_path, encoding="utf-8"):
            if line.strip():
                s = json.loads(line)
                spans[s["span_id"]] = s
    figures = {}
    fig_path = os.path.join(work, "figures.json")
    if os.path.isfile(fig_path):
        for f in json.load(open(fig_path, encoding="utf-8")).get("figures", []):
            figures[f["fig_id"]] = f

    bindings = {"plan": os.path.abspath(plan_path), "ok": False,
                "verdicts": [], "failures": [], "evidence_map": {}}
    try:
        plan = json.load(open(plan_path, encoding="utf-8"))
    except Exception as e:
        bindings["failures"].append({"where": "plan", "reason": f"cannot read plan: {e}"})
        _write(work, bindings)
        log(f"FAIL: cannot read plan.json: {e}")
        return 1

    for slide in plan.get("slides", []):
        sid = slide.get("id", "?")
        fig = slide.get("figure")
        if fig is not None:
            if fig not in figures:
                _fail(bindings, sid, None, f"figure id '{fig}' not in figures.json")
            elif figures[fig].get("kind") == "figure" and not figures[fig].get("crop_path"):
                _fail(bindings, sid, None,
                      f"figure '{fig}' has no crop image (see figures.json note)")
        for i, bullet in enumerate(slide.get("bullets", [])):
            bid = f"{sid}/b{i + 1}"
            span_ids = bullet.get("span_ids", [])
            quote = bullet.get("quote", "")
            text = bullet.get("text", "")
            missing = [x for x in span_ids if x not in spans]
            if not span_ids:
                _fail(bindings, sid, bid, "no span_ids; every bullet must cite evidence")
                continue
            if missing:
                _fail(bindings, sid, bid, f"unknown span_ids: {missing}")
                continue
            concat = norm(" ".join(spans[x]["text"] for x in span_ids))
            if norm(quote) not in concat:
                _fail(bindings, sid, bid,
                      f"quote is not a verbatim substring of its spans: {quote!r}")
                continue
            bad_nums = [t for t in NUM_RE.findall(text) if t not in concat]
            if bad_nums:
                _fail(bindings, sid, bid,
                      f"numeric token(s) {bad_nums} absent from cited spans; "
                      "refusing unverifiable numbers")
                continue
            pages = sorted({spans[x]["page"] for x in span_ids})
            bindings["verdicts"].append({"bullet": bid, "ok": True,
                                         "span_ids": span_ids, "pages": pages})
            bindings["evidence_map"][bid] = {
                "span_ids": span_ids,
                "pages": pages,
                "quote": quote,
                "footer": "p." + ",".join(str(p) for p in pages) + " · spans "
                          + ",".join(span_ids),
            }
            if fig:
                bindings["evidence_map"][bid]["figure"] = fig

    bindings["ok"] = not bindings["failures"]
    _write(work, bindings)
    if bindings["ok"]:
        log(f"OK: {len(bindings['verdicts'])} bullet(s) verified fail-closed")
        return 0
    log(f"FAIL: {len(bindings['failures'])} problem(s); fix the plan, not the checker")
    for f in bindings["failures"]:
        log(f"  - {f['where']}: {f['reason']}")
    return 1


def _fail(bindings, sid, bid, reason):
    bindings["failures"].append({"where": bid or sid, "reason": reason})
    bindings["verdicts"].append({"bullet": bid or sid, "ok": False, "reason": reason})


def _write(work, bindings):
    os.makedirs(work, exist_ok=True)
    with open(os.path.join(work, "bindings.json"), "w", encoding="utf-8") as f:
        json.dump(bindings, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    sys.exit(main())
