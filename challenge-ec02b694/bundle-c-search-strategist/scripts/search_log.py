#!/usr/bin/env python3
"""search_log.py -- append-only JSONL decision log with replay verification.

Each line of the log is one decision record:

  {
    "seq":             <int, strictly increasing from 1>,
    "round":           <int, search round the decision belongs to>,
    "points":          <list of point dicts emitted/acted on>,
    "results":         <snapshot: list of result-row dicts the decision saw>,
    "results_digest":  <sha256 hex of canonical JSON of the results snapshot>,
    "decision":        <"EMIT" | "STOP" | free-text summary>,
    "criterion_states":<object with the state of every stopping criterion>
  }

Modes:
  append  --log L --round N --points-json P --results-json R --decision D
            [--criteria-json C]
  verify  --log L [--results RESULTS.csv] [--output REPORT.json]

`verify` replays the log and checks, for every record:
  * seq is strictly increasing starting at 1;
  * results_digest equals the recomputed sha256 of the embedded snapshot;
  * mandatory fields are present;
and, when --results is given, that every snapshot row still appears in the
results CSV (third-party cross-check against the raw lab record).

Exit codes: 0 ok, 1 verification failed, 2 bad input.  Never a traceback.

NOTE: the canonical digest helpers below are duplicated verbatim in
next_batch.py so the two scripts stay independent single files; keep them
byte-identical.
"""

import argparse
import csv
import hashlib
import json
import sys

VERSION = "1.0.0"

# --- canonical digest helpers (keep in sync with next_batch.py) ---

