#!/usr/bin/env python3
"""Inventory inputs and initialize the honest result contract.

Only Python's standard library is used.  The script never fabricates missing
case metadata: malformed or absent case.json files are structural errors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise ValueError(f"missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path} is not valid UTF-8: {exc}") from exc


def _field_from_item(item: Any) -> str | None:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ("name", "field", "key"):
            value = item.get(key)
            if isinstance(value, str):
                return value
        if len(item) == 1:
            only_key = next(iter(item))
            if isinstance(only_key, str):
                return only_key
    return None


def extract_contract_fields(contract: Any) -> list[str]:
    """Accept output_contract as a list or as a field->description dict."""
    fields: list[str] = []
    if isinstance(contract, list):
        for item in contract:
            field = _field_from_item(item)
            if not field:
                raise ValueError(f"unsupported output_contract list item: {item!r}")
            fields.append(field)
    elif isinstance(contract, dict):
        nested = contract.get("fields")
        if isinstance(nested, (list, dict)):
            return extract_contract_fields(nested)
        fields = list(contract.keys())
    else:
        raise ValueError("output_contract must be a list or an object")

    if not fields:
        raise ValueError("output_contract contains no fields")
    if any(not isinstance(field, str) or not field for field in fields):
        raise ValueError("output_contract field names must be non-empty strings")
    if len(set(fields)) != len(fields):
        duplicates = sorted({field for field in fields if fields.count(field) > 1})
        raise ValueError(f"duplicate output_contract fields: {duplicates}")
    return fields


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_files(root: Path) -> Iterable[Path]:
    for current, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for filename in sorted(filenames):
            path = Path(current) / filename
            if path.is_symlink():
                # Record symlinks as an integrity problem instead of following
                # them outside the input tree.
                raise ValueError(f"input contains a symlink, refusing to follow: {path}")
            if path.is_file():
                yield path


def build_inventory(input_root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in iter_files(input_root):
        entries.append(
            {
                "path": path.relative_to(input_root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return entries


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="input directory to scan")
    parser.add_argument("--work", required=True, type=Path, help="work directory")
    parser.add_argument("--output", required=True, type=Path, help="final output directory")
    parser.add_argument("--force", action="store_true", help="overwrite an existing result.json skeleton")
    args = parser.parse_args(argv)

    input_root = args.input.resolve()
    work_dir = args.work.resolve()
    output_dir = args.output.resolve()

    try:
        if not input_root.is_dir():
            raise ValueError(f"input directory does not exist: {input_root}")
        case_path = input_root / "case.json"
        case = load_json(case_path)
        if not isinstance(case, dict):
            raise ValueError("case.json must contain a JSON object")
        if "case_id" not in case:
            raise ValueError("case.json lacks case_id")
        if "output_contract" not in case:
            raise ValueError("case.json lacks output_contract")
        case_id = case["case_id"]
        contract_fields = extract_contract_fields(case["output_contract"])
        inventory = build_inventory(input_root)

        work_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        write_json(
            work_dir / "inventory.json",
            {
                "case_id": case_id,
                "input_root": str(input_root),
                "file_count": len(inventory),
                "files": inventory,
            },
        )
        write_json(
            work_dir / "missing_materials.json",
            {
                "case_id": case_id,
                "missing_materials": [],
                "note": "骨架待填：逐项登记原始数据、作者仓库、依赖、文本层、种子或硬件等缺失；缺失是事实，不得补造。",
            },
        )

        result_path = output_dir / "result.json"
        if result_path.exists() and not args.force:
            print(f"kept existing result.json (use --force to replace): {result_path}")
        else:
            result: dict[str, Any] = {"case_id": case_id}
            for field in contract_fields:
                if field != "case_id":
                    result[field] = None
            result["status"] = "partial"
            result["notes"] = "骨架待填：仅由 inventory.py 初始化；尚未完成证据门、运行核对和差异归因。"
            write_json(result_path, result)
            print(f"wrote result skeleton: {result_path}")

        print(f"inventory: {len(inventory)} files")
        print(f"contract fields: {len(contract_fields)}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"inventory error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
