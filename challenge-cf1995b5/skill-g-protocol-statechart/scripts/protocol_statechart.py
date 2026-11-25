#!/usr/bin/env python3
"""Compile one experimental protocol specification into a bounded QC statechart.

Python 3 standard library only. All costs and durations use Decimal arithmetic.
Simulations execute injected, explicitly hypothetical branch labels; they never
measure an experiment and never use eval/exec.
"""

import argparse
import hashlib
import html
import json
from pathlib import Path
import shutil
import subprocess
import sys

from decimal import Decimal, InvalidOperation


SCHEMA_VERSION = "1.0"
EXAMPLE_NOTICE = "合成示例输出，非正式测评结果"
GENERAL_NOTICE = "协议状态图与假设仿真输出；不是实测实验结果"
OPERATORS = {"<", "<=", ">", ">=", "==", "!="}
TEXT_SUFFIXES = {".txt", ".md", ".json", ".csv", ".tsv", ".yaml", ".yml"}
TERMINAL_OUTCOMES = {"success", "failure"}


class InputError(Exception):
    pass


def decimal_value(value, label="value"):
    if isinstance(value, bool) or value is None:
        raise InvalidOperation(label)
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InputError(f"{label} must be a finite decimal; got {value!r}") from exc
    if not result.is_finite():
        raise InputError(f"{label} must be finite; got {value!r}")
    return result


def decimal_text(value):
    value = decimal_value(value)
    if value == 0:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def json_default(value):
    if isinstance(value, Decimal):
        return decimal_text(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def load_json(path):
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle, parse_float=Decimal)
    except FileNotFoundError as exc:
        raise InputError(f"required JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise InputError(f"invalid JSON in {path}: line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def write_json(path, value):
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=json_default))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def case_identifier(case):
    return str(case.get("case_id") or case.get("id") or "unknown_case")


def output_notice(case):
    return EXAMPLE_NOTICE if case.get("synthetic") is True else GENERAL_NOTICE


def case_domains(case):
    """Canonical parameter_domains wins even when it is deliberately empty."""
    if isinstance(case.get("parameter_domains"), dict):
        return case["parameter_domains"]
    legacy = case.get("experimental_domains")
    return legacy if isinstance(legacy, dict) else {}


def budget_settings(case):
    """Return canonical contract limits with explicit legacy minute aliases."""
    contract = case.get("resource_contract") if isinstance(case.get("resource_contract"), dict) else {}
    legacy = case.get("budget") if isinstance(case.get("budget"), dict) else {}
    maximum = contract.get("budget_cap") if "budget_cap" in contract else legacy.get("max_cost", legacy.get("max_total_cost"))
    deadline_days = contract.get("deadline_days") if "deadline_days" in contract else None
    deadline_minutes = None if deadline_days is not None else legacy.get("deadline_minutes", legacy.get("max_duration_minutes"))
    return {
        "currency": contract.get("currency", legacy.get("currency", "unspecified")),
        "max_cost": maximum,
        "deadline_days": deadline_days,
        "deadline_minutes": deadline_minutes,
        "canonical": bool(contract),
    }


def output_paths(args):
    return Path(args.work_dir), Path(args.output_dir)


def required_fields(case):
    contract = case.get("output_contract") or {}
    fields = contract.get("required_fields") or []
    result = []
    if isinstance(fields, dict):
        fields = list(fields)
    for field in fields:
        if isinstance(field, str):
            result.append(field)
        elif isinstance(field, dict) and isinstance(field.get("name"), str):
            result.append(field["name"])
    return list(dict.fromkeys(result))


def read_task(path):
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise InputError(f"required task file not found: {path}") from exc
    return {"path": str(path), "role": "task", "sha256": sha256(path), "characters_read": len(text), "text": text}


def read_materials(directory, exclude_paths=()):
    """Discover material files without reclassifying case/task inputs as evidence."""
    directory = Path(directory)
    excluded = {Path(path).resolve() for path in exclude_paths if path is not None}
    records = []
    warnings = []
    if not directory.is_dir():
        message = f"Materials directory absent: {directory}; no material contents were assumed."
        return records, [message]
    for path in sorted(directory.rglob("*"), key=lambda item: str(item.relative_to(directory))):
        if not path.is_file() or path.is_symlink() or path.resolve() in excluded:
            continue
        relative = str(path.relative_to(directory))
        record = {
            "path": str(path), "relative_path": relative, "role": "material", "sha256": sha256(path),
            "evidence_scope": "Supplied material provenance; not independently verified scientific evidence.",
        }
        suffix = path.suffix.lower()
        if suffix in TEXT_SUFFIXES:
            raw = path.read_bytes()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                record["extraction"] = "failed"
                warnings.append(f"Material is not valid UTF-8: {relative}; its contents were not assumed.")
                records.append(record)
                continue
            record.update({"extraction": "read_utf8_text", "characters_read": len(text), "excerpt": text[:12000]})
        elif suffix == ".pdf":
            executable = shutil.which("pdftotext")
            if executable:
                completed = subprocess.run(
                    [executable, str(path), "-"], check=False, capture_output=True, timeout=60
                )
                if completed.returncode == 0:
                    text = completed.stdout.decode("utf-8", errors="replace")
                    record.update({
                        "extraction": "pdftotext",
                        "characters_read": len(text),
                        "excerpt": text[:12000],
                    })
                    if not text.strip():
                        warnings.append(f"PDF yielded no text: {relative}; inspect it manually before scientific reliance.")
                else:
                    record["extraction"] = "failed"
                    warnings.append(f"pdftotext failed for {relative} with exit {completed.returncode}; PDF content not assumed.")
            else:
                record["extraction"] = "unavailable"
                warnings.append(
                    f"PDF text not extracted for {relative}: pdftotext is unavailable. Provide UTF-8 text or inspect the PDF with an available PDF tool."
                )
        else:
            record["extraction"] = "unsupported"
            warnings.append(f"Unsupported material type not read: {relative}; its contents were not assumed.")
        records.append(record)
    return records, warnings


def _resource_items(value):
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def note_json_objects(note):
    """Recover every decodable embedded JSON object without assuming note layout."""
    if isinstance(note, dict):
        return [note]
    if not isinstance(note, str):
        return []
    decoder = json.JSONDecoder(parse_float=Decimal)
    objects = []
    offset = 0
    while offset < len(note):
        start = note.find("{", offset)
        if start < 0:
            break
        try:
            value, end = decoder.raw_decode(note, start)
        except json.JSONDecodeError:
            offset = start + 1
            continue
        offset = max(end, start + 1)
        if isinstance(value, dict):
            objects.append(value)
    return objects


def build_resource_register(case):
    """Merge canonical resources and equipment-note objects, retaining conflicts."""
    contract = case.get("resource_contract") if isinstance(case.get("resource_contract"), dict) else {}
    register = {
        "contract_present": isinstance(case.get("resource_contract"), dict),
        "equipment": [], "reagents": [], "materials": [], "conflicts": [], "errors": [],
        "note_objects": note_json_objects(case.get("equipment_domain_note", contract.get("equipment_domain_note", ""))),
    }
    identities = {}

    def fingerprint(item):
        return json.dumps(item, ensure_ascii=False, sort_keys=True, default=json_default)

    def add(item, kind, origin):
        if not isinstance(item, dict):
            register["errors"].append(f"Resource from {origin} is not an object.")
            return
        resource_id = item.get("id")
        if not isinstance(resource_id, str) or not resource_id:
            register["errors"].append(f"Resource from {origin} lacks a nonempty string id.")
            return
        key = (kind, resource_id)
        clean = dict(item)
        bucket = "equipment" if kind == "equipment" else ("reagents" if kind == "reagent" else "materials")
        if key in identities:
            prior = identities[key]
            if fingerprint(prior["_clean"]) != fingerprint(clean):
                register["conflicts"].append({
                    "id": resource_id, "kind": kind, "existing": prior["_clean"], "incoming": clean,
                    "origins": prior["record"]["origins"] + [origin],
                })
            elif origin not in prior["record"]["origins"]:
                prior["record"]["origins"].append(origin)
            return
        record = dict(clean)
        record.update({
            "resource_kind": kind,
            "origins": [origin],
            "note_only": origin == "equipment_domain_note",
        })
        identities[key] = {"record": record, "_clean": clean}
        register[bucket].append(record)
        for other_kind in ("equipment", "reagent", "material"):
            other = identities.get((other_kind, resource_id))
            if other is not None and other_kind != kind:
                register["conflicts"].append({
                    "id": resource_id, "kind": "cross_kind", "existing_kind": other_kind,
                    "incoming_kind": kind, "origins": other["record"]["origins"] + [origin],
                })

    for item in _resource_items(contract.get("equipment")):
        add(item, "equipment", "resource_contract.equipment")
    for item in _resource_items(contract.get("reagents")):
        add(item, "reagent", "resource_contract.reagents")
    optional = contract.get("resources")
    if isinstance(optional, dict):
        for key, kind in (("equipment", "equipment"), ("reagents", "reagent"), ("materials", "material")):
            for item in _resource_items(optional.get(key)):
                add(item, kind, f"resource_contract.resources.{key}")
    elif isinstance(optional, list):
        for item in optional:
            if not isinstance(item, dict):
                register["errors"].append("Optional resource entry is not an object.")
                continue
            kind = str(item.get("resource_kind") or item.get("kind") or item.get("type") or "").lower()
            kind = {"equipment": "equipment", "device": "equipment", "reagent": "reagent", "material": "material"}.get(kind)
            if kind is None:
                register["errors"].append(f"Optional resource {item.get('id')!r} has no recognized equipment/reagent/material kind.")
            else:
                add(item, kind, "resource_contract.resources")

    note_objects = register["note_objects"]
    for index, obj in enumerate(note_objects):
        origin = "equipment_domain_note"
        found = []
        found.extend(_resource_items(obj.get("equipment")))
        resources = obj.get("resources")
        if isinstance(resources, dict):
            found.extend(_resource_items(resources.get("equipment")))
        if not found and isinstance(obj.get("id"), str) and any(key in obj for key in ("name", "model", "spec", "price_per_hour")):
            found.append(obj)
        if not found:
            register["errors"].append(f"Embedded note JSON object {index} contains no equipment entries.")
        for item in found:
            add(item, "equipment", origin)

    equipment_ids = {item["id"] for item in register["equipment"]}
    material_ids = {item["id"] for item in register["reagents"] + register["materials"]}
    register["known_ids"] = {"equipment": sorted(equipment_ids), "materials": sorted(material_ids)}
    register["note_only_equipment_ids"] = sorted(item["id"] for item in register["equipment"] if item["note_only"])
    register["deduplicated_counts"] = {
        "equipment": len(register["equipment"]), "reagents": len(register["reagents"]), "materials": len(register["materials"]),
    }
    return register


