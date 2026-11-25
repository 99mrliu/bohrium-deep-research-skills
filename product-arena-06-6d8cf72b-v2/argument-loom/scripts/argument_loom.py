#!/usr/bin/env python3
"""Deterministic section-native argument graph audit, rendering, and assembly.

Python 3.9+; standard library only. Exit 0 means requested checks passed. Exit 2
means malformed invocation/input or an audit FAIL. No semantic-truth claim is made.
"""

import argparse
import copy
import json
import re
import sys
from pathlib import Path

NODE_TYPES = {"claim", "evidence", "warrant", "limitation", "transition", "background"}
EDGE_TYPES = {"supports", "warrants", "limits", "motivates", "transitions_to"}
SEMANTIC_STATUSES = {"unreviewed", "reviewer_confirmed", "disputed"}
LIMIT_STATUSES = {"reported", "not_reported", "not_applicable"}
PROGRESSIVE_EDGES = {"motivates", "transitions_to"}
SUPPORTED_SCHEMA = {
    "type", "properties", "required", "additionalProperties", "items", "enum",
    "const", "minLength", "maxLength", "pattern", "minItems", "maxItems",
    "uniqueItems", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "minProperties", "maxProperties", "anyOf"
}


def normalize(text):
    if not isinstance(text, str):
        return ""
    return re.sub(r"\s+", " ", text).strip()


def load_json(path):
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("cannot read valid UTF-8 JSON {}: {}".format(path, exc))
    if not isinstance(value, dict):
        raise ValueError("top-level JSON value must be an object: {}".format(path))
    return value


def write_text(path, text):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def write_json(path, value):
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


class Audit(object):
    def __init__(self, audit_type):
        self.data = {
            "audit_type": audit_type,
            "status": "PASS",
            "semantic_truth_checked": False,
            "caveat": "PASS checks deterministic anchors, topology, coverage, and contract syntax only; it does not prove semantic entailment or scientific truth.",
            "issues": [],
            "metrics": {}
        }

    def issue(self, severity, code, path, message):
        self.data["issues"].append({
            "severity": severity, "code": code, "path": path, "message": message
        })
        if severity == "ERROR":
            self.data["status"] = "FAIL"

    def error(self, code, path, message):
        self.issue("ERROR", code, path, message)

    def warning(self, code, path, message):
        self.issue("WARNING", code, path, message)

    @property
    def failed(self):
        return self.data["status"] == "FAIL"


def require(condition, audit, code, path, message):
    if not condition:
        audit.error(code, path, message)
    return condition


def source_paragraphs(source, audit):
    sections = source.get("sections")
    if not require(isinstance(sections, list) and sections, audit,
                   "SOURCE_SECTIONS", "source.sections", "must be a nonempty array"):
        return {}, {}
    by_id = {}
    orders = {}
    for s_index, section in enumerate(sections):
        spath = "source.sections[{}]".format(s_index)
        if not require(isinstance(section, dict), audit, "SOURCE_SECTION", spath, "must be an object"):
            continue
        sid = section.get("section_id")
        if not require(isinstance(sid, str) and sid, audit, "SOURCE_SECTION_ID", spath, "section_id must be nonempty"):
            continue
        if sid in by_id:
            audit.error("DUPLICATE_SECTION", spath, "duplicate section_id: " + sid)
            continue
        order = section.get("order")
        require(isinstance(order, int) and not isinstance(order, bool), audit,
                "SOURCE_ORDER", spath + ".order", "must be an integer")
        if order in orders:
            audit.error("DUPLICATE_ORDER", spath + ".order", "duplicate section order: {}".format(order))
        orders[order] = sid
        require(isinstance(section.get("title"), str) and section.get("title"), audit,
                "SOURCE_TITLE", spath + ".title", "section title must be nonempty")
        require(isinstance(section.get("purpose"), str) and section.get("purpose"), audit,
                "SOURCE_PURPOSE", spath + ".purpose", "section purpose must be nonempty")
        by_id[sid] = section
        paragraphs = section.get("paragraphs")
        if not require(isinstance(paragraphs, list) and paragraphs, audit,
                       "SOURCE_PARAGRAPHS", spath + ".paragraphs", "must be a nonempty array"):
            continue
        paragraph_ids = set()
        for p_index, paragraph in enumerate(paragraphs):
            ppath = spath + ".paragraphs[{}]".format(p_index)
            if not isinstance(paragraph, dict):
                audit.error("SOURCE_PARAGRAPH", ppath, "must be an object")
                continue
            pid = paragraph.get("paragraph_id")
            if not require(isinstance(pid, str) and pid, audit,
                           "SOURCE_PARAGRAPH_ID", ppath, "paragraph_id must be nonempty"):
                continue
            if pid in paragraph_ids:
                audit.error("DUPLICATE_PARAGRAPH", ppath, "duplicate paragraph_id in section: " + pid)
            paragraph_ids.add(pid)
            require(isinstance(paragraph.get("text"), str) and normalize(paragraph.get("text")), audit,
                    "SOURCE_TEXT", ppath + ".text", "paragraph text must be nonempty")
    lookup = {}
    for sid, section in by_id.items():
        for paragraph in section.get("paragraphs", []):
            if isinstance(paragraph, dict) and isinstance(paragraph.get("paragraph_id"), str):
                lookup[sid + "/" + paragraph["paragraph_id"]] = paragraph
    return by_id, lookup


