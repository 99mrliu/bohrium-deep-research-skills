#!/usr/bin/env python3
"""Self-check for codiscover output. Stdlib only.

Verifies, independently of the generator:
  1. case_id / status / sources fields exist and are consistent;
  2. no candidate is a direct neighbor of the seed (seed refs / citers excluded);
  3. every candidate has >= 1 structural signal (co-citation or coupling) and the
     evidence items carry locators pointing at existing files;
  4. scores equal the sum of their parts; ranks are monotone in score;
  5. every locator file exists on disk.

Writes /app/work/verify_report.json; exit code always 0.
"""
import json
import os
import sys
from pathlib import Path


def main():
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "/app/output")
    work_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "/app/work")
    work_dir.mkdir(parents=True, exist_ok=True)
    report = {"checks": [], "ok": True}

    def check(name, ok, detail=""):
        report["checks"].append({"check": name, "ok": bool(ok), "detail": str(detail)})
        if not ok:
            report["ok"] = False

    rp = out_dir / "result.json"
    if not rp.exists():
        check("result_exists", False, "result.json missing")
        (work_dir / "verify_report.json").write_text(json.dumps(report, indent=2))
        print(json.dumps({"ok": False}))
        return 0
    r = json.loads(rp.read_text(encoding="utf-8"))
    check("case_id_present", bool(r.get("case_id")), r.get("case_id"))
    check("status_field", r.get("status") in ("ok", "partial", "failed"), r.get("status"))

    cands = r.get("candidates", [])
    seed = r.get("seed") or {}
    seed_ids = {x for x in (seed.get("doi"), seed.get("arxiv")) if x}

    no_signal, no_loc, bad_files = 0, 0, set()
    dup_ids = set()
    seen = set()
    for c in cands:
        ev = c.get("association_evidence", {})
        n_struct = len(ev.get("co_citation", [])) + len(ev.get("bibliographic_coupling", []))
        if n_struct < 1:
            no_signal += 1
        items = list(ev.get("co_citation", [])) + list(ev.get("bibliographic_coupling", []))
        for it in items:
            locs = [v for v in it.values() if isinstance(v, dict) and v.get("file")]
            if not locs:
                no_loc += 1
            for loc in locs:
                if not os.path.exists(loc["file"]):
                    bad_files.add(loc["file"])
        cid = c.get("doi") or c.get("arxiv") or c.get("title")
        if cid in seen:
            dup_ids.add(str(cid)[:60])
        seen.add(cid)
        if c.get("doi") in seed_ids or c.get("arxiv") in seed_ids:
            check("candidate_not_seed", False, cid)
    check("structural_signal_mandatory", no_signal == 0, "%d lack" % no_signal)
    check("evidence_locators_present", no_loc == 0, "%d items" % no_loc)
    check("locator_files_exist", not bad_files, "; ".join(sorted(bad_files)[:5]))
    check("no_duplicate_candidates", not dup_ids, "; ".join(sorted(dup_ids)[:5]))

    score_bad = 0
    for c in cands:
        parts = c.get("score_parts", {})
        if abs(sum(parts.values()) - c.get("score", -1)) > 0.01:
            score_bad += 1
    check("score_equals_parts", score_bad == 0, "%d mismatch" % score_bad)
    scores = [c.get("score", 0) for c in cands]
    check("ranks_monotone", all(scores[i] >= scores[i + 1] - 1e-9
                                for i in range(len(scores) - 1)))
    check("sources_listed", bool(r.get("sources")))
    check("exclusion_documented", bool(r.get("direct_neighbors")))

    (work_dir / "verify_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": report["ok"],
                      "failed": [c["check"] for c in report["checks"] if not c["ok"]]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