def domain_errors(name, value, domain):
    errors = []
    if not isinstance(domain, dict):
        return [f"Parameter {name}: case domain is not an object."]
    kind = domain.get("type", "decimal")
    if kind in {"categorical", "category", "enum"}:
        allowed = domain.get("values", domain.get("allowed", [])) if kind == "enum" else domain.get("allowed", domain.get("values", []))
        if not isinstance(allowed, list) or not allowed:
            return [f"Parameter {name}: enum/categorical domain requires a nonempty values/allowed list."]
        if value not in allowed:
            errors.append(f"Parameter {name}: {value!r} is not in declared allowed values {allowed!r}.")
        return errors
    if kind not in {"range", "decimal", "number", "integer"}:
        return [f"Parameter {name}: unsupported domain type {kind!r}."]
    try:
        actual = decimal_value(value, name)
        minimum = decimal_value(domain.get("min"), f"{name}.min")
        maximum = decimal_value(domain.get("max"), f"{name}.max")
        step = decimal_value(domain.get("step"), f"{name}.step")
    except (InputError, InvalidOperation) as exc:
        return [f"Parameter {name}: invalid numeric value/domain ({exc})."]
    if step <= 0 or minimum > maximum:
        return [f"Parameter {name}: domain requires min <= max and step > 0."]
    if actual < minimum or actual > maximum:
        errors.append(f"Parameter {name}: {decimal_text(actual)} outside [{decimal_text(minimum)}, {decimal_text(maximum)}].")
    if (actual - minimum) % step != 0:
        errors.append(f"Parameter {name}: {decimal_text(actual)} is off the Decimal step grid {decimal_text(step)} from {decimal_text(minimum)}.")
    if kind == "integer" and actual != actual.to_integral_value():
        errors.append(f"Parameter {name}: integer domain received {decimal_text(actual)}.")
    return errors


def candidate_audits(case):
    domains = case_domains(case)
    limits = budget_settings(case)
    candidates = case.get("candidate_plans") or []
    if not isinstance(candidates, list):
        return [{
            "candidate_id": "unknown_candidate", "errors": ["candidate_plans must be a list."],
            "assessment": "rejected_or_requires_revision", "evidence_status": "candidate_claims_audited_not_measured",
        }]
    audits = []
    for index, raw_candidate in enumerate(candidates):
        candidate = raw_candidate if isinstance(raw_candidate, dict) else {}
        cid = str(candidate.get("version") or candidate.get("id") or candidate.get("candidate_id") or f"unknown_candidate_{index + 1}")
        errors = [] if isinstance(raw_candidate, dict) else ["Candidate entry is not an object."]
        if not (candidate.get("version") or candidate.get("id") or candidate.get("candidate_id")):
            errors.append("Candidate has no version, id, or candidate_id; a positional unknown_candidate ID was assigned.")
        cost_items = candidate.get("cost_items") or []
        duration_items = candidate.get("duration_items") or []
        if not isinstance(cost_items, list):
            errors.append("cost_items must be a list.")
            cost_items = []
        if not isinstance(duration_items, list):
            errors.append("duration_items must be a list.")
            duration_items = []

        def parsed(value, label):
            try:
                return decimal_value(value, label)
            except (InputError, InvalidOperation) as exc:
                errors.append(str(exc))
                return None

        total_cost = Decimal(0)
        cost_complete = bool(cost_items)
        if not cost_items:
            errors.append("No cost_items supplied; candidate cost cannot be recomputed.")
        item_audits = []
        for item_index, raw_item in enumerate(cost_items):
            label = f"{cid}.cost_items[{item_index}]"
            if not isinstance(raw_item, dict):
                errors.append(f"{label} is not an object.")
                cost_complete = False
                continue
            item = raw_item
            item_name = str(item.get("item") or item.get("id") or item_index)
            computed = None
            basis = None
            if "unit_price" in item or "quantity" in item:
                unit_price = parsed(item.get("unit_price"), f"{label}.unit_price")
                quantity = parsed(item.get("quantity"), f"{label}.quantity")
                if unit_price is not None and quantity is not None:
                    computed = unit_price * quantity
                    basis = "unit_price*quantity"
            elif "amount" in item:
                computed = parsed(item.get("amount"), f"{label}.amount")
                basis = "amount"
            else:
                errors.append(f"{label} ({item_name}) needs amount or unit_price*quantity.")
            if computed is None:
                cost_complete = False
            else:
                total_cost += computed
            declared_subtotal = item.get("subtotal")
            normalized_subtotal = None
            if declared_subtotal is not None:
                normalized_subtotal = parsed(declared_subtotal, f"{label}.subtotal")
                if computed is not None and normalized_subtotal is not None and normalized_subtotal != computed:
                    errors.append(
                        f"Cost item {item_name}: declared subtotal {decimal_text(normalized_subtotal)} != recomputed {decimal_text(computed)}."
                    )
            elif basis == "unit_price*quantity":
                errors.append(f"Cost item {item_name}: canonical subtotal is missing.")
            item_audits.append({
                "item": item_name, "basis": basis,
                "recomputed_amount": None if computed is None else decimal_text(computed),
                "declared_subtotal": None if normalized_subtotal is None else decimal_text(normalized_subtotal),
            })

        declared_costs = {}
        primary_declared = None
        for key in ("total_cost", "claimed_total_cost", "cost_subtotal"):
            if candidate.get(key) is not None:
                value = parsed(candidate.get(key), f"{cid}.{key}")
                declared_costs[key] = None if value is None else decimal_text(value)
                if primary_declared is None:
                    primary_declared = value
                if cost_complete and value is not None and value != total_cost:
                    errors.append(f"Cost arithmetic mismatch: {key}={decimal_text(value)}, recomputed {decimal_text(total_cost)}.")
        if not declared_costs:
            errors.append("No total_cost, claimed_total_cost, or cost_subtotal declared.")

        total_duration = None
        duration_complete = None
        claimed_duration = None
        has_legacy_duration = "duration_items" in candidate or candidate.get("claimed_total_duration_minutes") is not None
        if has_legacy_duration:
            total_duration = Decimal(0)
            duration_complete = isinstance(candidate.get("duration_items"), list) and bool(duration_items)
            if not duration_items:
                errors.append("Legacy duration_items are missing/empty; minutes cannot be recomputed from est_days.")
            for item_index, item in enumerate(duration_items):
                if not isinstance(item, dict):
                    errors.append(f"{cid}.duration_items[{item_index}] is not an object.")
                    duration_complete = False
                    continue
                minutes = parsed(item.get("minutes"), f"{cid}.duration_items[{item_index}].minutes")
                if minutes is None:
                    duration_complete = False
                else:
                    total_duration += minutes
            claimed_duration = parsed(candidate.get("claimed_total_duration_minutes"), f"{cid}.claimed_total_duration_minutes")
            if duration_complete and claimed_duration is not None and claimed_duration != total_duration:
                errors.append(
                    f"Duration arithmetic mismatch (minutes alias only): claimed {decimal_text(claimed_duration)}, recomputed {decimal_text(total_duration)}."
                )

        estimated_days = None
        if candidate.get("est_days") is not None:
            estimated_days = parsed(candidate.get("est_days"), f"{cid}.est_days")
        elif not has_legacy_duration:
            errors.append("No canonical est_days or legacy duration_items supplied.")

        parameters = candidate.get("parameters") or {}
        if not isinstance(parameters, dict):
            errors.append("parameters must be an object.")
            parameters = {}
        elif not parameters and domains:
            errors.append("parameters is missing/empty although the case declares parameter domains.")
        for name, value in parameters.items():
            if name not in domains:
                errors.append(f"Parameter {name}: no domain declared in case.")
            else:
                errors.extend(domain_errors(name, value, domains[name]))

        over_budget = None
        if limits["max_cost"] is not None and cost_complete:
            maximum = parsed(limits["max_cost"], "resource_contract.budget_cap")
            if maximum is not None:
                over_budget = total_cost > maximum
                if over_budget:
                    errors.append(f"Recomputed cost {decimal_text(total_cost)} exceeds budget_cap {decimal_text(maximum)} {limits['currency']}.")
        over_deadline = None
        over_deadline_days = None
        over_deadline_minutes = None
        deadline_unit = None
        if limits["deadline_days"] is not None:
            deadline_unit = "days"
            maximum_days = parsed(limits["deadline_days"], "resource_contract.deadline_days")
            if maximum_days is not None and estimated_days is not None:
                over_deadline_days = estimated_days > maximum_days
                over_deadline = over_deadline_days
                if over_deadline_days:
                    errors.append(f"Candidate est_days {decimal_text(estimated_days)} exceeds deadline_days {decimal_text(maximum_days)}.")
        elif limits["deadline_minutes"] is not None:
            deadline_unit = "minutes"
            maximum_minutes = parsed(limits["deadline_minutes"], "budget.deadline_minutes")
            if maximum_minutes is not None and duration_complete and total_duration is not None:
                over_deadline_minutes = total_duration > maximum_minutes
                over_deadline = over_deadline_minutes
                if over_deadline_minutes:
                    errors.append(f"Recomputed legacy duration {decimal_text(total_duration)} minutes exceeds deadline {decimal_text(maximum_minutes)} minutes.")

        audits.append({
            "candidate_id": cid,
            "summary": candidate.get("summary", ""),
            "declared_total_cost": None if primary_declared is None else decimal_text(primary_declared),
            "declared_total_cost_fields": declared_costs,
            "claimed_total_cost": declared_costs.get("claimed_total_cost", declared_costs.get("total_cost")),
            "recomputed_total_cost": decimal_text(total_cost) if cost_complete else None,
            "cost_recomputation_complete": cost_complete,
            "cost_item_audits": item_audits,
            "currency": limits["currency"],
            "declared_est_days": None if estimated_days is None else decimal_text(estimated_days),
            "est_days": None if estimated_days is None else decimal_text(estimated_days),
            "claimed_total_duration_minutes": None if claimed_duration is None else decimal_text(claimed_duration),
            "recomputed_total_duration_minutes": None if not duration_complete or total_duration is None else decimal_text(total_duration),
            "duration_recomputation_complete": duration_complete,
            "duration_unit_note": "est_days is kept in days; no minutes are inferred from it. duration_items is a legacy minutes-only alias.",
            "over_budget": over_budget,
            "over_deadline": over_deadline,
            "over_deadline_days": over_deadline_days,
            "over_deadline_minutes": over_deadline_minutes,
            "deadline_unit": deadline_unit,
            "errors": errors,
            "assessment": "rejected_or_requires_revision" if errors else "arithmetically_consistent_pending_scientific_review",
            "evidence_status": "candidate_claims_audited_not_measured",
        })
    return audits


