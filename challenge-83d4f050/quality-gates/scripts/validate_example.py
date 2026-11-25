#!/usr/bin/env python3
"""Exercise real stages, failure/resume, scientific exit codes and determinism.

All binaries live outside the text-only bundle under validation/quality-gates.
No network, Git, shared source, or privileged /app path is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
FIXTURE = HERE.parent / "examples" / "synthetic_case"
RUNNER = HERE / "runner.py"
CHALLENGE = HERE.parents[2]
SCOPED = CHALLENGE / "validation" / "quality-gates"
APP_OUT = SCOPED / "runtime" / "app" / "output" / "quality-gates"
APP_WORK = SCOPED / "runtime" / "app" / "work" / "quality-gates"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def call(case: Path, work: Path, out: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(RUNNER), "run", "--case-root", str(case), "--work", str(work), "--output", str(out), *extra], text=True, capture_output=True)


def contract(case: Path) -> dict:
    return json.loads((case / "input" / "case.json").read_text(encoding="utf-8"))["output_contract"]


def file_fingerprints(out: Path) -> dict[str, str]:
    return {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()}


def entry(proc: subprocess.CompletedProcess) -> dict:
    return {"command": " ".join(proc.args), "exit_code": proc.returncode, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--validation-root", type=Path, default=SCOPED)
    ap.add_argument("--app-output", type=Path, default=APP_OUT)
    ap.add_argument("--app-work", type=Path, default=APP_WORK)
    args = ap.parse_args()
    root = args.validation_root.resolve()
    report = {"synthetic": True, "tests": []}

    def prepare(name: str) -> Path:
        case = root / name / "input" / "case"
        if case.parent.parent.exists():
            shutil.rmtree(case.parent.parent)
        shutil.copytree(FIXTURE, case)
        return case

    # Success and byte-for-byte repeat on a fresh work directory, same case/output.
    success_case = prepare("success")
    work = args.app_work.resolve() / "success"
    out = args.app_output.resolve()
    if work.exists():
        shutil.rmtree(work)
    first = call(success_case, work, out)
    e = entry(first)
    assert first.returncode == 0, e
    oc = contract(success_case)
    result = json.loads((out / oc["result"]).read_text(encoding="utf-8"))
    manifest = json.loads((out / oc["run_manifest"]).read_text(encoding="utf-8"))
    assert result["status"] == "partial" and manifest["current_stage"] == "audited"
    assert manifest["completed_stages"] == ["observed", "specified", "rendered", "exported", "audited"]
    audit = json.loads((out / oc["audit"]).read_text(encoding="utf-8"))
    assert audit["passed"] and audit["svg"]["edge_count"] == 3
    assert any(x["relation"] == "feedback_inhibition" for x in audit["svg"]["edges"])
    assert any(x["uncertain"] == "true" for x in audit["svg"]["edges"])
    fingerprints = file_fingerprints(out)
    e.update({"status": "partial_pending_native_visual_attestation", "completed_stages": manifest["completed_stages"], "artifact_count": len(fingerprints)})
    shutil.rmtree(work)
    second = call(success_case, work, out)
    repeat = entry(second)
    assert second.returncode == 0, repeat
    repeated = file_fingerprints(out)
    assert repeated == fingerprints, {"different": [k for k in fingerprints if fingerprints[k] != repeated.get(k)], "added": sorted(set(repeated) - set(fingerprints)), "removed": sorted(set(fingerprints) - set(repeated))}
    e["deterministic_repeat"] = repeat
    e["deterministic_byte_equality"] = True
    report["tests"].append({"name": "success_and_determinism", **e})

    # Two independent contract failures must be non-zero, then repair/resume.
    for name, injection in (("missing-png", "missing-png"), ("missing-result-field", "missing-result-field")):
        case = prepare(name)
        w = args.app_work.resolve() / name
        o = args.app_output.resolve() / "failures" / name
        if w.exists():
            shutil.rmtree(w)
        if o.exists():
            shutil.rmtree(o)
        failed = call(case, w, o, "--inject-failure", injection)
        record = {"name": name, "failed_run": entry(failed)}
        assert failed.returncode == 3, record
        failed_result = json.loads((o / contract(case)["result"]).read_text(encoding="utf-8"))
        assert failed_result["status"] == "failed" and failed_result["error"]["kind"] == "contract"
        failed_manifest = json.loads((o / contract(case)["run_manifest"]).read_text(encoding="utf-8"))
        assert failed_manifest["status"] == "failed" and "exported" in failed_manifest["completed_stages"]
        failed_mirror = root / name / "output_failed"
        if failed_mirror.exists():
            shutil.rmtree(failed_mirror)
        shutil.copytree(o, failed_mirror)
        resumed = call(case, w, o, "--resume")
        record["resume"] = entry(resumed)
        assert resumed.returncode == 0, record
        oc = contract(case)
        resumed_result = json.loads((o / oc["result"]).read_text(encoding="utf-8"))
        assert resumed_result["status"] == "partial"
        for key in oc["asset_paths"]:
            assert (o / oc[key]).is_file() and (o / oc[key]).stat().st_size > 0, (name, key)
        if injection == "missing-png":
            assert len(json.loads((o / oc["recovery"]).read_text(encoding="utf-8"))) >= 1
        record["recovered_stage"] = "audited"
        record["honest_status"] = "partial_pending_native_visual_attestation"
        recovered_mirror = root / name / "output"
        if recovered_mirror.exists():
            shutil.rmtree(recovered_mirror)
        shutil.copytree(o, recovered_mirror)
        report["tests"].append(record)

    # Scientific rejection is deliberately distinct from contract failure.
    science_case = prepare("scientific-failure")
    review_path = science_case / "input" / "scientific_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["verdict"] = "fail"
    review_path.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
    science = call(science_case, args.app_work.resolve() / "scientific-failure", args.app_output.resolve() / "failures" / "scientific-failure")
    science_entry = {"name": "scientific-failure", **entry(science)}
    assert science.returncode == 4, science_entry
    report["tests"].append(science_entry)

    # Mirror the canonical successful outputs to validation/<name>/output.
    dst = root / "success" / "output"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(out, dst)
    report["visual_attestation"] = "Still pending: native Agent must inspect actual success PNG/PDF and run runner.py attest with current hashes."
    report["result"] = "PASS: deterministic artifacts, missing-PNG and missing-field failures/resume, and distinct scientific exit 4"
    root.mkdir(parents=True, exist_ok=True)
    (root / "validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
