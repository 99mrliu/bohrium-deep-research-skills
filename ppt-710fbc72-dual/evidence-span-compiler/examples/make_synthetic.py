#!/usr/bin/env python3
"""Generate an explicitly synthetic source PDF and a real multi-layout PPTX template."""
from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from pptx import Presentation
from pptx.util import Inches
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def make_pdf(path: Path) -> None:
    pdf = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter

    def header(page: int, title: str) -> None:
        pdf.setFillColor(HexColor("#173F5F"))
        pdf.setFont("Helvetica-Bold", 17)
        pdf.drawString(58, 738, title)
        pdf.setFillColor(HexColor("#A00"))
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawRightString(554, 758, "SYNTHETIC / ILLUSTRATIVE ONLY")
        pdf.setFillColor(HexColor("#333333"))
        pdf.setFont("Helvetica", 9)
        pdf.drawRightString(554, 34, f"Synthetic study | page {page} of 6")

    def lines(items: list[str], start: float = 680, gap: float = 28, size: int = 12) -> None:
        pdf.setFillColor(HexColor("#222222"))
        pdf.setFont("Helvetica", size)
        for index, text in enumerate(items):
            pdf.drawString(62, start - index * gap, text)

    header(1, "Synthetic response study")
    lines([
        "This document is an explicitly synthetic research example.",
        "All observations were generated for software verification only.",
        "The study compares two simulated conditions, A and B.",
        "The simulated cohort contained 24 participants.",
        "No external observations or human-subject data were used.",
        "The objective is to demonstrate traceable presentation evidence.",
    ])
    pdf.showPage()

    header(2, "Methods and estimate")
    lines([
        "Condition A and Condition B were evaluated in a controlled simulation.",
        "The simulated mean response increased by 18% from baseline.",
        "Condition B was 12 points higher than Condition A in this synthetic run.",
        "The estimate is exploratory and does not establish causality.",
        "No confidence interval was estimated in this minimal example.",
        "All values are illustrative and must not guide clinical decisions.",
    ])
    pdf.showPage()

    header(3, "Vector chart")
    pdf.setStrokeColor(HexColor("#555555"))
    pdf.setFillColor(HexColor("#FFFFFF"))
    pdf.rect(90, 350, 420, 230, fill=1, stroke=1)
    pdf.setFont("Helvetica", 10)
    pdf.setFillColor(HexColor("#222222"))
    pdf.drawString(96, 590, "Simulated response (illustrative units)")
    for x, value, color, label in [(180, 42, "#20639B", "Condition A"), (350, 54, "#3CAEA3", "Condition B")]:
        bar_height = value * 3
        pdf.setFillColor(HexColor(color))
        pdf.rect(x, 390, 80, bar_height, fill=1, stroke=0)
        pdf.setFillColor(HexColor("#222222"))
        pdf.drawCentredString(x + 40, 375, label)
        pdf.drawCentredString(x + 40, 396 + bar_height, str(value))
    pdf.setStrokeColor(HexColor("#333333"))
    pdf.line(120, 390, 490, 390)
    pdf.setFont("Helvetica", 11)
    pdf.drawString(90, 320, "Figure 1. Simulated response by condition (illustrative units).")
    lines(["The vector chart is a visual restatement of the synthetic values."], start=275)
    pdf.showPage()

    header(4, "Tabulated summary")
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(100, 620, "Condition")
    pdf.drawString(300, 620, "Participants")
    pdf.drawString(440, 620, "Response")
    rows = [("A", "12", "42"), ("B", "12", "54")]
    pdf.setFont("Helvetica", 11)
    for index, row in enumerate(rows):
        y = 580 - index * 42
        pdf.drawString(100, y, row[0])
        pdf.drawString(300, y, row[1])
        pdf.drawString(440, y, row[2])
        pdf.setStrokeColor(HexColor("#AAAAAA"))
        pdf.line(90, y - 12, 510, y - 12)
    pdf.setFont("Helvetica", 11)
    pdf.drawString(90, 455, "Table 1. Synthetic condition summary; no external observations.")
    lines(["Counts are simulated allocations and are not recruitment claims."], start=410)
    pdf.showPage()

    header(5, "Limitations")
    lines([
        "Only two simulated conditions were compared.",
        "No external validation was performed; results are illustrative.",
        "The study does not support clinical or causal claims.",
        "The example omits sampling variability and uncertainty intervals.",
        "Qualifiers must remain attached to every presentation claim.",
    ])
    pdf.showPage()

    header(6, "Conclusion")
    lines([
        "The 12-point difference is descriptive and hypothesis-generating only.",
        "External validity remains untested in this synthetic example.",
        "Future evaluation would require independently observed data.",
        "This synthetic document supports software testing, not scientific inference.",
    ])
    pdf.save()


def make_template(path: Path) -> None:
    presentation = Presentation()
    presentation.slide_width = Inches(13.333333)
    presentation.slide_height = Inches(7.5)
    title = presentation.slides.add_slide(presentation.slide_layouts[0])
    title.shapes.title.text = "PRE-EXISTING TEMPLATE SLIDE — REMOVE DURING GENERATION"
    content = presentation.slides.add_slide(presentation.slide_layouts[1])
    content.shapes.title.text = "Template inventory example"
    content.placeholders[1].text = "This old slide must not appear in the generated deck."
    presentation.save(path)
    # Change theme colors in the real package while retaining all native layouts/masters.
    temporary = path.with_suffix(".theme.tmp")
    namespace = "http://schemas.openxmlformats.org/drawingml/2006/main"
    replacements = {"accent1": "173F5F", "accent2": "20639B", "accent3": "3CAEA3", "accent4": "F6D55C"}
    with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "ppt/theme/theme1.xml":
                root = ElementTree.fromstring(data)
                for element in root.iter():
                    local = element.tag.rsplit("}", 1)[-1]
                    if local in replacements:
                        for child in element:
                            if child.tag == f"{{{namespace}}}srgbClr":
                                child.set("val", replacements[local])
                data = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
            target.writestr(item, data)
    temporary.replace(path)


def generate(output_root: Path) -> Path:
    input_dir = output_root / "input"
    if input_dir.exists():
        shutil.rmtree(input_dir)
    input_dir.mkdir(parents=True)
    make_pdf(input_dir / "research.pdf")
    make_template(input_dir / "template.pptx")
    (input_dir / "task.md").write_text(
        "# SYNTHETIC work order\n\nFormat: 6 slides; 8 minutes; audience: methods reviewers.\n"
        "Create a concise evidence-linked academic briefing from research.pdf.\n",
        encoding="utf-8",
    )
    case = {
        "case_id": "SYNTHETIC-evidence-span-001",
        "mode": "generate",
        "materials": ["research.pdf", "task.md"],
        "artifacts": {"template": "template.pptx"},
        "workorder": "task.md",
        "output_contract": {"fields": {
            "editable_source": {"type": "string", "description": "Editable PPTX"},
            "export_artifact": {"type": "string"},
            "content_map": {"type": "string"},
            "compliance_checks": {"type": "object"},
            "exceptions": {"type": "array"},
        }},
    }
    (input_dir / "case.json").write_text(json.dumps(case, indent=2) + "\n", encoding="utf-8")
    return input_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    path = generate(args.output_root.resolve())
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
