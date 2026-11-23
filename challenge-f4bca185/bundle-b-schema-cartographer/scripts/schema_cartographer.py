#!/usr/bin/env python3
"""schema-cartographer: heterogeneous literature-extraction cleaning and standardization.

Focus: heterogeneous field mapping, versioned schema/semantic-type coordination,
source-preserving cleaning, defensible unit normalization and conservative
duplicate flagging. Python 3.10+ standard library only.

The script never invents missing values, never silently merges scientific
conflicts and always writes an honest partial result before doing real work.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import traceback
import unicodedata
from collections import Counter, OrderedDict
from pathlib import Path

TOOL_NAME = "schema-cartographer"
TOOL_VERSION = "1.0.0"
BUNDLE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICTIONARY = BUNDLE_ROOT / "references" / "field-dictionary.json"
DEFAULT_UNITS = BUNDLE_ROOT / "references" / "units.json"

RECORD_CONTAINER_KEYS = {
    "records", "rows", "data", "items", "entries", "extractions",
    "extracted_records", "table_rows", "materials", "数据集", "记录", "抽取记录",
}
CONTRACT_KEYS = {"output_contract", "output-contract", "outputcontract"}
CASE_ID_KEYS = ("case_id", "caseId", "id", "case")

NUM = r"[+-]?(?:\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?"
RE_RANGE = re.compile(
    r"^\s*(" + NUM + r")\s*(?:–|—|\.\.|~|～|至|到|−|\s-\s|-)\s*(" + NUM + r")\s*([^\d\s].*)?$"
)
RE_SINGLE = re.compile(r"^\s*(" + NUM + r")\s*([^\d\s].*)?$")
RE_PM = re.compile(r"^\s*(" + NUM + r")\s*(?:±|\+/-|\+\-)\s*(" + NUM + r")\s*([^\d\s].*)?$")
RE_UNIT_BRACKETS = re.compile(r"[\(\[（【]\s*([^\)\]）】]{1,40}?)\s*[\)\]）】]")
RE_NON_WORD = re.compile(r"[^0-9a-z一-鿿]+")
RE_WS = re.compile(r"\s+")

COMPONENT_SUFFIXES = {
    "min": "low", "minimum": "low", "low": "low", "lower": "low", "lo": "low",
    "max": "high", "maximum": "high", "high": "high", "upper": "high", "hi": "high",
    "下限": "low", "上限": "high", "最小": "low", "最大": "high", "最低": "low", "最高": "high",
}


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def norm_text(value: object) -> str:
    """NFKC + casefold + whitespace collapse; stable for Chinese and Latin text."""
    if value is None:
        return ""
    return RE_WS.sub(" ", unicodedata.normalize("NFKC", str(value))).strip().casefold()


def normalize_header(header: str):
    """Return (normalized_base, unit_hint, component) for a raw column header.

    Unit-looking bracket groups are removed from the base and surfaced as hints;
    min/max/low/high conventions are surfaced as range components.
    """
    raw_text = unicodedata.normalize("NFKC", str(header)).strip()
    raw_hints = RE_UNIT_BRACKETS.findall(raw_text)  # original case, kept for evidence fidelity
    text = raw_text.casefold()
    base = RE_UNIT_BRACKETS.sub(" ", text)
    slash_hint = None
    slash = re.search(r"/\s*([a-z°µμ%][\w°µμ\-^/]{0,11})\s*$", base)
    if slash and base[: slash.start()].strip():
        slash_hint = slash.group(1)
        base = base[: slash.start()]
    base = RE_NON_WORD.sub("_", base).strip("_")
    component = None
    tokens = base.split("_") if base else []
    if tokens:
        last = tokens[-1]
        if last in COMPONENT_SUFFIXES and len(tokens) > 1:
            component = COMPONENT_SUFFIXES[last]
            tokens = tokens[:-1]
        elif tokens[0] in COMPONENT_SUFFIXES and len(tokens) > 1:
            component = COMPONENT_SUFFIXES[tokens[0]]
            tokens = tokens[1:]
        else:
            for suffix, comp in COMPONENT_SUFFIXES.items():
                if len(suffix) > 1 and base.endswith(suffix) and len(base) > len(suffix):
                    component = comp
                    tokens = [base[: -len(suffix)]]
                    break
    base = "_".join(t for t in tokens if t)
    unit_hint = raw_hints[-1].strip() if raw_hints else slash_hint
    return base, unit_hint, component


def alias_norm(alias: str) -> str:
    return normalize_header(alias)[0]


def fmt_num(value):
    if value is None:
        return None
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return float(f"{value:.12g}")
    return value


def csv_cell(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def is_missing(raw, missing_tokens) -> bool:
    if raw is None:
        return True
    return norm_text(raw) in missing_tokens


def clean_number(text: str):
    try:
        return float(str(text).replace(",", ""))
    except (TypeError, ValueError):
        return None


def flatten_record(node, prefix=""):
    """Flatten nested dicts to dotted paths; lists are kept as JSON strings."""
    flat = OrderedDict()
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flat.update(flatten_record(value, path))
        elif isinstance(value, list):
            flat[path] = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            flat[path] = value
    return flat


# ---------------------------------------------------------------------------
# ingestion
# ---------------------------------------------------------------------------

class RawRow:
    __slots__ = ("row_id", "source_id", "locator", "data")

    def __init__(self, row_id, source_id, locator, data):
        self.row_id = row_id
        self.source_id = source_id
        self.locator = locator
        self.data = data


def looks_like_csv(text: str) -> bool:
    if "\n" not in text or len(text) > 5_000_000:
        return False
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return False
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",\t;|")
        sample = text[:4096]
        has_header = csv.Sniffer().has_header(sample)
    except csv.Error:
        return False
    if not has_header:
        return False
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [r for r in reader if any(c.strip() for c in r)]
    if len(rows) < 2 or len(rows[0]) < 2:
        return False
    width = len(rows[0])
    stable = sum(1 for r in rows[1:] if len(r) == width)
    return stable >= max(1, int(0.6 * (len(rows) - 1)))


def parse_csv_text(text, source_id, rows_out, sources, start_index):
    dialect = csv.Sniffer().sniff(text[:4096], delimiters=",\t;|")
    reader = csv.reader(io.StringIO(text), dialect)
    raw_rows = [r for r in reader if any(c.strip() for c in r)]
    if not raw_rows:
        return start_index
    headers = [h.strip() or f"column_{i+1}" for i, h in enumerate(raw_rows[0])]
    for offset, values in enumerate(raw_rows[1:], start=2):
        padded = list(values) + [""] * (len(headers) - len(values))
        data = OrderedDict(zip(headers, padded[: len(headers)]))
        rows_out.append(RawRow(f"R{start_index:06d}", source_id,
                               f"{source_id}#row{offset}", data))
        start_index += 1
    sources.append({"source_id": source_id, "kind": "csv",
                    "rows": len(raw_rows) - 1, "columns": headers})
    return start_index


def ingest_case(case_path: Path):
    """Recursively harvest nested JSON records, embedded CSV strings and CSV files."""
    case_text = case_path.read_text(encoding="utf-8-sig")
    case = json.loads(case_text)
    rows, sources, warnings = [], [], []
    counter = 1
    seen_csv_files = set()

    def add_record_list(items, source_id, pointer):
        nonlocal counter
        added = 0
        for index, item in enumerate(items):
            if isinstance(item, dict):
                flat = flatten_record(item)
                rows.append(RawRow(f"R{counter:06d}", source_id,
                                   f"{pointer}/{index}", flat))
                counter += 1
                added += 1
        if added:
            sources.append({"source_id": source_id, "kind": "json_records",
                            "rows": added, "locator": pointer})

    def load_csv_file(file_path: Path, pointer):
        nonlocal counter
        resolved = str(file_path.resolve())
        if resolved in seen_csv_files:
            return
        seen_csv_files.add(resolved)
        try:
            text = file_path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            warnings.append(f"CSV file referenced at {pointer} could not be read: {exc}")
            return
        counter = parse_csv_text(text, f"{case_path.name}:{file_path.name}",
                                 rows, sources, counter)

    def walk(node, pointer):
        nonlocal counter
        if isinstance(node, dict):
            for key, value in node.items():
                if str(key).casefold() in CONTRACT_KEYS:
                    continue
                walk(value, f"{pointer}/{key}")
        elif isinstance(node, list):
            if node and all(isinstance(x, dict) for x in node):
                add_record_list(node, f"{case_path.name}{pointer}", pointer)
            else:
                for index, value in enumerate(node):
                    walk(value, f"{pointer}/{index}")
        elif isinstance(node, str):
            stripped = node.strip()
            if not stripped:
                return
            if stripped.casefold().endswith(".csv") and "\n" not in stripped:
                candidate = (case_path.parent / stripped).resolve()
                if candidate.is_file():
                    load_csv_file(candidate, pointer)
                return
            if looks_like_csv(node):
                source_id = f"{case_path.name}{pointer}"
                counter = parse_csv_text(node, source_id, rows, sources, counter)

    if isinstance(case, list) and all(isinstance(x, dict) for x in case):
        add_record_list(case, case_path.name, "")
    else:
        walk(case, "")
    return case, rows, sources, warnings, case_text


def find_case_id(case) -> str:
    if isinstance(case, dict):
        for key in CASE_ID_KEYS:
            value = case.get(key)
            if isinstance(value, (str, int)) and str(value).strip():
                return str(value).strip()
    return "unknown-case"


# ---------------------------------------------------------------------------
# schema profiling (semantic type inference)
# ---------------------------------------------------------------------------

def classify_value(raw, missing_tokens):
    if is_missing(raw, missing_tokens):
        return "missing"
    text = str(raw).strip()
    if RE_RANGE.match(text):
        return "range"
    if RE_PM.match(text):
        return "numeric"
    if RE_SINGLE.match(text):
        return "numeric"
    return "string"


def profile_columns(rows, missing_tokens):
    columns = OrderedDict()
    for row in rows:
        for header, raw in row.data.items():
            key = f"{row.source_id}::{header}"
            columns.setdefault(key, {"source_id": row.source_id, "header": header,
                                     "present": 0, "kinds": Counter(), "samples": [],
                                     "distinct": set()})
    for key, profile in columns.items():
        for row in rows:
            if row.source_id != profile["source_id"]:
                continue
            raw = row.data.get(profile["header"])
            profile["present"] += 1
            kind = classify_value(raw, missing_tokens)
            profile["kinds"][kind] += 1
            if kind != "missing":
                text = str(raw).strip()
                profile["distinct"].add(norm_text(text))
                if len(profile["samples"]) < 5:
                    profile["samples"].append(text[:80])
    for key, profile in columns.items():
        kinds = profile["kinds"]
        non_missing = profile["present"] - kinds.get("missing", 0)
        n = max(non_missing, 1)
        ratios = {k: kinds.get(k, 0) / n for k in ("numeric", "range", "string")}
        values = list(profile["distinct"])
        uniqueness = len(values) / n if non_missing else 0.0
        base, _, _ = normalize_header(profile["header"])
        id_name_hint = base.endswith("_id") or base in {"id", "doi"} or base.endswith("编号")
        id_value_hint = all(
            re.fullmatch(r"[A-Za-z0-9][\w.\-/:#]{1,120}", v) for v in values[:50]
        ) and all(" " not in v for v in values[:50])
        doi_like = bool(values) and all(
            re.fullmatch(r"10\.\d{4,9}/\S+", v) for v in values[:100])
        if non_missing == 0:
            semantic = "missing"
        elif doi_like:
            semantic = "identifier"
        elif ratios["range"] >= 0.6:
            semantic = "range"
        elif ratios["numeric"] + ratios["range"] >= 0.8:
            semantic = "numeric"
        elif uniqueness >= 0.9 and id_value_hint and (id_name_hint or ratios["string"] >= 0.8):
            semantic = "identifier"
        else:
            semantic = "string"
        profile["non_missing"] = non_missing
        profile["semantic_type"] = semantic
        rule_label = "TYPE-002b DOI-shaped values (10.<registrant>/<suffix>)" if doi_like else {
            "missing": "TYPE-000 all values are missing tokens",
            "range": "TYPE-004 >=60% of non-missing values match low..high range syntax",
            "numeric": "TYPE-003 >=80% of non-missing values parse as numbers or ranges",
            "identifier": "TYPE-002 >=90% unique, identifier-shaped tokens, no spaces",
            "string": "TYPE-001 fallback free text",
        }[semantic]
        profile["type_evidence"] = {
            "kind_counts": dict(kinds),
            "uniqueness": round(uniqueness, 4),
            "rule": rule_label,
        }
        profile["samples"] = profile["samples"]
        del profile["distinct"]
        del profile["kinds"]
        del profile["present"]
    return columns


# ---------------------------------------------------------------------------
# header mapping
# ---------------------------------------------------------------------------

class Mapper:
    def __init__(self, dictionary, units_doc=None):
        self.dictionary = dictionary
        self.fields = dictionary["fields"]
        self.stop_tokens = set(dictionary.get("stop_header_tokens", []))
        self.alias_index = []
        for field in self.fields:
            variants = {field["name"], *field.get("aliases", [])}
            for alias in variants:
                norm = alias_norm(alias)
                if norm:
                    self.alias_index.append((field["name"], alias, norm))
        # unit token -> dimensions that recognize it (for "Field_UNIT" header conventions)
        self.unit_dims = {}
        if units_doc:
            for dim_name, dim in units_doc.get("dimensions", {}).items():
                for unit_name, spec in dim.get("units", {}).items():
                    for alias in {unit_name, *spec.get("aliases", [])}:
                        self.unit_dims.setdefault(norm_text(alias), set()).add(dim_name)

    def candidates(self, header, profile):
        base, unit_hint, component = normalize_header(header)
        variants = [(base, unit_hint, None)]
        if unit_hint is None and "_" in base:
            stem, _, last = base.rpartition("_")
            if stem and last and last in self.unit_dims:
                variants.append((stem, last, "MAP-002"))
        best = {}
        for field_name, alias, norm in self.alias_index:
            field = self.field(field_name)
            for variant_base, variant_hint, suffix_rule in variants:
                score, rule = 0.0, None
                if variant_base == norm:
                    if suffix_rule:
                        if not field.get("dimension") or \
                           field["dimension"] not in self.unit_dims.get(variant_hint, set()):
                            continue
                        score, rule = 0.92, "MAP-002 alias plus '_UNIT' suffix convention"
                    else:
                        score, rule = 0.99, "MAP-001 exact normalized alias match"
                elif not suffix_rule and len(norm) >= 3 and \
                        (variant_base.startswith(norm + "_") or variant_base.endswith("_" + norm)):
                    remainder = variant_base[len(norm):].strip("_") if variant_base.startswith(norm) \
                        else variant_base[: -len(norm)].strip("_")
                    remainder_tokens = set(remainder.split("_")) - {""}
                    if remainder_tokens and remainder_tokens <= self.stop_tokens:
                        score, rule = 0.78, "MAP-003 alias plus stop-word tokens"
                if not rule:
                    continue
                effective_hint = variant_hint if variant_hint else unit_hint
                entry = {"field": field_name, "score": score, "rule": rule,
                         "matched_alias": alias, "unit_hint": effective_hint,
                         "component": component}
                current = best.get(field_name)
                if current is None or score > current["score"]:
                    best[field_name] = entry
        # MAP-TYPE-GUARD: fuzzy (non-exact) matches onto numeric fields require
        # value-level numeric support in the column profile; component headers
        # are only valid for numeric (range-capable) fields.
        for field_name in list(best):
            field = self.field(field_name)
            entry = best[field_name]
            if entry["score"] < 0.9 and field["semantic_type"] == "numeric":
                counts = profile.get("type_evidence", {}).get("kind_counts", {})
                numeric_like = counts.get("numeric", 0) + counts.get("range", 0)
                if profile["semantic_type"] in {"string", "identifier"} and numeric_like == 0:
                    del best[field_name]
                    continue
            if component and field["semantic_type"] != "numeric":
                del best[field_name]
        return best

    def field(self, name):
        for field in self.fields:
            if field["name"] == name:
                return field
        return None

    def map_columns(self, profiles):
        mappings, unmapped, reviews = OrderedDict(), [], []
        for key, profile in profiles.items():
            best = self.candidates(profile["header"], profile)
            ranked = sorted(best.values(), key=lambda c: (-c["score"], c["field"]))
            if ranked and ranked[0]["score"] >= 0.6:
                if len(ranked) > 1 and ranked[0]["score"] - ranked[1]["score"] < 0.03:
                    # MAP-005: an explicit unit hint that exactly one tied
                    # candidate's dimension recognizes disambiguates the header.
                    hint = ranked[0].get("unit_hint")
                    tied = [c for c in ranked
                            if ranked[0]["score"] - c["score"] < 0.03]
                    if hint:
                        unit_aware = [
                            c for c in tied
                            if self.field(c["field"]).get("dimension") in
                            self.unit_dims.get(norm_text(hint), set())
                        ]
                        if len(unit_aware) == 1:
                            chosen = unit_aware[0]
                            chosen["score"] = min(0.995, round(chosen["score"] + 0.05, 4))
                            chosen["rule"] += " + MAP-005 unit-hint disambiguation"
                            chosen["disambiguated"] = True
                            ranked = [chosen] + [c for c in ranked if c is not chosen]
                if len(ranked) > 1 and not ranked[0].get("disambiguated") and \
                        ranked[0]["score"] - ranked[1]["score"] < 0.03:
                    entry = self._unmapped_entry(key, profile, "ambiguous_header",
                                                 [c["field"] for c in ranked])
                    unmapped.append(entry)
                    reviews.append(review("MAP-AMBIG", "high", "ambiguous_header",
                                          column=key,
                                          message=f"Header {profile['header']!r} matches multiple canonical fields "
                                                  f"{[c['field'] for c in ranked]}; left unmapped for human review."))
                    continue
                chosen = ranked[0]
                if chosen["component"]:
                    chosen["rule"] = "MAP-004 component (min/low/max/high) convention on aliased header"
                mappings[key] = {
                    "column": key, "source_id": profile["source_id"],
                    "header": profile["header"], "canonical_field": chosen["field"],
                    "component": chosen["component"],
                    "confidence": chosen["score"], "rule": chosen["rule"],
                    "evidence": {
                        "matched_alias": chosen["matched_alias"],
                        "normalized_header": normalize_header(profile["header"])[0],
                        "header_unit_hint": chosen["unit_hint"],
                        "profile_semantic_type": profile["semantic_type"],
                        "type_evidence": profile["type_evidence"],
                    },
                }
            else:
                reason = "no_alias_candidate" if not ranked else "low_confidence"
                unmapped.append(self._unmapped_entry(key, profile, reason, []))
        return mappings, unmapped, reviews

    @staticmethod
    def _unmapped_entry(key, profile, reason, alternatives):
        entry = {"column": key, "source_id": profile["source_id"],
                 "header": profile["header"], "reason": reason,
                 "semantic_type": profile["semantic_type"],
                 "samples": profile["samples"],
                 "type_evidence": profile["type_evidence"]}
        if alternatives:
            entry["alternative_fields"] = alternatives
        return entry


# ---------------------------------------------------------------------------
# unit handling and value cleaning
# ---------------------------------------------------------------------------

class UnitTable:
    def __init__(self, units_doc):
        self.dimensions = units_doc["dimensions"]
        self.alias_lookup = {}
        for dim_name, dim in self.dimensions.items():
            for unit_name, spec in dim["units"].items():
                for alias in {unit_name, *spec.get("aliases", [])}:
                    self.alias_lookup[(dim_name, norm_text(alias))] = (unit_name, spec)

    def resolve(self, dimension, unit_text):
        if not dimension or unit_text is None:
            return None
        return self.alias_lookup.get((dimension, norm_text(unit_text)))


def review(rule, severity, kind, message, row_id=None, column=None, extra=None):
    item = {"review_id": f"RV-{review.counter:05d}", "rule": rule,
            "severity": severity, "kind": kind, "message": message}
    review.counter += 1
    if row_id:
        item["row_id"] = row_id
    if column:
        item["column"] = column
    if extra:
        item["evidence"] = extra
    return item


review.counter = 1


class Cleaner:
    def __init__(self, dictionary, unit_table, mappings, changelog, reviews,
                 anomalies, unresolved):
        self.fields = {f["name"]: f for f in dictionary["fields"]}
        self.missing_tokens = set(dictionary.get("missing_tokens", []))
        self.units = unit_table
        self.mappings = mappings
        self.changelog = changelog
        self.reviews = reviews
        self.anomalies = anomalies
        self.unresolved = unresolved
        self.unknown_units = OrderedDict()

    def log(self, rule, scope, row_id, field, column, old, new, evidence=None):
        entry = {"change_id": f"CH-{len(self.changelog)+1:06d}", "rule": rule,
                 "scope": scope, "row_id": row_id, "field": field,
                 "source_column": column, "old_value": old, "new_value": new}
        if evidence:
            entry["evidence"] = evidence
        self.changelog.append(entry)

    def convert(self, number, field, unit_name, spec, row, raw, column):
        dimension = field.get("dimension")
        target = self.units.dimensions[dimension]["target"]
        value = number * spec["factor"] + spec["offset"]
        value = fmt_num(value)
        if spec["factor"] != 1.0 or spec["offset"] != 0.0 or unit_name != target:
            self.log("UNIT-CONV", "cell", row.row_id, field["name"], column,
                     {"raw": raw, "number": number, "unit": unit_name},
                     {"value": value, "unit": target},
                     {"formula": spec["formula"], "factor": spec["factor"],
                      "offset": spec["offset"], "precision": "12 significant digits"})
        return value, target

    def clean_numeric(self, row, field, raw, column, component, unit_hint, cell):
        raw_text = str(raw).strip()
        range_match = RE_RANGE.match(raw_text)
        pm_match = None if range_match else RE_PM.match(raw_text)
        single_match = None if (range_match or pm_match) else RE_SINGLE.match(raw_text)
        trailing_unit = None
        low = high = value = uncertainty = None
        if range_match:
            low, high = clean_number(range_match.group(1)), clean_number(range_match.group(2))
            trailing_unit = range_match.group(3)
            cell["kind"] = "range"
            self.log("RANGE-SPLIT", "cell", row.row_id, field["name"], column, raw_text,
                     {"low": low, "high": high},
                     {"rule": "low/high endpoints preserved; no midpoint invented"})
        elif pm_match:
            value, uncertainty = clean_number(pm_match.group(1)), clean_number(pm_match.group(2))
            trailing_unit = pm_match.group(3)
            cell["kind"] = "value_with_uncertainty"
        elif single_match:
            value = clean_number(single_match.group(1))
            trailing_unit = single_match.group(2)
            cell["kind"] = "value"
        else:
            cell["kind"] = "unparseable"
            self.anomalies.append({"rule": "ANOM-PARSE", "row_id": row.row_id,
                                   "field": field["name"], "column": column,
                                   "raw": raw_text,
                                   "message": "Numeric field value could not be parsed; kept raw, normalized value left null."})
            cell["flags"].append("unparseable_numeric")
            return

        unit_candidates = []
        if unit_hint:
            unit_candidates.append(("header", unit_hint))
        if trailing_unit and trailing_unit.strip():
            unit_candidates.append(("value", trailing_unit.strip()))
        dimension = field.get("dimension")
        resolved = None
        if unit_candidates and dimension:
            normalized_units = {norm_text(u) for _, u in unit_candidates}
            if len(normalized_units) > 1:
                self.reviews.append(review(
                    "UNIT-CONFLICT", "high", "unit_conflict", row_id=row.row_id, column=column,
                    message=f"Header unit {unit_hint!r} and value unit {trailing_unit!r} disagree; no conversion applied.",
                    extra={"raw": raw_text}))
                cell["flags"].append("unit_conflict")
                return
            unit_text = unit_candidates[0][1]
            resolved = self.units.resolve(dimension, unit_text)
            if resolved is None:
                key = f"{dimension}::{norm_text(unit_text)}"
                self.unknown_units.setdefault(key, {
                    "dimension": dimension, "unit_text": unit_text,
                    "columns": [], "rows": []})
                if column not in self.unknown_units[key]["columns"]:
                    self.unknown_units[key]["columns"].append(column)
                self.unknown_units[key]["rows"].append(row.row_id)
                cell["unit_raw"] = unit_text
                cell["kind"] = cell["kind"] + "_unknown_unit"
                cell["flags"].append("unknown_unit")
                self.anomalies.append({"rule": "UNIT-UNKNOWN", "row_id": row.row_id,
                                       "field": field["name"], "column": column,
                                       "raw": raw_text, "unit": unit_text,
                                       "message": "Unknown unit: raw parsed numbers kept in raw fields, normalized values left null."})
                return
        elif unit_candidates and not dimension:
            resolved = None

        unit_out = None
        if resolved:
            unit_name, spec = resolved
            if value is not None:
                value, unit_out = self.convert(value, field, unit_name, spec, row, raw_text, column)
            if low is not None:
                low, unit_out = self.convert(low, field, unit_name, spec, row, raw_text, column)
            if high is not None:
                high, _ = self.convert(high, field, unit_name, spec, row, raw_text, column)
        else:
            if dimension:
                cell["flags"].append("unit_missing")
                cell["note"] = "No unit supplied: numbers retained verbatim, no conversion applied."
            unit_out = None

        if low is not None and high is not None and low > high:
            self.anomalies.append({"rule": "ANOM-RANGE-ORDER", "row_id": row.row_id,
                                   "field": field["name"], "column": column, "raw": raw_text,
                                   "message": "Range low endpoint is greater than high endpoint; endpoints kept as extracted."})
            cell["flags"].append("range_inverted")

        if component in {"low", "high"} and cell["kind"] in {"value", "value_with_uncertainty"}:
            # split-column convention (Yield_min / Yield_max): this column supplies
            # exactly one endpoint of the canonical range; nothing is averaged.
            cell[component] = value
            cell["unit"] = unit_out
            cell["kind"] = "range_component"
            if cell.get("low") is not None and cell.get("high") is not None and cell["low"] > cell["high"]:
                self.anomalies.append({"rule": "ANOM-RANGE-ORDER", "row_id": row.row_id,
                                       "field": field["name"], "column": column, "raw": raw_text,
                                       "message": "Composed range has low > high after combining split columns; endpoints kept as extracted."})
                cell["flags"].append("range_inverted")
        else:
            cell["value"], cell["low"], cell["high"] = value, low, high
            cell["uncertainty"] = uncertainty
            cell["unit"] = unit_out

        plausible = field.get("plausible_range")
        if plausible:
            check_values = [v for v in (value, low, high) if v is not None]
            plausible_unit = plausible.get("unit")
            unit_matches = unit_out == plausible_unit or (
                unit_out is None and False)
            if unit_matches:
                for v in check_values:
                    if v < plausible["min"] or v > plausible["max"]:
                        self.anomalies.append({"rule": "ANOM-OUT-OF-RANGE", "row_id": row.row_id,
                                               "field": field["name"], "column": column,
                                               "value": v, "unit": unit_out,
                                               "expected": plausible,
                                               "message": "Value outside dictionary plausible_range; kept, not clipped."})
                        cell["flags"].append("out_of_plausible_range")
                        break

    def clean_rows(self, rows):
        cleaned = []
        for row in rows:
            values, source_columns, flags = OrderedDict(), OrderedDict(), []
            unmapped_raw = OrderedDict()
            mapped_headers = set()
            for key, mapping in self.mappings.items():
                if mapping["source_id"] != row.source_id:
                    continue
                header = mapping["header"]
                mapped_headers.add(header)
                field = self.fields[mapping["canonical_field"]]
                raw = row.data.get(header)
                column = key
                cell = source_columns.get(field["name"])
                if cell is None:
                    cell = {"raw": raw if header in row.data else None,
                            "source_column": header if header in row.data else None,
                            "flags": [], "value": None, "low": None, "high": None,
                            "uncertainty": None, "unit": None}
                    values[field["name"]] = cell
                    source_columns[field["name"]] = cell
                elif header in row.data and cell.get("source_column") is None:
                    cell["source_column"] = header
                    cell["raw"] = raw
                if is_missing(raw, self.missing_tokens):
                    if header in row.data:
                        reason = "explicit missing token/null in source cell; retained as null, nothing imputed"
                        flag = "missing"
                    else:
                        reason = "column absent in this row (sparse union of per-source columns); retained as null"
                        flag = "absent_column"
                    if flag not in cell["flags"]:
                        cell["flags"].append(flag)
                    self.log("MISS-001", "cell", row.row_id, field["name"], column,
                             raw, None, {"reason": reason})
                    continue
                if field["semantic_type"] in {"string", "identifier"}:
                    if mapping["component"]:
                        continue
                    new_value = str(raw).strip()
                    if cell.get("value") is not None and norm_text(cell["value"]) != norm_text(new_value):
                        self.reviews.append(review(
                            "FIELD-COLLISION", "high", "column_collision",
                            row_id=row.row_id, column=column,
                            message=f"Two source columns map to '{field['name']}' with different values "
                                    f"({cell['value']!r} vs {new_value!r}); first value kept, both raw values preserved.",
                            extra={"kept_from": cell.get("source_column"),
                                   "conflicting_column": header,
                                   "conflicting_raw": raw}))
                        cell.setdefault("alternate_raw", []).append({header: raw})
                        continue
                    cell["value"] = new_value
                    cell["kind"] = field["semantic_type"]
                    cell["raw"] = raw
                    if field["semantic_type"] == "identifier":
                        cell["value_normalized"] = norm_text(raw)
                    self.log("TYPE-TEXT", "cell", row.row_id, field["name"], column,
                             raw, cell["value"], {"semantic_type": field["semantic_type"]})
                else:
                    unit_hint = mapping["evidence"].get("header_unit_hint") or \
                        normalize_header(header)[1]
                    self.clean_numeric(row, field, raw, column, mapping["component"],
                                       unit_hint, cell)
                    if mapping["component"]:
                        cell.setdefault("components", {})[mapping["component"]] = raw
            for header, raw in row.data.items():
                if header not in mapped_headers:
                    unmapped_raw[header] = raw
            flags = sorted({f for cell in values.values() for f in cell.get("flags", [])})
            cleaned.append({"row_id": row.row_id,
                            "source_id": row.source_id,
                            "locator": row.locator,
                            "values": values,
                            "unmapped_values": unmapped_raw,
                            "flags": flags,
                            "raw": row.data})
        return cleaned


# ---------------------------------------------------------------------------
# conservative duplicate detection
# ---------------------------------------------------------------------------

def context_signature(row_record, context_fields):
    parts, non_empty = [], 0
    for name in context_fields:
        cell = row_record["values"].get(name, {})
        value = cell.get("value_normalized")
        if value is None:
            value = cell.get("value")
            if value is None and (cell.get("low") is not None or cell.get("high") is not None):
                value = (cell.get("low"), cell.get("high"), cell.get("unit"))
        text = norm_text(value)
        if text:
            non_empty += 1
        parts.append(f"{name}={text}")
    return "|".join(parts), non_empty


def measure_signature(row_record, measure_fields):
    parts = []
    for name in measure_fields:
        cell = row_record["values"].get(name, {})
        if cell.get("value") is None and cell.get("low") is None and cell.get("high") is None:
            continue
        parts.append(f"{name}={cell.get('value')}/{cell.get('low')}/{cell.get('high')}/{cell.get('unit')}")
    return ";".join(parts)


def deduplicate(cleaned, fields, changelog, reviews):
    context_fields = [f["name"] for f in fields if f.get("context_key")]
    measure_fields = [f["name"] for f in fields
                      if not f.get("context_key") and f["semantic_type"] == "numeric"]
    groups = OrderedDict()
    for record in cleaned:
        signature, non_empty = context_signature(record, context_fields)
        if non_empty < 2:
            record["duplicate_status"] = "dedup_key_incomplete"
            continue
        groups.setdefault(signature, []).append(record)
    report = []
    group_index = 0
    for signature, members in groups.items():
        if len(members) < 2:
            continue
        group_index += 1
        group_id = f"DG-{group_index:04d}"
        measure_groups = OrderedDict()
        for record in members:
            measure_groups.setdefault(measure_signature(record, measure_fields), []).append(record)
        has_conflict = len(measure_groups) > 1
        group_entry = {"duplicate_group": group_id, "context_key": signature,
                       "row_ids": [m["row_id"] for m in members],
                       "distinct_measure_signatures": len(measure_groups)}
        exact_subgroups = []
        for measure_sig, same_measure in measure_groups.items():
            if len(same_measure) > 1:
                exact_subgroups.append([r["row_id"] for r in same_measure])
            for record in same_measure:
                statuses = []
                if len(same_measure) > 1:
                    statuses.append("exact_duplicate_candidate")
                if has_conflict:
                    statuses.append("context_value_conflict")
                if not statuses:
                    statuses.append("unique_within_context")
                record["duplicate_group"] = group_id
                record["duplicate_status"] = ";".join(statuses)
                for status in statuses:
                    rule = "DUP-EXACT" if status == "exact_duplicate_candidate" else (
                        "DUP-CONFLICT" if status == "context_value_conflict" else "DUP-CONTEXT")
                    changelog.append({"change_id": f"CH-{len(changelog)+1:06d}",
                                      "rule": rule, "scope": "row",
                                      "row_id": record["row_id"], "field": "_duplicate",
                                      "source_column": None, "old_value": None,
                                      "new_value": status,
                                      "evidence": {"duplicate_group": group_id,
                                                   "context_key": signature,
                                                   "note": "flag only: no row is merged or dropped by this tool"}})
        if has_conflict:
            group_entry["status"] = "scientific_conflict_requires_human_adjudication"
            reviews.append(review(
                "DUP-CONFLICT", "high", "duplicate_context_conflicting_values",
                message=f"Rows {[m['row_id'] for m in members]} share the same context key {signature!r} "
                        "but disagree on measured values. Kept as separate rows; requires human scientific adjudication, "
                        "not unit arithmetic.",
                extra={"duplicate_group": group_id,
                       "measure_groups": {sig or "(no measured values)": [r["row_id"] for r in recs]
                                          for sig, recs in measure_groups.items()}}))
        else:
            group_entry["status"] = "exact_duplicate_candidates_not_merged"
        if exact_subgroups:
            group_entry["exact_duplicate_subgroups"] = exact_subgroups
            reviews.append(review(
                "DUP-EXACT", "medium", "exact_duplicate_candidates",
                message=f"Rows {exact_subgroups} agree on every context and measured value within "
                        f"group {group_id}; flagged as duplicate-extraction candidates. "
                        "Nothing dropped automatically.",
                extra={"duplicate_group": group_id, "context_key": signature,
                       "exact_duplicate_subgroups": exact_subgroups}))
        report.append(group_entry)
    for record in cleaned:
        record.setdefault("duplicate_status", "unique")
        record.setdefault("duplicate_group", None)
    return report


# ---------------------------------------------------------------------------
# output contract handling
# ---------------------------------------------------------------------------

def extract_contract(case):
    if not isinstance(case, dict):
        return OrderedDict(), "absent"
    raw = None
    for key, value in case.items():
        if str(key).casefold() in CONTRACT_KEYS:
            raw = value
            break
    if raw is None:
        return OrderedDict(), "absent"
    contract = OrderedDict()
    if isinstance(raw, dict) and isinstance(raw.get("fields"), (dict, list)):
        raw = raw["fields"]
    if isinstance(raw, dict):
        for name, spec in raw.items():
            if isinstance(spec, str):
                contract[name] = spec
            elif isinstance(spec, dict):
                contract[name] = str(spec.get("type", spec.get("kind", "string")))
            else:
                contract[name] = "string"
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                contract[item] = "string"
            elif isinstance(item, dict) and "name" in item:
                contract[item["name"]] = str(item.get("type", "string"))
    return contract, "present"


def coerce_contract_value(name, expected_type, pools):
    """Pools maps conceptual names to (value, artifact_relative_path)."""
    entry = pools.get(name)
    if entry is None:
        return None, "unknown_contract_field"
    value, path = entry
    kind = expected_type.casefold()
    if kind in {"list", "array"}:
        if isinstance(value, list):
            return value, None
        if isinstance(value, dict) and all(isinstance(v, list) for v in value.values()):
            return list(value.values()), "flattened_dict_of_lists"
        return None, f"type_mismatch_expected_list_got_{type(value).__name__}"
    if kind in {"dict", "object", "mapping"}:
        return (value, None) if isinstance(value, dict) else (None, f"type_mismatch_expected_dict_got_{type(value).__name__}")
    if isinstance(value, str):
        return value, None
    if path:
        return path, "string_field_filled_with_artifact_relative_path"
    if isinstance(value, (int, float)):
        return str(value), "stringified_number"
    return None, f"type_mismatch_expected_string_got_{type(value).__name__}"


# ---------------------------------------------------------------------------
# artifact writers
# ---------------------------------------------------------------------------

def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_cleaned_csv(path, cleaned, fields):
    headers = ["row_id", "source_id", "source_locator", "duplicate_group", "duplicate_status", "flags"]
    layout = []
    for field in fields:
        name, kind = field["name"], field["semantic_type"]
        if kind in {"string", "identifier"}:
            layout.append((name, [name, f"{name}__raw", f"{name}__src"]))
        else:
            layout.append((name, [name, f"{name}__low", f"{name}__high", f"{name}__unc",
                                  f"{name}__unit", f"{name}__raw", f"{name}__src"]))
        headers.extend(layout[-1][1])
    headers.append("unmapped_json")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for record in cleaned:
            line = [record["row_id"], record["source_id"], record["locator"],
                    record.get("duplicate_group") or "", record.get("duplicate_status", ""),
                    ";".join(record.get("flags", []))]
            for name, columns in layout:
                cell = record["values"].get(name, {})
                getters = {
                    name: cell.get("value"),
                    f"{name}__low": cell.get("low"),
                    f"{name}__high": cell.get("high"),
                    f"{name}__unc": cell.get("uncertainty"),
                    f"{name}__unit": cell.get("unit"),
                    f"{name}__raw": cell.get("raw"),
                    f"{name}__src": cell.get("source_column"),
                }
                line.extend(csv_cell(getters.get(column)) for column in columns)
            line.append(json.dumps(record.get("unmapped_values", {}), ensure_ascii=False, sort_keys=True))
            writer.writerow(line)


def write_change_log(path, changelog):
    with path.open("w", encoding="utf-8") as handle:
        for entry in changelog:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def build_audit(audit_path, args, case_id, run_hash, dictionary, units_doc, sources,
                profiles, mappings, unmapped, cleaned, duplicates, changelog,
                reviews, anomalies, unknown_units, status, warnings, contract,
                unresolved_contract, error=None):
    lines = []
    add = lines.append
    add(f"# Audit — {TOOL_NAME} v{TOOL_VERSION}")
    add("")
    add("Synthetic/local runs of this audit are examples only, never official case answers.")
    add("")
    add("## Run identity")
    add(f"- case_id: `{case_id}`")
    add(f"- status: **{status}**")
    add(f"- input_sha256: `{run_hash}`")
    add(f"- case file: `{Path(args.case).name}`; task file: `{Path(args.task).name if args.task else '(none)'}`")
    add(f"- dictionary: `{dictionary.get('dictionary_id')}` schema_version `{dictionary.get('schema_version')}`")
    add(f"- unit table: `{units_doc.get('units_id')}` version `{units_doc.get('version')}`")
    add("- wall-clock timestamps are intentionally omitted so identical inputs produce byte-identical outputs.")
    if error:
        add("")
        add("## Error")
        add("```")
        add(error)
        add("```")
    add("")
    add("## Sources")
    for source in sources:
        add(f"- `{source['source_id']}` ({source['kind']}): {source.get('rows', 0)} rows")
    if warnings:
        add("")
        add("### Ingestion warnings")
        for warning in warnings:
            add(f"- {warning}")
    add("")
    add("## Schema profile and mapping")
    add(f"- profiled columns: {len(profiles)}; mapped: {len(mappings)}; unmapped: {len(unmapped)}")
    add("")
    add("| column | canonical field | component | confidence | rule | semantic type |")
    add("|---|---|---|---|---|---|")
    for key, mapping in mappings.items():
        add(f"| `{mapping['header']}` ({mapping['source_id']}) | `{mapping['canonical_field']}` | "
            f"{mapping.get('component') or ''} | {mapping['confidence']:.2f} | {mapping['rule']} | "
            f"{mapping['evidence']['profile_semantic_type']} |")
    for entry in unmapped:
        add(f"| `{entry['header']}` ({entry['source_id']}) | *(unmapped: {entry['reason']})* | | 0.00 | "
            f"see unresolved-schema.json | {entry['semantic_type']} |")
    add("")
    add("## Units and value cleaning")
    conversions = [c for c in changelog if c["rule"] == "UNIT-CONV"]
    range_splits = [c for c in changelog if c["rule"] == "RANGE-SPLIT"]
    add(f"- unit conversions applied: {len(conversions)} (every entry records formula, factor, offset and 12-significant-digit rounding)")
    formulas = sorted({c["evidence"]["formula"] for c in conversions})
    for formula in formulas:
        add(f"  - `{formula}`")
    add(f"- range splits (low/high preserved, no midpoint invented): {len(range_splits)}")
    add(f"- unknown units (no conversion, values left null, raw preserved): {len(unknown_units)}")
    for item in unknown_units.values():
        add(f"  - `{item['unit_text']}` (dimension {item['dimension']}) on {item['columns']}")
    add("")
    add("## Duplicate detection (conservative)")
    add(f"- groups flagged: {len(duplicates)}; no row was merged or dropped.")
    for group in duplicates:
        add(f"- `{group['duplicate_group']}` {group['status']}: rows {group['row_ids']}")
    add("- context keys come from dictionary `context_key: true`; rows with <2 non-empty context parts are not compared.")
    add("")
    add("## Missing values, anomalies and review")
    missing = [c for c in changelog if c["rule"] == "MISS-001"]
    add(f"- missing cells preserved as null: {len(missing)}")
    add(f"- anomalies: {len(anomalies)}; review items: {len(reviews)}")
    add(f"- unresolved output-contract fields: {len(unresolved_contract)} "
        f"{[u['field'] for u in unresolved_contract]}")
    add("")
    add("## Traceability and self-check")
    add("Every cleaned row keeps `raw` (original flattened record) and per-field `source_column`;")
    add("every changed value has a rule-coded entry in change-log.jsonl with old/new values and source locator.")
    add("Re-run with identical inputs and diff the output directory: all files must be byte-identical.")
    add("")
    audit_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_partial(out_dir, case_id, status, stage, message=""):
    payload = {"case_id": case_id, "status": status, "stage": stage,
               "skill": {"name": TOOL_NAME, "version": TOOL_VERSION},
               "sources": [], "uncertainty": [message] if message else [],
               "change_records": [], "artifacts": {},
               "unresolved_contract_fields": []}
    write_json(out_dir / "result.json", payload)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="schema_cartographer",
        description="Clean heterogeneous literature-extraction records: versioned header mapping, "
                    "semantic type inference, unit normalization, conservative duplicate flagging.")
    parser.add_argument("--case", default="/input/case.json", help="input case JSON (default /input/case.json)")
    parser.add_argument("--task", default="/input/task.md", help="task markdown for provenance (default /input/task.md)")
    parser.add_argument("--work", default="/app/work", help="scratch directory (default /app/work)")
    parser.add_argument("--out", default="/app/output", help="output directory (default /app/output)")
    parser.add_argument("--dictionary", default=str(DEFAULT_DICTIONARY),
                        help="editable field dictionary JSON (defaults to bundle references/)")
    parser.add_argument("--units", default=str(DEFAULT_UNITS),
                        help="editable unit table JSON (defaults to bundle references/)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    out_dir = Path(args.out)
    work_dir = Path(args.work)
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    case_path = Path(args.case)

    # Contract requirement: an honest partial result exists from the very first step.
    write_partial(out_dir, "unknown-case", "partial", "initialized",
                  "Run started; outputs not produced yet.")

    dictionary = units_doc = None
    status = "partial"
    try:
        if not case_path.is_file():
            raise FileNotFoundError(f"case file not found: {case_path}")
        dictionary = json.loads(Path(args.dictionary).read_text(encoding="utf-8"))
        units_doc = json.loads(Path(args.units).read_text(encoding="utf-8"))
        missing_tokens = set(dictionary.get("missing_tokens", []))

        case, rows, sources, warnings, case_text = ingest_case(case_path)
        case_id = find_case_id(case)
        task_text = ""
        task_path = Path(args.task) if args.task else None
        if task_path and task_path.is_file():
            task_text = task_path.read_text(encoding="utf-8", errors="replace")
        elif task_path:
            warnings.append(f"task file not found: {task_path}")
        run_hash = hashlib.sha256(
            (case_text + "\n" + task_text).encode("utf-8")).hexdigest()
        contract, contract_state = extract_contract(case)

        write_partial(out_dir, case_id, "partial", "ingested",
                      f"{len(rows)} raw rows ingested; mapping and cleaning pending.")
        if not rows:
            empty = {"case_id": case_id, "status": "input_error", "stage": "ingestion",
                     "skill": {"name": TOOL_NAME, "version": TOOL_VERSION},
                     "error": "No JSON record lists, embedded CSV material or readable CSV files were found in the case input.",
                     "sources": sources, "uncertainty": warnings,
                     "change_records": [], "artifacts": {"result": "result.json", "audit": "audit.md"},
                     "unresolved_contract_fields": []}
            for name in contract:
                empty[name] = None
            empty["unresolved_contract_fields"] = [
                {"field": name, "reason": "input_error_no_records"} for name in contract]
            write_json(out_dir / "result.json", empty)
            build_audit(out_dir / "audit.md", args, case_id, run_hash, dictionary,
                        units_doc, sources, {}, OrderedDict(), [], [], [], [], [],
                        [], {}, "input_error", warnings, contract,
                        empty["unresolved_contract_fields"],
                        error=empty["error"])
            return 2

        profiles = profile_columns(rows, missing_tokens)
        mapper = Mapper(dictionary, units_doc)
        unit_table = UnitTable(units_doc)
        mappings, unmapped, map_reviews = mapper.map_columns(profiles)
        unresolved = {"unmapped_columns": unmapped, "unknown_units": [],
                      "schema_version": dictionary.get("schema_version"),
                      "dictionary_id": dictionary.get("dictionary_id")}
        changelog, anomalies = [], []
        reviews = list(map_reviews)
        cleaner = Cleaner(dictionary, unit_table, mappings, changelog, reviews,
                          anomalies, unresolved)
        for key, mapping in mappings.items():
            changelog.append({"change_id": f"CH-{len(changelog)+1:06d}",
                              "rule": mapping["rule"], "scope": "column",
                              "row_id": None, "field": mapping["canonical_field"],
                              "source_column": key,
                              "old_value": mapping["header"],
                              "new_value": mapping["canonical_field"],
                              "evidence": mapping["evidence"] | {"confidence": mapping["confidence"]}})
        cleaned = cleaner.clean_rows(rows)
        unresolved["unknown_units"] = list(cleaner.unknown_units.values())
        duplicates = deduplicate(cleaned, dictionary["fields"], changelog, reviews)

        missing_list = [c for c in changelog if c["rule"] == "MISS-001"]
        unresolved["unresolved_contract_fields"] = []
        status = "success"
        uncertainty = []
        if unmapped:
            uncertainty.append(f"{len(unmapped)} columns could not be mapped to the canonical schema; "
                               "their raw values are preserved in unmapped_json and unresolved-schema.json.")
        if cleaner.unknown_units:
            uncertainty.append(f"{len(cleaner.unknown_units)} unknown unit(s) blocked conversion; "
                               "affected normalized values are null and raw values are preserved.")
        unitless = sum(1 for record in cleaned for cell in record["values"].values()
                       if "unit_missing" in cell.get("flags", []))
        if unitless:
            uncertainty.append(f"{unitless} numeric cell(s) carried no explicit unit: numbers kept verbatim "
                               "with unit=null; no default unit was assumed.")
        if any(g["status"] == "scientific_conflict_requires_human_adjudication" for g in duplicates):
            uncertainty.append("At least one duplicate-context value conflict needs human scientific adjudication; "
                               "no automatic merge was performed.")
        uncertainty.extend(warnings)
        if contract_state == "absent":
            uncertainty.append("case.json contained no output_contract; standard result fields were emitted and "
                               "unresolved_contract_fields is empty by construction.")

        artifacts = OrderedDict([
            ("cleaned_csv", "cleaned.csv"),
            ("cleaned_json", "cleaned.json"),
            ("mapping_report", "mapping-report.json"),
            ("unresolved_schema", "unresolved-schema.json"),
            ("review_queue", "review-queue.json"),
            ("change_log", "change-log.jsonl"),
            ("audit", "audit.md"),
            ("result", "result.json"),
        ])
        summary = {
            "raw_rows": len(rows), "cleaned_rows": len(cleaned),
            "profiled_columns": len(profiles), "mapped_columns": len(mappings),
            "unmapped_columns": len(unmapped),
            "unknown_units": len(cleaner.unknown_units),
            "unit_conversions": sum(1 for c in changelog if c["rule"] == "UNIT-CONV"),
            "range_splits": sum(1 for c in changelog if c["rule"] == "RANGE-SPLIT"),
            "missing_cells": len(missing_list), "anomalies": len(anomalies),
            "duplicate_groups": len(duplicates), "review_items": len(reviews),
            "change_records": len(changelog),
        }
        review_doc = {"missing": missing_list, "anomalies": anomalies, "reviews": reviews}
        mapping_doc = {"dictionary_id": dictionary.get("dictionary_id"),
                       "schema_version": dictionary.get("schema_version"),
                       "mappings": list(mappings.values()),
                       "unmapped_columns": unmapped,
                       "column_profiles": profiles}

        result = OrderedDict()
        result["case_id"] = case_id
        result["status"] = status
        result["skill"] = {"name": TOOL_NAME, "version": TOOL_VERSION}
        result["summary"] = summary
        result["sources"] = sources
        result["uncertainty"] = uncertainty
        result["change_records"] = changelog
        result["artifacts"] = artifacts
        result["duplicate_groups"] = duplicates
        result["review_required"] = bool(reviews or anomalies or unmapped or cleaner.unknown_units)
        result["input_sha256"] = run_hash

        pools = {
            "case_id": (case_id, None), "status": (status, None),
            "status_detail": (json.dumps(summary, ensure_ascii=False), None),
            "sources": (sources, None), "uncertainty": (uncertainty, None),
            "change_records": (changelog, "change-log.jsonl"),
            "change_log": (changelog, "change-log.jsonl"),
            "artifacts": (artifacts, None), "summary": (summary, None),
            "records": (cleaned, "cleaned.json"), "cleaned_records": (cleaned, "cleaned.json"),
            "cleaned_data": (cleaned, "cleaned.json"), "rows": (cleaned, "cleaned.json"),
            "review_queue": (review_doc, "review-queue.json"),
            "reviews": (reviews, "review-queue.json"),
            "mapping_report": (mapping_doc, "mapping-report.json"),
            "unresolved_schema": (unresolved, "unresolved-schema.json"),
            "duplicate_groups": (duplicates, None),
            "audit": (str(artifacts["audit"]), "audit.md"),
            "input_sha256": (run_hash, None),
        }
        unresolved_contract = []
        for name, expected_type in contract.items():
            value, note = coerce_contract_value(name, expected_type, pools)
            result[name] = value
            if note:
                unresolved_contract.append({"field": name, "expected_type": expected_type,
                                            "reason": note})
        result["unresolved_contract_fields"] = unresolved_contract
        unresolved["unresolved_contract_fields"] = unresolved_contract
        if unresolved_contract:
            result["uncertainty"].append(
                f"{len(unresolved_contract)} output_contract field(s) could not be filled faithfully; "
                "they are null and listed in unresolved_contract_fields (never fabricated).")

        # write all artifacts deterministically
        write_cleaned_csv(out_dir / "cleaned.csv", cleaned, dictionary["fields"])
        write_json(out_dir / "cleaned.json",
                   {"case_id": case_id, "schema_version": dictionary.get("schema_version"),
                    "records": cleaned})
        write_json(out_dir / "mapping-report.json", mapping_doc)
        write_json(out_dir / "unresolved-schema.json", unresolved)
        write_json(out_dir / "review-queue.json", review_doc)
        write_change_log(out_dir / "change-log.jsonl", changelog)
        write_json(out_dir / "result.json", result)
        build_audit(out_dir / "audit.md", args, case_id, run_hash, dictionary, units_doc,
                    sources, profiles, mappings, unmapped, cleaned, duplicates, changelog,
                    reviews, anomalies, cleaner.unknown_units, status, warnings,
                    contract, unresolved_contract)
        return 0
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        error = f"Invalid input: {exc}"
        status = "input_error"
    except FileNotFoundError as exc:
        error = str(exc)
        status = "input_error"
    except Exception:
        error = traceback.format_exc()
        status = "partial"
    case_id = locals().get("case_id", "unknown-case")
    payload = {"case_id": case_id, "status": status, "skill": {"name": TOOL_NAME, "version": TOOL_VERSION},
               "error": error, "sources": [], "uncertainty": ["Run did not complete; see error and audit.md."],
               "change_records": [], "artifacts": {"result": "result.json", "audit": "audit.md"},
               "unresolved_contract_fields": []}
    write_json(out_dir / "result.json", payload)
    audit = out_dir / "audit.md"
    audit.write_text(f"# Audit — {TOOL_NAME}\n\n- case_id: `{case_id}`\n- status: **{status}**\n\n"
                     f"## Error\n```\n{error}\n```\n", encoding="utf-8")
    return 2 if status == "input_error" else 1


if __name__ == "__main__":
    sys.exit(main())
