#!/usr/bin/env python3
"""Dynamic output-contract skeleton, projection, and bounded JSON-Schema checks.

Supports JSON-Schema-shaped objects, {field: type} maps, lists of field names,
and lists of {name/key/field, type} descriptors. Unknown fields stay null and are
reported unresolved; no values are fabricated to make a contract pass.
"""
import json
import math
import re

CONTRACT_KEYS = (
    "output_contract", "outputContract", "contract", "output", "output_schema",
    "result_schema", "expected_output", "expected_outputs", "output_fields",
    "required_fields", "output_format",
)
SCHEMA_KEYS = {"type", "properties", "required", "items", "additionalProperties", "enum",
               "const", "description", "title", "$schema", "default", "examples", "fields"}
VERDICTS = {"supported", "partially_supported", "contradicted", "insufficient_evidence"}


def normalize(key):
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def find_contract(case, depth=0):
    if not isinstance(case, dict) or depth > 3:
        return None
    for key in CONTRACT_KEYS:
        if case.get(key) is not None:
            return case[key]
    if isinstance(case.get("outputs"), (dict, list)):
        return case["outputs"]
    for key in ("task", "spec", "evaluation", "grader", "case", "request"):
        found = find_contract(case.get(key), depth + 1)
        if found is not None:
            return found
    return None


def case_identifier(case):
    if isinstance(case, dict):
        for key in ("case_id", "caseId", "id", "sample_id", "sampleId", "uid"):
            if case.get(key) is not None and case.get(key) != "":
                return str(case[key])
    return "unspecified"


def selected_type(spec):
    if isinstance(spec, str):
        aliases = {"list": "array", "dict": "object", "str": "string", "float": "number", "int": "integer"}
        return aliases.get(spec, spec)
    if not isinstance(spec, dict):
        return None
    value = spec.get("type")
    if isinstance(value, list):
        return next((item for item in value if item != "null"), None)
    return value


def verdict_shape(verdicts, spec):
    if selected_type(spec) == "object" and not (isinstance(spec, dict) and spec.get("properties")):
        return {item["claim_id"]: item for item in verdicts}
    return verdicts


def resolve(key, spec, context, field_status, path):
    name = normalize(key)
    aliases = {
        "caseid": "case_id", "id": "case_id", "sampleid": "case_id",
        "claims": "claim_verdicts", "claimverdicts": "claim_verdicts", "verdicts": "claim_verdicts",
        "results": "claim_verdicts", "answers": "claim_verdicts", "adjudications": "claim_verdicts",
        "status": "status", "runstatus": "status", "state": "status",
        "sources": "sources", "source": "sources", "provenance": "sources",
        "uncertainty": "uncertainty", "uncertainties": "uncertainty", "limitations": "uncertainty",
        "warnings": "warnings", "changerecords": "change_records", "changes": "change_records",
        "quantitativereport": "quantitative_report", "quantreport": "quantitative_report",
        "derived": "derived", "derivedresults": "derived", "calculations": "derived",
        "observations": "observations", "evidence": "derived", "summary": "summary",
        "reportartifact": "report_artifact", "plotartifact": "plot_artifact", "notes": "uncertainty",
    }
    target = aliases.get(name)
    dotted = ".".join(path + [str(key)])
    if target is None:
        field_status[dotted] = "unresolved"
        return None
    value = context.get(target)
    if target == "status":
        value = context["status"] if selected_type(spec) in (None, "string") else {
            "state": context["status"], "complete": context["status"] == "success"
        }
    elif target == "claim_verdicts":
        value = verdict_shape(context["claim_verdicts"], spec)
    elif target == "sources" and selected_type(spec) == "object":
        value = {"items": context["sources"]}
    elif target == "uncertainty" and selected_type(spec) == "string":
        value = "\n".join(context["uncertainty"])
    elif target == "change_records" and selected_type(spec) == "object":
        value = {"items": context["change_records"]}
    elif target == "quantitative_report" and selected_type(spec) == "string":
        value = context["report_artifact"]
    elif target == "summary" and selected_type(spec) == "string":
        value = "%d claims adjudicated; run status %s" % (len(context["claim_verdicts"]), context["status"])
    field_status[dotted] = "filled" if value not in (None, "", [], {}) else "not_reported"
    return value


def fill(spec, context, field_status, path=None, key=None):
    path = path or []
    if isinstance(spec, dict) and ("properties" in spec or "fields" in spec):
        nested = spec.get("properties") if spec.get("properties") is not None else spec.get("fields")
        return fill(nested, context, field_status, path)
    if isinstance(spec, dict) and not (set(spec) & SCHEMA_KEYS):
        return {str(child_key): fill(child_spec, context, field_status, path + [str(child_key)], child_key)
                for child_key, child_spec in spec.items()}
    if isinstance(spec, dict) and selected_type(spec) == "object" and spec.get("additionalProperties") and key:
        value = resolve(key, spec, context, field_status, path)
        return value
    if isinstance(spec, list):
        if all(isinstance(item, str) for item in spec):
            return {item: fill(item, context, field_status, path + [item], item) for item in spec}
        named = [item for item in spec if isinstance(item, dict) and any(k in item for k in ("name", "key", "field"))]
        if named:
            result = {}
            for item in named:
                name = str(item.get("name") or item.get("key") or item.get("field"))
                child_spec = {k: v for k, v in item.items() if k not in ("name", "key", "field")}
                result[name] = fill(child_spec or "string", context, field_status, path + [name], name)
            return result
        return [fill(item, context, field_status, path, key) for item in spec]
    if key is None:
        return {}
    return resolve(key, spec, context, field_status, path)


