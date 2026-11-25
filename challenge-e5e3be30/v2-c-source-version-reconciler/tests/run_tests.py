#!/usr/bin/env python3
"""Executable offline checks for the SYNTHETIC source-version-reconciler example."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ElementTree

BUNDLE = Path(__file__).resolve().parents[1]
CLI = BUNDLE / "scripts" / "reconcile.py"
EXAMPLE = BUNDLE / "examples" / "minimal"
INPUT = EXAMPLE / "input"
WORK = EXAMPLE / "work"
OUTPUT = EXAMPLE / "output" / "result.json"
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cli(*arguments: str, expect: int = 0) -> subprocess.CompletedProcess:
    completed = subprocess.run(
        [sys.executable, str(CLI), *arguments],
        env=ENV,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert completed.returncode == expect, (
        f"expected exit {expect}, got {completed.returncode}\n"
        f"command: {' '.join(arguments)}\nstdout: {completed.stdout}\nstderr: {completed.stderr}"
    )
    return completed


def reconcile(input_dir: Path, work: Path, result: Path, metadata: Path, evidence: Path, expect: int = 0) -> subprocess.CompletedProcess:
    cli("init", "--input", str(input_dir), "--output", str(result))
    partial = load(result)
    case = load(input_dir / "case.json")
    assert partial["case_id"] == case["case_id"]
    assert partial["status"] == "partial"
    assert partial["sources"] == []
    assert partial["change_records"][0]["phase"] == "initialize"
    assert set(case["output_contract"]).issubset(partial)
    cli("inventory", "--input", str(input_dir), "--output", str(work / "source-inventory.json"))
    validation = cli("validate", "--input", str(input_dir), "--work", str(work), "--metadata", str(metadata), expect=expect)
    if expect:
        return validation
    return cli(
        "finalize", "--input", str(input_dir), "--work", str(work), "--metadata", str(metadata),
        "--evidence", str(evidence), "--output", str(result), expect=expect,
    )


def happy_path() -> None:
    reconcile(INPUT, WORK, OUTPUT, EXAMPLE / "reviewed-source-metadata.json", EXAMPLE / "reviewed-evidence-map.json")
    inventory = load(WORK / "source-inventory.json")
    assert inventory["file_count"] == 4
    assert inventory["duplicate_file_count"] == 1
    assert "SYNTHETIC" in inventory["case_id"] and inventory["case_labels"] == ["SYNTHETIC"]
    original = next(file for file in inventory["files"] if file["file_id"] == "documents/paper_v1.txt")
    duplicate = next(file for file in inventory["files"] if file["file_id"] == "documents/paper_v1_duplicate.txt")
    expected_hash = hashlib.sha256((INPUT / "documents" / "paper_v1.txt").read_bytes()).hexdigest()
    assert original["sha256"] == duplicate["sha256"] == expected_hash
    assert duplicate["duplicate_of"] == original["file_id"]
    result = load(OUTPUT)
    assert result["status"] == "partial"
    assert set(result) >= {"case_id", "claims", "version_matrix", "source_version_dag", "sources", "uncertainty", "change_records"}
    claims = {claim["claim_id"]: claim for claim in result["claims"]}
    revision = claims["SYNTHETIC-claim-main-revision"]
    assert revision["status"] == "partially_supported"
    assert revision["version_scope"] == ["doc-v1", "doc-v2"]
    assert [item["outcome"] for item in revision["evidence"]] == ["supported", "contradicted"]
    assert all(item["quote_verified"] for item in revision["evidence"])
    supplement = claims["SYNTHETIC-claim-supplement-condition"]
    assert supplement["status"] == "supported"
    assert supplement["version_scope"] == ["doc-supplement-s2"]
    assert all(item["document_id"] == "doc-supplement-s2" for item in supplement["evidence"])
    assert "S-1" in supplement["evidence"][0]["locator"]
    assert result["version_matrix"]["doc-v1"]["claim_statements"][0]["quote"] != result["version_matrix"]["doc-v2"]["claim_statements"][0]["quote"]
    svg = (WORK / "provenance.svg").read_text(encoding="utf-8")
    assert "SYNTHETIC" in svg and "doc-v1" in svg and "doc-v2" in svg and "doc-supplement-s2" in svg
    assert "structural relations, not authority ranking" in svg
    ElementTree.fromstring(svg)
    checked = load(WORK / "evidence-map-checked.json")
    for claim in checked["claims"]:
        for evidence in claim["evidence"]:
            assert evidence["matched_file_id"] in next(source["files"] for source in result["sources"] if source["document_id"] == evidence["document_id"])


def dag_failure_paths(tmp: Path) -> None:
    metadata = load(EXAMPLE / "reviewed-source-metadata.json")
    work = tmp / "failure-work"
    work.mkdir()
    cli("inventory", "--input", str(INPUT), "--output", str(work / "source-inventory.json"))
    cyclic = copy.deepcopy(metadata)
    cyclic["documents"][0]["relations"].append({"type": "revises", "target_id": "doc-v2"})
    cycle_path = dump_and_return(tmp / "cycle-metadata.json", cyclic)
    failed = cli("validate", "--input", str(INPUT), "--work", str(work), "--metadata", str(cycle_path), expect=1)
    assert "cycle detected" in failed.stderr
    assert not (work / "source-version-dag.json").exists(), "cycle must not emit a valid DAG"
    dangling = copy.deepcopy(metadata)
    dangling["documents"][1]["relations"][0]["target_id"] = "doc-does-not-exist"
    dangling_path = dump_and_return(tmp / "dangling-metadata.json", dangling)
    failed = cli("validate", "--input", str(INPUT), "--work", str(work), "--metadata", str(dangling_path), expect=1)
    assert "dangling relation" in failed.stderr and "doc-does-not-exist" in failed.stderr


def dump_and_return(path: Path, value) -> Path:
    dump(path, value)
    return path


def wrong_document_quote(tmp: Path) -> None:
    evidence = load(EXAMPLE / "reviewed-evidence-map.json")
    evidence["claim_decisions"][0]["evidence"][1]["quote"] = evidence["claim_decisions"][0]["evidence"][0]["quote"]
    evidence_path = dump_and_return(tmp / "wrong-document-evidence.json", evidence)
    work, result = tmp / "wrong-quote-work", tmp / "wrong-quote-result.json"
    reconcile(INPUT, work, result, EXAMPLE / "reviewed-source-metadata.json", evidence_path)
    final = load(result)
    revision = next(claim for claim in final["claims"] if claim["claim_id"] == "SYNTHETIC-claim-main-revision")
    assert revision["evidence"][1]["quote_verified"] is False
    checked = load(work / "evidence-map-checked.json")
    checked_revision = next(claim for claim in checked["claims"] if claim["claim_id"] == revision["claim_id"])
    assert checked_revision["evidence"][1]["matched_file_id"] is None
    assert any("absence is not contradiction" in item for item in final["uncertainty"])


def stale_inventory_failure(tmp: Path) -> None:
    copied_input = tmp / "stale-input"
    copied_input.mkdir()
    for path in INPUT.rglob("*"):
        if path.is_file():
            target = copied_input / path.relative_to(INPUT)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
    work, result = tmp / "stale-work", tmp / "stale-result.json"
    cli("init", "--input", str(copied_input), "--output", str(result))
    cli("inventory", "--input", str(copied_input), "--output", str(work / "source-inventory.json"))
    (copied_input / "documents" / "paper_v2.txt").write_text("SYNTHETIC changed bytes after inventory\n", encoding="utf-8")
    failed = cli(
        "finalize", "--input", str(copied_input), "--work", str(work),
        "--metadata", str(EXAMPLE / "reviewed-source-metadata.json"),
        "--evidence", str(EXAMPLE / "reviewed-evidence-map.json"), "--output", str(result), expect=1,
    )
    assert "stale inventory/hash mismatch" in failed.stderr
    assert load(result)["status"] == "partial", "failure must leave the early honest partial result intact"


def single_document_downgrade(tmp: Path) -> None:
    single_input = tmp / "single-input"
    single_input.mkdir()
    for path in INPUT.rglob("*"):
        if path.is_file():
            target = single_input / path.relative_to(INPUT)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
    case = load(single_input / "case.json")
    case["case_id"] = "SYNTHETIC-single-document"
    case["output_contract"]["custom_empty_list"] = []
    case["output_contract"]["custom_empty_object"] = {}
    dump(single_input / "case.json", case)
    claims = load(single_input / "claims-to-verify.json")
    claims[0]["version_scope"] = ["doc-v1"]
    dump(single_input / "claims-to-verify.json", claims[:1])
    metadata = load(EXAMPLE / "reviewed-source-metadata.json")
    metadata["documents"] = metadata["documents"][:1]
    metadata_path = dump_and_return(tmp / "single-metadata.json", metadata)
    evidence = load(EXAMPLE / "reviewed-evidence-map.json")
    decision = evidence["claim_decisions"][0]
    decision["evidence"] = decision["evidence"][:1]
    evidence["claim_decisions"] = [decision]
    evidence_path = dump_and_return(tmp / "single-evidence.json", evidence)
    work, result = tmp / "single-work", tmp / "single-result.json"
    reconcile(single_input, work, result, metadata_path, evidence_path)
    final = load(result)
    assert len(final["sources"]) == 1
    assert final["status"] == "partial"
    assert final["claims"][0]["status"] == "insufficient_evidence"
    assert final["custom_empty_list"] == [] and final["custom_empty_object"] == {}
    assert any("cross-version comparison is impossible" in item for item in final["uncertainty"])
    checked = load(work / "evidence-map-checked.json")
    assert "fewer than two" in checked["claims"][0]["scope_limitation"]


def main() -> None:
    happy_path()
    with tempfile.TemporaryDirectory(prefix="source-version-reconciler-test-") as temporary:
        tmp = Path(temporary)
        dag_failure_paths(tmp)
        # This subtest owns its directory to keep quote-failure evidence isolated.
        wrong_document_quote(tmp / "wrong-quote")
        stale_inventory_failure(tmp)
        single_document_downgrade(tmp)
    print("PASS: happy path, real hashes, duplicate detection, scoped quotes, version matrix and SVG")
    print("PASS: cycle and dangling relation both rejected with exit 1")
    print("PASS: wrong-document quote fails locally without becoming contradiction")
    print("PASS: stale input hash is rejected and early partial result remains")
    print("PASS: one-document comparison downgrades honestly; extra list/dict contract fields survive")


if __name__ == "__main__":
    main()
