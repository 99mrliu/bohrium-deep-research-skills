#!/usr/bin/env python3
"""make_fixture.py — create a fully synthetic demo case (SYNTHETIC markers everywhere).

Usage: make_fixture.py <base_dir>

Creates:
  <base>/input/paper.pdf   one-page synthetic English paper (title contains SYNTHETIC)
  <base>/input/case.json   case_id "synthetic-demo-005", output_contract, synthetic_example: true
  <base>/input/task.md     synthetic task brief
  <base>/work/plan.json    3-slide plan whose evidence quotes REALLY appear in the paper
"""
import json
import os
import sys


def _esc(s):
    return s.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def write_pdf(path, pages):
    # pages: list of list of ops; op = ("text", x, y, size, s) or ("line", x1,y1,x2,y2)
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
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>")
        objs.append(f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream")
    objs.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = b"%PDF-1.4\n"
    offsets = []
    for n, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode("latin-1")
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode("latin-1")
    out += f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("latin-1")
    with open(path, "wb") as f:
        f.write(out)


# --- synthetic paper content (ASCII only; quotes here are reused as plan evidence) ---
PAPER_TITLE = "SYNTHETIC PAPER: Gate-Journal Pipelines Improve Auditability"
PAPER_LINES = [
    (PAPER_TITLE, 16, 720),
    ("A. Example and B. Demo, Institute of Synthetic Studies", 11, 695),
    ("Abstract.", 12, 660),
    ("We study whether gated, journaled build pipelines make academic deck", 11, 640),
    ("generation auditable. In a synthetic benchmark of 40 runs, our method", 11, 624),
    ("achieves an accuracy of 92.3% on slide-fact consistency, and every one", 11, 608),
    ("of the 40 runs produced a replay-verifiable delivery manifest.", 11, 592),
    ("Method. Each stage must pass a machine-checked gate before the next", 12, 556),
    ("stage starts; all commands are appended to a hash-chained journal.", 11, 540),
    ("Results. Accuracy of 92.3% versus 71.0% for the ungated baseline;", 12, 508),
    ("zero undetected tampering events across 40 runs.", 11, 492),
    ("Conclusion. Gates plus journals turn it-ran-once into anyone-can-audit.", 12, 460),
]

CASE_JSON = {
    "case_id": "synthetic-demo-005",
    "synthetic_example": True,
    "task": "Turn the attached SYNTHETIC one-page paper into a 3-slide academic deck.",
    "output_contract": {
        "status": "success",
        "editable_source": "/app/output/presentation.pptx",
        "export_artifact": "/app/output/presentation.pdf",
        "content_map": {"slide_titles": "path-or-list"},
        "compliance_checks": ["gates-passed", "journal-verified"],
        "exceptions": []
    }
}

TASK_MD = """# SYNTHETIC EXAMPLE task — not real research

Convert `paper.pdf` (a synthetic one-page English paper; its title contains
SYNTHETIC) into a 3-slide academic deck (title, method, results) with speaker
notes and a footer source line. Every factual bullet must be traceable to a
quote in the paper. This case is synthetic and carries no real-world claims.
"""

PLAN = {
    "meta": {
        "deck_title": "SYNTHETIC EXAMPLE — Gate-Journal Pipelines",
        "source": "paper.pdf (SYNTHETIC fixture)",
        "footer": "Source: SYNTHETIC fixture paper | SYNTHETIC EXAMPLE — not real research"
    },
    "slides": [
        {
            "title": "SYNTHETIC EXAMPLE — Gate-Journal Pipelines Improve Auditability",
            "bullets": [
                "Synthetic benchmark of 40 gated pipeline runs",
                "Every run produced a replay-verifiable delivery manifest"
            ],
            "notes": "Opening slide. All content is synthetic demo data.",
            "evidence": [
                {"quote": "replay-verifiable delivery manifest", "source": "paper.pdf abstract"}
            ]
        },
        {
            "title": "Method: stage gates + hash-chained journal",
            "bullets": [
                "Each stage must pass a machine-checked gate before the next starts",
                "All commands are appended to a hash-chained journal"
            ],
            "notes": "Describe the gated, journaled pipeline.",
            "evidence": [
                {"quote": "machine-checked gate before the next", "source": "paper.pdf method"},
                {"quote": "hash-chained journal", "source": "paper.pdf method"}
            ]
        },
        {
            "title": "Results: accuracy of 92.3%",
            "bullets": [
                "Slide-fact consistency: accuracy of 92.3% vs 71.0% ungated baseline",
                "Zero undetected tampering events across 40 runs"
            ],
            "notes": "Synthetic numbers; do not cite as real results.",
            "evidence": [
                {"quote": "accuracy of 92.3%", "source": "paper.pdf results"}
            ]
        }
    ]
}


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "work")
    input_dir = os.path.join(base, "input")
    work_dir = os.path.join(base, "work")
    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(work_dir, exist_ok=True)

    ops = [("text", 72, y, size, s) for s, size, y in PAPER_LINES]
    ops.append(("line", 72, 700, 540, 700))
    paper_path = os.path.join(input_dir, "paper.pdf")
    write_pdf(paper_path, [ops])

    with open(os.path.join(input_dir, "case.json"), "w", encoding="utf-8") as f:
        json.dump(CASE_JSON, f, indent=2)
    with open(os.path.join(input_dir, "task.md"), "w", encoding="utf-8") as f:
        f.write(TASK_MD)
    with open(os.path.join(work_dir, "plan.json"), "w", encoding="utf-8") as f:
        json.dump(PLAN, f, indent=2)

    print(f"fixture: wrote {paper_path} (+ case.json, task.md, work/plan.json) under {base}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