def assemble(contract, context):
    field_status = {}
    if contract is None:
        result = {}
        field_status["output_contract"] = "not_declared"
    elif isinstance(contract, str):
        # Prose contracts are not parsed into imaginary fields; required standard
        # fields remain available and the ambiguity is explicit in the audit.
        result = {}
        field_status["output_contract"] = "free_text_unresolved"
    else:
        result = fill(contract, context, field_status)
        if not isinstance(result, dict):
            result = {"value": result}
            field_status["output_contract"] = "root_wrapped_for_required_metadata"
    # These four metadata fields plus case_id are platform-mandated even when a
    # closed case schema forgot to declare them. The checker discloses that clash.
    result["case_id"] = context["case_id"]
    if "status" not in result:
        result["status"] = context["status"]
    for key in ("sources", "uncertainty", "change_records"): 
        if key not in result:
            result[key] = context[key]
    verdict_fields = [key for key in result if normalize(key) in
                      ("claims", "claimverdicts", "verdicts", "results", "answers", "adjudications")]
    if not verdict_fields:
        result["claim_verdicts"] = context["claim_verdicts"]
    return result, field_status


def check_schema(value, schema, path="$"):
    errors, warnings = [], []
    if not isinstance(schema, dict):
        return errors, warnings
    supported = {"type", "properties", "required", "items", "additionalProperties", "enum", "const",
                 "minItems", "maxItems", "minLength", "maxLength", "minimum", "maximum",
                 "description", "title", "$schema", "default", "examples"}
    for key in set(schema) - supported:
        warnings.append(path + ": unchecked schema keyword " + key)
    types = schema.get("type")
    if isinstance(types, str):
        types = [types]
    predicates = {
        "null": lambda x: x is None, "string": lambda x: isinstance(x, str),
        "object": lambda x: isinstance(x, dict), "array": lambda x: isinstance(x, list),
        "boolean": lambda x: isinstance(x, bool),
        "integer": lambda x: isinstance(x, int) and not isinstance(x, bool),
        "number": lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x),
    }
    if types and not any(predicates.get(kind, lambda x: False)(value) for kind in types):
        return [path + ": type mismatch, expected " + str(types)], warnings
    if "enum" in schema and value not in schema["enum"]:
        errors.append(path + ": outside enum")
    if "const" in schema and value != schema["const"]:
        errors.append(path + ": differs from const")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(path + "." + key + ": missing required field")
        if schema.get("additionalProperties") is False:
            for key in set(value) - set(properties):
                errors.append(path + "." + key + ": unexpected field in closed schema")
        for key, child in value.items():
            child_schema = properties.get(key, schema.get("additionalProperties", {}))
            err, warn = check_schema(child, child_schema, path + "." + key)
            errors.extend(err); warnings.extend(warn)
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(path + ": below minItems")
        if len(value) > schema.get("maxItems", float("inf")):
            errors.append(path + ": above maxItems")
        for index, item in enumerate(value):
            err, warn = check_schema(item, schema.get("items", {}), path + "[%d]" % index)
            errors.extend(err); warnings.extend(warn)
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(path + ": below minLength")
        if len(value) > schema.get("maxLength", float("inf")):
            errors.append(path + ": above maxLength")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < schema.get("minimum", -float("inf")):
            errors.append(path + ": below minimum")
        if value > schema.get("maximum", float("inf")):
            errors.append(path + ": above maximum")
    return errors, warnings


def audit(result, contract, field_status, claim_count):
    errors, warnings = [], []
    for key in ("case_id", "status", "sources", "uncertainty", "change_records"):
        if key not in result:
            errors.append("missing platform field: " + key)
    raw_status = result.get("status")
    run_state = raw_status.get("state") if isinstance(raw_status, dict) else raw_status
    if run_state not in ("success", "partial", "failed"):
        errors.append("status must be success, partial, or failed")
    if isinstance(contract, dict) and ("properties" in contract or contract.get("type") == "object"):
        errors, warnings = check_schema(result, contract)
    elif isinstance(contract, dict):
        for key in contract:
            if key not in result:
                errors.append("missing contract field: " + key)
    elif contract is None:
        warnings.append("no output_contract declared; default fields used")
    else:
        warnings.append("contract shape not machine-checkable")
    verdict_items = result.get("claim_verdicts", [])
    if isinstance(verdict_items, dict):
        verdict_items = list(verdict_items.values())
    if not verdict_items:
        for value in result.values():
            candidates = list(value.values()) if isinstance(value, dict) else value
            if (isinstance(candidates, list) and candidates and
                    all(isinstance(item, dict) and "claim_id" in item for item in candidates)):
                verdict_items = candidates
                break
    for item in verdict_items:
        verdict = item.get("verdict")
        if verdict is not None and verdict not in VERDICTS:
            errors.append("invalid four-level verdict for " + str(item.get("claim_id")))
        if verdict is not None and item.get("verdict_origin") != "agent":
            errors.append("numeric verdict lacks explicit Agent origin for " + str(item.get("claim_id")))
    if run_state == "success":
        if len(verdict_items) != claim_count:
            errors.append("successful result does not cover every claim")
        if any(item.get("verdict") not in VERDICTS for item in verdict_items):
            errors.append("successful result has an unresolved or invalid verdict")
    unresolved = [key for key, value in field_status.items() if value != "filled"]
    if unresolved:
        warnings.append("unresolved contract fields: " + ", ".join(unresolved))
    return {
        "contract_check": "fail" if errors else ("needs_review" if warnings else "pass"),
        "errors": errors, "warnings": warnings, "field_status": field_status,
        "unresolved_fields": unresolved, "semantic_verification": "Agent verdict provenance checked; truth of rationale not machine-certified",
        "claims_checked": len(verdict_items),
    }


def dumps(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
