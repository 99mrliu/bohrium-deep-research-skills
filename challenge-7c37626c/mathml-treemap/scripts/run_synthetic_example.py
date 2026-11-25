#!/usr/bin/env python3
"""Run and assert the fully synthetic normal, failure, and empty-source tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, List
import xml.etree.ElementTree as ET

from mathml_ir import SUPPORTED_TAGS, element_to_ir, render_latex, roundtrip_ir

BUNDLE = Path(__file__).resolve().parents[1]
SCRIPTS = BUNDLE / "scripts"
EXAMPLE = BUNDLE / "examples" / "synthetic"
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}


def invoke(arguments: List[str], expected: int = 0) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [sys.executable, *arguments],
        cwd=BUNDLE,
        env=ENV,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    if completed.returncode != expected:
        raise AssertionError(f"Expected exit {expected}, got {completed.returncode}: {arguments}")
    return completed


def load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def reset(path: Path) -> None:
    if path.exists():
        if path.is_symlink() or not path.is_dir():
            raise RuntimeError(f"Refusing to reset unexpected path: {path}")
        shutil.rmtree(path)
    path.mkdir(parents=True)


def supported_subset_test() -> Dict[str, Any]:
    source = """<math data-test="all-tags"><mrow>
      <mstyle><mpadded><mi>s</mi></mpadded></mstyle><mphantom><mi>p</mi></mphantom><mspace/>
      <menclose notation="radical"><mi>w</mi></menclose>
      <semantics><mi>q</mi><annotation encoding="application/x-tex">q</annotation><annotation-xml encoding="MathML-Content"><mi>q</mi></annotation-xml></semantics>
      <mfrac><mi>x</mi><mn>2</mn></mfrac>
      <msub><mi mathvariant="bold">x</mi><mn>1</mn></msub>
      <msup><mi>x</mi><mn>2</mn></msup>
      <msubsup><mi>x</mi><mn>1</mn><mn>2</mn></msubsup>
      <msqrt><mi>z</mi></msqrt><mroot><mn>27</mn><mn>3</mn></mroot>
      <mfenced open="[" close="]" separators=";"><mi>a</mi><mi>b</mi></mfenced>
      <munder><mo form="prefix">∑</mo><mn>0</mn></munder>
      <mover><mi>x</mi><mo stretchy="true">¯</mo></mover>
      <munderover><mo fence="false" separator="false">∑</mo><mn>0</mn><mi>n</mi></munderover>
      <mtable><mtr><mtd><mi>a</mi></mtd><mtd><mtext>synthetic</mtext></mtd></mtr><mlabeledtr><mtd><mi>b</mi></mtd></mlabeledtr></mtable>
    </mrow></math>"""
    ir = element_to_ir(ET.fromstring(source))

    def tags(node: Dict[str, Any]) -> set[str]:
        return {node["tag"]} | {tag for child in node["children"] for tag in tags(child)}

    observed = tags(ir)
    assert observed == SUPPORTED_TAGS, f"Tag coverage mismatch: {observed ^ SUPPORTED_TAGS}"
    report = roundtrip_ir(ir)
    latex, issues = render_latex(ir)
    assert report["status"] == "pass" and report["discrepancies"] == []
    assert report["roundtripped_ir"]["attributes"]["data-test"] == "all-tags"
    assert not issues
    for fragment in (r"\frac{", r"\underset{", r"\overset{", r"\left[", r"\begin{matrix}"):
        assert fragment in latex

    variants = element_to_ir(ET.fromstring("<math><mrow><mi>①</mi><mo>−</mo><mn>1</mn><mo>⋅</mo></mrow></math>"))
    variant_report = roundtrip_ir(variants)
    variant_latex, variant_issues = render_latex(variants)
    serialized = json.dumps(variant_report["roundtripped_ir"], ensure_ascii=False)
    assert variant_report["status"] == "pass" and not variant_issues
    assert "①" in serialized and "−" in serialized and "⋅" in serialized
    assert "①" in variant_latex and r"\cdot" in variant_latex
    return {"status": "pass", "supported_tags_tested": len(observed), "semantic_variant_codepoints_preserved": ["①", "−", "⋅"]}


def normal_test() -> Dict[str, Any]:
    work = EXAMPLE / "work"
    output = EXAMPLE / "output"
    reset(work)
    reset(output)
    case = EXAMPLE / "input" / "case.json"
    task = EXAMPLE / "input" / "task.md"
    invoke([
        str(SCRIPTS / "extract_mathml.py"), "--case", str(case), "--task", str(task), "--work", str(work)
    ])
    catalog_path = work / "mathml" / "catalog.json"
    invoke([str(SCRIPTS / "verify_roundtrip.py"), "--catalog", str(catalog_path), "--strict"])
    invoke([
        str(SCRIPTS / "assemble_result.py"),
        "--case", str(case),
        "--task", str(task),
        "--catalog", str(catalog_path),
        "--analysis", str(EXAMPLE / "input" / "agent_analysis.json"),
        "--output", str(output / "result.json"),
    ])
    catalog = load(catalog_path)
    result = load(output / "result.json")
    verification = load(work / "mathml" / "roundtrip-verification.json")
    validation = load(output / "result_validation.json")
    assert catalog["case_id"] == "SYNTHETIC-MATHML-001"
    assert catalog["formula_count"] == 2 and catalog["status"] == "success"
    assert {item["source"]["id"] for item in catalog["formulas"]} == {"SYN-F01", "SYN-F02"}
    assert all(item["roundtrip"]["status"] == "pass" for item in catalog["formulas"])
    assert verification["canonical_roundtrip_pass_count"] == 2
    nested = next(item for item in catalog["formulas"] if item["source"]["id"] == "SYN-F01")
    assert r"\frac{" in nested["latex"] and r"\begin{matrix}" in nested["latex"]
    assert r"\left[" in nested["latex"] and r"\mathit{velocity}" in nested["latex"]
    assert nested["publisher_checks"]["alttext"]["authoritative"] is False
    assert nested["ordered_path"][-1]["tag"] == "math"
    assert result["case_id"] == "SYNTHETIC-MATHML-001"
    assert result["status"] == "partial"
    assert isinstance(result["formula_analysis"], list) and len(result["formula_analysis"]) == 2
    generated_latex = {item["formula_key"]: item["latex"] for item in catalog["formulas"]}
    assert all(item["latex"] == generated_latex[item["formula_key"]] for item in result["formula_analysis"])
    assert isinstance(result["numeric_analysis"], dict) and result["numeric_analysis"]["evaluation"] == 3
    assert result["extraction_summary"]["formula_count"] == 2
    assert validation["contract_valid"] is True
    assert (EXAMPLE / "work" / "mathml" / "catalog.md").is_file()
    return {
        "status": "pass",
        "formula_count": catalog["formula_count"],
        "roundtrip_pass_count": verification["canonical_roundtrip_pass_count"],
        "result_status": result["status"],
        "result": str(output / "result.json"),
        "catalog": str(work / "mathml" / "catalog.md"),
    }


def unsupported_test() -> Dict[str, Any]:
    root = EXAMPLE / "expected_failure"
    work = root / "work"
    reset(work)
    case = root / "input" / "case.json"
    task = root / "input" / "task.md"
    extraction = invoke([
        str(SCRIPTS / "extract_mathml.py"), "--case", str(case), "--task", str(task), "--work", str(work)
    ], expected=2)
    catalog_path = work / "mathml" / "catalog.json"
    verification_run = invoke([
        str(SCRIPTS / "verify_roundtrip.py"), "--catalog", str(catalog_path), "--strict"
    ], expected=2)
    catalog = load(catalog_path)
    entry = catalog["formulas"][0]
    assert catalog["status"] == "partial"
    assert entry["roundtrip"]["status"] == "unsupported"
    assert entry["roundtrip"]["canonical_equal"] is True
    assert any(item["tag"] == "mystery" for item in entry["roundtrip"]["unsupported_nodes"])
    assert "UNSUPPORTED MathML:mystery" in entry["latex"]
    assert entry["publisher_checks"]["alttext"]["status"] == "mismatch"
    assert entry["publisher_checks"]["alttext"]["authoritative"] is False
    assert "UNSUPPORTED" in verification_run.stderr
    test = {
        "status": "pass",
        "unsupported_tag": "mystery",
        "extraction_exit": extraction.returncode,
        "strict_verification_exit": verification_run.returncode,
        "latex_marker_retained": True,
        "no_silent_structural_pass": True,
        "publisher_alttext_status": entry["publisher_checks"]["alttext"]["status"],
    }
    (root / "failure-test.json").write_text(json.dumps(test, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return test


def empty_test() -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="no-formula-test-", dir=EXAMPLE) as raw:
        root = Path(raw)
        inputs = root / "input"
        inputs.mkdir()
        case_data = {
            "case_id": "SYNTHETIC-MATHML-EMPTY",
            "source": "publisher-source.xml",
            "output_contract": {
                "required_fields": ["status", "formula_analysis", "variable_analysis", "derivation_analysis", "numeric_analysis"],
                "field_types": {
                    "status": "string", "formula_analysis": "array", "variable_analysis": "array",
                    "derivation_analysis": "array", "numeric_analysis": "object"
                },
                "status_enum": ["success", "partial", "insufficient_evidence"]
            }
        }
        (inputs / "case.json").write_text(json.dumps(case_data), encoding="utf-8")
        (inputs / "task.md").write_text("Synthetic empty source test; no formula may be invented.\n", encoding="utf-8")
        (inputs / "publisher-source.xml").write_text("<article><body><p>No formula here.</p></body></article>\n", encoding="utf-8")
        case = inputs / "case.json"
        task = inputs / "task.md"
        work = root / "work"
        output = root / "output" / "result.json"
        invoke([str(SCRIPTS / "extract_mathml.py"), "--case", str(case), "--task", str(task), "--work", str(work)])
        catalog = load(work / "mathml" / "catalog.json")
        assert catalog["status"] == "insufficient_evidence" and catalog["formula_count"] == 0
        assert "No `<math>` nodes" in (work / "mathml" / "catalog.md").read_text(encoding="utf-8")
        invoke([
            str(SCRIPTS / "assemble_result.py"), "--case", str(case), "--task", str(task),
            "--catalog", str(work / "mathml" / "catalog.json"), "--output", str(output)
        ])
        result = load(output)
        assert result["case_id"] == "SYNTHETIC-MATHML-EMPTY"
        assert result["status"] == "insufficient_evidence"
        assert result["formula_analysis"] == [] and result["variable_analysis"] == []
        assert result["numeric_analysis"]["status"] == "insufficient_evidence"
        assert load(output.parent / "result_validation.json")["contract_valid"] is True
        return {"status": "pass", "case_id": result["case_id"], "result_status": result["status"], "formula_count": 0}


def main() -> int:
    subset = supported_subset_test()
    normal = normal_test()
    failure = unsupported_test()
    empty = empty_test()
    summary = {"supported_subset": subset, "normal_end_to_end": normal, "expected_unknown_tag_failure": failure, "no_formula": empty}
    destination = EXAMPLE / "test-results.json"
    destination.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"All synthetic tests passed. Summary: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
