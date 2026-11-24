#!/usr/bin/env python3
"""diff_runs.py -- Twin-pass reconciliation and idempotence verifier.

Compares the artifact triple (cleaned.csv, ledger.csv, summary.json)
produced by engine_row.py (--a) and engine_col.py (--b):

  * cleaned.csv  -- cell by cell (header + every data cell)
  * ledger.csv   -- record by record (raw line equality)
  * summary.json -- leaf by leaf over the union of flattened key paths

Zero divergences -> twin_pass_verdict.json verdict=PASS, exit 0.
Any divergence  -> verdict=FAIL plus reconciliation_queue.csv listing every
divergent cell as:
    artifact, row, field, engine_a_value, engine_a_reason,
    engine_b_value, engine_b_reason
where the "reason" columns are filled from each engine's own ledger.csv
entries for the affected src_row/field ("-" when the ledger is silent),
so the agent can judge spec ambiguity vs engine defect without re-running.

With --idempotence, engine A is re-run once into a scratch directory and
its three artifacts must be byte-identical to the reference run (--a);
this guards against hidden state, dict-order or filesystem-order leaks.

Usage:
    python3 diff_runs.py --a OUT_ROW --b OUT_COL --outdir DIFFDIR \
        [--idempotence --engine ENGINE_ROW --rules RULES --csv NORMCSV]

Exit codes:
    0  PASS (reconciliation clean and, when requested, idempotence clean)
    6  divergence found, or idempotence check failed
"""

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile

EXIT_PASS = 0
EXIT_DIVERGED = 6

ARTIFACTS = ("cleaned.csv", "ledger.csv", "summary.json")
QUEUE_HEADER = ["artifact", "row", "field", "engine_a_value", "engine_a_reason",
                "engine_b_value", "engine_b_reason"]


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def read_csv(path):
    text = read_text(path)
    if text is None:
        return None
    rows = list(csv.reader(text.splitlines()))
    return rows


def load_ledger(dirpath):
    rows = read_csv(os.path.join(dirpath, "ledger.csv"))
    if not rows or len(rows) < 2:
        return []
    return rows[1:]  # skip header


def reason_from_ledger(ledger_rows, src_row, field):
    """Explain a cleaned.csv divergence from the engine's own ledger."""
    if src_row is None:
        return "-"
    hits = [r for r in ledger_rows if len(r) >= 6 and r[1] == src_row]
    if not hits:
        return "-"
    by_field = [r for r in hits if r[2] == field]
    chosen = by_field or hits
    return " | ".join("%s:%s" % (r[0], r[4]) for r in chosen)


def compare_cleaned(dir_a, dir_b, queue):
    rows_a = read_csv(os.path.join(dir_a, "cleaned.csv"))
    rows_b = read_csv(os.path.join(dir_b, "cleaned.csv"))
    if rows_a is None or rows_b is None:
        queue.append(["cleaned.csv", "-", "(file)",
                      "<present>" if rows_a is not None else "<missing>", "-",
                      "<present>" if rows_b is not None else "<missing>", "-"])
        return
    ledger_a = load_ledger(dir_a)
    ledger_b = load_ledger(dir_b)
    head_a = rows_a[0] if rows_a else []
    head_b = rows_b[0] if rows_b else []
    if head_a != head_b:
        for pos in range(max(len(head_a), len(head_b))):
            va = head_a[pos] if pos < len(head_a) else "<absent>"
            vb = head_b[pos] if pos < len(head_b) else "<absent>"
            if va != vb:
                queue.append(["cleaned.csv", "0", "(header col %d)" % pos, va, "-", vb, "-"])
    data_a = rows_a[1:]
    data_b = rows_b[1:]
    width = max(len(head_a), len(head_b))
    for r in range(max(len(data_a), len(data_b))):
        ra = data_a[r] if r < len(data_a) else None
        rb = data_b[r] if r < len(data_b) else None
        src_a = ra[0] if ra and len(ra) > 0 else None
        src_b = rb[0] if rb and len(rb) > 0 else None
        if ra is None or rb is None:
            queue.append(["cleaned.csv", str(r + 1), "(row)",
                          "<absent>" if ra is None else ",".join(ra),
                          reason_from_ledger(ledger_a, src_a, ""),
                          "<absent>" if rb is None else ",".join(rb),
                          reason_from_ledger(ledger_b, src_b, "")])
            continue
        for c in range(width):
            va = ra[c] if c < len(ra) else "<absent>"
            vb = rb[c] if c < len(rb) else "<absent>"
            if va != vb:
                field = head_a[c] if c < len(head_a) else "(col %d)" % c
                queue.append(["cleaned.csv", str(r + 1), field, va,
                              reason_from_ledger(ledger_a, src_a, field),
                              vb, reason_from_ledger(ledger_b, src_b, field)])


def compare_ledger(dir_a, dir_b, queue):
    text_a = read_text(os.path.join(dir_a, "ledger.csv"))
    text_b = read_text(os.path.join(dir_b, "ledger.csv"))
    if text_a is None or text_b is None:
        queue.append(["ledger.csv", "-", "(file)",
                      "<present>" if text_a is not None else "<missing>", "-",
                      "<present>" if text_b is not None else "<missing>", "-"])
        return
    lines_a = text_a.splitlines()
    lines_b = text_b.splitlines()
    for i in range(max(len(lines_a), len(lines_b))):
        la = lines_a[i] if i < len(lines_a) else "<absent>"
        lb = lines_b[i] if i < len(lines_b) else "<absent>"
        if la != lb:
            queue.append(["ledger.csv", str(i), "(row)", la, "-", lb, "-"])


