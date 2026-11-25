#!/usr/bin/env python3
"""Stdlib smoke tests for initialization, source grounding, and both examples."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def invoke(args, expected=0):
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != expected:
        raise AssertionError(f"Unexpected exit {result.returncode}: {args}\n{result.stdout}\n{result.stderr}")
    return result


def main():
    examples = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_examples.py")], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    print(examples.stdout, end="")
    if examples.returncode != 0:
        raise AssertionError(f"Example runner failed:\n{examples.stdout}\n{examples.stderr}")
    with tempfile.TemporaryDirectory(prefix="claim-evidence-smoke-") as temporary:
        base = Path(temporary)
        inputs = base / "input"
        work = base / "work"
        output = base / "output"
        inputs.mkdir()
        minimal = ROOT / "examples" / "minimal"
        for name in ("case.json", "target-fields.json", "task.md", "source.txt"):
            (inputs / name).write_text((minimal / name).read_text(encoding="utf-8"), encoding="utf-8")
        invoke([sys.executable, str(ROOT / "scripts" / "prepare_case.py"), "--input", str(inputs), "--work", str(work), "--output", str(output)])
        early = json.loads((output / "result.json").read_text(encoding="utf-8"))
        sources = json.loads((work / "sources.json").read_text(encoding="utf-8"))
        assert early["status"] == "partial" and len(early["result"]["fields"]) == 4
        assert all(field["status"] == "extraction_failed" and field["scalar"] is None for field in early["result"]["fields"])
        assert sources["sources"] and sources["sources"][0]["paragraphs"]

        damaged = json.loads((minimal / "output" / "result.json").read_text(encoding="utf-8"))
        damaged["result"]["fields"][0]["evidence"][0]["quote"] = "INVENTED QUOTATION"
        damaged["result"]["field_results"] = damaged["result"]["fields"]
        bad_result = base / "bad-result.json"
        bad_result.write_text(json.dumps(damaged), encoding="utf-8")
        checked = invoke([
            sys.executable, str(ROOT / "scripts" / "validate_result.py"), "--result", str(bad_result),
            "--graph", str(minimal / "output" / "graph.json"), "--targets", str(minimal / "target-fields.json"),
            "--sources", str(minimal / "source.paragraphs.json"),
        ], expected=2)
        assert "quotation is not a verbatim substring" in checked.stderr
    print("PREPARE_CASE SMOKE TEST PASSED: early honest partial and registered source paragraphs")
    print("INVENTED-QUOTE TEST PASSED: altered quotation rejected")
    print("ALL SELF_TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
