#!/usr/bin/env python3
"""Raw-data ingestion, row provenance, replicate-aware statistics and transforms."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


class DataError(ValueError):
    """Invalid data/specification; callers must return non-zero."""


DERIVED_FIELDS = [
    "source_sha256", "source_row", "row_checksum", "feature", "sample", "group", "replicate",
    "raw_value", "transformed_value", "sample_mean", "group_mean", "group_sd", "group_sem",
    "group_n", "log2FC", "p_value", "neg_log10_p", "fill", "size",
]
GROUP_FIELDS = [
    "feature", "group", "n_samples", "sample_ids", "group_mean", "group_sd",
    "group_sem", "log2FC", "p_value", "neg_log10_p", "fill",
]


def strict_json(path):
    def bad_constant(value):
        raise DataError(f"non-finite JSON number {value} in {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"), parse_constant=bad_constant)
    except DataError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DataError(f"cannot read JSON {path}: {exc}") from exc


def sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical_row(raw):
    return json.dumps(raw, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def load_spec(path):
    spec = strict_json(path)
    if not isinstance(spec, dict):
        raise DataError("data spec must be an object")
    allowed = {"path", "format", "columns", "filters", "transforms"}
    unknown = set(spec) - allowed
    if unknown:
        raise DataError(f"data spec may only contain path/format/columns/filters/transforms; offending: {sorted(unknown)}")
    if not isinstance(spec.get("path"), str) or not spec["path"]:
        raise DataError("data spec.path is required and must identify raw data, not derived values")
    columns = spec.get("columns")
    if not isinstance(columns, dict):
        raise DataError("data spec.columns must map logical fields to raw column names")
    for required in ("sample", "group", "value"):
        if not isinstance(columns.get(required), str) or not columns[required]:
            raise DataError(f"data spec.columns.{required} is required")
    allowed_columns = {"sample", "group", "value", "feature", "replicate", "p"}
    if set(columns) - allowed_columns:
        raise DataError(f"unsupported logical columns: {sorted(set(columns) - allowed_columns)}")
    if not isinstance(spec.get("filters", []), list) or not isinstance(spec.get("transforms", {}), dict):
        raise DataError("filters must be an array and transforms must be an object")
    if set(spec.get("transforms", {})) - {"value", "log2FC", "neg_log10_p"}:
        raise DataError("transforms only supports value, log2FC and neg_log10_p")
    return spec


def load_raw(path, fmt=None):
    try:
        raw_bytes = path.read_bytes()
        text = raw_bytes.decode("utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise DataError(f"cannot read raw UTF-8 dataset {path}: {exc}") from exc
    fmt = fmt or path.suffix.lower().lstrip(".")
    common_sha = sha256_bytes(raw_bytes)
    rows = []
    if fmt in {"csv", "tsv"}:
        delimiter = "," if fmt == "csv" else "\t"
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        headers = reader.fieldnames
        if not headers or any(h is None or h == "" for h in headers) or len(headers) != len(set(headers)):
            raise DataError("raw delimited data must have unique, non-empty column names")
        for row_number, row in enumerate(reader, start=2):
            if None in row:
                raise DataError(f"row {row_number} has more fields than the header")
            rows.append({"_source_row": row_number, "_raw": row})
    elif fmt == "json":
        try:
            value = json.loads(text, parse_constant=lambda x: (_ for _ in ()).throw(DataError(f"non-finite raw JSON value {x}")))
        except DataError:
            raise
        except json.JSONDecodeError as exc:
            raise DataError(f"invalid raw JSON: {exc}") from exc
        if isinstance(value, dict):
            value = value.get("rows")
        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            raise DataError("raw JSON must be an array of objects or {rows:[...]} ")
        headers = sorted({key for row in value for key in row})
        for row_number, row in enumerate(value, start=1):
            rows.append({"_source_row": row_number, "_raw": row})
    else:
        raise DataError(f"unsupported raw data format {fmt!r}; use csv, tsv or json")
    if not rows:
        raise DataError("raw dataset has no observations")
    for row in rows:
        row["_source_sha256"] = common_sha
        row["_row_checksum"] = sha256_bytes(canonical_row(row["_raw"]).encode("utf-8"))
    return rows, headers


def _raw_column(spec, logical):
    columns = spec["columns"]
    if logical not in columns:
        return None
    return columns[logical]


def _cell(row, column):
    return row["_raw"].get(column)


def apply_filters(rows, spec):
    filters = spec.get("filters", [])
    kept, excluded = [], []
    for row in rows:
        reasons = []
        for rule in filters:
            if not isinstance(rule, dict) or set(rule) - {"column", "operator", "value"}:
                raise DataError("each filter only supports column/operator/value")
            column, operator = rule.get("column"), rule.get("operator", "eq")
            if not isinstance(column, str):
                raise DataError("filter.column must be a raw column name")
            value = _cell(row, column)
            if value is None or value == "":
                match = operator == "not_null" and False
            elif operator == "not_null":
                match = True
            elif operator in {"eq", "ne", "in"}:
                expected = rule.get("value")
                if operator == "in":
                    match = isinstance(expected, list) and value in expected
                else:
                    match = value == expected if operator == "eq" else value != expected
            elif operator in {"gt", "ge", "lt", "le"}:
                try:
                    observed, expected = finite_number(value, f"filter {column}"), finite_number(rule.get("value"), f"filter expected {column}")
                except DataError:
                    match = False
                else:
                    match = {"gt": observed > expected, "ge": observed >= expected, "lt": observed < expected, "le": observed <= expected}[operator]
            else:
                raise DataError(f"unsupported filter operator {operator!r}")
            if not match:
                reasons.append({"column": column, "operator": operator, "expected": rule.get("value")})
        (kept if not reasons else excluded).append(row if not reasons else {**row, "_exclusion_reasons": reasons})
    if not kept:
        raise DataError("all rows were removed by filters")
    return kept, excluded


def finite_number(value, label):
    if value is None or isinstance(value, bool) or (isinstance(value, str) and not value.strip()):
        raise DataError(f"{label} is missing/non-numeric: {value!r}")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DataError(f"{label} is not numeric: {value!r}") from exc
    if not math.isfinite(number):
        raise DataError(f"{label} must be finite: {value!r}")
    return number


def _one_transform(value, config, label):
    if not isinstance(config, dict) or set(config) - {"operation", "pseudocount", "factor", "offset"}:
        raise DataError(f"invalid value transform at {label}")
    operation = config.get("operation")
    if operation in {"log2", "log10", "ln"}:
        offset = finite_number(config.get("pseudocount", 0), f"{label}.pseudocount")
        if value + offset <= 0:
            raise DataError(f"{label} logarithm needs value + pseudocount > 0, got {value + offset}")
        return {"log2": math.log2, "log10": math.log10, "ln": math.log}[operation](value + offset)
    if operation == "scale":
        return value * finite_number(config.get("factor"), f"{label}.factor")
    if operation == "offset":
        return value + finite_number(config.get("offset"), f"{label}.offset")
    if operation == "abs":
        return abs(value)
    raise DataError(f"unsupported value transform operation {operation!r}")


def transform_value(value, config, label):
    operations = config if isinstance(config, list) else [config]
    for item in operations:
        value = _one_transform(value, item, label)
    if not math.isfinite(value):
        raise DataError(f"{label} produced a non-finite value")
    return value


def _constant_feature_value(rows, column, feature, label):
    values = [finite_number(_cell(row, column), f"{label} feature {feature} row {row['_source_row']}") for row in rows]
    if not values:
        raise DataError(f"feature {feature} has no {label}")
    if any(abs(value - values[0]) > 1e-12 * max(1, abs(values[0])) for value in values[1:]):
        raise DataError(f"feature {feature} has ambiguous non-constant {label}; precompute an unambiguous feature statistic")
    return values[0]


def analyze(rows, spec):
    """Return observation, independent-sample, group and feature tables.

    A sample is a unique configured sample id within (feature, group). Repeated rows
    are first averaged within sample; n/SD/SEM use only those sample means.
    """
    columns = spec["columns"]
    observations = []
    by_sample = defaultdict(list)
    by_feature = defaultdict(list)
    for row in rows:
        feature_value = _cell(row, columns["feature"]) if "feature" in columns else "ALL"
        sample, group = _cell(row, columns["sample"]), _cell(row, columns["group"])
        if feature_value is None or sample is None or group is None or not all(str(x).strip() for x in (feature_value, sample, group)):
            raise DataError(f"row {row['_source_row']} has missing feature/sample/group")
        feature, sample, group = str(feature_value), str(sample), str(group)
        raw = finite_number(_cell(row, columns["value"]), f"value at raw row {row['_source_row']}")
        value = transform_value(raw, spec["transforms"]["value"], f"value at raw row {row['_source_row']}") if "value" in spec["transforms"] else raw
        replicate = str(_cell(row, columns["replicate"])) if "replicate" in columns else ""
        obs = {
            "source_sha256": row["_source_sha256"], "source_row": row["_source_row"],
            "row_checksum": row["_row_checksum"], "feature": feature, "sample": sample,
            "group": group, "replicate": replicate, "raw_value": raw, "transformed_value": value,
        }
        observations.append(obs)
        by_sample[(feature, group, sample)].append(obs)
        by_feature[feature].append(row)
    samples = []
    for (feature, group, sample), members in sorted(by_sample.items()):
        values = [member["transformed_value"] for member in members]
        samples.append({
            "feature": feature, "group": group, "sample": sample, "sample_mean": statistics.fmean(values),
            "within_sample_replicates": len(members),
            "source_rows": [member["source_row"] for member in members],
        })
    by_group = defaultdict(list)
    for sample in samples:
        by_group[(sample["feature"], sample["group"])].append(sample)
    groups = {}
    for (feature, group), members in sorted(by_group.items()):
        values = [member["sample_mean"] for member in members]
        n = len(values)
        mean = statistics.fmean(values)
        sd = statistics.stdev(values) if n >= 2 else None
        sem = sd / math.sqrt(n) if sd is not None else None
        summary = {
            "feature": feature, "group": group, "n_samples": n,
            "sample_ids": [member["sample"] for member in members], "sample_mean": None,
            "group_mean": mean, "group_sd": sd, "group_sem": sem,
            "log2FC": None, "p_value": None, "neg_log10_p": None,
        }
        groups[(feature, group)] = summary
    for sample in samples:
        summary = groups[(sample["feature"], sample["group"])]
        for field in ("n_samples", "group_mean", "group_sd", "group_sem"):
            sample[field] = summary[field]
    features = {}
    ratio_config = spec["transforms"].get("log2FC")
    p_config = spec["transforms"].get("neg_log10_p")
    for feature, raw_rows in sorted(by_feature.items()):
        log2fc = None
        if ratio_config:
            if not isinstance(ratio_config, dict):
                raise DataError("transforms.log2FC must be an object")
            operation = ratio_config.get("operation")
            if operation == "column":
                if set(ratio_config) - {"operation", "column"} or not isinstance(ratio_config.get("column"), str):
                    raise DataError("log2FC column transform only supports operation/column")
                log2fc = _constant_feature_value(raw_rows, ratio_config["column"], feature, "log2FC")
            elif operation == "mean_ratio":
                allowed = {"operation", "numerator_group", "denominator_group", "pseudocount"}
                if set(ratio_config) - allowed:
                    raise DataError("mean_ratio transform contains unsupported options")
                numerator, denominator = ratio_config.get("numerator_group"), ratio_config.get("denominator_group")
                if (feature, numerator) not in groups or (feature, denominator) not in groups:
                    raise DataError(f"feature {feature} lacks numerator/denominator group for mean_ratio")
                pseudo = finite_number(ratio_config.get("pseudocount", 0), "log2FC.pseudocount")
                top = groups[(feature, numerator)]["group_mean"] + pseudo
                bottom = groups[(feature, denominator)]["group_mean"] + pseudo
                if top <= 0 or bottom <= 0:
                    raise DataError(f"feature {feature} mean_ratio requires positive adjusted means")
                log2fc = math.log2(top / bottom)
            else:
                raise DataError("log2FC operation must be column or mean_ratio")
        p_value, neg_log10_p, clamped = None, None, False
        if p_config:
            if not isinstance(p_config, dict) or set(p_config) - {"operation", "column", "floor"} or p_config.get("operation") != "neg_log10" or not isinstance(p_config.get("column"), str):
                raise DataError("neg_log10_p requires operation=neg_log10, column and optional floor")
            p_value = _constant_feature_value(raw_rows, p_config["column"], feature, "p value")
            floor = finite_number(p_config.get("floor", 1e-300), "p floor")
            if floor <= 0 or p_value < 0 or p_value > 1:
                raise DataError(f"feature {feature} p value/floor outside legal range")
            if p_value == 0:
                p_value_for_log = floor
                clamped = True
            else:
                p_value_for_log = p_value
            neg_log10_p = -math.log10(p_value_for_log)
        features[feature] = {"feature": feature, "log2FC": log2fc, "p_value": p_value, "neg_log10_p": neg_log10_p, "p_zero_clamped": clamped}
        for (f, _group), summary in groups.items():
            if f == feature:
                summary.update({"log2FC": log2fc, "p_value": p_value, "neg_log10_p": neg_log10_p})
    for sample in samples:
        sample.update(features[sample["feature"]])
        sample["abs_log2FC"] = abs(sample["log2FC"]) if sample["log2FC"] is not None else None
    for summary in groups.values():
        summary["abs_log2FC"] = abs(summary["log2FC"]) if summary["log2FC"] is not None else None
    for obs in observations:
        key = (obs["feature"], obs["group"], obs["sample"])
        matches = [s for s in samples if (s["feature"], s["group"], s["sample"]) == key]
        if len(matches) != 1:
            raise DataError(f"internal sample identity error for {key}")
        sample = matches[0]
        obs.update({key: sample.get(key) for key in ("sample_mean", "group_mean", "group_sd", "group_sem")})
        obs["group_n"] = groups[(obs["feature"], obs["group"])]["n_samples"]
        obs.update({key: features[obs["feature"]][key] for key in ("log2FC", "p_value", "neg_log10_p")})
        obs["abs_log2FC"] = abs(obs["log2FC"]) if obs["log2FC"] is not None else None
    # Independent numerical audit of the sample definition and every group statistic.
    for (feature, group), summary in groups.items():
        selected = [s["sample_mean"] for s in samples if s["feature"] == feature and s["group"] == group]
        assert len(selected) == summary["n_samples"]
        if not math.isclose(statistics.fmean(selected), summary["group_mean"], rel_tol=1e-12, abs_tol=1e-12):
            raise DataError("internal group mean verification failed")
        if len(selected) >= 2 and not math.isclose(statistics.stdev(selected), summary["group_sd"], rel_tol=1e-12, abs_tol=1e-12):
            raise DataError("internal group SD verification failed")
    return observations, samples, list(groups.values()), list(features.values())


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row.get(key) is None else row.get(key) for key in fields})
