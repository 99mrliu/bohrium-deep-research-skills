#!/usr/bin/env python3
"""Recompute all IR -> MathML -> IR checks from an extraction catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict

from mathml_ir import roundtrip_ir


def load_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, help="Path to mathml/catalog.json")
    parser.add_argument("--strict", action="store_true", help="Return 2 for any unsupported node or discrepancy")
    args = parser.parse_args()
    catalog_path = Path(args.catalog).expanduser().resolve()
    catalog = load_json(catalog_path)
    formulas = catalog.get("formulas")
    if not isinstance(formulas, list):
        raise ValueError("catalog.formulas must be an array")

    reports = []
    for entry in formulas:
        if not isinstance(entry, dict) or not isinstance(entry.get("ir"), dict):
            raise ValueError("Every catalog formula entry must contain an IR object")
        report = {"formula_key": entry.get("formula_key"), **roundtrip_ir(entry["ir"])}
        reports.append(report)
        relative = entry.get("roundtrip_file")
        if isinstance(relative, str):
            # catalog.json is in work/mathml, while roundtrip_file starts with mathml/.
            output = catalog_path.parent.parent / relative
            write_json(output, report)
        print(
            f"{report['formula_key']}: status={report['status']}, "
            f"discrepancies={len(report['discrepancies'])}, "
            f"unsupported={len(report['unsupported_nodes'])}"
        )
        for discrepancy in report["discrepancies"]:
            print(f"  DISCREPANCY {discrepancy['path']}: {discrepancy['kind']}", file=sys.stderr)
        for unsupported in report["unsupported_nodes"]:
            print(f"  UNSUPPORTED {unsupported['path']}: {unsupported['tag']}", file=sys.stderr)

    bad = [report for report in reports if report["status"] != "pass"]
    status = "insufficient_evidence" if not reports else ("partial" if bad else "success")
    summary = {
        "case_id": catalog.get("case_id"),
        "status": status,
        "formula_count": len(reports),
        "canonical_roundtrip_pass_count": len(reports) - len(bad),
        "nonpass_formula_keys": [report["formula_key"] for report in bad],
        "reports": reports,
        "publisher_text_is_truth": False,
        "note": "Advertised alttext/tex-math checks in catalog.json remain separate; this summary verifies only canonical IR roundtrip.",
    }
    summary_path = catalog_path.parent / "roundtrip-verification.json"
    write_json(summary_path, summary)
    print(f"roundtrip verification: status={status}, summary={summary_path}")
    if args.strict and bad:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
