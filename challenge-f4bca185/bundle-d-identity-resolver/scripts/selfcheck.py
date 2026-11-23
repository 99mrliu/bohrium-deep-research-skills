#!/usr/bin/env python3
"""Self-check harness for the identity resolver skill.

Runs, using only the stdlib and paths relative to this repository:

  1. pipeline on examples/synthetic-case.json (twice, into temp dirs)
     -> asserts byte-identical outputs (determinism);
  2. expectation assertions on duplicate decisions
     (aliases merge, phases/dopants/contexts/sources never merge,
     conflicts never averaged, independent replicates kept distinct);
  3. CSV ingestion on examples/synthetic-extra.csv;
  4. invalid-input test (malformed JSON, missing file)
     -> honest status=input_error, exit code 2, partial result.json written;
  5. --refresh-examples: writes the deterministic example outputs into
     examples/synthetic-output (used to regenerate the shipped example).

Exit code 0 when every check passes, 1 otherwise. No timestamps or
machine-specific paths are written anywhere.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "identity_resolver.py"
CASE = ROOT / "examples" / "synthetic-case.json"
TASK = ROOT / "examples" / "synthetic-task.md"
CSV = ROOT / "examples" / "synthetic-extra.csv"

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(f"{name}: {detail}")


def run_pipeline(case: Path, out: Path, work: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--case", str(case), "--task", str(TASK),
         "--work", str(work), "--out", str(out)],
        capture_output=True, text=True)


def load(out: Path, name: str):
    with open(out / name, "r", encoding="utf-8") as fh:
        return json.load(fh)


def dir_bytes(d: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(d.iterdir()) if p.is_file()}


def main() -> int:
    refresh = "--refresh-examples" in sys.argv

    with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
        o1, w1 = Path(t1) / "out", Path(t1) / "work"
        o2, w2 = Path(t2) / "out", Path(t2) / "work"

        r1 = run_pipeline(CASE, o1, w1)
        check("json_run_exit_0", r1.returncode == 0, r1.stderr[-500:])
        r2 = run_pipeline(CASE, o2, w2)
        check("json_rerun_exit_0", r2.returncode == 0, r2.stderr[-500:])

        b1, b2 = dir_bytes(o1), dir_bytes(o2)
        check("determinism_byte_identical", b1 == b2,
              "differing files: " + ", ".join(
                  k for k in set(b1) | set(b2) if b1.get(k) != b2.get(k)))

        cleaned = load(o1, "cleaned_records.json")
        report = load(o1, "duplicate_report.json")
        review = load(o1, "review_queue.json")
        result = load(o1, "result.json")
        chlog = load(o1, "change_log.json")

        rows = cleaned["rows"]
        by_member = {}
        for row in rows:
            for m in row["members"]:
                by_member[m["record_id"]] = row

        # --- expectation assertions (synthetic ground truth)
        def cluster_of(rid):
            return by_member[rid]["cluster_id"]

        check("records_ingested", result["counts"]["input_records"] == 19,
              f"got {result['counts']['input_records']}")
        check("alias_exact_duplicate_merged",
              cluster_of("r0001") == cluster_of("r0002")
              and by_member["r0001"]["member_count"] >= 2,
              "TiO2 vs 'titanium dioxide (rutile)' identical row must merge")
        check("unit_conversion_enables_merge",
              cluster_of("r0007") == cluster_of("r0001"),
              "3000 meV must equal 3.0 eV within one study/locator/run")
        check("independent_replicate_kept_distinct",
              cluster_of("r0003") != cluster_of("r0001"),
              "run-2 replicate must not merge into run-1")
        check("independent_replicate_distinct_experiment_id",
              by_member["r0003"]["experiment_id"] != by_member["r0001"]["experiment_id"])
        check("anatase_not_merged_with_rutile",
              cluster_of("r0004") != cluster_of("r0001"))
        check("doped_sample_not_merged_with_undoped",
              cluster_of("r0005") != cluster_of("r0001"))
        check("conflict_kept_separate",
              cluster_of("r0006") != cluster_of("r0001"),
              "3.05 eV vs 3.0 eV same identity must be a conflict, not a merge")
        conflict_states = [c for c in report["candidates"]
                           if c["state"] == "conflict"]
        check("conflict_pairs_reported",
              any(set(c["pair"]) == {"r0001", "r0006"} for c in conflict_states),
              "conflict pair r0001/r0006 missing")
        check("conflict_never_averaged",
              abs(by_member["r0001"]["value"] - 3.0) < 1e-12
              and abs(by_member["r0006"]["value"] - 3.05) < 1e-12,
              "conflicting values must remain the original member values")
        check("different_context_not_merged",
              cluster_of("r0010") != cluster_of("r0011")
              and cluster_of("r0010") != cluster_of("r0001"),
              "300 K vs 350 K vs unspecified context must stay separate")
        check("context_unit_conversion_enables_exact_dup",
              cluster_of("r0012") == cluster_of("r0013"),
              "25 degC must normalize to 298.15 K and reveal the repeated row")
        check("cross_source_same_value_not_merged",
              cluster_of("r0014") != cluster_of("r0001"),
              "same value from a different source is corroboration, not duplicate")
        xs = [c for c in report["candidates"]
              if c["state"] == "not_duplicate" and "r0014" in c["pair"]]
        check("cross_source_pair_logged", len(xs) >= 1)
        check("hydrate_not_merged_with_anhydrous",
              cluster_of("r0018") != cluster_of("r0019"),
              "Na2SO4 vs Na2SO4·10H2O are different samples")
        check("unknown_unit_flagged_null_normalized",
              by_member["r0015"]["value_normalized"] is None
              and any(a["kind"] == "unknown_unit" and a["record_id"] == "r0015"
                      for a in review["anomalies"]))
        check("missing_unit_flagged_null_normalized",
              by_member["r0008"]["value_normalized"] is None
              and any(a["kind"] == "missing_unit" and a["record_id"] == "r0008"
                      for a in review["anomalies"]))
        check("missing_value_stays_null",
              by_member["r0009"]["value"] is None
              and by_member["r0009"]["value_kind"] == "missing")
        check("range_value_kept_as_interval",
              by_member["r0016"]["value"] is None
              and by_member["r0016"]["value_min"] == 2.3
              and by_member["r0016"]["value_max"] == 2.5)
        check("out_of_range_flagged_not_modified",
              by_member["r0017"]["value_normalized"] == 25
              and any(a["kind"] == "out_of_plausible_range"
                      and a["record_id"] == "r0017"
                      for a in review["anomalies"]))
        check("status_success", result["status"] == "success",
              result["status"])
        check("invariants_all_pass",
              all(c["passed"] for c in result["invariants"]))
        check("contract_fields_present",
              all(k in result for k in
                  ("cleaned_table", "duplicate_clusters", "review_summary",
                   "summary", "custom_unmapped_note")))
        check("contract_unmapped_field_null_and_unresolved",
              result.get("custom_unmapped_note") is None
              and any(u["item"] == "output_contract.custom_unmapped_note"
                      for u in result["unresolved"]))
        check("contract_cleaned_table_filled",
              isinstance(result.get("cleaned_table"), dict)
              and result["cleaned_table"]["row_count"] == result["counts"]["output_rows"])
        check("change_log_rule_coded",
              all("rule_id" in c and "record_id" in c and "change_id" in c
                  for c in chlog["changes"]))
        check("change_log_covers_merge_and_conflict",
              any(c["rule_id"] == "D-001/D-002" for c in chlog["changes"])
              and any(c["rule_id"] == "D-009" for c in chlog["changes"]))
        check("sources_recorded",
              {s["source_key"] for s in result["sources"]}
              == {"source:10.0000/synth.a", "source:10.0000/synth.b",
                  "source:10.0000/synth.c"})
        check("member_lineage_retained",
              result["counts"]["input_records"]
              == sum(r["member_count"] for r in rows))
        check("synthetic_mark_propagated",
              result.get("synthetic_input") is True)

        # --- CSV ingestion
        with tempfile.TemporaryDirectory() as t3:
            o3, w3 = Path(t3) / "out", Path(t3) / "work"
            rc = run_pipeline(CSV, o3, w3)
            check("csv_run_exit_0", rc.returncode == 0, rc.stderr[-500:])
            cj = load(o3, "cleaned_records.json")
            crow_members = [m["record_id"] for row in cj["rows"]
                            for m in row["members"]]
            check("csv_records_ingested", len(crow_members) == 3,
                  str(crow_members))
            merged = [row for row in cj["rows"] if row["member_count"] == 2]
            check("csv_alias_duplicate_merged", len(merged) == 1,
                  "TiO2 / titanium dioxide identical CSV rows must merge")
            check("csv_replicate_kept_distinct",
                  len(cj["rows"]) == 2, "replicate run-2 must remain separate")

        # --- invalid input: malformed JSON
        with tempfile.TemporaryDirectory() as t4:
            bad = Path(t4) / "bad.json"
            bad.write_text("{not valid json", encoding="utf-8")
            o4, w4 = Path(t4) / "out", Path(t4) / "work"
            rb = run_pipeline(bad, o4, w4)
            check("invalid_json_exit_2", rb.returncode == 2,
                  f"exit={rb.returncode}")
            rj = load(o4, "result.json")
            check("invalid_json_honest_status",
                  rj["status"] == "input_error" and rj["change_records"] == [])
        # --- invalid input: missing file
        with tempfile.TemporaryDirectory() as t5:
            o5, w5 = Path(t5) / "out", Path(t5) / "work"
            rm = run_pipeline(Path(t5) / "nope.json", o5, w5)
            check("missing_file_exit_2", rm.returncode == 2)
            rj5 = load(o5, "result.json")
            check("missing_file_honest_status", rj5["status"] == "input_error")

        if refresh:
            dest = ROOT / "examples" / "synthetic-output"
            dest.mkdir(exist_ok=True)
            for name, data in b1.items():
                (dest / name).write_bytes(data)
            print(f"refreshed {len(b1)} files into examples/synthetic-output")

    print()
    if FAILURES:
        print(f"SELF-CHECK FAILED ({len(FAILURES)} failure(s))")
        for f in FAILURES:
            print(" -", f)
        return 1
    print("SELF-CHECK PASSED (all checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
