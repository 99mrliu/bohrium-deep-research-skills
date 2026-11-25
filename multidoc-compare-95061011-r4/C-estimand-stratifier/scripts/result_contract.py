#!/usr/bin/env python3
"""Render exactly case_id plus the original, dynamically named output_contract fields."""
from __future__ import annotations

import re
from typing import Any, Dict, Mapping


def _token(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _shape(value: Any, template: Any) -> Any:
    """Preserve a contract field's broad list/dict/scalar type without inventing data."""
    if isinstance(template, list):
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return list(value.values())
        return [value]
    if isinstance(template, dict):
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            return {"items": value}
        return {"value": value}
    if value is None:
        return "" if isinstance(template, str) else None
    return value


def _empty_like(template: Any) -> Any:
    if isinstance(template, list):
        return []
    if isinstance(template, dict):
        return {key: _empty_like(value) for key, value in template.items()}
    if isinstance(template, str):
        return ""
    return None


def render_result(case_id: str, output_contract: Mapping[str, Any], context: Mapping[str, Any]) -> Dict[str, Any]:
    """No extra top-level fields are added; unknown contract fields remain honestly empty.

    Values in output_contract are type templates, not prose schemas. Recognized field names
    are matched case/punctuation-insensitively. A dict template receives either its natural
    dict value or {"items": [...]}; a list template always remains a list.
    """
    if not isinstance(output_contract, Mapping) or not output_contract:
        raise ValueError("case.json output_contract must be a nonempty object")
    result: Dict[str, Any] = {"case_id": case_id}
    value_map = {
        "comparisonmatrix": context["matrix_path"],
        "matrix": context["matrix_path"],
        "comparisonoperations": context["operations_path"],
        "operations": context["operations_path"],
        "status": context["status"],
        "sources": context["sources"],
        "source": context["sources"],
        "uncertainty": context["uncertainty"],
        "uncertainties": context["uncertainty"],
        "changerecords": context["change_records"],
        "changelog": context["change_records"],
        "operationresults": context["operation_results"],
        "operationsresults": context["operation_results"],
        "strata": context["strata"],
        "stratumregister": context["strata"],
        "estimandregister": context["estimands"],
        "estimands": context["estimands"],
    }
    for field, template in output_contract.items():
        if field == "case_id":
            result[field] = case_id
            continue
        token = _token(field)
        value = value_map.get(token)
        result[field] = _empty_like(template) if token not in value_map else _shape(value, template)
    return result
