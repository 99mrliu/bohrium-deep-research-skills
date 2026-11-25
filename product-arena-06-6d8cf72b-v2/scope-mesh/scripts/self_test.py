#!/usr/bin/env python3
"""Deterministic positive and expected-failure self-tests; no example files or writes."""
from __future__ import annotations

import copy
import json
from typing import Any, Dict

from scope_mesh import DIMENSIONS, audit_claims_payload, validate_contract_payload, validate_scope_payload


def base_record() -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "record_id": "NEG-R1",
        "claim_id": "NEG-C1",
        "classification": "demonstrated",
        "evidence": [{"source": "negative-source.txt", "anchor": "S1", "quote": "exact bounded quote"}],
    }
    for field in DIMENSIONS:
        record[field] = f"explicit {field}"
    return record


def bounded_claim(statement: str = "The bounded sample improved.") -> Dict[str, Any]:
    return {
        "claims": [{
            "claim_id": "NEG-C1",
            "statement": statement,
            "universal": False,
            "scope_record_ids": ["NEG-R1"],
        }]
    }


def codes(report: Dict[str, Any]) -> set:
    return {error["code"] for error in report["errors"]}


def main() -> int:
    sources = {"negative-source.txt": "[S1]\nexact bounded quote\n[S2]\nsecond exact quote\n"}
    good = {"records": [base_record()]}
    tests = []

    missing = copy.deepcopy(good)
    missing["records"][0]["metric_unit"] = ""
    report = validate_scope_payload(missing, source_texts=sources)
    tests.append(("empty metric/unit rejected", any(e["code"] == "DIMENSION_REQUIRED" for e in report["errors"])))

    bad_quote = copy.deepcopy(good)
    bad_quote["records"][0]["evidence"][0]["quote"] = "quote from somewhere else"
    report = validate_scope_payload(bad_quote, source_texts=sources)
    tests.append(("wrong verbatim quote rejected", any(e["code"] == "QUOTE_MISMATCH" for e in report["errors"])))

    bad_nr = copy.deepcopy(good)
    bad_nr["records"][0]["comparator"] = {"status": "NR", "reason": ""}
    report = validate_scope_payload(bad_nr, source_texts=sources)
    tests.append(("reasonless NR rejected", any(e["code"] == "INVALID_NR_NA" for e in report["errors"])))

    universal = {
        "claims": [{
            "claim_id": "NEG-U1",
            "statement": "The method always works on all datasets.",
            "universal": True,
            "scope_record_ids": ["NEG-R1"],
            "section_coverage": {
                "methods": {"checked": True, "evidence": {"source": "negative-source.txt", "anchor": "S1", "quote": "exact bounded quote"}},
                "results": {"checked": True, "evidence": {"source": "negative-source.txt", "anchor": "S1", "quote": "exact bounded quote"}},
                "tables": {"checked": True, "evidence": {"source": "negative-source.txt", "anchor": "S1", "quote": "exact bounded quote"}}
            },
            "exception_search": {"performed": False, "terms": [], "locations": []},
            "counterexamples": []
        }]
    }
    report = audit_claims_payload(universal, good, source_texts=sources)
    flags = set(report["claims"][0]["flags"])
    tests.append(("unclosed universal flagged", {"UNIVERSAL_MISSING_DISCUSSION", "UNIVERSAL_NO_EXCEPTION_SEARCH"} <= flags))

    closed_universal = copy.deepcopy(universal)
    closed_universal["claims"][0]["section_coverage"]["discussion"] = {
        "checked": True,
        "evidence": {"source": "negative-source.txt", "anchor": "S1", "quote": "exact bounded quote"},
    }
    closed_universal["claims"][0]["exception_search"] = {
        "performed": True,
        "terms": ["opposite"],
        "locations": ["negative-source.txt [S1]"],
    }
    report = audit_claims_payload(closed_universal, good, source_texts=sources)
    tests.append(("aggregate universal may link differently-owned bounded records", report["valid"] and "RECORD_CLAIM_MISMATCH" not in codes(report)))

    report = audit_claims_payload(bounded_claim("All samples improved."), good, source_texts=sources)
    tests.append(("bare word-boundary all flagged", "POSSIBLE_UNIVERSAL_NOT_DECLARED" in report["claims"][0]["flags"]))
    report = audit_claims_payload(bounded_claim("Overall, the small alloy sample improved."), good, source_texts=sources)
    tests.append(("all substrings do not cause false positives", "POSSIBLE_UNIVERSAL_NOT_DECLARED" not in report["claims"][0]["flags"]))
    for word in ("所有", "全部"):
        report = audit_claims_payload(bounded_claim(f"{word}样本均改善。"), good, source_texts=sources)
        tests.append((f"Chinese universal {word} flagged", "POSSIBLE_UNIVERSAL_NOT_DECLARED" in report["claims"][0]["flags"]))

    mismatched_claim = bounded_claim()
    mismatched_claim["claims"][0]["claim_id"] = "NEG-C2"
    report = audit_claims_payload(mismatched_claim, good, source_texts=sources)
    tests.append(("nonuniversal record claim mismatch rejected", not report["valid"] and "RECORD_CLAIM_MISMATCH" in codes(report)))
    composed_claim = copy.deepcopy(mismatched_claim)
    composed_claim["claims"][0]["scope_record_link_exceptions"] = {
        "NEG-R1": {"kind": "composition", "reason": "This documented aggregate includes the bounded premise without relabelling its source conclusion."}
    }
    report = audit_claims_payload(composed_claim, good, source_texts=sources)
    tests.append(("documented composition exception accepted", report["valid"]))

    contract = {
        "case_id": "NEG-CASE",
        "output_contract": {
            "type": "object",
            "additionalProperties": False,
            "required": ["case_id", "items"],
            "properties": {
                "case_id": {"type": "string", "const": "NEG-CASE"},
                "items": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "string"}}
            }
        }
    }
    report = validate_contract_payload({"case_id": "NEG-CASE", "items": ["only one"], "extra": 1}, contract)
    tests.append(("extra field and wrong item count rejected", {"ADDITIONAL_PROPERTY", "MIN_ITEMS"} <= codes(report)))

    any_of = {"type": "string", "anyOf": [{"minLength": 3}, {"pattern": "^x"}]}
    report = validate_contract_payload("ab", any_of)
    tests.append(("anyOf nonmatch cannot false-pass", not report["valid"] and "ANY_OF_MISMATCH" in codes(report)))
    report = validate_contract_payload("abc", any_of)
    tests.append(("anyOf accepts a matching branch", report["valid"]))
    report = validate_contract_payload("x", any_of)
    tests.append(("anyOf accepts either matching branch", report["valid"]))

    one_of = {"oneOf": [{"type": "integer"}, {"minimum": 2}]}
    report = validate_contract_payload(1, one_of)
    tests.append(("oneOf accepts exactly one match", report["valid"]))
    report = validate_contract_payload(3, one_of)
    tests.append(("oneOf rejects multiple matches", not report["valid"] and "ONE_OF_MULTIPLE_MATCHES" in codes(report)))
    report = validate_contract_payload(1.5, one_of)
    tests.append(("oneOf rejects zero matches", not report["valid"] and "ONE_OF_MISMATCH" in codes(report)))

    unknown = copy.deepcopy(contract)
    unknown["output_contract"]["properties"]["items"]["items"]["format"] = "uri"
    valid_result = {"case_id": "NEG-CASE", "items": ["one", "two"]}
    report = validate_contract_payload(valid_result, unknown)
    tests.append(("nested unknown keyword cannot false-pass", not report["valid"] and not report["schema_valid"] and "UNSUPPORTED_SCHEMA_KEYWORD" in codes(report)))

    unknown_branch = {"anyOf": [{"type": "string"}, {"type": "number", "exclusiveMinimum": 0}]}
    report = validate_contract_payload("valid first branch", unknown_branch)
    tests.append(("unknown keyword in unused anyOf branch rejected", not report["valid"] and "UNSUPPORTED_SCHEMA_KEYWORD" in codes(report)))
    report = validate_contract_payload("anything", {"anyOf": None})
    tests.append(("null combinator declaration rejected instead of ignored", not report["valid"] and not report["schema_valid"] and "INVALID_SCHEMA" in codes(report)))

    declared = copy.deepcopy(contract)
    declared["output_contract"]["properties"]["note"] = {"type": "string"}
    report = validate_contract_payload(valid_result, declared)
    tests.append(("omitted declared case property rejected", not report["valid"] and "DECLARED_PROPERTY_MISSING" in codes(report)))
    report = validate_contract_payload(dict(valid_result, note="present"), declared)
    tests.append(("present declared optional-schema property accepted", report["valid"]))

    report = validate_contract_payload(valid_result, contract, case_id="OVERRIDE")
    tests.append(("case identity remains authoritative over CLI override", not report["valid"] and "CASE_ID_ARGUMENT_MISMATCH" in codes(report) and report["case_id"] == "NEG-CASE"))

    failed = [name for name, passed in tests if not passed]
    for name, passed in tests:
        print(f"{'PASS' if passed else 'FAIL'} check: {name}")
    print(json.dumps({"test_cases": len(tests), "failures": len(failed), "semantic_validation": False}))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
