#!/usr/bin/env python3
"""refit_apply.py — apply edit ops to a deck model and write the new pptx.

Ops JSON: a list of ops, or an object {"ops": [...], "target_slides": n}.
Every op MUST carry a non-empty "reason" — the consent form.  Nothing
changes without an op + reason.

Op indices ("slide", "from", "to", "after", "donor") are 0-based positions
in the CURRENT deck state at the moment the op is applied; ops apply in
list order.

Supported ops:
  {"op":"rewrite_paras","slide":i,"paras":[{"pid","text"}],"reason":...}
  {"op":"set_notes","slide":i,"text":"...","reason":...}
  {"op":"delete_slide","slide":i,"reason":...,"dropped_numbers":[...],
   "dropped_terms":[...]}
  {"op":"move_slide","from":i,"to":j,"reason":...}
  {"op":"add_slide","after":i,"donor":k,"paras":[{"pid","text"},...],
   "reason":...,"introduced_numbers":[...]}

Optional honesty declarations on any op: "introduced_numbers" (new numbers
with justification) and "dropped_numbers" / "dropped_terms".

Usage:
  refit_apply.py --model work/model.json --ops work/refit_ops.json \
      --src /input/starting-deck.pptx --out /app/output/presentation.pptx
"""

import argparse
import copy
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deck_io  # noqa: E402

VALID_OPS = {"rewrite_paras", "set_notes", "delete_slide",
             "move_slide", "add_slide"}


def _fail(msg):
    raise SystemExit("refit_apply: " + msg)


def load_ops(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("ops", []), data.get("target_slides")
    return data, None


def apply_ops(model, ops):
    """Return (new_model, change_record). Does NOT write files."""
    slides = copy.deepcopy(model["slides"])
    record = []

    def slide_at(i, opname):
        if not (0 <= i < len(slides)):
            _fail("op %r: slide index %d out of range (%d slides)"
                  % (opname, i, len(slides)))
        return slides[i]

    for n, op in enumerate(ops):
        kind = op.get("op")
        if kind not in VALID_OPS:
            _fail("op #%d: unknown op %r" % (n, kind))
        if not str(op.get("reason", "")).strip():
            _fail("op #%d (%s): missing 'reason' — every change needs "
                  "the consent form" % (n, kind))
        entry = {"seq": n, "op": kind, "reason": op["reason"],
                 "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

        if kind == "rewrite_paras":
            s = slide_at(op["slide"], kind)
            by_pid = {p["pid"]: p for p in s["paras"]}
            for para in op.get("paras", []):
                pid = para.get("pid")
                if pid not in by_pid:
                    _fail("op #%d: pid %s not on slide %d (%s)"
                          % (n, pid, op["slide"], s["part"]))
                by_pid[pid]["text"] = para["text"]
            entry["slide"] = op["slide"]
            entry["part"] = s["part"]
            entry["pids"] = [p["pid"] for p in op.get("paras", [])]

        elif kind == "set_notes":
            s = slide_at(op["slide"], kind)
            notes = [p for p in s["paras"] if p["role"] == "notes"]
            if not notes:
                _fail("op #%d: slide %d has no notes part to edit; pick a "
                      "slide that has speaker notes" % (n, op["slide"]))
            notes[0]["text"] = op["text"]
            for extra in notes[1:]:
                extra["text"] = ""
            entry["slide"] = op["slide"]
            entry["part"] = s["part"]

        elif kind == "delete_slide":
            s = slide_at(op["slide"], kind)
            entry["slide"] = op["slide"]
            entry["part"] = s["part"]
            slides.pop(op["slide"])

        elif kind == "move_slide":
            s = slide_at(op["from"], kind)
            slide_at(op["to"], kind)
            moved = slides.pop(op["from"])
            slides.insert(op["to"], moved)
            entry["from"], entry["to"] = op["from"], op["to"]
            entry["part"] = s["part"]

        elif kind == "add_slide":
            donor = slide_at(op["donor"], kind)
            base = slide_at(op["after"], kind) if op["after"] >= 0 else None
            new_slide = copy.deepcopy(donor)
            new_slide["new"] = True
            new_slide["donor_part"] = donor["part"]
            new_slide["part"] = None
            new_slide["notes_part"] = None
            by_pid = {p["pid"]: p for p in new_slide["paras"]}
            for para in op.get("paras", []):
                pid = para.get("pid")
                if pid not in by_pid:
                    _fail("op #%d: pid %s not in donor slide %d"
                          % (n, pid, op["donor"]))
                by_pid[pid]["text"] = para["text"]
            pos = slides.index(base) + 1 if base is not None else 0
            slides.insert(pos, new_slide)
            entry["after"], entry["donor"] = op["after"], op["donor"]
            entry["donor_part"] = donor["part"]

        for extra in ("introduced_numbers", "dropped_numbers", "dropped_terms"):
            if op.get(extra):
                entry[extra] = op[extra]
        record.append(entry)

    new_model = copy.deepcopy(model)
    new_model["slides"] = slides
    for i, s in enumerate(new_model["slides"]):
        s["index"] = i
    return new_model, record


def main(argv=None):
    ap = argparse.ArgumentParser(description="apply refit ops to a pptx")
    ap.add_argument("--model", required=True)
    ap.add_argument("--ops", required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--change-record", default=None,
                    help="default: $CASE_WORK_DIR/change_record.json")
    args = ap.parse_args(argv)

    with open(args.model, encoding="utf-8") as f:
        model = json.load(f)
    ops, _target = load_ops(args.ops)

    new_model, record = apply_ops(model, ops)
    deck_io.write_deck(new_model, args.src, args.out)

    cr_path = args.change_record or os.path.join(
        os.environ.get("CASE_WORK_DIR", "work"), "change_record.json")
    os.makedirs(os.path.dirname(cr_path) or ".", exist_ok=True)
    with open(cr_path, "w", encoding="utf-8") as f:
        json.dump({"applied": len(record), "ops": record}, f, ensure_ascii=False,
                  indent=1)

    print("applied %d ops -> %s (%d slides); change record: %s"
          % (len(record), args.out, len(new_model["slides"]), cr_path))


if __name__ == "__main__":
    main()
