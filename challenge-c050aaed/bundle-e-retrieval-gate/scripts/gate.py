#!/usr/bin/env python3
"""Pre-delivery quality gate for a reading-annotation work product.

Machine-checks the whole result before it ships and FORCES status="partial"
in result.json when any check fails, so an unfinished result can never
masquerade as complete.

Checks:
  1. contract_completeness — result.json exists, its case_id matches the case,
     and every field named by the case's output_contract is present (parsed
     dynamically; if output_contract is absent that fact is recorded and only
     case_id is checked).
  2. artifact_integrity — every artifact referenced by result.json's
     "artifacts" map ({name: {path, sha256}}) exists under --output-dir and its
     recorded sha256 matches the file on disk.
  3. verification_rates — every *verify*/claims JSON report in --output-dir
     meets thresholds: anchors verified/total >= --min-anchor-rate (default
     0.95) with zero 'failed'; notes claims verified == total. No report found
     is a failure.
  4. retrieval_smoke — each known-item query in --smoke-queries is run against
     the index; must_find_id must appear in the top 5. A query with
     must_find_id: null is a negative control and must return zero hits.
  5. replay_determinism — build_index is re-run from the input paths recorded
     in the index meta and the result is byte-compared with the shipped index.

Writes gate_report.json {checks:[{name,pass,detail}], verdict, failed}.
Exit codes: 0 all pass; 3 at least one check failed (result.json rewritten to
status="partial" with the failed check names appended to its
uncertainty/limitations field, all other fields preserved); 2 usage error.
"""
import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_index import build, dump_index  # noqa: E402
import query as qmod  # noqa: E402

SMOKE_TOP_K = 5


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def check_contract(case, output_dir):
    result_path = os.path.join(output_dir, "result.json")
    if not os.path.isfile(result_path):
        return {"name": "contract_completeness", "pass": False,
                "detail": "result.json missing in output dir"}, None
    try:
        with open(result_path, encoding="utf-8") as fh:
            result = json.load(fh)
    except json.JSONDecodeError as exc:
        return {"name": "contract_completeness", "pass": False,
                "detail": f"result.json is not valid JSON: {exc}"}, None

    problems, notes = [], []
    case_id = case.get("case_id", case.get("id"))
    if case_id is None:
        notes.append("case.json has no case_id field; case_id match skipped")
    elif result.get("case_id") != case_id:
        problems.append(f"case_id mismatch: result.json has "
                        f"{result.get('case_id')!r}, case has {case_id!r}")

    contract = case.get("output_contract")
    if contract is None:
        notes.append("case.json has no output_contract; checked case_id only")
    else:
        if isinstance(contract, list):
            fields = contract
        elif isinstance(contract, dict):
            fields = contract.get("fields", list(contract))
        else:
            fields = [str(contract)]
        missing = [f for f in fields if f not in result]
        if missing:
            problems.append("missing output_contract field(s): " + ", ".join(missing))
        else:
            notes.append(f"all {len(fields)} output_contract field(s) present: "
                         + ", ".join(fields))

    return {"name": "contract_completeness", "pass": not problems,
            "detail": "; ".join(problems + notes) or "ok"}, result


def check_artifacts(result, output_dir):
    artifacts = (result or {}).get("artifacts")
    if not artifacts:
        return {"name": "artifact_integrity", "pass": True,
                "detail": "result.json references no artifacts; nothing to hash-check"}
    problems, ok = [], []
    for name in sorted(artifacts):
        entry = artifacts[name]
        rel, want = entry.get("path"), (entry.get("sha256") or "").lower()
        full = os.path.join(output_dir, rel or "")
        if not rel or not os.path.isfile(full):
            problems.append(f"{name}: missing file {rel!r}")
            continue
        got = sha256_file(full)
        if got != want:
            problems.append(f"{name}: sha256 mismatch for {rel} "
                            f"(recorded {want[:12]}…, actual {got[:12]}…)")
        else:
            ok.append(name)
    detail = []
    if ok:
        detail.append(f"verified {len(ok)} artifact(s): " + ", ".join(ok))
    detail += problems
    return {"name": "artifact_integrity", "pass": not problems,
            "detail": "; ".join(detail)}