def validate_anchor(anchor, source_id, paragraphs, audit, path):
    if not require(isinstance(anchor, dict), audit, "ANCHOR_OBJECT", path, "substantive node requires an anchor object"):
        return
    require(anchor.get("source_id") == source_id, audit, "ANCHOR_SOURCE", path + ".source_id",
            "must match graph/source source_id: " + source_id)
    locator = anchor.get("locator")
    if not require(isinstance(locator, str) and locator.count("/") == 1, audit,
                   "ANCHOR_LOCATOR", path + ".locator", "must have form section_id/paragraph_id"):
        return
    paragraph = paragraphs.get(locator)
    if not require(paragraph is not None, audit, "ANCHOR_TARGET", path + ".locator",
                   "locator does not resolve in source: " + locator):
        return
    quote = anchor.get("quote")
    if not require(isinstance(quote, str) and quote and len(quote) <= 240, audit,
                   "ANCHOR_QUOTE_LENGTH", path + ".quote", "quote must contain 1..240 Unicode characters"):
        return
    require(normalize(quote) == quote, audit, "ANCHOR_NORMALIZATION", path + ".quote",
            "quote must already use normalized single-space whitespace")
    text = normalize(paragraph.get("text", ""))
    require(quote in text, audit, "ANCHOR_QUOTE", path + ".quote",
            "quote is not a contiguous verbatim substring of normalized source text")
    start, end = anchor.get("start"), anchor.get("end")
    if (start is None) != (end is None):
        audit.error("ANCHOR_OFFSET_PAIR", path, "start and end must be supplied together or omitted")
    elif start is not None:
        valid = (isinstance(start, int) and not isinstance(start, bool) and
                 isinstance(end, int) and not isinstance(end, bool) and
                 0 <= start < end <= len(text))
        if not require(valid, audit, "ANCHOR_OFFSET_RANGE", path,
                       "offsets must be integers satisfying 0 <= start < end <= normalized text length"):
            return
        require(text[start:end] == quote, audit, "ANCHOR_OFFSET_QUOTE", path,
                "normalized text[start:end] must exactly reproduce quote")
    else:
        require(text.count(quote) == 1, audit, "ANCHOR_AMBIGUOUS", path + ".quote",
                "quote without offsets must occur exactly once in the normalized paragraph")
    if "page" in anchor:
        require(isinstance(anchor["page"], int) and not isinstance(anchor["page"], bool) and anchor["page"] >= 1,
                audit, "ANCHOR_PAGE", path + ".page", "page must be a positive integer")
        if isinstance(paragraph.get("page"), int):
            require(anchor["page"] == paragraph["page"], audit, "ANCHOR_PAGE_MISMATCH", path + ".page",
                    "page disagrees with source paragraph metadata")


def relation_ok(edge_type, source_type, target_type):
    if edge_type == "supports":
        return source_type == "evidence" and target_type == "claim"
    if edge_type == "warrants":
        return source_type == "warrant" and target_type == "claim"
    if edge_type == "limits":
        return source_type == "limitation" and target_type == "claim"
    if edge_type == "motivates":
        return source_type in {"claim", "background"} and target_type == "claim"
    if edge_type == "transitions_to":
        return source_type == "transition" and target_type in {"claim", "background"}
    return False


def check_progressive_cycles(nodes, edges, audit):
    adjacency = {node_id: [] for node_id in nodes}
    for edge in edges:
        if edge.get("type") in PROGRESSIVE_EDGES and edge.get("from") in adjacency:
            adjacency[edge["from"]].append(edge.get("to"))
    visiting, visited = set(), set()

    def visit(node_id):
        if node_id in visiting:
            audit.error("PROGRESSIVE_CYCLE", "graph.edges", "cycle in motivates/transitions_to subgraph at " + node_id)
            return
        if node_id in visited:
            return
        visiting.add(node_id)
        for target in adjacency.get(node_id, []):
            visit(target)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in adjacency:
        visit(node_id)


