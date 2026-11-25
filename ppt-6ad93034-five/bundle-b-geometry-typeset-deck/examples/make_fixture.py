#!/usr/bin/env python3
"""make_fixture.py -- build ALL synthetic inputs for the bundle example.

Creates (under examples/work/):
  input/target-template.pptx  -- a minimal but valid pptx built by IMPORTING
                                 the bundle's own deck_forge machinery, with a
                                 custom theme1.xml (title font "Georgia", body
                                 font "Helvetica", accent1 #1F4E79). This plays
                                 the role of the organizer template.
  input/case.json             -- case_id "synthetic-demo-002", output_contract
                                 with the six default fields.
  input/task.md               -- the slide work order (synthetic).
  work/plan.json              -- the agent-authored talk plan, deliberately
                                 DENSE: one slide with 12 long bullets (forces
                                 the continuation-split policy) and one slide
                                 with 45 bullets (forces the backup-overflow
                                 policy), plus a title slide and a slide with a
                                 source_line and a MISSING image (placeholder).

Everything is fictional and marked synthetic.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import deck_forge  # noqa: E402

WORK = os.path.join(HERE, "work")
INPUT = os.path.join(WORK, "input")
PLAN_DIR = os.path.join(WORK, "work")

FIXTURE_THEME = deck_forge.default_theme_xml() \
    .replace('typeface="Calibri Light"', 'typeface="Georgia"') \
    .replace('typeface="Calibri"', 'typeface="Helvetica"') \
    .replace('val="4472C4"', 'val="1F4E79"') \
    .replace('name="GeometryTypesetDefault"', 'name="FixtureConferenceTheme"') \
    .encode("utf-8")


def build_template():
    """Assemble the synthetic organizer template via deck_forge.forge()."""
    layout = {
        "meta": {"title": "Fixture Conference Template (synthetic)"},
        "slide_w_emu": 12192000, "slide_h_emu": 6858000,
        "fonts": {}, "colors": {},
        "slides": [{"id": "blank", "role": "content", "title": "",
                    "slide_no": 1, "footer": ""}],
        "actions": [], "warnings": [],
    }
    out = os.path.join(INPUT, "target-template.pptx")
    deck_forge.forge(out, layout, theme_bytes=FIXTURE_THEME)
    return out


def write_inputs():
    os.makedirs(INPUT, exist_ok=True)
    os.makedirs(PLAN_DIR, exist_ok=True)

    case = {
        "case_id": "synthetic-demo-002",
        "synthetic": True,
        "output_contract": {
            "status": "success|partial|unable_to_determine|refused",
            "editable_source": "path to editable pptx",
            "export_artifact": "path to exported pdf or null",
            "content_map": "path to layout/content map",
            "compliance_checks": "audit summary object",
            "exceptions": "list of declared limitations",
        },
    }
    with open(os.path.join(INPUT, "case.json"), "w", encoding="utf-8") as fh:
        json.dump(case, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    with open(os.path.join(INPUT, "task.md"), "w", encoding="utf-8") as fh:
        fh.write(
            "# Synthetic work order (synthetic-demo-002)\n\n"
            "Turn the fictional paper 'Adaptive Lattice Refinement for "
            "Benchmark-Free Solvers' into a 10-minute conference deck using "
            "the organizer template. Preserve template fonts/colors; no body "
            "text below 14pt; dense content must split, never shrink.\n")

    dense = ("Synthetic finding %02d: the fictional solver reduced the "
             "discretization error by 38.2%% on mesh family %s while keeping "
             "the runtime overhead below 12%% across all 240 synthetic test "
             "cases reported in the fabricated benchmark suite v0.9")
    backlog = ("Backlog item %02d: fabricated derivation step with parameter "
               "alpha=%.2f, beta=%d, showing the synthetic convergence bound "
               "holds for the invented operator family L%d under assumption "
               "A%d of the fictional framework")
    plan = {
        "meta": {
            "title": "SYNTHETIC EXAMPLE — Adaptive Lattice Refinement (fictional study)",
            "synthetic": True,
            "time_minutes": 10,
        },
        "slides": [
            {"id": "title", "role": "title",
             "title": "SYNTHETIC EXAMPLE — Adaptive Lattice Refinement for Benchmark-Free Solvers",
             "bullets": [
                 "A. Researcher, B. Author — Institute of Synthetic Studies (fictional)",
                 "GeoTypeSet Conf 2026 — synthetic demonstration deck",
             ],
             "notes": "Synthetic title slide. No real paper exists."},
            {"id": "findings", "role": "content",
             "title": "Key findings (dense slide)",
             "bullets": [dense % (i + 1, chr(ord("A") + i % 6)) for i in range(12)],
             "notes": "12 long bullets -> continuation-split policy must fire."},
            {"id": "backlog", "role": "content",
             "title": "Full derivation backlog",
             "bullets": [backlog % (i + 1, 0.1 * (i + 1), i % 7, i % 4, i % 3)
                         for i in range(45)],
             "notes": "45 bullets -> continuation budget exceeded -> backup slides."},
            {"id": "method", "role": "content",
             "title": "Method overview",
             "bullets": [
                 "Fictional three-stage pipeline: probe, adapt, certify — each stage "
                 "is fully synthetic and described only in this fixture.",
                 "The invented error estimator uses a fabricated dual-weighted "
                 "residual with synthetic calibration constants k1=0.42, k2=7.",
                 "All numbers on this slide are invented for the synthetic example.",
             ],
             "source_line": "Source: synthetic fixture plan.json — fictional citation "
                            "[1] A. Researcher et al., J. Synthetic Results 0 (2026).",
             "image": "figs/lattice_schematic.png",
             "notes": "Demonstrates source_line rendering and the missing-image "
                      "placeholder (figs/lattice_schematic.png does not exist)."},
        ],
    }
    with open(os.path.join(PLAN_DIR, "plan.json"), "w", encoding="utf-8") as fh:
        json.dump(plan, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def main():
    tpl = build_template()
    write_inputs()
    print("make_fixture: template=%s (%d bytes)" % (tpl, os.path.getsize(tpl)))
    print("make_fixture: wrote case.json, task.md, plan.json under %s" % WORK)
    return 0


if __name__ == "__main__":
    sys.exit(main())
