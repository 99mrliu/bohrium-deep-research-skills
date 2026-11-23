#!/usr/bin/env python3
"""Lineage Guardian: lossless intake and conservative cleaning for extracted tables.

Python 3.10+, standard library only.  No network access, no randomness, no clock.
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
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any, Iterable, Optional

VERSION = "1.0.0"
SYNTHETIC_LABEL = "SYNTHETIC_EXAMPLE_NOT_AN_OFFICIAL_ANSWER"
MISSING_TOKENS = {
    "", "-", "--", "—", "n/a", "na", "n.r.", "nr", "none", "null",
    "not reported", "not available", "missing", "未报告", "未提供", "缺失", "无",
}
RECORD_KEYS = {
    "records", "rows", "data", "entries", "measurements", "observations",
    "extracted_data", "extracted_records", "literature_records", "items", "tables",
}
EXCLUDED_JSON_KEYS = {"output_contract", "input_contract", "schema", "json_schema"}
PATH_SUFFIXES = {".csv", ".tsv", ".json"}
NUM = r"[+-]?(?:\d+(?:[.,]\d+)?|\.\d+)(?:[eE][+-]?\d+)?"
RANGE_RE = re.compile(
    rf"^\s*({NUM})\s*(?:–|—|~|～|\.\.|\bto\b|(?<=\d)-(?=\s*[+\d]))\s*({NUM})\s*(.*?)\s*$",
    re.IGNORECASE,
)
SCALAR_RE = re.compile(rf"^\s*({NUM})\s*(.*?)\s*$")

CANONICAL_FIELDS = [
    "material_name", "material_id", "property_name", "property_value_raw",
    "property_value_text", "property_value_number", "property_value_min",
    "property_value_max", "unit_raw", "unit_canonical", "unit_family",
    "value_standard", "value_standard_min", "value_standard_max",
    "temperature_c", "temperature_c_min", "temperature_c_max",
    "pressure_kpa", "pressure_kpa_min", "pressure_kpa_max",
    "time_s", "time_s_min", "time_s_max", "concentration",
    "concentration_min", "concentration_max", "concentration_unit",
    "experiment_id", "literature_ref", "conditions", "extraction_context",
]
CSV_COLUMNS = [
    "example_label", "row_id", "source_id", "table_id", "source_row_index",
    "row_fingerprint", "row_status", "include_in_statistics", "duplicate_status",
    "duplicate_group_id",
] + CANONICAL_FIELDS + [
    "conditions_canonical", "unmapped_fields", "quality_flags", "source_locator",
]

ALIASES = {
    "material_name": {
        "material", "material name", "material label", "substance", "substance name",
        "compound", "compound name", "chemical", "sample", "sample name", "system",
        "材料", "材料名称", "物质", "物质名称", "化合物", "样品", "样品名称",
    },
    "material_id": {
        "material id", "substance id", "cas", "cas no", "cas number", "cas registry number",
        "smiles", "inchi", "材料id", "材料编号", "cas号", "物质编号",
    },
    "property_name": {
        "property", "property name", "metric", "metric name", "parameter", "indicator",
        "measurement", "property metric", "property/metric", "性质", "属性", "指标", "参数",
    },
    "property_value": {
        "value", "result", "result value", "measured value", "measurement value", "data",
        "value extracted", "extracted value", "property value", "reading", "数值", "结果", "测量值",
    },
    "unit_raw": {"unit", "units", "value unit", "measurement unit", "单位", "数值单位"},
    "temperature_c": {
        "temperature", "temp", "t", "temperature c", "temperature degc", "reaction temperature",
        "annealing temperature", "温度", "反应温度", "退火温度",
    },
    "pressure_kpa": {"pressure", "p", "pressure kpa", "reaction pressure", "压力", "反应压力"},
    "time_s": {
        "time", "duration", "reaction time", "annealing time", "holding time", "时间", "时长",
        "反应时间", "退火时间",
    },
    "concentration": {"concentration", "conc", "molarity", "浓度", "摩尔浓度"},
    "concentration_unit": {"concentration unit", "conc unit", "浓度单位"},
    "experiment_id": {
        "experiment", "experiment id", "exp id", "experiment no", "batch", "batch id", "run id",
        "record id", "实验", "实验id", "实验编号", "批次",
    },
    "literature_ref": {
        "reference", "source", "doi", "paper", "paper doi", "citation", "literature", "title",
        "pages", "page", "locator", "文献", "文献来源", "引用", "doi号",
    },
    "conditions": {"conditions", "condition", "experiment conditions", "实验条件", "条件"},
    "extraction_context": {
        "context", "notes", "note", "remarks", "remark", "comment", "comments", "details",
        "extraction context", "备注", "注释", "上下文", "抽取上下文",
    },
}
ALIAS_LOOKUP = {
    alias: canonical for canonical, aliases in ALIASES.items() for alias in aliases
}
HEADER_UNIT_RE = re.compile(
    r"^(.*?)(?:\s*[\(\[]\s*([^\)\]]+)\s*[\)\]]|[_\s]+(degc|°c|kpa|mpa|pa|ks|ms|min|kj|mj|j))$",
    re.IGNORECASE,
)
PROPERTY_SYNONYMS = {
    "bandgap": "band_gap", "band gap": "band_gap", "band_gap": "band_gap", "eg": "band_gap",
    "electrical conductivity": "conductivity", "conductivity": "conductivity",
    "product yield": "yield", "yield": "yield", "annealing time": "annealing_time",
    "reaction time": "reaction_time", "glass transition": "glass_transition_temperature",
    "tg": "glass_transition_temperature", "plqy": "plqy", "photoluminescence quantum yield": "plqy",
    "density": "density", "swelling energy": "swelling_energy",
}

# factor is relative to target; affine temperature conversions are handled separately.
UNITS: dict[str, dict[str, Any]] = {}


def add_unit(symbols: Iterable[str], family: str, target: str, canonical: str, factor: str = "1") -> None:
    for symbol in symbols:
        UNITS[symbol] = {"family": family, "target": target, "canonical": canonical, "factor": Decimal(factor)}


add_unit(["°c", "℃", "degc", "celsius", "degree celsius", "degrees celsius"], "temperature", "degC", "degC")
add_unit(["k", "kelvin"], "temperature", "degC", "degC")
add_unit(["°f", "℉", "degf", "fahrenheit"], "temperature", "degC", "degC")
add_unit(["s", "sec", "secs", "second", "seconds"], "time", "s", "s")
add_unit(["ks", "kilosecond", "kiloseconds"], "time", "s", "s", "1000")
add_unit(["ms", "millisecond", "milliseconds"], "time", "s", "s", "0.001")
add_unit(["us", "µs", "μs", "microsecond", "microseconds"], "time", "s", "s", "0.000001")
add_unit(["min", "mins", "minute", "minutes"], "time", "s", "s", "60")
add_unit(["h", "hr", "hrs", "hour", "hours"], "time", "s", "s", "3600")
add_unit(["d", "day", "days"], "time", "s", "s", "86400")
add_unit(["kpa", "kilopascal", "kilopascals"], "pressure", "kPa", "kPa")
add_unit(["pa", "pascal", "pascals"], "pressure", "kPa", "kPa", "0.001")
add_unit(["mpa", "megapascal", "megapascals"], "pressure", "kPa", "kPa", "1000")
add_unit(["bar"], "pressure", "kPa", "kPa", "100")
add_unit(["mbar"], "pressure", "kPa", "kPa", "0.1")
add_unit(["atm", "atmosphere", "atmospheres"], "pressure", "kPa", "kPa", "101.325")
add_unit(["psi"], "pressure", "kPa", "kPa", "6.894757")
add_unit(["j", "joule", "joules"], "energy", "J", "J")
add_unit(["kj", "kilojoule", "kilojoules"], "energy", "J", "J", "1000")
add_unit(["mj", "megajoule", "megajoules"], "energy", "J", "J", "1000000")
add_unit(["ev", "electronvolt", "electronvolts"], "energy", "J", "J", "1.602176634e-19")
add_unit(["molar", "mol/l", "mol l-1", "mol l^-1"], "concentration", "mol/L", "mol/L")
add_unit(["mmolar", "mmol/l", "mmol l-1", "mmol l^-1"], "concentration", "mol/L", "mol/L", "0.001")
add_unit(["umolar", "umol/l", "µmol/l", "μmol/l"], "concentration", "mol/L", "mol/L", "0.000001")
add_unit(["%", "percent", "percentage", "wt%", "vol%"], "percent", "%", "%")
add_unit(["fraction", "ratio", "dimensionless"], "dimensionless", "1", "1")
add_unit(["ppm"], "concentration_ratio", "ppm", "ppm")
add_unit(["ppb"], "concentration_ratio", "ppb", "ppb")


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, value: Any) -> None:
    path.write_text(dump_json(value), encoding="utf-8", newline="\n")


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def cell_text(value: Any) -> str:
    if value is None:
        return ""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (dict, list)):
        return canonical_json(value)
    return str(value)


def decimal_number(value: Decimal) -> Any:
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def decimal_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        rendered = format(value.normalize(), "f")
        return rendered
    return str(value)


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return decimal_number(value)
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return value


def is_missing_text(text: str) -> bool:
    return normalize_space(text).casefold() in MISSING_TOKENS


def normalize_header(header: str) -> str:
    text = unicodedata.normalize("NFKC", header).lstrip("\ufeff").strip().casefold()
    text = re.sub(r"\s+", " ", text)
    return text


def map_header(raw_header: str) -> tuple[str, Optional[str], Optional[str]]:
    normalized = normalize_header(raw_header)
    if normalized in ALIAS_LOOKUP:
        return normalized, ALIAS_LOOKUP[normalized], None
    match = HEADER_UNIT_RE.match(normalized)
    if match:
        base = normalize_space(match.group(1)).strip("_ -")
        unit = (match.group(2) or match.group(3) or "").strip()
        if base in ALIAS_LOOKUP:
            canonical = ALIAS_LOOKUP[base]
            if canonical == "property_value":
                canonical = "property_value"
            return normalized, canonical, unit or None
    # Header aliases that include a canonical unit without brackets.
    for alias, canonical in sorted(ALIAS_LOOKUP.items(), key=lambda item: -len(item[0])):
        if normalized.startswith(alias + " ") or normalized.startswith(alias + "_"):
            suffix = normalized[len(alias):].strip(" _-")
            if suffix and suffix in UNITS:
                return normalized, canonical, suffix
    return normalized, None, None


def normalize_unit_token(token: str) -> str:
    text = unicodedata.normalize("NFKC", token).strip()
    text = text.replace("−", "-").replace("–", "-")
    text = re.sub(r"\s+", "", text)
    # Molarity case is chemically meaningful; a lower-case bare "m" remains unknown.
    exact_molar = {"M": "molar", "mM": "mmolar", "µM": "umolar", "μM": "umolar"}
    if text in exact_molar:
        return exact_molar[text]
    return text.casefold()


def parse_decimal(token: str) -> Decimal:
    text = token.strip()
    if "," in text:
        if re.fullmatch(r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?(?:[eE][+-]?\d+)?", text):
            text = text.replace(",", "")
        elif "." not in text and re.fullmatch(r"[+-]?\d+,\d+", text):
            text = text.replace(",", ".")
        else:
            raise InvalidOperation("ambiguous numeric grouping")
    return Decimal(text)


def contract_names(contract: Any) -> list[str]:
    if contract is None:
        return []
    if isinstance(contract, str):
        try:
            return contract_names(json.loads(contract))
        except (json.JSONDecodeError, TypeError):
            return [part.strip() for part in re.split(r"[\n,;]+", contract) if part.strip()]
    if isinstance(contract, list):
        names: list[str] = []
        for item in contract:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict):
                descriptor_name = next(
                    (item[key] for key in ("name", "field", "key", "path") if isinstance(item.get(key), str)),
                    None,
                )
                if descriptor_name:
                    names.append(descriptor_name)
                elif len(item) == 1:
                    names.append(str(next(iter(item))))
                else:
                    names.extend(str(key) for key in item)
        return list(dict.fromkeys(names))
    if isinstance(contract, dict):
        return [str(key) for key in contract]
    return [str(contract)]


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


class LineageGuardian:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.case_path = Path(args.case).expanduser().resolve()
        self.task_path = Path(args.task).expanduser().resolve()
        self.out = Path(args.out).expanduser().resolve()
        self.work = Path(args.work).expanduser().resolve()
        self.case_root: Any = None
        self.task_text = ""
        self.case_id: Any = None
        self.raw_contract: Any = None
        self.synthetic = False
        self.sources: list[dict[str, Any]] = []
        self.source_by_path: dict[str, dict[str, Any]] = {}
        self.tables: list[dict[str, Any]] = []
        self.cleaned_rows: list[dict[str, Any]] = []
        self.changes: list[dict[str, Any]] = []
        self.anomalies: list[dict[str, Any]] = []
        self.uncertainty: list[str] = []
        self.errors: list[dict[str, Any]] = []
        self.input_integrity: list[dict[str, Any]] = []
        self.unresolved_contract_fields: list[str] = []
        self.had_input_error = False
        self.had_decode_recovery = False
        self.excluded_empty = 0
        self.seen_paths: set[str] = set()

    # ---------- output primitives and honest partials ----------
    def minimal_result(self, status: str = "partial") -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "status": status,
            "partial": True,
            "stage": "intake_initialization",
            "sources": self.sources,
            "uncertainty": self.uncertainty or ["Run is incomplete; no scientific value has been inferred."],
            "change_records": self.changes,
            "artifacts": {},
            "anomalies": self.anomalies,
            "review_queue": [],
            "errors": self.errors,
            "unresolved_contract_fields": self.unresolved_contract_fields,
        }

    def save_partial(self, stage: str, status: str = "partial") -> None:
        result = self.minimal_result(status)
        result["stage"] = stage
        if self.raw_contract is not None:
            # Preserve contract keys even when the run cannot proceed.
            for key in contract_names(self.raw_contract):
                result.setdefault(key, None)
        write_json(self.out / "result.json", json_safe(result))

    def record_error(self, code: str, message: str, path: Optional[Path] = None) -> None:
        item = {"code": code, "message": message}
        if path is not None:
            item["path"] = str(path)
        self.errors.append(item)

    def add_anomaly(
        self, rule_id: str, category: str, severity: str, message: str,
        *, source_id: Optional[str] = None, row: Optional[dict[str, Any]] = None,
        field: Optional[str] = None, raw_value: Any = None, review: bool = True,
        details: Any = None,
    ) -> dict[str, Any]:
        anomaly = {
            "anomaly_id": f"A{len(self.anomalies) + 1:05d}",
            "rule_id": rule_id, "category": category, "severity": severity,
            "message": message, "source_id": source_id, "row_id": row.get("row_id") if row else None,
            "field": field, "raw_value": raw_value, "review_required": review, "details": details,
        }
        if row:
            anomaly["source_id"] = row["source_id"]
            anomaly["table_id"] = row["table_id"]
            anomaly["row_fingerprint"] = row["row_fingerprint"]
            anomaly["source_locator"] = row["provenance"]["source_locator"]
        self.anomalies.append(anomaly)
        return anomaly

    def add_change(
        self, row: Optional[dict[str, Any]], rule_id: str, field: str, action: str,
        raw_value: Any, new_value: Any, reason: str, *, column: Optional[str] = None,
        formula: Optional[str] = None, unit_from: Optional[str] = None,
        unit_to: Optional[str] = None, precision: Optional[str] = None,
    ) -> None:
        change = {
            "change_id": f"C{len(self.changes) + 1:06d}",
            "example_label": SYNTHETIC_LABEL if self.synthetic else "",
            "rule_id": rule_id, "field": field, "action": action,
            "raw_value": raw_value, "new_value": new_value, "reason": reason,
            "column": column, "formula": formula, "unit_from": unit_from,
            "unit_to": unit_to, "precision": precision,
            "row_id": row.get("row_id") if row else None,
            "source_id": row.get("source_id") if row else None,
            "table_id": row.get("table_id") if row else None,
            "row_fingerprint": row.get("row_fingerprint") if row else None,
            "source_locator": row["provenance"]["source_locator"] if row else None,
        }
        self.changes.append(change)

    # ---------- byte-level intake ----------
    def display_path(self, path: Path) -> str:
        """Prefer stable input-relative paths; retain absolute form only for external files."""
        resolved = path.resolve()
        bases = [self.case_path.parent, self.task_path.parent, Path.cwd().resolve()]
        for base in bases:
            try:
                return str(resolved.relative_to(base.resolve()))
            except (ValueError, OSError):
                continue
        return str(resolved)

    def read_integrity(self, path: Path, role: str) -> tuple[str, dict[str, Any]]:
        data = path.read_bytes()
        bom = data.startswith(b"\xef\xbb\xbf")
        decode_errors = 0
        try:
            text = data.decode("utf-8")
            decode_status = "valid_utf8"
        except UnicodeDecodeError:
            decode_errors = 1
            text = data.decode("utf-8", errors="replace")
            decode_status = "recovered_with_replacement"
            self.had_decode_recovery = True
        meta = {
            "path": self.display_path(path), "role": role, "sha256": sha256_bytes(data), "bytes": len(data),
            "encoding": "UTF-8", "utf8_bom": bom, "decode_status": decode_status,
            "decode_error_events": decode_errors,
            "replacement_character_count": text.count("\ufffd"),
        }
        return text, meta

    def register_source(self, path: Path, role: str, text: str, meta: dict[str, Any], reference: str) -> dict[str, Any]:
        key = str(path.resolve())
        if key in self.source_by_path:
            source = self.source_by_path[key]
            if reference not in source["discovered_via"]:
                source["discovered_via"].append(reference)
            return source
        source = {
            "source_id": f"S{len(self.sources) + 1:03d}", "path": self.display_path(path),
            "path_as_referenced": reference, "role": role, "format": path.suffix.lower().lstrip("."),
            "sha256": meta["sha256"], "bytes": meta["bytes"], "encoding": meta["encoding"],
            "utf8_bom": meta["utf8_bom"], "decode_status": meta["decode_status"],
            "decode_error_events": meta["decode_error_events"],
            "replacement_character_count": meta["replacement_character_count"],
            "discovered_via": [reference], "table_ids": [], "raw_row_count": 0,
        }
        self.sources.append(source)
        self.source_by_path[key] = source
        self.input_integrity.append(meta)
        if meta["decode_error_events"]:
            self.add_anomaly(
                "R-ANM-001", "malformed_encoding", "error",
                "Invalid UTF-8 bytes were replaced with U+FFFD; affected text requires source re-extraction.",
                source_id=source["source_id"], details={"path": self.display_path(path)},
            )
        if meta["replacement_character_count"]:
            self.add_anomaly(
                "R-ANM-002", "replacement_character", "warning",
                "U+FFFD is present in decoded input; it may be original corruption or decode recovery.",
                source_id=source["source_id"],
                details={"count": meta["replacement_character_count"]},
            )
        return source

    # ---------- JSON and path discovery ----------
    def resolve_reference(self, reference: str) -> Optional[Path]:
        ref = reference.strip().strip("<>`\"'")
        if not ref or re.match(r"^[a-z]+://", ref, re.IGNORECASE):
            return None
        path = Path(ref).expanduser()
        candidates = [path] if path.is_absolute() else [self.case_path.parent / path, self.task_path.parent / path, Path.cwd() / path]
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if resolved.is_file():
                return resolved
        return (candidates[0].resolve() if candidates else None)

    def collect_references(self, node: Any, parent_key: str = "") -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        if isinstance(node, dict):
            for key, value in node.items():
                if key in EXCLUDED_JSON_KEYS:
                    continue
                if isinstance(value, str) and Path(value.strip()).suffix.lower() in PATH_SUFFIXES:
                    found.append((value.strip(), f"case_json:{key}"))
                else:
                    found.extend(self.collect_references(value, key))
        elif isinstance(node, list):
            for value in node:
                found.extend(self.collect_references(value, parent_key))
        return found

    def parse_case(self) -> None:
        if not self.case_path.is_file():
            self.had_input_error = True
            self.record_error("CASE_NOT_FOUND", "The case JSON does not exist or is not a file.", self.case_path)
            return
        try:
            text, meta = self.read_integrity(self.case_path, "case_control")
            self.case_root = json.loads(text.lstrip("\ufeff"))
            if isinstance(self.case_root, dict):
                self.case_id = self.case_root.get("case_id", self.case_root.get("id"))
                self.raw_contract = self.case_root.get("output_contract")
                self.synthetic = self.case_root.get("synthetic") is True
            # Case can also be an embedded table source.
            source = self.register_source(self.case_path, "case_json", text, meta, self.display_path(self.case_path))
            self.discover_json_tables(self.case_root, source)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            self.had_input_error = True
            self.record_error("CASE_PARSE_ERROR", f"Case JSON could not be parsed: {exc}", self.case_path)
            try:
                raw = self.case_path.read_bytes()
                text = raw.decode("utf-8", errors="replace")
                self.input_integrity.append({
                    "path": str(self.case_path), "role": "case_control", "sha256": sha256_bytes(raw),
                    "bytes": len(raw), "decode_status": "parse_failed", "utf8_bom": raw.startswith(b"\xef\xbb\xbf"),
                    "replacement_character_count": text.count("\ufffd"),
                })
                # If the output_contract fragment itself is complete JSON, retain its requested
                # top-level keys without pretending the enclosing case parsed successfully.
                marker = re.search(r'"output_contract"\s*:\s*', text)
                if marker:
                    try:
                        self.raw_contract, _ = json.JSONDecoder().raw_decode(text, marker.end())
                    except json.JSONDecodeError:
                        self.raw_contract = None
                for ref in re.findall(r"[A-Za-z0-9_./\\-]+\.(?:csv|tsv|json)", text, re.IGNORECASE):
                    self.referenced_paths.append((ref, "recovered_case_text"))
            except OSError:
                pass

    def parse_task(self) -> None:
        if not self.task_path.is_file():
            self.had_input_error = True
            self.record_error("TASK_NOT_FOUND", "Task text was not found; table discovery continues from case/input.", self.task_path)
            return
        try:
            text, meta = self.read_integrity(self.task_path, "task_control")
            self.task_text = text
            self.input_integrity.append(meta)
            for ref in re.findall(r"[A-Za-z0-9_./\\-]+\.(?:csv|tsv|json)", text, re.IGNORECASE):
                self.referenced_paths.append((ref, "task_markdown"))
        except OSError as exc:
            self.had_input_error = True
            self.record_error("TASK_READ_ERROR", str(exc), self.task_path)

    def discover_materials(self) -> None:
        self.referenced_paths: list[tuple[str, str]] = []
        self.parse_case()
        self.parse_task()
        if self.case_root is not None:
            self.referenced_paths.extend(self.collect_references(self.case_root))
        # Directory scan finds material supplied beside case.json even if a wrapper omitted a path.
        base = self.case_path.parent
        if base.is_dir():
            try:
                for path in sorted(base.rglob("*"), key=lambda p: str(p)):
                    if not path.is_file() or path.suffix.lower() not in PATH_SUFFIXES:
                        continue
                    resolved = path.resolve()
                    if resolved in {self.case_path, self.task_path}:
                        continue
                    if is_relative_to(resolved, self.out) or is_relative_to(resolved, self.work):
                        continue
                    self.referenced_paths.append((str(resolved), "input_directory_scan"))
            except OSError as exc:
                self.record_error("INPUT_SCAN_ERROR", str(exc), base)
        unique: list[tuple[str, str, Path]] = []
        for reference, origin in self.referenced_paths:
            resolved = self.resolve_reference(reference)
            if resolved is None:
                continue
            if resolved == self.case_path:
                continue
            key = str(resolved)
            if key in self.seen_paths:
                continue
            self.seen_paths.add(key)
            unique.append((reference, origin, resolved))
        for reference, origin, path in unique:
            if not path.is_file():
                self.had_input_error = True
                self.record_error("MATERIAL_NOT_FOUND", f"Referenced material is unavailable: {reference}", path)
                continue
            try:
                text, meta = self.read_integrity(path, "material")
                source = self.register_source(path, "material", text, meta, f"{origin}:{reference}")
                if path.suffix.lower() in {".csv", ".tsv"}:
                    self.parse_csv_table(text, source, delimiter="\t" if path.suffix.lower() == ".tsv" else ",")
                elif path.suffix.lower() == ".json":
                    try:
                        root = json.loads(text.lstrip("\ufeff"))
                        before = len(self.tables)
                        self.discover_json_tables(root, source)
                        if len(self.tables) == before:
                            self.add_anomaly(
                                "R-INT-004", "json_without_table", "warning",
                                "Referenced JSON contains no recognized nested table.", source_id=source["source_id"],
                            )
                    except json.JSONDecodeError as exc:
                        self.had_input_error = True
                        self.record_error("MATERIAL_JSON_ERROR", str(exc), path)
                        self.add_anomaly(
                            "R-ERR-002", "malformed_material", "error", "Material JSON could not be parsed.",
                            source_id=source["source_id"], details=str(exc),
                        )
            except (OSError, csv.Error) as exc:
                self.had_input_error = True
                self.record_error("MATERIAL_READ_ERROR", str(exc), path)

    def make_table(self, source: dict[str, Any], format_name: str, pointer: str, raw_headers: list[str]) -> dict[str, Any]:
        table = {
            "table_id": f"T{len(self.tables) + 1:03d}", "source_id": source["source_id"],
            "format": format_name, "source_locator": pointer, "columns": [], "raw_rows": [],
        }
        for index, header in enumerate(raw_headers):
            normalized, canonical, default_unit = map_header(header)
            table["columns"].append({
                "column_index": index, "column_key": header, "raw_header": header,
                "normalized_header": normalized, "canonical_field": canonical, "default_unit": default_unit,
            })
        self.tables.append(table)
        source["table_ids"].append(table["table_id"])
        return table

    def discover_json_tables(self, root: Any, source: dict[str, Any]) -> None:
        def add_table(rows: list[Any], columns: Optional[list[Any]], pointer: str) -> None:
            if columns is not None:
                headers = [cell_text(column) for column in columns]
            else:
                headers = []
                for record in rows:
                    if isinstance(record, dict):
                        for key in record:
                            if str(key) not in headers:
                                headers.append(str(key))
            table = self.make_table(source, "json", pointer, headers)
            for row_index, record in enumerate(rows, start=1):
                cells = []
                if isinstance(record, dict):
                    for col_index, header in enumerate(headers):
                        present = header in record
                        cells.append({
                            "column_index": col_index, "column_key": header, "raw_header": header,
                            "value": record.get(header), "present": present,
                        })
                elif isinstance(record, list):
                    for col_index, header in enumerate(headers):
                        present = col_index < len(record)
                        cells.append({
                            "column_index": col_index, "column_key": header, "raw_header": header,
                            "value": record[col_index] if present else None, "present": present,
                        })
                else:
                    headers = headers or ["value"]
                    if not table["columns"]:
                        table = self.make_table(source, "json", pointer, headers)
                    cells = [{"column_index": 0, "column_key": "value", "raw_header": "value", "value": record, "present": True}]
                row_pointer = f"{pointer}/{row_index - 1}"
                self.add_raw_row(table, cells, row_pointer)

        def walk(node: Any, pointer: str = "$", parent_key: str = "") -> None:
            if isinstance(node, dict):
                for column_key in ("columns", "headers", "fields"):
                    for row_key in ("rows", "records", "data"):
                        if isinstance(node.get(column_key), list) and isinstance(node.get(row_key), list):
                            add_table(node[row_key], node[column_key], f"{pointer}/{row_key}")
                            return
                for key, value in node.items():
                    if key in EXCLUDED_JSON_KEYS:
                        continue
                    walk(value, f"{pointer}/{key}", str(key))
            elif isinstance(node, list):
                wrappers = any(isinstance(item, dict) and any(k in item for k in ("columns", "headers")) for item in node)
                descriptor_only = bool(node) and all(
                    isinstance(item, dict) and any(str(v).lower().endswith(tuple(PATH_SUFFIXES)) for v in item.values() if isinstance(v, str))
                    and not any(k in item for k in ("value", "result", "property", "material")) for item in node
                )
                is_records = bool(node) and all(isinstance(item, dict) for item in node) and not wrappers and not descriptor_only
                if (is_records and (parent_key in RECORD_KEYS or pointer == "$")) or (
                    not node and parent_key in {"rows", "records"}
                ):
                    add_table(node, None, pointer)
                    return
                for index, item in enumerate(node):
                    walk(item, f"{pointer}/{index}", parent_key)
        walk(root)

    # ---------- CSV intake with exact raw row identities ----------
    def parse_csv_table(self, text: str, source: dict[str, Any], delimiter: str = ",") -> None:
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
        physical_rows: list[tuple[list[str], int, int]] = []
        try:
            previous_end = 1
            for parsed in reader:
                line_end = reader.line_num
                physical_rows.append((parsed, previous_end, line_end))
                previous_end = line_end + 1
        except csv.Error as exc:
            self.had_input_error = True
            self.add_anomaly(
                "R-ERR-002", "malformed_csv", "error", "CSV parser failed; no rows from this source were trusted.",
                source_id=source["source_id"], details=str(exc),
            )
            return
        rows = [item[0] for item in physical_rows]
        if not rows:
            table = self.make_table(source, "csv", "$/rows", [])
            self.add_anomaly(
                "R-ANM-006", "empty_table", "warning", "The CSV source has no header or records.",
                source_id=source["source_id"],
            )
            return
        raw_headers = rows[0]
        column_keys: list[str] = []
        counts: Counter[str] = Counter()
        for header in raw_headers:
            counts[header] += 1
            column_keys.append(header if counts[header] == 1 else f"{header}#{counts[header]}")
        table = self.make_table(source, "csv", "$/rows", column_keys)
        for column, raw_header in zip(table["columns"], raw_headers):
            column["raw_header"] = raw_header
            normalized, canonical, default_unit = map_header(raw_header)
            column.update({"normalized_header": normalized, "canonical_field": canonical, "default_unit": default_unit})
        for header, count in counts.items():
            if count > 1:
                self.add_anomaly(
                    "R-FLD-004", "duplicate_header", "warning",
                    "Duplicate raw headers were disambiguated by occurrence, not overwritten.",
                    source_id=source["source_id"], field=header, details={"occurrences": count},
                )
        for row_index, values in enumerate(rows[1:], start=1):
            cells = []
            for col_index, column_key in enumerate(column_keys):
                present = col_index < len(values)
                cells.append({
                    "column_index": col_index, "column_key": column_key,
                    "raw_header": raw_headers[col_index], "value": values[col_index] if present else "",
                    "present": present,
                })
            for extra_index, value in enumerate(values[len(column_keys):], start=1):
                col_index = len(column_keys) + extra_index - 1
                cells.append({
                    "column_index": col_index, "column_key": f"__extra_cell_{extra_index}",
                    "raw_header": "__extra_cell__", "value": value, "present": True,
                })
            row = self.add_raw_row(table, cells, f"$/{row_index}")
            _, line_start, line_end = physical_rows[row_index]
            row["physical_line_start"] = line_start
            row["physical_line_end"] = line_end
            if len(values) != len(column_keys):
                self.add_anomaly(
                    "R-INT-003", "ragged_csv_row", "warning",
                    "CSV row width differs from header; absent cells stayed null and extra cells were preserved.",
                    source_id=source["source_id"], row=row,
                    details={"header_columns": len(column_keys), "row_columns": len(values)},
                )

    def add_raw_row(self, table: dict[str, Any], cells: list[dict[str, Any]], pointer: str) -> dict[str, Any]:
        source = next(source for source in self.sources if source["source_id"] == table["source_id"])
        row_index = len(table["raw_rows"]) + 1
        fingerprint = sha256_bytes(canonical_json(cells).encode("utf-8"))
        empty = all(is_missing_text(cell_text(cell["value"])) for cell in cells)
        raw_row = {
            "example_label": SYNTHETIC_LABEL if self.synthetic else "",
            "row_id": f"{table['table_id']}-R{row_index:05d}", "source_id": source["source_id"],
            "table_id": table["table_id"], "source_row_index": row_index,
            "source_locator": pointer, "json_pointer": pointer if table["format"] == "json" else None,
            "physical_line_start": None, "physical_line_end": None,
            "raw_cells": cells, "row_fingerprint": fingerprint, "empty": empty,
        }
        table["raw_rows"].append(raw_row)
        source["raw_row_count"] += 1
        return raw_row

    # ---------- field and value normalization ----------
    def flag(self, row: dict[str, Any], flag: str) -> None:
        if flag not in row["quality_flags"]:
            row["quality_flags"].append(flag)

    def normalize_raw_text(self, row: dict[str, Any], field: str, raw: Any, column: Optional[str]) -> Optional[str]:
        if raw is None:
            return None
        original = cell_text(raw)
        cleaned = unicodedata.normalize("NFC", original).lstrip("\ufeff").strip()
        if cleaned != original:
            self.add_change(row, "R-VAL-001", field, "trim_unicode", original, cleaned, "Outer whitespace/BOM removed; raw value retained.", column=column)
        if is_missing_text(cleaned):
            if original.strip():
                self.add_change(row, "R-VAL-003", field, "null_missing_token", original, None, "Recognized missing token; no value inferred.", column=column)
            return None
        if "\ufffd" in cleaned:
            self.flag(row, "replacement_character")
            self.add_anomaly(
                "R-ANM-002", "replacement_character", "warning",
                "Affected cell contains U+FFFD; verify it against the original extraction.",
                row=row, field=field, raw_value=original,
            )
        return cleaned

    def new_cleaned_row(self, raw: dict[str, Any]) -> dict[str, Any]:
        row = {field: None for field in CANONICAL_FIELDS}
        row.update({
            "example_label": SYNTHETIC_LABEL if self.synthetic else "",
            "row_id": raw["row_id"], "source_id": raw["source_id"], "table_id": raw["table_id"],
            "source_row_index": raw["source_row_index"], "row_fingerprint": raw["row_fingerprint"],
            "row_status": "needs_review", "include_in_statistics": False,
            "duplicate_status": "unique", "duplicate_group_id": None,
            "conditions_canonical": None, "unmapped_fields": {}, "quality_flags": [],
            "provenance": {
                "source_id": raw["source_id"], "table_id": raw["table_id"], "row_id": raw["row_id"],
                "source_row_index": raw["source_row_index"], "source_locator": raw["source_locator"],
                "json_pointer": raw["json_pointer"], "row_fingerprint": raw["row_fingerprint"],
            },
        })
        return row

    def process_rows(self) -> None:
        for table in self.tables:
            column_by_key = {column["column_key"]: column for column in table["columns"]}
            for raw in table["raw_rows"]:
                if raw["empty"]:
                    self.excluded_empty += 1
                    raw["disposition"] = "excluded_empty"
                    row_stub = self.new_cleaned_row(raw)
                    self.flag(row_stub, "empty_row")
                    self.add_anomaly(
                        "R-ANM-006", "empty_row", "warning",
                        "An entirely empty/missing-token row was excluded from cleaned rows but retained in raw_snapshot.json.",
                        row=row_stub,
                    )
                    self.add_change(row_stub, "R-ANM-006", "row_status", "exclude_empty", "empty", "excluded_empty", "No scientific cells were available; exclusion is explicit and reversible.")
                    continue
                row = self.new_cleaned_row(raw)
                raw["disposition"] = "cleaned"
                assignments: dict[str, tuple[Any, str, Optional[str]]] = {}
                for cell in raw["raw_cells"]:
                    column = column_by_key.get(cell["column_key"], {
                        "raw_header": cell["raw_header"], "canonical_field": None, "default_unit": None,
                    })
                    canonical = column["canonical_field"]
                    key = cell["column_key"]
                    if canonical is None:
                        row["unmapped_fields"][key] = cell["value"]
                        self.add_change(
                            row, "R-FLD-003", "unmapped_fields", "preserve_unmapped", cell["value"], cell["value"],
                            "No safe alias was found; original cell remains in unmapped_fields.", column=key,
                        )
                        if not is_missing_text(cell_text(cell["value"])):
                            self.flag(row, "unmapped_nonempty_field")
                        continue
                    target = "property_value" if canonical == "property_value" else canonical
                    if target in assignments and not is_missing_text(cell_text(cell["value"])):
                        old_raw, old_key, _ = assignments[target]
                        if not is_missing_text(cell_text(old_raw)) and cell_text(old_raw) != cell_text(cell["value"]):
                            row["unmapped_fields"][key] = cell["value"]
                            self.flag(row, "conflicting_column_aliases")
                            self.add_anomaly(
                                "R-FLD-005", "conflicting_column_aliases", "error",
                                "Two non-empty columns map to one canonical field with different values; the later value was not overwritten.",
                                row=row, field=target, raw_value=cell["value"],
                                details={"kept_column": old_key, "conflicting_column": key},
                            )
                            continue
                    assignments[target] = (cell["value"], key, column.get("default_unit"))
                    if normalize_header(column["raw_header"]) != target and target != "property_value":
                        self.add_change(
                            row, "R-FLD-002", target, "map_column_alias", column["raw_header"], target,
                            "Header alias mapped by the explicit dictionary; cell content unchanged.", column=key,
                        )
                defaults: dict[str, Optional[str]] = {}
                for canonical, (raw_value, column, default_unit) in assignments.items():
                    defaults[canonical] = default_unit
                    value = self.normalize_raw_text(row, canonical, raw_value, column)
                    if canonical == "property_value":
                        row["property_value_raw"] = cell_text(raw_value) if raw_value is not None else None
                        row["property_value_text"] = value
                    elif canonical in CANONICAL_FIELDS:
                        row[canonical] = value
                    # A standalone unit field requires no numeric parser here.
                self.normalize_property_name(row, assignments.get("property_name", (None, None, None))[1])
                self.normalize_measurements(row, assignments, defaults)
                self.required_field_checks(row)
                self.finalize_row(row)
                self.cleaned_rows.append(row)

    def normalize_property_name(self, row: dict[str, Any], column: Optional[str]) -> None:
        value = row.get("property_name")
        if not value:
            return
        spaced = normalize_space(value)
        lookup = spaced.casefold().replace("-", " ")
        canonical = PROPERTY_SYNONYMS.get(lookup)
        if canonical:
            self.add_change(row, "R-NAM-001", "property_name", "canonicalize_name", value, canonical, "Only an explicit property synonym rule was applied.", column=column)
            row["property_name"] = canonical
        elif spaced != value:
            self.add_change(row, "R-VAL-002", "property_name", "collapse_whitespace", value, spaced, "Whitespace normalized without changing terminology.", column=column)
            row["property_name"] = spaced

    def parse_measurement(self, text: Optional[str], fallback_unit: Optional[str]) -> dict[str, Any]:
        result: dict[str, Any] = {
            "number": None, "min": None, "max": None, "unit_token": fallback_unit,
            "explicit_unit": None, "is_range": False, "parse_error": None,
        }
        if text is None:
            return result
        match = RANGE_RE.match(text)
        try:
            if match:
                result.update({
                    "min": parse_decimal(match.group(1)), "max": parse_decimal(match.group(2)),
                    "explicit_unit": match.group(3).strip() or None, "is_range": True,
                })
            else:
                match = SCALAR_RE.match(text)
                if match:
                    result.update({"number": parse_decimal(match.group(1)), "explicit_unit": match.group(2).strip() or None})
                else:
                    result["parse_error"] = "not_a_supported_numeric_or_range"
            if result["explicit_unit"]:
                result["unit_token"] = result["explicit_unit"]
        except (InvalidOperation, ValueError) as exc:
            result["parse_error"] = str(exc)
        if result["min"] is not None and result["max"] is not None and result["min"] > result["max"]:
            result["parse_error"] = "reversed_range"
        return result

    def convert_number(self, value: Optional[Decimal], unit_info: dict[str, Any], unit_token: str) -> tuple[Optional[Decimal], str]:
        if value is None:
            return None, ""
        family = unit_info["family"]
        token = normalize_unit_token(unit_token)
        if family == "temperature":
            if token == "k":
                return value - Decimal("273.15"), "C = K - 273.15"
            if token in {"°f", "℉", "degf", "fahrenheit"}:
                return (value - Decimal("32")) * Decimal(5) / Decimal(9), "C = (F - 32) * 5/9"
            return value, "C = C"
        factor: Decimal = unit_info["factor"]
        if factor == 1:
            return value, "value * 1"
        return value * factor, f"value * {format(factor, 'f')}"

    def normalize_measurements(
        self, row: dict[str, Any], assignments: dict[str, tuple[Any, str, Optional[str]]],
        defaults: dict[str, Optional[str]],
    ) -> None:
        separate_unit = row.get("unit_raw")
        property_fallback = separate_unit or defaults.get("property_value")
        parsed_property = self.parse_measurement(row.get("property_value_text"), property_fallback)
        self.apply_measurement(row, "property", parsed_property, assignments.get("property_value", (None, None, None))[1])
        condition_specs = [
            ("temperature", "temperature_c", "temperature_c"),
            ("pressure", "pressure_kpa", "pressure_kpa"),
            ("time", "time_s", "time_s"),
            ("concentration", "concentration", "concentration"),
        ]
        for key, field, assignment_key in condition_specs:
            value = row.get(field)
            if key == "concentration":
                value = row.get("concentration")
            fallback = row.get("concentration_unit") if key == "concentration" else defaults.get(assignment_key)
            parsed = self.parse_measurement(value, fallback)
            self.apply_measurement(row, key, parsed, assignments.get(assignment_key, (None, None, None))[1])
        # Promote generic properties to condition fields only when both unit family and property name agree.
        prop = (row.get("property_name") or "").casefold()
        family = row.get("unit_family")
        promotion = {
            "temperature": ("temperature_c", {"temperature", "temp", "annealing_temperature", "glass_transition_temperature"}),
            "pressure": ("pressure_kpa", {"pressure"}),
            "time": ("time_s", {"time", "duration", "annealing_time", "reaction_time", "holding_time"}),
            "concentration": ("concentration", {"concentration", "molarity"}),
        }
        if family in promotion and any(token in prop for token in promotion[family][1]):
            target = promotion[family][0]
            if row.get(target) is None and row.get(f"{target}_min") is None:
                row[target] = row.get("value_standard")
                row[f"{target}_min"] = row.get("value_standard_min")
                row[f"{target}_max"] = row.get("value_standard_max")
                if family == "concentration":
                    row["concentration_unit"] = row.get("unit_canonical")
                self.add_change(
                    row, "R-FLD-006", target, "promote_semantic_condition", row.get("property_value_text"), row.get(target),
                    "Property name and unit family agree; generic value also exposed in a typed condition field.",
                )

    def apply_measurement(self, row: dict[str, Any], kind: str, parsed: dict[str, Any], column: Optional[str]) -> None:
        if kind == "property":
            raw_text = row.get("property_value_text")
            raw_field = "property_value_text"
        else:
            base = {"temperature": "temperature_c", "pressure": "pressure_kpa", "time": "time_s", "concentration": "concentration"}[kind]
            raw_text = row.get(base)
            raw_field = base
        if raw_text is None:
            return
        raw_values = (parsed["number"], parsed["min"], parsed["max"])
        if kind == "property":
            row["property_value_number"], row["property_value_min"], row["property_value_max"] = [decimal_number(v) if v is not None else None for v in raw_values]
        if parsed["is_range"]:
            self.add_change(
                row, "R-VAL-005", raw_field, "parse_range", raw_text,
                [decimal_text(parsed["min"]), decimal_text(parsed["max"])],
                "Range endpoints preserved separately; no midpoint was invented.", column=column,
            )
        if parsed["explicit_unit"]:
            self.add_change(
                row, "R-UNIT-008", raw_field, "split_value_unit", raw_text, parsed["unit_token"],
                "Unit was parsed from the value cell; numeric text and unit remain traceable.", column=column,
            )
        if parsed["parse_error"]:
            self.flag(row, "unparsed_numeric" if parsed["parse_error"] != "reversed_range" else "reversed_range")
            self.add_anomaly(
                "R-ANM-004" if parsed["parse_error"] != "reversed_range" else "R-ANM-007",
                "numeric_parse", "warning", f"Value was preserved but not standardized: {parsed['parse_error']}.",
                row=row, field=raw_field, raw_value=raw_text,
            )
            return
        if all(value is None for value in raw_values):
            return
        token = parsed.get("unit_token")
        if not token:
            self.flag(row, "missing_unit")
            self.add_anomaly(
                "R-ANM-010", "missing_unit", "warning",
                "A numeric value has no declared unit; no unit was guessed.",
                row=row, field=raw_field, raw_value=raw_text,
            )
            return
        normalized_token = normalize_unit_token(token)
        unit_info = UNITS.get(normalized_token)
        if unit_info is None:
            if kind == "property":
                row["unit_raw"] = token
            self.flag(row, "unknown_unit")
            self.add_anomaly(
                "R-ANM-005", "unknown_unit", "warning",
                "Unit is not in the explicit conversion dictionary; value remains unconverted.",
                row=row, field=raw_field, raw_value=token,
            )
            self.add_change(
                row, "R-UNIT-007", raw_field, "flag_unknown_unit", raw_text, None,
                "No conversion was attempted for an unknown or context-ambiguous unit.", column=column, unit_from=token,
            )
            return
        converted = [self.convert_number(value, unit_info, token) for value in raw_values]
        converted_values = [item[0] for item in converted]
        formulas = sorted({item[1] for item in converted if item[1]})
        family = unit_info["family"]
        canonical = unit_info["canonical"]
        if kind == "property":
            row["unit_raw"] = token
            row["unit_canonical"] = canonical if unit_info["target"] != canonical else unit_info["target"]
            row["unit_family"] = family
            row["value_standard"], row["value_standard_min"], row["value_standard_max"] = [
                decimal_number(value) if value is not None else None for value in converted_values
            ]
            targets = ("value_standard", "value_standard_min", "value_standard_max")
        else:
            base = {"temperature": "temperature_c", "pressure": "pressure_kpa", "time": "time_s", "concentration": "concentration"}[kind]
            if kind == "concentration":
                row["concentration_unit"] = canonical if unit_info["target"] != canonical else unit_info["target"]
            row[base], row[f"{base}_min"], row[f"{base}_max"] = [
                decimal_number(value) if value is not None else None for value in converted_values
            ]
            targets = (base, f"{base}_min", f"{base}_max")
        before = [decimal_number(value) if value is not None else None for value in raw_values]
        after = [decimal_number(value) if value is not None else None for value in converted_values]
        if before != after or normalize_unit_token(token) != normalize_unit_token(unit_info["target"]):
            self.add_change(
                row, "R-UNIT-002", raw_field, "convert_unit", before, after,
                "Base-unit conversion uses exact decimal factors; original cell and formula are retained.",
                column=column, formula="; ".join(formulas), unit_from=token, unit_to=unit_info["target"],
                precision="Decimal arithmetic; JSON numbers emitted without significance padding",
            )
        for target, value in zip(targets, after):
            if value is not None:
                row[target] = value

    def required_field_checks(self, row: dict[str, Any]) -> None:
        if not row.get("material_name") and not row.get("material_id"):
            self.flag(row, "missing_material")
            self.add_anomaly(
                "R-ANM-003", "missing_required", "error", "Material name and identifier are both absent; no material was inferred.",
                row=row, field="material_name",
            )
        if not row.get("property_name"):
            self.flag(row, "missing_property")
            self.add_anomaly(
                "R-ANM-003", "missing_required", "error", "Property name is absent; no metric was inferred from a value or unit.",
                row=row, field="property_name",
            )
        raw_property = row.get("property_value_raw")
        if raw_property is None or is_missing_text(cell_text(raw_property)):
            self.flag(row, "missing_value")
            self.add_anomaly(
                "R-ANM-003", "missing_value", "error", "Property value is absent or explicitly missing; null is retained.",
                row=row, field="property_value_raw",
            )
        if row.get("unmapped_fields"):
            self.flag(row, "unmapped_fields_present")

    def finalize_row(self, row: dict[str, Any]) -> None:
        # Context fingerprint is deliberately separate from duplicate merging.
        context = {
            "temperature": [row.get("temperature_c"), row.get("temperature_c_min"), row.get("temperature_c_max")],
            "pressure": [row.get("pressure_kpa"), row.get("pressure_kpa_min"), row.get("pressure_kpa_max")],
            "time": [row.get("time_s"), row.get("time_s_min"), row.get("time_s_max")],
            "concentration": [row.get("concentration"), row.get("concentration_min"), row.get("concentration_max"), row.get("concentration_unit")],
            "conditions": normalize_space(row.get("conditions") or "").casefold(),
            "experiment_id": normalize_space(row.get("experiment_id") or "").casefold(),
        }
        row["conditions_canonical"] = context
        blocking = {"missing_material", "missing_property", "missing_value", "conflicting_column_aliases"}
        row["include_in_statistics"] = not any(flag in blocking for flag in row["quality_flags"])
        row["row_status"] = "needs_review" if row["quality_flags"] else "cleaned"

    # ---------- non-destructive duplicate analysis ----------
    def duplicate_analysis(self) -> None:
        exact_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        semantic_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        semantic_keys: dict[str, str] = {}
        for row in self.cleaned_rows:
            exact_groups[row["row_fingerprint"]].append(row)
            material_id = re.sub(r"[^a-z0-9]", "", (row.get("material_id") or "").casefold())
            material_name = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", unicodedata.normalize("NFKC", row.get("material_name") or "").casefold())
            material_key = ("id:" + material_id) if material_id else ("name:" + material_name)
            prop = normalize_space(row.get("property_name") or "").casefold()
            values = [row.get("value_standard"), row.get("value_standard_min"), row.get("value_standard_max")]
            if material_key in {"id:", "name:"} or not prop or all(value is None for value in values) or not row.get("unit_canonical"):
                continue
            key_obj = {
                "material": material_key, "property": prop, "values": values,
                "unit": row.get("unit_canonical"), "reference": normalize_space(row.get("literature_ref") or "").casefold(),
            }
            key = sha256_bytes(canonical_json(key_obj).encode("utf-8"))
            semantic_groups[key].append(row)
            semantic_keys[key] = canonical_json(key_obj)
        grouped_rows: set[str] = set()
        for fingerprint, rows in exact_groups.items():
            if len(rows) < 2:
                continue
            group_id = "X" + fingerprint[:10]
            for row in rows:
                row["duplicate_status"] = "exact_duplicate_candidate"
                row["duplicate_group_id"] = group_id
                self.flag(row, "exact_duplicate_candidate")
                self.add_change(row, "R-DUP-001", "duplicate_status", "flag_only", "unique", "exact_duplicate_candidate", "Identical raw row fingerprints; every row retained for human review.")
                self.add_anomaly("R-DUP-001", "duplicate", "warning", "Exact duplicate candidate; no row was dropped or merged.", row=row, details={"group_id": group_id})
                grouped_rows.add(row["row_id"])
        duplicate_group_count = 0
        for key, rows in semantic_groups.items():
            if len(rows) < 2:
                continue
            duplicate_group_count += 1
            group_id = "D" + key[:10]
            contexts: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in rows:
                context_key = canonical_json(row["conditions_canonical"])
                contexts[context_key].append(row)
                row["duplicate_group_id"] = row["duplicate_group_id"] or group_id
            if len(contexts) > 1:
                for row in rows:
                    self.flag(row, "same_core_different_context")
                    self.add_anomaly(
                        "R-DUP-003", "context_conflict", "error",
                        "Rows share material/property/value but differ in experiment context; merging is forbidden without adjudication.",
                        row=row, details={"group_id": group_id, "semantic_key": semantic_keys[key]},
                    )
                    self.add_change(row, "R-DUP-003", "duplicate_status", "flag_only", row["duplicate_status"], "same_core_different_context", "Context differs; records remain distinct.", column=None)
                    row["duplicate_status"] = "same_core_different_context"
                    grouped_rows.add(row["row_id"])
            for context_rows in contexts.values():
                if len(context_rows) < 2:
                    continue
                for row in context_rows:
                    # Preserve the stronger context-conflict status if one was just assigned.
                    if row["duplicate_status"] == "same_core_different_context":
                        self.flag(row, "duplicate_candidate_within_context")
                        status = "same_core_different_context+duplicate_within_context"
                        row["duplicate_status"] = status
                    else:
                        row["duplicate_status"] = "duplicate_extraction_candidate"
                    self.flag(row, "duplicate_extraction_candidate")
                    self.add_change(row, "R-DUP-002", "duplicate_status", "flag_only", "unique", row["duplicate_status"], "Same semantic measurement key and experiment context; all candidates retained.")
                    self.add_anomaly("R-DUP-002", "duplicate", "warning", "Duplicate extraction candidate within one context; no automatic merge occurred.", row=row, details={"group_id": group_id})
                    grouped_rows.add(row["row_id"])
        for row in self.cleaned_rows:
            if row["row_id"] in grouped_rows:
                row["row_status"] = "needs_review"
        self.duplicate_group_count = duplicate_group_count + sum(1 for rows in exact_groups.values() if len(rows) > 1)

    # ---------- result, review queue, audit ----------
    def build_review_queue(self) -> dict[str, Any]:
        items = []
        for index, anomaly in enumerate((a for a in self.anomalies if a["review_required"]), start=1):
            item = dict(anomaly)
            item["review_id"] = f"Q{index:05d}"
            item["recommended_action"] = self.recommended_action(anomaly)
            items.append(item)
        return {
            "example_label": SYNTHETIC_LABEL if self.synthetic else "",
            "items": items, "item_count": len(items),
            "policy": "Human review is required for listed items; no duplicate or unknown unit was silently resolved.",
        }

    @staticmethod
    def recommended_action(anomaly: dict[str, Any]) -> str:
        category = anomaly["category"]
        return {
            "malformed_encoding": "Re-read the original bytes/source document and replace U+FFFD only from evidence.",
            "replacement_character": "Verify the affected cell against the source; do not guess the lost character.",
            "missing_value": "Consult the cited source; leave null if it is not reported.",
            "missing_required": "Supply an evidenced field or retain null with the review flag.",
            "unknown_unit": "Confirm unit definition and locality before adding a conversion rule.",
            "missing_unit": "Find an explicit unit in context/header; leave unconverted if absent.",
            "duplicate": "Compare source contexts and decide externally; the pipeline intentionally keeps all rows.",
            "context_conflict": "Treat as distinct experiments unless documentary evidence proves identity.",
            "numeric_parse": "Review notation or extend a versioned numeric rule; preserve raw text meanwhile.",
            "conflicting_column_aliases": "Choose the correct source column using evidence; both cells remain preserved.",
        }.get(category, "Inspect the source locator and record a documented human decision.")

    def source_ids(self) -> list[str]:
        return [source["source_id"] for source in self.sources]

    def artifact_info(self, name: str, description: str) -> dict[str, Any]:
        path = self.out / name
        return {
            "file": name, "description": description, "sha256": sha256_file(path), "bytes": path.stat().st_size,
            "generated_from_source_ids": self.source_ids(),
        }

    def status(self) -> str:
        if self.had_input_error and not self.cleaned_rows:
            return "input_error"
        if self.had_input_error or self.had_decode_recovery:
            return "partial"
        if not self.tables and not self.cleaned_rows:
            return "input_error"
        return "success"

    def uncertainty_text(self) -> list[str]:
        items = list(self.uncertainty)
        items.extend([
            "Only the supplied extraction records were cleaned; original papers were not independently re-read by this script.",
            "Unknown, missing, or context-ambiguous units were not converted or inferred.",
            "Duplicate and context-conflict flags are non-destructive candidates; no rows were merged or dropped as duplicates.",
        ])
        if self.synthetic:
            items.insert(0, "SYNTHETIC EXAMPLE ONLY: these are generated teaching records, not official answers or real experiments.")
        if self.had_decode_recovery:
            items.append("At least one input required UTF-8 replacement decoding; affected characters cannot be reconstructed automatically.")
        if self.unresolved_contract_fields:
            items.append("Unresolved output-contract keys are null and listed in unresolved_contract_fields; no placeholder values were fabricated.")
        if any(a["category"] in {"missing_value", "missing_required"} for a in self.anomalies):
            items.append("Missing fields remain null/empty; absence of an anomaly for a field is not evidence that a paper reports it.")
        return list(dict.fromkeys(items))

    def build_semantics(self, review: dict[str, Any], artifacts: dict[str, Any]) -> dict[str, Any]:
        return {
            "case_id": self.case_id, "status": self.status(), "sources": self.sources,
            "uncertainty": self.uncertainty_text(), "change_records": self.changes,
            "artifacts": artifacts, "cleaned_rows": self.cleaned_rows, "cleaned_data": self.cleaned_rows,
            "cleaned_csv": "cleaned_rows.csv", "raw_snapshot": "raw_snapshot.json",
            "anomalies": self.anomalies, "review_queue": review, "review_items": review["items"],
            "audit_report": "audit_report.md", "change_log": self.changes,
            "warnings": self.anomalies, "errors": self.errors, "evidence": self.sources,
            "provenance": self.sources, "partial": self.status() in {"partial", "input_error", "error"},
            "unresolved_contract_fields": self.unresolved_contract_fields,
            "input_fingerprint": self.input_fingerprint(),
        }

    def input_fingerprint(self) -> str:
        payload = [{"path": item.get("path"), "sha256": item.get("sha256")} for item in self.input_integrity]
        return sha256_bytes(canonical_json(payload).encode("utf-8"))

    def write_outputs(self) -> dict[str, Any]:
        self.duplicate_analysis()
        review = self.build_review_queue()
        raw_snapshot = {
            "schema_version": VERSION, "example_label": SYNTHETIC_LABEL if self.synthetic else "",
            "case_id": self.case_id, "policy": "Raw cells, header occurrences, row identities, and SHA256 fingerprints are preserved before normalization.",
            "tables": self.tables,
        }
        write_json(self.out / "raw_snapshot.json", raw_snapshot)
        write_json(self.out / "cleaned_rows.json", self.cleaned_rows)
        with (self.out / "cleaned_rows.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, lineterminator="\n", extrasaction="ignore")
            writer.writeheader()
            for row in self.cleaned_rows:
                flat = dict(row)
                flat["source_locator"] = row["provenance"]["source_locator"]
                flat["unmapped_fields"] = canonical_json(row["unmapped_fields"])
                flat["quality_flags"] = canonical_json(row["quality_flags"])
                flat["conditions_canonical"] = canonical_json(row["conditions_canonical"])
                for field in CSV_COLUMNS:
                    value = flat.get(field)
                    if value is None:
                        flat[field] = ""
                    elif isinstance(value, bool):
                        flat[field] = "true" if value else "false"
                    elif isinstance(value, (dict, list)):
                        flat[field] = canonical_json(value)
                writer.writerow({field: flat.get(field, "") for field in CSV_COLUMNS})
        with (self.out / "change_log.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for change in self.changes:
                handle.write(canonical_json(json_safe(change)) + "\n")
        write_json(self.out / "review_queue.json", review)
        summary = {
            "source_count": len(self.sources), "table_count": len(self.tables),
            "raw_row_count": sum(len(table["raw_rows"]) for table in self.tables),
            "cleaned_row_count": len(self.cleaned_rows), "excluded_empty_rows": self.excluded_empty,
            "change_record_count": len(self.changes), "anomaly_count": len(self.anomalies),
            "review_item_count": review["item_count"], "duplicate_group_count": getattr(self, "duplicate_group_count", 0),
            "unknown_unit_count": sum("unknown_unit" in row["quality_flags"] for row in self.cleaned_rows),
            "missing_value_count": sum("missing_value" in row["quality_flags"] for row in self.cleaned_rows),
        }
        # Unknown contract keys are nulled only after all meaningful fields are available.
        semantics = self.build_semantics(review, {})
        self.unresolved_contract_fields = []
        contract = contract_names(self.raw_contract)
        if not contract:
            contract = ["case_id", "status", "cleaned_rows", "cleaned_csv", "sources", "uncertainty", "change_records", "artifacts", "anomalies", "review_queue", "audit_report"]
        for key in contract:
            if key not in semantics:
                normalized = key.strip().casefold()
                alias_map = {
                    "records": "cleaned_rows", "rows": "cleaned_rows", "normalized_rows": "cleaned_rows",
                    "results": "cleaned_rows", "result": "cleaned_rows", "output": "cleaned_rows",
                    "source_files": "sources", "input_sources": "sources", "review": "review_queue",
                    "output_files": "artifacts", "report": "audit_report", "notes": "uncertainty",
                }
                if normalized in alias_map:
                    semantics[key] = semantics[alias_map[normalized]]
                else:
                    semantics[key] = None
                    self.unresolved_contract_fields.append(key)
        # Rebuild after unresolved fields are known so uncertainty is accurate.
        artifacts = {
            "cleaned_csv": self.artifact_info("cleaned_rows.csv", "UTF-8 flattened cleaned table; every non-empty input row is retained."),
            "cleaned_rows_json": self.artifact_info("cleaned_rows.json", "Machine-readable cleaned rows with full row provenance."),
            "raw_snapshot": self.artifact_info("raw_snapshot.json", "Lossless raw cells, exact row identities, and input fingerprints."),
            "change_log": self.artifact_info("change_log.jsonl", "Per-cell changes with rule IDs, formulas, and row locators."),
            "review_queue": self.artifact_info("review_queue.json", "Anomalies requiring human adjudication."),
        }
        self.write_audit(summary, review, artifacts)
        artifacts["audit_report"] = self.artifact_info("audit_report.md", "Human-readable deterministic audit summary.")
        semantics = self.build_semantics(review, artifacts)
        result: dict[str, Any] = {
            "schema_version": VERSION, "example_label": SYNTHETIC_LABEL if self.synthetic else "",
            "partial": self.status() in {"partial", "input_error", "error"},
            "summary": summary, "input_integrity": self.input_integrity,
            "input_fingerprint": self.input_fingerprint(), "output_contract": self.raw_contract,
            "unresolved_contract_fields": self.unresolved_contract_fields,
            "errors": self.errors, "synthetic_input": self.synthetic,
            "deterministic_execution": {
                "clock_used": False, "randomness_used": False, "network_used": False,
                "ordering": "Discovery order is stable; directory entries are sorted; JSON keys are sorted.",
            },
        }
        # Core fields are always present; requested fields retain their exact top-level spelling.
        for key, value in semantics.items():
            if key in {"case_id", "status", "sources", "uncertainty", "change_records", "artifacts", "anomalies", "review_queue", "errors", "partial", "unresolved_contract_fields", "input_fingerprint"}:
                result[key] = value
        for key in contract:
            result[key] = semantics.get(key)
        write_json(self.out / "result.json", json_safe(result))
        return result

    def write_audit(self, summary: dict[str, Any], review: dict[str, Any], artifacts: dict[str, Any]) -> None:
        label = "# SYNTHETIC Lineage Guardian Audit — NOT AN OFFICIAL ANSWER" if self.synthetic else "# Lineage Guardian Audit Report"
        lines = [label, "", f"- case_id: `{self.case_id}`", f"- status: **{self.status()}**", f"- schema_version: `{VERSION}`", "", "## Run policy", "", "Raw input is immutable in the raw snapshot. Unknown units stay unconverted; missing values stay null; duplicate candidates are flagged without merging. Original papers were not independently re-read.", "", "## Input integrity and provenance", "", "| source | path | SHA256 | BOM | decode status | replacement chars | raw rows |", "|---|---|---|---:|---|---:|---:|"]
        for source in self.sources:
            lines.append(f"| {source['source_id']} | `{source['path']}` | `{source['sha256']}` | {str(source['utf8_bom']).lower()} | {source['decode_status']} | {source['replacement_character_count']} | {source['raw_row_count']} |")
        lines.extend(["", "## Counts", ""])
        for key, value in summary.items():
            lines.append(f"- {key}: **{value}**")
        lines.extend(["", "## Rule application counts", "", "| rule | count |", "|---|---:|"])
        for rule, count in sorted(Counter(change["rule_id"] for change in self.changes).items()):
            lines.append(f"| {rule} | {count} |")
        lines.extend(["", "## Review hotspots", ""])
        if review["items"]:
            for item in review["items"]:
                lines.append(f"- `{item['review_id']}` **{item['rule_id']}** `{item.get('row_id')}`: {item['message']}")
        else:
            lines.append("No review items were generated.")
        lines.extend(["", "## Output artifacts", "", "| artifact | file | SHA256 |", "|---|---|---|"])
        for key, artifact in artifacts.items():
            lines.append(f"| {key} | `{artifact['file']}` | `{artifact['sha256']}` |")
        lines.extend(["", "## Unresolved output-contract fields", ""])
        if self.unresolved_contract_fields:
            for key in self.unresolved_contract_fields:
                lines.append(f"- `{key}` = null (no safe semantic mapping; not fabricated)")
        else:
            lines.append("None.")
        lines.extend(["", "## Reproduction and limits", "", "Run with Python 3.10+ standard library only. No clock, random seed, network, locale-dependent sort, or external package affects output. Audit paths describe this run's inputs; artifacts use relative filenames. Ranging preserves endpoints, not midpoints. A successful status means processing completed, not that review items are scientifically resolved.", ""])
        (self.out / "audit_report.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")

    def run(self) -> dict[str, Any]:
        self.out.mkdir(parents=True, exist_ok=True)
        self.work.mkdir(parents=True, exist_ok=True)
        # This write precedes case parsing and is deliberately an honest partial.
        self.save_partial("intake_initialization")
        try:
            self.discover_materials()
            self.save_partial("material_discovery_complete", "input_error" if self.had_input_error and not self.tables else "partial")
            self.process_rows()
            self.save_partial("normalization_complete", "input_error" if not self.cleaned_rows and self.had_input_error else "partial")
            return self.write_outputs()
        except Exception as exc:  # last-resort honest failure, with all already known contract keys.
            self.record_error("UNEXPECTED_ERROR", f"{type(exc).__name__}: {exc}")
            self.add_anomaly("R-ERR-001", "runtime_error", "error", "Run stopped unexpectedly; inspect result.json errors and partial outputs.", review=True)
            partial = self.minimal_result("input_error" if not self.cleaned_rows else "partial")
            partial["stage"] = "failed"
            partial["traceback"] = traceback.format_exc()
            if self.raw_contract is not None:
                for key in contract_names(self.raw_contract):
                    if key in {"status", "sources", "uncertainty", "change_records", "artifacts", "case_id", "anomalies", "errors"}:
                        continue
                    partial.setdefault(key, None)
                    if key not in {"cleaned_rows", "cleaned_csv", "review_queue", "audit_report", "raw_snapshot"}:
                        self.unresolved_contract_fields.append(key)
            partial["unresolved_contract_fields"] = self.unresolved_contract_fields
            write_json(self.out / "result.json", json_safe(partial))
            raise


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean extracted literature tables while preserving byte, row, and rule lineage.")
    parser.add_argument("--case", default="/input/case.json", help="Case JSON path (default: /input/case.json)")
    parser.add_argument("--task", default="/input/task.md", help="Task Markdown path (default: /input/task.md)")
    parser.add_argument("--work", default="/app/work", help="Scratch directory (default: /app/work)")
    parser.add_argument("--out", default="/app/output", help="Output directory (default: /app/output)")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    guardian = LineageGuardian(parse_args(argv))
    result = guardian.run()
    return 1 if result.get("status") == "input_error" else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"lineage_guardian: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(2)
