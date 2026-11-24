#!/usr/bin/env python3
"""run_demo.py -- end-to-end SYNTHETIC demonstration of search-strategist.

Reproduces everything under examples/synthetic-output/:

  1. plan_search.py        -> search_plan.json
  2. loop: next_batch.py   -> next_batch_seq<N>.json (EMIT batches)
           oracle.py       -> results.csv            (synthetic "experiments")
     until STOP or the safety iteration cap
  3. search_log.py verify  -> verify_report.json     (replay passes)
  4. tampered log + verify -> verify_tampered.json   (replay FAILS, exit 1)
  5. plan_search.py rerun  -> determinism_check.json (byte-identical)
  6. result.json           -> the challenge output contract, honestly filled

The oracle is a synthetic hidden response surface (quadratic + small
deterministic noise); see examples/README.md.  Pure standard library.
"""

import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IN = os.path.join(HERE, "synthetic-input")
OUT = os.path.join(HERE, "synthetic-output")
SCRIPTS = os.path.join(ROOT, "scripts")

ARTIFACTS = ["search_plan.json", "search_plan_rerun.json", "results.csv",
             "decision_log.jsonl", "tampered_log.jsonl", "verify_report.json",
             "verify_tampered.json", "determinism_check.json", "result.json"]


def run(cmd, expect=None):
    proc = subprocess.run([sys.executable] + cmd,
                          capture_output=True, text=True)
    if expect is not None and proc.returncode != expect:
        raise RuntimeError("command %s exited %d (expected %d)\n%s\n%s"
                           % (cmd, proc.returncode, expect,
                              proc.stdout, proc.stderr))
    if "Traceback" in proc.stderr:
        raise RuntimeError("traceback leaked from %s\n%s" % (cmd, proc.stderr))
    return proc


