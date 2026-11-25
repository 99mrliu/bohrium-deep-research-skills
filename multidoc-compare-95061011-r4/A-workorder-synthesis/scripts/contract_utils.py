#!/usr/bin/env python3
"""Shared, domain-neutral helpers for workorder planning and assembly."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable


class InputError(ValueError):
    """A user-correctable input or validation error."""


def _no_duplicate_keys(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle, object_pairs_hook=_no_duplicate_keys)
    except FileNotFoundError as exc:
        raise InputError(f"File not found: {path}") from exc
    except UnicodeError as exc:
        raise InputError(f"Not valid UTF-8: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise InputError(f"Invalid JSON in {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _field_from_item(item: Any) -> tuple[str, dict[str, Any]]:
    if isinstance(item, str) and item:
        return item, {}
    if isinstance(item, dict):
        for name_key in ("name", "key", "field", "output_key", "id"):
            name = item.get(name_key)
            if isinstance(name, str) and name:
                return name, dict(item)
    raise InputError(
        "Each output_contract list item must be a nonempty field name or an "
        "object with name/key/field/output_key/id."
    )


def contract_fields(contract: Any) -> list[tuple[str, dict[str, Any]]]:
    """Return (exact key, specification) pairs without renaming contract keys."""
    if isinstance(contract, list):
        fields = [_field_from_item(item) for item in contract]
    elif isinstance(contract, dict):
        if "fields" in contract:
            return contract_fields(contract["fields"])
        if "properties" in contract and isinstance(contract["properties"], dict):
            fields = [
                (name, dict(spec) if isinstance(spec, dict) else {})
                for name, spec in contract["properties"].items()
            ]
        else:
            fields = []
            for name, spec in contract.items():
                if not isinstance(name, str) or not name:
                    raise InputError("output_contract contains an empty field name.")
                if isinstance(spec, dict):
                    fields.append((name, dict(spec)))
                elif isinstance(spec, str):
                    fields.append((name, {"description": spec}))
                else:
                    fields.append((name, {}))
    else:
        raise InputError("output_contract must be a list or dictionary.")

    if not fields:
        raise InputError("output_contract names no fields.")
    names = [name for name, _ in fields]
    if len(names) != len(set(names)):
        raise InputError("output_contract contains duplicate field names.")
    return fields


def get_contract(workorder: dict[str, Any]) -> Any:
    if "output_contract" not in workorder:
        raise InputError("Workorder has no output_contract.")
    return workorder["output_contract"]


def _scope_items(scope: Any) -> Any:
    if isinstance(scope, dict):
        for key in ("in_scope", "include", "documents", "items", "sources"):
            if key in scope:
                return scope[key]
        # Also accept a mapping keyed by the exact source_document_id.
        if scope and all(isinstance(key, str) for key in scope):
            return list(scope.keys())
    return scope


def _document_id(item: Any) -> str | None:
    if isinstance(item, str) and item:
        return item
    if isinstance(item, dict):
        for key in ("source_document_id", "document_id", "id"):
            value = item.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def in_scope_documents(workorder: dict[str, Any]) -> list[str]:
    scope: Any = None
    for key in (
        "document_scope",
        "in_scope_documents",
        "source_documents",
        "documents",
        "corpus",
    ):
        if key in workorder:
            scope = workorder[key]
            break
    scope = _scope_items(scope)
    if not isinstance(scope, list):
        raise InputError(
            "Cannot determine document scope. Use document_scope.in_scope as a "
            "list of exact source_document_id strings or objects."
        )
    documents: list[str] = []
    for item in scope:
        document_id = _document_id(item)
        if document_id is None:
            raise InputError(f"Invalid in-scope document entry: {item!r}")
        if document_id not in documents:
            documents.append(document_id)
    if not documents:
        raise InputError("The in-scope document list is empty.")
    return documents


def normalise_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def read_paragraphs(path: Path) -> dict[str, str]:
    """Read UTF-8 text with [paragraph_id] markers into exact source spans."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise InputError(f"Source text not found: {path}") from exc
    except UnicodeError as exc:
        raise InputError(f"Source text is not UTF-8: {path}: {exc}") from exc
    paragraphs: dict[str, list[str]] = {}
    current: str | None = None
    marker = re.compile(r"^\s*\[([^\]\s]+)\]\s*(.*)$")
    for line in text.splitlines():
        match = marker.match(line)
        if match:
            current = match.group(1)
            if current in paragraphs:
                raise InputError(f"Duplicate paragraph_id {current!r} in {path}")
            paragraphs[current] = [match.group(2)]
        elif current is not None:
            paragraphs[current].append(line)
    if not paragraphs:
        raise InputError(f"No [paragraph_id] markers found in {path}")
    return {key: normalise_space(" ".join(value)) for key, value in paragraphs.items()}


def resolve_under(root: Path, relative_path: str) -> Path:
    if not isinstance(relative_path, str) or not relative_path:
        raise InputError("Each document needs a nonempty relative text path.")
    root = root.resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise InputError(f"Document path escapes --source-root: {relative_path}") from exc
    return candidate


def validate_value_type(name: str, value: Any, spec: dict[str, Any]) -> None:
    expected = spec.get("type")
    if expected is not None:
        choices = expected if isinstance(expected, list) else [expected]
        type_checks = {
            "string": lambda item: isinstance(item, str),
            "number": lambda item: isinstance(item, (int, float))
            and not isinstance(item, bool),
            "integer": lambda item: isinstance(item, int)
            and not isinstance(item, bool),
            "boolean": lambda item: isinstance(item, bool),
            "array": lambda item: isinstance(item, list),
            "object": lambda item: isinstance(item, dict),
            "null": lambda item: item is None,
        }
        unknown = [choice for choice in choices if choice not in type_checks]
        if unknown:
            raise InputError(f"Unsupported type(s) for {name!r}: {unknown}")
        if not any(type_checks[choice](value) for choice in choices):
            raise InputError(
                f"Contract field {name!r} must have type {expected}; "
                f"got {type(value).__name__}."
            )
    if "enum" in spec and isinstance(spec["enum"], list) and value not in spec["enum"]:
        raise InputError(f"Contract field {name!r} is outside its declared enum.")
