#!/usr/bin/env python3
"""Run the clearly labelled SYNTHETIC example; no official answers are stored."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from case_runner import Runner


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--example-dir", required=True, help="Directory containing synthetic case.json and spec.json")
    parser.add_argument("--output-dir", required=True, help="Directory for SVG, result, checkpoint, manifest, and report")
    parser.add_argument("--preview-png", action="store_true", help="Request PNG through an already installed exporter")
    parser.add_argument("--preview-pdf", action="store_true", help="Request PDF through an already installed exporter")
    parser.add_argument("--resume", action="store_true", help="Resume using the output checkpoint and actual input hashes")
    args = parser.parse_args()
    example_dir = Path(args.example_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    runner_args = argparse.Namespace(
        case=str(example_dir / "case.json"),
        task=str(example_dir / "task.md"),
        spec=str(example_dir / "spec.json"),
        work_dir=str(output_dir / "work"),
        output_dir=str(output_dir),
        preview_png=args.preview_png,
        preview_pdf=args.preview_pdf,
        resume=args.resume,
    )
    return Runner(runner_args).run()


if __name__ == "__main__":
    sys.exit(main())
