#!/usr/bin/env python3
"""validate_output.py — check the whole /app/output set; write validation_report.json.

Checks (each recorded pass/fail/warn with detail):
  result.json      parses; has case_id; has every required contract field
  deck.pptx        valid zip; all XML well-formed; slide count within limit
  notes            every slide has a notes part with non-empty text
  placeholders     WARN if any "[pending" / "TODO" stubs remain (partial signal)
  previews         if a render manifest with status ok exists, PNG count matches
                   slide count; if manifest says renderer_unavailable -> WARN

deliverable_state: complete | partial | broken. Exit 1 on broken, else 0.

Usage:
  python3 validate_output.py [--outdir /app/output] [--case /input/case.json] \
      [--state /app/work/session_state.json] [--deck deck.pptx]
"""
import argparse
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
from xml.etree import ElementTree as ET


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def contract_fields(case):
    oc = case.get("output_contract") or case.get("outputContract") or {}
    raw = oc if isinstance(oc, list) else (oc.get("required_fields") or oc.get("required")
                                           or oc.get("fields") or oc.get("requiredFields") or []) \
        if isinstance(oc, dict) else []
    names = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, str) and item.strip():
            names.append(item.strip())
        elif isinstance(item, dict):
            for k in ("name", "field", "key", "id"):
                if isinstance(item.get(k), str):
                    names.append(item[k].strip())
                    break
    return names


def slide_and_notes_names(z):
    slides = sorted([n for n in z.namelist()
                     if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)],
                    key=lambda n: int(re.search(r"\d+", n).group()))
    notes = set(n for n in z.namelist() if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", n))
    return slides, notes


def text_of(xml_bytes):
    try:
        root = ET.fromstring(xml_bytes)
    except Exception:
        return ""
    ns = "{http://schemas.openxmlformats.org/drawingml/2006/main}t"
    return " ".join(el.text or "" for el in root.iter(ns))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate the /app/output deliverable set")
    ap.add_argument("--outdir", default="/app/output")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--state", default=None)
    ap.add_argument("--deck", default=None)
    args = ap.parse_args(argv)

    checks = []

    def check(name, ok, detail="", severity="fail"):
        checks.append({"check": name, "result": "pass" if ok else severity, "detail": detail})
        return ok

    broken = False

    # ---- result.json ---- #
    rpath = os.path.join(args.outdir, "result.json")
    result = load_json(rpath)
    if not check("result_json_parses", bool(result), rpath):
        broken = True
    cid = result.get("case_id")
    if not check("result_has_case_id", bool(cid), str(cid or "missing")):
        broken = True
    fields = contract_fields(load_json(args.case))
    missing = [f for f in fields if f not in result]
    if not check("contract_fields_present", not missing,
                 "missing: %s" % missing if missing else "%d fields present" % len(fields)):
        broken = True
    pending_fields = [f for f in fields
                      if isinstance(result.get(f), dict) and result[f].get("status") == "pending"]
    check("contract_fields_filled", not pending_fields,
          "still pending: %s" % pending_fields if pending_fields else "all filled",
          severity="warn")
    check("status_taxonomy", result.get("status") in ("success", "partial", "unable_to_determine"),
          str(result.get("status")))

    # ---- deck ---- #
    deck = args.deck or os.path.join(args.outdir, "deck.pptx")
    n_slides = 0
    if not os.path.exists(deck):
        check("deck_exists", False, deck)
        broken = True
    elif not zipfile.is_zipfile(deck):
        check("deck_is_zip", False, deck)
        broken = True
    else:
        with zipfile.ZipFile(deck) as z:
            bad = []
            for n in z.namelist():
                if n.endswith(".xml") or n.endswith(".rels"):
                    try:
                        ET.fromstring(z.read(n))
                    except Exception as e:
                        bad.append("%s: %s" % (n, e))
            if not check("deck_xml_wellformed", not bad, "; ".join(bad[:3]) or "all XML parses"):
                broken = True
            slides, notes = slide_and_notes_names(z)
            n_slides = len(slides)
            check("deck_has_slides", n_slides > 0, "%d slides" % n_slides)
            if n_slides == 0:
                broken = True
            limit = None
            if args.state and os.path.exists(args.state):
                limit = (load_json(args.state).get("constraints") or {}).get("slide_limit")
            if limit:
                if not check("slide_count_within_limit", n_slides <= int(limit),
                             "%d slides vs limit %s" % (n_slides, limit)):
                    broken = True
            no_notes = [s for s in slides
                        if "ppt/notesSlides/notesSlide%s.xml"
                        % re.search(r"\d+", s).group() not in notes]
            if not check("notes_part_per_slide", not no_notes,
                         "missing notes for: %s" % no_notes if no_notes else "all slides have notes"):
                broken = True
            stub = []
            for s in slides:
                body_txt = text_of(z.read(s))
                nn = "ppt/notesSlides/notesSlide%s.xml" % re.search(r"\d+", s).group()
                note_txt = text_of(z.read(nn)) if nn in notes else ""
                if not note_txt.strip():
                    stub.append("%s (empty notes)" % s)
                if "[pending" in body_txt or "TODO" in note_txt or "[pending" in note_txt:
                    stub.append("%s (placeholder)" % s)
            check("no_placeholder_stubs", not stub,
                  "; ".join(stub) if stub else "no [pending]/TODO stubs", severity="warn")

    # ---- previews ---- #
    mpath = os.path.join(args.outdir, "render_manifest.json")
    manifest = load_json(mpath) if os.path.exists(mpath) else None
    if manifest:
        if manifest.get("status") == "ok":
            pngs = [f for f in os.listdir(manifest.get("preview_dir", args.outdir))
                    if f.lower().endswith(".png")] \
                if os.path.isdir(manifest.get("preview_dir", "")) else []
            check("previews_match_slides", n_slides > 0 and len(pngs) >= n_slides,
                  "%d PNGs for %d slides" % (len(pngs), n_slides))
        else:
            check("render_available", False,
                  "renderer status: %s (must be disclosed in result.json uncertainty)"
                  % manifest.get("status"), severity="warn")
    else:
        check("render_stage_reached", False,
              "no render_manifest.json; run render_preview.py before delivery", severity="warn")

    state = "broken" if broken else (
        "complete" if all(c["result"] == "pass" for c in checks) else "partial")
    report = {"generated_at": utcnow(), "outdir": os.path.abspath(args.outdir),
              "deliverable_state": state, "checks": checks}
    with open(os.path.join(args.outdir, "validation_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("deliverable_state:", state)
    for c in checks:
        print("  [%s] %s — %s" % (c["result"].upper(), c["check"], c["detail"]))
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