def validate_graph(case, source, graph):
    audit = Audit("graph")
    source_id = source.get("source_id")
    require(isinstance(source_id, str) and source_id, audit, "SOURCE_ID", "source.source_id", "must be nonempty")
    require(source.get("status") in {"readable", "partial", "unreadable"}, audit,
            "SOURCE_STATUS", "source.status", "must be readable, partial, or unreadable")
    require(graph.get("source_id") == source_id, audit, "GRAPH_SOURCE", "graph.source_id", "must equal source.source_id")
    require(isinstance(graph.get("graph_id"), str) and graph.get("graph_id"), audit,
            "GRAPH_ID", "graph.graph_id", "must be nonempty")
    require(isinstance(graph.get("paper_id"), str) and graph.get("paper_id"), audit,
            "PAPER_ID", "graph.paper_id", "must be nonempty")
    if isinstance(case.get("case_id"), str):
        audit.data["metrics"]["case_id"] = case["case_id"]
    source_sections, paragraphs = source_paragraphs(source, audit)
    graph_sections = graph.get("sections")
    if require(isinstance(graph_sections, list), audit, "GRAPH_SECTIONS", "graph.sections", "must be an array"):
        require(len(graph_sections) == len(source_sections), audit, "SECTION_INVENTORY", "graph.sections",
                "graph and source section counts must agree")
        for index, (actual, expected) in enumerate(zip(graph_sections, source.get("sections", []))):
            for key in ("section_id", "order", "title", "purpose"):
                require(isinstance(actual, dict) and actual.get(key) == expected.get(key), audit,
                        "SECTION_ALIGNMENT", "graph.sections[{}].{}".format(index, key),
                        "must exactly preserve the source section inventory")

    nodes_raw = graph.get("nodes")
    edges_raw = graph.get("edges")
    if not require(isinstance(nodes_raw, list) and nodes_raw, audit, "GRAPH_NODES", "graph.nodes", "must be a nonempty array"):
        nodes_raw = []
    if not require(isinstance(edges_raw, list), audit, "GRAPH_EDGES", "graph.edges", "must be an array"):
        edges_raw = []
    nodes, duplicate_node_ids = {}, set()
    for index, node in enumerate(nodes_raw):
        path = "graph.nodes[{}]".format(index)
        if not isinstance(node, dict):
            audit.error("NODE_OBJECT", path, "must be an object")
            continue
        node_id = node.get("id")
        if not require(isinstance(node_id, str) and node_id, audit, "NODE_ID", path + ".id", "must be nonempty"):
            continue
        if node_id in nodes:
            audit.error("DUPLICATE_NODE", path + ".id", "duplicate node ID: " + node_id)
            duplicate_node_ids.add(node_id)
            continue
        nodes[node_id] = node
        node_type = node.get("type")
        require(node_type in NODE_TYPES, audit, "NODE_TYPE", path + ".type", "unknown node type: {}".format(node_type))
        require(isinstance(node.get("text"), str) and node.get("text"), audit, "NODE_TEXT", path + ".text", "must be nonempty")
        sid = node.get("section_id")
        require(sid in source_sections, audit, "NODE_SECTION", path + ".section_id", "unknown source section: {}".format(sid))
        if sid in source_sections:
            require(node.get("section_order") == source_sections[sid].get("order"), audit,
                    "NODE_SECTION_ORDER", path + ".section_order", "must match source section order")
        require(node.get("semantic_status") in SEMANTIC_STATUSES, audit,
                "SEMANTIC_STATUS", path + ".semantic_status", "must be unreviewed, reviewer_confirmed, or disputed")
        if node_type == "claim" and node.get("core") is True:
            require(node.get("limit_status") in LIMIT_STATUSES, audit,
                    "LIMIT_STATUS", path + ".limit_status", "core claim requires reported, not_reported, or not_applicable")
            if node.get("semantic_status") != "reviewer_confirmed":
                audit.warning("SEMANTIC_REVIEW_OPEN", path + ".semantic_status",
                              "core claim is not reviewer_confirmed; human semantic review remains open")
        validate_anchor(node.get("anchor"), source_id, paragraphs, audit, path + ".anchor")

    edges, edge_ids = [], set()
    incoming = {node_id: [] for node_id in nodes}
    participants = set()
    for index, edge in enumerate(edges_raw):
        path = "graph.edges[{}]".format(index)
        if not isinstance(edge, dict):
            audit.error("EDGE_OBJECT", path, "must be an object")
            continue
        edge_id = edge.get("id")
        if not require(isinstance(edge_id, str) and edge_id, audit, "EDGE_ID", path + ".id", "must be nonempty"):
            continue
        if edge_id in edge_ids:
            audit.error("DUPLICATE_EDGE", path + ".id", "duplicate edge ID: " + edge_id)
        edge_ids.add(edge_id)
        edges.append(edge)
        edge_type = edge.get("type")
        require(edge_type in EDGE_TYPES, audit, "EDGE_TYPE", path + ".type", "unknown edge type: {}".format(edge_type))
        source_node, target_node = nodes.get(edge.get("from")), nodes.get(edge.get("to"))
        if not require(source_node is not None, audit, "EDGE_FROM", path + ".from", "unknown node: {}".format(edge.get("from"))):
            continue
        if not require(target_node is not None, audit, "EDGE_TO", path + ".to", "unknown node: {}".format(edge.get("to"))):
            continue
        require(edge["from"] != edge["to"], audit, "SELF_EDGE", path, "self-edges are not allowed")
        require(relation_ok(edge_type, source_node.get("type"), target_node.get("type")), audit,
                "RELATION_TYPE", path, "{} does not allow {} -> {}".format(edge_type, source_node.get("type"), target_node.get("type")))
        incoming[edge["to"]].append(edge)
        participants.update((edge["from"], edge["to"]))
        if edge_type in PROGRESSIVE_EDGES:
            require(target_node.get("section_order") >= source_node.get("section_order"), audit,
                    "BACKWARD_PROGRESSION", path, "motivates/transitions_to must preserve or advance section order")
    check_progressive_cycles(nodes, edges, audit)

    for node_id, node in nodes.items():
        if node.get("type") != "claim":
            require(node_id in participants, audit, "ORPHAN_NODE", "graph.nodes." + node_id,
                    "non-claim node must participate in at least one edge")
        if node.get("type") != "claim" or node.get("core") is not True:
            continue
        by_type = {kind: [edge for edge in incoming[node_id] if edge.get("type") == kind]
                   for kind in ("supports", "warrants", "limits")}
        require(bool(by_type["supports"]), audit, "MISSING_EVIDENCE", "graph.nodes." + node_id,
                "core claim requires at least one incoming evidence supports edge")
        require(bool(by_type["warrants"]), audit, "MISSING_WARRANT", "graph.nodes." + node_id,
                "core claim requires at least one incoming warrant warrants edge")
        limit_status = node.get("limit_status")
        if limit_status == "reported":
            require(bool(by_type["limits"]), audit, "MISSING_LIMITATION", "graph.nodes." + node_id,
                    "limit_status=reported requires an incoming limitation limits edge")
        elif limit_status in {"not_reported", "not_applicable"}:
            require(not by_type["limits"], audit, "LIMIT_EDGE_UNEXPECTED", "graph.nodes." + node_id,
                    "limit_status={} conflicts with an incoming limits edge".format(limit_status))

    core_claims = [node for node in nodes.values() if node.get("type") == "claim" and node.get("core") is True]
    audit.data["metrics"].update({
        "sections": len(source_sections), "nodes": len(nodes), "edges": len(edges),
        "core_claims": len(core_claims), "duplicate_node_ids": len(duplicate_node_ids)
    })
    return audit


