#!/usr/bin/env python3
"""Parse the supported, explicit output_contract shapes without guessing fields.

The parser returns all declared answer fields separately from the subset that is
required. List and mapping forms make every declared field required. JSON Schema
uses ``properties`` for all declared fields and ``required`` for the required
subset. Standard result keys are valid contract fields; only output_contract is
rejected because a nested output_contract is forbidden in result.json.
"""


def _validate_names(names, location, allow_empty=False):
    if not isinstance(names, list):
        raise ValueError(f"{location} must be an array")
    if not names and not allow_empty:
        raise ValueError(f"{location} must be a non-empty array")
    for name in names:
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{location} entries must be non-empty strings")
    if len(set(names)) != len(names):
        raise ValueError(f"{location} contains duplicates")
    if "output_contract" in names:
        raise ValueError("output_contract cannot be a contract answer field; answer fields must be flattened")
    return list(names)


def _names_from_container(value, location, allow_empty=False):
    """Read a string/name-object array or a mapping keyed by field name."""
    if isinstance(value, dict):
        return _validate_names(list(value), location, allow_empty=allow_empty)
    if not isinstance(value, list):
        raise ValueError(f"{location} must be an array or an object keyed by field name")
    names = []
    for index, item in enumerate(value):
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict) and "name" in item:
            names.append(item["name"])
        else:
            raise ValueError(f"{location}[{index}] must be a field name or an object with a name string")
    return _validate_names(names, location, allow_empty=allow_empty)


def _require_subset(required, fields, location):
    unknown = [name for name in required if name not in fields]
    if unknown:
        raise ValueError(f"{location} names absent from declared fields/properties: {', '.join(unknown)}")


def _from_json_schema(schema, location):
    if not isinstance(schema, dict):
        raise ValueError(f"{location} must be an object")
    properties = schema.get("properties")
    if not isinstance(properties, dict) or not properties:
        raise ValueError(f"{location}.properties must be a non-empty object keyed by field name")
    fields = _validate_names(list(properties), f"{location}.properties")
    if "required" in schema:
        required = _validate_names(schema["required"], f"{location}.required", allow_empty=True)
    else:
        required = []
    _require_subset(required, fields, f"{location}.required")
    return {"fields": fields, "required_fields": required}


def parse_output_contract(case):
    """Return ``{"fields": [...], "required_fields": [...]}`` for a case.

    Supported forms are:
    * output_contract: ["field", ...] (name objects are also accepted);
    * output_contract: {field: definition, ...};
    * output_contract.fields and/or required_fields as arrays or mappings;
    * JSON Schema directly, or under schema/json_schema, with properties/required.
    """
    if not isinstance(case, dict):
        raise ValueError("case must be an object")
    contract = case.get("output_contract")
    location = "case.output_contract"
    if isinstance(contract, list):
        fields = _names_from_container(contract, location)
        return {"fields": fields, "required_fields": list(fields)}
    if not isinstance(contract, dict) or not contract:
        raise ValueError("case.output_contract must be a non-empty object or array")

    schema_key = next((key for key in ("schema", "json_schema") if key in contract), None)
    if schema_key is not None:
        if "properties" in contract or "required" in contract:
            raise ValueError("Do not mix nested JSON Schema with top-level properties/required")
        return _from_json_schema(contract[schema_key], f"{location}.{schema_key}")
    if "properties" in contract or "required" in contract:
        return _from_json_schema(contract, location)

    if "fields" in contract or "required_fields" in contract:
        if "fields" in contract:
            fields = _names_from_container(contract["fields"], f"{location}.fields")
        else:
            fields = _names_from_container(contract["required_fields"], f"{location}.required_fields")
        if "required_fields" in contract:
            required = _names_from_container(
                contract["required_fields"], f"{location}.required_fields", allow_empty="fields" in contract
            )
            _require_subset(required, fields, f"{location}.required_fields")
        else:
            required = list(fields)
        return {"fields": fields, "required_fields": required}

    fields = _validate_names(list(contract), location)
    return {"fields": fields, "required_fields": list(fields)}