def check_verification(output_dir, min_anchor_rate):
    reports = sorted(f for f in os.listdir(output_dir)
                     if f.lower().endswith(".json")
                     and ("verif" in f.lower() or "claims" in f.lower()))
    if not reports:
        return {"name": "verification_rates", "pass": False,
                "detail": "no *verify*/claims report found in output dir"}
    problems, details = [], []
    for fname in reports:
        try:
            with open(os.path.join(output_dir, fname), encoding="utf-8") as fh:
                rep = json.load(fh)
        except json.JSONDecodeError as exc:
            problems.append(f"{fname}: invalid JSON: {exc}")
            continue
        anchors = rep.get("anchors")
        claims = rep.get("notes_claims", rep.get("claims"))
        if anchors is None and claims is None:
            problems.append(f"{fname}: unrecognized schema (need 'anchors' and/or "
                            f"'notes_claims' with total/verified/failed)")
            continue
        if anchors is not None:
            total = anchors.get("total", 0)
            verified = anchors.get("verified", 0)
            failed = anchors.get("failed", 0)
            rate = verified / total if total else 1.0
            if rate < min_anchor_rate or failed != 0:
                problems.append(f"{fname}: anchor rate {rate:.3f} "
                                f"(need >= {min_anchor_rate}), failed={failed} (need 0)")
            else:
                details.append(f"{fname}: anchors {verified}/{total} = {rate:.3f}, "
                               f"failed=0")
        if claims is not None:
            total = claims.get("total", 0)
            verified = claims.get("verified", 0)
            if verified != total:
                problems.append(f"{fname}: note claims {verified}/{total} verified "
                                f"(need 1.0)")
            else:
                details.append(f"{fname}: note claims {verified}/{total} = 1.0")
    return {"name": "verification_rates", "pass": not problems,
            "detail": "; ".join(details + problems)}


def check_smoke(smoke_path, idx):
    with open(smoke_path, encoding="utf-8") as fh:
        smoke = json.load(fh)
    queries = smoke.get("queries", smoke) if isinstance(smoke, dict) else smoke
    problems, details = [], []
    for i, entry in enumerate(queries, 1):
        qtext = entry.get("q")
        must = entry.get("must_find_id")
        results = qmod.search(idx, q=qtext, tag=entry.get("tag"),
                              type_=entry.get("type"), file=entry.get("file"),
                              since=entry.get("since"), until=entry.get("until"))
        top_ids = [doc_id for doc_id, _ in results[:SMOKE_TOP_K]]
        label = f"smoke[{i}] q={qtext!r}"
        if must is None:
            if results:
                problems.append(f"{label}: negative control returned {len(results)} "
                                f"hit(s), expected zero")
            else:
                details.append(f"{label}: negative control ok (zero hits)")
        elif must in top_ids:
            details.append(f"{label}: {must} found at rank "
                           f"{top_ids.index(must) + 1}")
        else:
            problems.append(f"{label}: {must} not in top-{SMOKE_TOP_K} "
                            f"(top: {top_ids or 'none'})")
    return {"name": "retrieval_smoke", "pass": not problems,
            "detail": "; ".join(details + problems)}


