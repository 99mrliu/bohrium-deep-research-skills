#!/usr/bin/env python3
"""Run the independent SYNTHETIC example and one semantic-header failure test."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

LABEL = "SYNTHETIC EXAMPLE — never official results"


def main():
    example_dir = Path(__file__).resolve().parent
    root = example_dir.parents[1]
    runtime = root / "scripts" / "runtime.py"
    output_dir = example_dir / "output"
    work_dir = example_dir / "work"
    failure_work = example_dir / "failure-work"
    failure_output = example_dir / "failure-output"
    for path in (output_dir, work_dir, failure_work, failure_output):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)

    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    def relative(path):
        return str(path.relative_to(root))

    def execute(bindings, work, output):
        command = [sys.executable, relative(runtime),
                   "--input-dir", relative(example_dir),
                   "--work-dir", relative(work), "--output-dir", relative(output)]
        if bindings:
            command += ["--bindings", relative(bindings)]
        printable = shlex.join(["python3"] + command[1:])
        completed = subprocess.run(command, cwd=root, env=env, text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        return printable, completed

    first_command, first = execute(None, work_dir, output_dir)
    if first.returncode != 0:
        raise RuntimeError("Geometry pass failed:\n" + first.stdout + first.stderr)
    first_result = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
    assert first_result["status"] == "partial"
    assert all(row["status"] == "extraction_failed" and row["scalar"] is None
               for row in first_result["result"]["fields"])

    final_bindings = example_dir / "curated-cell-bindings.json"
    final_command, final = execute(final_bindings, work_dir, output_dir)
    if final.returncode != 0:
        raise RuntimeError("Curated pass failed:\n" + final.stdout + final.stderr)
    result = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
    assert result["case_id"] == "SYNTHETIC-EXAMPLE-NOT-OFFICIAL"
    assert result["status"] == "answered"
    assert result["result"]["example_label"] == LABEL
    fields = result["result"]["fields"]
    assert len(fields) == 3 and len({row["field_id"] for row in fields}) == 3
    assert [row["status"] for row in fields] == ["reported", "reported", "not_reported"]
    assert fields[0]["scalar"] == "42.0" and fields[0]["units"] == "%"
    assert fields[1]["scalar"] == "51.3" and fields[1]["units"] == "%"
    assert fields[0]["experimental_condition"] == fields[0]["condition"]
    assert "24 h" in fields[0]["experimental_condition"]
    assert "24 h" in fields[1]["experimental_condition"]
    assert fields[1]["evidence"][0]["page"] == 2
    assert len(fields[1]["evidence"][0]["location"]["column_header_cell_ids"]) == 2
    assert fields[2]["scalar"] is None and fields[2]["evidence"] == []
    assert fields[2]["experimental_condition"] == fields[2]["condition"]
    assert "80 °C" in fields[2]["condition"] and "24 h" in fields[2]["condition"]
    markdown = (output_dir / "table-preview.md").read_text(encoding="utf-8")
    assert LABEL in markdown and "s001-seg002-r02-c03" in markdown
    svg_text = (output_dir / "table-preview.svg").read_text(encoding="utf-8")
    assert LABEL in svg_text and "<text" in svg_text
    ET.fromstring(svg_text)

    # Meaningful negative case: the scalar and cell ID remain valid, but the
    # reviewer drops the timing qualifier. Exact header verification must reject it.
    invalid = json.loads(final_bindings.read_text(encoding="utf-8"))
    invalid["label"] = LABEL + " — deliberate header-mismatch failure test"
    invalid["bindings"] = copy.deepcopy(invalid["bindings"])
    invalid["bindings"][0]["expected_column_header_text"][0] = "Yield (%)"
    invalid_path = failure_work / "invalid-header-bindings.json"
    invalid_path.write_text(json.dumps(invalid, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failure_command, failure = execute(invalid_path, failure_work, failure_output)
    assert failure.returncode == 2, failure.stdout + failure.stderr
    assert "column header text differs" in failure.stderr
    assert "no candidate answer was promoted" in failure.stderr
    failure_result = json.loads((failure_output / "result.json").read_text(encoding="utf-8"))
    assert failure_result["status"] == "partial"
    assert all(row["status"] == "extraction_failed" and row["scalar"] is None
               for row in failure_result["result"]["fields"])
    assert any(item.get("kind") == "binding_rejected" for item in failure_result["uncertainties"])

    observation = (LABEL + "\nCommand: " + failure_command +
                   "\nExit code: " + str(failure.returncode) +
                   "\nObserved rejection: " + failure.stderr.strip() +
                   "\nAll three failure-output scalar values remained null.\n")
    (output_dir / "failure-observation.txt").write_text(observation, encoding="utf-8")
    summary = {
        "example_label": LABEL,
        "commands": [first_command, final_command, failure_command],
        "geometry_pass_exit": first.returncode,
        "curated_pass_exit": final.returncode,
        "failure_test_exit": failure.returncode,
        "observations": [
            "Geometry-only pass preserved three null scalars with partial status.",
            "Curated pass emitted exactly three unique fields: reported, reported, not_reported.",
            "Page-2 value retained two effective yield-header cells and explicit condition evidence.",
            "Markdown and SVG text previews contained the synthetic label and stable cell IDs; SVG parsed as XML.",
            "Dropping 'at 24 h' from the expected header caused exit 2 and no value promotion."
        ],
        "result": "examples/minimal/output/result.json",
        "failure_result": "examples/minimal/failure-output/result.json"
    }
    (output_dir / "test-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