def compact_template(case, resource_register=None):
    domains = case_domains(case)
    register = resource_register or build_resource_register(case)
    equipment_id = register["known_ids"]["equipment"][0] if register["known_ids"]["equipment"] else "EQ1"
    material_id = register["known_ids"]["materials"][0] if register["known_ids"]["materials"] else "M1"
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": "replace_me",
        "title": "replace_with_protocol_title",
        "outcome_status": "hypothetical_unmeasured",
        "parameters": {name: "REPLACE_WITH_VALUE_IN_CASE_DOMAIN" for name in domains},
        "scientific_plan": {
            "hypotheses": [{"id": "H1", "statement": "falsifiable statement", "falsification": "observable result that rejects H1"}],
            "variables": {"independent": [], "dependent": [], "controlled": []},
            "controls": [{"id": "C1", "purpose": "calibration blank", "procedure_state": "S_BLANK"}],
            "acceptance_criteria": [{"metric": "qc_metric", "operator": "<=", "threshold": "REPLACE", "unit": "%", "record": "run_log.qc"}],
            "risk_and_revisions": [{"risk": "QC failure", "trigger": "guard fails", "revision": "bounded repeat or fail-safe terminal"}],
            "planning_evidence": [{"claim": "planning assumption only", "source_type": "synthetic_planning_assumption", "measured": False}],
        },
        "resources": {
            "equipment": [{"id": equipment_id, "name": "replace equipment details without changing a contract ID"}],
            "materials": [{"id": material_id, "name": "replace material details without changing a contract ID", "quantity": "1", "unit": "unit", "cost": "0"}],
        },
        "candidate_revisions": [
            {"candidate_id": "REPLACE_WITH_VERSION_OR_ID", "action": "revise", "changes": [], "reason": "link defects to the actual revised parameters/cost/time"}
        ],
        "uncertainty": ["Add agent-authored limitations that must survive compilation."],
        "change_log": [{"action": "authored_protocol_spec", "details": "Describe actual candidate revisions and graph decisions."}],
        "confirmation_items": ["Add case-specific items requiring human confirmation."],
        "settings": {"global_step_cap": 100},
        "states": [
            {"id": "S_START", "kind": "start", "next": "S_BLANK", "duration_minutes": "0", "cost": "0", "max_visits": 1},
            {"id": "S_BLANK", "kind": "action", "equipment": [equipment_id], "materials": [material_id], "parameters": {}, "duration_minutes": "5", "cost": "0", "next": "D_QC", "max_visits": 1},
            {"id": "D_QC", "kind": "decision", "duration_minutes": "0", "cost": "0", "max_visits": 1,
             "branches": [{"label": "qc_fail", "guard": {"metric": "qc_metric", "operator": ">", "threshold": "REPLACE", "unit": "%", "record": "run_log.qc"}, "next": "T_FAIL"}], "else": "T_SUCCESS"},
            {"id": "T_SUCCESS", "kind": "terminal", "outcome": "success", "duration_minutes": "0", "cost": "0", "max_visits": 1},
            {"id": "T_FAIL", "kind": "terminal", "outcome": "failure", "duration_minutes": "0", "cost": "0", "max_visits": 1},
        ],
        "scenarios": [{"scenario_id": "nominal", "outcome_basis": "synthetic_what_if", "decision_outcomes": {"D_QC": ["else"]}}],
    }


def source_records(case_path, task_record, material_records, spec_path=None, spec=None):
    sources = [{
        "path": str(case_path), "role": "case", "sha256": sha256(case_path),
        "evidence_scope": "Organizer input provenance, not external scientific evidence.",
    }]
    task_source = {key: value for key, value in task_record.items() if key != "text"}
    task_source["evidence_scope"] = "Task provenance, not external scientific evidence."
    sources.append(task_source)
    for record in material_records:
        sources.append({key: value for key, value in record.items() if key != "excerpt"})
    if spec_path is not None:
        sources.append({
            "path": str(spec_path), "role": "agent_authored_protocol_spec", "sha256": sha256(spec_path),
            "evidence_scope": "Authorship provenance only; the spec itself is not scientific proof.",
        })
    scientific = (spec or {}).get("scientific_plan") or {}
    for index, evidence in enumerate(scientific.get("planning_evidence") or []):
        if not isinstance(evidence, dict):
            continue
        locator_keys = ("source_locator", "locator", "citation", "url", "doi", "path")
        locators = {key: evidence[key] for key in locator_keys if evidence.get(key) is not None}
        if isinstance(evidence.get("source"), (str, dict)):
            locators["source"] = evidence["source"]
        sources.append({
            "role": "agent_authored_planning_evidence",
            "evidence_id": evidence.get("evidence_id", f"planning_evidence_{index + 1}"),
            "claim": evidence.get("claim"),
            "source_type": evidence.get("source_type"),
            "measured": evidence.get("measured", False),
            "source_locators": locators,
            "evidence_scope": "Agent-registered planning evidence; not made scientifically valid merely by inclusion in the spec.",
        })
    return sources


def bootstrap_result(case, status, audit, sources, warnings, notice):
    unknown = []
    common = {
        "revised_plan": {"partial": True, "reason": "Protocol spec not yet authored/compiled.", "template": "protocol_spec.template.json"},
        "candidate_assessment": audit,
        "validation": {"status": "partial", "stage": "bootstrap", "warnings": warnings},
        "status": status,
        "uncertainty": ["No protocol statechart has been compiled; no branch or scenario has been tested."] + warnings,
        "sources": sources,
        "change_log": ["Read case/task/material inputs; recomputed candidate arithmetic and domains; wrote compact template and early partial result."],
        "confirmation_items": [
            "Expert must confirm scientific suitability and actual SOPs before execution.",
            "Author one protocol_spec.json, then run compile.",
            "For deadline_days, graph minutes are divided by 1440 only as an elapsed-time comparison; booking, queueing and calendar time may be longer and require confirmation.",
        ],
    }
    result = {
        "case_id": case_identifier(case),
        "output_notice": notice,
        "completion_scope": "early_bootstrap_partial_only",
        "output_contract_unknown_fields": [],
        "simulation_interpretation": "No simulation performed at bootstrap; future scenarios are what-if paths, never measured outcomes.",
        "prospective_notice": "Costs and deadlines are planning estimates, not supplier quotes, bookings, or approvals.",
    }
    for field in required_fields(case):
        if field in common:
            result[field] = common[field]
        elif field == "case_id":
            result["case_id"] = case_identifier(case)
        else:
            marker = {"partial": True, "field": field, "reason": "Unknown required field has no validated bootstrap mapping."}
            result[field] = marker
            unknown.append(field)
    result["output_contract_unknown_fields"] = unknown
    for key, value in common.items():
        result.setdefault(key, value)
    return result


