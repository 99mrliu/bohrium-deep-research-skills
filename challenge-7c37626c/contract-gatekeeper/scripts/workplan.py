#!/usr/bin/env python3
"""Budget-aware phase plan with checkpoints.

Reads triage.json (when present) and writes plan.md: phases matched to the
input branch, each with a checkpoint that rewrites result.json. Budget:
64 model requests / 900 s. Stdlib only.
"""
import argparse
import json
from pathlib import Path

BUDGET = {"model_requests": 64, "seconds": 900}

PHASES = {
    "default": [
        ("P0 triage + bank early partial", "1 request", "always"),
        ("P1 inventory & evidence sweep", "4 requests", "always"),
        ("P2 primary analysis per task", "24 requests", "capability-gated"),
        ("P3 secondary analysis / gap fill", "20 requests", "capability-gated"),
        ("P4 self-check + lint + finalize", "8 requests", "always"),
    ],
    "metrics_only": [
        ("P0 triage + bank early partial", "1 request", "always"),
        ("P1 restate explicit metrics with conditions", "6 requests", "always"),
        ("P2 name missing formula objects", "6 requests", "always"),
        ("P4 lint + finalize as insufficient_evidence", "4 requests", "always"),
    ],
    "pdf_only": [
        ("P0 triage + bank early partial", "1 request", "always"),
        ("P1 visual transcription (marked visual)", "18 requests", "always"),
        ("P2 grounding & checks from visual evidence", "24 requests", "always"),
        ("P4 lint + finalize", "8 requests", "always"),
    ],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="/app/work")
    args = ap.parse_args()
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)

    branch = "default"
    t = work / "triage.json"
    if t.exists():
        branch = json.loads(t.read_text(encoding="utf-8")).get("branch", "default")
    phases = PHASES.get(branch, PHASES["default"])

    lines = ["# Work plan (contract-gatekeeper)", "",
             "Budget: %d model requests / %d s. Every checkpoint rewrites "
             "/app/output/result.json so an interrupted run still ships an "
             "honest partial." % (BUDGET["model_requests"], BUDGET["seconds"]),
             "", "| phase | budget | gate | checkpoint |",
             "|-|-|-|-|"]
    for name, budget, gate in phases:
        lines.append("| %s | %s | %s | rewrite result.json (partial allowed) |"
                     % (name, budget, gate))
    lines += ["", "Rules:",
              "- Checkpoint after EVERY phase; a result.json older than one "
              "phase is stale.",
              "- Skip capability-gated phases only when triage marked the "
              "capability False; 'repair_first'/'context_needed' means spend "
              "requests there, not elsewhere.",
              "- The null-reason rule applies from P0 onward.",
              "- Never spend the last 4 requests before linting: reserve "
              "P4 always."]
    (work / "plan.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("plan: branch=%s, %d phases -> %s" % (branch, len(phases), work / "plan.md"))


if __name__ == "__main__":
    main()
