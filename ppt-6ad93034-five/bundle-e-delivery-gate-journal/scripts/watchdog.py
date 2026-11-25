#!/usr/bin/env python3
"""watchdog.py — owns /app/output/result.json so that ANY kill point leaves a
valid, honest result.

Commands:
  watchdog.py init --case /input/case.json
      Run BEFORE any real work. Immediately writes result.json with the
      original case_id, every output_contract root field with type-correct
      placeholders, status "partial".
  watchdog.py advance --stage NAME [--set-json 'k=<json>']... [--exception "..."]...
      Merge updates after a stage. Paths recorded in editable_source /
      export_artifact / content_map must exist on disk — nonexistent paths
      are REFUSED. status stays "partial".
  watchdog.py finalize --status success|partial
      "success" is refused unless gate-plan/gate-build/gate-render all PASS.

The watchdog never fabricates: it records only what it can verify.
"""
import argparse
import datetime
import json
import os
import sys

WORK_DIR = os.environ.get("CASE_WORK_DIR", "/app/work")
OUTPUT_DIR = os.environ.get("CASE_OUTPUT_DIR", "/app/output")
RESULT_PATH = os.path.join(OUTPUT_DIR, "result.json")

DEFAULT_CONTRACT = ["status", "editable_source", "export_artifact",
                    "content_map", "compliance_checks", "exceptions"]
PATH_KEYS = {"editable_source", "export_artifact"}
GATE_STAGES = ("plan", "build", "render")


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def placeholder_for(value):
    """Type-correct empty placeholder mirroring the contract value's type."""
    if isinstance(value, bool):
        return False
    if isinstance(value, list):
        return []
    if isinstance(value, dict):
        return {}
    return None  # str, number, null


def load_result():
    if not os.path.isfile(RESULT_PATH):
        print("watchdog: ERROR result.json does not exist; run `watchdog.py init` first", file=sys.stderr)
        sys.exit(1)
    with open(RESULT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_result(result):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    result["updated_utc"] = utc_now()
    tmp = RESULT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    os.replace(tmp, RESULT_PATH)


def cmd_init(args):
    with open(args.case, "r", encoding="utf-8") as f:
        case = json.load(f)
    case_id = case.get("case_id") or case.get("id") or "unknown"
    contract = case.get("output_contract")
    fields = list(contract.keys()) if isinstance(contract, dict) and contract else DEFAULT_CONTRACT
    result = {}
    for key in fields:
        if key == "status":
            result["status"] = "partial"
        else:
            result[key] = placeholder_for(contract.get(key)) if isinstance(contract, dict) else None
    if "status" not in result:
        result["status"] = "partial"
    result["case_id"] = case_id
    result["stage"] = "initialized"
    if "synthetic_example" in case:
        result["synthetic_example"] = case["synthetic_example"]
    save_result(result)
    print(f"watchdog: result.json initialized (case_id={case_id}, status=partial) — "
          f"valid honest result now exists at every future kill point")
    return 0


def resolve_existing(path):
    """Return the path if it names an existing file, else None."""
    for cand in (path, os.path.join(OUTPUT_DIR, path), os.path.join(os.getcwd(), path)):
        if os.path.isfile(cand):
            return path
    return None


def cmd_advance(args):
    result = load_result()
    for pair in args.set_json or []:
        if "=" not in pair:
            print(f"watchdog: ERROR malformed --set-json {pair!r} (expected k=<json>)", file=sys.stderr)
            return 1
        key, raw = pair.split("=", 1)
        key = key.strip()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw  # tolerate bare strings
        if key in PATH_KEYS:
            if value is not None and resolve_existing(str(value)) is None:
                print(f"watchdog: REFUSED — {key} path does not exist: {value}", file=sys.stderr)
                return 1
        elif key == "content_map" and isinstance(value, dict):
            for k, v in value.items():
                if isinstance(v, str) and resolve_existing(v) is None:
                    print(f"watchdog: REFUSED — content_map[{k!r}] path does not exist: {v}", file=sys.stderr)
                    return 1
        result[key] = value
    for exc in args.exception or []:
        exs = result.get("exceptions")
        if not isinstance(exs, list):
            exs = []
        exs.append(exc)
        result["exceptions"] = exs
    result["stage"] = args.stage
    result["status"] = "partial"  # status stays partial until finalize
    save_result(result)
    print(f"watchdog: advanced to stage={args.stage} (status=partial)")
    return 0


def cmd_finalize(args):
    result = load_result()
    if args.status == "success":
        failed = []
        for stage in GATE_STAGES:
            gp = os.path.join(WORK_DIR, f"gate-{stage}.json")
            verdict = None
            if os.path.isfile(gp):
                try:
                    with open(gp, "r", encoding="utf-8") as f:
                        verdict = json.load(f).get("verdict")
                except Exception:
                    verdict = None
            if verdict != "PASS":
                failed.append(f"{stage}={verdict or 'missing'}")
        if failed:
            print(f"watchdog: REFUSED to write status=success — gates not all PASS: "
                  f"{', '.join(failed)}. Finalize as partial instead.", file=sys.stderr)
            return 1
    result["status"] = args.status
    result["stage"] = "finalized"
    result["finalized_utc"] = utc_now()
    save_result(result)
    print(f"watchdog: finalized status={args.status}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="result.json watchdog/state machine")
    sub = ap.add_subparsers(dest="command", required=True)
    ip = sub.add_parser("init")
    ip.add_argument("--case", required=True)
    adv = sub.add_parser("advance")
    adv.add_argument("--stage", required=True)
    adv.add_argument("--set-json", action="append", default=[])
    adv.add_argument("--exception", action="append", default=[])
    fp = sub.add_parser("finalize")
    fp.add_argument("--status", required=True, choices=["success", "partial"])
    args = ap.parse_args()
    return {"init": cmd_init, "advance": cmd_advance, "finalize": cmd_finalize}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
