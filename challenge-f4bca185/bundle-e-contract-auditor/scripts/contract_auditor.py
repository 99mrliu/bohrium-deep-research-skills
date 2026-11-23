#!/usr/bin/env python3
"""Contract-aware literature extraction cleaner and independent auditor.

Python 3.10+, standard library only.  The run stage writes an honest partial
result before doing any expensive work; the verify stage re-reads the case and
artifacts and never trusts state left in memory by the run stage.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import unicodedata
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "1.0.0"
TOOL_NAME = "bundle-e-contract-auditor"
CORE_FIELDS = [
    "case_id",
    "result",
    "status",
    "sources",
    "uncertainty",
    "change_records",
    "coverage",
    "artifacts",
    "unresolved_fields",
]
ARTIFACT_FILES = {
    "cleaned_csv": "cleaned.csv",
    "cleaned_json": "cleaned.json",
    "anomalies": "anomalies.csv",
    "review_queue": "review_queue.csv",
    "change_records": "changes.jsonl",
    "validation": "validation.json",
    "checksums": "checksums.sha256",
    "manifest": "manifest.json",
    "audit": "audit.md",
    "result": "result.json",
}
PAYLOAD_FILES = [
    "cleaned.csv",
    "cleaned.json",
    "anomalies.csv",
    "review_queue.csv",
    "changes.jsonl",
    "audit.md",
    "result.json",
]
SEVERITIES = ("blocking", "error", "warning", "info")
MISSING_LITERALS = {
    "",
    "-",
    "--",
    "?",
    "na",
    "n/a",
    "nan",
    "none",
    "null",
    "missing",
    "not reported",
    "not available",
    "unreported",
    "unknown",
}
NUMERIC_OUTPUT_FIELDS = {
    "value",
    "value_min",
    "value_max",
    "conversion_factor",
    "conversion_offset",
    "source_decimal_places",
}
BASE_OUTPUT_FIELDS = [
    "input_row_id",
    "source_pointer",
    "row_status",
    "record_id",
    "source_id",
    "substance",
    "property",
    "value",
    "unit",
    "value_min",
    "value_max",
    "raw_value",
    "raw_unit",
    "conversion_rule",
    "conversion_formula",
    "conversion_factor",
    "conversion_offset",
    "conversion_change_id",
    "source_decimal_places",
    "source_record_sha256",
    "page",
    "paragraph",
    "table",
    "figure",
    "conditions",
    "context",
]
# Synonyms deliberately map only to stable scientific roles.  Unknown columns
# are never guessed; they are retained under unmapped__* and reviewed.
FIELD_ALIASES = {
    "record_id": {
        "record_id",
        "recordid",
        "extraction_id",
        "extractionid",
        "row_id",
        "rowid",
        "id",
        "entry_id",
        "entryid",
    },
    "source_id": {
        "source_id",
        "sourceid",
        "paper_id",
        "paperid",
        "document_id",
        "documentid",
        "paper_doi",
        "paperdoi",
        "document_doi",
        "documentdoi",
        "publication_id",
        "doi",
        "citation",
        "source",
        "reference",
        "ref",
    },
    "substance": {
        "substance",
        "material",
        "material_name",
        "materialname",
        "compound",
        "chemical",
        "chemical_name",
        "sample",
        "sample_name",
        "species",
        "analyte",
        "entity",
        "name",
    },
    "property": {
        "property",
        "property_name",
        "propertyname",
        "metric",
        "metric_name",
        "indicator",
        "parameter",
        "measurement",
        "measurement_name",
        "observable",
        "target_property",
    },
    "value": {
        "value",
        "numeric_value",
        "numericvalue",
        "property_value",
        "propertyvalue",
        "measurement_value",
        "measurementvalue",
        "measured_value",
        "measuredvalue",
        "result_value",
        "resultvalue",
        "mean",
        "average",
        "val",
        "y",
    },
    "unit": {
        "unit",
        "units",
        "value_unit",
        "valueunit",
        "property_unit",
        "propertyunit",
        "measurement_unit",
        "uom",
        "unit_of_measure",
    },
    "value_min": {
        "min",
        "minimum",
        "lower",
        "lower_bound",
        "lowerbound",
        "range_min",
        "rangemin",
        "value_min",
        "valuemin",
        "lo",
    },
    "value_max": {
        "max",
        "maximum",
        "upper",
        "upper_bound",
        "upperbound",
        "range_max",
        "rangemax",
        "value_max",
        "valuemax",
        "hi",
    },
    "page": {"page", "page_number", "pagenumber", "p", "pages"},
    "paragraph": {"paragraph", "para", "paragraph_id", "section", "section_id"},
    "table": {"table", "table_id", "tableid", "table_number", "tablenumber"},
    "figure": {"figure", "fig", "figure_id", "figureid", "figure_number"},
    "conditions": {
        "condition",
        "conditions",
        "experimental_conditions",
        "experiment_conditions",
        "test_conditions",
        "condition_id",
    },
    "context": {
        "context",
        "experiment",
        "experiment_id",
        "experimentid",
        "run_id",
        "runid",
        "method",
        "assay",
        "protocol",
        "sample_context",
        "notes",
        "note",
    },
}
ALIAS_TO_FIELD = {
    alias: canonical for canonical, aliases in FIELD_ALIASES.items() for alias in aliases
}


def norm_text(value: Any) -> str:
    """Unicode-normalized, lowercase token used for deterministic matching."""
    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    text = text.replace("μ", "µ")
    return re.sub(r"[\s\-_.:/\\()\[\]{}]+", "", text)


def safe_field_name(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    text = text.replace("μ", "µ")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")
    return text or "unnamed"


def json_stable(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_finite_json(value: Any, location: str = "$", problems: list[str] | None = None) -> list[str]:
    problems = problems if problems is not None else []
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        problems.append(location)
    elif isinstance(value, dict):
        for key, child in value.items():
            ensure_finite_json(child, f"{location}.{key}", problems)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            ensure_finite_json(child, f"{location}[{index}]", problems)
    return problems


def load_json_strict(path: Path) -> Any:
    def bad_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant {value!r} is not allowed")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return json.load(handle, parse_constant=bad_constant)


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass


def display_input_path(path: Path, declared: str | None = None) -> str:
    if declared:
        cleaned = declared.replace("\\", "/")
        if not Path(cleaned).is_absolute() and ".." not in Path(cleaned).parts:
            return cleaned
    return path.name


def source_pointer(source_name: str, key_path: str) -> str:
    return f"{source_name}#{key_path.lstrip('/')}"


def make_cell_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        return format(value, ".17g")
    if isinstance(value, Decimal):
        return format(value, "f") if value == value.to_integral() else format(value.normalize(), "f")
    if isinstance(value, (dict, list)):
        return json_stable(value)
    return str(value)


def parse_decimal(value: Any) -> tuple[Decimal | None, str | None, int | None]:
    """Return (number, interval_kind, decimal_places) for a scalar only.

    Missing markers are represented as (None, 'missing', None).  Malformed and
    interval values are deliberately not guessed here.
    """
    if value is None:
        return None, "missing", None
    if isinstance(value, bool):
        return None, "malformed", None
    if isinstance(value, (int, float, Decimal)):
        if isinstance(value, float) and not math.isfinite(value):
            return None, "malformed", None
        text = str(value)
    else:
        text = unicodedata.normalize("NFKC", str(value)).strip()
    if norm_text(text) in MISSING_LITERALS:
        return None, "missing", None
    if re.fullmatch(r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?(?:[eE][+-]?\d+)?", text):
        text = text.replace(",", "")
    if "_" in text:
        return None, "malformed", None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None, "malformed", None
    if not number.is_finite():
        return None, "malformed", None
    mantissa = re.split(r"[eE]", text, maxsplit=1)[0].replace(",", "")
    decimal_places = len(mantissa.split(".", 1)[1]) if "." in mantissa else 0
    try:
        float(number)
    except (OverflowError, ValueError):
        return None, "malformed", None
    return number, None, decimal_places


def split_interval(value: Any) -> tuple[str, str] | None:
    if not isinstance(value, str):
        return None
    text = unicodedata.normalize("NFKC", value).strip()
    match = re.match(r"^(.+?)\s*(?:–|—|~|≤\s*to\s*|to)\s*(.+)$", text, flags=re.IGNORECASE)
    if not match:
        return None
    left, right = match.group(1).strip(), match.group(2).strip()
    return (left, right) if left and right else None


class UnitDef:
    def __init__(
        self,
        canonical: str,
        dimension: str,
        factor: str,
        aliases: Iterable[str],
        preadd: str = "0",
    ) -> None:
        self.canonical = canonical
        self.dimension = dimension
        self.factor = Decimal(factor)
        self.preadd = Decimal(preadd)
        self.aliases = set(aliases) | {canonical}

    def to_base(self, value: Decimal) -> Decimal:
        return (value + self.preadd) * self.factor

    def from_base(self, value: Decimal) -> Decimal:
        return (value / self.factor) - self.preadd

    def raw_to_target_formula(self, target: "UnitDef") -> str:
        steps: list[str] = []
        if self.preadd != 0:
            steps.append(f"x0 = raw + {self.preadd}")
            current = "x0"
        else:
            current = "raw"
        if self.factor != 1:
            steps.append(f"x_base = {current} × {self.factor}")
        elif steps:
            steps.append("x_base = x0")
        else:
            steps.append("x_base = raw")
        if target.factor != 1:
            steps.append(f"x1 = x_base ÷ {target.factor}")
            current = "x1"
        else:
            current = "x_base"
        if target.preadd != 0:
            steps.append(f"target = {current} − {target.preadd}")
        elif current != "target":
            steps.append(f"target = {current}")
        return "; ".join(steps)


def norm_unit(value: Any) -> str:
    """Unit token normalization that preserves SI case distinctions (m vs M)."""
    text = unicodedata.normalize("NFKC", str(value)).strip()
    text = text.replace("μ", "µ")
    text = re.sub(r"[\s_]+", "", text)
    text = text.replace("（", "(").replace("）", ")")
    return text


def build_unit_registry() -> dict[str, UnitDef]:
    definitions = [
        ("m", "length", "1", ["meter", "metre", "meters", "metres"]),
        ("mm", "length", "0.001", ["millimeter", "millimetre", "millimeters"]),
        ("cm", "length", "0.01", ["centimeter", "centimetre"]),
        ("µm", "length", "0.000001", ["um", "micrometer", "micrometre", "micron", "microns", "μm"]),
        ("nm", "length", "0.000000001", ["nanometer", "nanometre"]),
        ("km", "length", "1000", ["kilometer", "kilometre"]),
        ("K", "temperature", "1", ["kelvin", "°k"]),
        ("°C", "temperature", "1", ["c", "celsius", "degc", "degreec", "℃"], "273.15"),
        ("°F", "temperature", "0.5555555555555555555555555556", ["f", "fahrenheit", "degf", "℉"], "459.67"),
        ("Pa", "pressure", "1", ["pascal", "pascals"]),
        ("kPa", "pressure", "1000", ["kilopascal", "kilopascals"]),
        ("MPa", "pressure", "1000000", ["megapascal", "megapascals"]),
        ("GPa", "pressure", "1000000000", ["gigapascal", "gigapascals"]),
        ("bar", "pressure", "100000", ["bars"]),
        ("mbar", "pressure", "100", ["millibar", "millibars"]),
        ("atm", "pressure", "101325", ["atmosphere", "atmospheres"]),
        ("mmHg", "pressure", "133.322387415", ["torr", "mm hg"]),
        ("psi", "pressure", "6894.757293168", ["poundpersquareinch"]),
        ("s", "time", "1", ["sec", "second", "seconds"]),
        ("ms", "time", "0.001", ["millisecond", "milliseconds"]),
        ("µs", "time", "0.000001", ["us", "microsecond", "microseconds", "μs"]),
        ("min", "time", "60", ["minute", "minutes"]),
        ("h", "time", "3600", ["hr", "hour", "hours"]),
        ("day", "time", "86400", ["days", "d"]),
        ("kg", "mass", "1", ["kilogram", "kilograms"]),
        ("g", "mass", "0.001", ["gram", "grams"]),
        ("mg", "mass", "0.000001", ["milligram", "milligrams"]),
        ("µg", "mass", "0.000000001", ["ug", "microgram", "micrograms", "μg"]),
        ("t", "mass", "1000", ["tonne", "tonnes", "metricton"]),
        ("m^3", "volume", "1", ["m3", "cubicmeter", "cubicmetre", "m³"]),
        ("L", "volume", "0.001", ["l", "liter", "litre", "liters", "litres"]),
        ("mL", "volume", "0.000001", ["ml", "milliliter", "millilitre", "cm3", "cc"]),
        ("µL", "volume", "0.000000001", ["ul", "microliter", "microlitre", "μl"]),
        ("m^2", "area", "1", ["m2", "squaremeter", "squaremetre", "㎡"]),
        ("cm^2", "area", "0.0001", ["cm2", "squarecentimeter", "squarecentimetre"]),
        ("mm^2", "area", "0.000001", ["mm2", "squaremillimeter"]),
        ("kg/m^3", "density", "1", ["kg/m3", "kgm-3", "kilogrampercubicmeter"]),
        ("g/cm^3", "density", "1000", ["g/cm3", "gcm-3", "grampercubiccentimeter"]),
        ("mol/L", "concentration", "1", ["M", "molar", "mol/liter", "mol/litre", "moldm-3"]),
        ("mmol/L", "concentration", "0.001", ["mM", "millimolar", "mmol/liter"]),
        ("µmol/L", "concentration", "0.000001", ["uM", "µM", "micromolar", "umol/l", "μmol/l"]),
        ("g/L", "mass_concentration", "1", ["gl-1", "gramperliter"]),
        ("mg/L", "mass_concentration", "0.001", ["mgl-1", "milligramperliter"]),
        ("mg/mL", "mass_concentration", "1", ["mgml-1", "milligrampermilliliter"]),
        ("1", "dimensionless", "1", ["dimensionless", "unitless", "none"]),
        ("%", "fraction_percent", "1", ["percent", "percentage", "pct"]),
        ("ppm", "fraction_percent", "0.0001", ["partspermillion"]),
        ("ppb", "fraction_percent", "0.0000001", ["partsperbillion"]),
        ("V", "voltage", "1", ["volt", "volts"]),
        ("mV", "voltage", "0.001", ["millivolt", "millivolts"]),
        ("kV", "voltage", "1000", ["kilovolt", "kilovolts"]),
        ("A", "current", "1", ["amp", "ampere", "amps", "amperes"]),
        ("mA", "current", "0.001", ["milliamp", "milliampere"]),
        ("µA", "current", "0.000001", ["ua", "microamp", "microampere", "μa"]),
        ("ohm", "resistance", "1", ["Ω", "ohms"]),
        ("kOhm", "resistance", "1000", ["kohm", "kilohm", "kΩ"]),
        ("Hz", "frequency", "1", ["hertz"]),
        ("kHz", "frequency", "1000", ["kilohertz"]),
        ("MHz", "frequency", "1000000", ["megahertz"]),
        ("GHz", "frequency", "1000000000", ["gigahertz"]),
        ("W", "power", "1", ["watt", "watts"]),
        ("mW", "power", "0.001", ["milliwatt", "milliwatts"]),
        ("kW", "power", "1000", ["kilowatt", "kilowatts"]),
        ("J", "energy", "1", ["joule", "joules"]),
        ("kJ", "energy", "1000", ["kilojoule", "kilojoules"]),
        ("MJ", "energy", "1000000", ["megajoule", "megajoules"]),
        ("eV", "energy", "0.0000000000000000001602176634", ["electronvolt", "electronvolts"]),
        ("meV", "energy", "0.0000000000000000000001602176634", ["millielectronvolt"]),
        ("Wh", "energy", "3600", ["watthour", "watthours"]),
        ("kWh", "energy", "3600000", ["kilowatthour", "kilowatthours"]),
        ("S/m", "conductivity", "1", ["sm-1", "siemenspermeter"]),
        ("S/cm", "conductivity", "100", ["scm-1", "siemenspercentimeter"]),
        ("mS/cm", "conductivity", "0.1", ["mscm-1", "millisiemenspercentimeter"]),
        ("mS/m", "conductivity", "0.001", ["msm-1", "millisiemenspermeter"]),
        ("A/m^2", "current_density", "1", ["a/m2", "am-2", "amperepersquaremeter"]),
        ("mA/cm^2", "current_density", "10", ["ma/cm2", "macm-2", "milliamperepersquarecentimeter"]),
        ("A/cm^2", "current_density", "10000", ["a/cm2", "acm-2"]),
        ("mAh/g", "specific_capacity", "1", ["mahg-1", "milliamperehourpergram"]),
        ("Ah/g", "specific_capacity", "1000", ["ahg-1", "amperehourpergram"]),
        ("mAh/kg", "specific_capacity", "0.001", ["mahkg-1"]),
        ("Pa·s", "viscosity", "1", ["pas", "pascalsecond", "pa.s"]),
        ("mPa·s", "viscosity", "0.001", ["mpas", "millipascalsecond", "cp", "centipoise"]),
    ]
    registry: dict[str, UnitDef] = {}
    for canonical, dimension, factor, aliases, *extra in definitions:
        preadd = extra[0] if extra else "0"
        unit = UnitDef(canonical, dimension, factor, aliases, preadd)
        for alias in unit.aliases:
            for key in (norm_unit(alias), norm_unit(alias).lower()):
                if key in registry:
                    # Deterministic collision behavior: the first explicit registry
                    # entry wins and the collision is documented in references.
                    continue
                registry[key] = unit
    return registry


UNIT_REGISTRY = build_unit_registry()
DIMENSION_DEFAULTS = {
    "length": "m",
    "temperature": "K",
    "pressure": "Pa",
    "time": "s",
    "mass": "kg",
    "volume": "m^3",
    "area": "m^2",
    "density": "kg/m^3",
    "concentration": "mol/L",
    "mass_concentration": "g/L",
    "dimensionless": "1",
    "fraction_percent": "%",
    "voltage": "V",
    "current": "A",
    "resistance": "ohm",
    "frequency": "Hz",
    "power": "W",
    "energy": "J",
    "conductivity": "S/m",
    "current_density": "A/m^2",
    "specific_capacity": "mAh/g",
    "viscosity": "Pa·s",
}


def lookup_unit(value: Any) -> UnitDef | None:
    if value is None:
        return None
    key = norm_unit(value)
    return UNIT_REGISTRY.get(key) or UNIT_REGISTRY.get(key.lower())


def canonical_unit_name(unit: UnitDef) -> str:
    return unit.canonical


class SourceRecord:
    def __init__(self, raw: Any, source_name: str, pointer: str, valid: bool = True) -> None:
        self.raw = raw
        self.source_name = source_name
        self.pointer = pointer
        self.valid = valid
        self.row_id = ""

    def stable_raw(self) -> dict[str, Any]:
        if isinstance(self.raw, dict):
            return self.raw
        return {"__invalid_record__": self.raw}

    def digest(self) -> str:
        return sha256_text(json_stable(self.stable_raw()))


class IngestionResult:
    def __init__(self, case: Any, records: list[SourceRecord], errors: list[dict[str, Any]], case_sha: str) -> None:
        self.case = case
        self.records = records
        self.errors = errors
        self.case_sha = case_sha


CONTAINER_KEYS = {
    "records",
    "rows",
    "extractions",
    "extractionrecords",
    "extraction_records",
    "datarecords",
    "data_records",
    "entries",
    "items",
    "observations",
    "literaturerecords",
    "literature_records",
}


def _looks_like_record(value: dict[str, Any]) -> bool:
    aliases = {norm_text(key) for key in value}
    return bool(aliases & set(ALIAS_TO_FIELD)) and not any(
        key in aliases for key in {"outputcontract", "properties", "required", "fieldmapping"}
    )


def _embedded_records(node: Any, pointer: str, source_name: str, found: list[SourceRecord], seen: set[int]) -> None:
    node_id = id(node)
    if node_id in seen:
        return
    seen.add(node_id)
    if isinstance(node, dict):
        for key in sorted(node, key=lambda item: str(item)):
            child = node[key]
            key_norm = norm_text(key)
            child_pointer = f"{pointer}/{safe_field_name(key)}"
            if key_norm in CONTAINER_KEYS:
                if isinstance(child, list):
                    for index, item in enumerate(child):
                        found.append(
                            SourceRecord(
                                item,
                                source_name,
                                f"{child_pointer}/{index}",
                                valid=isinstance(item, dict),
                            )
                        )
                    continue
                if isinstance(child, dict) and _looks_like_record(child):
                    found.append(SourceRecord(child, source_name, child_pointer, valid=True))
                    continue
            _embedded_records(child, child_pointer, source_name, found, seen)
    elif isinstance(node, list):
        if pointer == "" and node and all(isinstance(item, dict) for item in node) and all(
            _looks_like_record(item) for item in node
        ):
            for index, item in enumerate(node):
                found.append(SourceRecord(item, source_name, f"/{index}", valid=True))
            return
        for index, child in enumerate(node):
            _embedded_records(child, f"{pointer}/{index}", source_name, found, seen)


def _declared_csv_files(node: Any, declared: list[str], seen: set[int]) -> None:
    node_id = id(node)
    if node_id in seen:
        return
    seen.add(node_id)
    if isinstance(node, dict):
        path_value = None
        format_value = ""
        for key, value in node.items():
            key_norm = norm_text(key)
            if key_norm in {"path", "file", "filename", "filepath"} and isinstance(value, str):
                path_value = value
            if key_norm in {"format", "type", "mediatype"}:
                format_value = str(value).lower()
        if path_value and (format_value == "csv" or path_value.lower().endswith(".csv")):
            declared.append(path_value)
        for key in sorted(node, key=lambda item: str(item)):
            _declared_csv_files(node[key], declared, seen)
    elif isinstance(node, list):
        for child in node:
            _declared_csv_files(child, declared, seen)


def flatten_record(raw: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}

    def visit(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            if not value:
                flattened[prefix] = None
            for key in sorted(value, key=lambda item: str(item)):
                child_name = f"{prefix}.{key}" if prefix else str(key)
                visit(child_name, value[key])
        elif isinstance(value, list):
            flattened[prefix] = json_stable(value) if value else None
        else:
            flattened[prefix] = value

    for key in sorted(raw, key=lambda item: str(item)):
        visit(str(key), raw[key])
    return flattened


def read_csv_records(path: Path, source_name: str) -> tuple[list[SourceRecord], list[dict[str, Any]], str]:
    errors: list[dict[str, Any]] = []
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        return [], [{"code": "INPUT_FILE_UNREADABLE", "severity": "blocking", "message": str(exc), "path": source_name}], ""
    digest = sha256_bytes(raw_bytes)
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        return [], [{"code": "INPUT_CSV_ENCODING", "severity": "blocking", "message": str(exc), "path": source_name}], digest
    records: list[SourceRecord] = []
    try:
        reader = csv.DictReader(text.splitlines())
        if not reader.fieldnames:
            errors.append({"code": "INPUT_CSV_EMPTY", "severity": "blocking", "message": "CSV has no header", "path": source_name})
            return records, errors, digest
        normalized_headers = [str(header) for header in reader.fieldnames]
        duplicate_headers = sorted({h for h in normalized_headers if normalized_headers.count(h) > 1})
        if duplicate_headers:
            errors.append(
                {
                    "code": "INPUT_CSV_DUPLICATE_HEADER",
                    "severity": "blocking",
                    "message": f"duplicate CSV headers: {', '.join(duplicate_headers)}",
                    "path": source_name,
                }
            )
            return records, errors, digest
        for index, row in enumerate(reader):
            extra = row.pop(None, None)
            if extra:
                errors.append(
                    {
                        "code": "INPUT_CSV_RAGGED_ROW",
                        "severity": "error",
                        "message": "row contains cells beyond the header",
                        "path": source_name,
                        "row_index": index,
                    }
                )
            records.append(SourceRecord(row, source_name, f"/rows/{index}", valid=True))
    except csv.Error as exc:
        errors.append({"code": "INPUT_CSV_PARSE", "severity": "blocking", "message": str(exc), "path": source_name})
    return records, errors, digest


def ingest_case(case_path: Path) -> IngestionResult:
    try:
        raw_bytes = case_path.read_bytes()
    except OSError as exc:
        return IngestionResult(
            None,
            [],
            [{"code": "INPUT_CASE_UNREADABLE", "severity": "blocking", "message": str(exc), "path": case_path.name}],
            "",
        )
    case_sha = sha256_bytes(raw_bytes)
    try:
        case = json.loads(
            raw_bytes.decode("utf-8-sig"),
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"non-finite JSON constant {value!r}")),
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        return IngestionResult(
            None,
            [],
            [{"code": "INPUT_CASE_INVALID", "severity": "blocking", "message": str(exc), "path": case_path.name}],
            case_sha,
        )
    records: list[SourceRecord] = []
    errors: list[dict[str, Any]] = []
    if isinstance(case, dict) or isinstance(case, list):
        _embedded_records(case, "", case_path.name, records, set())
    else:
        errors.append({"code": "INPUT_CASE_SHAPE", "severity": "blocking", "message": "case root must be an object or array"})
    declared: list[str] = []
    _declared_csv_files(case, declared, set())
    unique_declared = sorted(set(declared))
    for declared_path in unique_declared:
        candidate = Path(declared_path)
        if not candidate.is_absolute():
            candidate = case_path.parent / candidate
        csv_records, csv_errors, _digest = read_csv_records(candidate, display_input_path(candidate, declared_path))
        records.extend(csv_records)
        errors.extend(csv_errors)
    if not records and not errors and isinstance(case, dict) and _looks_like_record(case):
        records.append(SourceRecord(case, case_path.name, "", valid=True))
    for index, record in enumerate(records, start=1):
        record.row_id = f"R{index:06d}"
    return IngestionResult(case, records, errors, case_sha)


def deep_get_any(data: Any, names: Iterable[str]) -> Any:
    wanted = {norm_text(name) for name in names}

    def visit(node: Any, seen: set[int]) -> Any:
        if id(node) in seen:
            return None
        seen.add(id(node))
        if isinstance(node, dict):
            for key, value in node.items():
                if norm_text(key) in wanted:
                    return value
            for key in sorted(node, key=lambda item: str(item)):
                result = visit(node[key], seen)
                if result is not None:
                    return result
        elif isinstance(node, list):
            for item in node:
                result = visit(item, seen)
                if result is not None:
                    return result
        return None

    return visit(data, set()) if data is not None else None


def contract_keys_from(contract: Any) -> list[str]:
    def from_item(item: Any) -> str | None:
        if isinstance(item, str):
            text = item.strip().strip("`'\"")
            text = re.split(r"\s*[(:=]\s*", text, maxsplit=1)[0].strip()
            return text if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", text) else None
        if isinstance(item, dict):
            for key in ("name", "field", "key", "property"):
                if isinstance(item.get(key), str):
                    return item[key]
        return None

    keys: list[str] = []
    if isinstance(contract, dict):
        wrappers = [contract[wrapper] for wrapper in ("fields", "required", "properties", "output_fields", "keys", "schema") if wrapper in contract]
        if not wrappers:
            wrappers = [contract]
        for source in wrappers:
            if isinstance(source, dict):
                keys.extend(str(key) for key in source)
            elif isinstance(source, list):
                keys.extend(key for key in (from_item(item) for item in source) if key)
            elif isinstance(source, str):
                keys.extend(contract_keys_from(source))
    elif isinstance(contract, list):
        keys.extend(key for key in (from_item(item) for item in contract) if key)
    elif isinstance(contract, str):
        text = contract.strip()
        try:
            return contract_keys_from(json.loads(text))
        except (ValueError, json.JSONDecodeError):
            pass
        candidates = re.split(r"[\n,;]+", text)
        for candidate in candidates:
            key = from_item(candidate)
            if key:
                keys.append(key)
    result: list[str] = []
    for key in keys:
        if key not in result:
            result.append(key)
    return result


def contract_from_task(task_text: str) -> list[str]:
    patterns = list(re.finditer(r"output[_ -]?contract", task_text, flags=re.IGNORECASE))
    decoder = json.JSONDecoder()
    for match in patterns:
        tail = task_text[match.end() :]
        colon = tail.find(":")
        if colon < 0:
            continue
        candidate = tail[colon + 1 :].lstrip()
        try:
            parsed, _end = decoder.raw_decode(candidate)
            return contract_keys_from(parsed)
        except (ValueError, json.JSONDecodeError):
            pass
    # Heading/list form: output_contract followed by - field lines.
    for match in patterns:
        lines = task_text[match.end() :].splitlines()[1:15]
        found: list[str] = []
        for line in lines:
            item = re.match(r"\s*(?:[-*]|\d+[.)])\s*([A-Za-z_][A-Za-z0-9_.-]*)", line)
            if item:
                found.append(item.group(1))
            elif found and line.strip() and not line.startswith((" ", "\t", "-", "*")):
                break
        if found:
            return found
    return []


def extract_contract(case: Any, task_text: str) -> list[str]:
    contract = deep_get_any(case, ["output_contract", "outputContract", "output contract", "contract"])
    keys = contract_keys_from(contract)
    if keys:
        return keys
    return contract_from_task(task_text)


def extract_case_id(case: Any) -> str | None:
    value = deep_get_any(case, ["case_id", "caseId", "case id", "id", "case"])
    if isinstance(value, (str, int)) and str(value).strip():
        return str(value).strip()
    return None


def mapping_from_case(case: Any) -> dict[str, str]:
    mapping: dict[str, str] = {}
    raw_mapping = deep_get_any(case, ["field_mapping", "fieldMapping", "column_mapping", "schema_mapping"])
    if isinstance(raw_mapping, dict):
        for left, right in raw_mapping.items():
            if isinstance(right, list):
                target = str(left)
                for alias in right:
                    mapping[norm_text(alias)] = safe_field_name(target)
            elif isinstance(right, str):
                left_norm = norm_text(left)
                right_norm = norm_text(right)
                if left_norm in FIELD_ALIASES or left_norm in BASE_OUTPUT_FIELDS:
                    mapping[right_norm] = safe_field_name(left)
                else:
                    mapping[left_norm] = safe_field_name(right)
    return mapping


def target_units_from_case(case: Any) -> dict[str, str]:
    raw = deep_get_any(case, ["target_units", "targetUnits", "unit_targets", "standard_units"])
    result: dict[str, str] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(value, str):
                result[norm_text(key)] = value
            elif isinstance(value, dict):
                for child_key, child_value in value.items():
                    if isinstance(child_value, str):
                        result[norm_text(child_key)] = child_value
    return result


class Cleaner:
    def __init__(self, case: Any, max_rows: int = 50000) -> None:
        self.case = case
        self.max_rows = max_rows
        self.case_mapping = mapping_from_case(case)
        self.target_units = target_units_from_case(case)
        self.anomalies: list[dict[str, Any]] = []
        self.changes: list[dict[str, Any]] = []
        self.review: list[dict[str, Any]] = []
        self.headers = list(BASE_OUTPUT_FIELDS)
        self.clean_rows: list[dict[str, Any]] = []
        self.coverage_rows: list[dict[str, Any]] = []
        self._change_counter = 0

    def add_anomaly(
        self,
        severity: str,
        code: str,
        message: str,
        row: SourceRecord | None = None,
        field: str | None = None,
        rule_id: str | None = None,
        details: dict[str, Any] | None = None,
        affected_rows: list[str] | None = None,
    ) -> None:
        item = {
            "_original_index": len(self.anomalies),
            "severity": severity,
            "code": code,
            "input_row_id": row.row_id if row else None,
            "source_pointer": source_pointer(row.source_name, row.pointer) if row else None,
            "field": field,
            "rule_id": rule_id,
            "message": message,
            "details": details or {},
        }
        if affected_rows:
            item["affected_rows"] = affected_rows
        self.anomalies.append(item)
        if severity in {"blocking", "error", "warning"} and code != "BUDGET_EXCLUDED":
            self.review.append(
                {
                    "anomaly_index": len(self.anomalies) - 1,
                    "severity": severity,
                    "input_row_id": item["input_row_id"],
                    "source_pointer": item["source_pointer"],
                    "field": field,
                    "issue": f"{code}: {message}",
                    "raw_value": (details or {}).get("raw_value"),
                    "suggested_action": suggested_action(code),
                    "status": "open",
                    "resolution": None,
                    "owner": None,
                }
            )

    def add_change(
        self,
        row: SourceRecord,
        field: str,
        before: Any,
        after: Any,
        action: str,
        rule_id: str,
        reason: str,
        raw_field: str | None = None,
        conversion: dict[str, Any] | None = None,
    ) -> str:
        self._change_counter += 1
        change_id = f"C{self._change_counter:06d}"
        record = {
            "change_id": change_id,
            "rule_id": rule_id,
            "input_row_id": row.row_id,
            "source_pointer": source_pointer(row.source_name, row.pointer),
            "raw_field": raw_field,
            "field": field,
            "before": before,
            "after": after,
            "action": action,
            "reason": reason,
        }
        if conversion:
            record["conversion"] = conversion
        self.changes.append(record)
        return change_id

    def canonical_for(self, raw_field: str) -> str | None:
        key = norm_text(raw_field)
        if key in self.case_mapping:
            return self.case_mapping[key]
        return ALIAS_TO_FIELD.get(key)

    def _target_for(self, raw_unit: UnitDef, property_value: Any) -> tuple[UnitDef | None, str | None]:
        candidates = [norm_text(property_value), raw_unit.dimension, "*"]
        target_name: str | None = None
        for candidate in candidates:
            if candidate and candidate in self.target_units:
                target_name = self.target_units[candidate]
                break
        if target_name is None:
            target_name = DIMENSION_DEFAULTS.get(raw_unit.dimension)
        target = lookup_unit(target_name)
        if target is None:
            return None, target_name
        if target.dimension != raw_unit.dimension:
            return None, target_name
        return target, target_name

    def _convert_decimal(self, value: Decimal, raw_unit: UnitDef, target: UnitDef) -> Decimal:
        with localcontext() as context:
            context.prec = 40
            base = raw_unit.to_base(value)
            return target.from_base(base)

    def _decimal_to_float(self, value: Decimal) -> float | None:
        try:
            converted = float(value)
        except (OverflowError, ValueError):
            return None
        return converted if math.isfinite(converted) else None

    def _conversion_trace(self, raw: Any, raw_unit: UnitDef, target: UnitDef, output: Decimal) -> dict[str, Any]:
        same_scale = raw_unit.preadd == 0 and target.preadd == 0
        factor = offset = None
        if same_scale:
            with localcontext() as context:
                context.prec = 40
                factor = raw_unit.factor / target.factor
                offset = Decimal("0")
        return {
            "raw_value": make_cell_string(raw),
            "raw_unit": raw_unit.canonical,
            "target_unit": target.canonical,
            "factor": self._decimal_to_float(factor) if factor is not None else None,
            "offset": self._decimal_to_float(offset) if offset is not None else None,
            "formula": raw_unit.raw_to_target_formula(target),
            "output": self._decimal_to_float(output),
        }

    def _standardize_unit_only(self, row: SourceRecord, output: dict[str, Any], raw_unit_value: Any) -> None:
        """Standardize a reported unit when no trustworthy numeric value exists."""
        if raw_unit_value is None or norm_text(raw_unit_value) in MISSING_LITERALS:
            output["unit"] = None
            return
        raw_unit = lookup_unit(raw_unit_value)
        if raw_unit is None:
            output["unit"] = None
            self.add_anomaly("error", "UNKNOWN_UNIT", "unit is not in the deterministic registry; unit remains null", row, "unit", "U003", {"raw_value": raw_unit_value})
            return
        target, target_name = self._target_for(raw_unit, output.get("property"))
        if target is None:
            output["unit"] = None
            self.add_anomaly("error", "UNKNOWN_TARGET_UNIT", f"target unit {target_name!r} is unavailable or dimension-incompatible", row, "unit", "U003", {"raw_value": target_name})
            return
        output["unit"] = target.canonical
        if make_cell_string(raw_unit_value) != raw_unit.canonical:
            self.add_change(row, "unit", make_cell_string(raw_unit_value), target.canonical, "normalize_unit_alias", "U001", "unit alias standardized even though the numeric value is unavailable", "unit")

    def _process_numeric_cell(
        self,
        row: SourceRecord,
        output: dict[str, Any],
        raw_value: Any,
        raw_unit_value: Any,
        raw_field: str,
    ) -> None:
        output["raw_value"] = make_cell_string(raw_value) if raw_value is not None else None
        output["raw_unit"] = make_cell_string(raw_unit_value) if raw_unit_value is not None else None
        interval = split_interval(raw_value)
        if interval:
            output["value"] = None
            self.add_anomaly(
                "warning",
                "INTERVAL_VALUE",
                "interval was decomposed into min/max; midpoint was not fabricated",
                row,
                "value",
                "V003",
                {"raw_value": raw_value},
            )
            left_number, left_state, left_places = parse_decimal(interval[0])
            right_number, right_state, right_places = parse_decimal(interval[1])
            output["source_decimal_places"] = max(left_places or 0, right_places or 0)
            if left_number is None:
                self.add_anomaly("error", "MALFORMED_INTERVAL_MIN", f"interval lower bound is {left_state}", row, "value_min", "V004", {"raw_value": interval[0]})
            if right_number is None:
                self.add_anomaly("error", "MALFORMED_INTERVAL_MAX", f"interval upper bound is {right_state}", row, "value_max", "V004", {"raw_value": interval[1]})
            if left_number is not None and right_number is not None and left_number > right_number:
                self.add_anomaly("error", "INTERVAL_BOUNDS_REVERSED", "interval lower bound exceeds upper bound", row, "value", "V004", {"raw_value": raw_value})
            self._convert_range(row, output, left_number, right_number, raw_unit_value)
            return
        number, state, decimal_places = parse_decimal(raw_value)
        output["source_decimal_places"] = decimal_places
        if state == "missing":
            if raw_value is not None and norm_text(raw_value) not in {""}:
                self.add_change(row, "value", make_cell_string(raw_value), None, "normalize_missing", "V001", "missing marker normalized to null", raw_field)
            self.add_anomaly("warning", "MISSING_VALUE", "numeric value is missing and remains null", row, "value", "V001", {"raw_value": raw_value})
            self._standardize_unit_only(row, output, raw_unit_value)
            return
        if state == "malformed" or number is None:
            output["value"] = None
            self.add_anomaly("error", "MALFORMED_NUMBER", "numeric value could not be parsed; original text is retained only in raw_value", row, "value", "V004", {"raw_value": raw_value})
            self._standardize_unit_only(row, output, raw_unit_value)
            return
        if raw_unit_value is None or norm_text(raw_unit_value) in MISSING_LITERALS:
            converted = self._decimal_to_float(number)
            output["value"] = converted
            output["unit"] = None
            self.add_change(row, "value", make_cell_string(raw_value), converted, "parse_numeric", "V002", "scalar parsed; no unit was assumed", raw_field)
            self.add_anomaly("warning", "MISSING_UNIT", "numeric value has no unit; value was not assigned a standard unit", row, "unit", "U004", {"raw_value": raw_value})
            return
        raw_unit = lookup_unit(raw_unit_value)
        if raw_unit is None:
            output["value"] = None
            output["unit"] = None
            self.add_anomaly("error", "UNKNOWN_UNIT", "unit is not in the deterministic registry; normalized value remains null", row, "unit", "U003", {"raw_value": raw_unit_value})
            return
        target, target_name = self._target_for(raw_unit, output.get("property"))
        if target is None:
            output["value"] = None
            output["unit"] = None
            self.add_anomaly("error", "UNKNOWN_TARGET_UNIT", f"target unit {target_name!r} is unavailable or dimension-incompatible", row, "unit", "U003", {"raw_value": target_name})
            return
        converted_decimal = self._convert_decimal(number, raw_unit, target)
        converted = self._decimal_to_float(converted_decimal)
        if converted is None:
            self.add_anomaly("blocking", "NONFINITE_CONVERSION", "conversion overflowed the finite JSON number domain", row, "value", "U002", {"raw_value": raw_value})
            return
        output["value"] = converted
        output["unit"] = target.canonical
        output["conversion_rule"] = "U002"
        output["conversion_formula"] = raw_unit.raw_to_target_formula(target)
        trace = self._conversion_trace(raw_value, raw_unit, target, converted_decimal)
        output["conversion_factor"] = trace["factor"]
        output["conversion_offset"] = trace["offset"]
        change_id = self.add_change(
            row,
            "value",
            make_cell_string(raw_value),
            converted,
            "unit_convert",
            "U002",
            f"{raw_unit.canonical} converted to {target.canonical} with recorded formula",
            raw_field,
            trace,
        )
        output["conversion_change_id"] = change_id
        if make_cell_string(raw_unit_value) != raw_unit.canonical:
            self.add_change(row, "unit", make_cell_string(raw_unit_value), raw_unit.canonical, "normalize_unit_alias", "U001", "unit alias normalized without changing value", "unit")

    def _convert_range(self, row: SourceRecord, output: dict[str, Any], left: Decimal | None, right: Decimal | None, raw_unit_value: Any) -> None:
        if left is None and right is None:
            return
        if raw_unit_value is None or norm_text(raw_unit_value) in MISSING_LITERALS:
            output["unit"] = None
            output["value_min"] = self._decimal_to_float(left) if left is not None else None
            output["value_max"] = self._decimal_to_float(right) if right is not None else None
            self.add_anomaly("warning", "MISSING_UNIT", "interval has no unit; no unit was assumed", row, "unit", "U004", {"raw_value": output.get("raw_value")})
            return
        raw_unit = lookup_unit(raw_unit_value)
        if raw_unit is None:
            output["unit"] = None
            self.add_anomaly("error", "UNKNOWN_UNIT", "interval unit is unknown; min/max remain null", row, "unit", "U003", {"raw_value": raw_unit_value})
            return
        target, target_name = self._target_for(raw_unit, output.get("property"))
        if target is None:
            output["unit"] = None
            self.add_anomaly("error", "UNKNOWN_TARGET_UNIT", f"target unit {target_name!r} is unavailable", row, "unit", "U003", {"raw_value": target_name})
            return
        for field, value in (("value_min", left), ("value_max", right)):
            if value is None:
                continue
            converted_decimal = self._convert_decimal(value, raw_unit, target)
            converted = self._decimal_to_float(converted_decimal)
            output[field] = converted
            self.add_change(row, field, str(value), converted, "unit_convert", "U002", f"interval endpoint converted from {raw_unit.canonical} to {target.canonical}", field, self._conversion_trace(str(value), raw_unit, target, converted_decimal))
        output["unit"] = target.canonical
        output["conversion_rule"] = "U002"
        output["conversion_formula"] = raw_unit.raw_to_target_formula(target)

    def process(self, records: list[SourceRecord], ingest_errors: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        for error in ingest_errors or []:
            self.add_anomaly(
                error.get("severity", "blocking"),
                error.get("code", "INPUT_ERROR"),
                error.get("message", "input error"),
                None,
                None,
                "I001",
                {key: value for key, value in error.items() if key not in {"severity", "code", "message"}},
            )
        processed: list[tuple[SourceRecord, dict[str, Any], str]] = []
        identity_by_key: dict[str, list[int]] = {}
        record_id_indexes: dict[str, list[int]] = {}
        limit = self.max_rows if self.max_rows > 0 else None
        for index, record in enumerate(records):
            if limit is not None and index >= limit:
                self.add_anomaly("error", "BUDGET_EXCLUDED", "row exceeded max_rows budget and was rejected without being changed", record, None, "B001")
                self.coverage_rows.append(coverage_item(record, "rejected", None, None, "max_rows budget exceeded"))
                continue
            if not record.valid or not isinstance(record.raw, dict):
                self.add_anomaly("error", "MALFORMED_RECORD", "input row is not an object and was rejected", record, None, "I002", {"raw_value": make_cell_string(record.raw)})
                self.coverage_rows.append(coverage_item(record, "rejected", None, None, "record is not a JSON/CSV object"))
                continue
            flattened = flatten_record(record.raw)
            if not flattened or all(value is None or norm_text(value) in MISSING_LITERALS for value in flattened.values()):
                self.add_anomaly("warning", "EMPTY_RECORD", "record has no reported values and was rejected", record, None, "I003")
                self.coverage_rows.append(coverage_item(record, "rejected", None, None, "all cells are missing"))
                continue
            output = {field: None for field in BASE_OUTPUT_FIELDS}
            output["input_row_id"] = record.row_id
            output["source_pointer"] = source_pointer(record.source_name, record.pointer)
            output["row_status"] = "kept"
            output["source_record_sha256"] = record.digest()
            grouped: dict[str, list[tuple[str, Any]]] = {}
            unknown: dict[str, Any] = {}
            for raw_field in sorted(flattened):
                raw_value = flattened[raw_field]
                canonical = self.canonical_for(raw_field)
                if canonical is None:
                    unmapped_name = f"unmapped__{safe_field_name(raw_field)}"
                    unknown[unmapped_name] = raw_value
                    self.add_anomaly("error", "UNMAPPED_COLUMN", "column has no deterministic mapping and was retained with an unmapped__ prefix", record, raw_field, "S004", {"raw_value": raw_value})
                    self.add_change(record, unmapped_name, raw_value, raw_value, "retain_unmapped_column", "S004", "unknown field retained losslessly; no semantic mapping guessed", raw_field)
                    continue
                grouped.setdefault(canonical, []).append((raw_field, raw_value))
            for canonical in sorted(grouped):
                candidates = grouped[canonical]
                nonmissing = [(field, value) for field, value in candidates if value is not None and norm_text(value) not in MISSING_LITERALS]
                distinct: list[tuple[str, Any]] = []
                for field, value in nonmissing:
                    if all(json_stable(value) != json_stable(existing) for _old, existing in distinct):
                        distinct.append((field, value))
                if len(distinct) > 1:
                    self.add_anomaly("error", "FIELD_VALUE_CONFLICT", "multiple source columns map to one canonical field with different values; no value was selected or merged", record, canonical, "S003", {"candidates": {field: value for field, value in candidates}})
                    output[canonical] = None
                    for field, value in candidates:
                        retained_name = f"unmapped__{safe_field_name(field)}"
                        unknown[retained_name] = value
                    continue
                chosen_field, chosen_value = candidates[0]
                if nonmissing:
                    chosen_field, chosen_value = nonmissing[0]
                normalized = normalize_scalar(chosen_value)
                output[canonical] = normalized
                if safe_field_name(chosen_field) != canonical:
                    self.add_change(record, canonical, chosen_value, normalized, "rename_field", "S001", f"source column {chosen_field!r} mapped to canonical field {canonical!r}", chosen_field)
                elif json_stable(chosen_value) != json_stable(normalized):
                    self.add_change(record, canonical, chosen_value, normalized, "normalize_scalar", "S002", "scalar whitespace/type representation normalized", chosen_field)
            # Explicit min/max columns supplement a scalar value.  An interval in
            # `value` has already decomposed and converted its own bounds, so it
            # must not be converted a second time.
            value_was_interval = split_interval(output.get("value")) is not None
            self._process_numeric_cell(record, output, output.get("value"), output.get("unit"), "value")
            if not value_was_interval:
                for field in ("value_min", "value_max"):
                    if output.get(field) is not None:
                        number, state, _places = parse_decimal(output[field])
                        if number is None:
                            self.add_anomaly("error", "MALFORMED_NUMBER", f"explicit {field} is {state}; value left null", record, field, "V004", {"raw_value": output.get(field)})
                            output[field] = None
                        else:
                            unit = lookup_unit(output.get("raw_unit"))
                            if unit:
                                target, target_name = self._target_for(unit, output.get("property"))
                                if target:
                                    converted_decimal = self._convert_decimal(number, unit, target)
                                    converted = self._decimal_to_float(converted_decimal)
                                    self.add_change(record, field, output[field], converted, "unit_convert", "U002", f"explicit bound converted from {unit.canonical} to {target.canonical}", field, self._conversion_trace(output[field], unit, target, converted_decimal))
                                    output[field] = converted
                                    output["unit"] = target.canonical
                            else:
                                output[field] = self._decimal_to_float(number)
            for key, value in sorted(unknown.items()):
                output[key] = normalize_scalar(value)
                if key not in self.headers:
                    self.headers.append(key)
            identity_payload = {
                key: value
                for key, value in output.items()
                if key not in {"input_row_id", "source_pointer", "row_status", "record_id", "source_record_sha256", "conversion_change_id"}
            }
            identity_hash = sha256_text(json_stable(identity_payload))
            processed.append((record, output, identity_hash))
            identity_by_key.setdefault(identity_hash, []).append(len(processed) - 1)
            record_id = make_cell_string(output.get("record_id"))
            if record_id:
                record_id_indexes.setdefault(record_id, []).append(len(processed) - 1)
        duplicate_of: dict[int, int] = {}
        # Auto-deduplicate only exact identity plus the same explicit record ID.
        # Same values under different IDs stay separate and are sent to review;
        # this prevents repeated experiments from being silently merged.
        for record_id, indexes in sorted(record_id_indexes.items()):
            for position in indexes[1:]:
                first = indexes[0]
                if identity_by_key and list(identity_by_key)[0] is not None and processed[position][2] == processed[first][2]:
                    duplicate_of[position] = first
                    self.add_change(processed[position][0], "__row__", processed[position][1]["source_pointer"], processed[first][1]["input_row_id"], "deduplicate_row", "D001", "exact identity and explicit record_id match; duplicate row excluded, never merged", "record_id")
                    self.add_anomaly("info", "EXACT_DUPLICATE_REMOVED", "duplicate extraction removed by record_id plus full-context identity key", processed[position][0], "record_id", "D001", {"kept_row": processed[first][1]["input_row_id"]})
        conflict_groups = [
            (record_id, indexes)
            for record_id, indexes in record_id_indexes.items()
            if len([index for index in indexes if index not in duplicate_of]) > 1
            and len({processed[index][2] for index in indexes if index not in duplicate_of}) > 1
        ]
        for record_id, indexes in sorted(conflict_groups):
            active = [index for index in indexes if index not in duplicate_of]
            self.add_anomaly(
                "error",
                "DUPLICATE_ID_CONFLICT",
                "same record_id has different scientific/context values; rows were kept separate and never merged",
                processed[active[0]][0],
                "record_id",
                "D002",
                {"record_id": record_id},
                [processed[index][1]["input_row_id"] for index in active],
            )
            for index in active:
                processed[index][1]["row_status"] = "flagged"
        for identity_hash, indexes in sorted(identity_by_key.items()):
            active = [index for index in indexes if index not in duplicate_of]
            if len(active) > 1:
                ids = {make_cell_string(processed[index][1].get("record_id")) for index in active}
                if len(ids) > 1 or "" in ids:
                    self.add_anomaly(
                        "warning",
                        "POTENTIAL_DUPLICATE_EXPERIMENT",
                        "identical values/context occur without the same explicit record_id; rows were retained for human adjudication",
                        processed[active[0]][0],
                        "record_id",
                        "D003",
                        {},
                        [processed[index][1]["input_row_id"] for index in active],
                    )
                    for index in active:
                        processed[index][1]["row_status"] = "flagged"
        row_anomalies: dict[str, list[dict[str, Any]]] = {}
        for anomaly in self.anomalies:
            if anomaly.get("input_row_id"):
                row_anomalies.setdefault(anomaly["input_row_id"], []).append(anomaly)
            for affected in anomaly.get("affected_rows", []):
                row_anomalies.setdefault(affected, []).append(anomaly)
        retained_output_index = 0
        for position, (record, output, _identity_hash) in enumerate(processed):
            if position in duplicate_of:
                primary_position = duplicate_of[position]
                self.coverage_rows.append(
                    coverage_item(record, "deduplicated", None, processed[primary_position][1]["input_row_id"], "exact duplicate by D001")
                )
                continue
            bad_levels = {item["severity"] for item in row_anomalies.get(record.row_id, [])}
            if bad_levels & {"blocking", "error", "warning"}:
                output["row_status"] = "flagged"
            retained_output_index += 1
            self.clean_rows.append(output)
            self.coverage_rows.append(coverage_item(record, output["row_status"], f"O{retained_output_index:06d}", None, None))
        # Put budget-rejected rows in original order; coverage was appended in
        # ingestion order already for all other rows.
        total = len(records)
        counts = {"total": total, "kept": 0, "flagged": 0, "deduplicated": 0, "rejected": 0}
        for item in self.coverage_rows:
            counts[item["disposition"]] += 1
        if sum(counts[key] for key in ("kept", "flagged", "deduplicated", "rejected")) != total:
            self.add_anomaly("blocking", "COVERAGE_MISMATCH", "internal coverage accounting failed", None, None, "C001", counts)
        if counts["kept"] + counts["flagged"] != len(self.clean_rows):
            self.add_anomaly("blocking", "ROW_COUNT_MISMATCH", "cleaned table does not equal retained coverage rows", None, None, "C001", counts)
        self.assign_ids()
        dynamic_headers = list(BASE_OUTPUT_FIELDS)
        for row in self.clean_rows:
            for key in row:
                if key not in dynamic_headers:
                    dynamic_headers.append(key)
        self.headers = dynamic_headers
        for row in self.clean_rows:
            for header in self.headers:
                row.setdefault(header, None)
        return {"rows": self.clean_rows, "headers": self.headers, "coverage": {"counts": counts, "rows": self.coverage_rows}}

    def assign_ids(self) -> None:
        severity_rank = {name: index for index, name in enumerate(SEVERITIES)}
        self.anomalies.sort(
            key=lambda item: (
                item.get("input_row_id") or "",
                severity_rank.get(item.get("severity", "info"), 99),
                item.get("code") or "",
                item.get("field") or "",
            )
        )
        old_to_new: dict[int, str] = {}
        for index, item in enumerate(self.anomalies, start=1):
            original_index = int(item.pop("_original_index"))
            old_to_new[original_index] = f"A{index:06d}"
            item_with_id = {"anomaly_id": old_to_new[original_index]}
            item_with_id.update(item)
            self.anomalies[index - 1] = item_with_id
        for review_index, item in enumerate(self.review, start=1):
            anomaly_id = old_to_new.get(item.pop("anomaly_index", -1))
            item_with_id = {"review_id": f"Q{review_index:06d}", "anomaly_id": anomaly_id}
            item_with_id.update(item)
            self.review[review_index - 1] = item_with_id


def normalize_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        text = unicodedata.normalize("NFKC", value).strip()
        if norm_text(text) in MISSING_LITERALS:
            return None
        return text
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def suggested_action(code: str) -> str:
    actions = {
        "UNKNOWN_UNIT": "add an explicit unit alias/factor to case unit configuration or correct the extraction; do not infer silently",
        "MALFORMED_NUMBER": "inspect the source locator and correct the numeric text; keep null until evidence is available",
        "MISSING_VALUE": "mark as not reported; do not impute",
        "MISSING_UNIT": "locate the unit in surrounding source context before standardizing",
        "UNMAPPED_COLUMN": "add a reviewed field mapping or retain as source-specific metadata",
        "FIELD_VALUE_CONFLICT": "resolve the conflicting source columns; neither value was selected",
        "DUPLICATE_ID_CONFLICT": "check whether the ID denotes distinct experiments; rows were kept separate",
        "POTENTIAL_DUPLICATE_EXPERIMENT": "confirm whether this is duplicate extraction or a repeated experiment",
        "INTERVAL_VALUE": "review whether downstream statistics should consume min/max rather than a point value",
        "BUDGET_EXCLUDED": "raise max_rows or split the input; excluded rows were rejected, not silently dropped",
        "INPUT_CASE_INVALID": "repair the JSON/CSV syntax and rerun; no scientific values were fabricated",
    }
    return actions.get(code, "inspect the source pointer and apply an explicit reviewed rule")


def coverage_item(record: SourceRecord, disposition: str, output_row_id: str | None, duplicate_of: str | None, reason: str | None) -> dict[str, Any]:
    return {
        "input_row_id": record.row_id,
        "source_pointer": source_pointer(record.source_name, record.pointer),
        "source_record_sha256": record.digest(),
        "disposition": disposition,
        "output_row_id": output_row_id,
        "duplicate_of": duplicate_of,
        "reason": reason,
    }


def sources_summary(ingestion: IngestionResult, case_path: Path, task_path: Path) -> list[dict[str, Any]]:
    grouped: dict[str, int] = {}
    for record in ingestion.records:
        grouped[record.source_name] = grouped.get(record.source_name, 0) + 1
    sources = [
        {
            "source_id": "case",
            "path": display_input_path(case_path),
            "sha256": ingestion.case_sha,
            "rows": grouped.get(case_path.name, 0),
            "role": "case and embedded extraction records",
        }
    ]
    for source_name in sorted(grouped):
        if source_name == case_path.name:
            continue
        candidate = case_path.parent / source_name
        sources.append(
            {
                "source_id": f"source:{source_name}",
                "path": source_name,
                "sha256": sha256_file(candidate) if candidate.exists() else None,
                "rows": grouped[source_name],
                "role": "declared CSV extraction records",
            }
        )
    if task_path.exists():
        sources.append(
            {
                "source_id": "task",
                "path": display_input_path(task_path),
                "sha256": sha256_file(task_path),
                "rows": None,
                "role": "task instructions and output contract hints",
            }
        )
    return sources


def result_status(cleaner: Cleaner, unresolved: list[dict[str, Any]], input_failed: bool = False) -> str:
    if input_failed or any(item["severity"] == "blocking" for item in cleaner.anomalies):
        return "input_error"
    if unresolved or any(item["severity"] in {"error", "warning"} for item in cleaner.anomalies):
        return "partial"
    return "success"


def apply_output_contract(
    contract_keys: list[str],
    base: dict[str, Any],
    cleaner: Cleaner,
    cleaned_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    unresolved: list[dict[str, Any]] = []
    aliases = {
        "answer": "summary",
        "summary": "summary",
        "cleaned_data": "cleaned_rows",
        "cleaned_records": "cleaned_rows",
        "records": "cleaned_rows",
        "data": "cleaned_rows",
        "table": "cleaned_rows",
        "cleaned_table": "cleaned_rows",
        "anomalies": "anomalies",
        "review_queue": "review",
        "validation": "validation_ref",
        "row_count": "row_count",
    }
    known = set(CORE_FIELDS) | set(aliases)
    for key in contract_keys:
        normalized_alias = aliases.get(norm_text(key), aliases.get(key))
        if key in base:
            continue
        if normalized_alias == "summary":
            base[key] = base["result"]["summary"]
        elif normalized_alias == "cleaned_rows":
            base[key] = cleaned_rows
        elif normalized_alias == "anomalies":
            base[key] = cleaner.anomalies
        elif normalized_alias == "review":
            base[key] = cleaner.review
        elif normalized_alias == "validation_ref":
            base[key] = ARTIFACT_FILES["validation"]
        elif normalized_alias == "row_count":
            base[key] = len(cleaned_rows)
        elif key not in known:
            base[key] = None
            unresolved.append({"field": key, "reason": "declared output_contract field has no deterministic adapter in this skill; left null rather than fabricated"})
    # Remove adapter internals if a contract used unusual names but not core names.
    base["unresolved_fields"] = unresolved
    return base, unresolved


def csv_text(headers: list[str], rows: list[dict[str, Any]]) -> str:
    from io import StringIO

    handle = StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({header: make_cell_string(row.get(header)) for header in headers})
    return handle.getvalue()


def write_artifacts(
    out_dir: Path,
    cleaner: Cleaner,
    clean_rows: list[dict[str, Any]],
    headers: list[str],
    result: dict[str, Any],
    audit_text: str,
) -> dict[str, str]:
    files: dict[str, str] = {}
    for key, filename in ARTIFACT_FILES.items():
        files[key] = filename
    write_text_atomic(out_dir / "cleaned.csv", csv_text(headers, clean_rows))
    write_text_atomic(out_dir / "cleaned.json", json.dumps(clean_rows, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n")
    anomaly_headers = ["anomaly_id", "severity", "code", "input_row_id", "source_pointer", "field", "rule_id", "message", "details", "affected_rows"]
    write_text_atomic(out_dir / "anomalies.csv", csv_text(anomaly_headers, cleaner.anomalies))
    review_headers = ["review_id", "anomaly_id", "severity", "input_row_id", "source_pointer", "field", "issue", "raw_value", "suggested_action", "status", "resolution", "owner"]
    write_text_atomic(out_dir / "review_queue.csv", csv_text(review_headers, cleaner.review))
    changes_text = "".join(json_stable(change) + "\n" for change in cleaner.changes)
    write_text_atomic(out_dir / "changes.jsonl", changes_text)
    write_text_atomic(out_dir / "audit.md", audit_text)
    write_text_atomic(out_dir / "result.json", json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n")
    write_manifest(out_dir, files)
    return files


def write_manifest(out_dir: Path, artifacts: dict[str, str]) -> None:
    payload_entries = []
    for filename in PAYLOAD_FILES:
        path = out_dir / filename
        payload_entries.append({"path": filename, "size_bytes": path.stat().st_size, "sha256": sha256_file(path)})
    checksum_text = "".join(f"{entry['sha256']}  {entry['path']}\n" for entry in payload_entries)
    write_text_atomic(out_dir / "checksums.sha256", checksum_text)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "hash_algorithm": "sha256",
        "files": payload_entries,
        "checksums_file": {
            "path": "checksums.sha256",
            "size_bytes": (out_dir / "checksums.sha256").stat().st_size,
            "sha256": sha256_file(out_dir / "checksums.sha256"),
        },
        "not_covered_by_manifest": ["manifest.json", "validation.json"],
        "artifacts": artifacts,
    }
    write_text_atomic(out_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def audit_markdown(result: dict[str, Any], cleaner: Cleaner, coverage: dict[str, Any]) -> str:
    counts = coverage["counts"]
    lines = [
        "# Contract audit report",
        "",
        f"- case_id: `{result.get('case_id')}`",
        f"- status: `{result.get('status')}`",
        "- deterministic rules: schema S001-S004, values V001-V004, units U001-U004, identity D001-D003, coverage C001",
        "",
        "## Coverage reconciliation",
        "",
        "| input rows | kept | flagged | deduplicated | rejected | cleaned rows |",
        "|---:|---:|---:|---:|---:|---:|",
        f"| {counts['total']} | {counts['kept']} | {counts['flagged']} | {counts['deduplicated']} | {counts['rejected']} | {counts['kept'] + counts['flagged']} |",
        "",
        "Every input row has exactly one disposition. `flagged` rows remain in the statistical table; `deduplicated` and `rejected` rows are excluded only with the reason in `result.json.coverage.rows`.",
        "",
        "## Severity ledger",
        "",
        "| severity | count | meaning |",
        "|---|---:|---|",
    ]
    for severity in SEVERITIES:
        count = sum(1 for item in cleaner.anomalies if item["severity"] == severity)
        meaning = {
            "blocking": "delivery cannot be treated as complete; result is input_error/partial and verifier exits nonzero if the failure is in the artifacts",
            "error": "a cell/row requires correction or reviewed configuration; row remains flagged when retained",
            "warning": "usable but uncertain; review queue entry required",
            "info": "deterministic no-loss action such as exact duplicate removal",
        }[severity]
        lines.append(f"| {severity} | {count} | {meaning} |")
    lines.extend(["", "## Anomalies", ""])
    if cleaner.anomalies:
        lines.extend(["| anomaly | severity | code | row | field | message |", "|---|---|---|---|---|---|"])
        for item in cleaner.anomalies[:200]:
            message = str(item["message"]).replace("|", "\\|")
            lines.append(f"| {item['anomaly_id']} | {item['severity']} | {item['code']} | {item.get('input_row_id') or ''} | {item.get('field') or ''} | {message} |")
        if len(cleaner.anomalies) > 200:
            lines.append(f"| … | | | | | {len(cleaner.anomalies) - 200} additional anomalies are in anomalies.csv |")
    else:
        lines.append("No anomalies.")
    lines.extend(
        [
            "",
            "## Review queue",
            "",
            f"Open items: {len(cleaner.review)}. The queue is deliberately separate from the statistical table so uncertain values are not silently consumed.",
            "",
            "## Artifact integrity",
            "",
            "`checksums.sha256` covers the payload files. `manifest.json` records sizes and hashes and explicitly excludes only itself and the verification report; run `verify` after moving or editing any artifact.",
        ]
    )
    return "\n".join(lines) + "\n"


def initial_partial_result(out_dir: Path, contract_keys: list[str], case_id: str | None, reason: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "result": {"summary": f"partial result saved before processing: {reason}", "cleaned_table": None, "row_count": 0},
        "status": "partial",
        "sources": [],
        "uncertainty": [{"severity": "info", "code": "RUN_IN_PROGRESS", "message": reason}],
        "change_records": [],
        "coverage": {"counts": {"total": 0, "kept": 0, "flagged": 0, "deduplicated": 0, "rejected": 0}, "rows": []},
        "artifacts": {"result": "result.json"},
        "unresolved_fields": [],
    }
    for key in contract_keys:
        if key not in result:
            result[key] = None
            result["unresolved_fields"].append({"field": key, "reason": "processing had not completed when this partial result was written"})
    write_text_atomic(out_dir / "result.json", json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return result


def run_clean(case_path: Path, task_path: Path, work_dir: Path, out_dir: Path, max_rows: int) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    task_text = ""
    task_error: str | None = None
    try:
        task_text = task_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        task_error = str(exc)
    preliminary_case = None
    preliminary_id = None
    try:
        preliminary_case = load_json_strict(case_path)
        preliminary_id = extract_case_id(preliminary_case)
    except Exception:
        pass
    contract_keys = extract_contract(preliminary_case, task_text)
    initial_partial_result(out_dir, contract_keys, preliminary_id, "run initialized; artifacts are being produced incrementally")
    state_path = work_dir / "run_state.json"
    write_text_atomic(state_path, json_stable({"stage": "initialized", "schema_version": SCHEMA_VERSION, "max_rows": max_rows}) + "\n")
    ingestion = ingest_case(case_path)
    cleaner = Cleaner(ingestion.case, max_rows=max_rows)
    input_findings = list(ingestion.errors)
    if task_error:
        input_findings.append({"code": "TASK_UNREADABLE", "severity": "warning", "message": task_error, "path": display_input_path(task_path)})
    processed = cleaner.process(ingestion.records, input_findings)
    input_failed = ingestion.case is None or not ingestion.records or any(item["severity"] == "blocking" for item in cleaner.anomalies)
    contract_keys = extract_contract(ingestion.case, task_text)
    case_id = extract_case_id(ingestion.case)
    coverage = processed["coverage"]
    counts = coverage["counts"]
    summary = (
        f"cleaned {counts['kept'] + counts['flagged']} of {counts['total']} input rows; "
        f"kept={counts['kept']}, flagged={counts['flagged']}, deduplicated={counts['deduplicated']}, rejected={counts['rejected']}; "
        f"open review items={len(cleaner.review)}"
    )
    base: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "result": {
            "summary": summary,
            "cleaned_table": ARTIFACT_FILES["cleaned_csv"],
            "cleaned_data": ARTIFACT_FILES["cleaned_json"],
            "row_count": len(cleaner.clean_rows),
            "headers": processed["headers"],
            "review_items": len(cleaner.review),
        },
        "status": result_status(cleaner, [], input_failed=input_failed),
        "sources": sources_summary(ingestion, case_path, task_path),
        "uncertainty": [
            {
                "anomaly_id": item["anomaly_id"],
                "severity": item["severity"],
                "code": item["code"],
                "input_row_id": item.get("input_row_id"),
                "source_pointer": item.get("source_pointer"),
                "field": item.get("field"),
                "message": item["message"],
            }
            for item in cleaner.anomalies
            if item["severity"] in {"blocking", "error", "warning"}
        ],
        "change_records": cleaner.changes,
        "coverage": coverage,
        "artifacts": ARTIFACT_FILES,
        "unresolved_fields": [],
    }
    base, unresolved = apply_output_contract(contract_keys, base, cleaner, cleaner.clean_rows)
    base["status"] = result_status(cleaner, unresolved, input_failed=input_failed)
    audit = audit_markdown(base, cleaner, coverage)
    write_artifacts(out_dir, cleaner, cleaner.clean_rows, processed["headers"], base, audit)
    write_text_atomic(state_path, json_stable({"stage": "artifacts_written", "status": base["status"], "rows": len(cleaner.clean_rows)}) + "\n")
    verification = verify_output(case_path, task_path, out_dir, write_report=True, max_rows=max_rows)
    if verification["summary"]["blocking"] and base["status"] != "input_error":
        # A verifier-blocking condition means the machine final check, not the
        # science, failed.  Preserve the useful partial result and report it.
        base["status"] = "partial"
        base["uncertainty"].append({"severity": "blocking", "code": "FINAL_VERIFICATION_FAILED", "message": "see validation.json"})
        write_artifacts(out_dir, cleaner, cleaner.clean_rows, processed["headers"], base, audit_markdown(base, cleaner, coverage))
        verification = verify_output(case_path, task_path, out_dir, write_report=True, max_rows=max_rows)
    write_text_atomic(state_path, json_stable({"stage": "verified", "verification": verification["status"]}) + "\n")
    if verification["summary"]["blocking"]:
        return 3
    return 2 if base["status"] == "input_error" else 0


class VerifyContext:
    def __init__(self) -> None:
        self.findings: list[dict[str, Any]] = []

    def add(self, check_id: str, severity: str, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        self.findings.append(
            {
                "check_id": check_id,
                "severity": severity,
                "status": "fail" if severity in {"blocking", "error"} else "pass_with_finding",
                "code": code,
                "message": message,
                "details": details or {},
            }
        )

    def passed(self, check_id: str, message: str, details: dict[str, Any] | None = None) -> None:
        self.findings.append({"check_id": check_id, "severity": "info", "status": "pass", "code": "PASS", "message": message, "details": details or {}})


def read_csv_table(path: Path) -> tuple[list[str], list[dict[str, str]], str | None]:
    try:
        text = path.read_text(encoding="utf-8-sig")
        reader = csv.DictReader(text.splitlines())
        if reader.fieldnames is None:
            return [], [], "CSV has no header"
        rows = [{key: (value if value != "" else None) for key, value in row.items()} for row in reader]
        return list(reader.fieldnames), rows, None
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        return [], [], str(exc)


def parse_csv_cell_like(header: str, value: str | None) -> Any:
    if value is None:
        return None
    if header in NUMERIC_OUTPUT_FIELDS or header in {"value", "value_min", "value_max"}:
        number, state, _places = parse_decimal(value)
        if state is None and number is not None:
            return float(number)
        return f"__invalid_numeric__:{value}"
    if value in {"true", "false"}:
        return value == "true"
    if value.startswith("{") or value.startswith("["):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def coerce_csv_cell_for_expected(value: str | None, expected: Any) -> Any:
    """CSV round-trip comparison driven by the expected cell's JSON type."""
    if expected is None:
        return None
    if value is None:
        return None
    if isinstance(expected, bool):
        return value == "true" if value in {"true", "false"} else f"__type_mismatch__:{value}"
    if isinstance(expected, int) and not isinstance(expected, bool):
        number, state, _places = parse_decimal(value)
        return int(number) if state is None and number is not None and number == number.to_integral() else f"__type_mismatch__:{value}"
    if isinstance(expected, float):
        number, state, _places = parse_decimal(value)
        converted = float(number) if state is None and number is not None else None
        return converted if converted is not None and math.isfinite(converted) else f"__type_mismatch__:{value}"
    if isinstance(expected, (dict, list)):
        try:
            return json.loads(value)
        except ValueError:
            return f"__type_mismatch__:{value}"
    return value


