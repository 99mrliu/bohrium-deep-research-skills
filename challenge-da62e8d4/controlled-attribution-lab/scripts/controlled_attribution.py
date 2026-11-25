#!/usr/bin/env python3
"""Execute hash-bound, single-factor numerical intervention plans.

The program distinguishes plan validity and execution completeness from the
scientific verdict. It never promotes an observed association to a unique root
cause. No shell is used and candidate commands are never stopped early because
another candidate failed.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import statistics
import subprocess
import sys
import time
from typing import Any


SCHEMA_VERSION = 1
LEGAL_FACTORS = {"implementation", "parameter", "data", "environment", "seed"}
DIRECTIONS = {"increase", "decrease", "unresolved"}
RESULT_STATUSES = {"success", "partial", "unable", "refused"}
EXECUTION_STATUSES = {"complete", "partial", "rejected"}
RUN_ID = re.compile(r"^[A-Za-z0-9_.-]+$")
HASH = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_ARTIFACT_CONTRACT = {
    "runs": "runs/index.json",
    "intervention_report_json": "intervention_report.json",
    "intervention_report_md": "intervention_report.md",
    "result": "result.json",
}
STANDARD_ARTIFACT_PATHS = set(DEFAULT_ARTIFACT_CONTRACT.values())
STANDARD_ARTIFACT_FIELDS = set(DEFAULT_ARTIFACT_CONTRACT)
STANDARD_RESULT_FIELDS = {
    "case_id",
    "status",
    "execution_status",
    "sources",
    "uncertainty",
    "change_records",
    "artifacts",
    "plan_sha256",
    "plan_hash_verified",
    "execution_command_count",
    "all_runs_succeeded",
    "conclusion_counts",
    "validation_errors",
    "attribution_scope",
    "case_output_contract_fields",
    "missing_artifact_contract_artifacts",
    "missing_contract_answer_fields",
    "evidence_delivery_complete",
}
DYNAMIC_ANSWER_FIELDS = {
    "reproduction_summary",
    "candidate_comparison",
    "attribution_summary",
    "intervention_summary",
    "scientific_conclusions",
    "difference_attribution",
    "noise_floor_analysis",
}
PLACEHOLDERS = {"", "n/a", "na", "none", "null", "unknown", "todo", "tbd", "未知", "待定"}
PATH_SUFFIXES = {
    ".json", ".jsonl", ".md", ".txt", ".csv", ".tsv", ".pdf", ".png",
    ".jpg", ".jpeg", ".svg", ".py", ".log", ".html",
}
SCOPE = "attributable only within tested conditions"


def missing_artifacts(output_dir: Path, contract: dict[str, str]) -> list[str]:
    """Only custom artifacts require command-side creation; core files are ours."""
    return sorted(
        artifact
        for artifact in set(contract.values()) - STANDARD_ARTIFACT_PATHS
        if not (output_dir / artifact).is_file()
    )


class PlanError(ValueError):
    """A preflight error that must prevent all candidate execution."""


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, value: Any) -> None:
    write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def canonical_plan(plan: dict[str, Any]) -> bytes:
    """Return the exact bytes whose hash pre-registers the whole plan."""
    unhashed = copy.deepcopy(plan)
    unhashed.get("registration", {}).pop("plan_sha256", None)
    return json.dumps(
        unhashed,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def plan_digest(plan: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_plan(plan)).hexdigest()


def load_plan(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PlanError(f"cannot load UTF-8 JSON plan: {exc}") from exc
    if not isinstance(value, dict):
        raise PlanError("plan root must be an object")
    return value


def require_object(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise PlanError(f"{key} must be an object")
    return value


def require_list(parent: dict[str, Any], key: str) -> list[Any]:
    value = parent.get(key)
    if not isinstance(value, list):
        raise PlanError(f"{key} must be an array")
    return value


def nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlanError(f"{label} must be a non-empty string")
    return value


def safe_artifact(value: Any, label: str) -> str:
    text = nonempty_string(value, label)
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts or text == ".":
        raise PlanError(f"{label} must be a safe relative artifact path")
    return text


def resolve_cwd(plan_path: Path, text: Any) -> Path:
    relative = nonempty_string(text, "run.cwd")
    candidate = Path(relative)
    if not candidate.is_absolute():
        candidate = plan_path.parent / candidate
    candidate = candidate.resolve()
    if not candidate.is_dir():
        raise PlanError(f"run cwd is not a directory: {candidate}")
    return candidate


def resolve_declared_path(cwd: Path, text: Any, label: str) -> Path:
    relative = nonempty_string(text, label)
    path = Path(relative)
    return path if path.is_absolute() else cwd / path


def validate_artifact_contract(plan: dict[str, Any]) -> dict[str, str]:
    """Read output locations, never confusing them with case answer fields.

    artifact_contract is canonical. The old plan.output_contract path mapping is
    accepted only as an explicitly documented legacy alias; case.output_contract
    is independently loaded from case_file and never handled here.
    """
    if "artifact_contract" in plan and "output_contract" in plan:
        raise PlanError(
            "use plan.artifact_contract for paths; legacy plan.output_contract "
            "cannot be combined with it"
        )
    raw = plan.get(
        "artifact_contract",
        plan.get("output_contract", DEFAULT_ARTIFACT_CONTRACT),
    )
    if not isinstance(raw, dict) or not raw:
        raise PlanError("artifact_contract must be a non-empty object")
    contract = dict(DEFAULT_ARTIFACT_CONTRACT)
    for key, value in raw.items():
        nonempty_string(key, "artifact_contract key")
        contract[key] = safe_artifact(value, f"artifact_contract.{key}")
    return contract


def parse_contract_field_list(items: Any, label: str) -> list[str]:
    if isinstance(items, dict):
        fields = []
        for name, spec in items.items():
            nonempty_string(name, f"{label} key")
            if isinstance(spec, dict) and spec.get("required") is False:
                continue
            fields.append(name.strip())
        return fields
    if not isinstance(items, list):
        raise PlanError(f"{label} must be an array or field mapping")
    fields = []
    for item in items:
        if isinstance(item, str):
            name = item
        elif isinstance(item, dict):
            if item.get("required") is False:
                continue
            name = next(
                (item[key] for key in ("name", "field", "key", "id") if key in item),
                None,
            )
        else:
            name = None
        nonempty_string(name, f"{label} entry")
        fields.append(name.strip())
    return fields


def extract_contract_fields(contract: Any) -> list[str]:
    """Extract required top-level answers from all supported case shapes."""
    if isinstance(contract, list):
        fields = parse_contract_field_list(contract, "case.output_contract")
    elif isinstance(contract, dict):
        if "properties" in contract:
            properties = contract["properties"]
            if not isinstance(properties, dict):
                raise PlanError("case JSON Schema properties must be an object")
            fields = list(properties)
            if "required" in contract:
                required = parse_contract_field_list(
                    contract["required"], "case JSON Schema required"
                )
                fields = [name for name in fields if name in required]
                fields += [name for name in required if name not in fields]
        elif "fields" in contract or "required_fields" in contract:
            fields = []
            for wrapper in ("fields", "required_fields"):
                if wrapper in contract:
                    for name in parse_contract_field_list(
                        contract[wrapper], f"case.output_contract.{wrapper}"
                    ):
                        if name not in fields:
                            fields.append(name)
        elif "required" in contract:
            fields = parse_contract_field_list(
                contract["required"], "case.output_contract.required"
            )
        else:
            # Direct mapping: every key declares an answer unless optional.
            fields = parse_contract_field_list(contract, "case.output_contract")
    else:
        raise PlanError(
            "case.output_contract must be a list, mapping, fields/required_fields "
            "object, or JSON Schema object"
        )
    if not fields:
        raise PlanError("case.output_contract declares no required fields")
    if any(not isinstance(name, str) or not name.strip() for name in fields):
        raise PlanError("case.output_contract field names must be non-empty strings")
    duplicates = sorted({name for name in fields if fields.count(name) > 1})
    if duplicates:
        raise PlanError(f"duplicate case.output_contract fields: {duplicates}")
    # Standard result fields and standard artifact names are valid declarations.
    # They are supplied by the executor rather than blocked as reserved keys.
    return fields


def resolve_case_file(plan_path: Path, plan: dict[str, Any]) -> Path:
    raw = nonempty_string(plan.get("case_file"), "case_file")
    path = Path(raw)
    return (path if path.is_absolute() else plan_path.parent / path).resolve()


def load_case(plan_path: Path, plan: dict[str, Any]) -> tuple[dict[str, Any], Path, list[str]]:
    case_path = resolve_case_file(plan_path, plan)
    try:
        case = json.loads(case_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PlanError(f"cannot load real case.json {case_path}: {exc}") from exc
    if not isinstance(case, dict):
        raise PlanError("case.json root must be an object")
    nonempty_string(case.get("case_id"), "case.json case_id")
    if "output_contract" not in case:
        raise PlanError("case.json must contain output_contract answer fields")
    fields = extract_contract_fields(case["output_contract"])
    return case, case_path, fields


def looks_like_artifact_only(value: str) -> bool:
    text = value.strip()
    path = PurePosixPath(text)
    return (
        path.suffix.lower() in PATH_SUFFIXES
        and not any(character.isspace() for character in text)
    )


def substantive(value: Any, root: bool = True) -> bool:
    """Reject empty answers and answers consisting only of an artifact path."""
    if value is None:
        return False
    if isinstance(value, str):
        text = value.strip()
        return text.lower() not in PLACEHOLDERS and not (
            root and looks_like_artifact_only(text)
        )
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    if isinstance(value, list):
        if not value or all(
            isinstance(item, str) and looks_like_artifact_only(item) for item in value
        ):
            return False
        return all(substantive(item, False) for item in value)
    if isinstance(value, dict):
        if not value:
            return False
        # A nested source path alongside a real statement is useful evidence;
        # a dict that merely wraps path keys is still not a substantive answer.
        if set(value) <= {"path", "file", "artifact", "artifact_path"}:
            return False
        return all(substantive(item, False) for item in value.values())
    return False


def unavailable(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("unavailable"), dict)


def validate_unavailable(field: str, value: dict[str, Any]) -> None:
    detail = value["unavailable"]
    nonempty_string(detail.get("reason"), f"contract_values.{field}.unavailable.reason")
    if not detail.get("missing") and not detail.get("next_steps"):
        raise PlanError(
            f"contract_values.{field}.unavailable needs missing and/or next_steps"
        )
    for key in ("missing", "next_steps", "evidence"):
        if key in detail:
            item = detail[key]
            if isinstance(item, list):
                if not item:
                    raise PlanError(f"contract_values.{field}.{key} must not be empty")
            elif not nonempty_string(item, f"contract_values.{field}.{key}"):
                raise PlanError(f"contract_values.{field}.{key} must be a list or string")


def validate_contract_values(
    plan: dict[str, Any], fields: list[str]
) -> dict[str, Any]:
    raw = plan.get("contract_values", {})
    if not isinstance(raw, dict):
        raise PlanError("contract_values must be an object")
    unknown = sorted(set(raw) - set(fields))
    if unknown:
        raise PlanError(f"contract_values contains fields absent from case contract: {unknown}")
    automatic = sorted(set(raw) & (STANDARD_RESULT_FIELDS | STANDARD_ARTIFACT_FIELDS))
    if automatic:
        raise PlanError(f"contract_values cannot override executor fields: {automatic}")
    for field, value in raw.items():
        if unavailable(value):
            validate_unavailable(field, value)
            continue
        answer = value.get("value") if isinstance(value, dict) and "value" in value else value
        if not substantive(answer):
            raise PlanError(
                f"contract_values.{field} must be substantive evidence, structured "
                "unavailable, and never only an artifact path"
            )
        if isinstance(value, dict) and "value" in value:
            if not value.get("evidence"):
                raise PlanError(
                    f"contract_values.{field} value wrapper needs non-empty evidence"
                )
    return raw


def validate_hash(plan: dict[str, Any]) -> str:
    registration = require_object(plan, "registration")
    claimed = registration.get("plan_sha256")
    if not isinstance(claimed, str) or not HASH.fullmatch(claimed):
        raise PlanError("registration.plan_sha256 must be 64 lowercase hex digits")
    actual = plan_digest(plan)
    if claimed != actual:
        raise PlanError(
            f"pre-registration SHA256 mismatch: claimed={claimed} actual={actual}; "
            "refusing to execute a plan changed after registration"
        )
    return actual


def validate_plan(
    plan: dict[str, Any],
    plan_path: Path,
    case: dict[str, Any],
    contract_fields: list[str],
    artifact_contract: dict[str, str],
) -> dict[str, Any]:
    """Validate every run before starting the first subprocess."""
    if plan.get("schema_version") != SCHEMA_VERSION:
        raise PlanError("schema_version must be 1")
    plan_case_id = nonempty_string(plan.get("case_id"), "case_id")
    if plan_case_id != case["case_id"]:
        raise PlanError(
            f"plan.case_id must equal real case.json case_id: {case['case_id']}"
        )
    nonempty_string(plan.get("question"), "question")
    contract_values = validate_contract_values(plan, contract_fields)

    metric = require_object(plan, "metric")
    metric_key = nonempty_string(metric.get("key"), "metric.key")
    epsilon = metric.get("noise_epsilon")
    if isinstance(epsilon, bool) or not isinstance(epsilon, (int, float)):
        raise PlanError("metric.noise_epsilon must be numeric")
    if not math.isfinite(epsilon) or epsilon < 0:
        raise PlanError("metric.noise_epsilon must be finite and non-negative")

    hypotheses_raw = require_list(plan, "hypotheses")
    hypotheses: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(hypotheses_raw):
        if not isinstance(raw, dict):
            raise PlanError(f"hypotheses[{index}] must be an object")
        hid = nonempty_string(raw.get("hypothesis_id"), "hypothesis_id")
        if hid in hypotheses:
            raise PlanError(f"duplicate hypothesis_id: {hid}")
        nonempty_string(raw.get("statement"), f"{hid}.statement")
        if raw.get("direction") not in DIRECTIONS:
            raise PlanError(f"{hid}.direction must be increase/decrease/unresolved")
        signatures = raw.get("predicted_signatures")
        if not isinstance(signatures, list) or not signatures:
            raise PlanError(f"{hid}.predicted_signatures must be non-empty")
        for signature in signatures:
            nonempty_string(signature, f"{hid}.predicted_signatures item")
        nonempty_string(raw.get("falsification"), f"{hid}.falsification")
        hypotheses[hid] = raw

    runs_raw = require_list(plan, "runs")
    if not runs_raw:
        raise PlanError("runs must not be empty")
    runs: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(runs_raw):
        if not isinstance(raw, dict):
            raise PlanError(f"runs[{index}] must be an object")
        rid = nonempty_string(raw.get("run_id"), "run_id")
        if not RUN_ID.fullmatch(rid):
            raise PlanError(f"unsafe run_id: {rid}")
        if rid in runs:
            raise PlanError(f"duplicate run_id: {rid}")
        nonempty_string(raw.get("candidate"), f"{rid}.candidate")
        if raw.get("role") not in {"baseline", "variant"}:
            raise PlanError(f"{rid}.role must be baseline or variant")
        argv = raw.get("argv")
        if not isinstance(argv, list) or not argv:
            raise PlanError(f"{rid}.argv must be a non-empty array")
        for argument in argv:
            if not isinstance(argument, str):
                raise PlanError(f"{rid}.argv entries must be strings")
        cwd = resolve_cwd(plan_path, raw.get("cwd"))
        env = raw.get("env")
        if not isinstance(env, dict):
            raise PlanError(f"{rid}.env must be an object")
        for key, value in env.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise PlanError(f"{rid}.env keys and values must be strings")
        timeout = raw.get("timeout_seconds")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise PlanError(f"{rid}.timeout_seconds must be finite and positive")
        inputs = raw.get("inputs")
        outputs = raw.get("outputs")
        if not isinstance(inputs, list) or not isinstance(outputs, list):
            raise PlanError(f"{rid} inputs and outputs must be explicit arrays")
        for item in inputs:
            input_path = resolve_declared_path(cwd, item, f"{rid}.inputs item")
            if not input_path.is_file():
                raise PlanError(f"declared input does not exist: {input_path}")
        for item in outputs:
            resolve_declared_path(cwd, item, f"{rid}.outputs item")
        runs[rid] = raw

    variants_raw = require_list(plan, "variants")
    if not variants_raw:
        raise PlanError("variants must not be empty")
    variants: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(variants_raw):
        if not isinstance(raw, dict):
            raise PlanError(f"variants[{index}] must be an object")
        vid = nonempty_string(raw.get("variant_id"), "variant_id")
        if vid in variants:
            raise PlanError(f"duplicate variant_id: {vid}")
        hid = nonempty_string(raw.get("hypothesis_id"), f"{vid}.hypothesis_id")
        if hid not in hypotheses:
            raise PlanError(f"{vid} references unknown hypothesis: {hid}")
        factor = raw.get("factor")
        if factor not in LEGAL_FACTORS:
            allowed = ",".join(sorted(LEGAL_FACTORS))
            raise PlanError(f"{vid}.factor must be one of {allowed}")
        changed = raw.get("changed_paths")
        if not isinstance(changed, list) or len(changed) != 1:
            raise PlanError(
                f"{vid} confounded/invalid: changed_paths must contain exactly one item"
            )
        if any(not isinstance(item, str) or not item for item in changed):
            raise PlanError(f"{vid}.changed_paths item must be a non-empty string")
        if len(set(changed)) != 1:
            raise PlanError(
                f"{vid} confounded/invalid: repeated declarations are not scientific factors"
            )
        if not changed[0].startswith(factor + "."):
            raise PlanError(f"{vid}.changed_paths must start with {factor}.")
        baseline_ids = raw.get("baseline_run_ids")
        run_ids = raw.get("run_ids")
        if not isinstance(baseline_ids, list) or len(baseline_ids) < 2:
            raise PlanError(f"{vid} needs at least two baseline_run_ids")
        if not isinstance(run_ids, list) or not run_ids:
            raise PlanError(f"{vid} needs at least one variant run_id")
        if len(set(baseline_ids)) != len(baseline_ids) or len(set(run_ids)) != len(run_ids):
            raise PlanError(f"{vid} has repeated run references")
        if set(baseline_ids) & set(run_ids):
            raise PlanError(f"{vid} baseline and variant runs overlap")
        try:
            baselines = [runs[rid] for rid in baseline_ids]
            interventions = [runs[rid] for rid in run_ids]
        except KeyError as exc:
            raise PlanError(f"{vid} references unknown run_id: {exc.args[0]}") from exc
        if any(run["role"] != "baseline" for run in baselines):
            raise PlanError(f"{vid} baseline_run_ids include a non-baseline run")
        if any(run["role"] != "variant" for run in interventions):
            raise PlanError(f"{vid} run_ids include a non-variant run")
        candidates = {run["candidate"] for run in baselines + interventions}
        if len(candidates) != 1:
            raise PlanError(f"{vid} baseline and variant candidates differ")
        variants[vid] = raw

    sources = plan.get("sources")
    if not isinstance(sources, list):
        raise PlanError("sources must be an array")
    for source in sources:
        if not isinstance(source, dict):
            raise PlanError("each source must be an object")
        nonempty_string(source.get("path"), "source.path")
        nonempty_string(source.get("role"), "source.role")
    notes = plan.get("provenance_notes")
    if not isinstance(notes, list) or any(not isinstance(item, str) for item in notes):
        raise PlanError("provenance_notes must be an array of strings")

    return {
        "artifact_contract": artifact_contract,
        "contract_values": contract_values,
        "metric_key": metric_key,
        "noise_epsilon": float(epsilon),
        "hypotheses": hypotheses,
        "runs": runs,
        "variants": variants,
    }


def subprocess_environment(overrides: dict[str, str]) -> dict[str, str]:
    """Use a minimal, auditable environment instead of exporting credentials."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    env.update(overrides)
    return env


