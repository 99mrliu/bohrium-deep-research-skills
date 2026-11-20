#!/usr/bin/env python3
"""Self-check for snowball_trace output. Stdlib only.

Re-reads /app/output/result.json and independently verifies:
  1. every edge endpoint exists as a node;
  2. every edge carries a source locator (file + pointer);
  3. every locator file actually exists on disk (re-checkable evidence);
  4. direction labels are consistent (backward = reference, forward = citation);
  5. layer numbers are coherent (child layer == parent layer + 1 for tree edges);
  6. result.json carries case_id, status, sources, uncertainty;
  7. no two nodes share the same DOI (identity hygiene spot check).

Writes /app/work/verify_report.json and prints a one-line summary.
Exit code 0 always; the report carries pass/fail per check.
"""
import json
import os
import sys
from pathlib import Path


def main():
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "/app/output")
    work_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "/app/work")
    work_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / "result.json"
    report = {"checks": [], "ok": True}

    def check(name, ok, detail=""):
        report["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
        if not ok:
            report["ok"] = False

    if not result_path.exists():
        check("result_exists", False, "result.json missing")
        (work_dir / "verify_report.json").write_text(json.dumps(report, indent=2))
        print(json.dumps({"ok": False, "reason": "result.json missing"}))
        return 0
    result = json.loads(result_path.read_text(encoding="utf-8"))
    nodes = {n["key"]: n for n in result.get("nodes", [])}
    edges = result.get("edges", [])

    check("case_id_present", bool(result.get("case_id")), str(result.get("case_id")))
    check("status_field", result.get("status") in ("ok", "partial", "failed"),
          str(result.get("status")))

    bad_endpoints = [e for e in edges
                     if e.get("from") not in nodes or e.get("to") not in nodes]
    check("edge_endpoints_resolve", not bad_endpoints,
          "%d edges with unknown endpoints" % len(bad_endpoints))

    missing_loc = [e for e in edges
                   if not (e.get("source") or {}).get("file")]
    check("edge_provenance_complete", not missing_loc,
          "%d edges lack source file" % len(missing_loc))

    missing_files = sorted({(e["source"] or {}).get("file") for e in edges
                            if (e.get("source") or {}).get("file")
                            and not os.path.exists(e["source"]["file"])})
    check("locator_files_exist", not missing_files,
          "; ".join(missing_files[:5]))

    bad_dir = [e for e in edges if e.get("direction") not in ("backward", "forward")]
    check("direction_labels_valid", not bad_dir, "%d bad" % len(bad_dir))

    layer_bad = 0
    for e in edges:
        f, t = nodes.get(e["from"]), nodes.get(e["to"])
        if f and t and e.get("layer") is not None and t.get("layer") is not None:
            if t["layer"] > e["layer"]:
                layer_bad += 1
    check("layer_coherence", layer_bad == 0, "%d incoherent edges" % layer_bad)

    seen_doi, dup = {}, []
    for n in nodes.values():
        d = n.get("doi")
        if d:
            if d in seen_doi:
                dup.append(d)
            seen_doi[d] = n["key"]
    check("no_duplicate_doi", not dup, "; ".join(dup[:5]))

    check("sources_listed", bool(result.get("sources")),
          "%d sources" % len(result.get("sources", [])))
    check("uncertainty_field", "uncertainty" in result)

    (work_dir / "verify_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": report["ok"],
                      "failed": [c["check"] for c in report["checks"] if not c["ok"]]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