def flatten(obj, prefix=""):
    out = {}
    if isinstance(obj, dict):
        for k in sorted(obj):
            out.update(flatten(obj[k], "%s.%s" % (prefix, k) if prefix else k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(flatten(v, "%s[%d]" % (prefix, i)))
    else:
        out[prefix] = obj
    return out


def compare_summary(dir_a, dir_b, queue):
    text_a = read_text(os.path.join(dir_a, "summary.json"))
    text_b = read_text(os.path.join(dir_b, "summary.json"))
    if text_a is None or text_b is None:
        queue.append(["summary.json", "-", "(file)",
                      "<present>" if text_a is not None else "<missing>", "-",
                      "<present>" if text_b is not None else "<missing>", "-"])
        return
    try:
        flat_a = flatten(json.loads(text_a))
    except json.JSONDecodeError as exc:
        queue.append(["summary.json", "-", "(parse)", "<invalid json: %s>" % exc, "-", "-", "-"])
        return
    try:
        flat_b = flatten(json.loads(text_b))
    except json.JSONDecodeError as exc:
        queue.append(["summary.json", "-", "(parse)", "-", "-", "<invalid json: %s>" % exc, "-"])
        return
    for path in sorted(set(flat_a) | set(flat_b)):
        va = flat_a.get(path, "<absent>")
        vb = flat_b.get(path, "<absent>")
        if va != vb:
            queue.append(["summary.json", "-", path,
                          json.dumps(va, ensure_ascii=False), "-",
                          json.dumps(vb, ensure_ascii=False), "-"])


def run_idempotence(engine, rules, csv_path, ref_dir, outdir):
    """Re-run engine A once; its artifacts must byte-match the reference."""
    result = {"status": "PASS", "engine": engine, "rules": rules, "csv": csv_path,
              "files": list(ARTIFACTS), "mismatches": []}
    scratch = tempfile.mkdtemp(prefix="idempotence_", dir=outdir)
    try:
        proc = subprocess.run(
            [sys.executable, engine, "--rules", rules, "--csv", csv_path, "--outdir", scratch],
            capture_output=True, text=True)
        if proc.returncode != 0:
            result["status"] = "FAIL"
            result["mismatches"].append(
                {"file": "(rerun)", "detail": "engine exited %d: %s"
                 % (proc.returncode, proc.stderr.strip()[:500])})
            return result
        for name in ARTIFACTS:
            ref = read_text(os.path.join(ref_dir, name))
            new = read_text(os.path.join(scratch, name))
            if ref != new:
                result["status"] = "FAIL"
                result["mismatches"].append(
                    {"file": name,
                     "detail": "byte mismatch between reference run and re-run"
                     if ref is not None and new is not None else "file missing on one side"})
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="Twin-pass reconciliation / idempotence.")
    ap.add_argument("--a", required=True, help="engine A output directory")
    ap.add_argument("--b", required=True, help="engine B output directory")
    ap.add_argument("--outdir", required=True, help="where verdict + queue are written")
    ap.add_argument("--idempotence", action="store_true",
                    help="also re-run engine A and demand byte-identical artifacts")
    ap.add_argument("--engine", help="path to engine_row.py (required with --idempotence)")
    ap.add_argument("--rules", help="path to rules.json (required with --idempotence)")
    ap.add_argument("--csv", help="path to normalized csv (required with --idempotence)")
    args = ap.parse_args(argv)

    if args.idempotence and not (args.engine and args.rules and args.csv):
        sys.stderr.write("diff_runs: --idempotence requires --engine, --rules and --csv\n")
        return EXIT_DIVERGED

    os.makedirs(args.outdir, exist_ok=True)

    queue = []
    compare_cleaned(args.a, args.b, queue)
    compare_ledger(args.a, args.b, queue)
    compare_summary(args.a, args.b, queue)

    by_artifact = {name: 0 for name in ARTIFACTS}
    for row in queue:
        by_artifact[row[0]] = by_artifact.get(row[0], 0) + 1

    case_id = None
    summary_text = read_text(os.path.join(args.a, "summary.json"))
    if summary_text is not None:
        try:
            case_id = json.loads(summary_text).get("case_id")
        except json.JSONDecodeError:
            case_id = None

    if args.idempotence:
        idem = run_idempotence(args.engine, args.rules, args.csv, args.a, args.outdir)
    else:
        idem = {"status": "SKIPPED"}

    recon_status = "PASS" if not queue else "FAIL"
    verdict = "PASS" if (recon_status == "PASS" and idem["status"] in ("PASS", "SKIPPED")) else "FAIL"

    queue_path = os.path.join(args.outdir, "reconciliation_queue.csv")
    with open(queue_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(QUEUE_HEADER)
        w.writerows(queue)

    verdict_doc = {
        "tool": "diff_runs.py",
        "case_id": case_id,
        "inputs": {"engine_a_dir": args.a, "engine_b_dir": args.b},
        "reconciliation": {
            "status": recon_status,
            "divergences": len(queue),
            "by_artifact": by_artifact,
            "queue_file": "reconciliation_queue.csv",
        },
        "idempotence": idem,
        "verdict": verdict,
        "policy": "no delivery while verdict is FAIL; resolve divergence in rules.json "
                  "(spec ambiguity) or in one engine (defect), then re-run BOTH engines",
    }
    verdict_path = os.path.join(args.outdir, "twin_pass_verdict.json")
    with open(verdict_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(verdict_doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    print("diff_runs: reconciliation=%s divergences=%d idempotence=%s verdict=%s -> %s"
          % (recon_status, len(queue), idem["status"], verdict, verdict_path))
    return EXIT_PASS if verdict == "PASS" else EXIT_DIVERGED


if __name__ == "__main__":
    sys.exit(main())
