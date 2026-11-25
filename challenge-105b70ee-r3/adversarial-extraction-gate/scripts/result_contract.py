"""Shared, standard-library-only contract checks for evidence-bound extraction.

These checks establish internal and source-corpus consistency only. They cannot
establish that an extraction is semantically correct; see references/decoy-review.md.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

TOP_KEYS = ("case_id", "status", "result", "claims", "uncertainties")
FIELD_KEYS = (
    "field_id", "status", "subject", "scalar", "units", "statistic",
    "experimental_condition", "condition", "comparator", "paragraph_id",
    "quote", "evidence", "notes",
)
STATUSES = {"answered", "partial", "insufficient_evidence", "input_error"}
FIELD_STATUSES = {"reported", "not_reported", "source_conflict", "extraction_failed"}
EVIDENCE_KEYS = ("source_id", "page", "paragraph_id", "quote")
HEDGE_RE = re.compile(
    r"\b(?:may|might|could|possibly|potentially|suggests?|suggested|appears?|appeared|seems?|seemed)\b"
    r"|可能|或许|提示|似乎|推测",
    re.IGNORECASE,
)
PROMOTED_CLAIM_KINDS = {"explicit_conclusion", "causal_conclusion", "established_fact"}


class InputDataError(ValueError):
    """Malformed input/resource data, distinct from a rejected extraction."""


def _unique_object(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    obj: Dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise InputDataError("duplicate JSON object key: %s" % key)
        obj[key] = value
    return obj


def _bad_constant(token: str) -> None:
    raise InputDataError("non-finite JSON number is forbidden: %s" % token)


def load_json(path: Path) -> Any:
    try:
        text = Path(path).read_text(encoding="utf-8")
        return json.loads(text, object_pairs_hook=_unique_object, parse_constant=_bad_constant)
    except InputDataError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InputDataError("cannot read UTF-8 JSON %s: %s" % (path, exc)) from exc


def parse_targets(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        records = None
        for container in ("fields", "target_fields", "targets"):
            if container in data:
                records = data[container]
                break
        if records is None:
            raise InputDataError("target-fields JSON needs a fields, target_fields, or targets array")
    else:
        raise InputDataError("target-fields JSON must be an object or array")
    if not isinstance(records, list) or not records:
        raise InputDataError("target field list must be a non-empty array")
    result: List[Dict[str, Any]] = []
    seen = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict) or not isinstance(record.get("field_id"), str) or not record["field_id"].strip():
            raise InputDataError("target field %d lacks a nonempty string field_id" % index)
        field_id = record["field_id"]
        if field_id in seen:
            raise InputDataError("duplicate requested field_id: %s" % field_id)
        seen.add(field_id)
        result.append(record)
    return result


def corpus_index(data: Any) -> Dict[Tuple[str, str], Dict[str, Any]]:
    if not isinstance(data, dict) or not isinstance(data.get("sources"), list):
        raise InputDataError("source corpus must be an object with a sources array")
    index: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for source in data["sources"]:
        if not isinstance(source, dict) or not isinstance(source.get("source_id"), str):
            raise InputDataError("every corpus source needs a string source_id")
        source_id = source["source_id"]
        paragraphs = source.get("paragraphs")
        if not isinstance(paragraphs, list):
            raise InputDataError("corpus source %s needs a paragraphs array" % source_id)
        for paragraph in paragraphs:
            if not isinstance(paragraph, dict):
                raise InputDataError("corpus paragraph in %s is not an object" % source_id)
            paragraph_id = paragraph.get("paragraph_id")
            text = paragraph.get("text")
            if not isinstance(paragraph_id, str) or not paragraph_id or not isinstance(text, str):
                raise InputDataError("corpus paragraph in %s needs paragraph_id and text" % source_id)
            key = (source_id, paragraph_id)
            if key in index:
                raise InputDataError("duplicate corpus locator: %s/%s" % key)
            if "page" not in paragraph:
                raise InputDataError("corpus paragraph %s/%s lacks page" % key)
            index[key] = {
                "source_id": source_id,
                "paragraph_id": paragraph_id,
                "page": paragraph["page"],
                "text": text,
            }
    return index


def issue(code: str, path: str, message: str) -> Dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _same_page(left: Any, right: Any) -> bool:
    return left == right or (left is not None and right is not None and str(left) == str(right))


def _literal_in_quote(value: Any, quote: str) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, float) and not math.isfinite(value):
        return False
    if isinstance(value, (int, float)):
        token = str(value)
        return re.search(r"(?<![\w.])%s(?![\w.])" % re.escape(token), quote) is not None
    if isinstance(value, str):
        return bool(value.strip()) and value in quote
    return False


def _evidence_issues(
    evidence: Any,
    path: str,
    index: Mapping[Tuple[str, str], Mapping[str, Any]],
) -> List[Dict[str, str]]:
    if not isinstance(evidence, dict):
        return [issue("EVIDENCE_NOT_OBJECT", path, "evidence must be an object")]
    problems = []
    for key in EVIDENCE_KEYS:
        if key not in evidence:
            problems.append(issue("MISSING_EVIDENCE_KEY", path, "missing evidence key: %s" % key))
    if problems:
        return problems
    source_id, paragraph_id = evidence["source_id"], evidence["paragraph_id"]
    quote = evidence["quote"]
    if not isinstance(source_id, str) or not isinstance(paragraph_id, str) or not isinstance(quote, str) or not quote:
        return [issue("INVALID_EVIDENCE_TYPES", path, "source_id/paragraph_id/quote must be strings; quote cannot be empty")]
    paragraph = index.get((source_id, paragraph_id))
    if paragraph is None:
        return [issue("UNKNOWN_EVIDENCE_LOCATOR", path, "source_id/paragraph_id is absent from the supplied corpus")]
    if not _same_page(evidence["page"], paragraph["page"]):
        problems.append(issue("EVIDENCE_PAGE_MISMATCH", path + ".page", "page does not match the corpus paragraph"))
    if quote not in paragraph["text"]:
        problems.append(issue("QUOTE_NOT_IN_PARAGRAPH", path + ".quote", "quote is not a verbatim substring of the cited paragraph"))
    return problems


def _target_value(target: Mapping[str, Any], key: str) -> Any:
    if key == "experimental_condition":
        return target.get("experimental_condition", target.get("condition"))
    return target.get(key)


def _validate_field(
    field: Any,
    target: Mapping[str, Any],
    path: str,
    index: Mapping[Tuple[str, str], Mapping[str, Any]],
) -> List[Dict[str, str]]:
    if not isinstance(field, dict):
        return [issue("FIELD_NOT_OBJECT", path, "field result must be an object")]
    problems = []
    for key in FIELD_KEYS:
        if key not in field:
            problems.append(issue("MISSING_FIELD_KEY", path, "missing required field key: %s" % key))
    if problems:
        return problems
    status = field["status"]
    if status not in FIELD_STATUSES:
        problems.append(issue("INVALID_FIELD_STATUS", path + ".status", "unknown field status"))
        return problems
    if field["experimental_condition"] != field["condition"]:
        problems.append(issue("CONDITION_ALIAS_MISMATCH", path + ".condition", "condition must exactly mirror experimental_condition"))
    for key in ("subject", "experimental_condition", "comparator"):
        expected = _target_value(target, key)
        if expected is not None and field[key] != expected:
            problems.append(issue(
                {"subject": "SUBJECT_MISMATCH", "experimental_condition": "CONDITION_MISMATCH", "comparator": "COMPARATOR_MISMATCH"}[key],
                path + "." + key,
                "value does not preserve the requested %s" % key,
            ))
    if not isinstance(field["notes"], (str, list)):
        problems.append(issue("INVALID_NOTES", path + ".notes", "notes must be a string or an array"))
    evidence = field["evidence"]
    primary: Optional[Mapping[str, Any]] = evidence if isinstance(evidence, dict) else None

    if status == "reported":
        if not _literal_in_quote(field["scalar"], field["quote"] if isinstance(field["quote"], str) else ""):
            problems.append(issue("SCALAR_ABSENT_FROM_QUOTE", path + ".scalar", "reported scalar is not literally present in the field quote"))
        if field["units"] is not None:
            if not isinstance(field["units"], str) or not field["units"] or not isinstance(field["quote"], str) or field["units"] not in field["quote"]:
                problems.append(issue("UNIT_NOT_IN_QUOTE", path + ".units", "units must be preserved as a nonempty literal substring of the quote"))
        if target.get("statistic_required") and (not isinstance(field["statistic"], str) or not field["statistic"].strip()):
            problems.append(issue("STATISTIC_DROPPED", path + ".statistic", "the target explicitly requires a statistic"))
        if field["statistic"] is not None:
            if not isinstance(field["statistic"], str) or not isinstance(field["quote"], str) or field["statistic"] not in field["quote"]:
                problems.append(issue("STATISTIC_NOT_IN_QUOTE", path + ".statistic", "statistic must be a literal substring of the quote"))
        if primary is None:
            problems.append(issue("REPORTED_REQUIRES_EVIDENCE", path + ".evidence", "reported requires one evidence object"))
    else:
        if status in {"not_reported", "source_conflict", "extraction_failed"}:
            for key in ("scalar", "units", "statistic"):
                if field[key] is not None:
                    problems.append(issue("VALUE_ON_%s" % status.upper(), path + "." + key, "%s requires null %s" % (status, key)))
        if status in {"not_reported", "extraction_failed"} and evidence not in (None, {}) and primary is None:
            problems.append(issue("EVIDENCE_NOT_OBJECT", path + ".evidence", "optional evidence must be one object or null"))
        if status in {"not_reported", "extraction_failed"} and not field["notes"]:
            problems.append(issue("MISSING_LIMIT_NOTE", path + ".notes", "%s requires an honest scope/failure note" % status))
        if status == "source_conflict":
            if not isinstance(evidence, list) or len(evidence) < 2:
                problems.append(issue("SOURCE_CONFLICT_REQUIRES_TWO_SOURCES", path + ".evidence", "source_conflict needs at least two distinct evidence objects"))
            else:
                locators = {(e.get("source_id"), e.get("paragraph_id")) for e in evidence if isinstance(e, dict)}
                quotes = {e.get("quote").strip() for e in evidence if isinstance(e, dict) and isinstance(e.get("quote"), str)}
                if len(locators) < 2 or len(quotes) < 2:
                    problems.append(issue("SOURCE_CONFLICT_NOT_INDEPENDENT", path + ".evidence", "conflict evidence needs distinct locators and nonidentical quotes"))
            if not field["notes"]:
                problems.append(issue("MISSING_CONFLICT_EXPLANATION", path + ".notes", "explain the unresolved disagreement without choosing a winner"))
            if field["quote"] is not None or field["paragraph_id"] is not None:
                problems.append(issue("CONFLICT_PRIMARY_QUOTE_AMBIGUOUS", path, "source_conflict keeps top-level quote/paragraph_id null; use evidence list"))
        for item_number, item in enumerate(evidence if isinstance(evidence, list) else []):
            problems.extend(_evidence_issues(item, "%s.evidence[%d]" % (path, item_number), index))

    if primary is not None:
        problems.extend(_evidence_issues(primary, path + ".evidence", index))
        if field["paragraph_id"] != primary.get("paragraph_id"):
            problems.append(issue("FIELD_EVIDENCE_PARAGRAPH_MISMATCH", path + ".paragraph_id", "field and primary evidence paragraph_id differ"))
        if field["quote"] != primary.get("quote"):
            problems.append(issue("FIELD_EVIDENCE_QUOTE_MISMATCH", path + ".quote", "field quote and primary evidence quote differ"))
    elif status == "reported":
        if field["quote"] is not None or field["paragraph_id"] is not None:
            problems.append(issue("PRIMARY_EVIDENCE_REQUIRED", path, "reported top-level quote/paragraph_id need primary evidence"))
    elif status in {"not_reported", "extraction_failed"} and (field["quote"] is not None or field["paragraph_id"] is not None):
        problems.append(issue("ORPHAN_QUOTE", path, "top-level quote/paragraph_id require an evidence object"))
    return problems


def _validate_claims(
    claims: Any,
    index: Mapping[Tuple[str, str], Mapping[str, Any]],
) -> List[Dict[str, str]]:
    if not isinstance(claims, list):
        return [issue("CLAIMS_NOT_ARRAY", "claims", "claims must be an array")]
    problems = []
    for number, claim in enumerate(claims):
        path = "claims[%d]" % number
        if not isinstance(claim, dict):
            problems.append(issue("CLAIM_NOT_OBJECT", path, "claim must be an object"))
            continue
        for key in ("claim_id", "kind", "statement", "source_id", "location", "evidence"):
            if key not in claim:
                problems.append(issue("MISSING_CLAIM_KEY", path, "missing claim key: %s" % key))
        if not all(key in claim for key in ("claim_id", "kind", "statement", "source_id", "location", "evidence")):
            continue
        evidence = claim["evidence"]
        problems.extend(_evidence_issues(evidence, path + ".evidence", index))
        if not isinstance(claim["statement"], str) or not claim["statement"].strip():
            problems.append(issue("EMPTY_CLAIM", path + ".statement", "claim statement must be nonempty"))
        if isinstance(evidence, dict):
            if claim["source_id"] != evidence.get("source_id"):
                problems.append(issue("CLAIM_SOURCE_MISMATCH", path + ".source_id", "claim source_id differs from evidence"))
            location = claim["location"]
            if not isinstance(location, dict) or location.get("paragraph_id") != evidence.get("paragraph_id") or not _same_page(location.get("page"), evidence.get("page")):
                problems.append(issue("CLAIM_LOCATION_MISMATCH", path + ".location", "claim location must match evidence"))
            quote = evidence.get("quote")
            if claim["kind"] in PROMOTED_CLAIM_KINDS and isinstance(quote, str) and HEDGE_RE.search(quote) and not HEDGE_RE.search(claim["statement"]):
                problems.append(issue("HEDGED_CLAIM_PROMOTED", path + ".statement", "hedged evidence cannot support an unhedged promoted claim"))
    return problems


def validate_result(
    result: Any,
    targets: Sequence[Mapping[str, Any]],
    corpus: Any,
    expected_case_id: Optional[str] = None,
) -> List[Dict[str, str]]:
    index = corpus_index(corpus)
    problems: List[Dict[str, str]] = []
    if not isinstance(result, dict):
        return [issue("RESULT_NOT_OBJECT", "$", "result JSON must be an object")]
    for key in TOP_KEYS:
        if key not in result:
            problems.append(issue("MISSING_TOP_KEY", "$", "missing required top-level key: %s" % key))
    if problems:
        return problems
    if expected_case_id is not None and result["case_id"] != expected_case_id:
        problems.append(issue("CASE_ID_MISMATCH", "case_id", "case_id does not match /input/case.json"))
    if result["status"] not in STATUSES:
        problems.append(issue("INVALID_TOP_STATUS", "status", "unknown top-level status"))
    if not isinstance(result["result"], dict):
        return problems + [issue("RESULT_BODY_NOT_OBJECT", "result", "result must be an object")]
    fields = result["result"].get("fields")
    if not isinstance(fields, list):
        return problems + [issue("FIELDS_NOT_ARRAY", "result.fields", "fields must be an array")]
    mirrored = result["result"].get("field_results")
    if mirrored is not None and mirrored != fields:
        problems.append(issue("FIELD_RESULTS_NOT_MIRRORED", "result.field_results", "field_results must be an exact mirror of fields when present"))

    by_id: Dict[str, List[Tuple[int, Any]]] = {}
    for number, field in enumerate(fields):
        field_id = field.get("field_id") if isinstance(field, dict) else None
        if isinstance(field_id, str):
            by_id.setdefault(field_id, []).append((number, field))
        else:
            problems.append(issue("INVALID_FIELD_ID", "result.fields[%d]" % number, "field_id must be a string"))
    target_map = {target["field_id"]: target for target in targets}
    for field_id, entries in by_id.items():
        if field_id not in target_map:
            problems.append(issue("UNREQUESTED_FIELD_ID", "result.fields", "unrequested field_id: %s" % field_id))
        if len(entries) > 1:
            problems.append(issue("DUPLICATE_FIELD_ID", "result.fields", "field_id occurs more than once: %s" % field_id))
    for field_id, target in target_map.items():
        entries = by_id.get(field_id, [])
        if not entries:
            problems.append(issue("MISSING_FIELD_ID", "result.fields", "requested field_id is missing: %s" % field_id))
        elif len(entries) == 1:
            number, field = entries[0]
            problems.extend(_validate_field(field, target, "result.fields[%d]" % number, index))
    problems.extend(_validate_claims(result["claims"], index))
    if not isinstance(result["uncertainties"], list):
        problems.append(issue("UNCERTAINTIES_NOT_ARRAY", "uncertainties", "uncertainties must be an array"))
    for optional in ("sources", "change_records"):
        if optional in result and not isinstance(result[optional], list):
            problems.append(issue("OPTIONAL_KEY_NOT_ARRAY", optional, "%s must be an array when present" % optional))
    return problems
