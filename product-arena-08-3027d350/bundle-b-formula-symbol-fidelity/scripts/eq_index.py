#!/usr/bin/env python3
"""eq_index.py — build the equation index and the contract-aware result.json.

Pipeline stage 3 of the formula-symbol-fidelity skill.

Inputs : math_linearized.jsonl + symbol_inventory.json (stage 1-2 outputs)
         and the case file (--case case.json with case_id + output_contract).
Outputs (in --out-dir):
  * equations_index.json — eq_number -> {page, bbox, linearized text,
    verification}; numbering gaps and duplicates are FLAGGED as
    inconsistencies, never repaired by guessing.
  * result.json — carries the original case_id, echoes every
    output_contract field (filled from the pipeline, or empty with an
    explanation when unknown), an honest status (success|partial),
    sources, uncertainty, and a change_record.

Exit codes: 0 = ok, 2 = input/usage error, 3 = degenerate input.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EQNUM_INT_RE = re.compile(r"^\d+$")


def analyze_numbering(entries):
    """Flag duplicates and integer-sequence gaps. Returns (anomalies, dupes)."""
    anomalies, dupes = [], set()
    counts = {}
    for e in entries:
        counts[e["eq_number"]] = counts.get(e["eq_number"], 0) + 1
    for num, c in sorted(counts.items()):
        if c > 1:
            dupes.add(num)
            anomalies.append(f"duplicate equation number ({num}): {c} occurrences")
    ints = sorted({int(n) for n in counts if EQNUM_INT_RE.match(n)})
    if ints:
        missing = [k for k in range(ints[0], ints[-1] + 1) if k not in ints]
        for k in missing:
            anomalies.append(f"gap in equation numbering: ({k}) missing")
    return anomalies, dupes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--linearized", required=True, help="math_linearized.jsonl")
    ap.add_argument("--inventory", required=True, help="symbol_inventory.json")
    ap.add_argument("--case", required=True, help="case.json of the current case")
    ap.add_argument("--out-dir", required=True, help="output directory")
    args = ap.parse_args(argv)

    try:
        recs = [json.loads(l) for l in Path(args.linearized)
                .read_text(encoding="utf-8").splitlines() if l.strip()]
        inventory = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
        case = json.loads(Path(args.case).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"error: malformed JSON: {exc}", file=sys.stderr)
        return 2

    entries = [r for r in recs if r.get("eq_number")]
    anomalies, dupes = analyze_numbering(entries)
    index = {
        "schema": "equations-index/1",
        "equations": [
            {
                "eq_number": e["eq_number"],
                "page": e["page"],
                "bbox": e["bbox"],
                "line_id": e["line_id"],
                "linearized": e.get("linearized", e["raw_text"]),
                "verification": ("duplicate_number" if e["eq_number"] in dupes
                                 else "ok"),
            } for e in entries
        ],
        "numbering": {"anomalies": anomalies,
                      "policy": "inconsistencies are flagged, never fixed by guessing"},
    }
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    idx_path = out_dir / "equations_index.json"
    idx_path.write_text(json.dumps(index, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    # ---- uncertainty: unknown symbols + numbering anomalies ----------------
    unknown_syms = inventory.get("unknown", [])
    uncertainty = []
    for u in unknown_syms:
        occ = ", ".join(f"p{o['page']}:{o['line_id']}" for o in u["occurrences"])
        uncertainty.append(
            f"unmappable symbol {u['codepoint']} kept verbatim, not guessed ({occ})")
    uncertainty.extend(anomalies)
    for lid in inventory.get("unmatched_lines", []):
        uncertainty.append(f"line {lid} could not be re-matched to word geometry")

    # ---- contract echo ------------------------------------------------------
    field_values = {
        "equations": index["equations"],
        "symbol_audit": {
            "status": inventory.get("status"),
            "totals": inventory.get("totals"),
            "unknown": unknown_syms,
        },
        "uncertainty": uncertainty,
    }
    contract = case.get("output_contract", {})
    echoed = {}
    for field in contract:
        if field in field_values:
            echoed[field] = field_values[field]
        else:
            echoed[field] = {"value": None,
                             "explanation": "contract field not produced by this "
                                            "pipeline; reported empty instead of guessed"}

    status = "success" if (inventory.get("status") == "ok" and not anomalies) \
        else "partial"
    result = {
        "case_id": case.get("case_id", "UNKNOWN_CASE_ID"),
        "status": status,
        "generated_by": "formula-symbol-fidelity/scripts/eq_index.py",
        **echoed,
        "sources": {
            "case": str(args.case),
            "linearized": str(args.linearized),
            "inventory": str(args.inventory),
        },
        "uncertainty": uncertainty,
        "change_record": [
            "parsed math_linearized.jsonl and symbol_inventory.json",
            "built equations_index.json; numbering anomalies flagged, not repaired",
            "echoed every output_contract field; unknown fields left empty "
            "with explanation",
            f"status set to '{status}' from symbol audit + numbering analysis",
        ],
    }
    res_path = out_dir / "result.json"
    res_path.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(json.dumps({"status": status,
                      "equations": len(entries),
                      "anomalies": len(anomalies),
                      "unknown_symbols": len(unknown_syms),
                      "out_dir": str(out_dir)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