def command_bootstrap(args):
    case = load_json(args.case)
    task = read_task(args.task)
    materials, material_warnings = read_materials(args.materials_dir, (args.case, args.task))
    work, output = output_paths(args)
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    audits = candidate_audits(case)
    resources = build_resource_register(case)
    notice = output_notice(case)
    limits = budget_settings(case)
    audit_document = {
        "output_notice": notice,
        "case_id": case_identifier(case),
        "task": {key: value for key, value in task.items() if key != "text"},
        "task_excerpt": task["text"][:12000],
        "materials": materials,
        "material_warnings": material_warnings,
        "candidate_assessment": audits,
        "resource_register": resources,
        "arithmetic": "Decimal range/enum domains; exact item subtotal, total cost, canonical est_days, and optional legacy minutes recomputation",
        "resource_contract": case.get("resource_contract") or {},
        "budget": {"currency": limits["currency"], "budget_cap": limits["max_cost"], "deadline_days": limits["deadline_days"], "legacy_deadline_minutes": limits["deadline_minutes"]},
        "status": "partial",
        "interpretation": "Candidate errors identify required revision; this audit is not experimental validation. Case/task records are provenance, not external scientific evidence.",
    }
    write_json(work / "bootstrap_audit.json", audit_document)
    write_json(work / "protocol_spec.template.json", compact_template(case, resources))
    sources = source_records(args.case, task, materials)
    result = bootstrap_result(case, "partial", audits, sources, material_warnings, notice)
    result["resource_register"] = resources
    write_json(output / "result.json", result)
    print(f"bootstrap: wrote early partial result to {output / 'result.json'}")
    print(f"bootstrap: candidate audits={len(audits)}, material records={len(materials)}, equipment={len(resources['equipment'])}, material resources={len(resources['known_ids']['materials'])}")
    return 0


class Validation:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.checks = []

    def check(self, name, passed, detail, fatal=True):
        self.checks.append({"check": name, "passed": bool(passed), "detail": detail})
        if not passed:
            (self.errors if fatal else self.warnings).append(f"{name}: {detail}")

    def error(self, name, detail):
        self.check(name, False, detail, fatal=True)

    def warn(self, name, detail):
        self.check(name, False, detail, fatal=False)


def guard_error(guard):
    if not isinstance(guard, dict):
        return "guard must be an object"
    for key in ("metric", "operator", "threshold", "unit", "record"):
        if key not in guard or guard[key] is None or guard[key] == "":
            return f"guard missing observable field {key}"
    if guard["operator"] not in OPERATORS:
        return f"operator must be one of {sorted(OPERATORS)}"
    return None


def outgoing(state):
    kind = state.get("kind")
    if kind == "decision":
        targets = [branch.get("next") for branch in state.get("branches") or []]
        targets.append(state.get("else"))
        return [target for target in targets if isinstance(target, str)]
    if kind in {"start", "action"}:
        return [state["next"]] if isinstance(state.get("next"), str) else []
    return []


