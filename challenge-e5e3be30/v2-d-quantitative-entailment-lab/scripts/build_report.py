#!/usr/bin/env python3
"""Recompute source-linked observations and write a quantitative evidence report.

Invalid n/events/interval/unit inputs exit 1. A successful report still contains
no scientific claim verdict: Agent semantic adjudication is a separate step.
"""
import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True
from quantlib import InputError, build_report, effect_svg, read_json, write_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", required=True)
    parser.add_argument("--claims", required=True)
    parser.add_argument("--case-id", default="unspecified")
    parser.add_argument("--confidence", type=float, default=0.95)
    parser.add_argument("--out", required=True, help="quantitative-report.json")
    parser.add_argument("--svg", help="optional effect/equivalently uncertainty SVG output")
    args = parser.parse_args(argv)
    try:
        observations = read_json(args.observations)
        claims = read_json(args.claims)
        report = build_report(observations, claims, args.case_id, args.confidence)
        write_json(args.out, report)
        svg_path = None
        if args.svg:
            svg = effect_svg(report)
            if svg is not None:
                Path(args.svg).parent.mkdir(parents=True, exist_ok=True)
                Path(args.svg).write_text(svg, encoding="utf-8")
                svg_path = args.svg
        print({"status": report["status"], "derived": len(report["derived"]),
               "tests": len(report["statistical_tests"]), "out": args.out, "svg": svg_path})
        return 0
    except (InputError, OSError, ValueError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