def verify_output(case_path: Path, task_path: Path, out_dir: Path, write_report: bool = True, max_rows: int = 0) -> dict[str, Any]:
    context = VerifyContext()
    result_path = out_dir / "result.json"
    result: Any = None
    case: Any = None
    task_text = ""
    task_error: str | None = None
    try:
        task_text = task_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        task_error = str(exc)
        context.add("INPUT_TASK", "error", "TASK_UNREADABLE", task_error)
    try:
        result = load_json_strict(result_path)
        if not isinstance(result, dict):
            raise ValueError("result.json root must be an object")
        context.passed("RESULT_JSON", "result.json is strict finite JSON")
    except Exception as exc:
        context.add("RESULT_JSON", "blocking", "RESULT_INVALID_JSON", str(exc))
    ingestion = ingest_case(case_path)
    if ingestion.case is None:
        case = None
        context.add("INPUT_CASE", "error", "INPUT_CASE_INVALID", "case is invalid; verifier will check that the stored result is an honest input_error", {"errors": ingestion.errors})
    else:
        case = ingestion.case
        context.passed("INPUT_CASE", "case re-ingested independently", {"input_rows": len(ingestion.records)})
    contract_keys = extract_contract(case, task_text)
    required_keys = list(dict.fromkeys(CORE_FIELDS + contract_keys))
    if isinstance(result, dict):
        missing = [key for key in required_keys if key not in result]
        if missing:
            context.add("OUTPUT_CONTRACT", "blocking", "CONTRACT_MISSING_FIELD", "declared output fields are missing", {"fields": missing})
        else:
            context.passed("OUTPUT_CONTRACT", "all core and declared contract fields are present", {"field_count": len(required_keys)})
        unresolved_fields = {item.get("field") for item in result.get("unresolved_fields", []) if isinstance(item, dict)}
        unknown_nulls = []
        for key in contract_keys:
            if key not in CORE_FIELDS and result.get(key) is None and key not in unresolved_fields:
                unknown_nulls.append(key)
        if unknown_nulls:
            context.add("UNRESOLVED_FIELDS", "error", "UNKNOWN_FIELD_NOT_LISTED", "null extension fields must be listed in unresolved_fields", {"fields": unknown_nulls})
        else:
            context.passed("UNRESOLVED_FIELDS", "all null extension fields are explicitly unresolved")
    # Manifest and checksums first: if these fail, downstream contents may have drifted.
    manifest: dict[str, Any] | None = None
    manifest_entries: dict[str, dict[str, Any]] = {}
    try:
        manifest = load_json_strict(out_dir / "manifest.json")
        if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
            raise ValueError("manifest.files must be a list")
        for entry in manifest["files"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                raise ValueError("manifest entry lacks path")
            rel = Path(entry["path"])
            if rel.is_absolute() or ".." in rel.parts:
                raise ValueError(f"unsafe manifest path {entry['path']!r}")
            manifest_entries[entry["path"]] = entry
        context.passed("MANIFEST_SCHEMA", "manifest schema and relative paths are valid", {"files": len(manifest_entries)})
    except Exception as exc:
        context.add("MANIFEST_SCHEMA", "blocking", "MANIFEST_INVALID", str(exc))
    for name, entry in manifest_entries.items():
        path = out_dir / name
        if not path.exists():
            context.add("ARTIFACT_EXISTENCE", "blocking", "ARTIFACT_MISSING", "manifest payload is missing", {"path": name})
            continue
        size = path.stat().st_size
        digest = sha256_file(path)
        if size != entry.get("size_bytes") or digest != entry.get("sha256"):
            context.add("ARTIFACT_CHECKSUM", "blocking", "ARTIFACT_CHECKSUM_DRIFT", "artifact size/hash differs from manifest", {"path": name, "expected_sha256": entry.get("sha256"), "actual_sha256": digest})
    if manifest and isinstance(manifest.get("checksums_file"), dict):
        checksum_path = out_dir / "checksums.sha256"
        expected = manifest["checksums_file"]
        if not checksum_path.exists():
            context.add("CHECKSUM_FILE", "blocking", "ARTIFACT_MISSING", "checksums.sha256 is missing")
        else:
            actual = sha256_file(checksum_path)
            if actual != expected.get("sha256") or checksum_path.stat().st_size != expected.get("size_bytes"):
                context.add("CHECKSUM_FILE", "blocking", "ARTIFACT_CHECKSUM_DRIFT", "checksums.sha256 differs from manifest", {"expected_sha256": expected.get("sha256"), "actual_sha256": actual})
            else:
                try:
                    lines = checksum_path.read_text(encoding="utf-8").splitlines()
                    parsed = {}
                    for line in lines:
                        digest, filename = line.split("  ", 1)
                        parsed[filename] = digest
                    drift = [name for name, entry in manifest_entries.items() if parsed.get(name) != entry.get("sha256")]
                    if drift:
                        context.add("CHECKSUM_LINES", "blocking", "ARTIFACT_CHECKSUM_DRIFT", "checksum file entries differ from manifest", {"paths": drift})
                    else:
                        context.passed("ARTIFACT_CHECKSUM", "all manifest payload checksums match")
                except Exception as exc:
                    context.add("CHECKSUM_LINES", "blocking", "CHECKSUM_FILE_INVALID", str(exc))
    if isinstance(result, dict) and isinstance(result.get("artifacts"), dict):
        for key, filename in ARTIFACT_FILES.items():
            if result["artifacts"].get(key) != filename:
                context.add("ARTIFACT_CONTRACT", "error", "ARTIFACT_REFERENCE_MISMATCH", "result artifact reference is missing or unexpected", {"artifact": key, "expected": filename, "actual": result["artifacts"].get(key)})
    # Rebuild the clean state from source in a fresh object.  This second stage
    # intentionally does not reuse any run-stage state.
    expected_cleaner = Cleaner(case, max_rows=max_rows)
    expected_findings = list(ingestion.errors)
    if task_error:
        expected_findings.append({"code": "TASK_UNREADABLE", "severity": "warning", "message": task_error, "path": display_input_path(task_path)})
    expected = expected_cleaner.process(ingestion.records, expected_findings)
    expected_rows = expected["rows"]
    expected_headers = expected["headers"]
    expected_coverage = expected["coverage"]
    headers, csv_rows, csv_error = read_csv_table(out_dir / "cleaned.csv")
    if csv_error:
        context.add("CLEANED_CSV", "blocking", "CLEANED_CSV_INVALID", csv_error)
    else:
        if headers != expected_headers:
            context.add("CLEANED_SCHEMA", "blocking", "CLEANED_SCHEMA_MISMATCH", "cleaned CSV headers differ from a fresh schema rebuild", {"expected": expected_headers, "actual": headers})
        elif len(csv_rows) != len(expected_rows):
            context.add("ROW_COUNT", "blocking", "ROW_COUNT_MISMATCH", "cleaned CSV row count differs from source coverage", {"expected": len(expected_rows), "actual": len(csv_rows)})
        else:
            mismatches = []
            for index, (actual, wanted) in enumerate(zip(csv_rows, expected_rows)):
                parsed_actual = {header: coerce_csv_cell_for_expected(actual.get(header), wanted.get(header)) for header in headers}
                for header in headers:
                    if parsed_actual.get(header) != wanted.get(header):
                        mismatches.append({"row_index": index, "input_row_id": wanted.get("input_row_id"), "field": header, "expected": wanted.get(header), "actual": actual.get(header)})
                        break
            if mismatches:
                code = "CLEANED_CONTENT_MISMATCH"
                if any(item["field"] in {"value", "value_min", "value_max", "conversion_change_id"} for item in mismatches):
                    code = "RAW_CONVERSION_TRACE_BREAK"
                context.add("CLEANED_CONTENT", "blocking", code, "cleaned rows differ from independently rebuilt source values/conversions", {"mismatches": mismatches[:20], "mismatch_count": len(mismatches)})
            else:
                context.passed("CLEANED_CONTENT", "every retained output cell matches a fresh source rebuild")
    try:
        cleaned_json = load_json_strict(out_dir / "cleaned.json")
        if not isinstance(cleaned_json, list):
            raise ValueError("cleaned.json root must be a list")
        if csv_rows and len(cleaned_json) != len(csv_rows):
            context.add("ROW_COUNT", "blocking", "ROW_COUNT_MISMATCH", "cleaned JSON/CSV row counts differ", {"csv": len(csv_rows), "json": len(cleaned_json)})
        bad_finite = ensure_finite_json(cleaned_json)
        if bad_finite:
            context.add("NONFINITE", "blocking", "NONFINITE_OUTPUT", "cleaned JSON contains NaN or Infinity", {"locations": bad_finite})
        if len(cleaned_json) == len(expected_rows):
            json_mismatches = []
            for index, (actual, wanted) in enumerate(zip(cleaned_json, expected_rows)):
                if not isinstance(actual, dict):
                    json_mismatches.append({"row_index": index, "field": "__row__", "actual_type": type(actual).__name__})
                    continue
                for header in expected_headers:
                    if actual.get(header) != wanted.get(header):
                        json_mismatches.append({"row_index": index, "input_row_id": wanted.get("input_row_id"), "field": header, "expected": wanted.get(header), "actual": actual.get(header)})
                        break
            if json_mismatches:
                context.add("CLEANED_JSON_CONTENT", "blocking", "CLEANED_CONTENT_MISMATCH", "cleaned JSON rows differ from independently rebuilt source values", {"mismatches": json_mismatches[:20], "mismatch_count": len(json_mismatches)})
    except Exception as exc:
        context.add("CLEANED_JSON", "blocking", "CLEANED_JSON_INVALID", str(exc))
    for row_index, row in enumerate(csv_rows):
        for field in NUMERIC_OUTPUT_FIELDS | {"value", "value_min", "value_max"}:
            if field in row and isinstance(parse_csv_cell_like(field, row.get(field)), str) and str(parse_csv_cell_like(field, row.get(field))).startswith("__invalid_numeric__"):
                context.add("NONFINITE", "blocking", "NONFINITE_OUTPUT", "numeric output cell is missing, malformed, NaN, or Infinity", {"row_index": row_index, "field": field, "value": row.get(field)})
    if isinstance(result, dict):
        actual_coverage = result.get("coverage")
        if actual_coverage != expected_coverage:
            context.add("COVERAGE", "blocking", "COVERAGE_MISMATCH", "result coverage does not prove every source row's disposition", {"expected_counts": expected_coverage["counts"], "actual": actual_coverage.get("counts") if isinstance(actual_coverage, dict) else None})
        else:
            context.passed("COVERAGE", "coverage reconciles kept/flagged/deduplicated/rejected to every input row")
        input_ids = [row.get("input_row_id") for row in csv_rows]
        if len(input_ids) != len(set(input_ids)):
            context.add("ROW_IDENTITY", "blocking", "ROW_IDENTITY_DUPLICATE", "cleaned table contains duplicate input_row_id values")
        expected_hash = {row["input_row_id"]: row["source_record_sha256"] for row in expected_rows}
        hash_breaks = [row.get("input_row_id") for row in csv_rows if expected_hash.get(row.get("input_row_id")) != row.get("source_record_sha256")]
        if hash_breaks:
            context.add("SOURCE_HASH", "blocking", "RAW_TRACE_BREAK", "output row source hash does not match the re-ingested raw input row", {"input_row_ids": hash_breaks})
    _headers, anomaly_rows, anomaly_error = read_csv_table(out_dir / "anomalies.csv")
    if anomaly_error:
        context.add("ANOMALIES", "blocking", "ANOMALIES_INVALID", anomaly_error)
    else:
        expected_keys = {
            (item.get("input_row_id"), item.get("code"), item.get("field"))
            for item in expected_cleaner.anomalies
        }
        actual_keys = {(row.get("input_row_id"), row.get("code"), row.get("field")) for row in anomaly_rows}
        missing = sorted((key for key in expected_keys - actual_keys if key[1] in {"UNMAPPED_COLUMN", "UNKNOWN_UNIT", "MALFORMED_NUMBER", "MISSING_VALUE", "DUPLICATE_ID_CONFLICT"}), key=repr)
        extra = sorted((key for key in actual_keys - expected_keys if key[1] in {"UNMAPPED_COLUMN", "UNKNOWN_UNIT", "MALFORMED_NUMBER", "DUPLICATE_ID_CONFLICT"}), key=repr)
        if missing:
            context.add("ANOMALY_RECONCILIATION", "error", "UNMAPPED_OR_ANOMALY_UNREPORTED", "fresh source checks found anomalies absent from anomalies.csv", {"missing": missing[:20], "missing_count": len(missing)})
        if extra:
            context.add("ANOMALY_RECONCILIATION", "error", "UNEXPECTED_ANOMALY", "anomalies.csv contains anomaly classes not reproduced from source", {"extra": extra[:20], "extra_count": len(extra)})
        if not missing and not extra:
            context.passed("ANOMALY_RECONCILIATION", "reported anomaly set reconciles with fresh source checks")
    try:
        actual_changes = []
        with (out_dir / "changes.jsonl").open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if line.strip():
                    actual_changes.append((line_number, json.loads(line)))
        expected_changes = {json_stable(change): change for change in expected_cleaner.changes}
        actual_stable = [json_stable(change) for _line, change in actual_changes]
        if actual_stable != list(expected_changes):
            context.add("CHANGE_LOG", "blocking", "RAW_CONVERSION_TRACE_BREAK", "changes.jsonl differs from independently rebuilt per-cell conversion/change trace", {"expected_records": len(expected_cleaner.changes), "actual_records": len(actual_changes)})
        else:
            context.passed("CHANGE_LOG", "per-cell change log and raw conversion traces match source", {"records": len(actual_changes)})
    except Exception as exc:
        context.add("CHANGE_LOG", "blocking", "CHANGE_LOG_INVALID", str(exc))
    if isinstance(result, dict):
        expected_status = result_status(expected_cleaner, result.get("unresolved_fields", []), input_failed=case is None or not ingestion.records)
        if result.get("status") != expected_status:
            context.add("STATUS", "blocking", "STATUS_INCONSISTENT", "stored status is not honest for fresh anomaly/contract findings", {"expected": expected_status, "actual": result.get("status")})
        else:
            context.passed("STATUS", "status is consistent with severity findings", {"status": result.get("status")})
    summary = {severity: sum(1 for item in context.findings if item["severity"] == severity) for severity in SEVERITIES}
    status = "fail" if summary["blocking"] else ("pass_with_findings" if summary["error"] else "pass")
    report = {
        "schema_version": SCHEMA_VERSION,
        "verifier": "independent-two-stage-v1",
        "status": status,
        "exit_code": 3 if summary["blocking"] else 0,
        "case_id": extract_case_id(case),
        "scope": "fresh read of case, task, result, cleaned tables, anomaly log, change log, checksums and manifest; no run-stage memory is trusted",
        "summary": summary,
        "checks": context.findings,
    }
    if write_report:
        try:
            write_text_atomic(out_dir / "validation.json", json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n")
        except OSError as exc:
            report["summary"]["blocking"] += 1
            report["status"] = "fail"
            report["exit_code"] = 3
            report["checks"].append({"check_id": "VALIDATION_WRITE", "severity": "blocking", "status": "fail", "code": "VALIDATION_WRITE_FAILED", "message": str(exc), "details": {}})
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Contract-aware literature extraction cleaner and independent verifier")
    parser.add_argument("command", nargs="?", choices=("run", "verify"), default="run", help="run cleaning or independently verify existing artifacts")
    parser.add_argument("--case", default="/input/case.json", help="input case JSON (default: /input/case.json)")
    parser.add_argument("--task", default="/input/task.md", help="task markdown (default: /input/task.md)")
    parser.add_argument("--work", default="/app/work", help="staging directory (default: /app/work)")
    parser.add_argument("--out", default="/app/output", help="artifact directory (default: /app/output)")
    parser.add_argument("--max-rows", type=int, default=50000, help="rows to process before honest budget exclusion; 0 means unlimited")
    parser.add_argument("--verify", action="store_true", help="verify an existing --out directory instead of cleaning")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    case_path = Path(args.case)
    task_path = Path(args.task)
    work_dir = Path(args.work)
    out_dir = Path(args.out)
    try:
        if args.verify or args.command == "verify":
            report = verify_output(case_path, task_path, out_dir, write_report=True, max_rows=args.max_rows)
            return int(report["exit_code"])
        return run_clean(case_path, task_path, work_dir, out_dir, max(0, args.max_rows))
    except KeyboardInterrupt:
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            initial_partial_result(out_dir, [], None, "interrupted before completion")
        except Exception:
            pass
        return 130
    except Exception as exc:  # last-resort contract preservation, never a traceback-only crash
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            result = initial_partial_result(out_dir, [], None, f"unhandled failure: {exc}")
            result["status"] = "input_error"
            write_text_atomic(out_dir / "result.json", json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n")
        except Exception:
            pass
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
