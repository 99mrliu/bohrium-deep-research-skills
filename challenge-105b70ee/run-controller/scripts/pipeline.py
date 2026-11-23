#!/usr/bin/env python3
"""Staged pipeline controller (run-controller skill).

Stages: orient -> extract -> bank -> skeleton -> [adjudicate gate: human/
model work, closed by `pipeline.py mark adjudicate`] -> finalize.

Deterministic stages run via workers.py/finalize.py next to this file.
Each stage writes state/<stage>.json (timestamp, duration, outputs) and
appends one line to run.log. Reruns skip completed stages unless --force.
Any abort after `skeleton` leaves a valid honest-partial result.json.

Usage:
  pipeline.py run  --input-dir D --work-dir W --output R [--stage S] [--force]
                   [--text-file F]
  pipeline.py status --work-dir W
  pipeline.py mark <stage> --work-dir W [--note "..."]

Exit codes: 0 ok; 1 stage failed (see run.log); 2 bad usage/input.
"""
import argparse
import json
import os
import subprocess
import sys
import time

STAGES = ["orient", "extract", "bank", "skeleton", "adjudicate", "finalize"]
HERE = os.path.dirname(os.path.abspath(__file__))


def state_path(work, stage):
    return os.path.join(work, "state", "%s.json" % stage)


def log(work, msg):
    os.makedirs(work, exist_ok=True)
    with open(os.path.join(work, "run.log"), "a", encoding="utf-8") as f:
        f.write("%s %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%S"), msg))


def done(work, stage):
    return os.path.isfile(state_path(work, stage))