def json_type_matches(value, expected):
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def validate_schema(value, schema, path, errors):
    if not isinstance(schema, dict):
        errors.append({"code": "SCHEMA_OBJECT", "path": path, "message": "schema must be an object"})
        return
    unsupported = sorted(set(schema) - SUPPORTED_SCHEMA)
    if unsupported:
        errors.append({"code": "UNSUPPORTED_SCHEMA", "path": path,
                       "message": "unsupported schema keywords: " + ", ".join(unsupported)})
    if "anyOf" in schema:
        branches = schema["anyOf"]
        if not isinstance(branches, list) or not branches:
            errors.append({"code": "ANYOF_SCHEMA", "path": path, "message": "anyOf must be a nonempty array"})
        else:
            for branch in branches:
                branch_errors = []
                validate_schema(value, branch, path, branch_errors)
                if not branch_errors:
                    break
            else:
                errors.append({"code": "ANYOF", "path": path, "message": "value does not satisfy any anyOf branch"})
    expected = schema.get("type")
    if expected is not None:
        choices = expected if isinstance(expected, list) else [expected]
        if not choices or not all(isinstance(choice, str) for choice in choices):
            errors.append({"code": "TYPE_SCHEMA", "path": path, "message": "type must be a string or array of strings"})
            return
        if not any(json_type_matches(value, choice) for choice in choices):
            errors.append({"code": "TYPE", "path": path, "message": "expected type {}, got {}".format(expected, type(value).__name__)})
            return
    if "const" in schema and value != schema["const"]:
        errors.append({"code": "CONST", "path": path, "message": "value does not equal const"})
    if "enum" in schema:
        if not isinstance(schema["enum"], list) or not schema["enum"]:
            errors.append({"code": "ENUM_SCHEMA", "path": path, "message": "enum must be a nonempty array"})
        elif value not in schema["enum"]:
            errors.append({"code": "ENUM", "path": path, "message": "value is not in enum"})
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append({"code": "MIN_LENGTH", "path": path, "message": "string shorter than minLength"})
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append({"code": "MAX_LENGTH", "path": path, "message": "string longer than maxLength"})
        if "pattern" in schema:
            try:
                if re.search(schema["pattern"], value) is None:
                    errors.append({"code": "PATTERN", "path": path, "message": "string does not match pattern"})
            except (re.error, TypeError):
                errors.append({"code": "PATTERN_SCHEMA", "path": path, "message": "invalid regular expression pattern"})
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        for key, code, comparison in (
            ("minimum", "MINIMUM", lambda x, bound: x >= bound),
            ("maximum", "MAXIMUM", lambda x, bound: x <= bound),
            ("exclusiveMinimum", "EXCLUSIVE_MINIMUM", lambda x, bound: x > bound),
            ("exclusiveMaximum", "EXCLUSIVE_MAXIMUM", lambda x, bound: x < bound)
        ):
            if key in schema:
                try:
                    valid = comparison(value, schema[key])
                except TypeError:
                    valid = False
                if not valid:
                    errors.append({"code": code, "path": path, "message": "numeric constraint failed: " + key})
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            errors.append({"code": "PROPERTIES_SCHEMA", "path": path, "message": "properties must be an object"})
            properties = {}
        required = schema.get("required", [])
        if not isinstance(required, list):
            errors.append({"code": "REQUIRED_SCHEMA", "path": path, "message": "required must be an array"})
            required = []
        for key in required:
            if key not in value:
                errors.append({"code": "REQUIRED", "path": path + "." + str(key), "message": "required property missing"})
        additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            item_path = path + "." + key
            if key in properties:
                validate_schema(item, properties[key], item_path, errors)
            elif additional is False:
                errors.append({"code": "ADDITIONAL_PROPERTY", "path": item_path, "message": "additional property forbidden"})
            elif isinstance(additional, dict):
                validate_schema(item, additional, item_path, errors)
        for key, code, comparison in (
            ("minProperties", "MIN_PROPERTIES", lambda x, bound: len(x) >= bound),
            ("maxProperties", "MAX_PROPERTIES", lambda x, bound: len(x) <= bound)
        ):
            if key in schema and not comparison(value, schema[key]):
                errors.append({"code": code, "path": path, "message": "object constraint failed: " + key})
    if isinstance(value, list):
        for key, code, comparison in (
            ("minItems", "MIN_ITEMS", lambda x, bound: len(x) >= bound),
            ("maxItems", "MAX_ITEMS", lambda x, bound: len(x) <= bound)
        ):
            if key in schema and not comparison(value, schema[key]):
                errors.append({"code": code, "path": path, "message": "array constraint failed: " + key})
        if schema.get("uniqueItems") is True:
            serialized = [json.dumps(item, sort_keys=True, ensure_ascii=False) for item in value]
            if len(serialized) != len(set(serialized)):
                errors.append({"code": "UNIQUE_ITEMS", "path": path, "message": "array items must be unique"})
        if "items" in schema:
            for index, item in enumerate(value):
                validate_schema(item, schema["items"], "{}[{}]".format(path, index), errors)