def tarjan(state_ids, adjacency):
    index = 0
    indices = {}
    low = {}
    stack = []
    on_stack = set()
    components = []

    def visit(node):
        nonlocal index
        indices[node] = index
        low[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in adjacency.get(node, []):
            if target not in indices:
                visit(target)
                low[node] = min(low[node], low[target])
            elif target in on_stack:
                low[node] = min(low[node], indices[target])
        if low[node] == indices[node]:
            component = []
            while True:
                member = stack.pop()
                on_stack.remove(member)
                component.append(member)
                if member == node:
                    break
            components.append(component)

    for state_id in state_ids:
        if state_id not in indices:
            visit(state_id)
    return components


def validate_spec(case, spec):
    v = Validation()
    domains = case_domains(case)
    v.check("schema_version", spec.get("schema_version") == SCHEMA_VERSION, f"Expected {SCHEMA_VERSION}.")
    v.check("outcome_status", spec.get("outcome_status") == "hypothetical_unmeasured", "Protocol outcomes must be explicitly hypothetical_unmeasured.")
    for field in ("candidate_revisions", "uncertainty", "change_log", "confirmation_items"):
        if field in spec:
            v.check(f"authored_{field}_container", isinstance(spec[field], (list, dict)), f"Optional {field} must be an array or object so it can be merged without loss.")
    scientific = spec.get("scientific_plan")
    v.check("scientific_plan_object", isinstance(scientific, dict), "scientific_plan object is required.")
    if not isinstance(scientific, dict):
        scientific = {}
    for section in ("hypotheses", "variables", "controls", "acceptance_criteria", "risk_and_revisions", "planning_evidence"):
        value = scientific.get(section)
        present = bool(value) and isinstance(value, (list, dict))
        v.check(f"scientific_section_{section}", present, f"Non-empty {section} is required.")
    for hypothesis in scientific.get("hypotheses") or []:
        if not isinstance(hypothesis, dict) or not hypothesis.get("statement") or not hypothesis.get("falsification"):
            v.error("falsifiable_hypothesis", "Every hypothesis needs statement and falsification.")
    for criterion in scientific.get("acceptance_criteria") or []:
        problem = guard_error(criterion)
        if problem:
            v.error("observable_acceptance_criterion", problem)
    parameters = spec.get("parameters")
    v.check("selected_parameters_object", isinstance(parameters, dict), "Top-level selected parameters object is required.")
    if not isinstance(parameters, dict):
        parameters = {}
    for name, value in parameters.items():
        if name not in domains:
            v.error("parameter_domain_declared", f"Selected parameter {name} is absent from case domains.")
        else:
            for problem in domain_errors(name, value, domains[name]):
                v.error("parameter_decimal_domain", problem)
    resources = spec.get("resources") or {}
    equipment = resources.get("equipment") or []
    materials = resources.get("materials") or []
    equipment_ids = [item.get("id") for item in equipment if isinstance(item, dict)]
    material_ids = [item.get("id") for item in materials if isinstance(item, dict)]
    v.check("unique_equipment_ids", len(equipment_ids) == len(set(equipment_ids)) and all(equipment_ids), "Equipment IDs must be unique and nonempty.")
    v.check("unique_material_ids", len(material_ids) == len(set(material_ids)) and all(material_ids), "Material IDs must be unique and nonempty.")
    known_equipment = set(equipment_ids)
    known_materials = set(material_ids)
    resource_register = build_resource_register(case)
    if resource_register["contract_present"]:
        for problem in resource_register["errors"]:
            v.error("contract_resource_register", problem)
        for conflict in resource_register["conflicts"]:
            v.error("contract_resource_conflict", json.dumps(conflict, ensure_ascii=False, sort_keys=True, default=json_default))
        allowed_equipment = set(resource_register["known_ids"]["equipment"])
        allowed_materials = set(resource_register["known_ids"]["materials"])
        for resource_id in equipment_ids:
            if resource_id not in allowed_equipment:
                v.error("spec_equipment_in_actual_contract", f"Unknown equipment {resource_id!r}; known actual contract/note IDs: {sorted(allowed_equipment)}.")
        for resource_id in material_ids:
            if resource_id not in allowed_materials:
                v.error("spec_material_in_actual_contract", f"Unknown material {resource_id!r}; known actual contract IDs: {sorted(allowed_materials)}.")

    states = spec.get("states")
    v.check("states_list", isinstance(states, list) and bool(states), "At least one state is required.")
    if not isinstance(states, list):
        states = []
    ids = [state.get("id") for state in states if isinstance(state, dict)]
    v.check("unique_state_ids", len(ids) == len(set(ids)) and all(isinstance(item, str) and item for item in ids), "Every state needs a unique nonempty string ID.")
    by_id = {state.get("id"): state for state in states if isinstance(state, dict) and isinstance(state.get("id"), str)}
    starts = [state for state in states if isinstance(state, dict) and state.get("kind") == "start"]
    v.check("exactly_one_start", len(starts) == 1, f"Found {len(starts)} start states.")
    for state in states:
        if not isinstance(state, dict):
            v.error("state_object", "Every state must be an object.")
            continue
        sid = state.get("id", "<missing>")
        kind = state.get("kind")
        if kind not in {"start", "action", "decision", "terminal"}:
            v.error("state_kind", f"{sid}: unsupported kind {kind!r}.")
        try:
            duration = decimal_value(state.get("duration_minutes"), f"{sid}.duration_minutes")
            cost = decimal_value(state.get("cost"), f"{sid}.cost")
            if duration < 0 or cost < 0:
                raise InputError(f"{sid}: duration and cost must be nonnegative.")
        except (InputError, InvalidOperation) as exc:
            v.error("state_exact_duration_cost", str(exc))
        max_visits = state.get("max_visits", 1)
        if isinstance(max_visits, bool) or not isinstance(max_visits, int) or max_visits < 1:
            v.error("state_max_visits", f"{sid}: max_visits must be an integer >= 1.")
        for resource_id in state.get("equipment") or []:
            if resource_id not in known_equipment:
                v.error("state_known_equipment", f"{sid}: unknown equipment {resource_id!r}.")
        for resource_id in state.get("materials") or []:
            if resource_id not in known_materials:
                v.error("state_known_material", f"{sid}: unknown material {resource_id!r}.")
        for name, value in (state.get("parameters") or {}).items():
            if name not in domains:
                v.error("state_parameter_domain", f"{sid}: parameter {name} is absent from case domains.")
            else:
                for problem in domain_errors(name, value, domains[name]):
                    v.error("state_parameter_decimal_domain", f"{sid}: {problem}")
        if kind in {"start", "action"} and not state.get("next"):
            v.error("nonterminal_outgoing", f"{sid}: nonterminal state requires next.")
        if kind == "terminal":
            if state.get("outcome") not in TERMINAL_OUTCOMES:
                v.error("terminal_outcome", f"{sid}: terminal outcome must be success or failure.")
            if state.get("next") or state.get("branches") or state.get("else"):
                v.error("terminal_no_outgoing", f"{sid}: terminal states cannot have outgoing transitions.")
        if kind == "decision":
            branches = state.get("branches")
            if not isinstance(branches, list) or not branches:
                v.error("decision_branches", f"{sid}: decision requires non-empty branches.")
                branches = []
            labels = [branch.get("label") for branch in branches if isinstance(branch, dict)]
            if len(labels) != len(set(labels)) or "else" in labels:
                v.error("decision_unique_labels", f"{sid}: branch labels must be unique and cannot use reserved else.")
            for branch in branches:
                if not isinstance(branch, dict) or not branch.get("next"):
                    v.error("decision_branch_next", f"{sid}: every branch requires next.")
                    continue
                problem = guard_error(branch.get("guard"))
                if problem:
                    v.error("decision_observable_guard", f"{sid}/{branch.get('label')}: {problem}.")
            if not isinstance(state.get("else"), str) or not state.get("else"):
                v.error("decision_explicit_else", f"{sid}: every decision requires explicit non-empty else/default next state.")
    adjacency = {sid: outgoing(state) for sid, state in by_id.items()}
    for source, targets in adjacency.items():
        for target in targets:
            if target not in by_id:
                v.error("transition_known_target", f"{source}: unknown target {target!r}.")
    reachable = set()
    if len(starts) == 1 and starts[0].get("id") in by_id:
        pending = [starts[0]["id"]]
        while pending:
            node = pending.pop()
            if node in reachable:
                continue
            reachable.add(node)
            pending.extend(target for target in adjacency.get(node, []) if target in by_id)
        unreachable = sorted(set(by_id) - reachable)
        v.check("no_unreachable_states", not unreachable, f"Unreachable states: {unreachable}.")
        success = sorted(sid for sid in reachable if by_id[sid].get("kind") == "terminal" and by_id[sid].get("outcome") == "success")
        failure = sorted(sid for sid in reachable if by_id[sid].get("kind") == "terminal" and by_id[sid].get("outcome") == "failure")
        v.check("success_terminal_reachable", bool(success), f"Reachable success terminals: {success}.")
        v.check("failure_terminal_reachable", bool(failure), f"Reachable failure terminals: {failure}.")
    else:
        reachable = set()
    components = tarjan(list(by_id), adjacency)
    cyclic_components = []
    for component in components:
        members = set(component)
        cyclic = len(component) > 1 or any(node in adjacency.get(node, []) for node in component)
        if cyclic:
            cyclic_components.append(component)
            exits = sorted({target for node in component for target in adjacency.get(node, []) if target not in members and target in by_id})
            v.check("cycle_has_exit", bool(exits), f"Cycle {sorted(component)} has exits {exits}.")
            unbounded = sorted(node for node in component if "max_visits" not in by_id[node])
            v.check("cycle_explicit_bounded_retry", not unbounded, f"Cycle {sorted(component)} states missing explicit max_visits: {unbounded}.")
    settings = spec.get("settings") or {}
    cap = settings.get("global_step_cap")
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
        v.error("global_step_cap", "settings.global_step_cap must be an integer >= 1.")
    decisions = {sid: state for sid, state in by_id.items() if state.get("kind") == "decision"}
    scenarios = spec.get("scenarios")
    v.check("scenarios_list", isinstance(scenarios, list) and bool(scenarios), "At least nominal scenario is required.")
    if not isinstance(scenarios, list):
        scenarios = []
    nominal = [item for item in scenarios if isinstance(item, dict) and item.get("scenario_id") == "nominal"]
    v.check("nominal_scenario", len(nominal) == 1, f"Expected exactly one nominal scenario; found {len(nominal)}.")
    scenario_ids = [item.get("scenario_id") for item in scenarios if isinstance(item, dict)]
    v.check("unique_scenario_ids", len(scenario_ids) == len(set(scenario_ids)) and all(scenario_ids), "Scenario IDs must be unique and nonempty.")
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            v.error("scenario_object", "Every scenario must be an object.")
            continue
        if scenario.get("outcome_basis") != "synthetic_what_if":
            v.error("scenario_hypothesis_label", f"{scenario.get('scenario_id')}: outcome_basis must be synthetic_what_if.")
        outcome_map = scenario.get("decision_outcomes")
        if not isinstance(outcome_map, dict):
            v.error("scenario_outcome_map", f"{scenario.get('scenario_id')}: decision_outcomes object is required.")
            continue
        for decision_id, labels in outcome_map.items():
            if decision_id not in decisions:
                v.error("scenario_known_decision", f"{scenario.get('scenario_id')}: unknown decision {decision_id}.")
                continue
            if not isinstance(labels, list) or not labels or not all(isinstance(label, str) for label in labels):
                v.error("scenario_outcome_list", f"{scenario.get('scenario_id')}/{decision_id}: outcomes must be nonempty string list.")
                continue
            valid = {branch.get("label") for branch in decisions[decision_id].get("branches") or []} | {"else"}
            for label in labels:
                if label not in valid:
                    v.error("scenario_known_branch", f"{scenario.get('scenario_id')}/{decision_id}: unknown branch label {label!r}.")
    info = {
        "by_id": by_id,
        "adjacency": adjacency,
        "reachable": reachable,
        "cyclic_components": cyclic_components,
        "decisions": decisions,
        "scenarios": scenarios,
        "domains": domains,
        "resource_register": resource_register,
    }
    return v, info


def simulate_scenario(spec, info, scenario):
    by_id = info["by_id"]
    start = next(state["id"] for state in spec["states"] if state.get("kind") == "start")
    cap = spec["settings"]["global_step_cap"]
    current = start
    visits = {}
    events = []
    path = []
    total_cost = Decimal(0)
    total_duration = Decimal(0)
    termination = None
    terminal = None
    while True:
        steps = sum(visits.values())
        if steps >= cap:
            termination = {"type": "detected_failure", "reason": f"Global step cap {cap} reached before entering {current}."}
            events.append({"event": "detected_failure", "reason": termination["reason"], "state_id": current})
            break
        state = by_id[current]
        count = visits.get(current, 0) + 1
        max_visits = state.get("max_visits", 1)
        if count > max_visits:
            termination = {"type": "detected_failure", "reason": f"State {current} exceeded max_visits {max_visits}."}
            events.append({"event": "detected_failure", "reason": termination["reason"], "state_id": current, "attempted_visit": count})
            break
        visits[current] = count
        path.append(current)
        state_cost = decimal_value(state.get("cost", "0"))
        state_duration = decimal_value(state.get("duration_minutes", "0"))
        total_cost += state_cost
        total_duration += state_duration
        events.append({
            "event": "state_visit", "step": steps + 1, "state_id": current, "visit": count,
            "state_cost": decimal_text(state_cost), "state_duration_minutes": decimal_text(state_duration),
            "cumulative_cost": decimal_text(total_cost), "cumulative_duration_minutes": decimal_text(total_duration),
        })
        if state.get("kind") == "terminal":
            terminal = current
            termination = {"type": "explicit_terminal", "outcome": state.get("outcome"), "terminal_id": current}
            events.append({"event": "terminal", "state_id": current, "outcome": state.get("outcome")})
            break
        if state.get("kind") == "decision":
            outcomes = scenario["decision_outcomes"].get(current, [])
            outcome_index = count - 1
            if outcome_index >= len(outcomes):
                termination = {"type": "detected_failure", "reason": f"Scenario {scenario['scenario_id']} supplied no outcome for decision {current}, visit {count}."}
                events.append({"event": "detected_failure", "reason": termination["reason"], "state_id": current})
                break
            label = outcomes[outcome_index]
            if label == "else":
                target = state.get("else")
                guard = None
            else:
                branch = next((item for item in state.get("branches") or [] if item.get("label") == label), None)
                if branch is None:
                    termination = {"type": "detected_failure", "reason": f"Unknown injected branch {label!r} at {current}."}
                    events.append({"event": "detected_failure", "reason": termination["reason"], "state_id": current})
                    break
                target = branch.get("next")
                guard = branch.get("guard")
            events.append({
                "event": "decision", "state_id": current, "visit": count, "selected_label": label,
                "guard": guard, "next": target, "outcome_basis": "injected_planning_hypothesis_not_measurement",
            })
            current = target
        else:
            current = state.get("next")
        if current not in by_id:
            termination = {"type": "detected_failure", "reason": f"Transition target {current!r} is unknown."}
            events.append({"event": "detected_failure", "reason": termination["reason"]})
            break
    return {
        "scenario_id": scenario["scenario_id"],
        "description": scenario.get("description", ""),
        "fault_injection": scenario.get("fault_injection"),
        "outcome_basis": "synthetic_what_if_all_outcomes_unmeasured",
        "path": path,
        "events": events,
        "state_visits": visits,
        "totals": {"duration_minutes": decimal_text(total_duration), "cost": decimal_text(total_cost), "state_visits": sum(visits.values())},
        "terminal_id": terminal,
        "termination": termination,
    }


def branch_coverage(spec, results):
    all_edges = set()
    for state in spec.get("states") or []:
        if state.get("kind") == "decision":
            for branch in state.get("branches") or []:
                all_edges.add((state["id"], branch.get("label")))
            all_edges.add((state["id"], "else"))
    tested = set()
    for result in results:
        for event in result["events"]:
            if event["event"] == "decision":
                tested.add((event["state_id"], event["selected_label"]))
    return {
        "tested_decision_branches": [{"decision_id": sid, "label": label} for sid, label in sorted(tested)],
        "untested_decision_branches": [{"decision_id": sid, "label": label} for sid, label in sorted(all_edges - tested)],
        "complete": all_edges == tested,
        "interpretation": "Coverage means an injected planning path selected a branch; it is not experimental evidence.",
    }


def conservative_bound(spec, info):
    cost = Decimal(0)
    duration = Decimal(0)
    state_bounds = {}
    for sid in sorted(info["reachable"]):
        state = info["by_id"][sid]
        visits = state.get("max_visits", 1)
        state_cost = decimal_value(state.get("cost", "0")) * visits
        state_duration = decimal_value(state.get("duration_minutes", "0")) * visits
        cost += state_cost
        duration += state_duration
        state_bounds[sid] = {"max_visits": visits, "cost": decimal_text(state_cost), "duration_minutes": decimal_text(state_duration)}
    return {
        "cost": decimal_text(cost), "duration_minutes": decimal_text(duration),
        "max_state_entries": sum(info["by_id"][sid].get("max_visits", 1) for sid in info["reachable"]),
        "per_state": state_bounds,
        "method": "Conservative sum over every reachable state of max_visits times exact state cost/duration; may include mutually exclusive terminals, so it is a safe upper bound, not a claimed attainable path.",
    }


def budget_envelope_audit(case, envelope):
    limits = budget_settings(case)
    result = {
        "currency": limits["currency"], "prospective": True,
        "calendar_confirmation_required": limits["deadline_days"] is not None,
        "calendar_note": "For deadline_days, conservative graph minutes are divided by 1440 for an elapsed-time comparison only; equipment booking windows, queues and calendar time may be longer and require confirmation.",
    }
    if limits["max_cost"] is not None:
        maximum = decimal_value(limits["max_cost"], "resource_contract.budget_cap")
        actual = decimal_value(envelope["conservative_graph_upper_bound"]["cost"])
        result["cost"] = {"limit": decimal_text(maximum), "upper_bound": decimal_text(actual), "within": actual <= maximum, "currency": limits["currency"]}
    actual_minutes = decimal_value(envelope["conservative_graph_upper_bound"]["duration_minutes"])
    if limits["deadline_days"] is not None:
        maximum_days = decimal_value(limits["deadline_days"], "resource_contract.deadline_days")
        result["deadline"] = {
            "unit": "days",
            "limit_days": decimal_text(maximum_days),
            "upper_bound_minutes": decimal_text(actual_minutes),
            "upper_bound_days": decimal_text(actual_minutes / Decimal(1440)),
            "comparison_basis": "Compare graph minutes with deadline_days * 1440; no minutes are inferred for candidate est_days.",
            "conversion": "elapsed_days = graph_duration_minutes / 1440",
            "within": actual_minutes <= maximum_days * Decimal(1440),
            "booking_calendar_time_may_be_longer": True,
            "confirmation_required": True,
        }
    elif limits["deadline_minutes"] is not None:
        maximum_minutes = decimal_value(limits["deadline_minutes"], "budget.deadline_minutes")
        result["deadline"] = {
            "unit": "minutes", "limit_minutes": decimal_text(maximum_minutes),
            "upper_bound_minutes": decimal_text(actual_minutes), "within": actual_minutes <= maximum_minutes,
        }
    return result


def make_simulation(case, spec, info, v):
    results = [simulate_scenario(spec, info, scenario) for scenario in info["scenarios"]]
    coverage = branch_coverage(spec, results)
    for result in results:
        if result["termination"]["type"] != "explicit_terminal":
            v.error("scenario_termination", f"{result['scenario_id']}: {result['termination']['reason']}")
    if coverage["untested_decision_branches"]:
        v.warn("decision_branch_scenario_coverage", f"Untested branch labels: {coverage['untested_decision_branches']}; result must be partial.")
    nominal_result = next(item for item in results if item["scenario_id"] == "nominal")
    scenario_max_cost = max((decimal_value(item["totals"]["cost"]) for item in results), default=Decimal(0))
    scenario_max_duration = max((decimal_value(item["totals"]["duration_minutes"]) for item in results), default=Decimal(0))
    bound = conservative_bound(spec, info)
    envelope = {
        "nominal": nominal_result["totals"],
        "worst_case_supplied_scenario_envelope": {
            "max_cost": decimal_text(scenario_max_cost), "max_duration_minutes": decimal_text(scenario_max_duration),
            "note": "Max cost and max duration are component-wise maxima over supplied scenarios and need not belong to one path.",
        },
        "conservative_graph_upper_bound": bound,
        "currency": budget_settings(case)["currency"],
        "measured": False,
    }
    budget_audit = budget_envelope_audit(case, envelope)
    if budget_audit.get("cost", {}).get("within") is False:
        v.error("worst_case_cost_budget", "Conservative graph upper bound exceeds case cost budget.")
    if budget_audit.get("deadline", {}).get("within") is False:
        v.error("worst_case_deadline", "Conservative graph upper bound exceeds case deadline.")
    return {
        "output_notice": output_notice(case),
        "case_id": case_identifier(case),
        "protocol_id": spec.get("protocol_id"),
        "simulation_type": "deterministic_structured_fault_injection",
        "outcome_warning": "All branch labels and injected outcomes are planning hypotheses. No scenario is a measured experimental outcome.",
        "scenario_results": results,
        "decision_branch_coverage": coverage,
        "envelope": envelope,
        "budget_deadline_audit": budget_audit,
    }, envelope


def render_svg(case, spec, info):
    states = spec.get("states") or []
    width = 1200
    row_height = 105
    height = max(240, 110 + row_height * len(states))
    positions = {}
    for index, state in enumerate(states):
        failure = state.get("kind") == "terminal" and state.get("outcome") == "failure"
        x = 850 if failure else (610 if state.get("kind") == "decision" else 300)
        y = 100 + index * row_height
        positions[state.get("id")] = (x, y)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Protocol statechart">',
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#475569"/></marker></defs>',
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        f'<text x="30" y="35" font-family="sans-serif" font-size="20" font-weight="bold" fill="#0f172a">{html.escape(str(spec.get("title", "Protocol statechart")))}</text>',
        f'<text x="30" y="60" font-family="sans-serif" font-size="13" fill="#991b1b">{html.escape(output_notice(case))}；所有分支均为未实测假设</text>',
    ]
    edge_labels = {}
    for state in states:
        sid = state.get("id")
        if state.get("kind") == "decision":
            for branch in state.get("branches") or []:
                edge_labels[(sid, branch.get("next"), branch.get("label"))] = branch.get("label")
            edge_labels[(sid, state.get("else"), "else")] = "else/default"
    for state in states:
        source = state.get("id")
        if source not in positions:
            continue
        x1, y1 = positions[source]
        for target in outgoing(state):
            if target not in positions:
                continue
            x2, y2 = positions[target]
            label = ""
            if state.get("kind") == "decision":
                if target == state.get("else"):
                    label = "else/default"
                else:
                    matching = [branch.get("label") for branch in state.get("branches") or [] if branch.get("next") == target]
                    label = "/".join(matching)
            lines.append(f'<path d="M {x1} {y1 + 25} C {x1} {y1 + 65}, {x2} {y2 - 65}, {x2} {y2 - 25}" fill="none" stroke="#475569" stroke-width="1.6" marker-end="url(#arrow)"/>')
            if label:
                mx = (x1 + x2) / 2
                my = (y1 + y2) / 2
                lines.append(f'<text x="{mx}" y="{my}" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#7c2d12">{html.escape(str(label))}</text>')
    for state in states:
        sid = state.get("id")
        if sid not in positions:
            continue
        x, y = positions[sid]
        kind = state.get("kind")
        if kind == "decision":
            points = f"{x},{y-32} {x+145},{y} {x},{y+32} {x-145},{y}"
            lines.append(f'<polygon points="{points}" fill="#fef3c7" stroke="#b45309" stroke-width="2"/>')
        else:
            fill = "#dcfce7" if state.get("outcome") == "success" else ("#fee2e2" if kind == "terminal" else "#dbeafe")
            if kind == "start":
                fill = "#e0e7ff"
            lines.append(f'<rect x="{x-135}" y="{y-27}" width="270" height="54" rx="10" fill="{fill}" stroke="#334155" stroke-width="1.7"/>')
        lines.append(f'<text x="{x}" y="{y-3}" text-anchor="middle" font-family="monospace" font-size="14" font-weight="bold" fill="#0f172a">{html.escape(str(sid))}</text>')
        caption = f"{kind}; {state.get('duration_minutes', '?')} min; cost {state.get('cost', '?')}; max {state.get('max_visits', 1)}"
        lines.append(f'<text x="{x}" y="{y+16}" text-anchor="middle" font-family="sans-serif" font-size="11" fill="#334155">{html.escape(caption)}</text>')
    lines.append('</svg>')
    return "\n".join(lines)