def canonical_json(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def results_digest(rows):
    return hashlib.sha256(canonical_json(rows).encode("utf-8")).hexdigest()

# --- end of duplicated helpers ---


def fail(msg, code=2):
    sys.stdout.write(json.dumps({"status": "error", "error": msg},
                                ensure_ascii=False, indent=2) + "\n")
    sys.exit(code)


def parse_json_arg(value, what):
    """Accept an inline JSON string or @path."""
    if value is None:
        return None
    if value.startswith("@"):
        path = value[1:]
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError:
            fail("%s: file not found: %s" % (what, path))
        except json.JSONDecodeError as exc:
            fail("%s: invalid JSON in %s: %s" % (what, path, exc))
        except OSError as exc:
            fail("%s: cannot read %s: %s" % (what, path, exc))
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        fail("%s: invalid inline JSON: %s" % (what, exc))


def read_log(path):
    records = []
    try:
        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    fail("log %s line %d is not valid JSON: %s" % (path, lineno, exc))
    except FileNotFoundError:
        fail("log file not found: %s" % path)
    except OSError as exc:
        fail("cannot read log %s: %s" % (path, exc))
    return records


def cmd_append(args):
    try:
        round_no = int(str(args.round))
    except ValueError:
        fail("--round must be an integer")
    points = parse_json_arg(args.points_json, "--points-json")
    results = parse_json_arg(args.results_json, "--results-json")
    criteria = parse_json_arg(args.criteria_json, "--criteria-json")
    if not isinstance(points, list):
        fail("--points-json must be a JSON list (use [] when empty)")
    if not isinstance(results, list):
        fail("--results-json must be a JSON list (use [] when empty)")
    if criteria is None:
        criteria = {}
    if not isinstance(criteria, dict):
        fail("--criteria-json must be a JSON object")
    import os
    existing = read_log(args.log) if os.path.exists(args.log) else []
    seq = (existing[-1].get("seq", 0) if existing and
           isinstance(existing[-1], dict) else 0) + 1
    record = {
        "seq": seq,
        "round": round_no,
        "points": points,
        "results": results,
        "results_digest": results_digest(results),
        "decision": str(args.decision),
        "criterion_states": criteria,
    }
    try:
        with open(args.log, "a", encoding="utf-8") as fh:
            fh.write(canonical_json(record) + "\n")
    except OSError as exc:
        fail("cannot append to log %s: %s" % (args.log, exc))
    sys.stdout.write(json.dumps({"status": "ok", "seq": seq},
                                ensure_ascii=False) + "\n")
    return 0


def load_results_csv(path):
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                fail("results CSV %s has no header" % path)
            rows = []
            for raw in reader:
                row = {}
                for k, v in raw.items():
                    if k is None:
                        continue
                    try:
                        row[k] = float(v)
                    except (TypeError, ValueError):
                        row[k] = v
                rows.append(row)
            return rows
    except FileNotFoundError:
        fail("results CSV not found: %s" % path)
    except OSError as exc:
        fail("cannot read results CSV %s: %s" % (path, exc))


def row_matches(snapshot_row, csv_row):
    for key, val in snapshot_row.items():
        if key not in csv_row:
            return False
        other = csv_row[key]
        if isinstance(val, float) or isinstance(other, float):
            try:
                if float(val) != float(other):
                    return False
            except (TypeError, ValueError):
                return False
        elif val != other:
            return False
    return True


def cmd_verify(args):
    records = read_log(args.log)
    problems = []
    checked = 0
    expected_seq = 1
    for i, rec in enumerate(records):
        lineno = i + 1
        if not isinstance(rec, dict):
            problems.append("line %d: record is not a JSON object" % lineno)
            continue
        for field in ("seq", "round", "points", "results", "results_digest",
                      "decision", "criterion_states"):
            if field not in rec:
                problems.append("line %d: missing field '%s'" % (lineno, field))
        seq = rec.get("seq")
        if not isinstance(seq, int) or seq != expected_seq:
            problems.append("line %d: seq %r, expected %d (monotonic from 1)"
                            % (lineno, seq, expected_seq))
            expected_seq = seq + 1 if isinstance(seq, int) else expected_seq + 1
        else:
            expected_seq = seq + 1
        rows = rec.get("results")
        digest = rec.get("results_digest")
        if isinstance(rows, list) and isinstance(digest, str):
            actual = results_digest(rows)
            if actual != digest:
                problems.append(
                    "line %d: results_digest mismatch (recorded %s, recomputed "
                    "%s) -- log entry or results were tampered with"
                    % (lineno, digest, actual))
        checked += 1
    cross = None
    if args.results:
        csv_rows = load_results_csv(args.results)
        missing = 0
        for rec in records:
            if not isinstance(rec, dict):
                continue
            for snap in rec.get("results") or []:
                if not any(row_matches(snap, r) for r in csv_rows):
                    missing += 1
        cross = {"results_csv": args.results,
                 "snapshot_rows_missing_from_csv": missing}
        if missing:
            problems.append("%d snapshot row(s) no longer appear in %s"
                            % (missing, args.results))
    report = {
        "schema_version": VERSION,
        "log": args.log,
        "records_checked": checked,
        "seq_monotonic_from_1": not any("seq" in p for p in problems),
        "digests_consistent": not any("digest mismatch" in p for p in problems),
        "cross_check": cross,
        "problems": problems,
        "status": "pass" if not problems else "fail",
    }
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as exc:
            fail("cannot write report %s: %s" % (args.output, exc))
    sys.stdout.write(text)
    return 0 if not problems else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="append-only decision log tool")
    sub = ap.add_subparsers(dest="mode", required=True)
    pa = sub.add_parser("append", help="append one decision record")
    pa.add_argument("--log", required=True)
    pa.add_argument("--round", required=True)
    pa.add_argument("--points-json", required=True)
    pa.add_argument("--results-json", required=True)
    pa.add_argument("--decision", required=True)
    pa.add_argument("--criteria-json", default=None)
    pa.set_defaults(func=cmd_append)
    pv = sub.add_parser("verify", help="replay and verify the log")
    pv.add_argument("--log", required=True)
    pv.add_argument("--results", default=None,
                    help="optional results CSV for cross-checking")
    pv.add_argument("--output", default=None, help="write JSON report here")
    pv.set_defaults(func=cmd_verify)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # last-resort guard: never leak a traceback
        fail("unexpected error: %s: %s" % (type(exc).__name__, exc), code=2)
