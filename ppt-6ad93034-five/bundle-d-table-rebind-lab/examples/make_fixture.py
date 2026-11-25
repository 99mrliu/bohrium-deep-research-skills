#!/usr/bin/env python3
"""make_fixture.py - synthetic 2-page English paper PDF + input/work fixtures.

SYNTHETIC EXAMPLE ONLY. The paper is the fictional "SynNet" study; every
number in it is invented. Writes (under --base, default ./work):
  input/paper.pdf          2-page vector PDF (ASCII only)
  input/case.json          case_id "synthetic-demo-004", six-field contract
  input/task.md            the academic-PPT task statement
  work/replot_spec.json    grouped-bar chart from table-1.csv
  work/plan.json           synthetic agent slide plan (PASS expected)
  work/plan_bad.json       same plan with one hallucinated "97.1%" (FAIL demo)

Table cells are placed with their own absolute Tm x-positions so that
`pdftotext -layout` yields clean columns for table_mine.py.
Pure stdlib. No network.
"""
from __future__ import annotations

import argparse
import json
import os


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_pdf(path, pages):
    # pages: list of list of ops; op = ("text", x, y, size, s) or
    # ("line", x1, y1, x2, y2). Coordinates in PDF pts, bottom-left origin.
    objs = []
    page_ids = [3 + 2 * i for i in range(len(pages))]
    font_id = 3 + 2 * len(pages)
    kids = " ".join(f"{i} 0 R" for i in page_ids)
    objs.append("<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>")
    for i, ops in enumerate(pages):
        lines = []
        for op in ops:
            if op[0] == "text":
                _, x, y, size, s = op
                lines.append(f"BT /F1 {size} Tf 1 0 0 1 {x} {y} Tm ({_esc(s)}) Tj ET")
            else:
                _, x1, y1, x2, y2 = op
                lines.append(f"1 w {x1} {y1} m {x2} {y2} l S")
        stream = "\n".join(lines)
        content_id = page_ids[i] + 1
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>")
        objs.append(f"<< /Length {len(stream.encode('latin-1'))} >>\n"
                    f"stream\n{stream}\nendstream")
    objs.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = b"%PDF-1.4\n"
    offsets = []
    for n, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode("latin-1")
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode("latin-1")
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n").encode("latin-1")
    with open(path, "wb") as f:
        f.write(out)


def para(x, y, size, lines, leading=14):
    return [("text", x, y - i * leading, size, s) for i, s in enumerate(lines)]


def build_paper_ops():
    page1 = []
    page1 += para(48, 745, 14, [
        "SynNet: A Numbers-First Study of SynBench (SYNTHETIC EXAMPLE)"])
    page1 += para(48, 722, 9, [
        "A. Researcher, B. Author - Synthetic Labs, Demo University"])
    page1 += para(48, 696, 11, ["Abstract"])
    page1 += para(48, 678, 10, [
        "We study SynBench, a fully synthetic benchmark invented for this",
        "demo paper. Table 1 reports test accuracy and F1 for three methods,",
        "and Figure 1 shows validation loss across epochs. SynNet reaches an",
        "accuracy of 92.3% on SynBench, improving over two baselines."])
    page1 += para(48, 600, 11, ["1  Introduction"])
    page1 += para(48, 582, 10, [
        "All content in this PDF is synthetic: the study, the benchmark, the",
        "methods and every printed number are fabricated to exercise the",
        "table-rebind-lab skill end to end. Nothing here is a real result."])
    # --- Table 1 (caption above the grid, cells at absolute x positions)
    page1.append(("text", 72, 470, 10,
                  "Table 1: Test accuracy (%) on SynBench (synthetic)."))
    rows = [
        ("Method", "Accuracy (%)", "F1"),
        ("Baseline-A", "88.1", "0.85"),
        ("Baseline-B", "89.7", "0.87"),
        ("SynNet (ours)", "92.3", "0.91"),
    ]
    for i, (m, a, f1) in enumerate(rows):
        y = 452 - 18 * i
        page1.append(("text", 72, y, 10, m))
        page1.append(("text", 260, y, 10, a))
        page1.append(("text", 400, y, 10, f1))
    page1 += para(48, 366, 10, [
        "Every value in Table 1 is printed verbatim above and is synthetic.",
        "The sentence-level claim mirrors the table: SynNet reaches an",
        "accuracy of 92.3% on SynBench."])

    page2 = []
    page2 += para(48, 745, 11, ["2  Experiments"])
    page2 += para(48, 727, 10, [
        "Training is stable across five epochs. Figure 1 plots validation",
        "loss across epochs; the curve below is drawn with vector line ops",
        "and is entirely synthetic content with no real measurement."])
    # --- Figure 1: vector axes + polyline (no text inside except labels)
    page2.append(("line", 100, 420, 460, 420))      # x axis
    page2.append(("line", 100, 420, 100, 620))      # y axis
    pts = [(120, 600), (200, 545), (280, 505), (360, 472), (440, 452)]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        page2.append(("line", x1, y1, x2, y2))
    page2.append(("text", 62, 608, 9, "loss"))
    for i, (px, _) in enumerate(pts, start=1):
        page2.append(("text", px - 2, 406, 9, str(i)))
    page2.append(("text", 262, 388, 9, "epoch"))
    page2.append(("text", 72, 350, 10,
                  "Figure 1: Validation loss across epochs (synthetic)."))
    page2 += para(48, 316, 10, [
        "The validation loss curve decreases monotonically in this synthetic",
        "run and is embedded into slides only as a verified bitmap crop."])
    return [page1, page2]


