#!/usr/bin/env python3
"""Noninteractive end-to-end synthetic example with a meaningful negative test."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import fitz
from PIL import Image
from pptx import Presentation

from make_synthetic import generate


def run(command: list[str], bundle: Path, expected: int | None = None) -> subprocess.CompletedProcess:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(command, cwd=bundle, env=environment, text=True, capture_output=True, check=False)
    print("+", " ".join(command))
    print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    if expected is not None and completed.returncode != expected:
        raise AssertionError(f"Command returned {completed.returncode}, expected {expected}: {command}")
    return completed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, type=Path,
                        help="Generated files directory; must be outside the Skill bundle")
    args = parser.parse_args()
    root = args.output_root.resolve()
    bundle = Path(__file__).resolve().parents[1]
    if bundle == root or bundle in root.parents:
        raise ValueError("Generated artifacts must stay outside the bundle.")
    root.mkdir(parents=True, exist_ok=True)
    input_dir = generate(root)
    work, output, negative_output = root / "work", root / "output", root / "negative-output"
    for directory in (work, output, negative_output):
        if directory.exists():
            shutil.rmtree(directory)
    runner = str(bundle / "scripts" / "run_case.py")
    run([sys.executable, runner, "prepare", "--input", str(input_dir), "--work", str(work), "--output", str(output)], bundle, 0)
    ledger = json.loads((work / "source_ledger.json").read_text(encoding="utf-8"))
    assets = json.loads((work / "asset_candidates.json").read_text(encoding="utf-8"))["assets"]
    skeleton = json.loads((work / "deck_plan.skeleton.json").read_text(encoding="utf-8"))
    evidence: list[dict] = []

    def anchor(quote: str) -> str:
        matches = [span for span in ledger["spans"] if quote in span["text"]]
        if len(matches) != 1:
            raise AssertionError(f"Expected one actual extracted span containing {quote!r}; got {len(matches)}")
        evidence_id = f"E{len(evidence) + 1:02d}"
        evidence.append({"id": evidence_id, "span_id": matches[0]["span_id"], "quote": quote,
                         "qualifier": "Synthetic and illustrative only; preserve the source context."})
        return evidence_id

    task = anchor("Format: 6 slides; 8 minutes; audience: methods reviewers.")
    cohort = anchor("The simulated cohort contained 24 participants.")
    response = anchor("The simulated mean response increased by 18% from baseline.")
    difference = anchor("Condition B was 12 points higher than Condition A in this synthetic run.")
    exploratory = anchor("The estimate is exploratory and does not establish causality.")
    figure_caption = anchor("Figure 1. Simulated response by condition (illustrative units).")
    table_caption = anchor("Table 1. Synthetic condition summary; no external observations.")
    limitations = anchor("No external validation was performed; results are illustrative.")
    no_causal = anchor("The study does not support clinical or causal claims.")
    conclusion = anchor("The 12-point difference is descriptive and hypothesis-generating only.")
    validity = anchor("External validity remains untested in this synthetic example.")
    figure_asset = next(item for item in assets if item["caption"].startswith("Figure 1."))
    table_asset = next(item for item in assets if item["caption"].startswith("Table 1."))
    assert table_asset["bbox"][2] >= 480, "Table candidate must include the rightmost Response column"

    def slide(slide_id: str, kind: str, title: str, takeaway: str, bullets: list,
              eids: list[str], notes: str, figures: list | None = None) -> dict:
        return {"id": slide_id, "kind": kind, "title": title, "takeaway": takeaway,
                "bullets": bullets, "notes": notes, "evidence": eids, "figures": figures or []}

    slides = [
        slide("s1", "title", "Synthetic response study",
              "An 8-minute briefing for methods reviewers using a simulated 24-participant cohort.", [],
              [task, cohort], "Open by stating that all data are synthetic and illustrative."),
        slide("s2", "content", "Design and scope", "The estimate is exploratory, not causal.",
              [{"text": "The simulated cohort contained 24 participants.", "evidence": [cohort]},
               {"text": "The simulated mean response increased by 18% from baseline.", "evidence": [response]},
               {"text": "The estimate is exploratory and does not establish causality.", "evidence": [exploratory]}],
              [cohort, response, exploratory], "Keep the exploratory qualifier beside the estimate."),
        slide("s3", "figure", "Observed response profile",
              "Condition B was 12 points higher in this synthetic run (Figure 1).", [],
              [difference, figure_caption], "Describe the displayed comparison; do not relabel it as an external result.",
              [{"asset_id": figure_asset["asset_id"], "evidence": [figure_caption, difference]}]),
        slide("s4", "table", "Summary table",
              "Table 1 summarizes the two simulated conditions without external observations.",
              [{"text": "The simulated cohort contained 24 participants.", "evidence": [cohort]}],
              [table_caption, cohort], "Read the source caption verbatim; counts are simulated allocations.",
              [{"asset_id": table_asset["asset_id"], "evidence": [table_caption]}]),
        slide("s5", "content", "Limitations and interpretation", "The qualifiers constrain every claim.",
              [{"text": "No external validation was performed; results are illustrative.", "evidence": [limitations]},
               {"text": "The study does not support clinical or causal claims.", "evidence": [no_causal]}],
              [limitations, no_causal], "Do not generalize beyond this explicitly synthetic example."),
        slide("s6", "closing", "Conclusion",
              "The 12-point difference is descriptive and hypothesis-generating only.",
              [{"text": "External validity remains untested in this synthetic example.", "evidence": [validity]},
               {"text": "Requested format: 6 slides, 8 minutes, methods reviewers.", "evidence": [task]}],
              [conclusion, validity, task], "Close with the limitation, then confirm the requested format."),
    ]
    plan = {"schema_version": "1.0", "case_id": skeleton["case_id"],
            "task_parameters": skeleton["task_parameters"], "template_path": skeleton["template_path"],
            "evidence": evidence, "slides": slides}
    plan_path = work / "deck_plan.json"
    original_plan = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
    plan_path.write_text(original_plan, encoding="utf-8")
    run([sys.executable, runner, "finish", "--work", str(work), "--output", str(output)], bundle, 0)

    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert result["case_id"] == "SYNTHETIC-evidence-span-001" and result["status"] == "success"
    for field in ("editable_source", "export_artifact", "content_map", "compliance_checks", "exceptions"):
        assert field in result, f"Missing original contract field: {field}"
    assert "type" not in result and "description" not in result
    assert result["editable_source"] == str(output / "presentation.pptx")
    assert result["export_artifact"] == str(output / "presentation.pdf")
    assert result["content_map"] == str(output / "evidence_map.json")
    deck = Presentation(output / "presentation.pptx")
    assert len(deck.slides) == 6
    assert all("Evidence anchors:" in slide.notes_slide.notes_text_frame.text for slide in deck.slides)
    assert all("PRE-EXISTING" not in shape.text for slide in deck.slides for shape in slide.shapes if hasattr(shape, "text"))
    png_dimensions = []
    with fitz.open(output / "presentation.pdf") as rendered:
        assert rendered.page_count == 6
        rendered_text = [page.get_text("text") for page in rendered]
        for expected in ("Synthetic response study", "Design and scope", "Observed response profile",
                         "Summary table", "Limitations and interpretation", "Conclusion"):
            assert any(expected in text for text in rendered_text), f"Rendered title missing: {expected}"
        assert "Figure 1." in rendered_text[2] and "Table 1." in rendered_text[3]
    for index in range(1, 7):
        path = output / "previews" / f"slide-{index:02d}.png"
        with Image.open(path) as image:
            assert image.width >= 1000 and image.height >= 500
            assert image.convert("L").getextrema()[0] < 240, f"Blank-looking preview: {path}"
            png_dimensions.append({"file": str(path), "width": image.width, "height": image.height})

    # Adapt regression: the same real two-slide base is edited in native layouts,
    # with four appended evidence-linked slides and no implicit deletion.
    adapt_input = root / "adapt-input"
    if adapt_input.exists():
        shutil.rmtree(adapt_input)
    shutil.copytree(input_dir, adapt_input)
    adapt_case_path = adapt_input / "case.json"
    adapt_case = json.loads(adapt_case_path.read_text(encoding="utf-8"))
    adapt_case["mode"] = "adapt"
    adapt_case_path.write_text(json.dumps(adapt_case, indent=2) + "\n", encoding="utf-8")
    adapt_work, adapt_output = root / "adapt-work", root / "adapt-output"
    for directory in (adapt_work, adapt_output):
        if directory.exists():
            shutil.rmtree(directory)
    run([sys.executable, runner, "prepare", "--input", str(adapt_input),
         "--work", str(adapt_work), "--output", str(adapt_output)], bundle, 0)
    adapt_plan = json.loads(original_plan)
    adapt_plan["mode"] = "adapt"
    adapt_plan["template_path"] = str(adapt_input / "template.pptx")
    adapt_plan["slides"][0]["source_slide_id"] = "original-0001"
    adapt_plan["slides"][1]["source_slide_id"] = "original-0002"
    (adapt_work / "deck_plan.json").write_text(json.dumps(adapt_plan, ensure_ascii=False, indent=2) + "\n",
                                                encoding="utf-8")
    run([sys.executable, runner, "finish", "--work", str(adapt_work),
         "--output", str(adapt_output)], bundle, 0)
    adapt_result = json.loads((adapt_output / "result.json").read_text(encoding="utf-8"))
    adapt_build = json.loads((adapt_output / "build_report.json").read_text(encoding="utf-8"))
    assert adapt_result["status"] == "success" and len(Presentation(adapt_output / "presentation.pptx").slides) == 6
    assert adapt_build["mode"] == "adapt" and adapt_build["removed_template_slide_count"] == 0
    assert adapt_build["slides"][0]["source_slide_id"] == "original-0001"
    assert adapt_build["slides"][1]["source_slide_id"] == "original-0002"
    with fitz.open(adapt_output / "presentation.pdf") as adapted_pdf:
        assert adapted_pdf.page_count == 6

    negative = json.loads(original_plan)
    negative["evidence"][0]["quote"] = "This unsupported quote is deliberately absent from the task."
    plan_path.write_text(json.dumps(negative, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        rejected = run([sys.executable, runner, "finish", "--work", str(work), "--output", str(negative_output)], bundle)
        assert rejected.returncode != 0, "Unsupported quote was not rejected"
        negative_report = json.loads((negative_output / "evidence_report.json").read_text(encoding="utf-8"))
        assert any(error["code"] == "quote_mismatch" for error in negative_report["errors"])
        negative_result = json.loads((negative_output / "result.json").read_text(encoding="utf-8"))
        assert negative_result["status"] == "failed"
    finally:
        plan_path.write_text(original_plan, encoding="utf-8")
    verification = {"status": "success", "positive": {"result": str(output / "result.json"),
                    "pptx": str(output / "presentation.pptx"), "pdf": str(output / "presentation.pdf"),
                    "png_dimensions": png_dimensions},
                    "adapt": {"result": str(adapt_output / "result.json"),
                              "pptx": str(adapt_output / "presentation.pptx"),
                              "pdf": str(adapt_output / "presentation.pdf"),
                              "edited_original_slides": 2, "appended_slides": 4},
                    "negative": {"returncode": rejected.returncode, "rejected_error": "quote_mismatch",
                                 "result": str(negative_output / "result.json")}}
    (root / "verification.json").write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(verification, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