def check_determinism(index_path):
    with open(index_path, "rb") as fh:
        shipped = fh.read()
    idx = json.loads(shipped.decode("utf-8"))
    inputs = idx.get("meta", {}).get("inputs") or {}
    stored = {k: v for k, v in inputs.items() if v}
    if not stored:
        return {"name": "replay_determinism", "pass": False,
                "detail": "index meta records no input paths; cannot replay"}

    index_dir = os.path.dirname(os.path.abspath(index_path))
    candidates = [os.getcwd(), index_dir, os.path.dirname(index_dir)]
    base = None
    for cand in candidates:
        if all(os.path.isfile(os.path.join(cand, p)) for p in stored.values()):
            base = cand
            break
    if base is None:
        return {"name": "replay_determinism", "pass": False,
                "detail": "original input files not found relative to cwd, the "
                          "index dir, or its parent; cannot replay"}

    prev = os.getcwd()
    try:
        os.chdir(base)  # rebuild with the stored path strings so bytes match
        rebuilt = build(stored.get("annotations"), stored.get("notes"),
                        stored.get("inventory"))
    finally:
        os.chdir(prev)
    if dump_index(rebuilt).encode("utf-8") == shipped:
        return {"name": "replay_determinism", "pass": True,
                "detail": f"rebuilt index is byte-identical (replayed from {base})"}
    return {"name": "replay_determinism", "pass": False,
            "detail": "rebuilt index differs byte-for-byte from shipped index.json "
                      "(index is stale, hand-edited, or tampered)"}


def force_partial(result, output_dir, failed_names):
    note = "gate failed checks: " + ", ".join(failed_names)
    result["status"] = "partial"
    for key in ("uncertainty", "limitations"):
        if key in result:
            v = result[key]
            if isinstance(v, list):
                v.append(note)
            elif isinstance(v, str):
                result[key] = (v + "; " + note) if v else note
            else:
                result[key] = [note]
            break
    else:
        result["uncertainty"] = [note]
    result_path = os.path.join(output_dir, "result.json")
    with open(result_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Pre-delivery quality gate: audit result.json, artifacts, "
                    "verification rates, retrieval smoke tests, and replay "
                    "determinism; force status=partial on any failure.")
    ap.add_argument("--case", required=True, help="path to case.json")
    ap.add_argument("--output-dir", required=True, help="dir containing result.json")
    ap.add_argument("--index", required=True, help="shipped index.json")
    ap.add_argument("--smoke-queries", required=True,
                    help="smoke.json with known-item queries [{q, must_find_id}]")
    ap.add_argument("--out", required=True, help="gate_report.json output path")
    ap.add_argument("--min-anchor-rate", type=float, default=0.95,
                    help="minimum anchors verified rate (default 0.95)")
    args = ap.parse_args(argv)

    for label, p in [("--case", args.case), ("--index", args.index),
                     ("--smoke-queries", args.smoke_queries)]:
        if not os.path.isfile(p):
            die(f"{label}: file not found: {p}")
    if not os.path.isdir(args.output_dir):
        die(f"--output-dir: not a directory: {args.output_dir}")
    try:
        with open(args.case, encoding="utf-8") as fh:
            case = json.load(fh)
    except json.JSONDecodeError as exc:
        die(f"{args.case}: invalid JSON: {exc}")
    idx = qmod.load_index(args.index)

    def guarded(name, fn, *fn_args):
        try:
            return fn(*fn_args)
        except Exception as exc:  # a crashed check is a failed check
            return {"name": name, "pass": False,
                    "detail": f"check raised {type(exc).__name__}: {exc}"}

    checks = []
    contract_check, result = check_contract(case, args.output_dir)
    checks.append(contract_check)
    checks.append(guarded("artifact_integrity", check_artifacts,
                          result, args.output_dir))
    checks.append(guarded("verification_rates", check_verification,
                          args.output_dir, args.min_anchor_rate))
    checks.append(guarded("retrieval_smoke", check_smoke,
                          args.smoke_queries, idx))
    checks.append(guarded("replay_determinism", check_determinism, args.index))

    failed = [c["name"] for c in checks if not c["pass"]]
    verdict = "pass" if not failed else "fail"
    report = {"checks": checks, "verdict": verdict, "failed": failed}
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    for c in checks:
        print(f"[{'PASS' if c['pass'] else 'FAIL'}] {c['name']}: {c['detail']}")
    print(f"verdict: {verdict} -> {args.out}")

    if failed:
        if result is not None:
            force_partial(result, args.output_dir, failed)
            print("result.json rewritten: status=partial, failed checks appended "
                  "to uncertainty/limitations")
        else:
            print("result.json absent/unparseable; nothing to rewrite")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