def validate_result(case, result):
    audit = Audit("output_contract")
    require(result.get("case_id") == case.get("case_id"), audit, "CASE_ID", "result.case_id",
            "result.case_id must exactly match case.case_id")
    contract = case.get("output_contract")
    if not require(isinstance(contract, dict), audit, "OUTPUT_CONTRACT", "case.output_contract", "must be an object"):
        return audit
    errors = []
    validate_schema(result, contract, "result", errors)
    for error in errors:
        audit.error(error["code"], error["path"], error["message"])
    audit.data["metrics"] = {
        "top_level_fields": len(result), "contract_issues": len(errors),
        "required_fields": contract.get("required", [])
    }
    return audit


def is_synthetic(case, source):
    """Only an explicit boolean case/source flag enables synthetic labelling."""
    return case.get("synthetic") is True or source.get("synthetic") is True


def anchor_text(node):
    anchor = node.get("anchor", {})
    return "{} · {} · \"{}\"".format(anchor.get("source_id", "?"), anchor.get("locator", "?"), anchor.get("quote", ""))


def md(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def render_notes(source, graph, result_status, synthetic=False):
    lines = ["# Section-aligned argument notes", ""]
    if synthetic:
        lines.extend([
            "> **合成示例 / non-official / SYNTHETIC EXAMPLE**",
            "> Unique fictional paper; not an official answer. Deterministic audits do not prove semantic truth.", ""
        ])
    else:
        lines.extend(["> Deterministic audits do not prove semantic truth or complete interpretation.", ""])
    lines.extend([
        "- **Paper:** " + source.get("title", graph.get("paper_id", "unknown")),
        "- **Source status:** " + source.get("status", "unknown"),
        "- **Assembly status:** " + result_status,
        "- **Graph:** " + graph.get("graph_id", "unknown"), ""
    ])
    nodes_by_id = {node["id"]: node for node in graph["nodes"]}
    for section in sorted(graph["sections"], key=lambda item: item["order"]):
        lines.extend(["## {}. {}".format(section["order"] + 1, section["title"]), "",
                      "**Purpose.** " + section["purpose"], ""])
        section_nodes = [node for node in graph["nodes"] if node["section_id"] == section["section_id"]]
        if not section_nodes:
            lines.extend(["_No graph node reported for this section._", ""])
        for node in section_nodes:
            core = " (core)" if node.get("core") is True else ""
            lines.extend(["### {} — {}{}".format(node["id"], node["type"], core), "", node["text"], "",
                          "- **Anchor:** " + anchor_text(node),
                          "- **Semantic review:** " + node.get("semantic_status", "unreviewed")])
            incoming = [edge for edge in graph["edges"] if edge["to"] == node["id"]]
            if node.get("type") == "claim":
                lines.append("- **Limit status:** " + node.get("limit_status", "not_reported"))
                for kind, label in (("supports", "Evidence"), ("warrants", "Warrants/reasoning"), ("limits", "Limitations")):
                    related = [nodes_by_id[edge["from"]] for edge in incoming if edge["type"] == kind]
                    if related:
                        lines.append("- **{}:**".format(label))
                        for related_node in related:
                            lines.append("  - {}: {} ({})".format(related_node["id"], related_node["text"], anchor_text(related_node)))
                    elif kind == "limits":
                        lines.append("- **Limitations:** no limitation edge; status is " + node.get("limit_status", "not_reported"))
            lines.append("")
    lines.extend(["## Uncertainties", ""])
    lines.extend("- " + item for item in graph.get("uncertainties", []))
    lines.extend(["", "## Change records", ""])
    for record in graph.get("change_records", []):
        lines.append("- **{}:** {}".format(record.get("action", "record"), record.get("detail", "")))
    return "\n".join(lines).rstrip() + "\n"


def render_graph_markdown(source, graph, synthetic=False):
    lines = ["# Argument graph", ""]
    if synthetic:
        lines.append("**合成示例 / non-official / SYNTHETIC EXAMPLE — not an official answer.**")
    else:
        lines.append("**Source-grounded working graph; deterministic checks do not certify semantic truth.**")
    lines.extend(["",
        "Source `{}`; graph `{}`. Edges preserve typed argument relations and source section order.".format(source.get("source_id"), graph.get("graph_id")), "",
        "| Edge | Type | From | To | From section → To section |",
        "|---|---|---|---|---|"
    ])
    nodes = {node["id"]: node for node in graph["nodes"]}
    for edge in graph["edges"]:
        source_node, target_node = nodes[edge["from"]], nodes[edge["to"]]
        lines.append("| {} | {} | {} | {} | {} → {} |".format(
            md(edge["id"]), md(edge["type"]), md(edge["from"]), md(edge["to"]),
            md(source_node["section_id"]), md(target_node["section_id"])))
    lines.extend(["", "## Core-claim coverage", "", "| Claim | Section | Evidence | Warrants | Limit status | Limitations | Semantic status |",
                  "|---|---|---|---|---|---|---|"])
    for node in graph["nodes"]:
        if node.get("type") != "claim" or node.get("core") is not True:
            continue
        incoming = [edge for edge in graph["edges"] if edge["to"] == node["id"]]
        related = {kind: ", ".join(edge["from"] for edge in incoming if edge["type"] == kind) or "—"
                   for kind in ("supports", "warrants", "limits")}
        lines.append("| {} | {} | {} | {} | {} | {} | {} |".format(
            md(node["id"]), md(node["section_id"]), related["supports"], related["warrants"],
            md(node.get("limit_status", "missing")), related["limits"], md(node.get("semantic_status", "missing"))))
    lines.extend(["", "## Audit boundary", "",
                  "A structural PASS is not a semantic-truth certificate. Read the anchored quotes and notes for the recorded human/agent review status.", ""])
    return "\n".join(lines)


def open_core_claims(graph):
    nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
    if not isinstance(nodes, list):
        return []
    return sorted(node.get("id", "<missing-id>") for node in nodes
                  if isinstance(node, dict) and node.get("type") == "claim" and
                  node.get("core") is True and node.get("semantic_status") != "reviewer_confirmed")


def overall_state(source, graph, audit):
    if audit.failed:
        return "failed"
    if source.get("status") != "readable" or open_core_claims(graph):
        return "partial"
    return "complete"


def constrained_status_values(schema):
    if not isinstance(schema, dict):
        return None
    constrained = any(key in schema for key in ("enum", "const", "anyOf"))
    if not constrained:
        return None
    values = set()
    if isinstance(schema.get("enum"), list):
        values.update(value for value in schema["enum"] if isinstance(value, str))
    if isinstance(schema.get("const"), str):
        values.add(schema["const"])
    if isinstance(schema.get("anyOf"), list):
        for branch in schema["anyOf"]:
            branch_values = constrained_status_values(branch)
            if branch_values is None:
                return None
            values.update(branch_values)
    return values


def select_status(state, contract, response):
    """Honor success/complete vocabulary and never let an overlay upgrade reality."""
    properties = contract.get("properties", {}) if isinstance(contract, dict) else {}
    schema = properties.get("status", {}) if isinstance(properties, dict) else {}
    allowed = constrained_status_values(schema)
    default = {"complete": "success", "partial": "partial", "failed": "failed"}[state]
    requested = response.get("status") if isinstance(response, dict) else None
    ranks = {"failed": 0, "partial": 1, "complete": 2, "success": 2}
    maximum = ranks[state]
    if allowed is None:
        if requested in ranks and ranks[requested] <= maximum:
            return requested
        return default
    if requested in allowed and requested in ranks and ranks[requested] <= maximum:
        return requested
    choices = [value for value in allowed if value in ranks and ranks[value] <= maximum]
    if not choices:
        return None
    preferred_rank = max(ranks[value] for value in choices)
    choices = [value for value in choices if ranks[value] == preferred_rank]
    for preferred in (default, "success", "complete", "partial", "failed"):
        if preferred in choices:
            return preferred
    return sorted(choices)[0]


def source_status_record(source):
    sections = source.get("sections")
    count = len(sections) if isinstance(sections, list) else 0
    raw_status = source.get("status")
    status = raw_status if raw_status in {"readable", "partial", "unreadable", "missing"} else "unreadable"
    if status == "readable":
        detail = "Source registry marks all {} registered sections readable; this does not claim semantic completeness.".format(count)
    elif status == "partial":
        detail = "Source recovery is partial across {} registered sections; unread or unresolved material prevents complete status.".format(count)
    elif status == "missing":
        detail = "The required source is missing; no section-reading completeness is claimed."
    else:
        detail = "Source text is unreadable or invalid across the {} registered sections; no complete reading is claimed.".format(count)
    return {"source_id": source.get("source_id", "unknown"), "status": status, "detail": detail}


def merge_overlay(base, overlay):
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_overlay(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def apply_response(candidate, response, contract, audit):
    response = response or {}
    properties = contract.get("properties", {}) if isinstance(contract, dict) else {}
    if not isinstance(properties, dict):
        properties = {}
    closed = isinstance(contract, dict) and contract.get("additionalProperties") is False
    if closed:
        for key in sorted(set(response) - set(properties)):
            audit.error("RESPONSE_PROPERTY", "response." + key,
                        "response field is not declared by the closed output contract")
    result = merge_overlay(candidate, response)
    if closed:
        result = {key: value for key, value in result.items() if key in properties}
    for key in properties:
        if key not in result:
            audit.error("RESPONSE_FIELD", "result." + key,
                        "declared contract property was not assembled; supply task-specific values with --response")
    return result


def render_failure_notes(source, audit, status, synthetic):
    lines = ["# Section-aligned argument notes unavailable", ""]
    if synthetic:
        lines.extend(["> **合成示例 / non-official / SYNTHETIC EXAMPLE**",
                      "> Unique fictional input; no complete graph or notes are claimed.", ""])
    lines.extend([
        "Assembly status: **{}**. The supplied graph did not pass deterministic validation; no graph-derived notes are claimed.".format(status),
        "", "Source status: **{}**.".format(source.get("status", "unknown")), "", "## Validation issues", ""
    ])
    lines.extend("- {}: {}".format(issue["code"], issue["message"]) for issue in audit.data["issues"])
    lines.extend(["", "See `audit.json`. The input graph, when parseable, is preserved separately without repairing or inventing content.", ""])
    return "\n".join(lines)


def render_failure_graph(source, status, synthetic):
    lines = ["# Argument graph unavailable", ""]
    if synthetic:
        lines.extend(["**合成示例 / non-official / SYNTHETIC EXAMPLE — no complete graph is claimed.**", ""])
    lines.extend([
        "Assembly status: **{}** for source `{}`. Graph rendering stopped after validation errors; no edges, claims, or coverage are inferred.".format(status, md(source.get("source_id", "unknown"))),
        "", "See `audit.json` and the preserved input graph. No structural or semantic PASS is claimed.", ""
    ])
    return "\n".join(lines)


def assemble(case, source, graph, output_dir, response=None, graph_error=None):
    output = Path(output_dir)
    if graph_error is None:
        audit = validate_graph(case, source, graph)
    else:
        audit = Audit("graph")
        audit.error("GRAPH_INPUT", "graph", graph_error)
        audit.data["metrics"] = {"sections": 0, "nodes": 0, "edges": 0, "core_claims": 0}
    graph_failed = audit.failed
    audit_path = output / "audit.json"
    write_json(audit_path, audit.data)

    safe_graph = graph if isinstance(graph, dict) else {}
    state = overall_state(source, safe_graph, audit)
    contract = case.get("output_contract", {})
    response = response or {}
    status = select_status(state, contract, response)
    if status is None:
        audit.error("STATUS_ENUM", "case.output_contract.properties.status",
                    "contract cannot represent the required {} status without falsely upgrading it".format(state))
        write_json(audit_path, audit.data)
        return audit

    uncertainties = list(safe_graph.get("uncertainties", [])) if isinstance(safe_graph.get("uncertainties"), list) else []
    review_open = open_core_claims(safe_graph)
    if review_open:
        uncertainties.append("Overall status is downgraded because core claims are unreviewed, unresolved, or disputed: " + ", ".join(review_open) + ".")
    if source.get("status") != "readable":
        uncertainties.append("Overall status is downgraded because source recovery is not fully readable.")
    if graph_failed:
        uncertainties.append("Assembly failed deterministic graph validation; no complete argument graph is claimed.")
    if not uncertainties:
        uncertainties.append("No graph uncertainties were supplied; deterministic validation still cannot establish semantic completeness.")
    changes = copy.deepcopy(safe_graph.get("change_records", [])) if isinstance(safe_graph.get("change_records"), list) else []
    changes.append({
        "action": "assemble",
        "detail": "Recorded an honest failed/partial result without rendering graph content; checked the output contract." if graph_failed else
                  "Deterministically rendered graph JSON/Markdown and section-aligned notes; checked the output contract."
    })
    synthetic = is_synthetic(case, source)
    if graph_failed:
        summary = "Assembly failed deterministic graph validation; inspect audit.json and preserved input."
    else:
        nodes = safe_graph.get("nodes", [])
        edges = safe_graph.get("edges", [])
        summary = "Assembled {} section-native nodes, {} typed edges, and {} core claims.".format(
            len(nodes), len(edges), audit.data["metrics"].get("core_claims", 0))
    if synthetic:
        summary = "合成示例 / non-official: " + summary
    candidate = {
        "case_id": case.get("case_id"),
        "status": status,
        "summary": summary,
        "outputs": {
            "argument_graph": "argument_graph.json", "notes": "notes.md",
            "graph_markdown": "graph.md", "audit": "audit.json"
        },
        "source_status": [source_status_record(source)],
        "uncertainties": uncertainties,
        "change_records": changes
    }
    result = apply_response(candidate, response, contract, audit)
    # select_status already permits conservative overlays; never re-admit an upgrade here.
    result["status"] = status
    if isinstance(contract, dict) and contract.get("additionalProperties") is False:
        properties = contract.get("properties", {})
        if not isinstance(properties, dict) or "status" not in properties:
            result.pop("status", None)
    contract_audit = validate_result(case, result)
    for issue in contract_audit.data["issues"]:
        audit.issue(issue["severity"], issue["code"], issue["path"], issue["message"])

    if graph_failed:
        preserved_graph = safe_graph if graph_error is None else {
            "source_id": source.get("source_id", "unknown"),
            "assembly_status": "unavailable",
            "detail": "Graph input was not readable as valid JSON; no graph content was reconstructed."
        }
        write_json(output / "argument_graph.json", preserved_graph)
        write_text(output / "notes.md", render_failure_notes(source, audit, status, synthetic))
        write_text(output / "graph.md", render_failure_graph(source, status, synthetic))
    elif not audit.failed:
        write_json(output / "argument_graph.json", safe_graph)
        write_text(output / "notes.md", render_notes(source, safe_graph, status, synthetic))
        write_text(output / "graph.md", render_graph_markdown(source, safe_graph, synthetic))

    response_invalid = any(issue["code"] in {"RESPONSE_FIELD", "RESPONSE_PROPERTY"}
                           for issue in audit.data["issues"])
    if not contract_audit.failed and not response_invalid:
        write_json(output / "result.json", result)
    write_json(audit_path, audit.data)
    return audit


def command_assemble(args):
    try:
        case, source = load_json(args.case), load_json(args.source)
        response = load_json(args.response) if args.response else {}
    except ValueError as exc:
        print("FAIL: " + str(exc), file=sys.stderr)
        return 2
    try:
        graph = load_json(args.graph)
        audit = assemble(case, source, graph, args.output_dir, response)
    except ValueError as exc:
        audit = assemble(case, source, {}, args.output_dir, response, graph_error=str(exc))
    print("{}: graph assembly audit ({} issues); semantic truth not machine-checked".format(
        audit.data["status"], len(audit.data["issues"])))
    return 2 if audit.failed else 0


def command_audit(args):
    try:
        case, source, graph = (load_json(path) for path in (args.case, args.source, args.graph))
        audit = validate_graph(case, source, graph)
        write_json(args.output, audit.data)
    except ValueError as exc:
        print("FAIL: " + str(exc), file=sys.stderr)
        return 2
    print("{}: graph audit ({} issues); semantic truth not machine-checked".format(audit.data["status"], len(audit.data["issues"])))
    return 2 if audit.failed else 0


def command_check_result(args):
    try:
        case, result = load_json(args.case), load_json(args.result)
        audit = validate_result(case, result)
        write_json(args.output, audit.data)
    except ValueError as exc:
        print("FAIL: " + str(exc), file=sys.stderr)
        return 2
    print("{}: output contract audit ({} issues)".format(audit.data["status"], len(audit.data["issues"])))
    return 2 if audit.failed else 0


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    assemble_parser = subparsers.add_parser("assemble", help="audit a graph, render notes/Markdown, and assemble contracted result.json")
    assemble_parser.add_argument("--case", required=True, help="actual case.json containing case_id and output_contract")
    assemble_parser.add_argument("--source", required=True, help="normalized source JSON registry")
    assemble_parser.add_argument("--graph", required=True, help="argument graph JSON")
    assemble_parser.add_argument("--response", help="JSON object overlay for direct answers and contract-specific declared fields")
    assemble_parser.add_argument("--output-dir", required=True, help="directory for contracted artifacts")
    assemble_parser.set_defaults(func=command_assemble)
    audit_parser = subparsers.add_parser("audit", help="audit source anchors, graph references/topology, and core-claim coverage")
    audit_parser.add_argument("--case", required=True)
    audit_parser.add_argument("--source", required=True)
    audit_parser.add_argument("--graph", required=True)
    audit_parser.add_argument("--output", required=True, help="audit JSON path")
    audit_parser.set_defaults(func=command_audit)
    result_parser = subparsers.add_parser("check-result", help="validate an existing result.json against case.output_contract")
    result_parser.add_argument("--case", required=True)
    result_parser.add_argument("--result", required=True)
    result_parser.add_argument("--output", required=True, help="contract audit JSON path")
    result_parser.set_defaults(func=command_check_result)
    return parser


def main(argv=None):
    try:
        args = build_parser().parse_args(argv)
        return args.func(args)
    except OSError as exc:
        print("FAIL: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
