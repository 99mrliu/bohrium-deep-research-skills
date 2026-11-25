#!/usr/bin/env python3
"""Validate agent-authored answers and assemble matrix, report, and result JSON."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from contract_utils import (
    InputError,
    contract_fields,
    get_contract,
    in_scope_documents,
    load_json,
    normalise_space,
    read_paragraphs,
    resolve_under,
    validate_value_type,
    write_json,
)

STATES = {"reported", "not_reported", "not_applicable", "unclear", "noncomparable"}
COMPARABILITY_AXES = ("task", "metric", "units", "material", "pollutant", "budget")
STANDARD_RESULT_KEYS = {"case_id", "status", "sources", "uncertainty", "change_records"}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InputError(message)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _inline(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ": "))


def _md(value: Any) -> str:
    return _inline(value).replace("|", "\\|").replace("\n", "<br>")


def _validate_documents(
    expected: list[str], documents: Any, source_root: Path
) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    _require(isinstance(documents, list), "common cells must contain a documents list.")
    _require(len(expected) >= 2, "Comparison matrix requires at least two in-scope documents.")
    mapped: dict[str, dict[str, str]] = {}
    document_rows: list[dict[str, str]] = []
    for item in documents:
        _require(isinstance(item, dict), "Each document entry must be an object.")
        document_id = item.get("source_document_id")
        _require(
            isinstance(document_id, str) and bool(document_id),
            "Each document needs an exact source_document_id.",
        )
        _require(document_id not in mapped, f"Duplicate mapped document: {document_id}")
        path = item.get("path")
        source_path = resolve_under(source_root, path)
        mapped[document_id] = read_paragraphs(source_path)
        document_rows.append({"source_document_id": document_id, "path": path})
    _require(
        set(mapped) == set(expected),
        "Document map must exactly cover the workorder scope; "
        f"expected {expected}, got {list(mapped)}.",
    )
    return document_rows, mapped


def _validate_cells(
    raw_cells: Any,
    expected: list[str],
    paragraphs: dict[str, dict[str, str]],
) -> dict[str, dict[str, Any]]:
    _require(isinstance(raw_cells, list) and bool(raw_cells), "cells must be a nonempty list.")
    cells: dict[str, dict[str, Any]] = {}
    coverage = {document_id: 0 for document_id in expected}
    for index, cell in enumerate(raw_cells, start=1):
        _require(isinstance(cell, dict), f"Cell {index} must be an object.")
        cell_id = cell.get("cell_id")
        _require(isinstance(cell_id, str) and bool(cell_id), f"Cell {index} needs cell_id.")
        _require(cell_id not in cells, f"Duplicate cell_id: {cell_id}")
        for key in ("question_id", "dimension"):
            _require(
                isinstance(cell.get(key), str) and bool(cell[key]),
                f"Cell {cell_id} needs {key}.",
            )
        document_id = cell.get("source_document_id")
        paragraph_id = cell.get("paragraph_id")
        _require(
            document_id in coverage,
            f"Cell {cell_id} has out-of-scope or unknown source_document_id: {document_id!r}.",
        )
        _require(
            isinstance(paragraph_id, str) and paragraph_id in paragraphs[document_id],
            f"Cell {cell_id} has unknown paragraph_id {paragraph_id!r} for {document_id}.",
        )
        state = cell.get("state")
        _require(state in STATES, f"Cell {cell_id} has invalid state {state!r}.")
        _require("value" in cell, f"Cell {cell_id} needs an explicit value (use not_reported if apt).")
        if state == "reported":
            quote = cell.get("quote")
            _require(
                isinstance(quote, str) and bool(normalise_space(quote)),
                f"Reported cell {cell_id} needs a nonempty source span quote.",
            )
            source_text = paragraphs[document_id][paragraph_id]
            _require(
                normalise_space(quote) in source_text,
                f"Cell {cell_id} quote is not an exact whitespace-normalised span of "
                f"{document_id}/{paragraph_id}.",
            )
        coverage[document_id] += 1
        cells[cell_id] = cell
    missing = [document_id for document_id, count in coverage.items() if count == 0]
    _require(not missing, f"Comparison matrix has no cells for in-scope documents: {missing}")
    return cells


def _validate_syntheses(raw_syntheses: Any, cells: dict[str, dict[str, Any]]) -> None:
    _require(isinstance(raw_syntheses, list), "syntheses must be a list (empty is valid).")
    seen: set[str] = set()
    for index, synthesis in enumerate(raw_syntheses, start=1):
        _require(isinstance(synthesis, dict), f"Synthesis {index} must be an object.")
        synthesis_id = synthesis.get("synthesis_id")
        _require(
            isinstance(synthesis_id, str) and bool(synthesis_id),
            f"Synthesis {index} needs synthesis_id.",
        )
        _require(synthesis_id not in seen, f"Duplicate synthesis_id: {synthesis_id}")
        seen.add(synthesis_id)
        member_ids = synthesis.get("member_cell_ids")
        _require(
            isinstance(member_ids, list) and member_ids,
            f"Synthesis {synthesis_id} needs member_cell_ids.",
        )
        unknown = [cell_id for cell_id in member_ids if cell_id not in cells]
        _require(not unknown, f"Synthesis {synthesis_id} references unknown cells: {unknown}")
        _require(
            isinstance(synthesis.get("statement"), str) and bool(synthesis["statement"]),
            f"Synthesis {synthesis_id} needs a statement.",
        )
        if synthesis.get("kind") != "quantitative":
            continue
        _require(
            len(member_ids) >= 2 and len(set(member_ids)) == len(member_ids),
            f"Quantitative synthesis {synthesis_id} needs at least two distinct member cells.",
        )
        members = [cells[cell_id] for cell_id in member_ids]
        checks = synthesis.get("comparability_checks")
        _require(
            isinstance(checks, dict),
            f"Quantitative synthesis {synthesis_id} lacks comparability_checks.",
        )
        for axis in COMPARABILITY_AXES:
            _require(
                checks.get(axis) is True,
                f"Quantitative synthesis {synthesis_id} must explicitly confirm {axis} comparability.",
            )
            _require(
                all(axis in cell and cell[axis] not in (None, "") for cell in members),
                f"Quantitative synthesis {synthesis_id} lacks member metadata for {axis}.",
            )
            first = _canonical(members[0][axis])
            _require(
                all(_canonical(cell[axis]) == first for cell in members[1:]),
                f"Quantitative synthesis {synthesis_id}: {axis} differs among member cells; "
                "retain separate/noncomparable values instead.",
            )
        values = [cell.get("value") for cell in members]
        _require(
            all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values),
            f"Quantitative synthesis {synthesis_id} needs numeric member cell values.",
        )
        _require(
            synthesis.get("units") == members[0]["units"],
            f"Quantitative synthesis {synthesis_id} result units must match member units.",
        )
        if synthesis.get("method") == "arithmetic_mean":
            expected_mean = sum(values) / len(values)
            result = synthesis.get("result")
            _require(
                isinstance(result, (int, float))
                and not isinstance(result, bool)
                and math.isclose(result, expected_mean, rel_tol=1e-9, abs_tol=1e-9),
                f"Quantitative synthesis {synthesis_id} arithmetic_mean must be {expected_mean}.",
            )


def _status(response: dict[str, Any]) -> str:
    completion = response.get("completion")
    _require(isinstance(completion, dict), "Response needs a completion object.")
    complete = completion.get("requested_work_complete")
    read_failures = completion.get("read_failures")
    fatal = completion.get("fatal_failure", False)
    _require(isinstance(complete, bool), "completion.requested_work_complete must be boolean.")
    _require(isinstance(read_failures, list), "completion.read_failures must be a list.")
    _require(isinstance(fatal, bool), "completion.fatal_failure must be boolean.")
    status = "failed" if fatal else ("partial" if not complete or read_failures else "success")
    if "status" in response:
        _require(response["status"] == status, f"Declared status must be {status}, not {response['status']}.")
    return status


def _result(
    case: dict[str, Any],
    workorder: dict[str, Any],
    response: dict[str, Any],
    document_rows: list[dict[str, str]],
    cells: dict[str, dict[str, Any]],
    output_label: str,
) -> dict[str, Any]:
    _require("case_id" in case, "case.json has no case_id.")
    raw_fields = response.get("fields")
    _require(isinstance(raw_fields, dict), "Response needs a fields object.")
    fields = contract_fields(get_contract(workorder))
    for name, spec in fields:
        _require(name in raw_fields, f"Missing output_contract key: {name}")
        validate_value_type(name, raw_fields[name], spec)
    collisions = STANDARD_RESULT_KEYS.intersection(raw_fields)
    _require(
        not collisions,
        "Response fields collide with standard result metadata keys: " + str(sorted(collisions)),
    )
    uncertainty = response.get("uncertainty")
    change_records = response.get("change_records")
    _require(isinstance(uncertainty, list), "Response uncertainty must be a list.")
    _require(isinstance(change_records, list), "Response change_records must be a list.")
    sources = []
    for document in document_rows:
        paragraph_ids = [
            cell["paragraph_id"]
            for cell in cells.values()
            if cell["source_document_id"] == document["source_document_id"]
        ]
        sources.append({**document, "paragraph_ids": sorted(set(paragraph_ids))})
    result = dict(raw_fields)
    result.update(
        {
            "case_id": case["case_id"],
            "status": _status(response),
            "sources": sources,
            "uncertainty": uncertainty,
            "change_records": change_records,
        }
    )
    if output_label:
        result["output_label"] = output_label
    return result


def _matrix_markdown(
    case_id: Any,
    expected: list[str],
    document_rows: list[dict[str, str]],
    cells: dict[str, dict[str, Any]],
    exclusions: list[Any],
    output_label: str,
) -> str:
    lines = ["# Comparison matrix", ""]
    if output_label:
        lines.extend([f"**{output_label}**", ""])
    lines.extend([f"Case: `{case_id}`", "", "## Document coverage", ""])
    lines.append("| In-scope source_document_id | Source text | Matrix cells |")
    lines.append("|---|---|---:|")
    for document in document_rows:
        count = sum(
            cell["source_document_id"] == document["source_document_id"] for cell in cells.values()
        )
        lines.append(
            f"| {_md(document['source_document_id'])} | {_md(document['path'])} | {count} |"
        )
    lines.extend(["", "## Agent-authored evidence cells", ""])
    lines.append(
        "| Question | Dimension | source_document_id | paragraph_id | State | Value | Units | Source span | Comparability metadata |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for cell in cells.values():
        metadata = {axis: cell[axis] for axis in COMPARABILITY_AXES if axis in cell}
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(cell["question_id"]),
                    _md(cell["dimension"]),
                    _md(cell["source_document_id"]),
                    _md(cell["paragraph_id"]),
                    _md(cell["state"]),
                    _md(cell["value"]),
                    _md(cell.get("units", "not_applicable")),
                    _md(cell.get("quote", "")),
                    _md(metadata),
                ]
            )
            + " |"
        )
    if exclusions:
        lines.extend(["", "## Retained exclusions / noncomparability", ""])
        for exclusion in exclusions:
            lines.append(f"- {_inline(exclusion)}")
    lines.extend(["", f"Coverage requirement: {len(expected)} of {len(expected)} in-scope documents represented.", ""])
    return "\n".join(lines)


def _report_markdown(
    result: dict[str, Any],
    field_names: list[str],
    syntheses: list[dict[str, Any]],
    exclusions: list[Any],
    output_label: str,
) -> str:
    lines = ["# Integration report", ""]
    if output_label:
        lines.extend([f"**{output_label}**", ""])
    lines.extend([f"Case: `{result['case_id']}`  ", f"Status: **{result['status']}**", ""])
    lines.extend(["## Requested responses", ""])
    for name in field_names:
        lines.extend([f"### {name}", ""])
        value = result[name]
        if isinstance(value, (dict, list)):
            lines.extend(["```json", json.dumps(value, ensure_ascii=False, indent=2), "```", ""])
        else:
            lines.extend([str(value), ""])
    if syntheses:
        lines.extend(["## Evidence synthesis", ""])
        for synthesis in syntheses:
            lines.extend([f"### {synthesis['synthesis_id']}", "", synthesis["statement"], ""])
            lines.append(f"- Kind: `{synthesis.get('kind', 'qualitative')}`")
            lines.append(f"- Member cells: `{', '.join(synthesis['member_cell_ids'])}`")
            if "method" in synthesis:
                lines.append(f"- Method: `{synthesis['method']}`")
            if "result" in synthesis:
                lines.append(f"- Result: `{_inline(synthesis['result'])} {_inline(synthesis.get('units', ''))}`")
            if synthesis.get("kind") == "quantitative":
                lines.append(
                    "- Comparability confirmed: "
                    + ", ".join(COMPARABILITY_AXES)
                )
            lines.append("")
    if exclusions:
        lines.extend(["## Noncomparable and excluded evidence", ""])
        for exclusion in exclusions:
            lines.append(f"- {_inline(exclusion)}")
        lines.append("")
    lines.extend(["## Uncertainty", ""])
    lines.extend([f"- {_inline(item)}" for item in result["uncertainty"]] or ["- None declared."])
    lines.extend(["", "## Sources", ""])
    for source in result["sources"]:
        lines.append(
            f"- `{source['source_document_id']}` (`{source['path']}`), paragraphs: "
            + ", ".join(f"`{item}`" for item in source["paragraph_ids"])
        )
    lines.extend(["", "## Change records", ""])
    lines.extend([f"- {_inline(item)}" for item in result["change_records"]] or ["- None."])
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, type=Path)
    parser.add_argument("--workorder", required=True, type=Path)
    parser.add_argument("--response", required=True, type=Path, help="Agent-authored response JSON")
    parser.add_argument("--cells", required=True, type=Path, help="Agent-authored common cells JSON")
    parser.add_argument("--source-root", required=True, type=Path, help="Root for paragraph-tagged UTF-8 sources")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--output-label", default="", help="Optional provenance label printed in all outputs")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        case = load_json(args.case)
        workorder = load_json(args.workorder)
        response = load_json(args.response)
        common = load_json(args.cells)
        for value, label in (
            (case, "case"),
            (workorder, "workorder"),
            (response, "response"),
            (common, "common cells"),
        ):
            _require(isinstance(value, dict), f"{label} must be a JSON object.")
        expected = in_scope_documents(workorder)
        document_rows, paragraphs = _validate_documents(
            expected, common.get("documents"), args.source_root
        )
        cells = _validate_cells(common.get("cells"), expected, paragraphs)
        syntheses = common.get("syntheses", [])
        _validate_syntheses(syntheses, cells)
        exclusions = common.get("excluded_from_synthesis", [])
        _require(isinstance(exclusions, list), "excluded_from_synthesis must be a list.")
        for exclusion in exclusions:
            if isinstance(exclusion, dict):
                unknown = [
                    cell_id
                    for cell_id in exclusion.get("cell_ids", [])
                    if cell_id not in cells
                ]
                _require(not unknown, f"Exclusion references unknown cells: {unknown}")
        result = _result(case, workorder, response, document_rows, cells, args.output_label)
        field_names = [name for name, _ in contract_fields(get_contract(workorder))]
        matrix = _matrix_markdown(
            case["case_id"], expected, document_rows, cells, exclusions, args.output_label
        )
        report = _report_markdown(
            result, field_names, syntheses, exclusions, args.output_label
        )
        args.output_dir.mkdir(parents=True, exist_ok=True)
        write_json(args.output_dir / "result.json", result)
        (args.output_dir / "comparison-matrix.md").write_text(matrix, encoding="utf-8")
        (args.output_dir / "integration-report.md").write_text(report, encoding="utf-8")
        print(
            json.dumps(
                {
                    "output_dir": str(args.output_dir),
                    "status": result["status"],
                    "documents": len(document_rows),
                    "cells": len(cells),
                    "contract_fields": len(field_names),
                },
                ensure_ascii=False,
            )
        )
        return 0
    except InputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
