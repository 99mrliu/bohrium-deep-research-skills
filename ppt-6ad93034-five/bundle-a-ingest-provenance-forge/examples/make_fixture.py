#!/usr/bin/env python3
"""Generate the SYNTHETIC example fixture (not an official case).

Default mode writes:
  <input>/paper.pdf   3-page synthetic English paper (stdlib PDF writer, ASCII)
  <input>/case.json   minimal case with a six-field output_contract
  <input>/task.md     slide work order

--emit-plan mode (run AFTER pdf_ingest.py and figure_zones.py) reads
<work>/spans.jsonl and <work>/figures.json and writes <work>/plan.json with
bullets whose quotes REALLY verify against the extracted spans.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


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
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                    f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
                    f"/Contents {content_id} 0 R >>")
        objs.append(f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream")
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
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n"
            "%%EOF\n").encode("latin-1")
    with open(path, "wb") as f:
        f.write(out)


def wrap(text, max_chars=80):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


def para(ops, text, x, y, size=11, leading=14, max_chars=80):
    for ln in wrap(text, max_chars):
        ops.append(("text", x, y, size, ln))
        y -= leading
    return y


def build_pages():
    p1, p2, p3 = [], [], []
    p1.append(("text", 72, 730, 16, "SYNTHETIC PAPER: Adaptive Gradient Sketching"))
    p1.append(("text", 72, 710, 11, "(A fully synthetic example - all content is fabricated)"))
    p1.append(("text", 72, 692, 11, "A. Researcher and B. Coauthor, Synthetic Lab"))
    p1.append(("text", 72, 660, 12, "Abstract"))
    y = para(p1,
             "We study adaptive gradient sketching (AGS), a deliberately simple optimizer "
             "variant for synthetic benchmarks. AGS rescales gradient coordinates using a "
             "running sketch of past updates. The method is evaluated on SynBench, a "
             "synthetic suite with known ground truth. All content in this document is "
             "fabricated for pipeline testing.", 72, 644)
    p1.append(("text", 72, y - 12, 12, "1. Introduction"))
    para(p1,
         "Gradient methods dominate modern optimization. This synthetic paper introduces "
         "AGS and reports controlled experiments on the SynBench suite. The document "
         "exists to exercise a PDF ingest pipeline: it has known text, a known figure, "
         "and known numbers, so every extraction claim can be checked.", 72, y - 30)

    p2.append(("text", 72, 750, 12, "2. Methods"))
    y = para(p2,
             "AGS maintains a sketch of squared gradients and rescales each coordinate "
             "before the update step. We train a small linear model for 50 epochs with "
             "learning rate 0.05 and batch size 32. Each run is repeated with three "
             "synthetic seeds and results are averaged.", 72, 732)
    p2.append(("text", 72, y - 12, 12, "3. Results"))
    para(p2,
         "AGS converges faster than the plain baseline on all synthetic tasks. The final "
         "model reaches an accuracy of 92.3% on the SynBench test set, compared to 89.1% "
         "for the baseline. Figure 1 shows the training curve. Variance across seeds was "
         "small, which suggests the sketching heuristic is stable on this suite.",
         72, y - 30)

    p3.append(("text", 72, 750, 12, "4. Figures and Limitations"))
    # vector figure: axes + descending polyline (top-left region of the page)
    p3.append(("line", 100, 480, 520, 480))  # x axis
    p3.append(("line", 100, 480, 100, 700))  # y axis
    pts = [(120, 680), (200, 645), (280, 605), (360, 568), (440, 542), (500, 526)]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        p3.append(("line", x1, y1, x2, y2))
    p3.append(("text", 72, 458, 10, "Figure 1: Training loss over 50 epochs (synthetic)."))
    y = para(p3,
             "Limitations: results are synthetic and do not reflect real benchmarks.",
             72, 424)
    para(p3,
         "Additional details appear in the synthetic appendix. All numbers on this page "
         "were generated for demonstration purposes only and must not be cited.",
         72, y - 10)
    return [p1, p2, p3]


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def find_span_window(spans, quote, max_window=3):
    """Return span_ids of the shortest consecutive window containing the quote."""
    spans = sorted(spans, key=lambda s: s["reading_order"])
    q = norm(quote)
    for w in range(1, max_window + 1):
        for i in range(len(spans) - w + 1):
            win = spans[i:i + w]
            if len({s["page"] for s in win}) > 1:
                continue
            if q in norm(" ".join(s["text"] for s in win)):
                return [s["span_id"] for s in win], win[0]["page"]
    raise SystemExit(f"[make_fixture] FATAL: quote not found in spans: {quote!r}")


def emit_plan(work):
    spans = [json.loads(l) for l in open(os.path.join(work, "spans.jsonl"), encoding="utf-8")
             if l.strip()]
    figures = {}
    fig_path = os.path.join(work, "figures.json")
    if os.path.isfile(fig_path):
        for f in json.load(open(fig_path, encoding="utf-8")).get("figures", []):
            figures[f["fig_id"]] = f
    fig_id = next((k for k, v in figures.items()
                   if v.get("kind") == "figure" and v.get("crop_path")), None)

    def b(text, quote):
        ids, _ = find_span_window(spans, quote)
        return {"text": text, "span_ids": ids, "quote": quote}

    plan = {
        "synthetic_example": True,
        "deck_title": "Adaptive Gradient Sketching",
        "slides": [
            {"id": "s1", "title": "Adaptive Gradient Sketching",
             "bullets": [b("Synthetic demo deck summarizing a fabricated paper with "
                           "coordinate-level provenance.",
                           "Adaptive Gradient Sketching")],
             "notes": "Synthetic title slide; every bullet cites verified span ids."},
            {"id": "s2", "title": "Key results",
             "bullets": [b("AGS reaches 92.3% accuracy on the SynBench test set.",
                           "accuracy of 92.3% on the SynBench test set"),
                         b("Figure 1 shows the training curve (embedded next slide).",
                           "Figure 1 shows the training curve")],
             "notes": "Numbers verified against cited spans by span_bind.py."},
            {"id": "s3", "title": "Training dynamics",
             "bullets": [b("Training loss decreases over 50 epochs (Figure 1).",
                           "Training loss over 50 epochs")],
             "figure": fig_id,
             "notes": "Figure cropped from the paper's own page by figure_zones.py."},
            {"id": "s4", "title": "Limitations",
             "bullets": [b("All results are synthetic and do not reflect real benchmarks.",
                           "results are synthetic and do not reflect real benchmarks")],
             "notes": "Honest-limitation slide, straight from the paper text."},
        ],
    }
    if fig_id is None:
        for s in plan["slides"]:
            s.pop("figure", None)
        print("[make_fixture] WARNING: no cropped figure found; plan has no figure")
    with open(os.path.join(work, "plan.json"), "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    print(f"[make_fixture] wrote {os.path.join(work, 'plan.json')} "
          f"(figure={fig_id})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit-plan", action="store_true",
                    help="only write plan.json from existing spans/figures")
    ap.add_argument("--input-dir", default=os.environ.get(
        "CASE_INPUT_DIR", os.path.join(HERE, "work", "input")))
    ap.add_argument("--work-dir", default=os.environ.get(
        "CASE_WORK_DIR", os.path.join(HERE, "work", "work")))
    ap.add_argument("--output-dir", default=os.environ.get(
        "CASE_OUTPUT_DIR", os.path.join(HERE, "work", "app-output")))
    args = ap.parse_args()
    if args.emit_plan:
        emit_plan(os.path.abspath(args.work_dir))
        return 0

    os.makedirs(args.input_dir, exist_ok=True)
    pdf_path = os.path.join(args.input_dir, "paper.pdf")
    write_pdf(pdf_path, build_pages())
    print(f"[make_fixture] wrote {pdf_path}")

    case = {
        "case_id": "synthetic-demo-001",
        "synthetic_example": True,
        "output_contract": {
            "status": "result status: success|partial|unable_to_determine|refused",
            "editable_source": "path to the editable .pptx deck",
            "export_artifact": "path to the exported .pdf, or null if no renderer",
            "content_map": "map of slide id to evidence summary",
            "compliance_checks": "named boolean checks",
            "exceptions": "list of known limitations",
        },
    }
    with open(os.path.join(args.input_dir, "case.json"), "w", encoding="utf-8") as f:
        json.dump(case, f, ensure_ascii=False, indent=2)

    with open(os.path.join(args.input_dir, "task.md"), "w", encoding="utf-8") as f:
        f.write("""# Slide work order (SYNTHETIC EXAMPLE)

Turn paper.pdf into a 4-slide academic deck: title, key results, training
dynamics (embed the Figure 1 crop), limitations. Every bullet must cite
verified span ids from the ingest layer; never invent numbers.

This is a synthetic example, not an official case result.
""")
    print(f"[make_fixture] wrote case.json and task.md in {args.input_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
