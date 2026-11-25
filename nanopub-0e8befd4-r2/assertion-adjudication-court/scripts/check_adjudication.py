#!/usr/bin/env python3
"""Validate an assertion-adjudication ledger using Python 3.9+ stdlib only.

Writes a UTF-8 JSON report for both passing and failing validation. A skipped
input ID is always an error; a complete, ID-preserving ledger with pending
items can be a valid partial result.
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path


VERDICTS = ("supported", "contradicted", "not_established", "mixed")
DISPOSITIONS = ("supported", "contradicted", "not_established")
STANCES = ("support", "reverse", "context")
REVIEW_DISPOSITIONS = ("accept", "rewrite", "reject")
CHECK_NAMES = (
    "case_schema",
    "output_contract",
    "required_result_fields",
    "input_id_coverage",
    "input_order",
    "original_text_preserved",
    "pending_shape",
    "component_verdict_logic",
    "support_and_reverse_evidence",
    "evidence_sources",
    "evidence_quotes",
    "corrected_claim_links",
    "source_inventory",
    "change_records",
    "result_consistency",
    "state_machine",
)


class DuplicateKeyError(ValueError):
    """JSON object contains a duplicate key."""


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError("duplicate JSON object key: {0}".format(key))
        result[key] = value
    return result


def read_json(path):
    with open(str(path), "r", encoding="utf-8") as handle:
        return json.load(handle, object_pairs_hook=unique_object)


def parse_task_contract(path):
    text = Path(path).read_text(encoding="utf-8")
    match = re.search(
        r"(?ms)^## output_contract\s*$.*?^```json\s*$(.*?)^```\s*$", text
    )
    if not match:
        raise ValueError("task lacks '## output_contract' followed by a JSON fence")
    payload = json.loads(match.group(1), object_pairs_hook=unique_object)
    contract = payload.get("output_contract")
    if not isinstance(contract, dict):
        raise ValueError("output_contract JSON block must contain an object")
    return contract


def is_nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def is_string_list(value):
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


class Validator:
    def __init__(self, case, task_contract, ledger, result, ledger_path, report_path):
        self.case = case
        self.contract = task_contract
        self.ledger = ledger
        self.result = result
        self.ledger_path = Path(ledger_path)
        self.report_path = Path(report_path)
        self.errors = []
        self.checks = dict((name, True) for name in CHECK_NAMES)
        self.case_assertions = []
        self.case_by_id = {}
        self.input_ids = []
        self.source_text = {}
        self.source_ids = []
        self.records_by_id = {}
        self.corrections_by_id = {}
        self.used_correction_ids = []
        self.coverage_ok = False
        self.all_adjudicated = False
        self.adjudicated_count = 0
        self.verdict_counts = dict((verdict, 0) for verdict in VERDICTS)

    def error(self, check, code, message):
        if check in self.checks:
            self.checks[check] = False
        self.errors.append({"code": code, "message": message})

    def require_case_schema(self):
        if not isinstance(self.case, dict):
            self.error("case_schema", "CASE_NOT_OBJECT", "case must be an object")
            return
        if not is_nonempty_string(self.case.get("case_id")):
            self.error("case_schema", "CASE_ID", "case_id must be a nonempty string")
        assertions = self.case.get("assertions")
        sources = self.case.get("sources")
        if not isinstance(assertions, list) or not assertions:
            self.error("case_schema", "ASSERTIONS", "assertions must be a nonempty array")
            assertions = []
        if not isinstance(sources, list) or not sources:
            self.error("case_schema", "SOURCES", "sources must be a nonempty array")
            sources = []
        seen_ids = set()
        for index, assertion in enumerate(assertions):
            if not isinstance(assertion, dict):
                self.error("case_schema", "ASSERTION_OBJECT", "assertion {0} is not an object".format(index))
                continue
            input_id = assertion.get("input_id")
            if not is_nonempty_string(input_id):
                self.error("case_schema", "INPUT_ID", "assertion {0} lacks input_id".format(index))
                continue
            if input_id in seen_ids:
                self.error("case_schema", "DUPLICATE_CASE_ID", "duplicate case input_id: " + input_id)
                continue
            if not isinstance(assertion.get("claim"), str):
                self.error("case_schema", "CASE_CLAIM", "claim must be a string for " + input_id)
                continue
            if type(assertion.get("compound")) is not bool:
                self.error("case_schema", "COMPOUND_FLAG", "compound must be boolean for " + input_id)
                continue
            seen_ids.add(input_id)
            self.input_ids.append(input_id)
            self.case_by_id[input_id] = assertion
            self.case_assertions.append(assertion)
        seen_sources = set()
        for index, source in enumerate(sources):
            if not isinstance(source, dict):
                self.error("case_schema", "SOURCE_OBJECT", "source {0} is not an object".format(index))
                continue
            source_id = source.get("source_id")
            if not is_nonempty_string(source_id):
                self.error("case_schema", "SOURCE_ID", "source {0} lacks source_id".format(index))
                continue
            if source_id in seen_sources:
                self.error("case_schema", "DUPLICATE_SOURCE_ID", "duplicate source_id: " + source_id)
                continue
            if not isinstance(source.get("text"), str):
                self.error("case_schema", "SOURCE_TEXT", "source text must be a string for " + source_id)
                continue
            seen_sources.add(source_id)
            self.source_ids.append(source_id)
            self.source_text[source_id] = source["text"]
        if len(self.case_assertions) != len(assertions):
            self.error("case_schema", "MALFORMED_ASSERTIONS", "one or more assertions were malformed")
        if len(self.source_text) != len(sources):
            self.error("case_schema", "MALFORMED_SOURCES", "one or more sources were malformed")

    def require_contract(self):
        if not isinstance(self.contract, dict):
            self.error("output_contract", "CONTRACT_OBJECT", "output_contract must be an object")
            self.contract = {}
            return
        required = self.contract.get("required_result_fields")
        if not is_string_list(required) or not required:
            self.error(
                "output_contract",
                "REQUIRED_FIELDS",
                "required_result_fields must be a nonempty string array",
            )
        elif len(set(required)) != len(required):
            self.error("output_contract", "DUPLICATE_REQUIRED_FIELD", "required_result_fields has duplicates")
        for key in ("case_id_field", "status_field"):
            if not is_nonempty_string(self.contract.get(key, "case_id" if key == "case_id_field" else "status")):
                self.error("output_contract", "CONTRACT_FIELD_NAME", key + " must be a nonempty string")
        statuses = self.contract.get("status_values", ["success", "partial"])
        if not is_string_list(statuses) or set(statuses) != {"success", "partial"}:
            self.error(
                "output_contract",
                "STATUS_VALUES",
                "status_values must contain exactly success and partial",
            )
        allowed = self.contract.get("allowed_verdicts", list(VERDICTS))
        if allowed != list(VERDICTS):
            self.error("output_contract", "VERDICT_SET", "allowed_verdicts must be the four specified verdicts")
        components = self.contract.get("allowed_component_dispositions", list(DISPOSITIONS))
        if components != list(DISPOSITIONS):
            self.error(
                "output_contract",
                "DISPOSITION_SET",
                "allowed_component_dispositions must exclude mixed",
            )

    def require_result_fields(self):
        if not isinstance(self.result, dict):
            self.error("required_result_fields", "RESULT_NOT_OBJECT", "result must be an object")
            self.result = {}
            return
        required = self.contract.get("required_result_fields", [])
        if is_string_list(required):
            for field in required:
                if field not in self.result:
                    self.error(
                        "required_result_fields",
                        "MISSING_RESULT_FIELD",
                        "required output_contract field absent: " + field,
                    )
        case_id_field = self.contract.get("case_id_field", "case_id")
        if self.result.get(case_id_field) != self.case.get("case_id"):
            self.error(
                "result_consistency",
                "CASE_ID_CHANGED",
                "result case_id does not equal the original case_id",
            )
        self.check_result_artifact_path("report_field", "adjudication_report", self.report_path)
        self.check_result_artifact_path("ledger_field", "adjudication_ledger", self.ledger_path)

    def check_result_artifact_path(self, contract_key, default_key, actual_path):
        key = self.contract.get(contract_key, default_key)
        if key not in self.result:
            return
        value = self.result.get(key)
        if not is_nonempty_string(value):
            self.error("result_consistency", "ARTIFACT_PATH", key + " must be a nonempty string")
        elif Path(value).name != actual_path.name:
            self.error(
                "result_consistency",
                "ARTIFACT_BASENAME",
                "{0} basename {1!r} does not match {2!r}".format(key, value, actual_path.name),
            )

    def build_correction_index(self):
        corrections = self.ledger.get("corrected_claims", [])
        if not isinstance(corrections, list):
            self.error("corrected_claim_links", "CORRECTIONS_ARRAY", "corrected_claims must be an array")
            return
        for index, correction in enumerate(corrections):
            if not isinstance(correction, dict):
                self.error("corrected_claim_links", "CORRECTION_OBJECT", "correction {0} is not an object".format(index))
                continue
            correction_id = correction.get("corrected_claim_id")
            if not is_nonempty_string(correction_id):
                self.error("corrected_claim_links", "CORRECTION_ID", "correction lacks corrected_claim_id")
                continue
            if correction_id in self.corrections_by_id:
                self.error("corrected_claim_links", "DUPLICATE_CORRECTION", "duplicate corrected_claim_id: " + correction_id)
                continue
            self.corrections_by_id[correction_id] = correction
            input_id = correction.get("input_id")
            if input_id not in self.case_by_id:
                self.error("corrected_claim_links", "CORRECTION_UNKNOWN_INPUT", "correction has unknown input_id: " + str(input_id))
            elif correction.get("corrected_text") == self.case_by_id[input_id].get("claim"):
                self.error("corrected_claim_links", "CORRECTION_REPEATS_ORIGINAL", "corrected_text equals original for " + correction_id)
            if not is_nonempty_string(correction.get("corrected_text")):
                self.error("corrected_claim_links", "CORRECTION_TEXT", "corrected_text must be nonempty for " + correction_id)
            if not is_nonempty_string(correction.get("rationale")):
                self.error("corrected_claim_links", "CORRECTION_RATIONALE", "rationale missing for " + correction_id)
            source_ids = correction.get("source_ids")
            if not is_string_list(source_ids) or not source_ids:
                self.error("corrected_claim_links", "CORRECTION_SOURCES", "source_ids must be nonempty for " + correction_id)
            else:
                for source_id in source_ids:
                    if source_id not in self.source_text:
                        self.error("evidence_sources", "UNKNOWN_CORRECTION_SOURCE", "unknown correction source_id: " + source_id)

    def require_coverage_and_index(self):
        records = self.ledger.get("assertions")
        if not isinstance(records, list):
            self.error("input_id_coverage", "LEDGER_ASSERTIONS", "ledger assertions must be an array")
            return []
        counts = Counter()
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                self.error("input_id_coverage", "LEDGER_RECORD_OBJECT", "ledger record {0} is not an object".format(index))
                continue
            input_id = record.get("input_id")
            if not is_nonempty_string(input_id):
                self.error("input_id_coverage", "LEDGER_INPUT_ID", "ledger record {0} lacks input_id".format(index))
                continue
            counts[input_id] += 1
            if input_id not in self.records_by_id:
                self.records_by_id[input_id] = record
        missing = [input_id for input_id in self.input_ids if counts[input_id] == 0]
        extra = [input_id for input_id in counts if input_id not in self.case_by_id]
        duplicate = [input_id for input_id, count in counts.items() if count != 1]
        for input_id in missing:
            self.error("input_id_coverage", "SKIPPED_INPUT_ID", "input_id missing from ledger: " + input_id)
        for input_id in extra:
            self.error("input_id_coverage", "EXTRA_INPUT_ID", "unknown ledger input_id: " + input_id)
        for input_id in duplicate:
            self.error("input_id_coverage", "DUPLICATE_LEDGER_ID", "input_id does not occur exactly once: " + input_id)
        self.coverage_ok = not missing and not extra and not duplicate
        actual_order = [record.get("input_id") for record in records if isinstance(record, dict)]
        if actual_order != self.input_ids:
            self.error("input_order", "INPUT_ORDER", "ledger input order differs from case input order")
        return records

    def validate_evidence(self, input_id, component_id, disposition, evidence):
        if not isinstance(evidence, list) or not evidence:
            self.error(
                "evidence_sources",
                "EVIDENCE_ARRAY",
                "evidence must be nonempty for {0}/{1}".format(input_id, component_id),
            )
            return
        stances = []
        for index, item in enumerate(evidence):
            if not isinstance(item, dict):
                self.error("evidence_sources", "EVIDENCE_OBJECT", "evidence item must be an object")
                continue
            source_id = item.get("source_id")
            if source_id not in self.source_text:
                self.error(
                    "evidence_sources",
                    "UNKNOWN_EVIDENCE_SOURCE",
                    "unknown source_id {0!r} at {1}/{2}".format(source_id, input_id, component_id),
                )
            quote = item.get("quote")
            if not is_nonempty_string(quote):
                self.error("evidence_quotes", "EVIDENCE_QUOTE", "quote missing at {0}/{1}".format(input_id, component_id))
            elif source_id in self.source_text and quote not in self.source_text[source_id]:
                self.error(
                    "evidence_quotes",
                    "QUOTE_NOT_IN_SOURCE",
                    "quote is not an exact substring at {0}/{1} evidence {2}".format(input_id, component_id, index),
                )
            if not is_nonempty_string(item.get("location")):
                self.error("evidence_sources", "EVIDENCE_LOCATION", "location missing at {0}/{1}".format(input_id, component_id))
            stance = item.get("stance")
            if stance not in STANCES:
                self.error("evidence_sources", "EVIDENCE_STANCE", "invalid stance at {0}/{1}".format(input_id, component_id))
            else:
                stances.append(stance)
        if disposition == "supported" and "support" not in stances:
            self.error(
                "support_and_reverse_evidence",
                "SUPPORT_EVIDENCE_REQUIRED",
                "supported component lacks support evidence: {0}/{1}".format(input_id, component_id),
            )
        if disposition == "contradicted" and "reverse" not in stances:
            self.error(
                "support_and_reverse_evidence",
                "REVERSE_EVIDENCE_REQUIRED",
                "contradicted component lacks reverse evidence: {0}/{1}".format(input_id, component_id),
            )

    def validate_records(self):
        for input_id in self.input_ids:
            record = self.records_by_id.get(input_id)
            if record is None:
                continue
            if record.get("original_claim") != self.case_by_id[input_id]["claim"]:
                self.error(
                    "original_text_preserved",
                    "ORIGINAL_CLAIM_CHANGED",
                    "original_claim differs from case claim for " + input_id,
                )
            decision_status = record.get("decision_status")
            verdict = record.get("verdict")
            components = record.get("components")
            corrected_ids = record.get("corrected_claim_ids")
            if decision_status not in ("adjudicated", "pending"):
                self.error("state_machine", "DECISION_STATUS", "invalid decision_status for " + input_id)
                continue
            if decision_status == "pending":
                if verdict is not None:
                    self.error("pending_shape", "PENDING_VERDICT", "pending verdict must be null for " + input_id)
                if components != []:
                    self.error("pending_shape", "PENDING_COMPONENTS", "pending components must be [] for " + input_id)
                if corrected_ids != []:
                    self.error("pending_shape", "PENDING_CORRECTIONS", "pending corrected_claim_ids must be [] for " + input_id)
                if record.get("review_disposition") != "pending":
                    self.error("pending_shape", "PENDING_REVIEW", "pending review_disposition must be pending for " + input_id)
                continue
            self.adjudicated_count += 1
            if verdict in self.verdict_counts:
                self.verdict_counts[verdict] += 1
            if verdict not in VERDICTS:
                self.error("component_verdict_logic", "VERDICT", "invalid verdict for " + input_id)
            if record.get("review_disposition") not in REVIEW_DISPOSITIONS:
                self.error("state_machine", "REVIEW_DISPOSITION", "invalid review_disposition for " + input_id)
            if not isinstance(components, list) or not components:
                self.error("component_verdict_logic", "COMPONENTS", "adjudicated components must be nonempty for " + input_id)
                components = []
            dispositions = []
            component_ids = set()
            for index, component in enumerate(components):
                if not isinstance(component, dict):
                    self.error("component_verdict_logic", "COMPONENT_OBJECT", "component must be an object for " + input_id)
                    continue
                component_id = component.get("component_id")
                if not is_nonempty_string(component_id):
                    self.error("component_verdict_logic", "COMPONENT_ID", "component_id missing for " + input_id)
                    component_id = "index-{0}".format(index)
                if component_id in component_ids:
                    self.error("component_verdict_logic", "DUPLICATE_COMPONENT", "duplicate component_id for " + input_id)
                component_ids.add(component_id)
                for field in ("text", "claim_nature", "evidence_basis", "rationale"):
                    if not is_nonempty_string(component.get(field)):
                        self.error(
                            "component_verdict_logic",
                            "COMPONENT_FIELD",
                            "{0} missing/nonempty violation at {1}/{2}".format(field, input_id, component_id),
                        )
                disposition = component.get("disposition")
                if disposition not in DISPOSITIONS:
                    self.error(
                        "component_verdict_logic",
                        "COMPONENT_DISPOSITION",
                        "invalid disposition at {0}/{1}".format(input_id, component_id),
                    )
                else:
                    dispositions.append(disposition)
                self.validate_evidence(input_id, component_id, disposition, component.get("evidence"))
            expected_count = 1 if not self.case_by_id[input_id]["compound"] else 2
            if not self.case_by_id[input_id]["compound"] and len(components) != expected_count:
                self.error("component_verdict_logic", "ATOMIC_COMPONENT_COUNT", "atomic assertion must have one component for " + input_id)
            if self.case_by_id[input_id]["compound"] and len(components) < expected_count:
                self.error("component_verdict_logic", "COMPOUND_NOT_SPLIT", "compound assertion needs at least two components for " + input_id)
            if dispositions and len(dispositions) == len(components):
                distinct = set(dispositions)
                if verdict == "mixed" and len(distinct) < 2:
                    self.error(
                        "component_verdict_logic",
                        "ILLEGAL_MIXED",
                        "mixed requires at least two different dispositions for " + input_id,
                    )
                expected_verdict = dispositions[0] if len(distinct) == 1 else "mixed"
                if verdict in VERDICTS and verdict != expected_verdict:
                    self.error(
                        "component_verdict_logic",
                        "VERDICT_COMPONENT_MISMATCH",
                        "{0} has verdict {1}, expected {2}".format(input_id, verdict, expected_verdict),
                    )
            if not is_string_list(corrected_ids):
                self.error("corrected_claim_links", "CORRECTED_IDS_ARRAY", "corrected_claim_ids must be an array for " + input_id)
                corrected_ids = []
            if len(set(corrected_ids)) != len(corrected_ids):
                self.error("corrected_claim_links", "DUPLICATE_CORRECTION_LINK", "duplicate corrected link for " + input_id)
            if verdict == "supported" and corrected_ids:
                self.error("corrected_claim_links", "SUPPORTED_HAS_CORRECTION", "supported assertion has corrections for " + input_id)
            for correction_id in corrected_ids:
                self.used_correction_ids.append(correction_id)
                correction = self.corrections_by_id.get(correction_id)
                if correction is None:
                    self.error(
                        "corrected_claim_links",
                        "MISSING_CORRECTED_CLAIM",
                        "unknown corrected_claim_id {0} at {1}".format(correction_id, input_id),
                    )
                elif correction.get("input_id") != input_id:
                    self.error(
                        "corrected_claim_links",
                        "CORRECTION_WRONG_INPUT",
                        "corrected claim {0} does not link back to {1}".format(correction_id, input_id),
                    )
        self.all_adjudicated = self.coverage_ok and self.adjudicated_count == len(self.input_ids)

    def validate_correction_closure(self):
        used_counts = Counter(self.used_correction_ids)
        for correction_id in self.corrections_by_id:
            if used_counts[correction_id] != 1:
                self.error(
                    "corrected_claim_links",
                    "CORRECTION_REFERENCE_COUNT",
                    "corrected claim must be referenced exactly once: " + correction_id,
                )
        for correction_id in used_counts:
            if correction_id not in self.corrections_by_id:
                continue
            if used_counts[correction_id] != 1:
                self.error(
                    "corrected_claim_links",
                    "CORRECTION_REFERENCE_COUNT",
                    "corrected claim must be referenced exactly once: " + correction_id,
                )

    def validate_sources_and_change_records(self):
        ledger_sources = self.ledger.get("sources")
        if not is_string_list(ledger_sources):
            self.error("source_inventory", "LEDGER_SOURCES", "ledger sources must be a string array")
        elif ledger_sources != self.source_ids:
            self.error(
                "source_inventory",
                "SOURCE_INVENTORY",
                "ledger sources must equal case sources in original order without omissions",
            )
        if (
            is_string_list(ledger_sources)
            and len(ledger_sources) != len(set(ledger_sources))
        ):
            self.error("source_inventory", "DUPLICATE_LEDGER_SOURCE", "ledger sources contains duplicates")
        for field in ("uncertainty", "change_records"):
            if not isinstance(self.ledger.get(field), list):
                self.error("result_consistency", "LEDGER_ARRAY", "ledger " + field + " must be an array")
            if field in self.result and self.result.get(field) != self.ledger.get(field):
                self.error("result_consistency", "RESULT_LEDGER_MISMATCH", "result and ledger differ for " + field)
        if "sources" in self.result and self.result.get("sources") != ledger_sources:
            self.error("result_consistency", "RESULT_SOURCES_MISMATCH", "result sources differ from ledger sources")
        changes = self.ledger.get("change_records", [])
        if not isinstance(changes, list):
            return
        change_ids = set()
        linked_corrections = []
        for index, change in enumerate(changes):
            if not isinstance(change, dict):
                self.error("change_records", "CHANGE_OBJECT", "change record {0} is not an object".format(index))
                continue
            change_id = change.get("change_id")
            if not is_nonempty_string(change_id):
                self.error("change_records", "CHANGE_ID", "change_id missing at index {0}".format(index))
            elif change_id in change_ids:
                self.error("change_records", "DUPLICATE_CHANGE_ID", "duplicate change_id: " + change_id)
            else:
                change_ids.add(change_id)
            if change.get("input_id") not in self.case_by_id:
                self.error("change_records", "CHANGE_UNKNOWN_INPUT", "change record has unknown input_id")
            if not is_nonempty_string(change.get("change_type")):
                self.error("change_records", "CHANGE_TYPE", "change_type missing for " + str(change_id))
            if change.get("original_preserved") is not True:
                self.error("change_records", "ORIGINAL_PRESERVED_FLAG", "original_preserved must be true for " + str(change_id))
            correction_ids = change.get("corrected_claim_ids")
            if not is_string_list(correction_ids) or not correction_ids:
                self.error("change_records", "CHANGE_CORRECTIONS", "change record corrected_claim_ids must be nonempty")
                continue
            linked_corrections.extend(correction_ids)
            for correction_id in correction_ids:
                correction = self.corrections_by_id.get(correction_id)
                if correction is None:
                    self.error("change_records", "CHANGE_UNKNOWN_CORRECTION", "unknown corrected claim: " + correction_id)
                elif correction.get("input_id") != change.get("input_id"):
                    self.error("change_records", "CHANGE_WRONG_INPUT", "change record and correction input differ")
        if set(linked_corrections) != set(self.corrections_by_id):
            self.error(
                "change_records",
                "UNRECORDED_CORRECTION",
                "every corrected claim must occur in at least one change record",
            )

    def validate_result_and_state(self):
        if "input_count" in self.result and self.result.get("input_count") != len(self.input_ids):
            self.error("result_consistency", "INPUT_COUNT", "result input_count differs from case")
        if "adjudicated_count" in self.result and self.result.get("adjudicated_count") != self.adjudicated_count:
            self.error("result_consistency", "ADJUDICATED_COUNT", "result adjudicated_count is not actual")
        if "verdict_counts" in self.result and self.result.get("verdict_counts") != self.verdict_counts:
            self.error("result_consistency", "VERDICT_COUNTS", "result verdict_counts are not actual")
        if self.ledger.get("case_id") != self.case.get("case_id"):
            self.error("result_consistency", "LEDGER_CASE_ID", "ledger case_id differs from case")
        complete = self.ledger.get("audit_complete")
        if type(complete) is not bool:
            self.error("state_machine", "AUDIT_COMPLETE_TYPE", "audit_complete must be boolean")
            complete = False
        if complete and not self.all_adjudicated:
            self.error(
                "state_machine",
                "FALSE_COMPLETE",
                "audit_complete=true requires full coverage and all inputs adjudicated",
            )
        expected_status = "success" if self.all_adjudicated and complete else "partial"
        status_field = self.contract.get("status_field", "status")
        actual_status = self.result.get(status_field)
        if actual_status not in ("success", "partial"):
            self.error("state_machine", "RESULT_STATUS", "result status must be success or partial")
        elif actual_status != expected_status:
            self.error(
                "state_machine",
                "STATUS_MISMATCH",
                "result status {0}, expected {1}".format(actual_status, expected_status),
            )
        return expected_status

    def run(self):
        if not isinstance(self.ledger, dict):
            self.error("input_id_coverage", "LEDGER_NOT_OBJECT", "ledger must be an object")
            self.ledger = {}
        self.require_case_schema()
        self.require_contract()
        self.require_result_fields()
        self.build_correction_index()
        self.require_coverage_and_index()
        self.validate_records()
        self.validate_correction_closure()
        self.validate_sources_and_change_records()
        expected_status = self.validate_result_and_state()
        return self.make_report(expected_status)

    def make_report(self, expected_status):
        pending = []
        for input_id in self.input_ids:
            record = self.records_by_id.get(input_id)
            if record is not None and record.get("decision_status") == "pending":
                pending.append(input_id)
        rejected = sum(
            1
            for record in self.records_by_id.values()
            if record.get("decision_status") == "adjudicated"
            and record.get("review_disposition") == "reject"
        )
        if "output_contract" not in self.checks:
            self.checks["output_contract"] = True
        report = {
            "schema_version": "1.0",
            "synthetic": self.case.get("synthetic") is True,
            "notice": "SYNTHETIC audit fixture; not a formal scientific result."
            if self.case.get("synthetic") is True
            else "Adjudication audit report.",
            "case_id": self.case.get("case_id"),
            "valid": not self.errors,
            "audit_complete": self.ledger.get("audit_complete") is True,
            "expected_process_status": expected_status,
            "input_count": len(self.input_ids),
            "ledger_record_count": len(self.records_by_id),
            "adjudicated_count": self.adjudicated_count,
            "pending_input_ids": pending,
            "uncovered_input_ids": [input_id for input_id in self.input_ids if input_id not in self.records_by_id],
            "verdict_counts": self.verdict_counts,
            "rejected_review_count": rejected,
            "checks": [
                {"check": name, "passed": self.checks[name]}
                for name in CHECK_NAMES
            ],
            "errors": self.errors,
        }
        return report


def write_json(path, payload):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def build_result(case, contract, ledger, ledger_path, report_path):
    """Emit a result for known contract fields, used by reproducible fixtures."""
    required = contract.get("required_result_fields", [])
    case_id_field = contract.get("case_id_field", "case_id")
    status_field = contract.get("status_field", "status")
    report_field = contract.get("report_field", "adjudication_report")
    ledger_field = contract.get("ledger_field", "adjudication_ledger")
    assertions = case.get("assertions", [])
    input_ids = [item.get("input_id") for item in assertions if isinstance(item, dict)]
    records = ledger.get("assertions", [])
    record_counts = Counter(
        item.get("input_id") for item in records if isinstance(item, dict)
    )
    unique_records = {}
    for item in records:
        if isinstance(item, dict) and item.get("input_id") not in unique_records:
            unique_records[item.get("input_id")] = item
    adjudicated = [
        input_id
        for input_id in input_ids
        if input_id in unique_records
        and record_counts[input_id] == 1
        and unique_records[input_id].get("decision_status") == "adjudicated"
    ]
    verdict_counts = dict((verdict, 0) for verdict in VERDICTS)
    for input_id in adjudicated:
        verdict = unique_records[input_id].get("verdict")
        if verdict in verdict_counts:
            verdict_counts[verdict] += 1
    covered_once = (
        len(record_counts) == len(input_ids)
        and all(record_counts[input_id] == 1 for input_id in input_ids)
    )
    complete = ledger.get("audit_complete") is True
    status = (
        "success"
        if covered_once and len(adjudicated) == len(input_ids) and complete
        else "partial"
    )
    values = {
        case_id_field: case.get("case_id"),
        status_field: status,
        report_field: Path(report_path).name,
        ledger_field: Path(ledger_path).name,
        "input_count": len(input_ids),
        "adjudicated_count": len(adjudicated),
        "verdict_counts": verdict_counts,
        "sources": ledger.get("sources"),
        "uncertainty": ledger.get("uncertainty"),
        "change_records": ledger.get("change_records"),
    }
    result = {}
    for field in required:
        if field not in values:
            raise ValueError("--emit-result cannot infer required field: " + field)
        result[field] = values[field]
    return result


def write_report(path, report):
    write_json(path, report)


def emergency_report(case_id, stage, message):
    return {
        "schema_version": "1.0",
        "synthetic": False,
        "notice": "Adjudication audit could not complete input parsing.",
        "case_id": case_id,
        "valid": False,
        "audit_complete": False,
        "expected_process_status": "partial",
        "input_count": 0,
        "ledger_record_count": 0,
        "adjudicated_count": 0,
        "pending_input_ids": [],
        "uncovered_input_ids": [],
        "verdict_counts": dict((verdict, 0) for verdict in VERDICTS),
        "rejected_review_count": 0,
        "checks": [{"check": name, "passed": False} for name in CHECK_NAMES],
        "errors": [{"code": stage, "message": message}],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, help="UTF-8 input case.json")
    parser.add_argument("--task", required=True, help="task.md with output_contract JSON fence")
    parser.add_argument("--ledger", required=True, help="adjudication ledger to validate")
    parser.add_argument("--result", required=True, help="result.json output/input path")
    parser.add_argument("--report", required=True, help="report path, written on success or failure")
    parser.add_argument(
        "--emit-result",
        action="store_true",
        help="first generate result from ledger for known output_contract fields, then validate it",
    )
    args = parser.parse_args(argv)
    case_id = None
    try:
        case = read_json(args.case)
        if isinstance(case, dict):
            case_id = case.get("case_id")
        contract = parse_task_contract(args.task)
        ledger = read_json(args.ledger)
        if args.emit_result:
            result = build_result(
                case, contract, ledger, args.ledger, args.report
            )
            write_json(args.result, result)
        else:
            result = read_json(args.result)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        report = emergency_report(case_id, "INPUT_PARSE_ERROR", str(exc))
        try:
            write_report(args.report, report)
        except OSError as write_exc:
            print("report write failed: {0}".format(write_exc), file=sys.stderr)
            return 2
        print("INVALID: {0}".format(exc), file=sys.stderr)
        return 2
    validator = Validator(case, contract, ledger, result, args.ledger, args.report)
    report = validator.run()
    write_report(args.report, report)
    if report["valid"]:
        print(
            "VALID: case_id={0} status={1} inputs={2} adjudicated={3} report={4}".format(
                report["case_id"],
                report["expected_process_status"],
                report["input_count"],
                report["adjudicated_count"],
                args.report,
            )
        )
        return 0
    print(
        "INVALID: case_id={0} errors={1} report={2}".format(
            report["case_id"], len(report["errors"]), args.report
        ),
        file=sys.stderr,
    )
    for error in report["errors"]:
        print("{0}: {1}".format(error["code"], error["message"]), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