def main():
    os.makedirs(OUT, exist_ok=True)
    for name in os.listdir(OUT):
        if name in ARTIFACTS or name.startswith("next_batch_seq"):
            os.remove(os.path.join(OUT, name))

    with open(os.path.join(IN, "budget.json"), encoding="utf-8") as fh:
        cfg = json.load(fh)
    with open(os.path.join(IN, "case.json"), encoding="utf-8") as fh:
        case = json.load(fh)

    plan_path = os.path.join(OUT, "search_plan.json")
    results = os.path.join(OUT, "results.csv")
    log = os.path.join(OUT, "decision_log.jsonl")

    # 1. plan ---------------------------------------------------------------
    run([os.path.join(SCRIPTS, "plan_search.py"),
         "--space", os.path.join(IN, "param_space.json"),
         "--budget", str(cfg["budget"]),
         "--history", str(cfg["history_points"]),
         "--seed", str(cfg["seed"]),
         "--output", plan_path], expect=0)
    with open(plan_path, encoding="utf-8") as fh:
        plan = json.load(fh)
    print("[1] plan: strategy=%s rounds=%d"
          % (plan["strategy"], len(plan["rounds"])))

    # 2. sequential loop -----------------------------------------------------
    decisions = []
    for it in range(1, 25):
        dpath = os.path.join(OUT, "next_batch_seq%d.json" % it)
        run([os.path.join(SCRIPTS, "next_batch.py"),
             "--plan", plan_path, "--results", results,
             "--log", log, "--output", dpath], expect=0)
        with open(dpath, encoding="utf-8") as fh:
            decision = json.load(fh)
        decisions.append(decision)
        print("[2.%d] %s: %s" % (it, decision["status"],
                                 decision["rationale"][:90]))
        if decision["status"] == "STOP":
            break
        run([os.path.join(IN, "oracle.py"),
             "--points", dpath, "--round", str(decision["next_round"]),
             "--csv", results], expect=0)

    # 3. verify the untouched log -------------------------------------------
    run([os.path.join(SCRIPTS, "search_log.py"), "verify",
         "--log", log, "--results", results,
         "--output", os.path.join(OUT, "verify_report.json")], expect=0)
    print("[3] verify: pass")

    # 4. tamper one digest, verify must fail ---------------------------------
    tampered = os.path.join(OUT, "tampered_log.jsonl")
    shutil.copyfile(log, tampered)
    with open(tampered, encoding="utf-8") as fh:
        lines = fh.readlines()
    rec = json.loads(lines[0])
    d = rec["results_digest"]
    rec["results_digest"] = ("0" if d[0] != "0" else "1") + d[1:]
    lines[0] = json.dumps(rec, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False) + "\n"
    with open(tampered, "w", encoding="utf-8") as fh:
        fh.writelines(lines)
    proc = run([os.path.join(SCRIPTS, "search_log.py"), "verify",
                "--log", tampered,
                "--output", os.path.join(OUT, "verify_tampered.json")],
               expect=1)
    print("[4] tampered verify: exit=%d (digest mismatch caught)" %
          proc.returncode)

    # 5. determinism: same seed -> byte-identical plan -----------------------
    rerun = os.path.join(OUT, "search_plan_rerun.json")
    run([os.path.join(SCRIPTS, "plan_search.py"),
         "--space", os.path.join(IN, "param_space.json"),
         "--budget", str(cfg["budget"]),
         "--history", str(cfg["history_points"]),
         "--seed", str(cfg["seed"]),
         "--output", rerun], expect=0)
    with open(plan_path, "rb") as fh:
        a = fh.read()
    with open(rerun, "rb") as fh:
        b = fh.read()
    det = {"seed": cfg["seed"], "runs_compared": 2,
           "byte_identical": a == b,
           "status": "pass" if a == b else "fail"}
    with open(os.path.join(OUT, "determinism_check.json"), "w",
              encoding="utf-8") as fh:
        json.dump(det, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("[5] determinism rerun: byte_identical=%s" % (a == b))

    # 6. result.json per the challenge output contract -----------------------
    final = decisions[-1]
    best = final.get("best_point") or {}
    contract = case.get("output_contract", [])
    payload = {
        "case_id": case.get("case_id"),
        "status": "success" if final["status"] == "STOP" else "partial",
        "sources": [
            "examples/synthetic-input/param_space.json",
            "examples/synthetic-input/budget.json",
            "examples/synthetic-input/oracle.py (SYNTHETIC oracle, not real data)",
            "examples/synthetic-output/search_plan.json",
            "examples/synthetic-output/decision_log.jsonl",
            "examples/synthetic-output/verify_report.json",
        ],
        "uncertainty": (
            "All responses come from a synthetic oracle (quadratic surface + "
            "+/-0.005 deterministic noise); the recommended optimum is "
            "evidence about the WORKFLOW, not about any real process. Noise "
            "estimate from confirmation repeats is based on >=2 replicates "
            "only."),
        "change_log": [
            "plan_search.py emitted strategy '%s' with %d round(s)"
            % (plan["strategy"], len(plan["rounds"])),
            "next_batch.py made %d decision(s); final: %s (%s)"
            % (len(decisions), final["status"],
               final.get("stop_criterion") or "n/a"),
            "search_log.py verify: pass; tampered replay: caught (exit 1)",
            "determinism rerun: byte_identical=%s" % (a == b),
        ],
    }
    if "experiment_plan" in contract:
        payload["experiment_plan"] = {
            "strategy": plan["strategy"],
            "strategy_rationale": plan["strategy_rationale"],
            "seed": plan["seed"],
            "budget": plan["budget"],
            "rounds": [{"round": r["round"], "name": r["name"],
                        "n_points": r["n_points"]} for r in plan["rounds"]],
            "stop": {"criterion": final.get("stop_criterion"),
                     "rationale": final["rationale"]},
            "recommended_point": best,
        }
    if "evidence_and_risk" in contract:
        payload["evidence_and_risk"] = {
            "decisions_logged": len(decisions),
            "log_verified": True,
            "tamper_detection": "verify on tampered_log.jsonl exits 1 with a "
                                "digest mismatch (verify_tampered.json)",
            "determinism": det,
            "risks": [
                "LHS screening with %d points can miss a narrow optimum "
                "region" % plan["rounds"][0]["n_points"],
                "2% relative-improvement threshold may stop early on plateaus",
                "synthetic oracle: real noise, drift and constraints absent",
            ],
        }
    if "confirmation_items" in contract:
        payload["confirmation_items"] = [
            "re-run plan_search.py with seed %d; expect byte-identical plan"
            % plan["seed"],
            "re-run search_log.py verify on decision_log.jsonl; expect pass",
            "repeat the recommended best point >= 2 times with real "
            "measurements before trusting the noise estimate",
        ]
    missing = [k for k in contract if k not in payload]
    if missing:
        payload["status"] = "partial"
        payload["change_log"].append("missing contract fields: %s" % missing)
    with open(os.path.join(OUT, "result.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("[6] result.json written (status=%s)" % payload["status"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
