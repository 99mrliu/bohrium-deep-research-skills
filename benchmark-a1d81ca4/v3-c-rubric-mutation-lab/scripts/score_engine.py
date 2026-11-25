#!/usr/bin/env python3
"""Deterministic, declarative 0/1/2 scorer. Standard library only.

The predicate language is data, not Python: no predicate or band is evaluated with
 eval/exec. See references/predicate_schema.md for the complete contract.
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
import unicodedata


class InputError(ValueError):
    """A safe, user-facing input or schema error."""


def _no_duplicate_keys(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise InputError("duplicate JSON object key: %s" % key)
        obj[key] = value
    return obj


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle, object_pairs_hook=_no_duplicate_keys)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InputError("cannot load JSON %s: %s" % (path, exc))


def dump_json(value, path=None):
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path is None:
        sys.stdout.write(text)
        return
    parent = os.path.dirname(os.path.abspath(path))
    try:
        os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except OSError as exc:
        raise InputError("cannot write JSON %s: %s" % (path, exc))


def canonical_hash(value):
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def normalize_text(value):
    """NFKC, common dash unification, casefolding, and whitespace folding."""
    value = unicodedata.normalize("NFKC", value)
    value = value.translate(str.maketrans({
        "−": "-", "–": "-", "—": "-", "‑": "-", "‒": "-",
    }))
    return " ".join(value.casefold().split())


def normalize_pattern(value):
    value = unicodedata.normalize("NFKC", value)
    return value.translate(str.maketrans({
        "−": "-", "–": "-", "—": "-", "‑": "-", "‒": "-",
    })).casefold()


def _alternatives(value, label):
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not value:
        raise InputError("%s must be a nonempty string or string array" % label)
    if any(not isinstance(entry, str) or not entry for entry in value):
        raise InputError("%s contains an empty or non-string alternative" % label)
    return value


def _number(value, label, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError("%s must be a finite JSON number" % label)
    if not math.isfinite(float(value)):
        raise InputError("%s must be finite" % label)
    if minimum is not None and float(value) < minimum:
        raise InputError("%s must be >= %s" % (label, minimum))
    return float(value)


def _compile_regex(node, path):
    alternatives = _alternatives(node.get("regex"), path + ".regex")
    flag_names = node.get("flags", [])
    if not isinstance(flag_names, list) or any(
        flag not in ("I", "M", "S") for flag in flag_names
    ):
        raise InputError("%s.flags may contain only I, M, S" % path)
    flags = 0
    for flag in flag_names:
        flags |= {"I": re.IGNORECASE, "M": re.MULTILINE, "S": re.DOTALL}[flag]
    return [(entry, re.compile(normalize_pattern(entry), flags))
            for entry in alternatives]


def _numeric_spec(node, path):
    spec = node["numeric"]
    if not isinstance(spec, dict):
        raise InputError("%s.numeric must be an object" % path)
    if spec.get("require_unit") is not True:
        raise InputError("%s.numeric.require_unit must be true" % path)
    units = _alternatives(spec.get("units"), path + ".numeric.units")
    comparison = spec.get("comparison")
    if comparison not in ("eq", "lt", "lte", "gt", "gte", "between"):
        raise InputError("%s.numeric.comparison is invalid" % path)
    if comparison == "between":
        low = _number(spec.get("min"), path + ".numeric.min")
        high = _number(spec.get("max"), path + ".numeric.max")
        if low > high:
            raise InputError("%s.numeric min exceeds max" % path)
        target = None
    else:
        target = _number(spec.get("target"), path + ".numeric.target")
        low = high = None
    tolerance = spec.get("tolerance")
    if not isinstance(tolerance, dict) or set(tolerance) != {"absolute", "relative"}:
        raise InputError(
            "%s.numeric.tolerance must contain exactly absolute and relative" % path
        )
    absolute = _number(tolerance["absolute"], path + ".numeric.absolute", 0)
    relative = _number(tolerance["relative"], path + ".numeric.relative", 0)
    normalized_units = sorted({normalize_text(unit) for unit in units},
                              key=lambda entry: (-len(entry), entry))
    if any(not unit for unit in normalized_units):
        raise InputError("%s.numeric.units normalizes to an empty unit" % path)
    unit_pattern = "|".join(re.escape(unit) for unit in normalized_units)
    # Units are mandatory. ASCII-looking boundaries prevent a number embedded in
    # an identifier from matching while still allowing CJK text around a value.
    pattern = re.compile(
        r"(?<![a-z0-9_.])(?P<number>[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
        r"(?:e[-+]?\d+)?)[ ]*(?P<unit>" + unit_pattern + r")(?![a-z0-9_])"
    )
    return {
        "comparison": comparison, "target": target, "min": low, "max": high,
        "absolute": absolute, "relative": relative, "units": normalized_units,
        "pattern": pattern,
    }


def validate_predicate(node, path="predicate"):
    if not isinstance(node, dict):
        raise InputError("%s must be an object" % path)
    operators = [key for key in ("literal", "regex", "all", "any", "not",
                                 "numeric", "forbidden") if key in node]
    if len(operators) != 1:
        raise InputError("%s must contain exactly one predicate operator" % path)
    operator = operators[0]
    if operator == "literal":
        _alternatives(node["literal"], path + ".literal")
        if node.get("mode", "contains") not in ("contains", "exact"):
            raise InputError("%s.mode must be contains or exact" % path)
        unexpected = set(node) - {"literal", "mode"}
        if unexpected:
            raise InputError("%s has unexpected keys: %s" % (path, sorted(unexpected)))
    elif operator == "regex":
        _compile_regex(node, path)
        unexpected = set(node) - {"regex", "flags"}
        if unexpected:
            raise InputError("%s has unexpected keys: %s" % (path, sorted(unexpected)))
    elif operator in ("all", "any", "forbidden"):
        children = node[operator]
        if not isinstance(children, list) or not children:
            raise InputError("%s.%s must be a nonempty array" % (path, operator))
        if set(node) != {operator}:
            raise InputError("%s.%s does not accept sibling keys" % (path, operator))
        for index, child in enumerate(children):
            validate_predicate(child, "%s.%s[%d]" % (path, operator, index))
    elif operator == "not":
        if set(node) != {"not"}:
            raise InputError("%s.not does not accept sibling keys" % path)
        validate_predicate(node["not"], path + ".not")
    elif operator == "numeric":
        if set(node) != {"numeric"}:
            raise InputError("%s.numeric does not accept sibling keys" % path)
        _numeric_spec(node, path)


def _result(passed, reason, details=None):
    return {"passed": bool(passed), "reason": reason,
            "details": details if details is not None else []}


def evaluate_predicate(node, text, path="predicate"):
    """Return a fully explicit result; node and text must already be safe types."""
    validate_predicate(node, path)
    if "literal" in node:
        alternatives = _alternatives(node["literal"], path + ".literal")
        normalized = [normalize_text(entry) for entry in alternatives]
        if node.get("mode", "contains") == "exact":
            matched = [entry for entry, norm in zip(alternatives, normalized)
                       if text == norm]
        else:
            matched = [entry for entry, norm in zip(alternatives, normalized)
                       if norm in text]
        return _result(bool(matched),
                       "literal alternatives matched: %s" % matched if matched
                       else "no literal alternative matched",
                       [{"operator": "literal", "matched": matched}])
    if "regex" in node:
        patterns = _compile_regex(node, path)
        matched = [source for source, pattern in patterns if pattern.search(text)]
        return _result(bool(matched),
                       "regex alternatives matched: %s" % matched if matched
                       else "no regex alternative matched",
                       [{"operator": "regex", "matched": matched}])
    if "numeric" in node:
        spec = _numeric_spec(node, path)
        matches = []
        for match in spec["pattern"].finditer(text):
            try:
                value = float(match.group("number"))
            except ValueError:
                continue
            if math.isfinite(value):
                matches.append({"value": value, "unit": match.group("unit"),
                                "text": match.group(0)})
        comparison = spec["comparison"]
        accepted = []
        comparisons = []
        for match in matches:
            value = match["value"]
            if comparison == "between":
                tolerance = spec["absolute"] + spec["relative"] * max(
                    abs(spec["min"]), abs(spec["max"]))
                passed = (spec["min"] - tolerance <= value <= spec["max"] + tolerance)
                target_text = "%s..%s" % (spec["min"], spec["max"])
            else:
                target = spec["target"]
                tolerance = spec["absolute"] + spec["relative"] * abs(target)
                if comparison == "eq":
                    passed = abs(value - target) <= tolerance
                elif comparison == "lt":
                    passed = value < target + tolerance
                elif comparison == "lte":
                    passed = value <= target + tolerance
                elif comparison == "gt":
                    passed = value > target - tolerance
                else:
                    passed = value >= target - tolerance
                target_text = str(target)
            comparisons.append({"value": value, "unit": match["unit"],
                                "comparison": comparison, "target": target_text,
                                "tolerance": tolerance, "passed": passed})
            if passed:
                accepted.append(match)
        if not matches:
            reason = "no numeric value with any required unit matched (%s)" % spec["units"]
        elif accepted:
            reason = "accepted numeric comparison(s): %s" % comparisons
        else:
            reason = "numeric values with required units failed comparison: %s" % comparisons
        return _result(bool(accepted), reason,
                       [{"operator": "numeric", "matches": comparisons,
                         "required_units": spec["units"]}])
    if "not" in node:
        child = evaluate_predicate(node["not"], text, path + ".not")
        return _result(not child["passed"], "negation of (%s)" % child["reason"],
                       [child])
    if "all" in node or "any" in node:
        operator = "all" if "all" in node else "any"
        children = [evaluate_predicate(child, text, "%s.%s[%d]" % (path, operator, i))
                    for i, child in enumerate(node[operator])]
        passed = all(child["passed"] for child in children) if operator == "all" \
            else any(child["passed"] for child in children)
        return _result(passed, "%s: %d/%d child predicates passed" % (
            operator, sum(child["passed"] for child in children), len(children)), children)
    if "forbidden" in node:
        children = [evaluate_predicate(child, text, "%s.forbidden[%d]" % (path, i))
                    for i, child in enumerate(node["forbidden"])]
        present = [index for index, child in enumerate(children) if child["passed"]]
        return _result(not present,
                       "forbidden assertions present at child indexes %s" % present
                       if present else "no forbidden assertion matched", children)
    raise InputError("%s has no supported operator" % path)


def _validate_band_condition(condition, check_ids, path):
    if isinstance(condition, str):
        if condition not in check_ids:
            raise InputError("%s references unknown check %s" % (path, condition))
        return
    if not isinstance(condition, dict) or len(condition) != 1:
        raise InputError("%s must be a check ID or all/any/not object" % path)
    operator = next(iter(condition))
    value = condition[operator]
    if operator == "not":
        _validate_band_condition(value, check_ids, path + ".not")
    elif operator in ("all", "any"):
        if not isinstance(value, list) or not value:
            raise InputError("%s.%s must be a nonempty array" % (path, operator))
        for index, child in enumerate(value):
            _validate_band_condition(child, check_ids,
                                     "%s.%s[%d]" % (path, operator, index))
    else:
        raise InputError("%s operator must be all, any, or not" % path)


def validate_rubric(rubric):
    if not isinstance(rubric, dict):
        raise InputError("rubric must be an object")
    predicates = rubric.get("predicates")
    if not isinstance(predicates, list) or not predicates:
        raise InputError("rubric.predicates must be a nonempty array")
    check_ids = set()
    for index, check in enumerate(predicates):
        if not isinstance(check, dict) or set(check) != {"id", "category", "predicate"}:
            raise InputError("predicate entry %d needs exactly id/category/predicate" % index)
        check_id = check["id"]
        if not isinstance(check_id, str) or not re.fullmatch(r"[a-z0-9_.-]+", check_id):
            raise InputError("predicate ID must match [a-z0-9_.-]+")
        if check_id in check_ids:
            raise InputError("duplicate predicate ID: %s" % check_id)
        if not isinstance(check["category"], str) or not check["category"]:
            raise InputError("predicate category must be a nonempty string")
        check_ids.add(check_id)
        validate_predicate(check["predicate"], "predicates[%d].predicate" % index)
    bands = rubric.get("score_bands")
    if not isinstance(bands, list) or not bands:
        raise InputError("rubric.score_bands must be a nonempty ordered array")
    for index, band in enumerate(bands):
        if not isinstance(band, dict) or set(band) != {"score", "when", "rationale"}:
            raise InputError("score band %d needs exactly score/when/rationale" % index)
        if isinstance(band["score"], bool) or band["score"] not in (0, 1, 2):
            raise InputError("score band %d has invalid score" % index)
        if not isinstance(band["rationale"], str) or not band["rationale"]:
            raise InputError("score band %d requires rationale" % index)
        _validate_band_condition(band["when"], check_ids, "score_bands[%d].when" % index)
    if isinstance(rubric.get("default_score"), bool) or rubric.get("default_score") not in (0, 1, 2):
        raise InputError("rubric.default_score must be 0, 1, or 2")
    unexpected = set(rubric) - {"predicates", "score_bands", "default_score"}
    if unexpected:
        raise InputError("rubric has unexpected keys: %s" % sorted(unexpected))


def _evaluate_band(condition, checks):
    if isinstance(condition, str):
        return checks[condition]
    operator = next(iter(condition))
    if operator == "not":
        return not _evaluate_band(condition["not"], checks)
    if operator == "all":
        return all(_evaluate_band(child, checks) for child in condition["all"])
    return any(_evaluate_band(child, checks) for child in condition["any"])


def score_candidate(item, candidate):
    """Score any candidate safely. Invalid/empty candidates always receive zero.

    A malformed rubric raises InputError instead of silently inventing a score.
    """
    if not isinstance(item, dict) or not isinstance(item.get("item_id"), str):
        raise InputError("item requires a string item_id")
    rubric = item.get("rubric")
    validate_rubric(rubric)
    malformed = not isinstance(candidate, str)
    text = "" if malformed else normalize_text(candidate)
    empty = not bool(text.strip())
    check_results = []
    check_map = {}
    for check in rubric["predicates"]:
        evaluated = evaluate_predicate(check["predicate"], text)
        result = {
            "id": check["id"], "category": check["category"],
            "passed": evaluated["passed"], "reason": evaluated["reason"],
            "details": evaluated["details"],
        }
        check_results.append(result)
        check_map[check["id"]] = evaluated["passed"]
    matched_band = None
    for index, band in enumerate(rubric["score_bands"]):
        if _evaluate_band(band["when"], check_map):
            matched_band = {"index": index, "score": band["score"],
                            "rationale": band["rationale"]}
            break
    if matched_band is None:
        score = rubric["default_score"]
        band_reason = "no score band matched; default_score applied"
    else:
        score = matched_band["score"]
        band_reason = matched_band["rationale"]
    if malformed:
        score = 0
        band_reason = "malformed non-string candidate forced score 0"
    elif empty:
        score = 0
        band_reason = "empty or whitespace-only candidate forced score 0"
    # This assertion is an internal invariant, not a scoring rule.
    if isinstance(score, bool) or score not in (0, 1, 2):
        score = 0
        band_reason = "invalid band result safely forced to 0"
    return {
        "item_id": item["item_id"], "score": int(score),
        "rubric_hash": canonical_hash(rubric),
        "input_status": "non_string" if malformed else ("empty" if empty else "ok"),
        "checks": check_results,
        "score_band": matched_band,
        "score_reason": band_reason,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--items", required=True, help="item-bank JSON")
    parser.add_argument("--item-id", required=True)
    parser.add_argument("--candidate-file", required=True, help="UTF-8 raw output")
    parser.add_argument("--output", help="write JSON here; default stdout")
    args = parser.parse_args(argv)
    try:
        bank = load_json(args.items)
        items = bank.get("items") if isinstance(bank, dict) else None
        if not isinstance(items, list):
            raise InputError("item bank requires an items array")
        selected = [item for item in items
                    if isinstance(item, dict) and item.get("item_id") == args.item_id]
        if len(selected) != 1:
            raise InputError("expected exactly one item with ID %s" % args.item_id)
        try:
            with open(args.candidate_file, "r", encoding="utf-8") as handle:
                candidate = handle.read()
        except (OSError, UnicodeError) as exc:
            raise InputError("cannot read candidate %s: %s" % (args.candidate_file, exc))
        dump_json(score_candidate(selected[0], candidate), args.output)
    except InputError as exc:
        sys.stderr.write("score_engine: %s\n" % exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
