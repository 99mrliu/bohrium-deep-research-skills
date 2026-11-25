#!/usr/bin/env python3
"""Validate a human/agent curation and generate graph, result, and evidence map.

The script checks discourse/provenance constraints and verbatim evidence. It does
not decide whether a sentence is a conclusion, find numbers, or infer conditions.
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

from common import (
    CLAIM_KINDS,
    ContractError,
    FIELD_STATUSES,
    atomic_json,
    dedupe_evidence,
    load_json,
    normalize_target_fields,
    source_paragraph_index,
    verify_evidence,
)

GUARDED_KINDS = {"hypothesis_speculation", "prior_work_cited_claim", "limitation"}


def require_string(item, key, context, allow_empty=False):
    value = item.get(key)
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ContractError(f"{context}: {key} must be a nonempty string")
    return value


def check_ids(items, id_key, label):
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            raise ContractError(f"Every {label} entry must be an object")
        item_id = require_string(item, id_key, label)
        if item_id in seen:
            raise ContractError(f"Duplicate {label} ID: {item_id}")
        seen.add(item_id)
    return seen


def verify_claim_guards(claim, paragraph_index):
    context = f"Claim {claim['claim_id']}"
    kind = claim["kind"]
    attribution = claim.get("attribution")
    if not isinstance(attribution, dict):
        raise ContractError(f"{context}: attribution object is required")
    origin = attribution.get("origin")
    if origin not in {"author_current_paper", "cited_work"}:
        raise ContractError(f"{context}: attribution.origin must identify current authors or cited work")
    require_string(attribution, "speaker", context)
    status = require_string(claim, "epistemic_status", context)
    modality = require_string(claim, "modality", context)
    hedges = claim.get("hedges", [])
    if not isinstance(hedges, list) or any(not isinstance(h, str) or not h for h in hedges):
        raise ContractError(f"{context}: hedges must be a list of literal strings")
    evidence_text = " ".join(e["quote"] for e in claim["evidence"])
    searchable = (claim["text"] + " " + evidence_text).casefold()
    for hedge in hedges:
        if hedge.casefold() not in searchable:
            raise ContractError(f"{context}: hedge {hedge!r} is absent from claim/evidence text")
    if kind == "author_conclusion":
        if origin != "author_current_paper":
            raise ContractError(f"{context}: NEGATIVE-PROMOTION-GUARD: cited work cannot be an author conclusion")
        if status not in {"author_conclusion", "concluded_by_authors"} or modality != "declarative":
            raise ContractError(f"{context}: author conclusion requires declarative current-author discourse")
    if kind == "hypothesis_speculation":
        if status == "established_author_conclusion" or modality == "declarative" or claim.get("promotion_allowed") is not False:
            raise ContractError(f"{context}: NEGATIVE-PROMOTION-GUARD: speculation cannot be promoted")
    if kind == "prior_work_cited_claim":
        if origin != "cited_work" or status == "established_author_conclusion" or claim.get("promotion_allowed") is not False:
            raise ContractError(f"{context}: NEGATIVE-PROMOTION-GUARD: cited claim must remain attributed and unpromoted")
    if kind == "limitation" and claim.get("promotion_allowed") is not False:
        raise ContractError(f"{context}: limitation must have promotion_allowed=false")


def build(case, targets, source_doc, curated):
    paragraph_index = source_paragraph_index(source_doc)
    case_id = case.get("case_id") if isinstance(case, dict) else None
    if not isinstance(case_id, str) or not case_id:
        raise ContractError("case.json requires a nonempty case_id")
    conditions = curated.get("conditions", [])
    observations = curated.get("observations", [])
    claims = curated.get("claims", [])
    field_curations = curated.get("field_results")
    if not isinstance(field_curations, list):
        raise ContractError("curated.json requires a field_results list")
    condition_ids = check_ids(conditions, "condition_id", "condition")
    observation_ids = check_ids(observations, "observation_id", "observation")
    claim_ids = check_ids(claims, "claim_id", "claim")
    condition_by_id = {x["condition_id"]: x for x in conditions}
    observation_by_id = {x["observation_id"]: x for x in observations}
    claim_by_id = {x["claim_id"]: x for x in claims}

    for condition in conditions:
        context = f"Condition {condition['condition_id']}"
        require_string(condition, "description", context)
        if not isinstance(condition.get("evidence"), list) or not condition["evidence"]:
            raise ContractError(f"{context}: at least one evidence item is required")
        for evidence in condition["evidence"]:
            verify_evidence(evidence, paragraph_index, context)

    for observation in observations:
        context = f"Observation {observation['observation_id']}"
        kind = require_string(observation, "kind", context)
        if kind not in {"quantitative_observation", "qualitative_observation", "method_observation"}:
            raise ContractError(f"{context}: unsupported observation kind")
        if not isinstance(observation.get("evidence"), list) or not observation["evidence"]:
            raise ContractError(f"{context}: evidence is required")
        for evidence in observation["evidence"]:
            verify_evidence(evidence, paragraph_index, context)
        for key in ("units", "statistic", "comparator"):
            if key not in observation:
                raise ContractError(f"{context}: explicit {key} key is required (null is allowed)")
        refs = observation.get("condition_ids", [])
        if not isinstance(refs, list) or any(ref not in condition_ids for ref in refs):
            raise ContractError(f"{context}: unknown or invalid condition_ids")
        if kind == "quantitative_observation":
            if observation.get("scalar") is None or observation.get("units") is None:
                raise ContractError(f"{context}: quantitative scalar and units must be explicit")
            if not refs:
                raise ContractError(f"{context}: quantitative observations must link experimental conditions")
        elif "scalar" not in observation:
            raise ContractError(f"{context}: explicit scalar key is required")

    for claim in claims:
        context = f"Claim {claim['claim_id']}"
        kind = require_string(claim, "kind", context)
        if kind not in CLAIM_KINDS:
            raise ContractError(f"{context}: unsupported kind {kind}")
        require_string(claim, "text", context)
        if not isinstance(claim.get("evidence"), list) or not claim["evidence"]:
            raise ContractError(f"{context}: evidence is required")
        for evidence in claim["evidence"]:
            verify_evidence(evidence, paragraph_index, context)
        for ref in claim.get("supporting_observation_ids", []):
            if ref not in observation_ids:
                raise ContractError(f"{context}: unknown supporting observation {ref}")
        for ref in claim.get("condition_ids", []):
            if ref not in condition_ids:
                raise ContractError(f"{context}: unknown condition {ref}")
        verify_claim_guards(claim, paragraph_index)

    curation_by_field = {}
    for item in field_curations:
        if not isinstance(item, dict):
            raise ContractError("Every field_results entry must be an object")
        field_id = require_string(item, "field_id", "field curation")
        if field_id in curation_by_field:
            raise ContractError(f"Duplicate curated field_id: {field_id}")
        curation_by_field[field_id] = item
    requested_ids = {target["field_id"] for target in targets}
    extras = set(curation_by_field) - requested_ids
    if extras:
        raise ContractError(f"Curated fields not requested: {sorted(extras)}")

    resolved_fields = []
    for target in targets:
        field_id = target["field_id"]
        item = copy.deepcopy(curation_by_field.get(field_id, {
            "field_id": field_id,
            "status": "extraction_failed",
            "scalar": None,
            "units": None,
            "statistic": None,
            "experimental_condition": None,
            "condition": None,
            "comparator": None,
            "evidence": [],
            "notes": "No source-grounded curation was supplied for this requested field.",
        }))
        context = f"Field {field_id}"
        status = item.get("status")
        if status not in FIELD_STATUSES:
            raise ContractError(f"{context}: invalid per-field status")
        obs_refs = item.get("observation_ids", [])
        claim_refs = item.get("claim_ids", [])
        if not isinstance(obs_refs, list) or any(ref not in observation_ids for ref in obs_refs):
            raise ContractError(f"{context}: invalid observation_ids")
        if not isinstance(claim_refs, list) or any(ref not in claim_ids for ref in claim_refs):
            raise ContractError(f"{context}: invalid claim_ids")
        linked_observations = [observation_by_id[ref] for ref in obs_refs]
        linked_claims = [claim_by_id[ref] for ref in claim_refs]
        own_evidence = item.get("evidence", [])
        if not isinstance(own_evidence, list):
            raise ContractError(f"{context}: evidence must be a list")
        for evidence in own_evidence:
            verify_evidence(evidence, paragraph_index, context)

        if status == "reported":
            if len(linked_observations) > 1:
                raise ContractError(f"{context}: ambiguous multiple observations; use source_conflict or a qualitative synthesis")
            if linked_observations:
                observation = linked_observations[0]
                for key in ("scalar", "units", "statistic", "comparator"):
                    if key in item and item[key] != observation.get(key):
                        raise ContractError(f"{context}: {key} differs from linked observation {observation['observation_id']}")
                    item[key] = copy.deepcopy(observation.get(key))
                condition_descriptions = [condition_by_id[ref]["description"] for ref in observation.get("condition_ids", [])]
                derived_condition = "; ".join(condition_descriptions) if condition_descriptions else None
                if "experimental_condition" in item and item["experimental_condition"] != derived_condition:
                    raise ContractError(f"{context}: experimental_condition differs from linked conditions")
                item["experimental_condition"] = derived_condition
            if item.get("scalar") is None:
                raise ContractError(f"{context}: reported field requires a non-null scalar")
        if status in {"not_reported", "extraction_failed"} and item.get("scalar") is not None:
            raise ContractError(f"{context}: {status} cannot carry a guessed scalar")
        if status == "source_conflict":
            if item.get("scalar") is not None:
                raise ContractError(f"{context}: source_conflict cannot silently select one scalar")
            if len(linked_observations) < 2:
                raise ContractError(f"{context}: source_conflict requires at least two observations")

        guarded = [claim for claim in linked_claims if claim["kind"] in GUARDED_KINDS]
        interpretation = item.pop("interpretation", None)
        if guarded:
            required = {
                "hypothesis_speculation": "reported_hypothesis",
                "prior_work_cited_claim": "reported_prior_work",
                "limitation": "reported_limitation",
            }
            if status == "not_reported":
                if interpretation != "not_an_established_author_conclusion":
                    raise ContractError(f"{context}: guarded claims require an explicit non-promotion interpretation")
            else:
                for claim in guarded:
                    if interpretation != required[claim["kind"]]:
                        raise ContractError(f"{context}: NEGATIVE-PROMOTION-GUARD: {claim['kind']} requires {required[claim['kind']]}")

        related_conditions = []
        for observation in linked_observations:
            related_conditions.extend(condition_by_id[ref] for ref in observation.get("condition_ids", []))
        for claim in linked_claims:
            related_conditions.extend(condition_by_id[ref] for ref in claim.get("condition_ids", []))
        evidence = own_evidence[:]
        for observation in linked_observations:
            evidence.extend(observation["evidence"])
        for claim in linked_claims:
            evidence.extend(claim["evidence"])
        for condition in related_conditions:
            evidence.extend(condition["evidence"])
        evidence = dedupe_evidence(evidence)
        if status in {"reported", "not_reported", "source_conflict"} and not evidence:
            raise ContractError(f"{context}: {status} requires source evidence/scope, not a bare assertion")
        if status == "source_conflict" and len({(e['source_id'], e['paragraph_id']) for e in evidence}) < 2:
            raise ContractError(f"{context}: conflict must expose both source locations")
        if status == "not_reported" and not item.get("notes"):
            raise ContractError(f"{context}: not_reported needs notes defining the searched absence or limitation")

        item["condition"] = item.get("experimental_condition")
        item["evidence"] = evidence
        if evidence:
            primary = evidence[0]
            item.setdefault("paragraph_id", primary["paragraph_id"])
            item.setdefault("quote", primary["quote"])
            matches = [e for e in evidence if e["paragraph_id"] == item["paragraph_id"] and e["quote"] == item["quote"]]
            if not matches:
                raise ContractError(f"{context}: primary paragraph_id/quote must occur in evidence")
        else:
            item["paragraph_id"] = None
            item["quote"] = ""
        if "units" not in item:
            item["units"] = None
        if "statistic" not in item:
            item["statistic"] = None
        if "comparator" not in item:
            item["comparator"] = None
        if status == "extraction_failed" and not item.get("notes"):
            item["notes"] = "Extraction was not completed; no value is asserted."
        claim_layers = [f"{claim['claim_id']}={claim['kind']}/{claim['epistemic_status']}" for claim in linked_claims]
        if claim_layers:
            item["notes"] = (item.get("notes", "") + " Claim layers: " + "; ".join(claim_layers) + ".").strip()
        # Keep the public record contractual; internal linkage remains in graph.json.
        item.pop("observation_ids", None)
        item.pop("claim_ids", None)
        item.pop("experimental_condition", None)
        # Insert aliases with exactly the same value, then restore canonical key.
        item["experimental_condition"] = item["condition"]
        ordered = {
            "field_id": field_id,
            "status": status,
            "scalar": item.get("scalar"),
            "units": item.get("units"),
            "statistic": item.get("statistic"),
            "experimental_condition": item.get("experimental_condition"),
            "condition": item.get("condition"),
            "comparator": item.get("comparator"),
            "paragraph_id": item.get("paragraph_id"),
            "quote": item.get("quote"),
            "evidence": evidence,
            "notes": item.get("notes", ""),
        }
        resolved_fields.append(ordered)

    statuses = [field["status"] for field in resolved_fields]
    if not statuses or all(status == "extraction_failed" for status in statuses):
        run_status = "insufficient_evidence"
    elif all(status == "not_reported" for status in statuses):
        run_status = "insufficient_evidence"
    elif any(status == "extraction_failed" for status in statuses):
        run_status = "partial"
    else:
        # Scoped non-reports and explicitly preserved conflicts are completed
        # adjudications, not pending extraction work.
        run_status = "answered"

    result_sources = []
    for source in source_doc["sources"]:
        result_sources.append({k: copy.deepcopy(v) for k, v in source.items() if k != "paragraphs"})
    result_claims = copy.deepcopy(claims)
    for claim in result_claims:
        primary = claim["evidence"][0]
        claim["source_id"] = primary["source_id"]
        claim["location"] = {"paragraph_id": primary["paragraph_id"], "page": primary.get("page")}
    uncertainties = copy.deepcopy(curated.get("uncertainties", []))
    for field in resolved_fields:
        if field["status"] != "reported":
            uncertainties.append({"kind": field["status"], "field_id": field["field_id"], "detail": field["notes"]})
    for claim in claims:
        if claim["kind"] in GUARDED_KINDS:
            uncertainties.append({
                "kind": "epistemic_boundary",
                "claim_id": claim["claim_id"],
                "detail": f"{claim['kind']}; modality={claim['modality']}; no promotion to established current-author fact",
            })

    public_result = {
        "case_id": case_id,
        "status": run_status,
        "result": {"fields": resolved_fields, "field_results": copy.deepcopy(resolved_fields)},
        "claims": result_claims,
        "uncertainties": uncertainties,
        "sources": result_sources,
        "change_records": [{
            "action": "validated_curation_to_graph",
            "detail": "Generated only from explicit curated classifications, observations, conditions, and verbatim source evidence.",
        }],
    }

    graph = make_graph(case_id, run_status, bool(case.get("synthetic", False)), source_doc, conditions, observations, claims, resolved_fields, field_curations)
    return public_result, graph


def make_graph(case_id, run_status, synthetic, source_doc, conditions, observations, claims, fields, field_curations):
    nodes = [{"id": f"case:{case_id}", "type": "case", "case_id": case_id, "status": run_status}]
    edges = []
    cited_paragraphs = set()
    for source in source_doc["sources"]:
        nodes.append({"id": f"source:{source['source_id']}", "type": "source", **{k: v for k, v in source.items() if k != "paragraphs"}})
    for collection, prefix, node_type in (
        (conditions, "condition", "experimental_condition"),
        (observations, "observation", "observation"),
        (claims, "claim", "claim"),
    ):
        for item in collection:
            item_id = item[{"condition": "condition_id", "observation": "observation_id", "claim": "claim_id"}[prefix]]
            nodes.append({"id": f"{prefix}:{item_id}", "type": node_type, **copy.deepcopy(item)})
            for evidence in item.get("evidence", []):
                paragraph_key = (evidence["source_id"], evidence["paragraph_id"])
                cited_paragraphs.add(paragraph_key)
                edges.append({
                    "from": f"{prefix}:{item_id}",
                    "to": f"paragraph:{evidence['source_id']}:{evidence['paragraph_id']}",
                    "type": "grounded_in",
                    "evidence": copy.deepcopy(evidence),
                })
    paragraph_lookup = {(p["paragraph_id"], s["source_id"]): p for s in source_doc["sources"] for p in s["paragraphs"]}
    for source_id, paragraph_id in sorted(cited_paragraphs):
        paragraph = paragraph_lookup[(paragraph_id, source_id)]
        nodes.append({
            "id": f"paragraph:{source_id}:{paragraph_id}",
            "type": "paragraph",
            "source_id": source_id,
            "paragraph_id": paragraph_id,
            "page": paragraph.get("page"),
            "text": paragraph["text"],
        })
    for observation in observations:
        for condition_id in observation.get("condition_ids", []):
            edges.append({"from": f"observation:{observation['observation_id']}", "to": f"condition:{condition_id}", "type": "observed_under"})
    for claim in claims:
        for observation_id in claim.get("supporting_observation_ids", []):
            edges.append({"from": f"claim:{claim['claim_id']}", "to": f"observation:{observation_id}", "type": "supported_by"})
        for condition_id in claim.get("condition_ids", []):
            edges.append({"from": f"claim:{claim['claim_id']}", "to": f"condition:{condition_id}", "type": "scoped_by"})
    curation_by_id = {item["field_id"]: item for item in field_curations}
    for field in fields:
        nodes.append({"id": f"field:{field['field_id']}", "type": "target_field", **copy.deepcopy(field)})
        curation = curation_by_id.get(field["field_id"], {})
        for observation_id in curation.get("observation_ids", []):
            edges.append({"from": f"field:{field['field_id']}", "to": f"observation:{observation_id}", "type": "realized_by"})
        for claim_id in curation.get("claim_ids", []):
            edges.append({"from": f"field:{field['field_id']}", "to": f"claim:{claim_id}", "type": "interpreted_with_epistemic_layer"})
    return {
        "schema_version": "claim-evidence-graph/1.0",
        "synthetic_example": synthetic,
        "case_id": case_id,
        "status": run_status,
        "nodes": nodes,
        "edges": edges,
        "promotion_policy": "Cited, hedged, speculative, and limitation nodes never become established current-author conclusions through graph traversal.",
    }


def markdown_escape(value):
    if value is None:
        return "—"
    text = str(value).replace("|", "\\|").replace("\n", " ")
    return text


def render_markdown(result, graph):
    title = "# Claim–evidence map (SYNTHETIC example)" if graph["synthetic_example"] else "# Claim–evidence map"
    lines = [
        title,
        "",
        f"- **Case:** `{result['case_id']}`",
        f"- **Run status:** `{result['status']}`",
        "- **Reading rule:** conclusions, limitations, hypotheses, observations, and cited claims remain separate discourse layers.",
        "",
        "## Requested fields",
        "",
        "| field_id | status | scalar | units | statistic | condition | comparator | primary location |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for field in result["result"]["fields"]:
        location = field["paragraph_id"] or "—"
        lines.append("| " + " | ".join(markdown_escape(x) for x in (
            field["field_id"], field["status"], field["scalar"], field["units"], field["statistic"],
            field["experimental_condition"], field["comparator"], location,
        )) + " |")
    lines.extend(["", "## Discourse-layered claims", ""])
    for claim in result["claims"]:
        lines.extend([
            f"### {claim['claim_id']} — `{claim['kind']}`",
            "",
            claim["text"],
            "",
            f"- Attribution: {claim['attribution']['speaker']} (`{claim['attribution']['origin']}`)",
            f"- Epistemic status: `{claim['epistemic_status']}`; modality: `{claim['modality']}`",
            f"- Preserved hedges: {', '.join('`' + h + '`' for h in claim.get('hedges', [])) or 'none'}",
            f"- Promotion allowed: `{str(claim.get('promotion_allowed', False)).lower()}`",
        ])
        for evidence in claim["evidence"]:
            page = f", page {evidence['page']}" if evidence.get("page") is not None else ""
            lines.append(f"- Evidence `{evidence['source_id']}/{evidence['paragraph_id']}{page}`: “{evidence['quote']}”")
        lines.append("")
    lines.extend(["## Quantitative and qualitative observations", ""])
    for node in graph["nodes"]:
        if node["type"] != "observation":
            continue
        lines.extend([
            f"### {node['observation_id']} — `{node['kind']}`",
            "",
            f"- Scalar: `{markdown_escape(node.get('scalar'))}`; units: `{markdown_escape(node.get('units'))}`",
            f"- Statistic: {markdown_escape(node.get('statistic'))}",
            f"- Comparator: {markdown_escape(node.get('comparator'))}",
            f"- Conditions: {', '.join(node.get('condition_ids', [])) or 'none linked'}",
        ])
        for evidence in node["evidence"]:
            lines.append(f"- Evidence `{evidence['source_id']}/{evidence['paragraph_id']}`: “{evidence['quote']}”")
        lines.append("")
    lines.extend(["## Conditions", ""])
    for node in graph["nodes"]:
        if node["type"] == "experimental_condition":
            lines.append(f"- **{node['condition_id']}:** {node['description']}")
            for evidence in node["evidence"]:
                lines.append(f"  - `{evidence['source_id']}/{evidence['paragraph_id']}`: “{evidence['quote']}”")
    lines.extend(["", "## Uncertainties and non-promotion boundaries", ""])
    for uncertainty in result["uncertainties"]:
        lines.append(f"- `{uncertainty.get('kind', 'uncertainty')}`: {uncertainty.get('detail', uncertainty)}")
    lines.extend(["", "## Graph audit", "", f"Generated **{len(graph['nodes'])} nodes** and **{len(graph['edges'])} directed edges**. `grounded_in` edges carry exact quotations; `supported_by` does not mean `proven`.", ""])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--curated", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        case = load_json(args.case)
        targets = normalize_target_fields(load_json(args.targets))
        sources = load_json(args.sources)
        curated = load_json(args.curated)
        result, graph = build(case, targets, sources, curated)
        args.output.mkdir(parents=True, exist_ok=True)
        atomic_json(args.output / "graph.json", graph)
        atomic_json(args.output / "result.json", result)
        (args.output / "evidence-map.md").write_text(render_markdown(result, graph), encoding="utf-8")
    except ContractError as exc:
        print(f"CURATE_ERROR: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"IO_ERROR: {exc}", file=sys.stderr)
        return 3
    print(f"Wrote {args.output / 'graph.json'}")
    print(f"Wrote {args.output / 'result.json'}")
    print(f"Wrote {args.output / 'evidence-map.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
