#!/usr/bin/env python3
"""Contract-adaptive local knowledge publisher (Python 3.9+, stdlib only).

This tool validates declared references, emits only the negotiated artifacts, and
uses a strict TriG/JSON-LD subset round-trip. Its RDF checks are structural
self-checks, not a complete W3C conformance test or Trusty URI registration.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
NP = "http://www.nanopub.org/nschema#"
PROV = "http://www.w3.org/ns/prov#"
DCTERMS = "http://purl.org/dc/terms/"
CGP = "urn:contract-graph-publisher:vocabulary:"
FORMATS = {"json", "jsonl", "rdf"}
CANONICAL = {
    "case_id",
    "claims",
    "evidence",
    "sources",
    "uncertainty",
    "change_records",
    "publications",
}


class PublishError(Exception):
    """A deterministic input, contract, or self-check failure."""


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PublishError("duplicate JSON key: %s" % key)
        result[key] = value
    return result


def load_json(path):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PublishError("cannot read UTF-8 JSON %s: %s" % (path, exc))
    try:
        return json.loads(text, object_pairs_hook=reject_duplicate_keys)
    except (json.JSONDecodeError, PublishError) as exc:
        raise PublishError("invalid JSON %s: %s" % (path, exc))


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    temporary.replace(path)


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def require_dict(value, label):
    if not isinstance(value, dict):
        raise PublishError("%s must be an object" % label)
    return value


def require_list(value, label):
    if not isinstance(value, list):
        raise PublishError("%s must be an array" % label)
    return value


def require_text(value, label):
    if not isinstance(value, str) or not value:
        raise PublishError("%s must be a non-empty string" % label)
    return value


def unique_text_list(value, label):
    values = require_list(value, label)
    result = []
    for index, item in enumerate(values):
        text = require_text(item, "%s[%d]" % (label, index))
        if text in result:
            raise PublishError("duplicate ID %s in %s" % (text, label))
        result.append(text)
    return result


def validate_iri(value, label):
    value = require_text(value, label)
    if re.search(r"[\x00-\x20<>\\^`{|}]", value) or ":" not in value:
        raise PublishError("%s is not a safe absolute IRI: %r" % (label, value))
    return value


def local_iri(case_id, kind, identifier=None):
    base = "urn:contract-graph-publisher:local:%s:%s" % (
        quote(case_id, safe=""),
        kind,
    )
    if identifier is not None:
        base += ":" + quote(identifier, safe="")
    return base


def iri_term(value):
    return {"kind": "iri", "value": value}


def literal_term(value, language=None, datatype=None):
    term = {"kind": "literal", "value": value}
    if language:
        term["language"] = language
    if datatype:
        term["datatype"] = datatype
    return term


def normalize_term(value, label, allow_literal):
    value = require_dict(value, label)
    allowed = {"iri"} | ({"value", "language", "datatype"} if allow_literal else set())
    if set(value) - allowed:
        raise PublishError("%s has unknown term fields: %s" % (label, sorted(set(value) - allowed)))
    if "iri" in value:
        if set(value) != {"iri"}:
            raise PublishError("%s cannot mix iri with literal fields" % label)
        return {"iri": validate_iri(value["iri"], label + ".iri")}
    if not allow_literal or "value" not in value:
        raise PublishError("%s requires an explicit iri or literal value" % label)
    if set(value) - {"value", "language", "datatype"}:
        raise PublishError("%s has invalid literal fields" % label)
    if not isinstance(value["value"], str):
        raise PublishError("%s.value must be a string" % label)
    result = {"value": value["value"]}
    if "language" in value:
        result["language"] = require_text(value["language"], label + ".language")
    if "datatype" in value:
        result["datatype"] = validate_iri(value["datatype"], label + ".datatype")
    if "language" in result and "datatype" in result:
        raise PublishError("%s cannot have both language and datatype" % label)
    return result


def term_to_rdf(term, allow_literal=True):
    if "iri" in term:
        return iri_term(term["iri"])
    if not allow_literal:
        raise PublishError("literal is not allowed for this RDF term")
    return literal_term(term["value"], term.get("language"), term.get("datatype"))


def parse_contract(case):
    case_id = require_text(case.get("case_id"), "case_id")
    contract = case.get("output_contract")
    if isinstance(contract, dict):
        fields_value = contract.get("fields")
        if contract.get("additionalProperties", False) is not False:
            raise PublishError("output_contract must set additionalProperties to false")
    else:
        fields_value = contract
    fields = unique_text_list(fields_value, "output_contract.fields")
    if "case_id" not in fields:
        raise PublishError("output_contract.fields must include the exact key case_id")

    manifest = require_dict(case.get("manifest"), "manifest")
    declared = unique_text_list(manifest.get("output_fields"), "manifest.output_fields")
    if declared != fields:
        missing = [key for key in fields if key not in declared]
        extra = [key for key in declared if key not in fields]
        raise PublishError(
            "manifest.output_fields must exactly match output_contract.fields; missing=%s extra=%s"
            % (missing, extra)
        )
    request_format = manifest.get("request_format")
    if request_format not in FORMATS:
        raise PublishError("manifest.request_format must be one of %s" % sorted(FORMATS))
    mapping = require_dict(case.get("field_mapping", {}), "field_mapping")
    for output_field, source_field in mapping.items():
        if output_field not in fields:
            raise PublishError("field_mapping contains undeclared output key: %s" % output_field)
        if output_field == "case_id" or source_field not in CANONICAL | {"contract_values"}:
            raise PublishError("invalid field_mapping for %s" % output_field)
    contract_values = require_dict(case.get("contract_values", {}), "contract_values")
    if set(contract_values) - set(fields):
        raise PublishError("contract_values contains keys outside output_contract")
    return case_id, fields, manifest, mapping, contract_values


def render_result(fields, mapping, contract_values, canonical):
    result = {}
    for field in fields:
        source = mapping.get(field, field if field in CANONICAL else "contract_values")
        if field == "case_id":
            result[field] = canonical["case_id"]
        elif source == "contract_values":
            if field not in contract_values:
                raise PublishError("no honest value supplied for required output field: %s" % field)
            result[field] = contract_values[field]
        else:
            if source not in canonical:
                raise PublishError("canonical value unavailable for output field: %s" % field)
            result[field] = canonical[source]
    if set(result) != set(fields) or list(result) != fields:
        raise PublishError("internal exact-key rendering failure")
    return result


def validate_result_readback(path, fields, case_id):
    result = require_dict(load_json(path), "result.json")
    if list(result) != fields or set(result) != set(fields):
        raise PublishError(
            "result readback keys differ from output_contract: expected=%r actual=%r"
            % (fields, list(result))
        )
    if result.get("case_id") != case_id:
        raise PublishError("result readback case_id does not match original case")
    return result


def normalize_input(case):
    raw_sources = require_list(case.get("sources"), "sources")
    sources = []
    source_ids = set()
    for index, raw in enumerate(raw_sources):
        raw = require_dict(raw, "sources[%d]" % index)
        source_id = require_text(raw.get("source_id"), "sources[%d].source_id" % index)
        if source_id in source_ids:
            raise PublishError("duplicate source_id: %s" % source_id)
        source_ids.add(source_id)
        item = {"source_id": source_id}
        for key in ("title", "locator"):
            if key in raw:
                item[key] = require_text(raw[key], "sources[%d].%s" % (index, key))
        sources.append(item)

    raw_evidence = require_list(case.get("evidence"), "evidence")
    evidence = []
    evidence_ids = set()
    for index, raw in enumerate(raw_evidence):
        raw = require_dict(raw, "evidence[%d]" % index)
        evidence_id = require_text(raw.get("evidence_id"), "evidence[%d].evidence_id" % index)
        if evidence_id in evidence_ids:
            raise PublishError("duplicate evidence_id: %s" % evidence_id)
        evidence_ids.add(evidence_id)
        item = {
            "evidence_id": evidence_id,
            "source_ids": unique_text_list(raw.get("source_ids"), "evidence[%d].source_ids" % index),
        }
        dangling = set(item["source_ids"]) - source_ids
        if dangling:
            raise PublishError("evidence %s has dangling source_ids: %s" % (evidence_id, sorted(dangling)))
        if "text" in raw:
            item["text"] = require_text(raw["text"], "evidence[%d].text" % index)
        evidence.append(item)

    raw_claims = require_list(case.get("claims"), "claims")
    claims = []
    claim_ids = set()
    uncertainties = []
    for index, raw in enumerate(raw_claims):
        label = "claims[%d]" % index
        raw = require_dict(raw, label)
        claim_id = require_text(raw.get("claim_id"), label + ".claim_id")
        if claim_id in claim_ids:
            raise PublishError("duplicate claim_id: %s" % claim_id)
        claim_ids.add(claim_id)
        item = {
            "claim_id": claim_id,
            "subject": normalize_term(raw.get("subject"), label + ".subject", False),
            "predicate": normalize_term(raw.get("predicate"), label + ".predicate", False),
            "object": normalize_term(raw.get("object"), label + ".object", True),
            "evidence_ids": unique_text_list(raw.get("evidence_ids"), label + ".evidence_ids"),
            "polarity": raw.get("polarity", "positive"),
            "hedged": raw.get("hedged", False),
        }
        if item["polarity"] not in {"positive", "negative"}:
            raise PublishError("%s.polarity must be positive or negative" % label)
        if not isinstance(item["hedged"], bool):
            raise PublishError("%s.hedged must be boolean" % label)
        dangling = set(item["evidence_ids"]) - evidence_ids
        if dangling:
            raise PublishError("claim %s has dangling evidence_ids: %s" % (claim_id, sorted(dangling)))
        for key in ("condition", "hedge", "uncertainty"):
            if key in raw:
                item[key] = require_text(raw[key], label + "." + key)
        if "hedge" in item and not item["hedged"]:
            raise PublishError("%s.hedge requires hedged=true" % label)
        if item["polarity"] == "negative":
            uncertainties.append({"claim_id": claim_id, "kind": "negative", "text": "Assertion is explicitly negative and reified."})
        if "condition" in item:
            uncertainties.append({"claim_id": claim_id, "kind": "conditional", "text": item["condition"]})
        if "hedge" in item:
            uncertainties.append({"claim_id": claim_id, "kind": "hedged", "text": item["hedge"]})
        if "uncertainty" in item:
            uncertainties.append({"claim_id": claim_id, "kind": "declared", "text": item["uncertainty"]})
        claims.append(item)
    return claims, evidence, sources, uncertainties


def validate_output_references(result, mapping):
    def canonical_value(name):
        for output_name, value in result.items():
            source = mapping.get(output_name, output_name if output_name in CANONICAL else "contract_values")
            if source == name:
                return value
        return []

    claims = canonical_value("claims")
    evidence = canonical_value("evidence")
    sources = canonical_value("sources")
    publications = canonical_value("publications")
    if not all(isinstance(value, list) for value in (claims, evidence, sources, publications)):
        raise PublishError("mapped claims/evidence/sources/publications outputs must be arrays")
    claim_ids = [item["claim_id"] for item in claims]
    evidence_ids = [item["evidence_id"] for item in evidence]
    source_ids = [item["source_id"] for item in sources]
    if len(set(claim_ids)) != len(claim_ids) or len(set(evidence_ids)) != len(evidence_ids) or len(set(source_ids)) != len(source_ids):
        raise PublishError("duplicate identifiers in result readback")
    for item in claims:
        if set(item["evidence_ids"]) - set(evidence_ids):
            raise PublishError("dangling claim evidence reference in result: %s" % item["claim_id"])
    for item in evidence:
        if set(item["source_ids"]) - set(source_ids):
            raise PublishError("dangling evidence source reference in result: %s" % item["evidence_id"])
    for publication in publications:
        if set(publication["claim_ids"]) - set(claim_ids):
            raise PublishError("dangling publication claim reference in result")
    return {
        "claims": len(claims),
        "evidence": len(evidence),
        "sources": len(sources),
        "references_complete": True,
    }


def add_quad(graphs, graph_name, subject, predicate, obj):
    graphs[graph_name].append((subject, iri_term(predicate), obj))


def build_nanopub(case_id, claims, evidence, sources, publication_options):
    publication_options = require_dict(publication_options, "manifest.publication")
    allowed_options = {"creator_iri", "license_iri", "created"}
    if set(publication_options) - allowed_options:
        raise PublishError("manifest.publication has unsupported fields; refusing to guess metadata")
    publication = local_iri(case_id, "publication")
    head = local_iri(case_id, "Head")
    assertion = local_iri(case_id, "assertion")
    provenance = local_iri(case_id, "provenance")
    pubinfo = local_iri(case_id, "pubinfo")
    graphs = {head: [], assertion: [], provenance: [], pubinfo: []}

    add_quad(graphs, head, iri_term(publication), RDF + "type", iri_term(NP + "Nanopublication"))
    add_quad(graphs, head, iri_term(publication), NP + "hasAssertion", iri_term(assertion))
    add_quad(graphs, head, iri_term(publication), NP + "hasProvenance", iri_term(provenance))
    add_quad(graphs, head, iri_term(publication), NP + "hasPublicationInfo", iri_term(pubinfo))

    evidence_nodes = {item["evidence_id"]: local_iri(case_id, "evidence", item["evidence_id"]) for item in evidence}
    source_nodes = {item["source_id"]: local_iri(case_id, "source", item["source_id"]) for item in sources}
    statement_nodes = {}
    for claim in claims:
        statement = local_iri(case_id, "statement", claim["claim_id"])
        statement_nodes[claim["claim_id"]] = statement
        add_quad(graphs, assertion, iri_term(statement), RDF + "type", iri_term(RDF + "Statement"))
        add_quad(graphs, assertion, iri_term(statement), RDF + "subject", term_to_rdf(claim["subject"], False))
        add_quad(graphs, assertion, iri_term(statement), RDF + "predicate", term_to_rdf(claim["predicate"], False))
        add_quad(graphs, assertion, iri_term(statement), RDF + "object", term_to_rdf(claim["object"]))
        add_quad(graphs, assertion, iri_term(statement), CGP + "claimId", literal_term(claim["claim_id"]))
        add_quad(graphs, assertion, iri_term(statement), CGP + "polarity", literal_term(claim["polarity"]))
        add_quad(graphs, assertion, iri_term(statement), CGP + "hedged", literal_term("true" if claim["hedged"] else "false", datatype="http://www.w3.org/2001/XMLSchema#boolean"))
        for key, predicate in (("condition", "condition"), ("hedge", "hedge"), ("uncertainty", "uncertainty")):
            if key in claim:
                add_quad(graphs, assertion, iri_term(statement), CGP + predicate, literal_term(claim[key]))

    add_quad(graphs, provenance, iri_term(provenance), CGP + "describesAssertion", iri_term(assertion))
    for claim in claims:
        for evidence_id in claim["evidence_ids"]:
            add_quad(graphs, provenance, iri_term(statement_nodes[claim["claim_id"]]), PROV + "wasDerivedFrom", iri_term(evidence_nodes[evidence_id]))
    for item in evidence:
        node = iri_term(evidence_nodes[item["evidence_id"]])
        add_quad(graphs, provenance, node, CGP + "evidenceId", literal_term(item["evidence_id"]))
        for source_id in item["source_ids"]:
            add_quad(graphs, provenance, node, PROV + "wasDerivedFrom", iri_term(source_nodes[source_id]))
        if "text" in item:
            add_quad(graphs, provenance, node, CGP + "evidenceText", literal_term(item["text"]))
    for item in sources:
        node = iri_term(source_nodes[item["source_id"]])
        add_quad(graphs, provenance, node, CGP + "sourceId", literal_term(item["source_id"]))
        for key, predicate in (("title", "title"), ("locator", "locator")):
            if key in item:
                add_quad(graphs, provenance, node, CGP + predicate, literal_term(item[key]))

    add_quad(graphs, pubinfo, iri_term(pubinfo), CGP + "describesPublication", iri_term(publication))
    add_quad(graphs, pubinfo, iri_term(publication), CGP + "iriStatus", literal_term("local-unregistered"))
    add_quad(graphs, pubinfo, iri_term(publication), CGP + "trustyStatus", literal_term("not-generated"))
    if "creator_iri" in publication_options:
        add_quad(graphs, pubinfo, iri_term(publication), DCTERMS + "creator", iri_term(validate_iri(publication_options["creator_iri"], "manifest.publication.creator_iri")))
    if "license_iri" in publication_options:
        add_quad(graphs, pubinfo, iri_term(publication), DCTERMS + "license", iri_term(validate_iri(publication_options["license_iri"], "manifest.publication.license_iri")))
    if "created" in publication_options:
        created = require_text(publication_options["created"], "manifest.publication.created")
        add_quad(graphs, pubinfo, iri_term(publication), DCTERMS + "created", literal_term(created, datatype="http://www.w3.org/2001/XMLSchema#dateTime"))

    record = {
        "claim_ids": [claim["claim_id"] for claim in claims],
        "publication_iri": publication,
        "head_graph": head,
        "assertion_graph": assertion,
        "provenance_graph": provenance,
        "pubinfo_graph": pubinfo,
        "iri_status": "local-unregistered",
        "trusty_status": "not-generated",
    }
    return graphs, record


def render_trig_term(term):
    if term["kind"] == "iri":
        return "<%s>" % term["value"]
    text = json.dumps(term["value"], ensure_ascii=False)
    if "language" in term:
        text += "@" + term["language"]
    if "datatype" in term:
        text += "^^<%s>" % term["datatype"]
    return text


def render_trig(graphs):
    lines = ["# Strict local TriG subset; local IRIs are not registered or Trusty URIs."]
    for graph_name, quads in graphs.items():
        lines.append("<%s> {" % graph_name)
        for subject, predicate, obj in quads:
            lines.append("%s %s %s ." % (render_trig_term(subject), render_trig_term(predicate), render_trig_term(obj)))
        lines.append("}")
    return "\n".join(lines) + "\n"


def parse_trig_term(text):
    if text.startswith("<") and text.endswith(">"):
        return iri_term(validate_iri(text[1:-1], "TriG IRI"))
    if not text.startswith('"'):
        raise PublishError("unsupported TriG term")
    try:
        value, end = json.JSONDecoder().raw_decode(text)
    except json.JSONDecodeError as exc:
        raise PublishError("invalid TriG literal: %s" % exc)
    if not isinstance(value, str):
        raise PublishError("TriG literal is not a string")
    suffix = text[end:]
    if not suffix:
        return literal_term(value)
    if suffix.startswith("@"):
        if not re.fullmatch(r"@[A-Za-z0-9-]+", suffix):
            raise PublishError("invalid TriG language tag")
        return literal_term(value, language=suffix[1:])
    if suffix.startswith("^^<") and suffix.endswith(">"):
        return literal_term(value, datatype=validate_iri(suffix[3:-1], "TriG datatype"))
    raise PublishError("unsupported TriG literal suffix")


def parse_trig_subset(text):
    token = r'(?:<[^>]+>|"(?:[^"\\]|\\.)*"(?:@[A-Za-z0-9-]+|\^\^<[^>]+>)?)'
    triple_pattern = re.compile(r"^(%s) (%s) (%s) \.$" % (token, token, token))
    graphs = {}
    current = None
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line or line.startswith("#"):
            continue
        if current is None:
            match = re.fullmatch(r"<([^>]+)> \{", line)
            if not match:
                raise PublishError("TriG subset parse error at line %d" % line_number)
            current = validate_iri(match.group(1), "TriG graph name")
            if current in graphs:
                raise PublishError("duplicate TriG graph: %s" % current)
            graphs[current] = []
        elif line == "}":
            current = None
        else:
            match = triple_pattern.fullmatch(line)
            if not match:
                raise PublishError("TriG subset triple parse error at line %d" % line_number)
            graphs[current].append(tuple(parse_trig_term(match.group(index)) for index in range(1, 4)))
    if current is not None:
        raise PublishError("unterminated TriG graph")
    return graphs


def rdf_object_json(term):
    if term["kind"] == "iri":
        return {"@id": term["value"]}
    value = {"@value": term["value"]}
    if "language" in term:
        value["@language"] = term["language"]
    if "datatype" in term:
        value["@datatype"] = term["datatype"]
    return value


def render_jsonld(graphs):
    graph_values = []
    for graph_name, quads in graphs.items():
        nodes = {}
        for subject, predicate, obj in quads:
            node = nodes.setdefault(subject["value"], {"@id": subject["value"]})
            if predicate["value"] == RDF + "type" and obj["kind"] == "iri":
                node.setdefault("@type", []).append(obj["value"])
            else:
                node.setdefault(predicate["value"], []).append(rdf_object_json(obj))
        graph_values.append({"@id": graph_name, "@graph": list(nodes.values())})
    return json_text({"@graph": graph_values})


def parse_jsonld_subset(path):
    document = require_dict(load_json(path), "nanopubs.jsonld")
    if set(document) != {"@graph"}:
        raise PublishError("JSON-LD top level must contain only @graph")
    graphs = {}
    for graph in require_list(document["@graph"], "JSON-LD @graph"):
        graph = require_dict(graph, "JSON-LD named graph")
        if set(graph) != {"@id", "@graph"}:
            raise PublishError("JSON-LD named graph must contain only @id and @graph")
        name = validate_iri(graph["@id"], "JSON-LD graph name")
        if name in graphs:
            raise PublishError("duplicate JSON-LD graph")
        graphs[name] = []
        for node in require_list(graph["@graph"], "JSON-LD graph nodes"):
            node = require_dict(node, "JSON-LD node")
            subject = iri_term(validate_iri(node.get("@id"), "JSON-LD node @id"))
            for predicate, values in node.items():
                if predicate == "@id":
                    continue
                if predicate == "@type":
                    for value in require_list(values, "JSON-LD @type"):
                        graphs[name].append((subject, iri_term(RDF + "type"), iri_term(validate_iri(value, "JSON-LD type"))))
                    continue
                validate_iri(predicate, "JSON-LD property")
                for value in require_list(values, "JSON-LD property values"):
                    value = require_dict(value, "JSON-LD value")
                    if set(value) == {"@id"}:
                        obj = iri_term(validate_iri(value["@id"], "JSON-LD object @id"))
                    else:
                        if "@value" not in value or not isinstance(value["@value"], str):
                            raise PublishError("JSON-LD literal must have a string @value")
                        if set(value) - {"@value", "@language", "@datatype"}:
                            raise PublishError("unsupported JSON-LD literal keys")
                        obj = literal_term(value["@value"], value.get("@language"), value.get("@datatype"))
                    graphs[name].append((subject, iri_term(predicate), obj))
    return graphs


def quad_multiset(quads):
    return sorted(json.dumps(quad, sort_keys=True, ensure_ascii=False) for quad in quads)


def validate_rdf_semantics(graphs, trig_graphs, jsonld_graphs, record, claims):
    if set(graphs) != {record["head_graph"], record["assertion_graph"], record["provenance_graph"], record["pubinfo_graph"]}:
        raise PublishError("nanopublication must have exactly Head/assertion/provenance/pubinfo graphs")
    for name in graphs:
        if quad_multiset(graphs[name]) != quad_multiset(trig_graphs.get(name, [])):
            raise PublishError("TriG round-trip differs in graph %s" % name)
        if quad_multiset(graphs[name]) != quad_multiset(jsonld_graphs.get(name, [])):
            raise PublishError("JSON-LD round-trip differs in graph %s" % name)
    if set(trig_graphs) != set(graphs) or set(jsonld_graphs) != set(graphs):
        raise PublishError("RDF graph names differ across representations")

    head_quads = graphs[record["head_graph"]]
    link_targets = {}
    for predicate, suffix in ((NP + "hasAssertion", "assertion_graph"), (NP + "hasProvenance", "provenance_graph"), (NP + "hasPublicationInfo", "pubinfo_graph")):
        matches = [obj["value"] for subj, pred, obj in head_quads if subj["value"] == record["publication_iri"] and pred["value"] == predicate]
        if len(matches) != 1 or matches[0] != record[suffix]:
            raise PublishError("Head has invalid part link: %s" % predicate)
        link_targets[predicate] = matches
    if len([quad for quad in head_quads if quad[1]["value"] in link_targets]) != 3:
        raise PublishError("Head must contain exactly three nanopublication part links")
    if not any(quad[1]["value"] == RDF + "type" and quad[2].get("value") == NP + "Nanopublication" for quad in head_quads):
        raise PublishError("Head lacks Nanopublication type")

    assertion_quads = graphs[record["assertion_graph"]]
    all_quads = [quad for quads in graphs.values() for quad in quads]
    for claim in claims:
        claim_statements = [subj["value"] for subj, pred, obj in assertion_quads if pred["value"] == CGP + "claimId" and obj.get("value") == claim["claim_id"]]
        if len(claim_statements) != 1:
            raise PublishError("assertion must have one reified statement per claim_id")
        statement = claim_statements[0]
        expected = {
            RDF + "type": iri_term(RDF + "Statement"),
            RDF + "subject": term_to_rdf(claim["subject"], False),
            RDF + "predicate": term_to_rdf(claim["predicate"], False),
            RDF + "object": term_to_rdf(claim["object"]),
        }
        for predicate, obj in expected.items():
            if not any(subj["value"] == statement and pred["value"] == predicate and obj == actual for subj, pred, actual in assertion_quads):
                raise PublishError("reified statement component missing for %s" % claim["claim_id"])
        direct = (term_to_rdf(claim["subject"], False), term_to_rdf(claim["predicate"], False), term_to_rdf(claim["object"]))
        if claim["polarity"] == "negative" or claim["hedged"] or "condition" in claim:
            if any(quad == direct for quad in all_quads):
                raise PublishError("qualified claim leaked as unconditional triple: %s" % claim["claim_id"])
    if not any(pred["value"] == CGP + "describesAssertion" and obj.get("value") == record["assertion_graph"] for subj, pred, obj in graphs[record["provenance_graph"]]):
        raise PublishError("provenance does not reference assertion")
    if not any(obj.get("value") == record["publication_iri"] and pred["value"] == CGP + "describesPublication" for subj, pred, obj in graphs[record["pubinfo_graph"]]):
        raise PublishError("pubinfo does not reference publication")
    statuses = {(pred["value"], obj.get("value")) for subj, pred, obj in graphs[record["pubinfo_graph"]] if subj["value"] == record["publication_iri"]}
    if (CGP + "iriStatus", "local-unregistered") not in statuses or (CGP + "trustyStatus", "not-generated") not in statuses:
        raise PublishError("pubinfo must disclose local unregistered non-Trusty status")
    return {
        "structural_self_check": "passed",
        "trig_subset_round_trip": "passed",
        "jsonld_subset_round_trip": "passed",
        "named_graph_count": len(graphs),
        "graph_quad_counts": {name: len(quads) for name, quads in graphs.items()},
        "reified_claim_count": len(claims),
        "qualified_direct_triple_leaks": 0,
        "limitation": "Strict generated-subset parsing and structural checks only; not complete W3C syntax/conformance validation. Local IRIs are neither registered nor Trusty URIs.",
    }


def validate_resources(path):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PublishError("cannot read resources.yaml: %s" % exc)
    limits = {}
    for key in ("max_requests", "max_seconds"):
        match = re.search(r"^%s:\s*(\d+)\s*$" % key, text, re.MULTILINE)
        if not match:
            raise PublishError("resources.yaml lacks integer %s" % key)
        limits[key] = int(match.group(1))
    if not 0 <= limits["max_requests"] <= 64 or not 1 <= limits["max_seconds"] <= 900:
        raise PublishError("resource limits exceed 64 requests or 900 seconds")
    return limits


def make_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, help="Input case.json")
    parser.add_argument("--task", required=True, help="Input task.md (read as UTF-8; schema is not inferred from prose)")
    parser.add_argument("--resources", required=True, help="environment/resources.yaml")
    parser.add_argument("--work", required=True, help="Writable work directory for early partial output")
    parser.add_argument("--output", required=True, help="Final output directory")
    return parser


def run(args):
    started = time.monotonic()
    work = Path(args.work)
    output = Path(args.output)
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    limits = validate_resources(args.resources)
    deadline = started + limits["max_seconds"]
    try:
        task_text = Path(args.task).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PublishError("cannot read UTF-8 task.md: %s" % exc)
    if not task_text.strip():
        raise PublishError("task.md must not be empty")
    case = require_dict(load_json(args.case), "case.json")
    case_id, fields, manifest, mapping, contract_values = parse_contract(case)
    canonical = {
        "case_id": case_id,
        "claims": [],
        "evidence": [],
        "sources": [],
        "uncertainty": [{"kind": "partial", "text": "Input normalization is incomplete; no completed publication is claimed."}],
        "change_records": [{"sequence": 0, "status": "partial", "action": "Contract accepted before claim normalization."}],
        "publications": [],
    }
    partial = render_result(fields, mapping, contract_values, canonical)
    write_text(work / "result.partial.json", json_text(partial))

    claims, evidence, sources, uncertainties = normalize_input(case)
    canonical.update({"claims": claims, "evidence": evidence, "sources": sources, "uncertainty": uncertainties})
    canonical["change_records"] = [
        {"sequence": 0, "status": "partial", "action": "Contract accepted before claim normalization."},
        {"sequence": 1, "status": "partial", "action": "Normalized claims, evidence, sources, and checked original references."},
    ]
    partial = render_result(fields, mapping, contract_values, canonical)
    write_text(work / "result.partial.json", json_text(partial))

    publications = []
    graphs = None
    record = None
    if manifest["request_format"] == "rdf":
        if not claims:
            raise PublishError("RDF publication requires at least one claim")
        graphs, record = build_nanopub(case_id, claims, evidence, sources, manifest.get("publication", {}))
        publications.append(record)
    canonical["publications"] = publications
    canonical["change_records"].append({"sequence": 2, "status": "complete", "action": "Local publication assembled; no network requests and no registration claimed."})
    candidate = render_result(fields, mapping, contract_values, canonical)
    candidate_path = work / "result.candidate.json"
    write_text(candidate_path, json_text(candidate))
    validate_result_readback(candidate_path, fields, case_id)
    reference_report = validate_output_references(candidate, mapping)
    validation = {
        "candidate_readback": "passed",
        "exact_top_level_keys": fields,
        "case_id_preserved": True,
        "candidate_reference_checks": reference_report,
        "request_format": manifest["request_format"],
        "network_requests": 0,
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "artifact_scope": "JSON base result; JSONL only when requested; both RDF files only for request_format=rdf",
    }

    candidate_jsonl = None
    candidate_trig = None
    candidate_jsonld = None
    if manifest["request_format"] == "jsonl":
        candidate_jsonl = "".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n" for item in claims)
        jsonl_candidate_path = work / "claims.candidate.jsonl"
        write_text(jsonl_candidate_path, candidate_jsonl)
        try:
            lines = jsonl_candidate_path.read_text(encoding="utf-8").splitlines()
            loaded_lines = [json.loads(line, object_pairs_hook=reject_duplicate_keys) for line in lines]
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise PublishError("JSONL candidate readback failed: %s" % exc)
        if len(lines) != len(claims) or loaded_lines != claims:
            raise PublishError("JSONL candidate differs from normalized claims")
        validation["jsonl_candidate_readback"] = {"status": "passed", "record_count": len(lines)}

    if manifest["request_format"] == "rdf":
        candidate_trig = render_trig(graphs)
        candidate_jsonld = render_jsonld(graphs)
        trig_candidate_path = work / "nanopubs.candidate.trig"
        jsonld_candidate_path = work / "nanopubs.candidate.jsonld"
        write_text(trig_candidate_path, candidate_trig)
        write_text(jsonld_candidate_path, candidate_jsonld)
        trig_graphs = parse_trig_subset(trig_candidate_path.read_text(encoding="utf-8"))
        jsonld_graphs = parse_jsonld_subset(jsonld_candidate_path)
        validation["rdf_candidate"] = validate_rdf_semantics(graphs, trig_graphs, jsonld_graphs, record, claims)

    if time.monotonic() > deadline:
        raise PublishError("local processing exceeded max_seconds")

    result_path = output / "result.json"
    write_text(result_path, json_text(candidate))
    readback = validate_result_readback(result_path, fields, case_id)
    reference_report = validate_output_references(readback, mapping)
    validation["result_readback"] = "passed"
    validation["reference_checks"] = reference_report

    if manifest["request_format"] == "jsonl":
        jsonl_path = output / "claims.jsonl"
        write_text(jsonl_path, candidate_jsonl)
        lines = jsonl_path.read_text(encoding="utf-8").splitlines()
        try:
            loaded_lines = [json.loads(line, object_pairs_hook=reject_duplicate_keys) for line in lines]
        except json.JSONDecodeError as exc:
            raise PublishError("final JSONL readback failed: %s" % exc)
        if len(lines) != len(claims) or loaded_lines != claims:
            raise PublishError("final JSONL differs from normalized claims")
        validation["jsonl_readback"] = {"status": "passed", "record_count": len(lines)}

    if manifest["request_format"] == "rdf":
        trig_path = output / "nanopubs.trig"
        jsonld_path = output / "nanopubs.jsonld"
        write_text(trig_path, candidate_trig)
        write_text(jsonld_path, candidate_jsonld)
        trig_graphs = parse_trig_subset(trig_path.read_text(encoding="utf-8"))
        jsonld_graphs = parse_jsonld_subset(jsonld_path)
        validation["rdf"] = validate_rdf_semantics(graphs, trig_graphs, jsonld_graphs, record, claims)
    validation["elapsed_seconds"] = round(time.monotonic() - started, 6)
    write_text(output / "validation-report.json", json_text(validation))
    print(json.dumps({"status": "ok", "output": str(result_path), "checks": validation}, ensure_ascii=False))
    return 0


def main(argv=None):
    args = make_parser().parse_args(argv)
    try:
        return run(args)
    except PublishError as exc:
        work = Path(args.work)
        work.mkdir(parents=True, exist_ok=True)
        write_text(work / "publish-error.json", json_text({"status": "error", "error": str(exc), "complete_publication_claimed": False}))
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
