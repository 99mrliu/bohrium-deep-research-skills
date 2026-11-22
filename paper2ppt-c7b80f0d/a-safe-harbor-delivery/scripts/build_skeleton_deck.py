#!/usr/bin/env python3
"""build_skeleton_deck.py — end of P0: skeleton deck covering all main-line page types.

Two backends:
  * template backend (--template given AND python-pptx importable): open the
    organizer template, delete its slides, add one slide per planned page using
    the template's own layouts (masters/theme inherited). patch_slide.py cannot
    edit these decks; patch with python-pptx instead (it prints the recipe).
  * stdlib backend (default): bundled minipptx writer; fully patchable by
    patch_slide.py. If a template was requested but python-pptx is missing,
    this backend is used and the deviation is recorded in the sidecar.

Always writes a sidecar <deck>.slides.json recording backend + slide contents.

Usage:
  python3 build_skeleton_deck.py --state /app/work/session_state.json \
      --out /app/output/deck.pptx [--template /input/template.pptx] \
      [--titles-from /app/work/paper.txt]
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def first_text_line(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("[pending"):
                    return line[:200]
    except Exception:
        pass
    return None


def build_stdlib(plan, out, paper_title):
    import minipptx
    deck = minipptx.Deck()
    for p in plan:
        title = p["title"]
        bullets = list(p["bullets"])
        if p["type"] == "title" and paper_title:
            bullets[0] = paper_title
        deck.add_slide(title=title, bullets=bullets, notes=p["notes"],
                       footer="[scaffold placeholder — not yet verified against paper]")
    deck.save(out)


def build_template(plan, out, template, paper_title):
    from pptx import Presentation  # local import; only reachable when importable
    prs = Presentation(template)
    # delete all existing slides (and their parts), keep masters/layouts/theme
    sldIdLst = prs.slides._sldIdLst
    for sldId in list(sldIdLst):
        rId = sldId.rId
        sldIdLst.remove(sldId)
        try:
            prs.part.drop_rel(rId)
        except Exception:
            pass

    def find_layout(*keywords):
        for lay in prs.slide_layouts:
            name = (lay.name or "").lower()
            if any(k in name for k in keywords):
                return lay
        return None

    title_layout = find_layout("title slide") or prs.slide_layouts[0]
    body_layout = find_layout("title and content", "content", "object") \
        or (prs.slide_layouts[1] if len(prs.slide_layouts) > 1 else prs.slide_layouts[0])

    for p in plan:
        layout = title_layout if p["type"] == "title" else body_layout
        slide = prs.slides.add_slide(layout)
        bullets = list(p["bullets"])
        if p["type"] == "title" and paper_title:
            bullets[0] = paper_title
        try:
            if slide.shapes.title is not None:
                slide.shapes.title.text = p["title"]
        except Exception:
            pass
        body_ph = None
        for ph in slide.placeholders:
            if ph.placeholder_format.idx != 0 and ph.has_text_frame:
                body_ph = ph
                break
        if body_ph is not None:
            tf = body_ph.text_frame
            tf.text = bullets[0] if bullets else ""
            for b in bullets[1:]:
                tf.add_paragraph().text = b
        try:
            slide.notes_slide.notes_text_frame.text = p["notes"]
        except Exception:
            pass
    prs.save(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build skeleton deck from session state")
    ap.add_argument("--state", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--template", default=None)
    ap.add_argument("--titles-from", default=None, help="paper.txt; first line seeds title slide")
    args = ap.parse_args(argv)

    state = load_json(args.state)
    plan = state.get("slide_plan") or []
    if not plan:
        sys.stderr.write("ERROR: session_state.json has empty slide_plan; run scaffold_output.py first\n")
        return 2

    template = args.template or (state.get("constraints") or {}).get("template_path")
    paper_title = first_text_line(args.titles_from) if args.titles_from else None

    backend = "stdlib-minipptx"
    deviation = None
    if template and os.path.exists(template):
        try:
            import pptx  # noqa: F401
            build_template(plan, args.out, template, paper_title)
            backend = "template-python-pptx"
        except ImportError:
            deviation = ("python-pptx not importable; organizer template %s NOT used; "
                         "fell back to stdlib skeleton writer (masters/theme not inherited)"
                         % template)
            build_stdlib(plan, args.out, paper_title)
    else:
        if template:
            deviation = "template path %s not found on disk; stdlib skeleton used" % template
        build_stdlib(plan, args.out, paper_title)

    sidecar = {
        "deck_path": os.path.abspath(args.out),
        "state_path": os.path.abspath(args.state),
        "backend": backend,
        "deviation": deviation,
        "built_at": utcnow(),
        "slides": [{"index": p["index"], "type": p["type"], "title": p["title"],
                    "bullets": p["bullets"], "notes": p["notes"],
                    "footer": "[scaffold placeholder — not yet verified against paper]",
                    "status": "pending"} for p in plan],
    }
    sidecar_path = args.out + ".slides.json"
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(sidecar, f, ensure_ascii=False, indent=2)

    state["backend"] = backend
    state["deck_path"] = os.path.abspath(args.out)
    state["updated_at"] = utcnow()
    if deviation:
        state.setdefault("deviations", []).append(deviation)
    with open(args.state, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    print("skeleton deck built:", args.out)
    print("  backend :", backend)
    if deviation:
        print("  DEVIATION:", deviation)
    for p in plan:
        print("  slide %d [%s] %s" % (p["index"], p["type"], p["title"]))
    print("  sidecar :", sidecar_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
