#!/usr/bin/env python3
"""patch_slide.py — P2: upgrade ONE slide, leaving the whole deliverable set valid.

Stdlib backend decks (built by minipptx): regenerates that slide's XML inside
the zip, re-validates the package, updates the sidecar and session_state.

Template-backend decks (python-pptx): this script REFUSES (exit 3) and prints
the exact python-pptx snippet the agent must run instead.

Usage:
  python3 patch_slide.py --deck /app/output/deck.pptx --slide 2 \
      [--title "..."] [--bullets-file bullets.txt] [--notes-file notes.txt] \
      [--footer "Source: §3.2, Table 1"]
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        return [ln.rstrip("\n") for ln in f]


def read_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


PY_PPTX_RECIPE = """\
This deck was built with the template backend (python-pptx). Patch it with
python-pptx directly, e.g.:

    python3 - <<'EOF'
    from pptx import Presentation
    prs = Presentation("{deck}")
    slide = prs.slides[{idx0}]          # slide {n}, 0-based
    slide.shapes.title.text = "..."
    body = None
    for ph in slide.placeholders:
        if ph.placeholder_format.idx != 0 and ph.has_text_frame:
            body = ph.text_frame; break
    if body is not None:
        body.clear()
        body.paragraphs[0].text = "bullet 1"
        for b in ["bullet 2", "bullet 3"]:
            body.add_paragraph().text = b
    slide.notes_slide.notes_text_frame.text = "..."
    prs.save("{deck}")
    EOF

Then run validate_output.py to confirm the set is still valid.
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description="Patch one slide of the deck")
    ap.add_argument("--deck", required=True)
    ap.add_argument("--slide", type=int, required=True, help="1-based slide number")
    ap.add_argument("--title", default=None)
    ap.add_argument("--bullets-file", default=None, help="one bullet per line; '- ' prefixes stripped")
    ap.add_argument("--notes-file", default=None)
    ap.add_argument("--footer", default=None)
    ap.add_argument("--mark", default="done", choices=["done", "pending"])
    args = ap.parse_args(argv)

    sidecar_path = args.deck + ".slides.json"
    if not os.path.exists(sidecar_path):
        sys.stderr.write("ERROR: sidecar %s missing; cannot patch safely.\n" % sidecar_path)
        return 2
    with open(sidecar_path, "r", encoding="utf-8") as f:
        sidecar = json.load(f)

    if sidecar.get("backend") != "stdlib-minipptx":
        sys.stderr.write("REFUSING to patch: backend=%s\n\n" % sidecar.get("backend"))
        sys.stderr.write(PY_PPTX_RECIPE.format(deck=os.path.abspath(args.deck),
                                               idx0=args.slide - 1, n=args.slide))
        return 3

    slides = sidecar["slides"]
    if not (1 <= args.slide <= len(slides)):
        sys.stderr.write("ERROR: slide %d out of range 1..%d\n" % (args.slide, len(slides)))
        return 2
    s = slides[args.slide - 1]

    if args.title is not None:
        s["title"] = args.title
    if args.bullets_file:
        s["bullets"] = [ln[2:] if ln.startswith("- ") else ln
                        for ln in read_lines(args.bullets_file) if ln.strip()]
    if args.notes_file:
        s["notes"] = read_text(args.notes_file)
    if args.footer is not None:
        s["footer"] = args.footer
    s["status"] = args.mark
    s["patched_at"] = utcnow()

    import minipptx
    try:
        minipptx.patch_slide_parts(args.deck, args.slide, s)
    except Exception as e:
        sys.stderr.write("ERROR: patch failed: %s\n" % e)
        return 1
    errors = minipptx.validate_package(args.deck)
    if errors:
        sys.stderr.write("ERROR: package invalid after patch: %s\n" % "; ".join(errors))
        return 1

    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(sidecar, f, ensure_ascii=False, indent=2)

    state_path = sidecar.get("state_path")
    if state_path and os.path.exists(state_path):
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        for p in state.get("slide_plan", []):
            if p.get("index") == args.slide:
                p["status"] = args.mark
                p["title"] = s["title"]
                p["bullets"] = s["bullets"]
                p["notes"] = s["notes"]
        state["updated_at"] = utcnow()
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    done = sum(1 for x in slides if x.get("status") == "done")
    print("patched slide %d/%d OK (%d done, %d pending)"
          % (args.slide, len(slides), done, len(slides) - done))
    return 0


if __name__ == "__main__":
    sys.exit(main())
