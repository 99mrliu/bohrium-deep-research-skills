#!/usr/bin/env python3
"""Deterministic causal-contrast inspection and experiment-plan compilation.

Python 3 standard library only. Scientific failures produce honest partial artifacts;
malformed CLI invocations are handled by argparse and return nonzero.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from decimal import Decimal, InvalidOperation
from typing import Any

GENERATOR = "causal_contrast.py/1.1"
SYNTHETIC_HEADER = "合成示例输出，非正式测评结果"
PROSPECTIVE_NOTICE = "前瞻性实验方案与机器校验输出；不是实测实验结果"
COMMON_FIELDS = [
    "revised_plan", "candidate_assessment", "validation", "status",
    "uncertainty", "sources", "change_log", "confirmation_items",
]


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_case(path: Path) -> tuple[dict[str, Any] | None, bytes, str | None]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            return None, raw, "case.json root must be an object"
        return value, raw, None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, b"", f"cannot read case.json: {exc}"


def decimal_value(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def decimal_text(value: Decimal) -> str:
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"


def required_fields(case: dict[str, Any]) -> list[str]:
    contract = case.get("output_contract", {})
    fields = contract.get("required_fields", []) if isinstance(contract, dict) else []
    return [x for x in fields if isinstance(x, str)] if isinstance(fields, list) else []


def missing_generator(field: str) -> dict[str, Any]:
    return {
        "status": "missing_generator",
        "value": None,
        "honest_partial": True,
        "reason": f"No deterministic generator is implemented for required field '{field}'.",
    }


def is_synthetic_case(case: dict[str, Any]) -> bool:
    if case.get("synthetic") is True:
        return True
    return any(isinstance(case.get(field), str) and "合成" in case[field] for field in ("case_kind", "scenario_label"))


def output_notice(case: dict[str, Any]) -> str:
    """Only explicitly labelled demonstrations receive the synthetic warning."""
    return SYNTHETIC_HEADER if is_synthetic_case(case) else PROSPECTIVE_NOTICE


def base_result(case: dict[str, Any], case_sha: str, stage: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "_header": output_notice(case),
        "_metadata": {"generator": GENERATOR, "case_sha256": case_sha, "stage": stage},
        "case_id": case.get("case_id", "unknown"),
        "status": "partial",
        "revised_plan": {"status": "not_generated", "reason": f"{stage} stage has no authored design yet."},
        "candidate_assessment": {"status": "not_run", "candidates": []},
        "validation": {"status": "FAIL", "errors": ["Design has not been compiled."], "warnings": []},
        "uncertainty": ["Scientific content is not yet confirmed; this is an early partial scaffold."],
        "sources": [],
        "change_log": [],
        "confirmation_items": ["An agent must author and compile design_spec.json."],
    }
    for field in required_fields(case):
        if field not in result:
            result[field] = missing_generator(field)
    return result


def blocked_result(case_id: str, message: str, output_dir: Path) -> dict[str, Any]:
    result = {
        "_header": PROSPECTIVE_NOTICE,
        "_metadata": {"generator": GENERATOR, "stage": "input_error"},
        "case_id": case_id,
        "status": "blocked",
        "revised_plan": {"status": "not_generated", "reason": message},
        "candidate_assessment": {"status": "not_run", "candidates": []},
        "validation": {"status": "FAIL", "errors": [message], "warnings": []},
        "uncertainty": ["The actual case input could not be parsed."],
        "sources": [], "change_log": [], "confirmation_items": ["Provide valid UTF-8 JSON input."],
    }
    dump(output_dir / "result.json", result)
    return result


def flatten_parameter_values(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def domain_violations(name: str, value: Any, domain: Any) -> list[str]:
    if not isinstance(domain, dict):
        return [f"{name}: declared parameter domain is not an object"]
    failures: list[str] = []
    for item in flatten_parameter_values(value):
        if domain.get("type") == "enum" or "enum" in domain or "values" in domain:
            allowed = domain.get("enum", domain.get("values", []))
            if not isinstance(allowed, list) or not allowed:
                failures.append(f"{name}: declared enum/values domain must be a nonempty list")
            elif item not in allowed:
                failures.append(f"{name}: {canonical(item)} is outside enum {canonical(allowed)}")
            continue
        number = decimal_value(item)
        if number is None:
            failures.append(f"{name}: {canonical(item)} is not a finite number")
            continue
        minimum = decimal_value(domain.get("min"))
        maximum = decimal_value(domain.get("max"))
        step = decimal_value(domain.get("step"))
        if minimum is not None and number < minimum:
            failures.append(f"{name}: {decimal_text(number)} is below min {decimal_text(minimum)}")
        if maximum is not None and number > maximum:
            failures.append(f"{name}: {decimal_text(number)} is above max {decimal_text(maximum)}")
        if step is not None:
            if step <= 0:
                failures.append(f"{name}: domain step must be positive")
            else:
                origin = minimum if minimum is not None else Decimal(0)
                quotient = (number - origin) / step
                if quotient != quotient.to_integral_value():
                    failures.append(f"{name}: {decimal_text(number)} is off step {decimal_text(step)} from {decimal_text(origin)}")
        if domain.get("type") == "integer" and number != number.to_integral_value():
            failures.append(f"{name}: {decimal_text(number)} is not an integer")
    return failures


def cost_audit(items: Any, declared_total: Any = None, label: str = "costs") -> dict[str, Any]:
    """Recompute every subtotal and the total without inferring billable quantities."""
    computed = Decimal(0)
    errors: list[str] = []
    normalized: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return {"computed_total": "0", "items": [], "errors": [f"{label} must be a list"]}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"{label}[{index}] must be an object")
            continue
        price = decimal_value(item.get("unit_price"))
        quantity = decimal_value(item.get("quantity"))
        if price is None or quantity is None:
            errors.append(f"{label}[{index}] requires numeric unit_price and quantity")
            continue
        if price < 0 or quantity < 0:
            errors.append(f"{label}[{index}] price and quantity must be nonnegative")
        subtotal = price * quantity
        computed += subtotal
        if "subtotal" in item:
            declared_subtotal = decimal_value(item.get("subtotal"))
            if declared_subtotal is None or declared_subtotal != subtotal:
                errors.append(f"{label}[{index}].subtotal {canonical(item.get('subtotal'))} != unit_price × quantity {decimal_text(subtotal)}")
        normalized.append({
            "item": item.get("item", item.get("resource_id", f"cost_{index}")),
            "resource_id": item.get("resource_id"),
            "unit_price": decimal_text(price), "quantity": decimal_text(quantity),
            "declared_subtotal": item.get("subtotal"),
            "computed_subtotal": decimal_text(subtotal),
        })
    if declared_total is not None:
        declared = decimal_value(declared_total)
        if declared is None or declared != computed:
            errors.append(f"declared total {canonical(declared_total)} != computed total {decimal_text(computed)}")
    return {"computed_total": decimal_text(computed), "items": normalized, "errors": errors}


def resource_contract(case: dict[str, Any]) -> dict[str, Any]:
    value = case.get("resource_contract", {})
    return value if isinstance(value, dict) else {}


def contract_budget(contract: dict[str, Any]) -> Decimal | None:
    return decimal_value(contract.get("budget_cap")) if "budget_cap" in contract else decimal_value(contract.get("budget_limit"))


def candidate_identifier(candidate: dict[str, Any], index: int) -> tuple[str, str]:
    for field in ("version", "id", "candidate_id"):
        if field in candidate and candidate[field] is not None and str(candidate[field]):
            return str(candidate[field]), field
    return f"candidate_{index}", "fallback_index"


def embedded_json_objects(text: Any) -> list[tuple[dict[str, Any], int]]:
    """Decode every top-level JSON object embedded in prose with raw_decode."""
    if not isinstance(text, str):
        return []
    decoder = json.JSONDecoder()
    objects: list[tuple[dict[str, Any], int]] = []
    position = 0
    while position < len(text):
        if text[position] != "{":
            position += 1
            continue
        try:
            value, end = decoder.raw_decode(text, position)
        except json.JSONDecodeError:
            position += 1
            continue
        if isinstance(value, dict):
            objects.append((value, position))
            position = end
        else:
            position += 1
    return objects


def build_resource_register(case: dict[str, Any]) -> dict[str, Any]:
    """Merge canonical/legacy lists and note resources; never hide their origins."""
    contract = resource_contract(case)
    register: dict[str, dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []

    def add(item: dict[str, Any], origin: str, inferred_class: str) -> None:
        identifier = item.get("id")
        if not nonempty_text(identifier):
            return
        record = register.get(identifier)
        if record is None:
            register[identifier] = {
                "id": identifier,
                "resource_class": item.get("resource_class", inferred_class),
                "name": item.get("name"), "model": item.get("model"),
                "spec": item.get("spec", item.get("capability")),
                "planning_unit_price": item.get("planning_unit_price"),
                "price_per_hour": item.get("price_per_hour"),
                "unit_price": item.get("unit_price"), "unit": item.get("unit"),
                "pack_size": item.get("pack_size"),
                "definition": item, "origins": [origin], "conflicting_definitions": False,
            }
            return
        record["origins"].append(origin)
        if canonical(record["definition"]) != canonical(item):
            record["conflicting_definitions"] = True
            conflict = next((x for x in conflicts if x["id"] == identifier), None)
            if conflict is None:
                conflict = {"id": identifier, "origins": list(record["origins"][:-1]),
                            "definitions": [record["definition"]]}
                conflicts.append(conflict)
            conflict["origins"].append(origin)
            conflict["definitions"].append(item)

    for field, inferred_class in (("resources", "unspecified"), ("equipment", "equipment"), ("reagents", "reagent")):
        items = contract.get(field, [])
        if isinstance(items, list):
            for index, item in enumerate(items):
                if isinstance(item, dict):
                    add(item, f"resource_contract.{field}[{index}]", inferred_class)

    def from_note(value: Any, origin: str, inferred_class: str = "unspecified") -> None:
        if not isinstance(value, dict):
            return
        if "id" in value and any(key in value for key in ("name", "model", "spec", "capability", "resource_class", "planning_unit_price", "price_per_hour", "unit_price")):
            add(value, origin, inferred_class)
        for field, resource_class in (("resources", "unspecified"), ("equipment", "equipment"), ("extra_equipment", "equipment"), ("reagents", "reagent")):
            children = value.get(field)
            if isinstance(children, list):
                for index, child in enumerate(children):
                    from_note(child, f"{origin}.{field}[{index}]", resource_class)
            elif isinstance(children, dict):
                from_note(children, f"{origin}.{field}", resource_class)

    for obj, position in embedded_json_objects(case.get("equipment_domain_note")):
        from_note(obj, f"equipment_domain_note@char{position}")
    resources = sorted(register.values(), key=lambda x: x["id"])
    return {
        "resources": resources,
        "resource_ids": sorted(register),
        "origins": {identifier: record["origins"] for identifier, record in sorted(register.items())},
        "conflicts": conflicts,
        "parser": "json.JSONDecoder.raw_decode over embedded objects in equipment_domain_note",
    }


def audit_candidates(case: dict[str, Any]) -> dict[str, Any]:
    domains = case.get("parameter_domains", {})
    domains = domains if isinstance(domains, dict) else {}
    contract = resource_contract(case)
    budget = contract_budget(contract)
    deadline = decimal_value(contract.get("deadline_days"))
    assessments: list[dict[str, Any]] = []
    candidates = case.get("candidate_plans", [])
    if not isinstance(candidates, list):
        candidates = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            assessments.append({"candidate_id": f"candidate_{index}", "status": "FAIL", "errors": ["candidate must be an object"]})
            continue
        candidate_id, identifier_field = candidate_identifier(candidate, index)
        errors: list[str] = []
        warnings: list[str] = []
        cost_field = "cost_items" if "cost_items" in candidate else "costs"
        if cost_field == "cost_items" and "costs" in candidate:
            warnings.append("Both cost_items and costs are present; canonical cost_items was audited.")
        audit = cost_audit(candidate.get(cost_field, []), label=cost_field)
        computed = Decimal(audit["computed_total"])
        for field in ("cost_subtotal", "total_cost"):
            if field in candidate:
                declared = decimal_value(candidate.get(field))
                if declared is None or declared != computed:
                    errors.append(f"{field} {canonical(candidate.get(field))} != recomputed {decimal_text(computed)}")
            else:
                warnings.append(f"{field} is absent; recomputed value is {decimal_text(computed)}")
        if budget is not None and computed > budget:
            errors.append(f"recomputed cost {decimal_text(computed)} exceeds budget {decimal_text(budget)}")
        duration_field = "est_days" if "est_days" in candidate else "duration_days"
        duration = decimal_value(candidate.get(duration_field))
        if deadline is not None and duration is not None and duration > deadline:
            errors.append(f"{duration_field} {decimal_text(duration)} days exceeds deadline {decimal_text(deadline)} days")
        elif duration is None:
            warnings.append("est_days/duration_days is absent or nonnumeric")
        parameters = candidate.get("parameters", {})
        if not isinstance(parameters, dict):
            errors.append("parameters must be an object")
            parameters = {}
        violations: list[str] = []
        for name, value in parameters.items():
            if name in domains:
                violations.extend(domain_violations(name, value, domains[name]))
            else:
                warnings.append(f"{name}: no declared domain; range not audited")
        errors.extend(violations)
        errors.extend(audit["errors"])
        assessments.append({
            "candidate_id": candidate_id,
            "version": candidate.get("version"),
            "input_id": candidate.get("id"),
            "legacy_candidate_id": candidate.get("candidate_id"),
            "aliases": {"identifier_field": identifier_field, "cost_items_field": cost_field, "duration_field": duration_field},
            "status": "FAIL" if errors else ("PASS_WITH_WARNINGS" if warnings else "PASS"),
            "declared_cost_subtotal": candidate.get("cost_subtotal"),
            "declared_total_cost": candidate.get("total_cost"),
            "recomputed_cost": decimal_text(computed), "cost_items": audit["items"],
            "est_days": candidate.get("est_days"), "duration_days": candidate.get("duration_days"),
            "parameter_domain_violations": violations,
            "errors": errors, "warnings": warnings,
        })
    return {
        "audit_basis": "Actual case candidate_plans; Decimal arithmetic and declared range/enum parameter_domains only. Billable quantity is used as declared, without inferred pack rounding.",
        "schema_aliases": {
            "candidate_id": ["version", "id", "candidate_id"],
            "cost_items": ["cost_items", "costs"], "duration_days": ["est_days", "duration_days"],
            "budget_cap": ["budget_cap", "budget_limit"], "numeric_domain": ["range", "number", "integer"],
            "enum_domain": ["values", "enum"],
        },
        "currency": contract.get("currency"),
        "budget_cap": contract.get("budget_cap", contract.get("budget_limit")),
        "budget_limit": contract.get("budget_limit"),
        "deadline_days": contract.get("deadline_days"),
        "candidate_count": len(assessments),
        "failed_candidate_count": sum(x["status"] == "FAIL" for x in assessments),
        "candidates": assessments,
    }


def material_inventory(input_dir: Path | None, case_path: Path, work_dir: Path) -> dict[str, Any]:
    if input_dir is None:
        input_dir = case_path.parent
    materials: list[dict[str, Any]] = []
    pdf_records: list[dict[str, Any]] = []
    pdftotext = shutil.which("pdftotext")
    if input_dir.exists():
        for path in sorted(p for p in input_dir.rglob("*") if p.is_file()):
            relative = str(path.relative_to(input_dir))
            try:
                raw = path.read_bytes()
            except OSError as exc:
                materials.append({"path": relative, "status": "unreadable", "error": str(exc)})
                continue
            record: dict[str, Any] = {"path": relative, "size_bytes": len(raw), "sha256": sha256_bytes(raw)}
            if path.suffix.lower() == ".pdf":
                extracted = work_dir / "pdf_text" / (relative.replace("/", "__") + ".txt")
                pdf: dict[str, Any] = {**record, "content_status": "not_extracted"}
                if not pdftotext:
                    pdf["extraction_status"] = "unavailable_pdftotext"
                    pdf["limitation"] = "pdftotext is unavailable; PDF content was not read."
                else:
                    extracted.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        completed = subprocess.run([pdftotext, "-layout", str(path), str(extracted)], capture_output=True, text=True, timeout=30)
                        if completed.returncode == 0:
                            text = extracted.read_text(encoding="utf-8", errors="replace")
                            pdf.update({"extraction_status": "extracted_unverified", "text_path": str(extracted), "text_excerpt": text[:12000], "truncated": len(text) > 12000})
                            pdf["content_status"] = "text_observed_not_scientifically_confirmed"
                        else:
                            pdf.update({"extraction_status": "failed", "stderr": completed.stderr[-2000:]})
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        pdf.update({"extraction_status": "failed", "error": str(exc)})
                pdf_records.append(pdf)
            elif path.suffix.lower() in {".md", ".txt", ".json", ".csv"}:
                text = raw.decode("utf-8", errors="replace")
                record.update({"status": "read_unverified", "text_excerpt": text[:20000], "truncated": len(text) > 20000})
                materials.append(record)
            else:
                record["status"] = "inventoried_content_not_extracted"
                materials.append(record)
    return {
        "input_dir": str(input_dir), "materials": materials, "pdfs": pdf_records,
        "pdftotext_available": bool(pdftotext),
        "limitation": "File labels and extracted text are observations, not confirmed scientific evidence. No PDF inference is made when content is unavailable.",
    }


def design_template(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "_header": output_notice(case),
        "_instructions": "Copy to /app/work/design_spec.json and replace empty structures with a concise, fully authored design. See references/contrast_design.md.",
        "schema_version": "1.0", "case_id": case.get("case_id", "REPLACE"),
        "design_summary": "", "hypotheses": [], "variables": [], "controls": [], "readouts": [],
        "replication": {}, "parameters": {}, "resources": [], "steps": [], "costs": [],
        "total_cost": None,
        "time_contract": {"one_time_step_ids": [], "per_biological_repeat_step_ids": [], "total_work_minutes": None, "instrument_booking_minutes": None, "note": "Distinguish one-pass steps from repeated work."},
        "schedule": {"total_days": None, "milestones": []},
        "evidence": [], "risks": [], "revision": {"base_candidate_id": "", "changes": [], "comparison": []},
        "uncertainty": [], "change_log": [], "confirmation_items": [],
    }


def inspect_command(args: argparse.Namespace) -> int:
    case_path = Path(args.case)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir = Path(args.work_dir) if args.work_dir else output_dir.parent / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    case, raw, error = load_case(case_path)
    if case is None:
        blocked_result("unknown", error or "invalid case", output_dir)
        return 0
    case_sha = sha256_bytes(raw)
    result = base_result(case, case_sha, "inspect")
    dump(output_dir / "result.json", result)  # Valid scaffold before inventory or PDF work.
    candidate_assessment = audit_candidates(case)
    inventory = material_inventory(Path(args.input_dir) if args.input_dir else None, case_path, work_dir)
    facts = {
        "case_id": case.get("case_id"), "title": case.get("title"),
        "task_text_observed": any(x.get("path") == "task.md" for x in inventory["materials"]),
        "parameter_domains": case.get("parameter_domains", {}),
        "resource_contract": resource_contract(case),
        "resource_register": build_resource_register(case),
        "materials": inventory["materials"], "pdf_inventory": inventory["pdfs"],
        "facts_status": "Observed input and mechanical audits only; inferred scientific facts are not confirmations.",
        "pdf_limitation": inventory["limitation"],
    }
    inspect_payload = {
        "_header": output_notice(case),
        "_metadata": {"generator": GENERATOR, "case_sha256": case_sha, "case_path": str(case_path)},
        "facts": facts, "candidate_assessment": candidate_assessment,
        "limitations": ["Candidate PASS does not establish causal validity or feasibility.", "Prospective resources, prices and bookings are not vendor quotes or approvals."],
    }
    dump(output_dir / "inspect.json", inspect_payload)
    dump(output_dir / "design_spec.template.json", design_template(case))
    result["candidate_assessment"] = candidate_assessment
    result["uncertainty"] = [inventory["limitation"], "No revised plan has yet been authored or scientifically audited."]
    result["sources"] = [{"source_class": "actual_input_inventory", "locator": x.get("path"), "supports": ["input_inventory"]} for x in inventory["materials"]]
    result["confirmation_items"] = ["Confirm equipment capability, availability, bookings and prices before execution.", "Author design_spec.json and run compile."]
    result["_metadata"]["artifacts"] = ["inspect.json", "design_spec.template.json", "result.json"]
    dump(output_dir / "result.json", result)
    return 0


def nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def require_text(container: dict[str, Any], fields: list[str], prefix: str, errors: list[str]) -> None:
    for field in fields:
        if not nonempty_text(container.get(field)):
            errors.append(f"{prefix}: required nonempty text '{field}' is missing")


def unique_ids(items: Any, label: str, errors: list[str]) -> set[str]:
    ids: set[str] = set()
    if not isinstance(items, list) or not items:
        errors.append(f"{label} must be a nonempty list")
        return ids
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"{label}[{index}] must be an object")
            continue
        identifier = item.get("id")
        if not nonempty_text(identifier):
            errors.append(f"{label}[{index}]: nonempty id required")
        elif identifier in ids:
            errors.append(f"{label}: duplicate id {identifier}")
        else:
            ids.add(identifier)
    return ids


def resolve_json_path(document: Any, locator: str) -> tuple[bool, Any]:
    if locator == "$":
        return True, document
    if not locator.startswith("$."):
        return False, None
    tokens = re.findall(r"\.([^.\[\]]+)|\[(\d+)\]", locator)
    if not tokens:
        return False, None
    cursor = document
    for key, index in tokens:
        if key:
            if not isinstance(cursor, dict) or key not in cursor:
                return False, None
            cursor = cursor[key]
        else:
            if not isinstance(cursor, list) or int(index) >= len(cursor):
                return False, None
            cursor = cursor[int(index)]
    return True, cursor


def verify_evidence(spec: dict[str, Any], case: dict[str, Any], case_path: Path, input_dir: Path | None, errors: list[str], warnings: list[str]) -> list[dict[str, Any]]:
    records = dict_list(spec.get("evidence"))
    evidence_ids = unique_ids(records, "evidence", errors)
    checks: list[dict[str, Any]] = []
    if not isinstance(records, list):
        return checks
    for index, evidence in enumerate(records):
        if not isinstance(evidence, dict):
            continue
        eid = str(evidence.get("id", f"evidence[{index}]"))
        require_text(evidence, ["source_class", "locator"], eid, errors)
        supports = evidence.get("supports")
        if not isinstance(supports, list) or not supports or not all(nonempty_text(x) for x in supports):
            errors.append(f"{eid}: supports must be a nonempty list of target IDs")
        quote = evidence.get("quote")
        check: dict[str, Any] = {"id": eid, "locator": evidence.get("locator"), "status": "WARN", "detail": "not mechanically verified"}
        source_class = evidence.get("source_class")
        locator = evidence.get("locator")
        if source_class == "case_json" and isinstance(locator, str):
            found, value = resolve_json_path(case, locator)
            if not found:
                check.update(status="FAIL", detail="case JSONPath did not resolve")
                errors.append(f"{eid}: case JSONPath did not resolve: {locator}")
            else:
                expected = canonical(value)
                if quote is None:
                    warnings.append(f"{eid}: resolved case value has no quote; value={expected}")
                    check.update(status="WARN", detail=f"resolved; quote absent; value={expected}")
                elif quote != expected:
                    check.update(status="FAIL", detail=f"quote mismatch; canonical case value={expected}")
                    errors.append(f"{eid}: quote does not exactly match canonical case JSON at {locator}")
                else:
                    check.update(status="PASS", detail="case JSONPath and canonical quote match exactly")
        elif source_class in {"provided_markdown", "provided_text", "provided_csv"} and isinstance(locator, str):
            relative = locator.split("#", 1)[0]
            candidates = [input_dir / relative] if input_dir else []
            candidates.extend([case_path.parent / relative, case_path.parent / "source_note.md" if relative == "source_note.md" else case_path.parent / relative])
            found_path = next((p for p in candidates if p.exists() and p.is_file()), None)
            if found_path is None:
                warnings.append(f"{eid}: supplied source file {relative} is unavailable; evidence remains unverified")
                check.update(status="WARN", detail="source file unavailable; no content confirmation")
            else:
                text = found_path.read_text(encoding="utf-8", errors="replace")
                if not nonempty_text(quote):
                    warnings.append(f"{eid}: quote required when provided source text is readable")
                    check.update(status="WARN", detail="source readable but quote absent")
                elif quote not in text:
                    errors.append(f"{eid}: quote is not an exact substring of {relative}")
                    check.update(status="FAIL", detail="quote not found in supplied source")
                else:
                    check.update(status="PASS", detail=f"exact quote found in {found_path}")
        elif source_class:
            if nonempty_text(quote):
                check.update(status="WARN", detail="traceable record supplied; external content not mechanically fetched")
                warnings.append(f"{eid}: external evidence not mechanically verified")
            else:
                warnings.append(f"{eid}: no quote available for external evidence")
                check["detail"] = "external record without quote"
        checks.append(check)
    return checks


def validate_replication(spec: dict[str, Any], errors: list[str]) -> None:
    replication = spec.get("replication")
    if not isinstance(replication, dict):
        errors.append("replication must be an object distinguishing biological repeats and technical wells")
        return
    if decimal_value(replication.get("biological_repeats")) is None or decimal_value(replication.get("biological_repeats", 0)) <= 0:
        errors.append("replication.biological_repeats must be positive and numeric")
    if decimal_value(replication.get("technical_wells")) is None or decimal_value(replication.get("technical_wells", 0)) <= 0:
        errors.append("replication.technical_wells must be positive and numeric")
    require_text(replication, ["independent_unit", "technical_unit", "distinction"], "replication", errors)
    if replication.get("independent_unit") == replication.get("technical_unit") and nonempty_text(replication.get("independent_unit")):
        errors.append("replication: independent and technical units must differ")
    for name in ("randomization", "blocking", "blinding"):
        item = replication.get(name)
        if not isinstance(item, dict) or not isinstance(item.get("relevant"), bool):
            errors.append(f"replication.{name}: object with boolean relevant is required (method if relevant, rationale if not)")
            continue
        if item["relevant"] and not nonempty_text(item.get("method")):
            errors.append(f"replication.{name}: method required when relevant")
        if not item["relevant"] and not nonempty_text(item.get("rationale")):
            errors.append(f"replication.{name}: rationale required when not relevant")


def validate_design(spec: dict[str, Any], case: dict[str, Any], case_path: Path, input_dir: Path | None) -> tuple[list[str], list[str], list[dict[str, Any]], dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    if spec.get("case_id") != case.get("case_id"):
        errors.append("design_spec.case_id must exactly match the actual case.case_id")
    require_text(spec, ["design_summary"], "design_spec", errors)
    hypotheses = spec.get("hypotheses")
    hypothesis_ids = unique_ids(hypotheses, "hypotheses", errors)
    if isinstance(hypotheses, list):
        for i, item in enumerate(hypotheses):
            if isinstance(item, dict):
                require_text(item, ["statement", "prediction", "falsification"], str(item.get("id", f"H[{i}]")), errors)
    variables = spec.get("variables")
    unique_ids(variables, "variables", errors)
    if isinstance(variables, list):
        for i, item in enumerate(variables):
            if not isinstance(item, dict):
                continue
            if item.get("kind") in {"independent", "dependent"}:
                require_text(item, ["operational_definition", "unit", "measurement", "level_source"], str(item.get("id", f"V[{i}]")), errors)
                if not isinstance(item.get("allowed_levels"), list) or not item.get("allowed_levels"):
                    errors.append(f"{item.get('id', f'V[{i}]')}: allowed_levels must be a nonempty list")
    controls = spec.get("controls")
    control_ids = unique_ids(controls, "controls", errors)
    if isinstance(controls, list):
        for i, item in enumerate(controls):
            if not isinstance(item, dict):
                continue
            cid = str(item.get("id", f"C[{i}]"))
            require_text(item, ["control_type", "condition", "excluded_alternative", "threat"], cid, errors)
            linked = item.get("hypothesis_ids")
            if not isinstance(linked, list) or not linked:
                errors.append(f"{cid}: hypothesis_ids must be a nonempty list")
            else:
                for hid in linked:
                    if hid not in hypothesis_ids:
                        errors.append(f"{cid}: unknown hypothesis ID {canonical(hid)}")
    evidence_checks = verify_evidence(spec, case, case_path, input_dir, errors, warnings)
    evidence_ids = {x.get("id") for x in dict_list(spec.get("evidence")) if isinstance(x, dict)} if isinstance(spec.get("evidence"), list) else set()
    readouts = spec.get("readouts")
    unique_ids(readouts, "readouts", errors)
    primary_count = 0
    if isinstance(readouts, list):
        for i, item in enumerate(readouts):
            if not isinstance(item, dict) or item.get("primary") is not True:
                continue
            primary_count += 1
            rid = str(item.get("id", f"R[{i}]"))
            require_text(item, ["direction", "metric", "unit", "criterion", "decision_rule"], rid, errors)
            refs = item.get("evidence")
            if not isinstance(refs, list) or not refs:
                errors.append(f"{rid}: primary readout requires evidence IDs")
            else:
                for ref in refs:
                    if ref not in evidence_ids:
                        errors.append(f"{rid}: unknown evidence ID {canonical(ref)}")
    if primary_count == 0:
        errors.append("at least one primary readout is required")
    validate_replication(spec, errors)
    domains = case.get("parameter_domains", {}) if isinstance(case.get("parameter_domains"), dict) else {}
    replication_values = spec.get("replication") if isinstance(spec.get("replication"), dict) else {}
    for replication_field in ("biological_repeats", "technical_wells"):
        if replication_field in replication_values and replication_field in domains:
            errors.extend(domain_violations(replication_field, replication_values[replication_field], domains[replication_field]))
    parameters = spec.get("parameters")
    if not isinstance(parameters, dict) or not parameters:
        errors.append("parameters must be a nonempty object")
        parameters = {}
    for name, value in parameters.items():
        if name in domains:
            errors.extend(domain_violations(name, value, domains[name]))
        else:
            warnings.append(f"parameter {name}: no declared domain; executable range could not be audited")
    resources = spec.get("resources")
    resource_ids = unique_ids(resources, "resources", errors)
    registry = build_resource_register(case)
    known_contract_ids = set(registry["resource_ids"])
    for conflict in registry["conflicts"]:
        errors.append(f"resource contract has conflicting duplicate definitions for {conflict['id']} at {conflict['origins']}")
    if isinstance(resources, list):
        for i, item in enumerate(resources):
            if isinstance(item, dict):
                require_text(item, ["resource_class", "requirement", "booking_status"], str(item.get("id", f"resource[{i}]")), errors)
                if isinstance(case.get("resource_contract"), dict) and item.get("id") not in known_contract_ids:
                    errors.append(f"resources[{i}]: ID {canonical(item.get('id'))} is absent from the parsed case resource register")
    steps = spec.get("steps")
    unique_ids(steps, "steps", errors)
    if isinstance(steps, list):
        for i, item in enumerate(steps):
            if not isinstance(item, dict):
                continue
            sid = str(item.get("id", f"S[{i}]"))
            require_text(item, ["instruction", "qc", "acceptance"], sid, errors)
            duration = decimal_value(item.get("duration_min"))
            if duration is None or duration <= 0:
                errors.append(f"{sid}: positive numeric duration_min required")
            elif "duration_min" in domains:
                errors.extend(domain_violations("duration_min", item.get("duration_min"), domains["duration_min"]))
            bound = item.get("equipment_resource_ids")
            if not isinstance(bound, list) or not bound:
                errors.append(f"{sid}: equipment_resource_ids must be a nonempty list")
            else:
                for ref in bound:
                    if ref not in resource_ids:
                        errors.append(f"{sid}: unknown equipment/resource ID {canonical(ref)}")
            step_parameters = item.get("parameters", {})
            if not isinstance(step_parameters, dict):
                errors.append(f"{sid}: parameters must be an object")
            else:
                for name, value in step_parameters.items():
                    if name in domains:
                        errors.extend(domain_violations(name, value, domains[name]))
                    else:
                        warnings.append(f"{sid} parameter {name}: no declared domain; range not audited")
    costs = spec.get("costs", [])
    contract = resource_contract(case)
    planning_prices: dict[str, tuple[Decimal, str, list[str]]] = {}
    for registered in registry["resources"]:
        for price_field in ("planning_unit_price", "price_per_hour", "unit_price"):
            price = decimal_value(registered.get(price_field))
            if price is not None:
                planning_prices[registered["id"]] = (price, price_field, registered["origins"])
                break
    if isinstance(costs, list):
        for i, item in enumerate(costs):
            if not isinstance(item, dict):
                continue
            if item.get("resource_id") not in resource_ids:
                errors.append(f"costs[{i}]: unknown resource_id {canonical(item.get('resource_id'))}")
            resource_id = item.get("resource_id")
            if resource_id in planning_prices:
                planning_price, price_field, origins = planning_prices[resource_id]
                price = decimal_value(item.get("unit_price"))
                if price is None or price != planning_price:
                    errors.append(f"costs[{i}]: unit_price must equal case {price_field} {decimal_text(planning_price)} for {resource_id} from {origins}")
    cost_result = cost_audit(costs, spec.get("total_cost"))
    cost_result["quantity_semantics"] = "Design quantity must already be the billable quantity after any pack-size rules; the compiler never infers quantities or pack rounding."
    errors.extend(cost_result["errors"])
    total = Decimal(cost_result["computed_total"])
    budget = contract_budget(contract)
    if budget is not None and total > budget:
        errors.append(f"plan cost {decimal_text(total)} exceeds case budget {decimal_text(budget)}")
    time_contract = spec.get("time_contract")
    time_recompute: dict[str, Any] = {"total_work_minutes": "0", "one_time_minutes": "0", "per_repeat_minutes": "0", "repeats": None}
    if not isinstance(time_contract, dict):
        errors.append("time_contract must distinguish one-time steps from per-biological-repeat steps")
    else:
        one_time_ids = time_contract.get("one_time_step_ids")
        repeat_ids = time_contract.get("per_biological_repeat_step_ids")
        step_records = dict_list(spec.get("steps"))
        step_ids = [item.get("id") for item in step_records]
        durations = {item.get("id"): decimal_value(item.get("duration_min")) for item in step_records}
        repeats = decimal_value(spec.get("replication", {}).get("biological_repeats")) if isinstance(spec.get("replication"), dict) else None
        if not isinstance(one_time_ids, list) or not isinstance(repeat_ids, list):
            errors.append("time_contract one_time_step_ids and per_biological_repeat_step_ids must be lists")
            one_time_ids, repeat_ids = [], []
        known_groups = (
            isinstance(one_time_ids, list) and isinstance(repeat_ids, list)
            and all(isinstance(ref, str) for ref in one_time_ids + repeat_ids + step_ids)
        )
        if not known_groups:
            errors.append("time_contract assignments require string step IDs")
        if known_groups:
            if set(one_time_ids) & set(repeat_ids):
                errors.append("time_contract step IDs cannot be both one-time and repeated")
            if set(one_time_ids + repeat_ids) != set(step_ids) or len(one_time_ids + repeat_ids) != len(step_ids):
                errors.append("time_contract must assign every executable step exactly once to one-time or per-repeat work")
            for ref in one_time_ids + repeat_ids:
                if ref not in durations or durations[ref] is None:
                    errors.append(f"time_contract: unknown step or nonnumeric duration for {canonical(ref)}")
    if isinstance(time_contract, dict) and known_groups and repeats is not None:
        one_minutes = sum((durations.get(ref) or Decimal(0) for ref in one_time_ids), Decimal(0))
        per_minutes = sum((durations.get(ref) or Decimal(0) for ref in repeat_ids), Decimal(0))
        work_minutes = one_minutes + repeats * per_minutes
        time_recompute = {"total_work_minutes": decimal_text(work_minutes), "one_time_minutes": decimal_text(one_minutes), "per_repeat_minutes": decimal_text(per_minutes), "repeats": decimal_text(repeats)}
        declared_work = decimal_value(time_contract.get("total_work_minutes"))
        if declared_work is None or declared_work != work_minutes:
            errors.append(f"time_contract.total_work_minutes {canonical(time_contract.get('total_work_minutes'))} != recomputed {decimal_text(work_minutes)}")
    booking_minutes = decimal_value(time_contract.get("instrument_booking_minutes")) if isinstance(time_contract, dict) else None
    if booking_minutes is None or booking_minutes < 0:
        errors.append("time_contract.instrument_booking_minutes must be nonnegative; unused booking contingency is separate from work time")
    require_text(time_contract, ["note"], "time_contract", errors) if isinstance(time_contract, dict) else None
    cost_result["time_recompute"] = time_recompute
    schedule = spec.get("schedule")
    if not isinstance(schedule, dict):
        errors.append("schedule object with total_days and milestones required")
    else:
        total_days = decimal_value(schedule.get("total_days"))
        deadline = decimal_value(contract.get("deadline_days"))
        if total_days is None or total_days <= 0:
            errors.append("schedule.total_days must be positive and numeric")
        if total_days is not None and deadline is not None and total_days > deadline:
            errors.append(f"schedule.total_days {decimal_text(total_days)} exceeds deadline {decimal_text(deadline)}")
        if not isinstance(schedule.get("milestones"), list) or not schedule.get("milestones"):
            errors.append("schedule.milestones must be a nonempty list")
    risks = spec.get("risks")
    unique_ids(risks, "risks", errors)
    if isinstance(risks, list):
        for i, item in enumerate(risks):
            if isinstance(item, dict):
                require_text(item, ["risk", "likelihood", "impact", "mitigation", "trigger", "contingency"], str(item.get("id", f"risk[{i}]")), errors)
    revision = spec.get("revision")
    if not isinstance(revision, dict):
        errors.append("revision object with base_candidate_id, changes and comparison required")
    else:
        base_id = revision.get("base_candidate_id")
        candidate_ids = {candidate_identifier(x, i)[0] for i, x in enumerate(case.get("candidate_plans", [])) if isinstance(x, dict)} if isinstance(case.get("candidate_plans"), list) else set()
        if str(base_id) not in candidate_ids:
            errors.append("revision.base_candidate_id must identify an actual candidate version/id/candidate_id")
        if not isinstance(revision.get("changes"), list) or not revision.get("changes"):
            errors.append("revision.changes must be a nonempty list")
        if not isinstance(revision.get("comparison"), list) or not revision.get("comparison"):
            errors.append("revision.comparison must be a nonempty before/after list")
    for field in ("uncertainty", "change_log", "confirmation_items"):
        if not isinstance(spec.get(field), list):
            errors.append(f"{field} must be a list (empty is allowed only when genuinely none)")
    return errors, warnings, evidence_checks, cost_result


def dict_list(value: Any) -> list[dict[str, Any]]:
    """Return only object records so malformed scientific sections can still render partial."""
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def markdown_cell(value: Any) -> str:
    if isinstance(value, (dict, list)):
        text = canonical(value)
    else:
        text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    lines.extend("| " + " | ".join(markdown_cell(x) for x in row) + " |" for row in rows)
    return "\n".join(lines) + "\n"


def render_plan_markdown(spec: dict[str, Any], plan: dict[str, Any], case: dict[str, Any], assessment: dict[str, Any]) -> str:
    notice = output_notice(case)
    footer = (f"{notice}。所有阈值和参数均为本合成情景的前瞻性协议假设，不是实验观测或文献事实。"
              if is_synthetic_case(case) else
              f"{notice}。阈值与参数仅按实际输入或明确协议假设呈现，不是实验观测或文献事实。")
    lines = [
        f"<!-- {notice} -->",
        "# 因果对照实验执行方案", "",
        f"- **案例**：{case.get('case_id')} — {case.get('title', '')}",
        f"- **状态**：{plan['validation_status']}；本文件为前瞻性方案，不含实测结果。",
        f"- **费用口径**：{resource_contract(case).get('currency', '未声明')}；{resource_contract(case).get('disclaimer', resource_contract(case).get('price_disclaimer', '价格与预订须确认'))}",
        "", "## 1. 可证伪机制假设", str(spec.get("design_summary") or ""),
        markdown_table(["ID", "假设", "预测", "证伪条件"], [[x.get("id"), x.get("statement"), x.get("prediction"), x.get("falsification")] for x in dict_list(spec.get("hypotheses")) if isinstance(x, dict)]),
        "## 2. 操作化变量",
        markdown_table(["ID", "类型", "单位", "操作定义", "测量", "允许水平", "来源"], [[x.get("id"), x.get("kind"), x.get("unit"), x.get("operational_definition"), x.get("measurement"), x.get("allowed_levels"), x.get("level_source")] for x in dict_list(spec.get("variables")) if isinstance(x, dict)]),
        "## 3. 对照—替代解释映射",
        markdown_table(["ID", "类型", "条件", "排除的替代解释", "威胁", "假设"], [[x.get("id"), x.get("control_type"), x.get("condition"), x.get("excluded_alternative"), x.get("threat"), x.get("hypothesis_ids")] for x in dict_list(spec.get("controls")) if isinstance(x, dict)]),
        "## 4. 主要读数与前瞻决策",
        markdown_table(["ID", "读数", "方向", "指标/单位", "判据", "决策规则", "证据"], [[x.get("id"), x.get("name"), x.get("direction"), f"{x.get('metric')} / {x.get('unit')}", x.get("criterion"), x.get("decision_rule"), x.get("evidence")] for x in dict_list(spec.get("readouts")) if isinstance(x, dict) and x.get("primary") is True]),
        "## 5. 重复、随机化、区组与盲法", "```json", json.dumps(spec.get("replication", {}), ensure_ascii=False, indent=2), "```",
        "**独立生物学重复不等于技术复孔；不得合并后虚增独立样本量。**",
        "## 6. 参数与执行步骤", "### 参数", "```json", json.dumps(spec.get("parameters", {}), ensure_ascii=False, indent=2), "```", "### 步骤",
        markdown_table(["ID", "时长(min)", "操作", "资源ID", "参数", "QC", "验收"], [[x.get("id"), x.get("duration_min"), x.get("instruction"), x.get("equipment_resource_ids"), x.get("parameters"), x.get("qc"), x.get("acceptance")] for x in dict_list(spec.get("steps")) if isinstance(x, dict)]),
        "## 7. 资源、精确成本与日程", "### 资源",
        markdown_table(["ID", "类别", "型号/规格", "能力要求", "预订状态"], [[x.get("id"), x.get("resource_class"), x.get("model"), x.get("requirement"), x.get("booking_status")] for x in dict_list(spec.get("resources")) if isinstance(x, dict)]),
        "### 成本（Decimal 重算）",
        markdown_table(["项目", "资源", "单价", "数量", "小计"], [[x.get("item"), x.get("resource_id"), x.get("unit_price"), x.get("quantity"), x.get("computed_subtotal")] for x in plan["cost_recompute"]["items"]]),
        f"**重算总成本：{plan['cost_recompute']['computed_total']}；单轮步骤合计：{plan['total_step_minutes']} min；按独立重复展开总工作：{plan.get('time_recompute', {}).get('total_work_minutes')} min；日程：{(plan.get('schedule') if isinstance(plan.get('schedule'), dict) else {}).get('total_days')} 天。** 所有价格、供应与仪器时段均非供应商报价或批准。",
        "### 时间合同（重复展开与仪器预订分开）",
        "```json", json.dumps({"declared": spec.get("time_contract", {}), "recomputed": plan.get("time_recompute", {})}, ensure_ascii=False, indent=2), "```",
        "### 日程", "```json", json.dumps(spec.get("schedule", {}), ensure_ascii=False, indent=2), "```",
        "## 8. 可追溯证据",
        markdown_table(["ID", "来源类别", "定位符", "支持对象", "原文/规范JSON值", "机械核验"], [[x.get("id"), x.get("source_class"), x.get("locator"), x.get("supports"), x.get("quote"), next((c["status"] for c in plan["evidence_verification"] if c["id"] == x.get("id")), "WARN")] for x in dict_list(spec.get("evidence")) if isinstance(x, dict)]),
        "## 9. 风险、触发与备选",
        markdown_table(["ID", "风险", "可能性", "影响", "缓解", "触发", "备选"], [[x.get("id"), x.get("risk"), x.get("likelihood"), x.get("impact"), x.get("mitigation"), x.get("trigger"), x.get("contingency")] for x in dict_list(spec.get("risks")) if isinstance(x, dict)]),
        "## 10. 相对候选方案的修订", "```json", json.dumps(spec.get("revision", {}), ensure_ascii=False, indent=2), "```",
        "### 候选方案机械审计（原方案的 FAIL 不自动否决经审计的修订方案）",
        markdown_table(["候选", "状态", "重算成本", "错误", "警告"], [[x.get("candidate_id"), x.get("status"), x.get("recomputed_cost"), x.get("errors"), x.get("warnings")] for x in assessment["candidates"]]),
        "## 11. 不确定性、变更与待确认", "### 不确定性", json.dumps(spec.get("uncertainty", []), ensure_ascii=False, indent=2),
        "### 变更记录", json.dumps(spec.get("change_log", []), ensure_ascii=False, indent=2),
        "### 待确认事项", json.dumps(spec.get("confirmation_items", []), ensure_ascii=False, indent=2),
        "", "---", footer, "",
    ]
    return "\n".join(lines)


def svg_body(x: float, y: float, text: str, max_units: int, max_lines: int) -> str:
    """Render portable SVG text without foreignObject or renderer-specific HTML."""
    lines: list[str] = []
    current = ""
    units = 0
    truncated = False
    for char in " ".join(str(text).split()):
        char_units = 2 if ord(char) > 255 else 1
        if current and units + char_units > max_units:
            lines.append(current)
            current = ""
            units = 0
            if len(lines) == max_lines:
                truncated = True
                break
        current += char
        units += char_units
    if len(lines) < max_lines and current:
        lines.append(current)
    elif len(lines) == max_lines and current:
        truncated = True
    if truncated and lines:
        lines[-1] = lines[-1][:-1] + "…" if len(lines[-1]) > 1 else "…"
    return "".join(
        f'<text class="body" x="{x}" y="{y + 16 * index}">{html.escape(line)}</text>'
        for index, line in enumerate(lines)
    )


def render_svg(spec: dict[str, Any], out: Path, case: dict[str, Any]) -> None:
    notice = output_notice(case)
    hypotheses = [x for x in dict_list(spec.get("hypotheses")) if nonempty_text(x.get("id"))]
    controls = [x for x in dict_list(spec.get("controls")) if nonempty_text(x.get("id"))]
    readouts = [x for x in dict_list(spec.get("readouts")) if nonempty_text(x.get("id")) and x.get("primary") is True]
    counts = [len(hypotheses), len(controls), len(readouts), 1]
    height = max(360, 110 + max(counts) * 125)
    h_pos = {x.get("id"): (40, 95 + i * 125) for i, x in enumerate(hypotheses)}
    c_pos = {x.get("id"): (430, 95 + i * 125) for i, x in enumerate(controls)}
    r_pos = {x.get("id"): (920, 95 + i * 125) for i, x in enumerate(readouts)}
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1240" height="%d" viewBox="0 0 1240 %d">' % (height, height),
        f'<!-- {notice} -->', f'<metadata>{html.escape(notice)}</metadata>',
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#44546a"/></marker>',
        '<style>text{font-family:Arial,"Noto Sans CJK SC",sans-serif;fill:#172b4d}.title{font-size:22px;font-weight:bold}.head{font-size:16px;font-weight:bold}.body{font-size:12px}.link{stroke:#44546a;stroke-width:1.5;fill:none;marker-end:url(#arrow)}.h{fill:#e8f1fb;stroke:#3572b0}.c{fill:#fff3d6;stroke:#b47b00}.r{fill:#e7f5e9;stroke:#398447}</style></defs>',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text class="title" x="40" y="35">Causal contrast map: hypotheses ↔ controls ↔ readouts</text>',
        f'<text class="body" x="40" y="58">{html.escape(notice)}</text>',
        '<text class="head" x="40" y="82">Hypotheses</text><text class="head" x="430" y="82">Controls / excluded alternatives</text><text class="head" x="920" y="82">Decision readouts</text>',
    ]
    for control in controls:
        cx, cy = c_pos.get(control.get("id"), (430, 95))
        hypothesis_links = control.get("hypothesis_ids") if isinstance(control.get("hypothesis_ids"), list) else []
        for hid in hypothesis_links:
            if isinstance(hid, str) and hid in h_pos:
                hx, hy = h_pos[hid]
                parts.append(f'<path class="link" d="M{cx},{cy + 44} C{cx - 55},{cy + 44} {hx + 330},{hy + 44} {hx + 300},{hy + 44}"/>')
    # Connect the first two controls to each readout only when evidence is explicit; remaining links use control coverage.
    for rid, (rx, ry) in r_pos.items():
        readout = next(x for x in readouts if x.get("id") == rid)
        linked = readout.get("control_ids") if isinstance(readout.get("control_ids"), list) else []
        if not linked:
            linked = [x.get("id") for x in controls[:1]]
        for cid in linked:
            if isinstance(cid, str) and cid in c_pos:
                cx, cy = c_pos[cid]
                parts.append(f'<path class="link" d="M{cx + 340},{cy + 44} C{cx + 390},{cy + 44} {rx - 50},{ry + 50} {rx},{ry + 50}"/>')
    for item in hypotheses:
        x, y = h_pos[item.get("id")]
        statement = str(item.get("statement", ""))
        parts.extend([f'<rect class="h" x="{x}" y="{y}" width="300" height="90" rx="8"/>', f'<text class="head" x="{x + 12}" y="{y + 23}">{html.escape(str(item.get("id")))}</text>', svg_body(x + 12, y + 42, statement, 46, 3)])
    for item in controls:
        x, y = c_pos[item.get("id")]
        label = f"{item.get('control_type')}: {item.get('excluded_alternative')}"
        parts.extend([f'<rect class="c" x="{x}" y="{y}" width="340" height="90" rx="8"/>', f'<text class="head" x="{x + 12}" y="{y + 23}">{html.escape(str(item.get("id")))}</text>', svg_body(x + 12, y + 42, label, 52, 3)])
    for item in readouts:
        x, y = r_pos[item.get("id")]
        label = f"{item.get('metric')} | {item.get('criterion')}"
        parts.extend([f'<rect class="r" x="{x}" y="{y}" width="280" height="100" rx="8"/>', f'<text class="head" x="{x + 12}" y="{y + 23}">{html.escape(str(item.get("id")))}</text>', svg_body(x + 12, y + 42, label, 42, 4)])
    parts.append('</svg>')
    write_text(out, "\n".join(parts) + "\n")


def compile_command(args: argparse.Namespace) -> int:
    case_path = Path(args.case)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    case, raw, error = load_case(case_path)
    if case is None:
        validation = {"_header": PROSPECTIVE_NOTICE, "status": "FAIL", "errors": [error or "invalid case"], "warnings": []}
        dump(output_dir / "validation.json", validation)
        blocked_result("unknown", error or "invalid case", output_dir)
        return 0
    case_sha = sha256_bytes(raw)
    result = base_result(case, case_sha, "compile")
    assessment = audit_candidates(case)
    result["candidate_assessment"] = assessment
    result["candidate_assessment"]["provenance"] = "Fresh internal rerun of inspect candidate audit; compile is standalone."
    dump(output_dir / "result.json", result)  # Early valid partial before reading the agent design.
    design_path = Path(args.design_spec)
    warnings: list[str] = []
    try:
        spec = json.loads(design_path.read_text(encoding="utf-8"))
        if not isinstance(spec, dict):
            errors = ["design_spec root must be an object"]
            spec = {}
        else:
            errors = []
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        spec = {}
        errors = [f"cannot read design_spec.json: {exc}"]
    input_dir = Path(args.input_dir) if args.input_dir else case_path.parent
    if not errors:
        errors, warnings, evidence_checks, cost_result = validate_design(spec, case, case_path, input_dir)
    else:
        evidence_checks, cost_result = [], {"computed_total": "0", "items": [], "errors": errors[:]}
    unknown = [x for x in required_fields(case) if x not in COMMON_FIELDS and x != "case_id"]
    if unknown:
        warnings.append("Unknown required fields use explicit missing-generator partial markers: " + ", ".join(unknown))
    validation_status = "FAIL" if errors else ("PASS_WITH_WARNINGS" if warnings else "PASS")
    steps = dict_list(spec.get("steps")) if isinstance(spec.get("steps"), list) else []
    total_minutes = sum(Decimal(str(x.get("duration_min", 0))) for x in steps if isinstance(x, dict) and decimal_value(x.get("duration_min")) is not None)
    plan = dict(spec)
    plan.update({
        "_header": output_notice(case),
        "_metadata": {"generator": GENERATOR, "case_sha256": case_sha, "scope": ("Prospective synthetic protocol assumptions; not measured results, vendor quotes or approvals." if is_synthetic_case(case) else "Prospective protocol and mechanical checks; not measured results, vendor quotes or approvals.")},
        "validation_status": validation_status,
        "cost_recompute": cost_result,
        "time_recompute": cost_result.get("time_recompute", {}),
        "total_step_minutes": decimal_text(total_minutes),
        "candidate_assessment_provenance": "Fresh mechanical audit of actual candidate_plans",
        "evidence_verification": evidence_checks,
    })
    validation = {
        "_header": output_notice(case),
        "_metadata": {"generator": GENERATOR, "case_sha256": case_sha},
        "status": validation_status, "errors": errors, "warnings": warnings,
        "fail_semantics": "Any FAIL makes result.status partial; scientific completion is never auto-claimed.",
        "checks": [
            {"id": "scientific_structure_and_arithmetic", "status": "FAIL" if errors else "PASS", "error_count": len(errors)},
            {"id": "candidate_audit", "status": "OBSERVED", "failed_candidates": assessment["failed_candidate_count"], "detail": "Candidate defects are reported separately from revised-plan validity."},
            {"id": "dynamic_required_fields", "status": "PARTIAL" if unknown else "PASS", "unknown_fields": unknown},
        ],
        "evidence_checks": evidence_checks, "cost_recompute": cost_result,
    }
    dump(output_dir / "validation.json", validation)
    dump(output_dir / "plan.json", plan)
    write_text(output_dir / "plan.md", render_plan_markdown(spec, plan, case, assessment))
    render_svg(spec, output_dir / "contrast_map.svg", case)
    complete = not errors and not unknown
    result.update({
        "status": "complete" if complete else "partial",
        "revised_plan": {
            "status": "generated" if not errors else "generated_with_failures",
            "artifacts": ["plan.json", "plan.md", "contrast_map.svg"],
            "design_summary": spec.get("design_summary"),
            "total_cost": cost_result["computed_total"], "currency": resource_contract(case).get("currency"),
            "single_pass_step_minutes": decimal_text(total_minutes),
            "total_work_minutes": cost_result.get("time_recompute", {}).get("total_work_minutes"),
            "instrument_booking_minutes": spec.get("time_contract", {}).get("instrument_booking_minutes") if isinstance(spec.get("time_contract"), dict) else None,
            "total_days": spec.get("schedule", {}).get("total_days") if isinstance(spec.get("schedule"), dict) else None,
            "execution_contract": "Bookmarked/planned only; obtain actual prices, equipment approval and bookings before execution.",
        },
        "validation": {"status": validation_status, "errors": errors, "warnings": warnings, "artifact": "validation.json"},
        "uncertainty": list_value(spec.get("uncertainty")) + ["Prices, availability, bookings and prospective parameters require confirmation; no measured results are present.", "If PDFs or extraction tools were unavailable, inspect.json records that limitation; no PDF content is inferred."],
        "sources": dict_list(spec.get("evidence")),
        "change_log": list_value(spec.get("change_log")),
        "confirmation_items": list_value(spec.get("confirmation_items")) + ["Confirm current vendor price and availability; prospective resource contract is not a vendor quote.", "Confirm equipment model/capability and booking approval before any experiment."],
    })
    for field in unknown:
        result[field] = missing_generator(field)
    result["_metadata"].update({"stage": "compiled", "artifacts": ["plan.json", "plan.md", "contrast_map.svg", "validation.json", "result.json"]})
    dump(output_dir / "result.json", result)
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Audit causal contrast identifiability and compile executable plans.")
    root.add_argument("--version", action="version", version=GENERATOR)
    sub = root.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect", help="Inventory actual input, audit candidates, and emit early partial/template.")
    inspect.add_argument("--case", required=True, help="Actual /input/case.json")
    inspect.add_argument("--input-dir", help="Actual input directory containing task.md, PDFs and materials")
    inspect.add_argument("--work-dir", help="Scratch directory for PDF text (normally /app/work)")
    inspect.add_argument("--output-dir", required=True, help="Final artifact directory (normally /app/output)")
    inspect.set_defaults(func=inspect_command)
    compile_parser = sub.add_parser("compile", help="Audit one design_spec.json and render all final artifacts.")
    compile_parser.add_argument("--case", required=True, help="Actual /input/case.json")
    compile_parser.add_argument("--design-spec", required=True, help="Single agent-authored design_spec.json")
    compile_parser.add_argument("--input-dir", help="Input directory for evidence quote verification")
    compile_parser.add_argument("--output-dir", required=True, help="Final artifact directory (normally /app/output)")
    compile_parser.set_defaults(func=compile_command)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.stderr.write("Interrupted; existing partial artifacts were preserved.\n")
        sys.exit(130)
