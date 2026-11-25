#!/usr/bin/env python3
"""Render observed transition-report rows to a self-contained UTF-8 SVG text preview."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from xml.sax.saxutils import escape


def text(x: float, y: float, value: object, size: int = 14, fill: str = "#172033", weight: str = "400") -> str:
    return (
        f'<text x="{x}" y="{y}" font-family="Arial, Helvetica, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" fill="{fill}">{escape(str(value))}</text>'
    )


def render(report: dict) -> str:
    rows = report.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("transition report has no observed rows to render")
    summary = report["summary"]
    width = 1240
    row_height = 82
    height = 172 + row_height * len(rows)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Counterfactual verdict transition report</title>',
        '<desc id="desc">Text preview generated from independent annotation transitions, not prefabricated verdicts.</desc>',
        f'<rect width="{width}" height="{height}" fill="#f6f8fc"/>',
        text(28, 40, "SYNTHETIC minimal-pair transitions" if report.get("synthetic") else "Minimal-pair transitions", 24, weight="700"),
        text(28, 70, f"status={report.get('status')}  total={summary['total']}  consistent={summary['consistent']}  inconsistent={summary['inconsistent']}", 15),
        text(28, 98, "Verdicts originate in independent annotations; this SVG only renders the observed report.", 13, "#4a5872"),
        text(28, 132, "probe / operator", 13, "#4a5872", "700"),
        text(380, 132, "expected relation", 13, "#4a5872", "700"),
        text(630, 132, "observed verdict transition", 13, "#4a5872", "700"),
        text(1000, 132, "calibration", 13, "#4a5872", "700"),
    ]
    y = 150
    for row in rows:
        good = row["consistent"]
        color = "#18794e" if good else "#b42318"
        background = "#ffffff" if good else "#fff1f0"
        parts.append(f'<rect x="20" y="{y}" width="1200" height="70" rx="8" fill="{background}" stroke="{color}" stroke-width="1"/>')
        parts.append(text(32, y + 25, f"{row['probe_id']} / {row['operator']}", 14, weight="700"))
        parts.append(text(32, y + 49, f"base={row['base_claim_id']}  semantic={row['semantic_relation']}", 12, "#4a5872"))
        parts.append(text(380, y + 37, row["expected_relation"], 14))
        parts.append(
            f'<text x="630" y="{y + 37}" data-observed-transition="{escape(row["observed_transition"])}" '
            f'font-family="Arial, Helvetica, sans-serif" font-size="14" fill="#172033">{escape(row["observed_transition"])}</text>'
        )
        parts.append(text(1000, y + 37, "consistent" if good else "RE-REVIEW", 14, color, "700"))
        y += row_height
    parts.append(text(28, height - 18, "A mismatch requires original-source re-review; it never auto-changes a verdict.", 13, "#4a5872"))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        with args.report.open("r", encoding="utf-8") as handle:
            report = json.load(handle)
        svg = render(report)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(svg, encoding="utf-8")
        print(f"rendered {len(report['rows'])} observed transitions: {args.output}")
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
