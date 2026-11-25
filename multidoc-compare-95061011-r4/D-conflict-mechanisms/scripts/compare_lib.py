#!/usr/bin/env python3
"""Scoped evidence validation, exact-key clustering, atlas and dynamic results."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import OrderedDict
from pathlib import Path

EVIDENCE_KINDS = {"observed_result", "author_interpretation", "speculation"}
VERDICTS = {"corroborates", "complements", "genuine_conflict", "apparent_conflict_due_to_scope", "incomparable", "insufficient"}
MECHANISM_STATUSES = {"supported_by_direct_comparison", "consistent_with_conditions", "unresolved"}
DIRECTIONS = {"increase", "decrease", "no_difference", "non_monotonic", "mixed"}
SIGNIFICANCE = {"not_reported", "reported_significant", "reported_not_significant", "not_applicable"}
REQUIRED_MATRIX_FIELDS = {"task", "material", "pollutant", "metric", "units", "budget"}
ARTIFACT_SUFFIXES = {".md", ".txt", ".csv", ".json", ".jsonl", ".html"}


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def as_list(value) -> list:
    return value if isinstance(value, list) else []


def index_by(items: list, key: str) -> dict:
    result = {}
    for item in items:
        if isinstance(item, dict) and isinstance(item.get(key), str):
            result[item[key]] = item
    return result


def markdown(value) -> str:
    if value is None:
        value = "unreported"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).replace("|", "\\|").replace("\n", " ")


def is_unreported(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip().lower() in {"unreported", "not reported", "unknown", ""})


def citation_exists(source_registry: dict, document_id, paragraph_id) -> bool:
    for document in source_registry.get("documents", []):
        if document.get("source_document_id") == document_id:
            return paragraph_id in document.get("paragraph_ids", [])
    return False


def check_citation(citation: dict, source_registry: dict, label: str, errors: list[str]) -> None:
    document_id = citation.get("source_document_id")
    paragraph_id = citation.get("paragraph_id")
    if not citation_exists(source_registry, document_id, paragraph_id):
        errors.append(f"{label}: nonexistent exact citation {document_id!r}/{paragraph_id!r}")


def common_matrix_lookup(workorder: dict, field_id: str) -> dict:
    for row in workorder.get("common_matrix", {}).get("rows", []):
        if row.get("field_id") == field_id:
            return {cell.get("source_document_id"): cell.get("value") for cell in row.get("cells", [])}
    return {}


def proposition_document_id(proposition: dict, evidence_by_id: dict) -> str | None:
    ids = proposition.get("evidence_ids", [])
    if len(ids) == 1 and ids[0] in evidence_by_id:
        return evidence_by_id[ids[0]].get("source_document_id")
    document_ids = {evidence_by_id[eid].get("source_document_id") for eid in ids if eid in evidence_by_id}
    return next(iter(document_ids)) if len(document_ids) == 1 else None


def core_dimensions(proposition: dict) -> dict:
    return {
        "task": proposition.get("task"),
        "comparison": proposition.get("comparison"),
        "metric": proposition.get("metric", {}).get("name"),
        "units": proposition.get("metric", {}).get("unit"),
        "material": sorted(proposition.get("materials", [])),
        "pollutant": sorted(proposition.get("pollutants", [])),
    }


def comparable_estimand(left: dict, right: dict) -> tuple[bool, list[str]]:
    reasons = []
    for field, lval in core_dimensions(left).items():
        rval = core_dimensions(right)[field]
        if lval != rval:
            reasons.append(f"{field} differs: {lval!r} versus {rval!r}")
    return not reasons, reasons


def matched_scope(left: dict, right: dict) -> bool:
    ignored = {"relation_role", "applicability", "applicability_conditions", "dataset_id"}
    lscope = {key: val for key, val in left.get("scope", {}).items() if key not in ignored}
    rscope = {key: val for key, val in right.get("scope", {}).items() if key not in ignored}
    return lscope == rscope


def observed_direction(proposition: dict, evidence_by_id: dict):
    evidence = [evidence_by_id[eid] for eid in proposition.get("evidence_ids", []) if eid in evidence_by_id]
    if not any(item.get("evidence_kind") == "observed_result" for item in evidence):
        return None
    return proposition.get("direction")


def derive_verdict(left: dict, right: dict, evidence_by_id: dict) -> tuple[str, str]:
    comparable, reasons = comparable_estimand(left, right)
    if not comparable:
        return "incomparable", "; ".join(reasons)
    ldir = observed_direction(left, evidence_by_id)
    rdir = observed_direction(right, evidence_by_id)
    opposite = {ldir, rdir} == {"increase", "decrease"}
    same = ldir is not None and ldir == rdir
    if matched_scope(left, right):
        if opposite:
            return "genuine_conflict", "Comparable estimand, matched scope, and opposite observed directions; attribution is not thereby resolved."
        if same:
            return "corroborates", "Comparable estimand, matched scope, and the same warranted observed direction; no pooling performed."
        return "insufficient", "Comparable estimand and scope, but observed directions are absent or cannot establish another verdict."
    roles = {left.get("scope", {}).get("relation_role"), right.get("scope", {}).get("relation_role")}
    if "scope_extension" in roles:
        return "complements", "An explicitly identified scope extension covers a different applicability domain."
    if opposite:
        return "apparent_conflict_due_to_scope", "Directions differ but scopes are not matched; this is not a genuine matched-condition conflict."
    return "insufficient", "Comparable dimensions but unmatched, non-extension scopes prevent a stronger relation."


def quantitative_compatibility(left: dict, right: dict, workorder: dict, evidence_by_id: dict) -> dict:
    """Admission checks only. This skill performs no pooled effect calculation."""
    checks = OrderedDict()
    reasons = []
    lcore, rcore = core_dimensions(left), core_dimensions(right)
    for field in ("task", "metric", "units", "material", "pollutant"):
        passed = lcore[field] == rcore[field] and not is_unreported(lcore[field]) and not is_unreported(rcore[field])
        checks[field] = passed
        if not passed:
            reasons.append(f"{field} is different or unreported")
    evidence = evidence_by_id
    ldoc = proposition_document_id(left, evidence)
    rdoc = proposition_document_id(right, evidence)
    budgets = common_matrix_lookup(workorder, "budget")
    lbudget, rbudget = budgets.get(ldoc), budgets.get(rdoc)
    budget_passed = not is_unreported(lbudget) and not is_unreported(rbudget) and lbudget == rbudget
    checks["budget"] = budget_passed
    if not budget_passed:
        reasons.append("budget is unreported or different")
    checks["matched_scope"] = matched_scope(left, right)
    if not checks["matched_scope"]:
        reasons.append("applicability scopes differ")
    same_dataset = left.get("dataset_id") is not None and left.get("dataset_id") == right.get("dataset_id")
    checks["same_dataset"] = same_dataset
    if not same_dataset:
        reasons.append("unlike or unidentified datasets")
    checks["same_dye"] = lcore["pollutant"] == rcore["pollutant"]
    if not checks["same_dye"]:
        reasons.append("different dyes must not be pooled")
    return {
        "allowed": all(checks.values()) and workorder.get("quantitative_synthesis_authorized") is True,
        "checks": checks,
        "reasons": reasons + ([] if workorder.get("quantitative_synthesis_authorized") is True else ["quantitative synthesis is not authorized"]),
        "note": "Compatibility admission test only; no quantitative pooling is performed.",
    }


def validate_common_matrix(workorder: dict, source_registry: dict, errors: list[str]) -> None:
    matrix = workorder.get("common_matrix")
    documents = [doc["source_document_id"] for doc in source_registry.get("documents", [])]
    if not isinstance(matrix, dict):
        errors.append("common_matrix must be an object")
        return
    fields = matrix.get("fields", [])
    missing = REQUIRED_MATRIX_FIELDS - set(fields)
    if missing:
        errors.append(f"common_matrix missing required fields: {sorted(missing)}")
    rows = matrix.get("rows", [])
    if set(fields) != {row.get("field_id") for row in rows}:
        errors.append("common_matrix fields and row field_id values differ")
    for row in rows:
        field_id = row.get("field_id", "<missing>")
        cells = row.get("cells", [])
        cell_docs = [cell.get("source_document_id") for cell in cells]
        if len(cells) != len(documents) or set(cell_docs) != set(documents) or len(set(cell_docs)) != len(cell_docs):
            errors.append(f"common_matrix {field_id}: must have exactly one cell for every document")
        for cell in cells:
            check_citation(cell, source_registry, f"common_matrix {field_id}", errors)
            if "value" not in cell:
                errors.append(f"common_matrix {field_id}: cell missing value; use unreported explicitly")


def validate_propositions(workorder: dict, source_registry: dict, evidence_by_id: dict, errors: list[str]) -> None:
    allowed = workorder.get("agent_specified_proposition_keys", [])
    if not isinstance(allowed, list) or len(set(allowed)) != len(allowed):
        errors.append("agent_specified_proposition_keys must be a unique list")
    propositions = workorder.get("propositions", [])
    ids = [item.get("proposition_id") for item in propositions]
    if len(ids) != len(set(ids)):
        errors.append("duplicate proposition_id")
    key_dimensions: dict[str, dict] = {}
    for proposition in propositions:
        pid = proposition.get("proposition_id", "<missing>")
        key = proposition.get("proposition_key")
        if key not in allowed:
            errors.append(f"{pid}: proposition_key was not agent-specified: {key!r}")
        dimensions = core_dimensions(proposition)
        if any(is_unreported(value) or value == [] for value in dimensions.values()):
            errors.append(f"{pid}: missing core topic/comparison/metric/scope dimension: {dimensions}")
        if key in key_dimensions and key_dimensions[key] != dimensions:
            errors.append(f"{pid}: same explicit key has heterogeneous scientific dimensions; no pooling or cluster merge permitted")
        key_dimensions.setdefault(key, dimensions)
        if proposition.get("claim_scope") not in {"scoped", "universal"}:
            errors.append(f"{pid}: claim_scope must be scoped or universal")
        if not isinstance(proposition.get("scope"), dict) or not proposition.get("scope"):
            errors.append(f"{pid}: nonempty applicability scope required")
        if not proposition.get("within_paper_limitations"):
            errors.append(f"{pid}: within-paper limitations are required")
        references = proposition.get("evidence_ids", [])
        if not references:
            errors.append(f"{pid}: evidence_ids cannot be empty")
        records = []
        for evidence_id in references:
            if evidence_id not in evidence_by_id:
                errors.append(f"{pid}: unknown evidence ID {evidence_id!r}")
            else:
                records.append(evidence_by_id[evidence_id])
        if "direction" in proposition:
            if proposition["direction"] not in DIRECTIONS:
                errors.append(f"{pid}: invalid direction")
            if not any(record.get("evidence_kind") == "observed_result" for record in records):
                errors.append(f"{pid}: direction requires cited observed_result evidence")
            if not any(record.get("direction") == proposition["direction"] and record.get("direction_basis") for record in records):
                errors.append(f"{pid}: proposition direction lacks matching evidence direction and basis")
        strength = proposition.get("strength", {})
        significance = strength.get("statistical_significance")
        if significance not in SIGNIFICANCE:
            errors.append(f"{pid}: invalid/missing statistical_significance")
        wording = strength.get("wording", "")
        if not wording:
            errors.append(f"{pid}: strength.wording required separately from significance")
        if significance == "not_reported" and re.search(r"\bsignificant\b|\bp\s*[<=>]", wording, re.I):
            errors.append(f"{pid}: significance inferred in wording despite not_reported")
        if not isinstance(proposition.get("metric"), dict) or not proposition["metric"].get("name") or not proposition["metric"].get("unit"):
            errors.append(f"{pid}: metric name and unit required")


def validate_evidence(workorder: dict, source_registry: dict, errors: list[str]) -> dict:
    records = workorder.get("evidence_records", [])
    evidence_by_id = index_by(records, "evidence_id")
    if len(evidence_by_id) != len(records):
        errors.append("duplicate or missing evidence_id")
    for evidence in records:
        eid = evidence.get("evidence_id", "<missing>")
        kind = evidence.get("evidence_kind")
        if kind not in EVIDENCE_KINDS:
            errors.append(f"{eid}: invalid evidence_kind")
        check_citation(evidence, source_registry, f"evidence {eid}", errors)
        if not evidence.get("finding"):
            errors.append(f"{eid}: finding required")
        if "direction" in evidence:
            if kind != "observed_result" or evidence.get("direction") not in DIRECTIONS or not evidence.get("direction_basis"):
                errors.append(f"{eid}: direction is only valid for an observed result with a basis")
        for measurement in evidence.get("measurements", []):
            if "value" not in measurement or not measurement.get("unit") or not measurement.get("arm"):
                errors.append(f"{eid}: measurements require arm, value and unit")
    return evidence_by_id


def validate_relations(workorder: dict, evidence_by_id: dict, errors: list[str]) -> None:
    propositions = index_by(workorder.get("propositions", []), "proposition_id")
    relation_ids = []
    for relation in workorder.get("conflict_relations", []):
        rid = relation.get("relation_id", "<missing>")
        relation_ids.append(relation.get("relation_id"))
        pair = relation.get("proposition_ids", [])
        verdict = relation.get("verdict")
        if verdict not in VERDICTS:
            errors.append(f"{rid}: invalid verdict")
            continue
        if len(pair) != 2 or pair[0] == pair[1] or any(pid not in propositions for pid in pair):
            errors.append(f"{rid}: exactly two distinct known proposition IDs required")
            continue
        derived, rationale = derive_verdict(propositions[pair[0]], propositions[pair[1]], evidence_by_id)
        if derived != verdict:
            errors.append(f"{rid}: declared {verdict!r} but scoped evidence gives {derived!r}: {rationale}")
    if len(relation_ids) != len(set(relation_ids)):
        errors.append("duplicate relation_id")


def attribution_problems(workorder: dict, source_registry: dict | None = None) -> list[str]:
    problems = []
    evidence_by_id = index_by(workorder.get("evidence_records", []), "evidence_id")
    source_registry = source_registry or {"documents": []}
    for mechanism in workorder.get("mechanism_attributions", []):
        mid = mechanism.get("mechanism_id", "<missing>")
        status = mechanism.get("status")
        if status not in MECHANISM_STATUSES:
            problems.append(f"{mid}: invalid mechanism status {status!r}")
        supporting = mechanism.get("supporting_explanations", [])
        alternatives = mechanism.get("alternative_explanations", [])
        if not supporting:
            problems.append(f"{mid}: supporting explanations required")
        if not alternatives:
            problems.append(f"{mid}: alternative explanations required for every status")
        comparisons = {item.get("comparison_id"): item for item in mechanism.get("direct_comparisons", [])}
        for comparison in mechanism.get("direct_comparisons", []):
            if source_registry.get("documents"):
                check_citation(comparison, source_registry, f"{mid} direct comparison", problems)
            if comparison.get("evidence_kind") != "observed_result" or comparison.get("design") != "direct_head_to_head":
                problems.append(f"{mid}: direct comparison must be observed direct_head_to_head")
            if not comparison.get("moderator") or not comparison.get("holds_constant"):
                problems.append(f"{mid}: direct comparison requires moderator and held-constant conditions")
        for explanation in supporting + alternatives:
            for evidence_id in explanation.get("evidence_refs", []):
                if evidence_id not in evidence_by_id:
                    problems.append(f"{mid}: unknown mechanism evidence {evidence_id!r}")
        if status == "supported_by_direct_comparison":
            if not comparisons:
                problems.append(f"{mid}: supported status has no direct comparison; conditions or speculation are insufficient")
            for explanation in supporting:
                comparison_id = explanation.get("tested_by")
                if comparison_id not in comparisons:
                    problems.append(f"{mid}: supporting explanation lacks tested_by direct comparison")
                matched_direct_observation = False
                comparison = comparisons.get(comparison_id, {})
                for evidence_id in explanation.get("evidence_refs", []):
                    record = evidence_by_id.get(evidence_id, {})
                    if record.get("evidence_kind") == "speculation":
                        problems.append(f"{mid}: speculation {evidence_id} cannot establish supported mechanism")
                    elif record.get("evidence_kind") != "observed_result":
                        problems.append(f"{mid}: support {evidence_id} is not observed_result")
                    same_citation = (
                        record.get("source_document_id") == comparison.get("source_document_id")
                        and record.get("paragraph_id") == comparison.get("paragraph_id")
                    )
                    if same_citation and record.get("design") == "direct_head_to_head":
                        matched_direct_observation = True
                if comparison_id in comparisons and not matched_direct_observation:
                    problems.append(f"{mid}: supporting evidence does not match the cited direct-comparison paragraph and design")
    return problems


def validate_workorder(workorder: dict, case: dict, source_registry: dict) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    if workorder.get("case_id") != case.get("case_id"):
        errors.append("case_id mismatch between case.json and comparison-workorder.json")
    documents = workorder.get("documents", [])
    registry_ids = {doc.get("source_document_id") for doc in source_registry.get("documents", [])}
    if {doc.get("source_document_id") for doc in documents} != registry_ids:
        errors.append("source registry and workorder documents differ")
    validate_common_matrix(workorder, source_registry, errors)
    evidence_by_id = validate_evidence(workorder, source_registry, errors)
    validate_propositions(workorder, source_registry, evidence_by_id, errors)
    validate_relations(workorder, evidence_by_id, errors)
    errors.extend(attribution_problems(workorder, source_registry))
    for field, values in common_matrix_lookup(workorder, "budget").items():
        if is_unreported(values):
            warnings.append(f"budget unreported for {field}")
    return {"valid": not errors, "errors": errors, "warnings": warnings, "source_registry": source_registry}


def make_clusters(workorder: dict) -> dict:
    allowed = list(workorder.get("agent_specified_proposition_keys", []))
    clusters = OrderedDict((key, []) for key in allowed)
    for proposition in workorder.get("propositions", []):
        key = proposition.get("proposition_key")
        if key not in clusters:
            raise ValueError(f"refusing inferred/fuzzy key: {key!r}")
        clusters[key].append(proposition.get("proposition_id"))
    return {
        "method": "exact agent-specified proposition_key only; no fuzzy/entity matching",
        "clusters": [{"proposition_key": key, "proposition_ids": ids} for key, ids in clusters.items()],
    }


def render_common_matrix(workorder: dict, source_registry: dict) -> str:
    documents = [doc["source_document_id"] for doc in source_registry["documents"]]
    lines = ["# Common-field matrix", "", "Every row contains every document. Citations are exact `(source_document_id, paragraph_id)` pairs; unreported and noncomparable values are preserved.", ""]
    lines.append("| Field | " + " | ".join(documents) + " |")
    lines.append("|---|" + "---|" * len(documents))
    for row in workorder["common_matrix"]["rows"]:
        cells = {cell["source_document_id"]: cell for cell in row["cells"]}
        rendered = []
        for document_id in documents:
            cell = cells[document_id]
            rendered.append(f"{markdown(cell['value'])}<br>Source: `{document_id}`, paragraph `{cell['paragraph_id']}`")
        lines.append(f"| {markdown(row['field_id'])} | " + " | ".join(rendered) + " |")
    lines.extend(["", "## Quantitative-synthesis gate", "", "Task, material, pollutant, metric, units, budget, scope, and dataset identity must all pass before quantitative synthesis could be considered. This example has unreported budgets and independent datasets and explicitly authorizes no pooling. Reported numbers remain side-by-side; no dye or dataset pooling is performed.", ""])
    return "\n".join(lines)


def _evidence_summary(proposition: dict, evidence_by_id: dict) -> str:
    citations = []
    for evidence_id in proposition.get("evidence_ids", []):
        record = evidence_by_id[evidence_id]
        citations.append(f"`{evidence_id}` ({record['evidence_kind']}; `{record['source_document_id']}`, `{record['paragraph_id']}`)")
    return "; ".join(citations)


def _measurements(proposition: dict, evidence_by_id: dict) -> str:
    values = []
    for evidence_id in proposition.get("evidence_ids", []):
        for measurement in evidence_by_id[evidence_id].get("measurements", []):
            values.append(f"{measurement['arm']}: {measurement['value']} {measurement['unit']}")
    return "; ".join(values) if values else "unreported / not applicable"


def render_atlas(workorder: dict, clusters: dict, source_registry: dict) -> str:
    evidence = index_by(workorder["evidence_records"], "evidence_id")
    propositions = index_by(workorder["propositions"], "proposition_id")
    lines = ["# Claim-scope and conflict-mechanism atlas", "", "This atlas is not a `+1/-1` claim graph. Lexical polarity is not scientific agreement, and condition differences are not causal attribution.", "", "## Exact-key proposition clusters", "", clusters["method"], ""]
    for cluster in clusters["clusters"]:
        lines.append(f"- `{cluster['proposition_key']}`: " + ", ".join(f"`{pid}`" for pid in cluster["proposition_ids"]))
    lines.extend(["", "## Propositions, evidence kinds and limitations", ""])
    for proposition in workorder["propositions"]:
        lines.extend([
            f"### {proposition['proposition_id']}", "",
            f"- **Tuple:** {proposition['topic']} / {proposition['comparison']} / {proposition['metric']['name']} ({proposition['metric']['unit']}) / `{proposition['claim_scope']}`.",
            f"- **Exact key:** `{proposition['proposition_key']}`.",
            f"- **Material / pollutant / task:** {markdown(proposition['materials'])} / {markdown(proposition['pollutants'])} / {proposition['task']}.",
            f"- **Applicability:** {markdown(proposition['scope'])}.",
            f"- **Evidence:** {_evidence_summary(proposition, evidence)}.",
            f"- **Direction:** {proposition.get('direction', 'not assigned; not warranted')}.",
            f"- **Strength wording:** {proposition['strength']['wording']}. **Statistical significance:** {proposition['strength']['statistical_significance']}.",
            f"- **Reported measurements (not pooled):** {_measurements(proposition, evidence)}.",
            f"- **Within-paper limitations:** {'; '.join(proposition['within_paper_limitations'])}.", ""
        ])
    lines.extend(["## Conflict verdicts", "", "Only explicitly supplied proposition pairs are evaluated.", "", "| Relation | Propositions | Verdict | Evidence-bounded rationale | Quantitative compatibility |", "|---|---|---|---|---|"])
    for relation in workorder["conflict_relations"]:
        left, right = [propositions[pid] for pid in relation["proposition_ids"]]
        compatibility = quantitative_compatibility(left, right, workorder, evidence)
        lines.append(f"| {relation['relation_id']} | {relation['proposition_ids'][0]} / {relation['proposition_ids'][1]} | **{relation['verdict']}** | {markdown(relation['rationale'])} | allowed={str(compatibility['allowed']).lower()}; {markdown('; '.join(compatibility['reasons']))} |")
    lines.extend(["", "## Mechanism attribution", "", "A mechanism is a hypothesis unless directly tested. Supporting and alternative explanations are both retained.", ""])
    for mechanism in workorder["mechanism_attributions"]:
        lines.extend([f"### {mechanism['mechanism_id']}: `{mechanism['status']}`", "", mechanism["claim"], "", "**Supporting explanations**"])
        for explanation in mechanism["supporting_explanations"]:
            lines.append(f"- {explanation['explanation']} Evidence: {markdown(explanation.get('evidence_refs', []))}; tested_by: `{explanation.get('tested_by', 'unreported')}`." )
        lines.append("")
        lines.append("**Alternative explanations**")
        for explanation in mechanism["alternative_explanations"]:
            lines.append(f"- {explanation['explanation']} Status: `{explanation.get('status', 'unresolved')}`; evidence: {markdown(explanation.get('evidence_refs', []))}.")
        if mechanism.get("direct_comparisons"):
            lines.append("")
            lines.append("**Direct comparisons**")
            for comparison in mechanism["direct_comparisons"]:
                lines.append(f"- `{comparison['comparison_id']}` tests `{comparison['moderator']}` via `{comparison['design']}`; source `{comparison['source_document_id']}`, paragraph `{comparison['paragraph_id']}`; held constant: {markdown(comparison['holds_constant'])}.")
        lines.append("")
    lines.extend(["## Concise integrated response", "", workorder["integrated_response"], ""])
    return "\n".join(lines)


def _contract_spec(contract) -> tuple[list, list]:
    fields: OrderedDict[str, dict] = OrderedDict()
    artifacts: list[str] = []

    def add_field(name, descriptor=None):
        if not isinstance(name, str) or name in fields:
            return
        fields[name] = descriptor if isinstance(descriptor, dict) else {}

    def add_item(item, field_context=False):
        if isinstance(item, str):
            if not field_context and Path(item).suffix.lower() in ARTIFACT_SUFFIXES:
                if item not in artifacts:
                    artifacts.append(item)
            else:
                add_field(item)
        elif isinstance(item, dict):
            if "name" in item:
                if item.get("kind") == "artifact" or str(item.get("name", "")).lower().endswith(tuple(ARTIFACT_SUFFIXES)):
                    if item["name"] not in artifacts:
                        artifacts.append(item["name"])
                else:
                    add_field(item["name"], item)
            else:
                walk(item, field_context)
        elif isinstance(item, list):
            for child in item:
                add_item(child, field_context)

    def walk(node, field_context=False):
        if isinstance(node, list):
            for item in node:
                add_item(item, field_context)
            return
        if not isinstance(node, dict):
            return
        for key, value in node.items():
            if key in {"artifacts", "files", "deliverables", "outputs"}:
                for item in value if isinstance(value, list) else [value]:
                    if isinstance(item, str) and item not in artifacts:
                        artifacts.append(item)
                    elif isinstance(item, dict) and item.get("path"):
                        if item["path"] not in artifacts:
                            artifacts.append(item["path"])
            elif key in {"result_fields", "required_fields", "fields", "required"}:
                add_item(value, True)
            elif key in {"result", "result.json"} and isinstance(value, (dict, list)):
                walk(value, True)
            elif key == "properties" and isinstance(value, dict):
                for name, descriptor in value.items():
                    add_field(name, descriptor)
            elif key in {"type", "description", "title", "$schema"}:
                continue
            else:
                add_field(key, value if isinstance(value, dict) else None)
    walk(contract)
    return list(fields.items()), artifacts


def _field_value(name: str, descriptor: dict, standard: dict):
    if name in standard:
        return copy.deepcopy(standard[name]), True
    normalized = name.strip().lower().replace("-", "_").replace(" ", "_")
    normalized = re.sub(r"\.(md|json|txt)$", "", normalized)
    if normalized in standard:
        return copy.deepcopy(standard[normalized]), True
    if "default" in descriptor:
        return copy.deepcopy(descriptor["default"]), True
    if descriptor.get("type") == "array":
        return [], False
    if descriptor.get("type") == "object":
        return {}, False
    return "unreported", False


def artifact_record(output_dir: Path, name: str) -> dict:
    path = output_dir / Path(name).name
    record = {"name": path.name, "path": str(path), "exists": path.is_file()}
    if path.is_file():
        data = path.read_bytes()
        record.update({"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    return record


def assemble_result(case: dict, workorder: dict, output_dir: Path, validation: dict, clusters: dict, forced_status: str | None = None) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    contract = workorder.get("output_contract", case.get("output_contract", []))
    requested_fields, requested_artifacts = _contract_spec(contract)
    default_artifacts = ["comparison-matrix.md", "conflict-atlas.md", "integrated-response.md", "result.json"]
    artifact_names = list(OrderedDict.fromkeys(default_artifacts + requested_artifacts))
    uncertainties = ["No quantitative pooling is performed; unreported and noncomparable values remain explicit."]
    uncertainties.extend(validation.get("warnings", []))
    for relation in workorder.get("conflict_relations", []):
        if relation.get("verdict") == "genuine_conflict":
            uncertainties.append(f"{relation['relation_id']} is a genuine conflict whose causal explanation remains unresolved.")
    for mechanism in workorder.get("mechanism_attributions", []):
        if mechanism.get("status") != "supported_by_direct_comparison":
            uncertainties.append(f"{mechanism.get('mechanism_id')}: {mechanism.get('status')}.")
        for alternative in mechanism.get("alternative_explanations", []):
            uncertainties.append(f"Alternative for {mechanism.get('mechanism_id')}: {alternative.get('explanation')}")
    changes = [
        {"step": "source_preparation", "record": validation.get("source_registry", {})},
        {"step": "evidence_scope_validation", "record": {key: validation[key] for key in ("valid", "errors", "warnings")}},
        {"step": "exact_key_clustering", "record": clusters},
        {"step": "atlas_and_matrix", "record": {"generated": ["comparison-matrix.md", "conflict-atlas.md", "integrated-response.md"], "quantitative_pooling": False}},
    ]
    standard = {
        "case_id": case.get("case_id"),
        "status": "success",
        "summary": workorder.get("integrated_response", "unreported"),
        "sources": validation.get("source_registry", {}).get("documents", []),
        "uncertainty": uncertainties,
        "uncertainties": uncertainties,
        "change_records": changes,
        "artifacts": [],
        "output_contract": copy.deepcopy(contract),
        "comparison_matrix": "comparison-matrix.md",
        "matrix": "comparison-matrix.md",
        "conflict_atlas": "conflict-atlas.md",
        "integrated_response": "integrated-response.md",
    }
    result = copy.deepcopy(standard)
    result.pop("uncertainties")
    dynamic_unknown = []
    for name, descriptor in requested_fields:
        value, known = _field_value(name, descriptor, standard)
        result[name] = value
        if not known:
            dynamic_unknown.append(name)
    status = forced_status or ("success" if validation.get("valid") else "failed")
    missing_artifacts = [name for name in requested_artifacts if not (output_dir / Path(name).name).is_file() and name != "result.json"]
    if dynamic_unknown:
        uncertainties.append("Output-contract fields not supplied by this pipeline: " + ", ".join(dynamic_unknown))
    if missing_artifacts:
        uncertainties.append("Requested artifacts not generated: " + ", ".join(missing_artifacts))
    if (dynamic_unknown or missing_artifacts) and status == "success":
        status = "partial"
    result["status"] = status
    result["artifacts"] = [artifact_record(output_dir, name) for name in artifact_names]
    result["output_contract"] = copy.deepcopy(contract)
    return result


def failed_result(case: dict, workorder: dict, output_dir: Path, error: str) -> dict:
    contract = workorder.get("output_contract", case.get("output_contract", []))
    requested, requested_artifacts = _contract_spec(contract)
    result = {
        "case_id": case.get("case_id", workorder.get("case_id", "unreported")),
        "status": "failed",
        "summary": error,
        "artifacts": [artifact_record(output_dir, name) for name in list(OrderedDict.fromkeys(["result.json"] + requested_artifacts))],
        "sources": [],
        "uncertainty": [error],
        "change_records": [{"step": "pipeline", "status": "failed", "error": error}],
        "output_contract": copy.deepcopy(contract),
    }
    standard = {"comparison_matrix": "comparison-matrix.md", "conflict_atlas": "conflict-atlas.md", "integrated_response": "integrated-response.md"}
    standard.update(result)
    for name, descriptor in requested:
        if name not in result:
            result[name], _ = _field_value(name, descriptor, standard)
    return result