def format_value(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=json_default)
    return str(value)


def render_plan_md(case, spec, simulation, candidate_assessment):
    scientific = spec.get("scientific_plan") or {}
    lines = [
        f"# {spec.get('title', 'Experimental protocol')}", "",
        f"> {output_notice(case)}。所有情景均为可执行流程的假设推演，未开展实测实验；成本/期为前瞻性规划值，不是报价、预约或批准。", "",
        f"- Case: `{case_identifier(case)}`", f"- Protocol: `{spec.get('protocol_id')}`",
        f"- Schema: `{spec.get('schema_version')}`", "",
        "## 可证伪假设", "",
    ]
    for item in scientific.get("hypotheses") or []:
        lines.append(f"- **{item.get('id')}**：{item.get('statement')} **证伪条件**：{item.get('falsification')}")
    lines.extend(["", "## 变量、参数与控制", "", "### 变量", "", "```json", json.dumps(scientific.get("variables") or {}, ensure_ascii=False, indent=2, default=json_default), "```", "", "### 有限域内选定参数", "", "| 参数 | 值 |", "|---|---|"])
    for name, value in sorted((spec.get("parameters") or {}).items()):
        lines.append(f"| {name} | {format_value(value)} |")
    lines.extend(["", "### 控制", ""])
    for item in scientific.get("controls") or []:
        lines.append(f"- {format_value(item)}")
    lines.extend(["", "## 材料与设备（规划绑定）", "", "| 类型 | ID | 名称 | 数量/规格 |", "|---|---|---|---|"])
    resources = spec.get("resources") or {}
    for item in resources.get("equipment") or []:
        lines.append(f"| 设备 | {item.get('id')} | {item.get('name')} | {format_value(item.get('specification', '按SOP确认'))} |")
    for item in resources.get("materials") or []:
        lines.append(f"| 材料 | {item.get('id')} | {item.get('name')} | {item.get('quantity', '?')} {item.get('unit', '')}；成本 {item.get('cost', '?')} |")
    lines.extend(["", "## 状态化操作程序与 QC 守卫", "", "| 状态 | 类型 | 时长 min | 成本 | 最大访问 | 后继/分支 |", "|---|---|---:|---:|---:|---|"])
    for state in spec.get("states") or []:
        if state.get("kind") == "decision":
            targets = [f"{branch.get('label')}→{branch.get('next')}" for branch in state.get("branches") or []]
            targets.append(f"else→{state.get('else')}")
        elif state.get("kind") == "terminal":
            targets = [f"terminal:{state.get('outcome')}"]
        else:
            targets = [str(state.get("next"))]
        lines.append(f"| {state.get('id')} | {state.get('kind')} | {state.get('duration_minutes')} | {state.get('cost')} | {state.get('max_visits', 1)} | {'; '.join(targets)} |")
    lines.extend(["", "### 决策观测记录", ""])
    for state in spec.get("states") or []:
        if state.get("kind") != "decision":
            continue
        for branch in state.get("branches") or []:
            guard = branch["guard"]
            lines.append(f"- `{state['id']}/{branch['label']}`：`{guard['metric']} {guard['operator']} {guard['threshold']} {guard['unit']}`，记录于 `{guard['record']}`；缺省分支为 `{state.get('else', '<MISSING>')}`。")
    lines.extend(["", "## 验收标准", ""])
    for item in scientific.get("acceptance_criteria") or []:
        lines.append(f"- {format_value(item)}")
    lines.extend(["", "## 候选方案审计", ""])
    for audit in candidate_assessment:
        lines.append(f"- `{audit['candidate_id']}`：{audit['assessment']}；" + ("；".join(audit["errors"]) if audit["errors"] else "未发现算术/域错误，仍需科学审查。"))
    if simulation and simulation.get("envelope"):
        envelope = simulation["envelope"]
        lines.extend(["", "## 路径成本与时间包络（非实测）", "", f"- Nominal：{envelope['nominal']['duration_minutes']} min，成本 {envelope['nominal']['cost']}。", f"- 已给情景逐分量最大值：{envelope['worst_case_supplied_scenario_envelope']['max_duration_minutes']} min，成本 {envelope['worst_case_supplied_scenario_envelope']['max_cost']}。", f"- 有界图保守上界：{envelope['conservative_graph_upper_bound']['duration_minutes']} min，成本 {envelope['conservative_graph_upper_bound']['cost']}。", f"- 解释：{envelope['conservative_graph_upper_bound']['method']}"])
    lines.extend(["", "## 风险与修订", ""])
    for item in scientific.get("risk_and_revisions") or []:
        lines.append(f"- {format_value(item)}")
    lines.extend(["", "## 规划证据与限制", "", "以下仅为方案内证据/假设登记，不构成外部科学结论或实测结果：", ""])
    for item in scientific.get("planning_evidence") or []:
        lines.append(f"- {format_value(item)}")
    lines.extend(["", "## 专家确认边界", "", "实际执行前必须由方法负责人确认仪器 SOP、试剂适用性、校准/QC 标准、安全处置、真实资源价格与可用性。状态图编译和仿真通过不等于科学有效性、安全性或实验成功。", ""])
    return "\n".join(lines)


