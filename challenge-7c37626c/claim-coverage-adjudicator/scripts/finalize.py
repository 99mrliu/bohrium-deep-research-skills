#!/usr/bin/env python3
"""Adjudicate afresh, then write the typed contract from the authored draft."""
from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

from adjudicate import adjudicate
from coverage_common import read_json, validate_contract_shape, write_json
from final_result import assemble_result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="/input/case.json")
    parser.add_argument("--work", default="/app/work")
    parser.add_argument("--out", default="/app/output")
    parser.add_argument("--sources")
    parser.add_argument("--claims")
    parser.add_argument("--draft")
    args = parser.parse_args()
    work, out = Path(args.work), Path(args.out)
    case_path = Path(args.case)
    sources_path = Path(args.sources) if args.sources else work / "source_excerpts.json"
    claims_path = Path(args.claims) if args.claims else work / "claims.json"
    draft_path = Path(args.draft) if args.draft else work / "result.draft.json"
    try:
        case, sources, claims, draft = (
            read_json(case_path), read_json(sources_path),
            read_json(claims_path), read_json(draft_path),
        )
        if not all(isinstance(value, dict) for value in (case, sources, claims, draft)):
            raise ValueError("case, sources, claims, and draft must be JSON objects")
    except Exception as exc:
        print("finalize: cannot consume authored inputs: %s" % exc, file=sys.stderr)
        print("finalize: existing early/checkpoint result.json is left unchanged", file=sys.stderr)
        return 2

    report = adjudicate(case, sources, claims, draft, work)
    write_json(work / "adjudication.json", report)
    result = assemble_result(
        case, draft, claims, report["recommended_status"], report["issues"], work
    )
    # Status was chosen by the adjudicator, never copied from the draft.
    contract_issues = validate_contract_shape(result, case)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "result.json", result)

    log_path = work / "change_log.json"
    try:
        log = read_json(log_path) if log_path.exists() else {"changes": []}
        if not isinstance(log, dict) or not isinstance(log.get("changes"), list):
            log = {"changes": []}
    except Exception:
        log = {"changes": [{"event": "previous change log unreadable"}]}
    log["changes"].append({
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "event": "finalized_after_adjudication",
        "draft": str(draft_path),
        "status": result.get("status"),
        "issue_count": report["issue_count"],
        "result": str(out / "result.json"),
    })
    write_json(log_path, log)
    print("finalize: status=%s issues=%d result=%s" % (
        result.get("status"), report["issue_count"], out / "result.json"))
    if contract_issues:
        print("finalize: result remains contract-invalid; see adjudication report", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
