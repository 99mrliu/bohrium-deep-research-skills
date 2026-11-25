#!/usr/bin/env python3
"""Regenerate and test both synthetic examples, including rejected promotion."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "scripts" / "build_graph.py"
VALIDATE = ROOT / "scripts" / "validate_result.py"


def run(command, expect=0):
    completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if completed.returncode != expect:
        raise RuntimeError(f"Command returned {completed.returncode}, expected {expect}: {command}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}")
    return completed


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def regenerate(example):
    prefix = ROOT / "examples" / example
    output = prefix / "output"
    common = ["--case", str(prefix / "case.json"), "--targets", str(prefix / "target-fields.json"), "--sources", str(prefix / "source.paragraphs.json")]
    print(run([sys.executable, str(BUILD), *common, "--curated", str(prefix / "curated.json"), "--output", str(output)]).stdout, end="")
    print(run([sys.executable, str(VALIDATE), "--result", str(output / "result.json"), "--graph", str(output / "graph.json"), "--targets", str(prefix / "target-fields.json"), "--sources", str(prefix / "source.paragraphs.json"), "--report", str(output / "validation.json")]).stdout, end="")
    return load(output / "result.json"), load(output / "graph.json"), load(output / "validation.json")


def main():
    minimal, minimal_graph, minimal_report = regenerate("minimal")
    assert len(minimal["result"]["fields"]) == 4
    assert minimal["result"]["fields"][0]["scalar"] == 82
    assert minimal["result"]["fields"][0]["experimental_condition"] == minimal["result"]["fields"][0]["condition"]
    assert minimal["result"]["fields"][2]["status"] == "not_reported"
    assert minimal["status"] == "answered"
    hypothesis = next(claim for claim in minimal["claims"] if claim["claim_id"] == "CL-HYP")
    assert hypothesis["kind"] == "hypothesis_speculation" and "may" in hypothesis["hedges"]
    assert not any(edge["type"] == "grounded_in" and "quote" not in edge["evidence"] for edge in minimal_graph["edges"])

    negative, _, negative_report = regenerate("negative")
    assert negative["status"] == "insufficient_evidence"
    assert negative["result"]["fields"][0]["status"] == "not_reported"
    assert negative["result"]["fields"][0]["scalar"] is None
    assert all(claim["kind"] != "author_conclusion" for claim in negative["claims"])

    prefix = ROOT / "examples" / "negative"
    with tempfile.TemporaryDirectory(prefix="claim-evidence-negative-") as temporary:
        completed = run([
            sys.executable, str(BUILD), "--case", str(prefix / "case.json"), "--targets", str(prefix / "target-fields.json"),
            "--sources", str(prefix / "source.paragraphs.json"), "--curated", str(prefix / "invalid-promotion.json"),
            "--output", temporary,
        ], expect=2)
        assert "NEGATIVE-PROMOTION-GUARD" in completed.stderr
        assert not (Path(temporary) / "result.json").exists()
        (prefix / "expected-error.txt").write_text(completed.stderr, encoding="utf-8")
    print("NEGATIVE TEST PASSED: cited hedged claim promotion rejected before output generation")
    print("ALL SYNTHETIC EXAMPLE TESTS PASSED")
    print(json.dumps({"minimal": minimal_report, "negative": negative_report}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
