#!/usr/bin/env python3
"""Harvest lossless numeric expressions into an append-only JSONL ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SCHEMA_VERSION = "numeric-ledger/v1"
DIGITS = "0123456789"
SUPERSCRIPT_DIGITS = "⁰¹²³⁴⁵⁶⁷⁸⁹"
BASE = r"(?:\d+(?:\.\d+)?|\.\d+)"
EXPONENT = rf"(?:[eE][+\-−]?\d+|(?:\s*[×x]\s*)?10[⁻−-]?[{SUPERSCRIPT_DIGITS}0-9]+)"
UNSIGNED_NUMBER = rf"(?:{BASE}(?:[eE][+\-−]?\d+|(?:\s*[×x]\s*)10[⁻−-]?[{SUPERSCRIPT_DIGITS}0-9]+)?|10[⁻−-]?[{SUPERSCRIPT_DIGITS}0-9]+)"
NUMBER = rf"[+\-−]?{UNSIGNED_NUMBER}"

# Unit spelling is recognized, never normalized. The final alternative covers
# common SI compounds while avoiding arbitrary English words after a number.
UNIT_LEXEME = r"(?:percentage[ -]points?|%|°[CFK]|(?:[kMGTmuncpfµμ]?(?:mol|min|eV|ppm|ppb|bar|atm|Hz|Pa|Wb|Bq|Gy|Sv|kat|lx|lm|cd|m|g|s|A|K|N|J|W|C|V|F|Ω|S|T|H|L|l|h|d|M))(?:[·/⁄](?:[kMGTmuncpfµμ]?(?:mol|min|eV|m|g|s|A|K|N|J|W|C|V|F|Ω|S|T|H|L|l|h|d|M)|10))?[⁻−-]?[⁰¹²³⁴⁵⁶⁷⁸⁹0-9]*)"
UNIT = rf"(?:\s*(?P<unit>{UNIT_LEXEME}))"
VALUE_BODY = (
    rf"(?P<comparator><|>|≤|≥|=|≈|~)?\s*(?P<first>{NUMBER})"
    rf"(?:\s*(?P<pm>±|\+/-)\s*(?P<uncertainty>{NUMBER}))?"
    rf"(?:\s*(?P<dash>–|—|\-)\s*(?P<second>{NUMBER}))?"
)
VALUE = rf"(?<![A-Za-z0-9_]){VALUE_BODY}{UNIT}?"
CI = (
    rf"(?<![A-Za-z0-9_])(?P<ci_open>[\[(])?\s*(?P<confidence>{NUMBER}\s*%)\s*CI\s*"
    rf"(?P<low>{NUMBER})\s*(?:,|–|—|\bto\b)\s*(?P<high>{NUMBER}){UNIT}?(?P<ci_close>[\])])?"
)
PSTAT = rf"(?<![A-Za-z0-9_])(?P<marker>p)\s*(?P<comparator><|>|≤|≥|=)\s*(?P<first>{NUMBER})"
NSTAT = rf"(?<![A-Za-z0-9_])(?P<marker>n)\s*(?P<comparator>=)\s*(?P<first>{NUMBER})"
REFERENCE = r"(?i:(?<![A-Za-z0-9_])(?:Table|Figure|Fig\.?)\s*[A-Za-z]?\d+(?:[A-Za-z])?(?:\s*[–—-]\s*\d+(?:[A-Za-z])?)?)"

def _unnamed(pattern):
    """Detection alternatives cannot reuse the decomposition group names."""
    return re.sub(r"\(\?P<[^>]+>", "(?:", pattern)


TOKEN_RE = re.compile(
    rf"(?P<CI>{_unnamed(CI)})|(?P<PSTAT>(?i:{_unnamed(PSTAT)}))|"
    rf"(?P<NSTAT>(?i:{_unnamed(NSTAT)}))|(?P<REFERENCE>{REFERENCE})|"
    rf"(?P<VALUE>{_unnamed(VALUE)})"
)
VALUE_RE = re.compile(rf"^{VALUE_BODY}{UNIT}?$")
CI_RE = re.compile(rf"^{CI}$")
PSTAT_RE = re.compile(rf"^(?i:{PSTAT})$")
NSTAT_RE = re.compile(rf"^(?i:{NSTAT})$")
REF_NUMBER_RE = re.compile(r"\d+(?:[A-Za-z])?")
RESIDUAL_NUMBER_RE = re.compile(rf"{NUMBER}|[{SUPERSCRIPT_DIGITS}]+")
STATEMENT_BOUNDARY_RE = re.compile(
    r"[;!?]+(?=\s|$)|\.(?=\s+(?:[A-Z\(\[]|$))|\n+"
)


class LedgerError(ValueError):
    """An exactness or append-only invariant was violated."""


def statement_spans(text: str):
    """Return non-whitespace statement spans without altering source text."""
    rough = []
    start = 0
    for match in STATEMENT_BOUNDARY_RE.finditer(text):
        rough.append((start, match.end()))
        start = match.end()
    if start < len(text) or not rough:
        rough.append((start, len(text)))
    spans = []
    for left, right in rough:
        while left < right and text[left].isspace():
            left += 1
        while right > left and text[right - 1].isspace():
            right -= 1
        if left < right:
            spans.append((left, right))
    return spans


def _span(match, group: str, absolute_start: int):
    start = match.start(group)
    if start < 0:
        return None
    end = match.end(group)
    return {
        "start": absolute_start + start,
        "end": absolute_start + end,
        "text": match.group(group),
    }


def _numeric_component(role, match, group, absolute_start):
    span = _span(match, group, absolute_start)
    if span is not None:
        span = {"role": role, **span}
    return span


def _classify(raw: str, start: int):
    """Decompose one raw expression while retaining all source typography."""
    if match := CI_RE.fullmatch(raw):
        opener, closer = match.group("ci_open"), match.group("ci_close")
        if (opener is None) != (closer is None) or (opener, closer) not in ((None, None), ("(", ")"), ("[", "]")):
            raise LedgerError(f"unbalanced confidence-interval brackets at offset {start}: {raw!r}")
        low = _span(match, "low", start)
        high = _span(match, "high", start)
        confidence = _numeric_component("confidence", match, "confidence", start)
        scalar_start = low["start"]
        scalar_end = high["end"]
        unit_span = _span(match, "unit", start)
        components = [x for x in (
            confidence,
            _numeric_component("lower", match, "low", start),
            _numeric_component("upper", match, "high", start),
        ) if x]
        kind = "confidence_interval"
        statistic = raw
        scalar = raw[scalar_start - start:scalar_end - start]
        units = unit_span["text"] if unit_span else None
        return kind, scalar, units, statistic, None, components, scalar_start, scalar_end, unit_span
    if match := PSTAT_RE.fullmatch(raw):
        number = _numeric_component("statistic_value", match, "first", start)
        comparator = match.group("comparator")
        return "p_statistic", match.group("first"), None, raw, comparator, [number], number["start"], number["end"], None
    if match := NSTAT_RE.fullmatch(raw):
        number = _numeric_component("sample_size", match, "first", start)
        comparator = match.group("comparator")
        return "n_statistic", match.group("first"), None, raw, comparator, [number], number["start"], number["end"], None
    # References have no scalar value, but their numeric components remain auditable.
    if re.fullmatch(REFERENCE, raw):
        components = [
            {"role": "reference_number", "start": start + m.start(), "end": start + m.end(), "text": m.group(0)}
            for m in REF_NUMBER_RE.finditer(raw)
        ]
        kind = "table_reference" if raw.lower().startswith("table") else "figure_reference"
        return kind, None, None, None, None, components, None, None, None
    match = VALUE_RE.fullmatch(raw)
    if not match:
        raise LedgerError(f"Internal lexer mismatch at offset {start}: {raw!r}")
    first = _numeric_component("range_start" if match.group("second") else "central", match, "first", start)
    components = [first]
    uncertainty = _numeric_component("uncertainty", match, "uncertainty", start)
    second = _numeric_component("range_end", match, "second", start)
    if uncertainty:
        components.append(uncertainty)
    if second:
        components.append(second)
    scalar_start = first["start"]
    scalar_end = (second or uncertainty or first)["end"]
    unit_span = _span(match, "unit", start)
    units = unit_span["text"] if unit_span else None
    comparator = match.group("comparator") or None
    if comparator:
        kind = "inequality"
    elif uncertainty:
        kind = "uncertainty"
    elif second:
        kind = "range"
    elif units and units.startswith("percentage"):
        kind = "percentage_point"
    elif units == "%":
        kind = "percent"
    else:
        kind = "scalar"
    return (
        kind,
        raw[scalar_start - start:scalar_end - start],
        units,
        None,
        comparator,
        components,
        scalar_start,
        scalar_end,
        unit_span,
    )


def _source_list(document):
    sources = document.get("sources") if isinstance(document, dict) else document
    if not isinstance(sources, list) or not sources:
        raise LedgerError("sources JSON must be a non-empty list or an object with a non-empty 'sources' list")
    return sources


def harvest_sources(document):
    """Return deterministic records in source/paragraph/offset order."""
    records = []
    seen_sources = set()
    next_id = 1
    for source in _source_list(document):
        if not isinstance(source, dict) or not isinstance(source.get("source_id"), str) or not source["source_id"]:
            raise LedgerError("every source needs a non-empty string source_id")
        source_id = source["source_id"]
        if source_id in seen_sources:
            raise LedgerError(f"duplicate source_id: {source_id}")
        seen_sources.add(source_id)
        paragraphs = source.get("paragraphs")
        if not isinstance(paragraphs, list):
            raise LedgerError(f"source {source_id!r} needs a paragraphs list")
        seen_paragraphs = set()
        for paragraph in paragraphs:
            if not isinstance(paragraph, dict):
                raise LedgerError(f"source {source_id!r} contains a non-object paragraph")
            paragraph_id = paragraph.get("paragraph_id")
            text = paragraph.get("text")
            if not isinstance(paragraph_id, str) or not paragraph_id or not isinstance(text, str):
                raise LedgerError(f"source {source_id!r}: paragraph_id and text must be strings")
            if paragraph_id in seen_paragraphs:
                raise LedgerError(f"duplicate paragraph_id {paragraph_id!r} in source {source_id!r}")
            seen_paragraphs.add(paragraph_id)
            page = paragraph.get("page", source.get("page"))
            paragraph_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            for statement_index, (statement_start, statement_end) in enumerate(statement_spans(text), 1):
                statement = text[statement_start:statement_end]
                statement_id = f"{source_id}:{paragraph_id}:s{statement_index:02d}"
                candidates = [
                    (match.start(), match.end(), False)
                    for match in TOKEN_RE.finditer(statement)
                ]
                # Coverage safety net: numeric fragments in identifiers such as C6H12O6
                # are still ledgered as residuals rather than silently disappearing.
                for match in RESIDUAL_NUMBER_RE.finditer(statement):
                    if not any(match.start() < end and match.end() > start for start, end, _ in candidates):
                        candidates.append((match.start(), match.end(), True))
                for local_start, local_end, residual in sorted(candidates):
                    start = statement_start + local_start
                    end = statement_start + local_end
                    raw = text[start:end]
                    if residual:
                        kind, scalar, units, statistic, comparator = "numeric_residual", raw, None, None, None
                        components = [{"role": "unclassified_numeric", "start": start, "end": end, "text": raw}]
                        scalar_start, scalar_end, unit_span = start, end, None
                    else:
                        (
                            kind, scalar, units, statistic, comparator, components,
                            scalar_start, scalar_end, unit_span,
                        ) = _classify(raw, start)
                    context_start = max(0, start - 60)
                    context_end = min(len(text), end + 60)
                    record = {
                        "schema_version": SCHEMA_VERSION,
                        "token_id": f"N{next_id:06d}",
                        "source_id": source_id,
                        "page": page,
                        "paragraph_id": paragraph_id,
                        "statement_id": statement_id,
                        "statement_start": statement_start,
                        "statement_end": statement_end,
                        "statement_quote": statement,
                        "offset_basis": "unicode_codepoint_half_open_within_paragraph_text",
                        "start": start,
                        "end": end,
                        "raw": raw,
                        "kind": kind,
                        "scalar": scalar,
                        "units": units,
                        "statistic": statistic,
                        "comparator": comparator,
                        "scalar_start": scalar_start,
                        "scalar_end": scalar_end,
                        "unit_start": unit_span["start"] if unit_span else None,
                        "unit_end": unit_span["end"] if unit_span else None,
                        "components": components,
                        "context_start": context_start,
                        "context_end": context_end,
                        "context": text[context_start:context_end],
                        "paragraph_sha256": paragraph_hash,
                    }
                    records.append(record)
                    next_id += 1
    return records


def validate_record_against_source(record, paragraph_text):
    """Check all stored offsets and exact strings against original text."""
    start, end = record["start"], record["end"]
    if not (0 <= start < end <= len(paragraph_text)) or paragraph_text[start:end] != record["raw"]:
        raise LedgerError(f"ledger token {record['token_id']} raw/offset mismatch")
    if paragraph_text[record["statement_start"]:record["statement_end"]] != record["statement_quote"]:
        raise LedgerError(f"ledger token {record['token_id']} statement quote mismatch")
    if paragraph_text[record["context_start"]:record["context_end"]] != record["context"]:
        raise LedgerError(f"ledger token {record['token_id']} context mismatch")
    for prefix, text_key in (("scalar", "scalar"), ("unit", "units")):
        value = record[text_key]
        left, right = record[f"{prefix}_start"], record[f"{prefix}_end"]
        if value is None:
            if left is not None or right is not None:
                raise LedgerError(f"ledger token {record['token_id']} has an orphan {prefix} span")
        elif left is None or right is None or paragraph_text[left:right] != value:
            raise LedgerError(f"ledger token {record['token_id']} {prefix} span mismatch")
    for component in record["components"]:
        if paragraph_text[component["start"]:component["end"]] != component["text"]:
            raise LedgerError(f"ledger token {record['token_id']} component mismatch")
    expected_hash = hashlib.sha256(paragraph_text.encode("utf-8")).hexdigest()
    if record["paragraph_sha256"] != expected_hash:
        raise LedgerError(f"ledger token {record['token_id']} paragraph hash mismatch")


def read_ledger(path: Path):
    if not path.exists():
        return []
    raw = path.read_bytes()
    if not raw:
        return []
    if not raw.endswith(b"\n"):
        raise LedgerError("append-only ledger is torn: final JSONL line lacks a newline")
    records = []
    seen = set()
    for line_number, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LedgerError(f"invalid ledger JSON at line {line_number}: {exc}") from exc
        token_id = record.get("token_id") if isinstance(record, dict) else None
        if not isinstance(token_id, str) or token_id in seen:
            raise LedgerError(f"invalid or duplicate token_id at ledger line {line_number}")
        seen.add(token_id)
        records.append(record)
    return records


def append_ledger(path: Path, expected):
    """Never rewrite or delete a ledger row; changed IDs are fatal."""
    existing = read_ledger(path)
    by_id = {record["token_id"]: record for record in existing}
    additions = []
    for record in expected:
        token_id = record["token_id"]
        if token_id in by_id:
            if by_id[token_id] != record:
                raise LedgerError(
                    f"append-only collision at {token_id}: source order/content changed; use a new ledger"
                )
        else:
            additions.append(record)
    if additions:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            for record in additions:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
    return existing, additions


def _md(value):
    if value is None:
        return "—"
    return str(value).replace("|", "\\|").replace("\n", "\\n")


def write_ledger_audit(path: Path, records):
    lines = [
        "# Numeric ledger audit",
        "",
        f"Records: **{len(records)}**. Offsets are half-open Unicode-codepoint spans within each paragraph's exact `text`.",
        "Compound expressions retain component offsets; no numeric or unit conversion has occurred.",
        "",
        "| Token | Source / paragraph / page | Kind | Exact raw | Scalar | Units | Statistic | Statement span |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in records:
        location = f"{r['source_id']} / {r['paragraph_id']} / {_md(r['page'])}"
        lines.append(
            f"| {r['token_id']} | {_md(location)} | {r['kind']} | `{_md(r['raw'])}` | "
            f"{_md(r['scalar'])} | {_md(r['units'])} | {_md(r['statistic'])} | "
            f"{r['statement_start']}–{r['statement_end']} |"
        )
        lines.append(f"  - Context {r['context_start']}–{r['context_end']}: {_md(r['context'])}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", required=True, type=Path, help="Canonical source JSON")
    parser.add_argument("--ledger", required=True, type=Path, help="Append-only numeric_ledger.jsonl")
    parser.add_argument("--audit", type=Path, help="Optional readable ledger audit")
    args = parser.parse_args(argv)
    try:
        document = json.loads(args.sources.read_text(encoding="utf-8"))
        expected = harvest_sources(document)
        existing, additions = append_ledger(args.ledger, expected)
        if args.audit:
            by_id = {r["token_id"]: r for r in existing}
            by_id.update({r["token_id"]: r for r in additions})
            write_ledger_audit(args.audit, [by_id[r["token_id"]] for r in expected])
        print(json.dumps({
            "status": "ok",
            "harvested_tokens": len(expected),
            "appended_tokens": len(additions),
            "existing_tokens_preserved": len(existing),
            "ledger": str(args.ledger),
        }, ensure_ascii=False))
    except (OSError, UnicodeError, json.JSONDecodeError, LedgerError) as exc:
        print(f"numeric_ledger error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
