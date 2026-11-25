#!/usr/bin/env python3
"""Shared, standard-library-only primitives for the rerun impact ledger."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json_new(path: Path, value: object, immutable: bool = True) -> None:
    """Create exactly once; never replace an existing audit record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with path.open("x", encoding="utf-8") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    if immutable:
        path.chmod(0o444)


def write_json_atomic(path: Path, value: object) -> None:
    """Atomically publish a result; audit manifests use write_json_new instead."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def hash_tree(root: Path) -> list[dict[str, object]]:
    if not root.is_dir():
        raise ValueError(f"not a directory: {root}")
    records: list[dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"symlinks are not accepted as source material: {path}")
        if path.is_file():
            records.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    if not records:
        raise ValueError(f"no source files found under: {root}")
    return records


def hash_file_record(path: Path) -> dict[str, object]:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"not a regular file: {path}")
    return {"bytes": path.stat().st_size, "sha256": sha256_file(path)}


def effective_run_record(run_dir: Path) -> dict[str, object]:
    execution = run_dir / "execution.json"
    if execution.exists():
        value = read_json(execution)
    else:
        value = read_json(run_dir / "manifest.json")
    if not isinstance(value, dict):
        raise ValueError("run record must be an object")
    return value


_FIELD_LIST_KEYS = (
    "fields",
    "required_fields",
    "required_top_fields",
    "required_top_level_fields",
)
_JSON_TYPES = frozenset(
    {"object", "array", "string", "number", "integer", "boolean", "null"}
)


def _validate_descriptor(descriptor: dict[str, object], location: str) -> None:
    declared = descriptor.get("type")
    if declared is None:
        return
    types = declared if isinstance(declared, list) else [declared]
    if not types or not all(
        isinstance(value, str) and value in _JSON_TYPES for value in types
    ):
        raise ValueError(
            f"{location}.type must be a JSON type or a nonempty list of JSON types"
        )
    if len(types) != len(set(types)):
        raise ValueError(f"{location}.type contains duplicate types")


def _map_descriptor(value: object, location: str) -> dict[str, object]:
    if value is None:
        descriptor: dict[str, object] = {}
    elif isinstance(value, str):
        descriptor = {"type": value}
    elif isinstance(value, dict):
        descriptor = dict(value)
    else:
        raise ValueError(f"{location} must be a type string, metadata object, or null")
    _validate_descriptor(descriptor, location)
    return descriptor


def _list_fields(value: object, location: str) -> list[tuple[str, dict[str, object]]]:
    if not isinstance(value, list):
        raise ValueError(f"{location} must be a list")
    entries: list[tuple[str, dict[str, object]]] = []
    seen: set[str] = set()
    for index, value_entry in enumerate(value):
        entry_location = f"{location}[{index}]"
        if isinstance(value_entry, str):
            name = value_entry
            descriptor: dict[str, object] = {}
        elif isinstance(value_entry, dict):
            name = value_entry.get("name")
            descriptor = {
                key: child for key, child in value_entry.items() if key != "name"
            }
            _validate_descriptor(descriptor, entry_location)
        else:
            raise ValueError(f"{entry_location} must be a string or descriptor object")
        if not isinstance(name, str) or not name:
            raise ValueError(f"{entry_location}.name must be a nonempty string")
        if name in seen:
            raise ValueError(f"{location} contains duplicate field {name!r}")
        seen.add(name)
        entries.append((name, descriptor))
    return entries


def _map_fields(value: object, location: str) -> list[tuple[str, dict[str, object]]]:
    if not isinstance(value, dict):
        raise ValueError(f"{location} must be an object")
    entries = []
    for name, descriptor in value.items():
        if not isinstance(name, str) or not name:
            raise ValueError(f"{location} field names must be nonempty strings")
        entries.append((name, _map_descriptor(descriptor, f"{location}.{name}")))
    return entries


def output_field_specs(case: dict[str, object]) -> list[dict[str, object]]:
    """Parse supported contract shapes independently of any particular example.

    List containers and ``properties`` may be combined; their descriptors are
    merged. A mapping without one of those containers is itself a field map.
    ``case_id`` and ``status`` are implicit required top-level fields.
    """
    if not isinstance(case, dict):
        raise ValueError("case must be an object")
    contract = case.get("output_contract")
    if contract is None:
        contract = {}
    if isinstance(contract, list):
        entries = _list_fields(contract, "case.output_contract")
    elif isinstance(contract, dict):
        containers = [key for key in _FIELD_LIST_KEYS if key in contract]
        entries = []
        for key in containers:
            entries.extend(_list_fields(contract[key], f"case.output_contract.{key}"))
        if "properties" in contract:
            entries.extend(
                _map_fields(contract["properties"], "case.output_contract.properties")
            )
        if not containers and "properties" not in contract:
            entries = _map_fields(contract, "case.output_contract")
    else:
        raise ValueError("case.output_contract must be a list or object")

    merged: dict[str, dict[str, object]] = {}
    ordered_names: list[str] = []
    for name, descriptor in entries:
        if name not in merged:
            ordered_names.append(name)
            merged[name] = dict(descriptor)
            continue
        previous = merged[name]
        if (
            "type" in previous
            and "type" in descriptor
            and previous["type"] != descriptor["type"]
        ):
            raise ValueError(f"conflicting type descriptors for output field {name!r}")
        previous.update(descriptor)
    for mandatory in ("case_id", "status"):
        if mandatory not in merged:
            ordered_names.append(mandatory)
            merged[mandatory] = {"type": "string"}
    return [{"name": name, **merged[name]} for name in ordered_names]


def output_fields(case: dict[str, object]) -> list[str]:
    return [str(spec["name"]) for spec in output_field_specs(case)]


def _empty_typed_value(declared: object) -> object:
    if isinstance(declared, list):
        declared = declared[0]
    return {
        "object": {},
        "array": [],
        "string": "",
        "number": 0,
        "integer": 0,
        "boolean": False,
        "null": None,
    }.get(declared)


def make_contract_payload(case: dict[str, object]) -> dict[str, object]:
    """Populate every declared field top-level with a safe typed PARTIAL value."""
    payload: dict[str, object] = {}
    for spec in output_field_specs(case):
        field = str(spec["name"])
        if field == "case_id":
            payload[field] = case.get("case_id")
        elif field == "status":
            payload[field] = "PARTIAL"
        elif field == "success":
            payload[field] = False
        elif "type" in spec:
            payload[field] = _empty_typed_value(spec["type"])
        elif field in {
            "items",
            "benchmark_draft",
            "questions",
            "scores",
            "sources",
            "uncertainty",
            "change_records",
            "limitations",
        }:
            payload[field] = []
        elif field in {"item_bank", "score_report", "rollup", "summary", "run_manifest"}:
            payload[field] = {}
        else:
            payload[field] = None
    return payload


def _matches_json_type(value: object, declared: str) -> bool:
    if declared == "object":
        return isinstance(value, dict)
    if declared == "array":
        return isinstance(value, list)
    if declared == "string":
        return isinstance(value, str)
    if declared == "number":
        return not isinstance(value, bool) and isinstance(value, (int, float))
    if declared == "integer":
        return not isinstance(value, bool) and (
            isinstance(value, int) or isinstance(value, float) and value.is_integer()
        )
    if declared == "boolean":
        return isinstance(value, bool)
    if declared == "null":
        return value is None
    return False


def contract_type_errors(
    case: dict[str, object], payload: dict[str, object]
) -> list[str]:
    """Return dynamic top-level shape and declared-descriptor type violations."""
    if not isinstance(payload, dict):
        return ["contract payload must be an object"]
    specs = output_field_specs(case)
    expected = {str(spec["name"]) for spec in specs}
    errors = [f"missing top-level field {field!r}" for field in expected - set(payload)]
    errors.extend(f"unexpected top-level field {field!r}" for field in set(payload) - expected)
    for spec in specs:
        field = str(spec["name"])
        declared = spec.get("type")
        if declared is None or field not in payload:
            continue
        types = declared if isinstance(declared, list) else [declared]
        if not any(_matches_json_type(payload[field], value) for value in types):
            errors.append(
                f"field {field!r} does not match declared type {declared!r}"
            )
    return sorted(errors)


def validate_contract_payload(
    case: dict[str, object], payload: dict[str, object]
) -> None:
    errors = contract_type_errors(case, payload)
    if errors:
        raise ValueError("output contract validation failed: " + "; ".join(errors))


def decimal_sum(values: object) -> Decimal:
    if not isinstance(values, dict) or not values:
        raise ValueError("component_scores must be a nonempty object")
    total = Decimal("0")
    for key, value in values.items():
        if not isinstance(key, str) or isinstance(value, bool) or not isinstance(
            value, (int, float)
        ):
            raise ValueError("component scores must be numeric values keyed by strings")
        total += Decimal(str(value))
    return total


def require_regular_file(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"required regular file is missing: {path}")
