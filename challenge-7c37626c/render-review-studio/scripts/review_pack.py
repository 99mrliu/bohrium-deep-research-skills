#!/usr/bin/env python3
"""Assemble the review pack and enforce visual completeness.

Writes review_report.md linking every preview, verifies each promised PNG
exists and exceeds a byte-size floor (blank/zero-byte previews fail), and
folds the artifact manifest into result.json. Missing previews degrade the
status to partial with the artifact named. Stdlib only.
"""
import argparse
import json
from pathlib import Path

MIN_PNG_BYTES = 400  # a real rendered PNG of one formula is never smaller


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    args = ap.parse_args()
    work, out = Path(args.work), Path(args.out)

    def load(name):
        p = work / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    render = load("render_report.json")
    compare = load("compare_report.json")
    table = load("table_report.json")

    manifest, problems = [], []

    def add(path, kind):
        p = Path(path)
        if not p.exists():
            problems.append("missing %s: %s" % (kind, path))
            return
        size = p.stat().st_size
        if p.suffix == ".png" and size < MIN_PNG_BYTES:
            problems.append("suspiciously small %s (%d bytes): %s" % (kind, size, path))
        manifest.append({"file": str(p), "kind": kind, "bytes": size})

    for r in render.get("rendered", []):
        add(r["png"], "formula_render")
    for s in compare.get("sheets", []):
        add(s["png"], "comparison_sheet")
    for pg in table.get("pages", []):
        add(pg["png"], "variable_table")
    if compare.get("source_page_png"):
        add(compare["source_page_png"], "source_page")

    unrenderable = render.get("unrenderable", [])

    lines = ["# Review pack (render-review-studio)", ""]
    lines.append("All previews below were rendered in-run from the actual "
                 "transcriptions and source materials.")
    for m in manifest:
        lines.append("- **%s** `%s` (%d bytes)" % (m["kind"], m["file"], m["bytes"]))
    if unrenderable:
        lines += ["", "## Unrenderable formulas (reported, not dropped)"]
        for u in unrenderable:
            lines.append("- `%s`: %s" % (u.get("id"), u.get("reason")))
    if problems:
        lines += ["", "## Pack problems (fail-closed)"]
        lines += ["- " + p for p in problems]
    (out / "review_report.md").write_text("\n".join(lines) + "\n",
                                          encoding="utf-8")

    rp = out / "result.json"
    if rp.exists():
        result = json.loads(rp.read_text(encoding="utf-8"))
        if not manifest and not unrenderable:
            result["status"] = "insufficient_evidence"
            problems.append("no formulas supplied; nothing to render")
        elif problems:
            result["status"] = "partial"
        else:
            result["status"] = "success"
        result.setdefault("answers", {})["review_pack"] = {
            "previews": manifest,
            "unrenderable": unrenderable,
            "report": str(out / "review_report.md"),
        }
        result.setdefault("uncertainty", {})["pack_problems"] = problems
        result.setdefault("artifacts", {})["previews"] = manifest
        result["artifacts"]["review_report"] = str(out / "review_report.md")
        rp.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print("review pack: %d previews, %d unrenderable, %d problems -> %s"
          % (len(manifest), len(unrenderable), len(problems), out / "review_report.md"))


if __name__ == "__main__":
    main()
