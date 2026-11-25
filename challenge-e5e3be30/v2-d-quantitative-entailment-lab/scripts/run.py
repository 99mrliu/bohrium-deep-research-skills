#!/usr/bin/env python3
"""Quantitative entailment runner under the 900-second / 64-request budget.

The Agent supplies structured observations extracted from the original paper and,
optionally, semantic verdicts. This script writes an early partial result, real
recomputation evidence, an SVG, dynamic-contract output and verification. It does
not parse PDF layout or pretend that numeric matching is semantic entailment.
"""
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
from contract import assemble, audit, case_identifier, find_contract
from finalize import draft_verdicts, finalize
from quantlib import InputError, build_report, effect_svg, read_json, write_json


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative_label(path, root):
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except (ValueError, OSError):
        return Path(path).name


def inventory(case_path, input_dir, claims_path, paper_paths):
    entries, seen = [], set()
    candidates = [(case_path, "case"), (claims_path, "claims"), (Path(input_dir) / "task.md", "task")]
    candidates.extend((Path(path), "paper") for path in paper_paths)
    for path, kind in candidates:
        if not path.is_file():
            continue
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        identifier = kind if kind != "paper" or not any(e["id"] == "paper" for e in entries) else "paper-%d" % (1 + sum(e["kind"] == "paper" for e in entries))
        entries.append({"id": identifier, "kind": kind, "path": relative_label(path, input_dir),
                        "sha256": sha256(path), "bytes": path.stat().st_size})
    if not any(entry["kind"] == "task" for entry in entries):
        task_path = Path(case_path).parent / "task.md"
        if task_path.is_file():
            entries.append({"id": "task", "kind": "task", "path": relative_label(task_path, input_dir),
                            "sha256": sha256(task_path), "bytes": task_path.stat().st_size})
    return entries


def discover_papers(input_dir, explicit):
    if explicit:
        return [Path(path) for path in explicit]
    if not Path(input_dir).is_dir():
        return []
    return sorted(path for path in Path(input_dir).rglob("*")
                  if path.is_file() and path.suffix.lower() in (".pdf", ".md", ".txt") and path.name != "task.md")[:10]


def locate_observations(argument, work, input_dir):
    candidates = [Path(argument)] if argument else [Path(work) / "observations.json", Path(input_dir) / "observations.json"]
    return next((path for path in candidates if path.is_file()), candidates[0])


