#!/usr/bin/env python3
"""End-to-end synthetic and failure checks; standard library only."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

MARKER = "SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE"
ARTIFACTS = ("cleaned.csv", "cleaned.json", "changes.jsonl", "review_queue.csv", "evidence.jsonl", "audit.md", "result.json")


def invoke(root, input_dir, work, output, case=None, task=None):
    command = [
        "python3", str(root / "scripts" / "evidence_adjudicator.py"),
        "--input", str(input_dir), "--work", str(work), "--output", str(output),
    ]
    if case is not None:
        command.extend(["--case", str(case)])
    if task is not None:
        command.extend(["--task", str(task)])
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def pointer_value(value, pointer):
    target = value
    for part in pointer.split("/")[1:]:
        part = part.replace("~1", "/").replace("~0", "~")
        target = target[int(part)] if isinstance(target, list) else target[part]
    return target


def validate_anchor(anchor, input_dir):
    source = input_dir / anchor["source"]
    if anchor["kind"] == "text_substring":
        text = source.read_text(encoding="utf-8")
        assert text[anchor["start"]:anchor["end"]] == anchor["exact_substring"]
        assert anchor["line"] >= 1 and anchor["column"] >= 1
    elif anchor["kind"] == "csv_cell":
        with source.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle))
        assert rows[anchor["row_number"] - 1][rows[0].index(anchor["column"])] == anchor["exact_substring"]
    elif anchor["kind"] == "json_pointer":
        value = pointer_value(json.loads(source.read_text(encoding="utf-8")), anchor["json_pointer"])
        assert anchor["serialized_value"] == json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    elif anchor["kind"] == "pdf_page_substring":
        assert anchor["page"] >= 1 and anchor["end"] >= anchor["start"]
    else:
        raise AssertionError("Unknown anchor kind: " + str(anchor.get("kind")))


def validate_example(root):
    output = root / "examples" / "synthetic-output"
    input_dir = root / "examples" / "synthetic-input"
    first = invoke(root, input_dir, output / ".work", output)
    assert first.returncode == 0, first.stderr
    hashes = {name: digest(output / name) for name in ARTIFACTS}
    second = invoke(root, input_dir, output / ".work", output)
    assert second.returncode == 0, second.stderr
    assert hashes == {name: digest(output / name) for name in ARTIFACTS}, "Outputs differ on deterministic rerun"
    if (output / ".work").is_dir():
        (output / ".work").rmdir()

    for name in ARTIFACTS:
        text = (output / name).read_text(encoding="utf-8")
        assert MARKER in text, name + " lacks synthetic marker"
    with (output / "cleaned.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert len(reader.fieldnames) == len(set(reader.fieldnames)), "Duplicate output CSV header"
        rows = list(reader)
    assert len(rows) == 1
    row = rows[0]
    assert row["melting_point_K"] == "181", "Conflict was silently replaced"
    assert row["extractor_note"] == "a note", "Authorized normalization missing"
    assert row["unsupported_label"] == "speculative-blue", "Unsupported value was removed or guessed"
    assert row["unknown_unit"] == ""
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert result["case_id"] == "SYNTHETIC-EVIDENCE-001"
    assert result["status"] == "partial"
    assert result["official_score"] is None and "official_score" in result["unresolved_fields"]
    assert result["summary"]["total_claims"] == 7
    assert result["summary"]["source_conflict"] == 1
    for key in ("sources", "uncertainty", "change_records", "change_log", "review_queue", "artifacts"):
        assert key in result
    for reference in result["artifacts"].values():
        assert (output / reference).is_file()

    claims = parse_jsonl(output / "evidence.jsonl")
    counts = {state: sum(claim["state"] == state for claim in claims) for state in ("corroborated", "source_conflict", "extractor_only", "unverifiable")}
    assert counts == {"corroborated": 4, "source_conflict": 1, "extractor_only": 1, "unverifiable": 1}, counts
    conflict = next(claim for claim in claims if claim["field_path"] == "/melting_point_K")
    assert conflict["observed_value"] == "181" and conflict["source_value"] is None
    assert any(item["value"] == "182" and item["anchor"]["row_number"] == 2 for item in conflict["conflicts"])
    for claim in claims:
        assert claim["field_type"] in ("string", "integer", "number", "boolean", "null")
        for anchor in claim["support_anchors"] + claim["missing_or_unusable_anchors"] + [item["anchor"] for item in claim["conflicts"]]:
            validate_anchor(anchor, input_dir)
    with (output / "review_queue.csv").open(encoding="utf-8", newline="") as handle:
        review = list(csv.DictReader(handle))
    assert {item["state"] for item in review} == {"source_conflict", "extractor_only", "unverifiable"}
    assert len(parse_jsonl(output / "changes.jsonl")) == 1
    json.loads((output / "cleaned.json").read_text(encoding="utf-8"))
    print("PASS synthetic outputs, anchors, states, CSV readability, contract, deterministic rerun")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def failure_checks(root, parent):
    # Valid case, but no independent evidence: nonempty claims must be unverifiable.
    missing = parent / "missing-evidence"
    inp = missing / "input"
    inp.mkdir(parents=True)
    write_json(inp / "case.json", {
        "example_marker": MARKER, "case": {"case_id": "SYNTHETIC-MISSING-EVIDENCE"},
        "output_contract": ["case_id", "status", "required_unknown"],
    })
    (inp / "task.md").write_text(MARKER + "\nAdjudicate extracted.json with no independent materials.\n", encoding="utf-8")
    write_json(inp / "extracted.json", {
        "example_marker": MARKER,
        "records": [{"example_marker": MARKER, "sample_id": "NO-EVIDENCE-1", "measurement": "unsupported-712"}],
    })
    completed = invoke(root, inp, missing / "work", missing / "output")
    assert completed.returncode == 0, completed.stderr
    result = json.loads((missing / "output" / "result.json").read_text(encoding="utf-8"))
    assert result["case_id"] == "SYNTHETIC-MISSING-EVIDENCE" and result["status"] == "partial"
    assert result["required_unknown"] is None and "required_unknown" in result["unresolved_fields"]
    claims = parse_jsonl(missing / "output" / "evidence.jsonl")
    measurement = next(claim for claim in claims if claim["field_path"] == "/measurement")
    assert measurement["state"] == "unverifiable", measurement
    assert "required_unknown" in (missing / "output" / "result.json").read_text(encoding="utf-8")

    # Parseable case contract with missing task: input_error, nonzero, null unknown field.
    absent_task = parent / "absent-task"
    inp = absent_task / "input"
    inp.mkdir(parents=True)
    write_json(inp / "case.json", {
        "example_marker": MARKER, "metadata": {"id": "SYNTHETIC-NO-TASK"},
        "output_contract": {"required": ["case_id", "status", "required_unknown"]},
    })
    completed = invoke(root, inp, absent_task / "work", absent_task / "output", task=inp / "missing-task.md")
    assert completed.returncode != 0
    result = json.loads((absent_task / "output" / "result.json").read_text(encoding="utf-8"))
    assert result["case_id"] == "SYNTHETIC-NO-TASK" and result["status"] == "input_error"
    assert result["required_unknown"] is None and "required_unknown" in result["unresolved_fields"]
    for name in ARTIFACTS:
        assert (absent_task / "output" / name).is_file(), name + " absent after input failure"

    # Actually malformed JSON has no recoverable contract but still emits the base result/artifacts.
    malformed = parent / "malformed-case"
    inp = malformed / "input"
    inp.mkdir(parents=True)
    (inp / "case.json").write_text('{"example_marker": "' + MARKER + '", invalid JSON', encoding="utf-8")
    (inp / "task.md").write_text(MARKER + "\n", encoding="utf-8")
    completed = invoke(root, inp, malformed / "work", malformed / "output")
    assert completed.returncode != 0
    result = json.loads((malformed / "output" / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "input_error" and result["case_id"] is None
    assert result["uncertainty"] and result["review_queue"] == []
    assert (malformed / "output" / "audit.md").read_text(encoding="utf-8").count("input_error") == 1
    print("PASS missing evidence, missing task, malformed JSON, nonzero input failures, partial preservation")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-root", help="Existing directory for disposable failure fixtures")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    validate_example(root)
    if args.work_root:
        Path(args.work_root).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="evidence-adjudicator-self-check-", dir=args.work_root) as temporary:
        failure_checks(root, Path(temporary))
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
