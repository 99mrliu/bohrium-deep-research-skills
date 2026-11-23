#!/usr/bin/env python3
"""Mechanically gate paper target values against extracted page text.

Exit codes: 0 means every target passed; 1 means at least one target was
quarantined; 2 means the JSON inputs have structural errors.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any


REQUIRED_TARGET_FIELDS = {"name", "value", "unit", "page", "quote"}
MINUS_CHARS = "\u2212\u2010\u2011\u2012\u2013\u2014\u2015"


def normalize(text: str) -> str:
    """Normalize text for evidence matching without interpreting its meaning."""
    text = unicodedata.normalize("NFKC", text)
    for ligature, replacement in {
        "\ufb00": "ff",
        "\ufb01": "fi",
        "\ufb02": "fl",
        "\ufb03": "ffi",
        "\ufb04": "ffl",
        "\ufb05": "st",
        "\ufb06": "st",
    }.items():
        text = text.replace(ligature, replacement)
    for char in MINUS_CHARS:
        text = text.replace(char, "-")
    text = text.replace("\u00ad", "")
    # Rejoin a word broken by a hyphen at a physical line end.
    text = re.sub(r"-\s*\r?\n\s*", "", text)
    # Collapse every whitespace run after dehyphenation.
    return re.sub(r"\s+", " ", text).strip()


def numeric_literal(text: str) -> str:
    """Apply target normalization plus the specified thousands-comma tolerance."""
    return normalize(text).replace(",", "")


def load_targets(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load targets JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise ValueError("targets.json root must be an array")

    targets: list[dict[str, Any]] = []
    names: set[str] = set()
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"target #{index} must be an object")
        missing = sorted(REQUIRED_TARGET_FIELDS - set(item))
        if missing:
            raise ValueError(f"target #{index} lacks required fields: {missing}")
        name = item["name"]
        value = item["value"]
        unit = item["unit"]
        page = item["page"]
        quote = item["quote"]
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"target #{index}: name must be a non-empty string")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"target #{index}: value must be a non-empty literal string")
        if not isinstance(unit, str):
            raise ValueError(f"target #{index}: unit must be a string")
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            raise ValueError(f"target #{index}: page must be a positive integer")
        if not isinstance(quote, str) or not quote.strip():
            raise ValueError(f"target #{index}: quote must be a non-empty string")
        if name in names:
            raise ValueError(f"duplicate target name: {name}")
        names.add(name)
        targets.append(dict(item))
    return targets


def load_pages(path: Path) -> dict[int, str]:
    pages: dict[int, str] = {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"pages.jsonl line {line_number} is invalid JSON: {exc}") from exc
                if not isinstance(item, dict):
                    raise ValueError(f"pages.jsonl line {line_number} must be an object")
                page = item.get("page")
                text = item.get("text")
                if not isinstance(page, int) or isinstance(page, bool) or page < 1:
                    raise ValueError(f"pages.jsonl line {line_number}: invalid page")
                if not isinstance(text, str):
                    raise ValueError(f"pages.jsonl line {line_number}: text must be a string")
                if page in pages:
                    raise ValueError(f"pages.jsonl contains duplicate page {page}")
                pages[page] = text
    except OSError as exc:
        raise ValueError(f"cannot read pages JSONL: {exc}") from exc
    if not pages:
        raise ValueError("pages.jsonl contains no pages")
    return pages


def evaluate_target(target: dict[str, Any], pages: dict[int, str]) -> tuple[bool, dict[str, Any]]:
    expected_page = target["page"]
    quote_norm = normalize(target["quote"])
    value_norm = numeric_literal(target["value"])
    quote_for_value = numeric_literal(target["quote"])
    value_in_quote = value_norm in quote_for_value

    specified_text = pages.get(expected_page)
    specified_match = specified_text is not None and quote_norm in normalize(specified_text)
    matched_page: int | None = expected_page if specified_match else None

    if specified_match:
        if value_in_quote:
            record = dict(target)
            record.update(
                {
                    "matched_page": matched_page,
                    "checks": {"quote_found": True, "value_in_quote": True, "page_matches": True},
                }
            )
            return True, record
        record = dict(target)
        record.update(
            {
                "reason": "value_not_in_quote",
                "expected_page": expected_page,
                "matched_page": matched_page,
                "detail": "quote was found on the specified page, but the literal value is absent from the quote",
            }
        )
        return False, record

    global_matches = [page for page, text in sorted(pages.items()) if quote_norm in normalize(text)]
    record = dict(target)
    if global_matches:
        record.update(
            {
                "reason": "page_mismatch",
                "expected_page": expected_page,
                "matched_page": global_matches[0],
                "all_matched_pages": global_matches,
                "detail": "quote exists in the document, but not on the declared physical page",
            }
        )
    else:
        record.update(
            {
                "reason": "quote_not_found",
                "expected_page": expected_page,
                "matched_page": None,
                "detail": "normalized quote is not a substring of any extracted page",
            }
        )
    return False, record


def markdown_cell(value: Any) -> str:
    text = "—" if value is None else str(value)
    return text.replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>")


def write_json(path: Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_report(path: Path, gated: list[dict[str, Any]], quarantined: list[dict[str, Any]]) -> None:
    verdict = "PASS" if not quarantined else "FAIL"
    lines = [
        f"GATE: {verdict}",
        "",
        f"passed: {len(gated)}; quarantined: {len(quarantined)}",
        "",
        "| 状态 | name | value | unit | 声明页 | 匹配页 | 原因 | 引文 |",
        "|---|---|---|---|---:|---:|---|---|",
    ]
    for item in gated:
        lines.append(
            "| 通过 | {name} | {value} | {unit} | {page} | {matched} | — | {quote} |".format(
                name=markdown_cell(item.get("name")),
                value=markdown_cell(item.get("value")),
                unit=markdown_cell(item.get("unit")),
                page=markdown_cell(item.get("page")),
                matched=markdown_cell(item.get("matched_page")),
                quote=markdown_cell(item.get("quote")),
            )
        )
    for item in quarantined:
        lines.append(
            "| 隔离 | {name} | {value} | {unit} | {page} | {matched} | {reason} | {quote} |".format(
                name=markdown_cell(item.get("name")),
                value=markdown_cell(item.get("value")),
                unit=markdown_cell(item.get("unit")),
                page=markdown_cell(item.get("page")),
                matched=markdown_cell(item.get("matched_page")),
                reason=markdown_cell(item.get("reason")),
                quote=markdown_cell(item.get("quote")),
            )
        )
    if quarantined:
        lines.extend(
            [
                "",
                "隔离项不得进入参数复原、运行或指标比较；修正证据后必须重新过门。",
            ]
        )
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", required=True, type=Path, help="targets JSON array")
    parser.add_argument("--pages", required=True, type=Path, help="pages JSONL from pdf_text.py")
    parser.add_argument("--out", required=True, type=Path, help="output directory")
    args = parser.parse_args(argv)

    try:
        targets = load_targets(args.targets.resolve())
        pages = load_pages(args.pages.resolve())
    except ValueError as exc:
        print(f"gate structural error: {exc}", file=sys.stderr)
        return 2

    gated: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    for target in targets:
        passed, record = evaluate_target(target, pages)
        (gated if passed else quarantined).append(record)

    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        write_json(out_dir / "gated.json", gated)
        write_json(out_dir / "quarantined.json", quarantined)
        write_report(out_dir / "gate_report.md", gated, quarantined)
    except OSError as exc:
        print(f"gate output error: {exc}", file=sys.stderr)
        return 2

    print(f"GATE: {'PASS' if not quarantined else 'FAIL'}")
    return 0 if not quarantined else 1


if __name__ == "__main__":
    raise SystemExit(main())