def write_manifest(path, case_id, status, started, changes, uncertainties, sources, error=None):
    artifacts = sorted(item.name for item in path.parent.iterdir() if item.is_file())
    write_json(path, {
        "schema_version": "1.0", "skill": "quantitative-entailment-lab", "case_id": case_id,
        "status": status, "started_at": started[1], "finished_at": timestamp(),
        "elapsed_seconds": round(time.monotonic() - started[0], 3),
        "time_budget_policy": "soft budget 780 seconds within overall 900-second run; computations are local and bounded",
        "sources": sources, "change_records": changes, "uncertainty": uncertainties,
        "artifacts": artifacts, "error": error,
    })


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="/input/case.json")
    parser.add_argument("--claims", default="/input/claims-to-verify.json")
    parser.add_argument("--input-dir", default="/input")
    parser.add_argument("--observations", help="Agent-extracted observations; default /app/work/observations.json then /input/observations.json")
    parser.add_argument("--verdicts", help="optional Agent-authored verdict JSON; otherwise result remains partial")
    parser.add_argument("--paper", action="append", default=[], help="source paper/text path, repeatable")
    parser.add_argument("--out", default="/app/output")
    parser.add_argument("--work", default="/app/work")
    parser.add_argument("--confidence", type=float, default=0.95)
    parser.add_argument("--time-budget", type=int, default=780)
    args = parser.parse_args(argv)
    started = (time.monotonic(), timestamp())
    out, work = Path(args.out), Path(args.work)
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    case_path, claims_path = Path(args.case), Path(args.claims)
    case = read_json(case_path) if case_path.is_file() else {}
    case_id = case_identifier(case)
    uncertainties, changes = [], [{"at": started[1], "action": "run_started"}]
    if not case:
        uncertainties.append("case.json missing or empty; case_id and output_contract may be unresolved")
    if args.time_budget <= 0 or args.time_budget > 850:
        return_code = 1
        print("ERROR: --time-budget must be in 1..850 seconds", file=sys.stderr)
        return return_code
    papers = discover_papers(args.input_dir, args.paper)
    sources = inventory(case_path, args.input_dir, claims_path, papers)
    if not any(source["kind"] == "paper" for source in sources):
        uncertainties.append("No paper file was discovered; observation quotes cannot be source-file verified by this runner")
    if not papers and args.paper:
        uncertainties.append("Explicit paper paths were not readable")
    empty_report = {"case_id": case_id, "synthetic": False, "derived": [], "statistical_tests": [], "observations": [], "warnings": []}
    context = {"case_id": case_id, "sources": sources, "uncertainty": uncertainties, "change_records": changes,
               "report_artifact": "quantitative-report.json", "plot_artifact": "effect-plot.svg"}
    result_path = out / "result.json"
    report_path = out / "quantitative-report.json"
    try:
        claims_document = read_json(claims_path)
        claims = claims_document.get("claims") if isinstance(claims_document, dict) else claims_document
        if not isinstance(claims, list):
            raise InputError("claims-to-verify.json must contain a list of claim questions")
        # Early partial is contract-shaped before observation validation/calculation.
        early_change = {"at": timestamp(), "action": "early_partial_written"}
        early_context = dict(context)
        early_context.update({"case_id": case_id, "status": "partial", "claim_verdicts": draft_verdicts(claims, empty_report),
                              "uncertainty": uncertainties + ["Early partial: recomputation not finished"],
                              "change_records": changes + [early_change],
                              "quantitative_report": empty_report, "derived": [], "observations": [], "warnings": [],
                              "summary": {"unresolved": len(claims)}})
        early_result, field_status = assemble(find_contract(case), early_context)
        changes.append(early_change)
        write_json(result_path, early_result)
        write_json(out / "verification.json", audit(early_result, find_contract(case), field_status, len(claims)))
        write_json(out / "run-context.json", context)
        write_manifest(out / "run-manifest.json", case_id, "partial", started, changes,
                       early_context["uncertainty"], sources)

        observations_path = locate_observations(args.observations, args.work, args.input_dir)
        if not observations_path.is_file():
            raise InputError("Agent-extracted observations.json not found: " + observations_path.name)
        if time.monotonic() - started[0] > args.time_budget:
            raise InputError("soft time budget exhausted before recomputation")
        observations_document = read_json(observations_path)
        report = build_report(observations_document, claims_document, case_id, args.confidence)
        write_json(report_path, report)
        svg = effect_svg(report)
        if svg is not None:
            (out / "effect-plot.svg").write_text(svg, encoding="utf-8")
        changes.append({"at": timestamp(), "action": "quantitative_report_and_effect_svg_generated",
                        "derived_count": len(report["derived"]), "statistical_test_count": len(report["statistical_tests"])})
        if report["synthetic"]:
            uncertainties.append("All example observations, claims, calculations and plots marked SYNTHETIC are artificial, not empirical findings.")
        write_json(out / "run-context.json", context)
        verdict_document = read_json(args.verdicts) if args.verdicts else None
        result, verification = finalize(case, claims_document, report, verdict_document, context)
        if not any(source["kind"] == "paper" for source in sources):
            # Missing original paper means the run is inherently partial even if
            # Agent supplied syntactically valid verdicts.
            if isinstance(result.get("status"), dict):
                result["status"] = {"state": "partial", "complete": False}
            else:
                result["status"] = "partial"
            verification["warnings"].append("downgraded to partial because no paper source was discovered")
        write_json(result_path, result)
        write_json(out / "verification.json", verification)
        status = result.get("status") if isinstance(result.get("status"), str) else result.get("status", {}).get("state", "partial")
        write_manifest(out / "run-manifest.json", case_id, status, started, result.get("change_records", changes),
                       result.get("uncertainty", uncertainties), sources)
        print(json.dumps({"status": status, "case_id": case_id, "derived": len(report["derived"]),
                          "result": "result.json", "report": "quantitative-report.json"}, ensure_ascii=False))
        return 0 if status in ("success", "partial") else 1
    except (InputError, OSError, ValueError) as exc:
        message = str(exc)
        changes.append({"at": timestamp(), "action": "recomputation_failed", "error": message})
        uncertainties.append(message)
        if result_path.is_file():
            try:
                partial = read_json(result_path)
                partial["status"] = "partial"
                partial["uncertainty"] = uncertainties
                partial["change_records"] = changes
                write_json(result_path, partial)
            except Exception:
                pass
        write_manifest(out / "run-manifest.json", case_id, "partial", started, changes, uncertainties, sources, message)
        print("ERROR: " + message, file=sys.stderr)
        print(json.dumps({"status": "partial", "case_id": case_id, "result": "result.json"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
