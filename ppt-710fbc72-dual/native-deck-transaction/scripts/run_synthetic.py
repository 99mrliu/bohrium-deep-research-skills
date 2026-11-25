#!/usr/bin/env python3
"""Run a self-contained SYNTHETIC/合成示例 adapt transaction and negative tests.

Example inputs and generated binary artifacts are written only beneath --output-root.
ReportLab is used only here to create the synthetic four-page PDF.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import fitz
from PIL import Image, ImageDraw
from pptx import Presentation
from pptx.util import Inches, Pt
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

from native_core import dump_json, load_json


def customize_template(path: Path) -> None:
    prs = Presentation()
    prs.slide_width = Inches(13.333333)
    prs.slide_height = Inches(7.5)
    prs.core_properties.title = "SYNTHETIC custom native template"
    # The stock package already has multiple native layouts. Change its theme,
    # rather than drawing a lookalike master in the generated deck.
    prs.save(path)
    temp = path.with_suffix(".tmp.pptx")
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(temp, "w") as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "ppt/theme/theme1.xml":
                text = data.decode("utf-8")
                text = re.sub(r'(<a:accent1>\s*<a:srgbClr val=")[0-9A-Fa-f]{6}("/>)', r"\g<1>7B61A8\2", text)
                data = text.encode("utf-8")
            dst.writestr(info, data)
    temp.replace(path)


def make_starting_deck(template: Path, path: Path) -> None:
    prs = Presentation(template)
    layouts = [x for master in prs.slide_masters for x in master.slide_layouts]
    content = next(x for x in layouts if x.name == "Title and Content")
    slides = [
        ("Study rationale", "This retained slide tests immutable native identity."),
        ("Preliminary finding", "Obsolete text is authorized for replacement."),
        ("Example-only appendix", "This explicitly listed example is authorized for removal."),
    ]
    for title, body in slides:
        slide = prs.slides.add_slide(content)
        slide.shapes.title.text = title
        body_ph = next(x for x in slide.placeholders if x != slide.shapes.title and x.has_text_frame)
        body_ph.text = body
        slide.notes_slide.notes_text_frame.text = "SYNTHETIC speaker notes; no real study is described."
    prs.save(path)


def make_paper(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=landscape(A4))
    width, height = landscape(A4)
    pages = [
        ("Synthetic Paper: Native Deck Transaction", [
            "A fully synthetic methods paper for source-linked slide adaptation.",
            "The study compares three simulated conditions and reports no human data.",
        ]),
        ("Figure 1. Synthetic response increases across three conditions.", [
            "The plotted values are illustrative and are not empirical observations.",
        ]),
        ("Results", [
            "Results: the response increased by 42% in the treatment group.",
            "The median latency was 18 seconds in the synthetic cohort.",
        ]),
        ("Conclusion", [
            "Conclusion: the synthetic intervention improved response under the tested conditions.",
            "These statements exist only to exercise quotation and rendering checks.",
        ]),
    ]
    for page_no, (heading, lines) in enumerate(pages, 1):
        c.setFillColor(HexColor("#30284C"))
        c.setFont("Helvetica-Bold", 20)
        c.drawString(48, height - 54, heading)
        c.setFillColor(HexColor("#222222"))
        c.setFont("Helvetica", 13)
        y = height - 100
        for line in lines:
            c.drawString(48, y, line)
            y -= 28
        if page_no == 2:
            origin_x, origin_y = 100, 130
            c.setStrokeColor(HexColor("#DDDAE8"))
            c.rect(origin_x, origin_y, 500, 250, stroke=1, fill=0)
            for i, value in enumerate((95, 155, 220)):
                c.setFillColor(HexColor("#7B61A8"))
                c.rect(origin_x + 60 + i * 145, origin_y, 70, value, stroke=0, fill=1)
                c.setFillColor(HexColor("#222222"))
                c.drawCentredString(origin_x + 95 + i * 145, origin_y - 20, ("Control", "Adapt", "Treat")[i])
        c.setFont("Helvetica", 9)
        c.drawRightString(width - 40, 30, f"SYNTHETIC page {page_no} of 4")
        c.showPage()
    c.save()


def evidence(sources: dict, page: int, needle: str, **extra) -> dict:
    doc = sources["documents"][0]
    page_rec = next(p for p in doc["pages"] if p["page"] == page)
    line = next(x for x in page_rec["lines"] if needle in x["text"])
    result = {
        "source_id": doc["source_id"], "page": page,
        "quote_id": line["quote_id"], "quote": line["text"],
    }
    result.update(extra)
    return result


def write_case(root: Path) -> tuple[Path, dict]:
    input_dir = root / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    template = input_dir / "template.pptx"
    starting = input_dir / "starting.pptx"
    paper = input_dir / "paper.pdf"
    customize_template(template)
    make_starting_deck(template, starting)
    make_paper(paper)
    case = {
        "case_id": "SYNTHETIC-native-adapt-001",
        "mode": "adapt",
        "constraints": {"slide_count": 5, "minutes": 7, "audience": "Synthetic reviewers"},
        "materials": [
            {"path": "starting.pptx", "role": "starting_deck"},
            {"path": "template.pptx", "role": "template"},
            {"path": "paper.pdf", "role": "paper"},
        ],
        "output_contract": {"fields": {
            "presentation": {"type": "string"}, "pdf": {"type": "string"},
            "previews": {"type": "array"}, "slide_count": {"type": "integer"},
            "sources": {"type": "array"}, "editable_source": {"type": "string"},
            "export_artifact": {"type": "string"}, "content_map": {"type": "string"},
            "compliance_checks": {"type": "object"}, "exceptions": {"type": "array"},
        }},
    }
    dump_json(input_dir / "case.json", case)
    (input_dir / "task.md").write_text(
        "# SYNTHETIC / 合成示例\n\nAdapt the immutable starting deck to exactly 5 slides for 7 minutes.\n"
        "Audience: Synthetic reviewers. Keep the study rationale, revise the preliminary finding, "
        "remove only the example appendix, and add source-linked results. All claims are fictional.\n",
        encoding="utf-8",
    )
    return input_dir, case


def run(script: Path, command: str, input_dir: Path, work: Path, output: Path, expect: int = 0) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        [sys.executable, str(script), command, "--input", str(input_dir), "--work", str(work), "--output", str(output)],
        capture_output=True, text=True, timeout=300,
    )
    print(f"\n$ {command} {work.name} -> {output.name}\n{proc.stdout}{proc.stderr}")
    if proc.returncode != expect:
        raise AssertionError(f"{command} returned {proc.returncode}, expected {expect}")
    return proc


def valid_plan(inventory: dict, sources: dict) -> dict:
    ids = inventory["base_slide_ids"]
    layout_idx = next(x["idx"] for x in inventory["base"]["layouts"] if x["name"] == "Title and Content")
    return {
        "schema_version": "1.0", "mode": "adapt", "base_path": inventory["base_path"], "base_slide_ids": ids,
        "meta": {
            "title": "SYNTHETIC native transaction", "audience": "Synthetic reviewers", "minutes": 7,
            "slide_count": 5, "minimum_explicit_font_pt": 12,
            "visual_review": {"status": "automated", "pages": [1, 2, 3, 4, 5], "corrections": []},
        },
        "operations": [
            {"op": "keep", "id": ids[0]},
            {
                "op": "edit", "id": ids[1], "source_slide_id": ids[1],
                "title": "Response increased by 42%",
                "bullets": ["The treatment group showed a 42% response increase."],
                # Omitted notes are inherited; evidence is appended without erasing them.
                "evidence": [evidence(sources, 3, "response increased by 42%", section="Results")],
            },
            {"op": "remove", "id": ids[2]},
            {
                "op": "append", "id": "new-figure", "layout_idx": layout_idx,
                "title": "Figure 1: synthetic response", "bullets": [],
                "figures": [{"source_id": "pdf-0001", "page": 2, "figure": "Figure 1"}],
                "notes": "Explain that the figure is a rendered source-page excerpt, not new evidence.",
                "evidence": [evidence(sources, 2, "Figure 1.", figure="Figure 1")],
            },
            {
                "op": "append", "id": "new-latency", "layout_idx": layout_idx,
                "title": "Median latency was 18 seconds",
                "bullets": ["The synthetic cohort had a median latency of 18 seconds."],
                "notes": "Pause before the final takeaway.",
                "evidence": [evidence(sources, 3, "median latency was 18 seconds", section="Results")],
            },
            {
                "op": "append", "id": "new-takeaway", "layout_idx": layout_idx,
                "title": "Study takeaway",
                "bullets": ["The synthetic intervention improved response under the tested conditions."],
                "notes": "Close within the seven-minute synthetic presentation.",
                "evidence": [evidence(sources, 4, "Conclusion:", section="Conclusion")],
            },
            {"op": "reorder", "final_order": [ids[0], ids[1], "new-figure", "new-latency", "new-takeaway"]},
        ],
    }


def verify(output: Path) -> dict:
    result = load_json(output / "result.json")
    diff = load_json(output / "native_diff.json")
    qa = load_json(output / "render_report.json")
    assert result["status"] == "success", result
    assert result["case_id"] == "SYNTHETIC-native-adapt-001"
    for field in ("presentation", "pdf", "previews", "slide_count", "sources", "editable_source",
                  "export_artifact", "content_map", "compliance_checks", "exceptions"):
        assert field in result and result[field] is not None, field
    assert result["editable_source"] == str(output / "presentation.pptx")
    assert result["export_artifact"] == str(output / "presentation.pdf")
    assert "type" not in result and "description" not in result
    assert diff["passed"] and diff["theme_untouched"] and diff["dimensions_same"]
    deck = Presentation(str(output / "presentation.pptx"))
    edited_notes = deck.slides[1].notes_slide.notes_text_frame.text
    assert "SYNTHETIC speaker notes" in edited_notes and "42%" in edited_notes
    assert len(diff["kept_slides"]) == 1 and diff["kept_slides"][0]["byte_identical_slide_and_relationships"]
    assert qa["passed"] and qa["pdf_page_count"] == 5 and len(qa["preview_paths"]) == 5
    assert not qa["lost_or_clipped_text"]
    with fitz.open(output / "presentation.pdf") as doc:
        text = [p.get_text() for p in doc]
        dims = [(round(p.rect.width, 2), round(p.rect.height, 2)) for p in doc]
    assert "42%" in "".join(text) and "18 seconds" in "".join(text)
    png_dims = []
    for path in sorted((output / "previews").glob("preview-*.png")):
        with Image.open(path) as im:
            png_dims.append(im.size)
            assert im.width > 500 and im.height > 250
    return {
        "status": result["status"], "pptx": str(output / "presentation.pptx"),
        "pdf_pages": qa["pdf_page_count"], "pdf_dimensions_pt": dims,
        "png_dimensions_px": png_dims, "kept_slide_byte_identity": True,
        "lost_or_clipped_text": qa["lost_or_clipped_text"],
    }


def negatives(script: Path, input_dir: Path, root: Path, plan: dict) -> dict:
    work = root / "negative-work"
    output = root / "negative-output"
    run(script, "prepare", input_dir, work, output)
    missing = copy.deepcopy(plan)
    missing["operations"] = [op for op in missing["operations"] if not (op.get("op") == "edit" and op.get("id") == plan["base_slide_ids"][1])]
    missing["operations"][-1]["final_order"].remove(plan["base_slide_ids"][1])
    dump_json(work / "transaction_plan.json", missing)
    first = run(script, "finish", input_dir, work, output, expect=2)
    first_result = load_json(output / "result.json")
    assert first_result["status"] == "failed"
    assert any("missing original slide accounting" in x for x in first_result["uncertainty"])

    dangling = copy.deepcopy(plan)
    next(op for op in dangling["operations"] if op.get("id") == "new-figure")["layout_idx"] = 9999
    dump_json(work / "transaction_plan.json", dangling)
    second = run(script, "finish", input_dir, work, output, expect=2)
    second_result = load_json(output / "result.json")
    assert second_result["status"] == "failed"
    assert any("dangling layout_idx" in x for x in second_result["uncertainty"])
    return {"missing_original_rejected": True, "dangling_layout_rejected": True}


def main() -> int:
    p = argparse.ArgumentParser(description="Generate and execute the SYNTHETIC/合成示例")
    p.add_argument("--output-root", required=True, type=Path, help="External writable example-run directory")
    args = p.parse_args()
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    script = Path(__file__).with_name("run_case.py")
    input_dir, _ = write_case(root)
    work, output = root / "work", root / "output"
    run(script, "prepare", input_dir, work, output)
    inventory, sources = load_json(work / "native_inventory.json"), load_json(work / "source_index.json")
    plan = valid_plan(inventory, sources)
    dump_json(work / "transaction_plan.json", plan)
    run(script, "finish", input_dir, work, output)
    summary = verify(output)
    summary["negative_tests"] = negatives(script, input_dir, root, plan)
    dump_json(root / "synthetic_test_summary.json", summary)
    print("\nSYNTHETIC TEST SUMMARY\n" + json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