def render_path_report(case, simulation):
    lines = ["# 路径仿真与覆盖报告", "", f"> {output_notice(case)}；以下均为 `synthetic_what_if`，不是实测结局。", "", "| 情景 | 路径 | 终止 | 访问数 | 时长 min | 成本 |", "|---|---|---|---:|---:|---:|"]
    for result in simulation["scenario_results"]:
        termination = result["termination"]
        label = termination.get("terminal_id") or termination["type"]
        lines.append(f"| {result['scenario_id']} | {' → '.join(result['path'])} | {label} | {result['totals']['state_visits']} | {result['totals']['duration_minutes']} | {result['totals']['cost']} |")
    lines.extend(["", "## 已覆盖判分支", ""])
    for item in simulation["decision_branch_coverage"]["tested_decision_branches"]:
        lines.append(f"- `{item['decision_id']}/{item['label']}`（仅为注入路径覆盖）")
    lines.extend(["", "## 未覆盖判分支", ""])
    untested = simulation["decision_branch_coverage"]["untested_decision_branches"]
    if untested:
        for item in untested:
            lines.append(f"- `{item['decision_id']}/{item['label']}`")
    else:
        lines.append("- 无（仅限已声明的决策分支；不表示科学或实测覆盖）。")
    lines.extend(["", "## 有界性", "", simulation["envelope"]["conservative_graph_upper_bound"]["method"], f"全局步数上限：`{simulation['envelope']['conservative_graph_upper_bound']['max_state_entries']}` 为按状态访问界之和；仿真另有规格中的 global_step_cap 硬停止。越界会成为 detected_failure，不会被静默忽略。", ""])
    return "\n".join(lines)


def empty_simulation(case, spec, reason):
    return {
        "output_notice": output_notice(case), "case_id": case_identifier(case), "protocol_id": spec.get("protocol_id"),
        "simulation_type": "not_run_due_to_validation_failure", "outcome_warning": "No valid scenario simulation was produced; no outcomes are measured.",
        "scenario_results": [], "decision_branch_coverage": branch_coverage(spec, []),
        "envelope": None, "reason": reason,
    }


def result_aliases(common):
    aliases = dict(common)
    aliases.update({
        "case_id": common["case_id"], "plan": common["revised_plan"], "protocol": common["revised_plan"],
        "hypotheses": common["revised_plan"]["hypotheses"], "variables": common["revised_plan"]["variables"],
        "controls": common["revised_plan"]["controls"], "materials": common["revised_plan"]["materials"],
        "procedures": common["revised_plan"]["procedures"], "parameters": common["revised_plan"]["parameters"],
        "acceptance_criteria": common["revised_plan"]["acceptance_criteria"],
        "risks": common["revised_plan"]["risk_and_revisions"], "risk_and_revisions": common["revised_plan"]["risk_and_revisions"],
        "costs": common["revised_plan"]["cost_time_envelope"], "time": common["revised_plan"]["cost_time_envelope"],
        "cost_time": common["revised_plan"]["cost_time_envelope"], "simulation": common["simulation_summary"],
        "statechart": common["revised_plan"]["statechart"], "candidate_plans": common["candidate_assessment"],
    })
    return aliases