CASE = {
    "case_id": "synthetic-demo-004",
    "title": "Synthetic SynNet paper -> academic deck (table rebind demo)",
    "paper": "paper.pdf",
    "output_contract": {
        "status": "success | partial | unable_to_determine | refused",
        "editable_source": "path to the editable pptx",
        "export_artifact": "path to the exported pdf, or null",
        "content_map": "slide id -> source binding summary",
        "compliance_checks": "named boolean/string check results",
        "exceptions": "list of precisely stated limitations",
    },
}

TASK_MD = """# Task (synthetic demo)

Turn the attached synthetic paper (`paper.pdf`, the fictional "SynNet" study)
into an editable academic deck:

1. Mine Table 1 into a provenance-carrying CSV and place it on a slide as a
   NATIVE editable pptx table (no screenshots of tables).
2. Replot a grouped-bar chart from the mined CSV in the template palette,
   with an in-chart source note; keep verbatim provenance.
3. Embed Figure 1 as a visually-verified crop with its original caption.
4. Every number on every slide must audit against the paper text or a CSV.
5. Deliver presentation.pptx, tables/, charts/, number_audit.json, result.json.

This is a SYNTHETIC EXAMPLE: all numbers are invented.
"""

REPLOT_SPEC = [{
    "chart_id": "chart-1",
    "csv": "table-1.csv",
    "kind": "grouped-bar",
    "x": "Method",
    "ys": ["Accuracy (%)", "F1"],
    "title": "SynBench accuracy and F1 (synthetic demo)",
    "figure_ref": "Figure 1",
    "palette": ["#1F4E79", "#C0504D"],
    "synthetic": True,
}]

PLAN = {
    "title": "SYNTHETIC EXAMPLE - SynNet on SynBench",
    "slides": [
        {"id": "s1", "kind": "title",
         "title": "SYNTHETIC EXAMPLE - SynNet on SynBench",
         "bullets": ["Mined tables, verbatim replots, verified crops",
                     "Every number audited against the synthetic paper"],
         "source_line": "Source: synthetic fixture paper"},
        {"id": "s2", "kind": "table",
         "title": "Test accuracy on SynBench (Table 1)",
         "table_ref": "table-1",
         "bullets": ["SynNet reaches an accuracy of 92.3% on SynBench."],
         "source_line": "Source: Table 1 of the synthetic paper"},
        {"id": "s3", "kind": "chart",
         "title": "Accuracy and F1 replotted from Table 1",
         "chart_ref": "chart-1",
         "bullets": ["Baseline-A scores 88.1% while SynNet (ours) reaches "
                     "92.3% with F1 of 0.91."],
         "source_line": "Source: Table 1, replotted verbatim"},
        {"id": "s4", "kind": "figure",
         "title": "Validation loss curve (Figure 1)",
         "figure_ref": "fig-1",
         "bullets": ["Validation loss decreases across epochs in the "
                     "synthetic run."],
         "source_line": "Source: Figure 1 of the synthetic paper"},
    ],
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.path.join(os.path.dirname(
        os.path.abspath(__file__)), "work"))
    args = ap.parse_args()
    in_dir = os.path.join(args.base, "input")
    work_dir = os.path.join(args.base, "work")
    os.makedirs(in_dir, exist_ok=True)
    os.makedirs(work_dir, exist_ok=True)

    pdf_path = os.path.join(in_dir, "paper.pdf")
    write_pdf(pdf_path, build_paper_ops())

    with open(os.path.join(in_dir, "case.json"), "w", encoding="utf-8") as f:
        json.dump(CASE, f, indent=2, ensure_ascii=False)
    with open(os.path.join(in_dir, "task.md"), "w", encoding="utf-8") as f:
        f.write(TASK_MD)
    with open(os.path.join(work_dir, "replot_spec.json"), "w",
              encoding="utf-8") as f:
        json.dump(REPLOT_SPEC, f, indent=2, ensure_ascii=False)
    with open(os.path.join(work_dir, "plan.json"), "w", encoding="utf-8") as f:
        json.dump(PLAN, f, indent=2, ensure_ascii=False)

    bad = json.loads(json.dumps(PLAN))
    bad["slides"][1]["bullets"] = [
        "SynNet reaches an accuracy of 97.1% on SynBench."]
    with open(os.path.join(work_dir, "plan_bad.json"), "w",
              encoding="utf-8") as f:
        json.dump(bad, f, indent=2, ensure_ascii=False)

    print(f"[make_fixture] wrote {pdf_path} "
          f"({os.path.getsize(pdf_path)} bytes), case.json, task.md, "
          f"replot_spec.json, plan.json, plan_bad.json")


if __name__ == "__main__":
    main()