def as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def parse_metric(stdout: str, key: str) -> tuple[Any, str | None, Any]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        return None, "stdout has no non-empty JSON line", None
    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        return None, f"last stdout line is not JSON: {exc}", None
    if not isinstance(payload, dict):
        return None, "last stdout JSON value is not an object", payload
    if key not in payload:
        return None, f"metric key is absent: {key}", payload
    value = payload[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, f"metric {key} is not numeric", payload
    if not math.isfinite(value):
        return None, f"metric {key} is not finite", payload
    return float(value), None, payload


def execute_run(
    raw: dict[str, Any], plan_path: Path, output_dir: Path, metric_key: str
) -> dict[str, Any]:
    rid = raw["run_id"]
    run_dir = output_dir / "runs" / rid
    run_dir.mkdir(parents=True, exist_ok=True)
    cwd = resolve_cwd(plan_path, raw["cwd"])
    env = subprocess_environment(raw["env"])
    record: dict[str, Any] = {
        "run_id": rid,
        "candidate": raw["candidate"],
        "role": raw["role"],
        "argv": raw["argv"],
        "cwd": str(cwd),
        "env": env,
        "timeout_seconds": raw["timeout_seconds"],
        "inputs": raw["inputs"],
        "declared_outputs": raw["outputs"],
        "stdout_path": f"runs/{rid}/stdout.txt",
        "stderr_path": f"runs/{rid}/stderr.txt",
        "record_path": f"runs/{rid}/record.json",
        "started_unix": time.time(),
    }
    started = time.monotonic()
    stdout = ""
    stderr = ""
    returncode: int | None = None
    timed_out = False
    launch_error: str | None = None
    try:
        completed = subprocess.run(
            raw["argv"],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=raw["timeout_seconds"],
            check=False,
            shell=False,
        )
        stdout = completed.stdout
        stderr = completed.stderr
        returncode = completed.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = as_text(exc.stdout)
        stderr = as_text(exc.stderr)
    except OSError as exc:
        launch_error = str(exc)
    record["duration_seconds"] = round(time.monotonic() - started, 6)
    record["exit_code"] = returncode
    record["timed_out"] = timed_out
    record["launch_error"] = launch_error
    write_text(run_dir / "stdout.txt", stdout)
    write_text(run_dir / "stderr.txt", stderr)

    value, metric_error, payload = parse_metric(stdout, metric_key)
    record["metric_key"] = metric_key
    record["metric_value"] = value
    record["metric_error"] = metric_error
    record["json_payload"] = payload
    output_checks = []
    for declared in raw["outputs"]:
        path = resolve_declared_path(cwd, declared, "outputs item")
        output_checks.append({"path": declared, "exists": path.exists()})
    record["output_checks"] = output_checks
    failures = []
    if launch_error:
        failures.append("launch_error")
    if timed_out:
        failures.append("timeout")
    if returncode != 0:
        failures.append("nonzero_exit")
    if metric_error:
        failures.append("metric_error")
    if any(not item["exists"] for item in output_checks):
        failures.append("missing_declared_output")
    record["failures"] = failures
    record["success"] = not failures
    write_json(run_dir / "record.json", record)
    return record


def pairwise_noise(values: list[float], epsilon: float) -> float:
    return epsilon + max(
        (abs(left - right) for left, right in itertools.combinations(values, 2)),
        default=0.0,
    )


def verdict(direction: str, effect: float | None, noise: float | None) -> tuple[str, str]:
    if effect is None or noise is None:
        return "inconclusive", "受控证据未支持确定性归因：有效数值或基线噪声不足。"
    if abs(effect) <= noise:
        return "inconclusive", "受控证据未支持确定性归因：效应未超过 baseline noise floor。"
    if direction == "unresolved":
        return (
            "supported",
            "受控证据支持存在超过噪声的可检测干预效应；事前方向为 unresolved，不识别唯一根因。",
        )
    predicted_sign = 1.0 if direction == "increase" else -1.0
    if effect * predicted_sign > 0:
        return "supported", "受控证据支持该事前方向性假设（仅限已测试条件）。"
    return "falsified", "受控证据未支持该事前方向；反向效应超过 baseline noise floor。"


def analyze(plan: dict[str, Any], checked: dict[str, Any], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {record["run_id"]: record for record in records}
    conclusions = []
    for raw_variant in plan["variants"]:
        hypothesis = checked["hypotheses"][raw_variant["hypothesis_id"]]
        baseline_ids = raw_variant["baseline_run_ids"]
        variant_ids = raw_variant["run_ids"]
        baseline_records = [by_id[rid] for rid in baseline_ids]
        variant_records = [by_id[rid] for rid in variant_ids]
        baseline_values = [r["metric_value"] for r in baseline_records if r["success"]]
        variant_values = [r["metric_value"] for r in variant_records if r["success"]]
        enough = len(baseline_values) >= 2 and len(variant_values) >= 1
        if enough:
            baseline_center = statistics.median(baseline_values)
            variant_center = statistics.median(variant_values)
            effect = variant_center - baseline_center
            noise = pairwise_noise(baseline_values, checked["noise_epsilon"])
        else:
            baseline_center = variant_center = effect = noise = None
        status, evidence = verdict(hypothesis["direction"], effect, noise)
        conclusions.append(
            {
                "variant_id": raw_variant["variant_id"],
                "hypothesis_id": hypothesis["hypothesis_id"],
                "statement": hypothesis["statement"],
                "predicted_signatures": hypothesis["predicted_signatures"],
                "signature_status": "manual_review_required; numeric direction alone does not establish a unique root cause",
                "falsification": hypothesis["falsification"],
                "direction": hypothesis["direction"],
                "factor": raw_variant["factor"],
                "changed_paths": raw_variant["changed_paths"],
                "candidate": baseline_records[0]["candidate"],
                "baseline_run_ids": baseline_ids,
                "variant_run_ids": variant_ids,
                "baseline_values": baseline_values,
                "variant_values": variant_values,
                "baseline_median": baseline_center,
                "variant_median": variant_center,
                "effect_variant_minus_baseline": effect,
                "noise_floor": noise,
                "noise_definition": "noise_epsilon + maximum absolute pairwise baseline difference",
                "status": status,
                "evidence_statement": evidence,
                "attribution_scope": SCOPE,
                "failed_runs": [
                    r["run_id"] for r in baseline_records + variant_records if not r["success"]
                ],
            }
        )
    return conclusions


def uncertainty_for(
    plan: dict[str, Any],
    records: list[dict[str, Any]],
    missing_artifact_paths: list[str] | None = None,
    missing_answer_fields: list[str] | None = None,
) -> list[str]:
    uncertainty = [
        SCOPE,
        "受控证据支持/未支持不等于证明唯一根因；未测试的交互作用和其他因素仍可能贡献差异。",
        "predicted_signatures 需要结合原输出和图表人工核验，方向统计本身不证明完整 signature。",
        "changed_paths 预检验证计划声明；调查者仍须检查实现是否发生未登记共变。",
    ]
    provenance = plan.get("provenance_notes", [])
    if isinstance(provenance, list):
        uncertainty.extend(str(item) for item in provenance)
    if any(not record["success"] for record in records):
        uncertainty.append("至少一个运行失败、超时、指标缺失或声明输出缺失，因此 result.status 为 partial。")
    if not records:
        uncertainty.append("预检拒绝，0 个候选命令被执行，没有科学干预证据；result.status 为 unable。")
    if missing_artifact_paths:
        uncertainty.append(
            "plan.artifact_contract 声明的自定义 artifact 缺失，不能冒充完整交付："
            + ", ".join(missing_artifact_paths)
        )
    if missing_answer_fields:
        uncertainty.append(
            "case.output_contract 字段仅有结构化 unavailable 或暂无实质答案，因此证据交付不完整："
            + ", ".join(missing_answer_fields)
        )
    return uncertainty


def source_snapshot(
    plan: dict[str, Any],
    plan_path: Path,
    digest: str | None,
    case_path: Path | None,
) -> list[dict[str, Any]]:
    snapshot = [
        {
            "path": str(plan_path),
            "role": "pre-registration plan",
            "sha256": digest,
        }
    ]
    if case_path is not None:
        item: dict[str, Any] = {
            "path": str(case_path),
            "role": "real case.json; authoritative case_id and answer output_contract",
            "resolved_path": str(case_path),
        }
        if case_path.is_file():
            item["sha256"] = hashlib.sha256(case_path.read_bytes()).hexdigest()
        snapshot.append(item)
    sources = plan.get("sources", [])
    if isinstance(sources, list):
        for source in sources:
            if not isinstance(source, dict) or not isinstance(source.get("path"), str):
                continue
            item = copy.deepcopy(source)
            path = Path(item["path"])
            resolved = path if path.is_absolute() else plan_path.parent / path
            if resolved.is_file() and "sha256" not in item:
                # Hash evidence bytes only; never inspect environment or credentials.
                item["sha256"] = hashlib.sha256(resolved.read_bytes()).hexdigest()
            item["resolved_path"] = str(resolved)
            snapshot.append(item)
    return snapshot


def structured_unavailable(field: str, execution_status: str) -> dict[str, Any]:
    if execution_status == "rejected":
        reason = "Plan/case preflight or hash validation failed; no candidate evidence was generated for this answer field."
        next_steps = "Correct and seal a new plan before execution; do not rewrite the rejected plan after viewing results."
    else:
        reason = "No substantive case-specific value or evidence-backed plan value was supplied for this required answer field."
        next_steps = "Add a substantive, evidence-backed contract_values entry in a new pre-registered plan and execute it."
    return {
        "unavailable": {
            "reason": reason,
            "missing": [f"substantive evidence for case.output_contract field {field}"],
            "next_steps": next_steps,
            "evidence": ["runs/index.json", "intervention_report.json"],
        }
    }


def dynamic_answer(
    field: str,
    records: list[dict[str, Any]],
    conclusions: list[dict[str, Any]],
) -> Any:
    reproduction = reproduction_summary(records)
    if field == "reproduction_summary" and records:
        return {
            "execution_command_count": len(records),
            "all_runs_succeeded": all(record["success"] for record in records),
            **reproduction,
        }
    if field == "candidate_comparison" and records:
        return {
            "candidate_summaries": reproduction["candidate_summaries"],
            "run_comparisons": reproduction["run_comparisons"],
            "failed_runs": [record["run_id"] for record in records if not record["success"]],
            "evidence": "runs/index.json and candidate-emitted stdout JSON",
        }
    if field in {
        "attribution_summary",
        "intervention_summary",
        "scientific_conclusions",
        "difference_attribution",
        "noise_floor_analysis",
    } and conclusions:
        return {
            "scope": SCOPE,
            "conclusions": conclusions,
            "evidence": "intervention_report.json and runs/index.json",
        }
    return None


def answer_field_value(
    field: str,
    plan: dict[str, Any],
    artifact_contract: dict[str, str],
    records: list[dict[str, Any]],
    conclusions: list[dict[str, Any]],
    execution_status: str,
) -> Any:
    if field in STANDARD_RESULT_FIELDS:
        return None  # The authoritative metadata is injected after field expansion.
    if field in STANDARD_ARTIFACT_FIELDS:
        # Only standard named artifacts may use a path as their contract answer.
        return artifact_contract.get(field, DEFAULT_ARTIFACT_CONTRACT[field])
    supplied = plan.get("contract_values", {})
    if isinstance(supplied, dict) and field in supplied:
        # Case-specific preregistered evidence may refine a generated default.
        return copy.deepcopy(supplied[field])
    dynamic = dynamic_answer(field, records, conclusions)
    if dynamic is not None:
        return dynamic
    return structured_unavailable(field, execution_status)


def missing_answer_fields(
    fields: list[str],
    plan: dict[str, Any],
    artifact_contract: dict[str, str],
    records: list[dict[str, Any]],
    conclusions: list[dict[str, Any]],
    execution_status: str,
) -> list[str]:
    missing = []
    for field in fields:
        if field in STANDARD_RESULT_FIELDS:
            continue
        value = answer_field_value(
            field, plan, artifact_contract, records, conclusions, execution_status
        )
        if unavailable(value):
            missing.append(field)
    return missing


def result_document(
    plan: dict[str, Any],
    plan_path: Path,
    case: dict[str, Any],
    case_path: Path | None,
    digest: str | None,
    contract_fields: list[str],
    artifact_contract: dict[str, str],
    status: str,
    execution_status: str,
    records: list[dict[str, Any]],
    conclusions: list[dict[str, Any]],
    validation_errors: list[str],
    missing_artifact_paths: list[str],
    missing_answer_fields_list: list[str],
) -> dict[str, Any]:
    if status not in RESULT_STATUSES or execution_status not in EXECUTION_STATUSES:
        raise PlanError("internal error: illegal result or execution status")
    counts = {name: 0 for name in ("supported", "falsified", "inconclusive")}
    for conclusion in conclusions:
        if conclusion["status"] in counts:
            counts[conclusion["status"]] += 1
    result: dict[str, Any] = {}
    for field in contract_fields:
        value = answer_field_value(
            field, plan, artifact_contract, records, conclusions, execution_status
        )
        if field not in STANDARD_RESULT_FIELDS:
            result[field] = value
    result.update(
        {
            "case_id": case.get("case_id", "unknown"),
            "status": status,
            "execution_status": execution_status,
            "sources": source_snapshot(plan, plan_path, digest, case_path),
            "uncertainty": uncertainty_for(
                plan, records, missing_artifact_paths, missing_answer_fields_list
            ),
            "artifacts": artifact_contract,
            "missing_artifact_contract_artifacts": missing_artifact_paths,
            "missing_contract_answer_fields": missing_answer_fields_list,
            "case_output_contract_fields": contract_fields,
            "evidence_delivery_complete": (
                not missing_artifact_paths and not missing_answer_fields_list
            ),
            "change_records": [
                {
                    "variant_id": item["variant_id"],
                    "hypothesis_id": item["hypothesis_id"],
                    "factor": item["factor"],
                    "changed_paths": item["changed_paths"],
                    "baseline_run_ids": item["baseline_run_ids"],
                    "variant_run_ids": item["variant_run_ids"],
                    "effect_variant_minus_baseline": item["effect_variant_minus_baseline"],
                    "noise_floor": item["noise_floor"],
                    "status": item["status"],
                    "evidence_statement": item["evidence_statement"],
                    "attribution_scope": SCOPE,
                }
                for item in conclusions
            ],
            "plan_sha256": digest,
            "plan_hash_verified": digest is not None,
            "execution_command_count": len(records),
            "all_runs_succeeded": bool(records) and all(r["success"] for r in records),
            "conclusion_counts": counts,
            "validation_errors": validation_errors,
            "attribution_scope": SCOPE,
        }
    )
    return result


def reproduction_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare emitted targets and preregistered tolerances without relaxing them."""
    comparisons = []
    candidates: dict[str, dict[str, Any]] = {}
    for record in records:
        payload = record.get("json_payload")
        if not isinstance(payload, dict):
            continue
        required = ("target", "tolerance", "within_preregistered_tolerance")
        if not all(key in payload for key in required):
            continue
        target = payload.get("target")
        tolerance = payload.get("tolerance")
        within = payload.get("within_preregistered_tolerance")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in (target, tolerance)
        ):
            continue
        if not isinstance(within, bool):
            continue
        item = {
            "run_id": record["run_id"],
            "candidate": record["candidate"],
            "role": record["role"],
            "target": payload.get("target"),
            "error": record.get("metric_value"),
            "tolerance": payload.get("tolerance"),
            "within_preregistered_tolerance": payload.get(
                "within_preregistered_tolerance"
            ),
        }
        comparisons.append(item)
        summary = candidates.setdefault(
            record["candidate"],
            {
                "baseline_comparable_runs": 0,
                "baseline_within_tolerance": 0,
                "variant_comparable_runs": 0,
                "variant_within_tolerance": 0,
                "target_values": set(),
                "tolerance_values": set(),
            },
        )
        prefix = "baseline" if record["role"] == "baseline" else "variant"
        summary[prefix + "_comparable_runs"] += 1
        if payload.get("within_preregistered_tolerance") is True:
            summary[prefix + "_within_tolerance"] += 1
        summary["target_values"].add(payload.get("target"))
        summary["tolerance_values"].add(payload.get("tolerance"))
    serializable = {}
    for candidate, summary in candidates.items():
        serializable[candidate] = {
            **{key: value for key, value in summary.items() if not isinstance(value, set)},
            "target_values": sorted(summary["target_values"]),
            "tolerance_values": sorted(summary["tolerance_values"]),
        }
    return {
        "basis": "candidate-emitted target/error/tolerance fields fixed before intervention",
        "run_comparisons": comparisons,
        "candidate_summaries": serializable,
        "limitation": "This scalar comparison does not replace real-PDF figure/table source localization and manual comparison.",
    }


def markdown_report(
    plan: dict[str, Any],
    digest: str | None,
    case_id: str,
    status: str,
    execution_status: str,
    conclusions: list[dict[str, Any]],
    errors: list[str],
    records: list[dict[str, Any]],
) -> str:
    reproduction = reproduction_summary(records)
    lines = [
        f"# 受控干预报告：{case_id}",
        "",
        f"- 结果状态：`{status}`",
        f"- 执行状态：`{execution_status}`",
        f"- 预注册 SHA256：`{digest or 'unverified'}`",
        f"- 归因范围：**{SCOPE}**",
        "- 措辞约束：仅报告“受控证据支持/未支持”，不自动断言唯一根因。",
        "",
        "## 目标与事前容差对照",
        "",
        "| run | candidate | role | target | error | tolerance | within tolerance |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    if reproduction["run_comparisons"]:
        for item in reproduction["run_comparisons"]:
            lines.append(
                "| {run_id} | {candidate} | {role} | {target} | {error} | {tolerance} | {within_preregistered_tolerance} |".format(**item)
            )
        for candidate, summary in sorted(reproduction["candidate_summaries"].items()):
            lines.append(
                f"\n候选 {candidate}：baseline {summary['baseline_within_tolerance']}/{summary['baseline_comparable_runs']} 达到事前容差；"
                f"variant {summary['variant_within_tolerance']}/{summary['variant_comparable_runs']} 达到事前容差。"
            )
    else:
        lines.append("| n/a | n/a | n/a | n/a | n/a | n/a | 未提供可比 JSON 字段，须人工补齐 |")
    lines.extend(
        [
            "",
            "此标量对照不替代真实 PDF 图表来源定位与趋势/关键点/误差/单位人工对照。",
            "",
            "## 事前假设与结果",
            "",
        ]
    )
    if errors:
        lines.extend(["## 预检错误", ""] + [f"- {error}" for error in errors] + [""])
    if not conclusions:
        lines.extend(["没有产生科学干预结论；候选命令未运行或证据不完整。", ""])
    for item in conclusions:
        lines.extend(
            [
                f"### {item['variant_id']} / {item['hypothesis_id']}：`{item['status']}`",
                "",
                f"- 假设：{item['statement']}",
                f"- factor / changed path：`{item['factor']}` / `{item['changed_paths'][0]}`",
                f"- baseline 值：`{item['baseline_values']}`",
                f"- variant 值：`{item['variant_values']}`",
                f"- effect（variant - baseline）：`{item['effect_variant_minus_baseline']}`",
                f"- noise floor：`{item['noise_floor']}`",
                f"- 事前方向：`{item['direction']}`",
                f"- 证据措辞：{item['evidence_statement']}",
                f"- 预测 signatures：{item['predicted_signatures']}（仍需原输出/图表人工核验）",
                f"- 范围：{SCOPE}",
                "",
            ]
        )
    lines.extend(
        [
            "## 复现与证据边界",
            "",
            "本报告包含候选输出的目标容差对照，但不替代真实论文来源核验和图表对照。正式任务须在 result 来源与不确定性中保留合成材料、原始仓库缺失和自行设定参数的说明。",
            "",
        ]
    )
    return "\n".join(lines)


def persist_outputs(
    output_dir: Path,
    plan: dict[str, Any],
    plan_path: Path,
    case: dict[str, Any],
    case_path: Path | None,
    digest: str | None,
    contract_fields: list[str],
    artifact_contract: dict[str, str],
    status: str,
    execution_status: str,
    records: list[dict[str, Any]],
    conclusions: list[dict[str, Any]],
    errors: list[str],
    missing_artifact_paths: list[str],
    missing_answer_fields_list: list[str],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    case_id = case.get("case_id", "unknown")
    write_json(output_dir / "preregistered_plan.json", plan)
    write_text(output_dir / "plan.sha256", (digest or "UNVERIFIED") + "\n")
    write_json(
        output_dir / "runs" / "index.json",
        {
            "case_id": case_id,
            "plan_sha256": digest,
            "execution_status": execution_status,
            "execution_command_count": len(records),
            "runs": records,
        },
    )
    report = {
        "case_id": case_id,
        "question": plan.get("question"),
        "plan_sha256": digest,
        "status": status,
        "execution_status": execution_status,
        "case_output_contract_fields": contract_fields,
        "validation_errors": errors,
        "conclusions": conclusions,
        "reproduction_comparison": reproduction_summary(records),
        "uncertainty": uncertainty_for(
            plan, records, missing_artifact_paths, missing_answer_fields_list
        ),
        "missing_artifact_contract_artifacts": missing_artifact_paths,
        "missing_contract_answer_fields": missing_answer_fields_list,
        "attribution_scope": SCOPE,
    }
    write_json(output_dir / "intervention_report.json", report)
    write_text(
        output_dir / "intervention_report.md",
        markdown_report(
            plan, digest, case_id, status, execution_status, conclusions, errors, records
        ),
    )
    result = result_document(
        plan,
        plan_path,
        case,
        case_path,
        digest,
        contract_fields,
        artifact_contract,
        status,
        execution_status,
        records,
        conclusions,
        errors,
        missing_artifact_paths,
        missing_answer_fields_list,
    )
    write_json(output_dir / "result.json", result)
    # Custom artifact paths are evidence locations only. Never fabricate their
    # contents or use a custom path as the answer to a case contract question.


def seal_plan(path: Path) -> int:
    plan = load_plan(path)
    registration = plan.get("registration")
    if not isinstance(registration, dict):
        raise PlanError("registration must be an object before sealing")
    registration["plan_sha256"] = plan_digest(plan)
    write_json(path, plan)
    print(json.dumps({"plan": str(path), "plan_sha256": registration["plan_sha256"]}))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--plan", type=Path, help="sealed JSON plan to validate and execute")
    group.add_argument("--seal-plan", type=Path, help="explicitly seal a plan before any run")
    parser.add_argument("--output-dir", type=Path, help="directory for final audit artifacts")
    args = parser.parse_args(argv)
    if args.seal_plan:
        try:
            return seal_plan(args.seal_plan.resolve())
        except PlanError as exc:
            print(f"plan sealing failed: {exc}", file=sys.stderr)
            return 2
    if args.output_dir is None:
        parser.error("--output-dir is required with --plan")

    plan_path = args.plan.resolve()
    output_dir = args.output_dir.resolve()
    plan: dict[str, Any] = {
        "case_id": "unknown",
        "sources": [],
        "provenance_notes": [],
    }
    case: dict[str, Any] = {}
    case_path: Path | None = None
    contract_fields: list[str] = []
    artifact_contract = dict(DEFAULT_ARTIFACT_CONTRACT)
    digest: str | None = None
    records: list[dict[str, Any]] = []
    conclusions: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        plan = load_plan(plan_path)
        artifact_contract = validate_artifact_contract(plan)
        case, case_path, contract_fields = load_case(plan_path, plan)
        digest = validate_hash(plan)
        checked = validate_plan(
            plan, plan_path, case, contract_fields, artifact_contract
        )
    except PlanError as exc:
        errors.append(str(exc))
        missing_artifact_paths: list[str] = []
        missing_answers = missing_answer_fields(
            contract_fields, plan, artifact_contract, records, conclusions, "rejected"
        )
        persist_outputs(
            output_dir,
            plan,
            plan_path,
            case,
            case_path,
            digest,
            contract_fields,
            artifact_contract,
            "unable",
            "rejected",
            records,
            conclusions,
            errors,
            missing_artifact_paths,
            missing_answers,
        )
        print(f"plan rejected before execution: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        errors.append(f"output/source I/O error during preflight: {exc}")
        print(errors[-1], file=sys.stderr)
        return 2

    # Every command is attempted, even after candidate A or another run fails.
    for raw in checked["runs"].values():
        records.append(execute_run(raw, plan_path, output_dir, checked["metric_key"]))
    conclusions = analyze(plan, checked, records)
    missing_artifact_paths = missing_artifacts(output_dir, artifact_contract)
    missing_answers = missing_answer_fields(
        contract_fields, plan, artifact_contract, records, conclusions, "complete"
    )
    delivery_complete = not missing_artifact_paths and not missing_answers
    execution_status = (
        "complete"
        if bool(records) and all(record["success"] for record in records) and delivery_complete
        else "partial"
    )
    status = "success" if execution_status == "complete" else "partial"
    persist_outputs(
        output_dir,
        plan,
        plan_path,
        case,
        case_path,
        digest,
        contract_fields,
        artifact_contract,
        status,
        execution_status,
        records,
        conclusions,
        errors,
        missing_artifact_paths,
        missing_answers,
    )
    print(
        json.dumps(
            {
                "case_id": case["case_id"],
                "status": status,
                "execution_status": execution_status,
                "executed": len(records),
                "conclusions": {
                    item["variant_id"]: item["status"] for item in conclusions
                },
                "result": str(output_dir / "result.json"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