def authored_entries(spec, key):
    value = spec.get(key, [])
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def compile_result(case, spec, status, validation_document, simulation, audits, sources, unknown):
    scientific = spec.get("scientific_plan") or {}
    envelope = simulation.get("envelope") if simulation else None
    revisions = authored_entries(spec, "candidate_revisions")
    audited_candidates = []
    for audit in audits:
        linked = [revision for revision in revisions if isinstance(revision, dict) and str(
            revision.get("candidate_id") or revision.get("version") or revision.get("id") or ""
        ) == str(audit.get("candidate_id"))]
        enriched_audit = dict(audit)
        enriched_audit["revision_records"] = linked
        audited_candidates.append(enriched_audit)
    common = {
        "case_id": case_identifier(case),
        "revised_plan": {
            "protocol_id": spec.get("protocol_id"), "title": spec.get("title"),
            "hypotheses": scientific.get("hypotheses") or [], "variables": scientific.get("variables") or {},
            "controls": scientific.get("controls") or [], "materials": spec.get("resources") or {},
            "parameters": spec.get("parameters") or {}, "procedures": spec.get("states") or [],
            "acceptance_criteria": scientific.get("acceptance_criteria") or [],
            "risk_and_revisions": scientific.get("risk_and_revisions") or [],
            "planning_evidence": scientific.get("planning_evidence") or [],
            "candidate_revisions": revisions,
            "statechart": {"file": "statechart.svg", "state_count": len(spec.get("states") or [])},
            "cost_time_envelope": envelope,
            "prospective_not_quote_or_approval": True,
        },
        "candidate_assessment": audited_candidates,
        "candidate_revisions": revisions,
        "validation": {
            "status": validation_document["status"], "errors": validation_document["errors"], "warnings": validation_document["warnings"],
            "branch_coverage": validation_document.get("decision_branch_coverage"),
            "files": ["plan.json", "plan.md", "validation.json", "simulation.json", "statechart.svg", "path_report.md"],
        },
        "status": status,
        "uncertainty": [
            "All scenario labels and fault injections are unmeasured planning hypotheses.",
            "Graph/static validation does not establish scientific validity, safety, or experimental success.",
        ] + validation_document["warnings"] + authored_entries(spec, "uncertainty"),
        "sources": sources,
        "change_log": [
            "Replaced bootstrap placeholder with agent-authored protocol statechart.",
            "Audited graph, domains, Decimal costs, resource bindings, terminals and bounded cycles.",
            "Executed deterministic nominal/fault-injection what-if scenarios; no measured experiment was run.",
        ] + authored_entries(spec, "change_log"),
        "confirmation_items": [
            "Method owner must confirm scientific suitability, calibration/QC limits and instrument/reagent SOPs.",
            "Safety officer must confirm hazards, waste handling and fail-safe actions before wet execution.",
            "Resource owner must confirm actual availability, prices and schedule; planning values are not quotes or bookings.",
            "For deadline_days, minutes/1440 is an elapsed-time comparison only; booking/calendar time may be longer and requires confirmation.",
        ] + authored_entries(spec, "confirmation_items"),
        "simulation_summary": {"file": "simulation.json", "scenario_count": len(simulation.get("scenario_results") or []), "measured": False},
    }
    result = {
        "case_id": case_identifier(case), "output_notice": output_notice(case), "status": status,
        "completion_scope": "planning_artifacts_and_simulation_only_not_experimental_validation",
        "output_contract_unknown_fields": unknown,
        "simulation_interpretation": "Synthetic what-if paths only; injected outcomes and branch labels are hypotheses, never measured outcomes.",
        "prospective_notice": "Resource/cost/deadline values are planning estimates, not quotes, bookings, approvals, or commitments.",
    }
    aliases = result_aliases(common)
    for field in required_fields(case):
        if field in aliases:
            result[field] = aliases[field]
        else:
            result[field] = {"partial": True, "field": field, "reason": "No validated dynamic mapping exists for this required field; author review is required."}
            if field not in unknown:
                unknown.append(field)
    for key, value in common.items():
        result.setdefault(key, value)
    return result


def command_compile(args):
    case = load_json(args.case)
    task = read_task(args.task)
    materials, material_warnings = read_materials(args.materials_dir, (args.case, args.task))
    work, output = output_paths(args)
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    spec = load_json(args.spec)
    notice = output_notice(case)
    audits = candidate_audits(case)
    sources = source_records(args.case, task, materials, args.spec, spec)
    # Preserve a valid early partial before any graph/simulation work.
    early = bootstrap_result(case, "partial", audits, sources, material_warnings, notice)
    early["uncertainty"].extend(authored_entries(spec, "uncertainty"))
    early["change_log"] = ["Compile started; this early partial remains if processing is interrupted."] + authored_entries(spec, "change_log")
    early["confirmation_items"].extend(authored_entries(spec, "confirmation_items"))
    early["candidate_revisions"] = authored_entries(spec, "candidate_revisions")
    write_json(output / "result.json", early)

    v, info = validate_spec(case, spec)
    for warning in material_warnings:
        v.warn("material_extraction_limitation", warning)
    simulation = None
    envelope = None
    if not v.errors:
        simulation, envelope = make_simulation(case, spec, info, v)
    else:
        simulation = empty_simulation(case, spec, "Spec validation failed; simulation skipped to avoid implying invalid paths were tested.")
    status = "partial" if v.errors or v.warnings else "complete"
    validation_document = {
        "output_notice": notice, "case_id": case_identifier(case), "protocol_id": spec.get("protocol_id"),
        "status": "fail" if v.errors else ("pass_with_warnings" if v.warnings else "pass"),
        "errors": v.errors, "warnings": v.warnings, "checks": v.checks,
        "graph": {
            "state_count": len(info["by_id"]), "reachable_state_count": len(info["reachable"]),
            "cyclic_components": [sorted(component) for component in info["cyclic_components"]],
            "decision_count": len(info["decisions"]),
            "terminal_success_ids": sorted(sid for sid in info["reachable"] if info["by_id"][sid].get("kind") == "terminal" and info["by_id"][sid].get("outcome") == "success"),
            "terminal_failure_ids": sorted(sid for sid in info["reachable"] if info["by_id"][sid].get("kind") == "terminal" and info["by_id"][sid].get("outcome") == "failure"),
        },
        "candidate_assessment": audits,
        "resource_register": info["resource_register"],
        "decision_branch_coverage": simulation.get("decision_branch_coverage"),
        "budget_deadline_audit": simulation.get("budget_deadline_audit") if simulation else None,
        "interpretation": "Pass verifies machine-checkable planning properties only. Injected scenario branches are hypotheses and not experimental measurements.",
    }
    plan = {
        "output_notice": notice, "case_id": case_identifier(case), "protocol_id": spec.get("protocol_id"),
        "title": spec.get("title"), "outcome_status": spec.get("outcome_status"),
        "parameters": spec.get("parameters") or {}, "scientific_plan": spec.get("scientific_plan") or {},
        "resources": spec.get("resources") or {}, "settings": spec.get("settings") or {},
        "states": spec.get("states") or [], "scenarios": spec.get("scenarios") or [],
        "candidate_revisions": authored_entries(spec, "candidate_revisions"),
        "uncertainty": authored_entries(spec, "uncertainty"),
        "change_log": authored_entries(spec, "change_log"),
        "confirmation_items": authored_entries(spec, "confirmation_items"),
        "cost_time_envelope": envelope,
        "interpretation": "Full experimental plan and executable decision graph. Costs/times are prospective; all simulations are unmeasured.",
    }
    write_json(output / "plan.json", plan)
    write_text(output / "plan.md", render_plan_md(case, spec, simulation, audits))
    write_json(output / "validation.json", validation_document)
    write_json(output / "simulation.json", simulation)
    write_text(output / "statechart.svg", render_svg(case, spec, info))
    write_text(output / "path_report.md", render_path_report(case, simulation) if simulation.get("scenario_results") else f"# 路径报告\n\n{notice}\n\n验证失败，未运行仿真：{'; '.join(v.errors)}")
    unknown = []
    result = compile_result(case, spec, status, validation_document, simulation, audits, sources, unknown)
    if unknown:
        result["status"] = "partial"
        status = "partial"
        result["uncertainty"].append(f"Unmapped output_contract.required_fields: {unknown}.")
        validation_document["warnings"].append(f"Unknown dynamic required fields left explicitly partial: {unknown}.")
        validation_document["status"] = "pass_with_warnings" if not v.errors else "fail"
        result["validation"]["warnings"] = validation_document["warnings"]
        result["validation"]["status"] = validation_document["status"]
        write_json(output / "validation.json", validation_document)
    write_json(output / "result.json", result)
    print(f"compile: status={status}, validation={validation_document['status']}, errors={len(v.errors)}, warnings={len(validation_document['warnings'])}")
    print(f"compile: outputs written to {output}")
    return 2 if v.errors else 0


def emergency_result(args, error, unexpected=False):
    output = Path(getattr(args, "output_dir", "/app/output"))
    try:
        case = load_json(args.case)
    except Exception:
        case = {"case_id": "unknown_case", "output_contract": {"required_fields": []}}
    status = "partial" if unexpected and getattr(args, "command", "") == "compile" else "blocked"
    result = bootstrap_result(case, status, [], [], [str(error)], output_notice(case))
    result["completion_scope"] = "partial_after_unexpected_compile_failure" if status == "partial" else "blocked_before_valid_compilation"
    write_json(output / "result.json", result)
    print(f"error: {error}", file=sys.stderr)


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    for name, help_text in (("bootstrap", "Read actual inputs, audit candidates, write template and early partial."), ("compile", "Validate one protocol spec, compile artifacts and simulate scenarios.")):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--case", default="/input/case.json")
        command.add_argument("--task", default="/input/task.md")
        command.add_argument("--materials-dir", default="/input", help="Material discovery root; direct PDFs/text are included and exact case/task paths are excluded.")
        command.add_argument("--work-dir", default="/app/work")
        command.add_argument("--output-dir", default="/app/output")
        if name == "compile":
            command.add_argument("--spec", default="/app/work/protocol_spec.json")
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "bootstrap":
            return command_bootstrap(args)
        if args.command == "compile":
            return command_compile(args)
        raise InputError(f"unknown command {args.command}")
    except (InputError, InvalidOperation, OSError, subprocess.SubprocessError) as exc:
        try:
            emergency_result(args, exc)
        except Exception as nested:
            print(f"error: {exc}; additionally could not write result.json: {nested}", file=sys.stderr)
        return 2
    except Exception as exc:
        try:
            emergency_result(args, exc, unexpected=True)
        except Exception as nested:
            print(f"error: {exc}; additionally could not write result.json: {nested}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
