#!/usr/bin/env python3
"""Final gate: lint, record the status transition in the audit trail, and
enforce that a successful status must survive the linter. Any violation
downgrades claimed success to partial with the violations as reason.
Stdlib only.
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contract_lint import lint


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    args = ap.parse_args()
    work, out = Path(args.work), Path(args.out)

    case_path = Path(args.case)
    case = json.loads(case_path.read_text(encoding="utf-8")) if case_path.exists() else {}
    rp = out / "result.json"
    if not rp.exists():
        print("result.json missing; nothing to finalize")
        return 1
    result = json.loads(rp.read_text(encoding="utf-8"))
    before = result.get("status")

    violations = lint(result, case)
    if violations:
        if before == "success":
            result["status"] = "partial"
        result.setdefault("uncertainty", {})["gate_violations"] = violations
    elif before not in ("success", "partial", "insufficient_evidence", "failed"):
        result["status"] = "partial"
        result.setdefault("uncertainty", {})["gate_violations"] = [
            "status %r not in contract enum; degraded to partial" % before]

    trail_path = work / "audit_trail.json"
    trail = []
    if trail_path.exists():
        trail = json.loads(trail_path.read_text(encoding="utf-8")).get("transitions", [])
    trail.append({
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "from": before, "to": result.get("status"),
        "violations": violations,
    })
    (work / "audit_trail.json").write_text(
        json.dumps({"transitions": trail}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    rp.write_text(json.dumps(result, indent=2, ensure_ascii=False),
                  encoding="utf-8")
    print("gate: %s -> %s (%d violations); trail -> %s"
          % (before, result.get("status"), len(violations), trail_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
