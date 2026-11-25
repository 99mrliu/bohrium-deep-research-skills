#!/usr/bin/env python3
"""Real end-to-end synthetic validation outside the text-only bundle.

Copies the case into challenge-scoped validation/source-surgery/<case_id>,
renders its source PNG, invokes the actual CLI with explicit scoped mirrors of
/app/work and /app/output, and mirrors deliverables to validation/<case_id>/output.
Failure cases assert non-zero + atomic rollback.
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
SURGERY = HERE / "source_surgery.py"
BASE_ID = "source-surgery__figure03_source__figure03__source-preserving"
FAIL_MODES = {"missing-id": "failed-missing-id", "duplicate-id": "failed-duplicate-id"}
CHALLENGE = HERE.parents[2]
SCOPED_VALIDATION = CHALLENGE / "validation" / "source-surgery"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate_png(svg: Path, png: Path) -> None:
    import pymupdf
    with pymupdf.open(svg) as d:
        png.write_bytes(d[0].get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False).tobytes("png"))


def invoke(case: Path, work: Path, output: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SURGERY), "run", "--case-root", str(case), "--work", str(work), "--output", str(output)], text=True, capture_output=True)


def mirror(output: Path, validation_case: Path) -> None:
    dst = validation_case / "output"
    if dst.exists():
        shutil.rmtree(dst)
    if output.exists():
        shutil.copytree(output, dst)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--validation-root", type=Path, default=SCOPED_VALIDATION)
    ap.add_argument("--app-output", type=Path, default=SCOPED_VALIDATION / "runtime" / "app" / "output" / "source-surgery")
    ap.add_argument("--app-work", type=Path, default=SCOPED_VALIDATION / "runtime" / "app" / "work" / "source-surgery")
    args = ap.parse_args()
    root = args.validation_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    report = {"synthetic": True, "cases": []}

    # Success: case-local originals; no global source/template directory.
    for case_id, mode in [(BASE_ID, None)] + [(BASE_ID.replace("source-preserving", m), m) for m in FAIL_MODES.values()]:
        case = root / case_id / "input" / "case"
        if case.parent.parent.exists():
            shutil.rmtree(case.parent.parent)
        shutil.copytree(FIXTURE, case)
        generate_png(case / "input" / "source.svg", case / "input" / "figure03.png")
        if mode:
            cj = case / "input" / "case.json"
            cfg = json.loads(cj.read_text(encoding="utf-8"))
            cfg["case_id"] = cfg["composite_id"] = case_id
            cfg["asset"]["mode"] = mode
            # All output path declarations carry the dynamic case_id.
            def replace_ids(value):
                if isinstance(value, dict):
                    return {k: replace_ids(v) for k, v in value.items()}
                if isinstance(value, list):
                    return [replace_ids(v) for v in value]
                return value.replace(BASE_ID, case_id) if isinstance(value, str) else value
            cfg = replace_ids(cfg)
            cj.write_text(json.dumps(cfg, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            if mode == "failed-missing-id":
                wp = case / "input" / "source_surgery" / "workorder.json"
                order = json.loads(wp.read_text(encoding="utf-8"))
                order["operations"][0]["id"] = "does-not-exist"
                text = json.dumps(order, indent=2, sort_keys=True) + "\n"
                wp.write_text(text, encoding="utf-8")
                (case / "input" / "workorder.json").write_text(text, encoding="utf-8")
            else:
                sp = case / "input" / "source.svg"
                sp.write_text(sp.read_text(encoding="utf-8").replace('id="node-c"', 'id="node-a"'), encoding="utf-8")
        output = args.app_output.resolve() if mode is None else args.app_output.resolve() / "failures" / case_id
        work = args.app_work.resolve() / case_id
        if work.exists():
            shutil.rmtree(work)
        source = case / "input" / "source.svg"
        before = digest(source)
        proc = invoke(case, work, output)
        entry = {"case_id": case_id, "command": " ".join(proc.args), "exit_code": proc.returncode, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip(), "source_sha256_before": before, "source_sha256_after": digest(source), "case_root": str(case), "output": str(output)}
        if mode is None:
            assert proc.returncode == 0, entry
            cfg = json.loads((case / "input" / "case.json").read_text(encoding="utf-8"))
            result = json.loads((output / cfg["output_contract"]["result"]).read_text(encoding="utf-8"))
            assert result["case_id"] == case_id and result["status"] == "partial"
            for key, relative in cfg["output_contract"]["asset_paths"].items():
                p = output / relative
                assert p.is_file() and p.stat().st_size > 0, (key, p)
                assert result[key] == str(p), (key, result[key], str(p))
            assert result["result_file_pointer"] == str(output / cfg["output_contract"]["result"])
            unchanged = json.loads((output / cfg["output_contract"]["unchanged_elements"]).read_text(encoding="utf-8"))
            assert unchanged["unchanged_element_count"] > 0
            entry.update({"status": result["status"], "visual_review": "pending native inspection + attest", "unchanged_element_count": unchanged["unchanged_element_count"], "changed_ids": sorted({x["id"] for x in result["change_record_details"]})})
        else:
            assert proc.returncode != 0, entry
            cfg = json.loads((case / "input" / "case.json").read_text(encoding="utf-8"))
            for key in ("edited_svg", "edited_png", "edited_pdf"):
                assert not (output / cfg["output_contract"][key]).exists(), (case_id, key)
            failed_result = json.loads((output / cfg["output_contract"]["result"]).read_text(encoding="utf-8"))
            assert failed_result["status"] == "failed" and failed_result["transaction_committed"] is False
            assert digest(source) == before
            entry.update({"atomic_failure_verified": True, "final_edited_absent": True})
        mirror(output, root / case_id)
        report["cases"].append(entry)

    # Make a discovery manifest for the three case-local runs (not a shared source).
    cases = [{"case_id": e["case_id"], "path": str(root / e["case_id"] / "input" / "case")} for e in report["cases"]]
    (root / "case_manifest.json").write_text(json.dumps({"layout": "validation/<case_id>/input/case/{input/...,task.md}", "cases": cases}, indent=2) + "\n", encoding="utf-8")
    report["result"] = "PASS: success artifacts real; both invalid-ID cases failed atomically; source success remains partial until actual visual attestation"
    (root / "validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
