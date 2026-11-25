#!/usr/bin/env python3
"""Assemble result.json from the actual list/dict output_contract."""
import argparse
from pathlib import Path

from compare_lib import assemble_result, dump_json, load_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--workorder", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--clusters", type=Path, required=True)
    args = parser.parse_args()
    result = assemble_result(
        load_json(args.case), load_json(args.workorder), args.output_dir,
        load_json(args.validation), load_json(args.clusters)
    )
    dump_json(args.output_dir / "result.json", result)
    # Refresh result.json's own hash/size in a second deterministic pass.
    for artifact in result["artifacts"]:
        if artifact["name"] == "result.json":
            artifact["exists"] = True
            artifact["path"] = str(args.output_dir / "result.json")
            artifact.pop("sha256", None)
            artifact["hash_note"] = "self-referential hash intentionally omitted"
            artifact.pop("bytes", None)
    dump_json(args.output_dir / "result.json", result)
    print(f"result.json status={result['status']}")
    return 0 if result["status"] in {"success", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