def record(work, stage, t0, extra):
    os.makedirs(os.path.join(work, "state"), exist_ok=True)
    data = {"stage": stage, "finished": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "duration_s": round(time.time() - t0, 2)}
    data.update(extra)
    with open(state_path(work, stage), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log(work, "stage %s done (%s)" % (stage, extra.get("summary", "ok")))


def run_stage(stage, a):
    t0 = time.time()
    work = a.work_dir
    if stage == "orient":
        case_p = os.path.join(a.input_dir, "case.json")
        if not os.path.isfile(case_p):
            log(work, "orient FAILED: case.json missing")
            print("orient: /input/case.json missing", file=sys.stderr)
            return 1
        case = json.load(open(case_p, encoding="utf-8"))
        tf_p = os.path.join(a.input_dir, "target-fields.json")
        fields = []
        if os.path.isfile(tf_p):
            tf = json.load(open(tf_p, encoding="utf-8"))
            fields = [f["field_id"] for f in tf.get("fields", [])]
        pdfs = [f for f in os.listdir(a.input_dir) if f.lower().endswith(".pdf")]
        record(work, "orient", t0, {
            "case_id": case.get("case_id"), "fields": fields, "pdfs": pdfs,
            "contract_keys": sorted((case.get("output_contract") or {}).keys()),
            "summary": "%d fields, pdfs=%s" % (len(fields), pdfs)})
        return 0
    if stage == "extract":
        orient = json.load(open(state_path(work, "orient"), encoding="utf-8"))
        pdfs = orient.get("pdfs") or []
        main = [p for p in pdfs if not any(
            k in p.lower() for k in ("supp", "_si", "mmc", "extdata"))]
        cmd = [sys.executable, os.path.join(HERE, "workers.py"), "extract",
               "--work-dir", work]
        if a.text_file:
            cmd += ["--text-file", a.text_file]
        elif main:
            cmd += ["--pdf", os.path.join(a.input_dir, main[0])]
            for si in [p for p in pdfs if p not in main]:
                cmd += ["--si", os.path.join(a.input_dir, si)]
        else:
            log(work, "extract FAILED: no pdf and no --text-file")
            print("extract: no PDF in /input and no --text-file", file=sys.stderr)
            return 1
        r = subprocess.run(cmd, capture_output=True, text=True)
        log(work, "extract: %s" % (r.stdout.strip() or r.stderr.strip()))
        if r.returncode != 0:
            print(r.stderr.strip(), file=sys.stderr)
            return 1
        record(work, "extract", t0, {"summary": r.stdout.strip()})
        return 0
    if stage == "bank":
        r = subprocess.run([sys.executable, os.path.join(HERE, "workers.py"),
                            "bank", "--work-dir", work],
                           capture_output=True, text=True)
        log(work, "bank: %s" % r.stdout.strip())
        if r.returncode != 0:
            print(r.stderr.strip(), file=sys.stderr)
            return 1
        record(work, "bank", t0, {"summary": r.stdout.strip()})
        return 0
    if stage == "skeleton":
        orient = json.load(open(state_path(work, "orient"), encoding="utf-8"))
        case = json.load(open(os.path.join(a.input_dir, "case.json"),
                              encoding="utf-8"))
        result = {
            "case_id": case.get("case_id"),
            "status": "partial",
            "result": {"field_results": [
                {"field_id": f, "status": "not_reported", "scalar": None,
                 "units": None, "statistic": None, "condition": None,
                 "comparator": None, "quote": None, "page": None,
                 "notes": "skeleton: not yet adjudicated"}
                for f in orient.get("fields", [])]},
            "claims": [], "uncertainties": [],
        }
        for k in (case.get("output_contract") or {}):
            result.setdefault(k, None)
        os.makedirs(os.path.dirname(os.path.abspath(a.output)), exist_ok=True)
        with open(a.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        record(work, "skeleton", t0,
               {"summary": "honest partial: %d fields not_reported"
                % len(orient.get("fields", []))})
        return 0
    if stage == "finalize":
        r = subprocess.run([sys.executable, os.path.join(HERE, "finalize.py"),
                            "--result", a.output, "--work-dir", work],
                           capture_output=True, text=True)
        sys.stdout.write(r.stdout)
        if r.returncode != 0:
            log(work, "finalize FAILED: %s" % r.stdout.strip().splitlines()[-1]
                if r.stdout.strip() else "contract violation")
            return 1
        record(work, "finalize", t0, {"summary": "contract ok, status set"})
        return 0
    return 2


def cmd_run(a):
    os.makedirs(a.work_dir, exist_ok=True)
    log(a.work_dir, "run start (output=%s)" % a.output)
    targets = [a.stage] if a.stage else STAGES
    for st in targets:
        if st == "adjudicate":
            if not done(a.work_dir, st):
                print("GATE: adjudicate pending — do field work, then: "
                      "pipeline.py mark adjudicate --work-dir %s" % a.work_dir)
                if not a.stage:
                    return 0  # stop here; rerun after marking
                return 2
            continue
        if done(a.work_dir, st) and not a.force:
            continue
        rc = run_stage(st, a)
        if rc != 0:
            print("stage %s failed — see %s/run.log" % (st, a.work_dir),
                  file=sys.stderr)
            return 1
    print("pipeline: done (%s)" % ",".join(
        s for s in targets if s != "adjudicate"))
    return 0


def cmd_status(a):
    for st in STAGES:
        p = state_path(a.work_dir, st)
        if os.path.isfile(p):
            d = json.load(open(p, encoding="utf-8"))
            print("%-11s done   %s  %s" % (st, d.get("finished"),
                                           d.get("summary", "")))
        else:
            print("%-11s PENDING" % st)
    return 0


def cmd_mark(a):
    if a.stage_name not in STAGES:
        print("unknown stage %s" % a.stage_name, file=sys.stderr)
        return 2
    record(a.work_dir, a.stage_name, time.time(),
           {"summary": "marked: %s" % (a.note or "done"), "manual": True})
    print("marked %s" % a.stage_name)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("--input-dir", required=True)
    p.add_argument("--work-dir", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--stage", choices=[s for s in STAGES if s != "adjudicate"])
    p.add_argument("--force", action="store_true")
    p.add_argument("--text-file")
    p = sub.add_parser("status")
    p.add_argument("--work-dir", required=True)
    p = sub.add_parser("mark")
    p.add_argument("stage_name")
    p.add_argument("--work-dir", required=True)
    p.add_argument("--note")
    a = ap.parse_args()
    return {"run": cmd_run, "status": cmd_status, "mark": cmd_mark}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
