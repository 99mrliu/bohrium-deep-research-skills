#!/usr/bin/env python3
"""Semantic reaction/network validator and compact layered SVG renderer.

Python standard library only. The input graph, not layout heuristics, is the
source of scientific meaning. This program never infers an interaction.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

SCHEMA_VERSION = "semantic-reaction-network/1.0"
EDGE_KINDS = {
    "material_flow", "sequence", "activation", "inhibition", "catalysis",
    "transport", "measurement",
}
NODE_KINDS = {"entity", "process", "measurement", "chart"}
CARRIERS = {"material", "control", "signal", "data"}
GENERIC_MARKERS = {"arrow", "generic", "generic-arrow", "default-arrow"}


class SemanticError(Exception):
    pass


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def issue(level, code, path, message, source_refs=None):
    return {
        "level": level,
        "code": code,
        "path": path,
        "message": message,
        "source_refs": source_refs or [],
    }


def endpoint(edge, side):
    value = edge.get(side, {})
    return value.get("node"), value.get("port")


def port_lookup(node):
    return {p.get("id"): p for p in node.get("ports", [])}


def edge_family(kind):
    if kind in {"material_flow", "transport"}:
        return "material"
    if kind == "sequence":
        return "sequence"
    return None


def tarjan(nodes, adjacency):
    index = 0
    stack, on_stack = [], set()
    indices, low = {}, {}
    components = []

    def visit(v):
        nonlocal index
        indices[v] = low[v] = index
        index += 1
        stack.append(v)
        on_stack.add(v)
        for w in sorted(adjacency.get(v, [])):
            if w not in indices:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], indices[w])
        if low[v] == indices[v]:
            component = []
            while True:
                w = stack.pop()
                on_stack.remove(w)
                component.append(w)
                if w == v:
                    break
            components.append(sorted(component))

    for node in sorted(nodes):
        if node not in indices:
            visit(node)
    return sorted(components)


def validate_chart(node, base_dir: Path, issues):
    config = node.get("chart")
    path = f"nodes[{node.get('id')}].chart"
    if not isinstance(config, dict):
        issues.append(issue("error", "CHART_CONFIG_MISSING", path,
                            "Chart nodes require explicit CSV mappings."))
        return None
    csv_value = config.get("csv_path")
    if not csv_value:
        issues.append(issue("error", "CHART_CSV_MISSING", path + ".csv_path",
                            "A real CSV path is required; inline invented series are not accepted."))
        return None
    csv_path = (base_dir / csv_value).resolve() if not Path(csv_value).is_absolute() else Path(csv_value)
    if not csv_path.is_file():
        issues.append(issue("error", "CHART_CSV_NOT_FOUND", path + ".csv_path",
                            f"CSV does not exist: {csv_value}"))
        return None
    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            rows = list(reader)
    except (OSError, csv.Error, UnicodeError) as exc:
        issues.append(issue("error", "CHART_CSV_UNREADABLE", path + ".csv_path", str(exc)))
        return None
    x, y = config.get("x"), config.get("y")
    if not headers or len(set(headers)) != len(headers):
        issues.append(issue("error", "CHART_HEADERS_INVALID", path,
                            "CSV headers must be nonempty and unique."))
    for role, column in (("x", x), ("y", y)):
        if column not in headers:
            issues.append(issue("error", "CHART_COLUMN_MISSING", path + "." + role,
                                f"Mapped {role} column {column!r} is not an actual CSV header."))
    series = config.get("series")
    if series and series not in headers:
        issues.append(issue("error", "CHART_COLUMN_MISSING", path + ".series",
                            f"Series column {series!r} is not an actual CSV header."))
    if len(rows) < 2:
        issues.append(issue("error", "CHART_TOO_FEW_ROWS", path,
                            "At least two actual CSV rows are required."))
    parsed = []
    for index, row in enumerate(rows, start=2):
        try:
            xv = float(row[x])
            yv = float(row[y])
            if not (math.isfinite(xv) and math.isfinite(yv)):
                raise ValueError("non-finite number")
        except (KeyError, TypeError, ValueError):
            issues.append(issue("error", "CHART_VALUE_INVALID", path,
                                f"CSV line {index} has an invalid mapped numeric value."))
            continue
        parsed.append({"csv_line": index, "x": xv, "y": yv,
                       "series": row.get(series, "") if series else "data"})
    if parsed and x in headers and y in headers:
        return {
            "path": str(csv_path), "sha256": sha256(csv_path), "headers": headers,
            "row_count": len(rows), "x": x, "y": y, "series": series,
            "panel": config.get("panel", "chart"), "rows": parsed,
            "x_label": config.get("x_label", x), "y_label": config.get("y_label", y),
        }
    return None


def validate_graph(graph, base_dir: Path):
    issues = []
    chart_data = {}
    if graph.get("schema_version") != SCHEMA_VERSION:
        issues.append(issue("error", "SCHEMA_VERSION", "schema_version",
                            f"Expected {SCHEMA_VERSION!r}."))
    if not graph.get("case_id"):
        issues.append(issue("error", "CASE_ID_MISSING", "case_id", "case_id is required."))
    compartments = graph.get("compartments", [])
    compartment_ids = {c.get("id") for c in compartments}
    if len(compartment_ids) != len(compartments) or None in compartment_ids:
        issues.append(issue("error", "COMPARTMENT_IDS", "compartments",
                            "Compartment IDs must be unique and nonnull."))
    nodes = graph.get("nodes", [])
    node_map = {n.get("id"): n for n in nodes if n.get("id")}
    if len(node_map) != len(nodes):
        issues.append(issue("error", "NODE_IDS", "nodes", "Node IDs must be unique and nonempty."))
    sources = graph.get("sources", [])
    source_map = {s.get("id"): s for s in sources if s.get("id")}
    if len(source_map) != len(sources):
        issues.append(issue("error", "SOURCE_IDS", "sources", "Source IDs must be unique and nonempty."))

    for source in sources:
        value = source.get("path")
        if value:
            path = Path(value)
            resolved = (base_dir / path).resolve() if not path.is_absolute() else path
            if not resolved.is_file():
                issues.append(issue("warning", "SOURCE_FILE_MISSING", f"sources[{source.get('id')}].path",
                                    f"Declared source is unavailable: {value}", [source.get("id")]))
    for node in nodes:
        nid = node.get("id")
        npath = f"nodes[{nid}]"
        if node.get("kind") not in NODE_KINDS:
            issues.append(issue("error", "NODE_KIND", npath + ".kind",
                                f"Unsupported node kind {node.get('kind')!r}."))
        if node.get("kind") in {"entity", "process", "measurement"} and node.get("compartment") not in compartment_ids:
            issues.append(issue("error", "COMPARTMENT_ENDPOINT", npath + ".compartment",
                                "Node compartment must be a declared compartment."))
        if not node.get("label"):
            issues.append(issue("error", "NODE_LABEL", npath + ".label", "A readable label is required."))
        ports = node.get("ports", [])
        pids = [p.get("id") for p in ports]
        if len(set(pids)) != len(pids) or None in pids:
            issues.append(issue("error", "PORT_IDS", npath + ".ports", "Port IDs must be unique and nonnull."))
        for port in ports:
            if port.get("direction") not in {"in", "out"}:
                issues.append(issue("error", "PORT_DIRECTION", npath + f".ports[{port.get('id')}].direction",
                                    "Port direction must be 'in' or 'out'."))
            if port.get("carrier") not in CARRIERS:
                issues.append(issue("error", "PORT_CARRIER", npath + f".ports[{port.get('id')}].carrier",
                                    "Port carrier must be material, control, signal, or data."))
        if node.get("required") and not node.get("source_refs"):
            issues.append(issue("error", "UNSUPPORTED_REQUIRED_NODE", npath + ".source_refs",
                                f"Required node {nid} has no source evidence."))
        for ref in node.get("source_refs", []):
            if ref not in source_map:
                issues.append(issue("error", "UNKNOWN_SOURCE_REF", npath + ".source_refs",
                                    f"Undeclared source reference {ref!r}."))
        if node.get("kind") == "chart":
            data = validate_chart(node, base_dir, issues)
            config = node.get("chart") or {}
            refs = config.get("source_refs", [])
            if not refs:
                issues.append(issue("error", "CHART_SOURCE_REQUIRED", npath + ".chart.source_refs",
                                    "Chart CSV mappings require explicit source references."))
            csv_bound = False
            for ref in refs:
                if ref not in source_map:
                    issues.append(issue("error", "UNKNOWN_SOURCE_REF", npath + ".chart.source_refs",
                                        f"Undeclared source reference {ref!r}."))
                    continue
                if data:
                    source_path = Path(source_map[ref].get("path", ""))
                    resolved = (base_dir / source_path).resolve() if not source_path.is_absolute() else source_path
                    if resolved == Path(data["path"]):
                        csv_bound = True
            if data and not csv_bound:
                issues.append(issue("error", "CHART_SOURCE_NOT_CSV", npath + ".chart.source_refs",
                                    "At least one chart source_ref must resolve to the exact mapped CSV file."))
            if data:
                chart_data[nid] = data

    edges = graph.get("edges", [])
    edge_map = {e.get("id"): e for e in edges if e.get("id")}
    if len(edge_map) != len(edges):
        issues.append(issue("error", "EDGE_IDS", "edges", "Edge IDs must be unique and nonempty."))
    allowed_roles = {
        "material_flow": ({"entity"}, {"entity", "process"}, {"process"}, {"entity", "process"}),
        "transport": ({"entity"}, {"entity"}, set(), set()),
        "sequence": ({"process", "measurement"}, {"process", "measurement"}, set(), set()),
        "activation": ({"entity", "process"}, {"entity", "process"}, set(), set()),
        "inhibition": ({"entity", "process"}, {"entity", "process"}, set(), set()),
        "catalysis": ({"entity"}, {"process"}, set(), set()),
        "measurement": ({"entity", "process", "measurement"}, {"measurement", "chart"}, set(), set()),
    }
    expected_carrier = {
        "material_flow": "material", "transport": "material", "sequence": "control",
        "activation": "signal", "inhibition": "signal", "catalysis": "signal",
        "measurement": "data",
    }
    adjacency = {nid: set() for nid in node_map}
    nonfeedback_adjacency = {nid: set() for nid in node_map}
    weak = {nid: set() for nid in node_map}
    chart_incoming = {nid: 0 for nid, n in node_map.items() if n.get("kind") == "chart"}
    for edge in edges:
        eid = edge.get("id")
        epath = f"edges[{eid}]"
        kind = edge.get("kind")
        if kind not in EDGE_KINDS:
            issues.append(issue("error", "EDGE_KIND", epath + ".kind", f"Unsupported interaction {kind!r}."))
            continue
        sn, sp = endpoint(edge, "from")
        tn, tp = endpoint(edge, "to")
        source_node, target_node = node_map.get(sn), node_map.get(tn)
        if not source_node or not target_node:
            issues.append(issue("error", "ENDPOINT_UNKNOWN", epath,
                                f"Unknown endpoint {sn!r} -> {tn!r}."))
            continue
        source_port = port_lookup(source_node).get(sp)
        target_port = port_lookup(target_node).get(tp)
        if not source_port or not target_port:
            issues.append(issue("error", "PORT_UNKNOWN", epath,
                                f"Unknown port {sn}.{sp} -> {tn}.{tp}."))
            continue
        source_roles, target_roles, alt_source_roles, alt_target_roles = allowed_roles[kind]
        source_ok = source_node.get("kind") in source_roles
        target_ok = target_node.get("kind") in target_roles
        if kind == "material_flow":
            source_ok = (source_node.get("kind") in source_roles or
                         (source_node.get("kind") in alt_source_roles and target_node.get("kind") == "entity"))
            target_ok = target_node.get("kind") in target_roles or target_node.get("kind") in alt_target_roles
        if not source_ok or not target_ok:
            issues.append(issue("error", "ENDPOINT_TYPE_INCOMPATIBLE", epath,
                                f"{kind} is incompatible with {source_node.get('kind')} -> {target_node.get('kind')}."))
        if source_port.get("direction") != "out" or target_port.get("direction") != "in":
            issues.append(issue("error", "PORT_DIRECTION_INCOMPATIBLE", epath,
                                "Edges must connect an output port to an input port."))
        carrier = expected_carrier[kind]
        if source_port.get("carrier") != carrier or target_port.get("carrier") != carrier:
            issues.append(issue("error", "PORT_CARRIER_INCOMPATIBLE", epath,
                                f"{kind} requires {carrier} ports at both endpoints."))
        if kind == "transport" and source_node.get("compartment") == target_node.get("compartment"):
            issues.append(issue("error", "TRANSPORT_COMPARTMENT", epath,
                                "Transport must cross two declared compartments."))
        if kind == "catalysis" and source_node.get("entity_type") not in {"enzyme", "catalyst"}:
            issues.append(issue("error", "CATALYST_TYPE", epath,
                                "Catalysis source must have entity_type enzyme or catalyst."))
        marker = (edge.get("visual") or {}).get("marker")
        if kind in {"activation", "inhibition"}:
            required = "activation-arrow" if kind == "activation" else "inhibition-bar"
            if marker in GENERIC_MARKERS or marker != required:
                issues.append(issue("error", "REGULATION_MARKER", epath + ".visual.marker",
                                    f"{kind} must use {required}; generic arrows are forbidden for regulation."))
        if not edge.get("source_refs"):
            issues.append(issue("error", "UNSUPPORTED_MECHANISM", epath + ".source_refs",
                                f"Interaction {eid} has no evidence; it cannot be inferred by the renderer."))
        for ref in edge.get("source_refs", []):
            if ref not in source_map:
                issues.append(issue("error", "UNKNOWN_SOURCE_REF", epath + ".source_refs",
                                    f"Undeclared source reference {ref!r}."))
        if kind not in {"measurement"} and target_node.get("kind") != "chart":
            adjacency[sn].add(tn)
            if not edge.get("feedback"):
                nonfeedback_adjacency[sn].add(tn)
            weak[sn].add(tn)
            weak[tn].add(sn)
        else:
            weak[sn].add(tn)
            weak[tn].add(sn)
        if kind == "measurement" and tn in chart_incoming:
            chart_incoming[tn] += 1
    for nid, count in chart_incoming.items():
        if count == 0:
            issues.append(issue("error", "CHART_MEASUREMENT_INPUT_MISSING", f"nodes[{nid}]",
                                "A chart requires an incoming typed measurement/data edge."))

    cyclic_components = [c for c in tarjan(set(node_map), adjacency)
                         if len(c) > 1 or any(n in adjacency[n] for n in c)]
    for component in cyclic_components:
        inside = [e for e in edges if endpoint(e, "from")[0] in component and endpoint(e, "to")[0] in component]
        if not any(e.get("feedback") for e in inside):
            issues.append(issue("error", "UNDECLARED_FEEDBACK_CYCLE", "edges",
                                "Directed cycle lacks an explicit feedback edge: " + ", ".join(component)))
    residual_cycles = [c for c in tarjan(set(node_map), nonfeedback_adjacency)
                       if len(c) > 1 or any(n in nonfeedback_adjacency[n] for n in c)]
    for component in residual_cycles:
        issues.append(issue("error", "CYCLE_WITHOUT_FEEDBACK_ON_EACH_PATH", "edges",
                            "Removing feedback edges must make every directed cycle acyclic: " + ", ".join(component)))
    for edge in edges:
        if not edge.get("feedback"):
            continue
        sn, _ = endpoint(edge, "from")
        tn, _ = endpoint(edge, "to")
        if sn not in node_map or tn not in node_map:
            continue
        # sn -> tn lies on a directed cycle exactly when tn reaches sn;
        # searching sn -> tn would find the candidate edge itself trivially.
        seen, stack = set(), [tn]
        reaches = False
        while stack:
            current = stack.pop()
            if current == sn:
                reaches = True
                break
            if current in seen:
                continue
            seen.add(current)
            stack.extend(adjacency.get(current, []))
        if not reaches:
            issues.append(issue("error", "FEEDBACK_NOT_CYCLIC", f"edges[{edge.get('id')}].feedback",
                                "Feedback=true is only valid on an edge participating in a directed cycle."))

    required = {nid for nid, n in node_map.items() if n.get("required")}
    seen = set()
    components = []
    for nid in sorted(required):
        if nid in seen:
            continue
        stack, component = [nid], set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            stack.extend(weak.get(current, set()) - component)
        seen |= component
        components.append(component)
    if len(components) > 1:
        issues.append(issue("error", "DISCONNECTED_REQUIRED_NODES", "nodes",
                            "Required semantic nodes are disconnected: " +
                            "; ".join(",".join(sorted(c)) for c in components)))

    outgoing = {nid: {} for nid in node_map}
    incoming = {nid: {} for nid in node_map}
    for edge in edges:
        family = edge_family(edge.get("kind"))
        if not family:
            continue
        sn, _ = endpoint(edge, "from")
        tn, _ = endpoint(edge, "to")
        outgoing.get(sn, {}).setdefault(family, []).append(edge.get("id"))
        incoming.get(tn, {}).setdefault(family, []).append(edge.get("id"))
    for collection, flows, direction in ((graph.get("branches", []), outgoing, "outgoing"),
                                         (graph.get("joins", []), incoming, "incoming")):
        declared = set()
        for item in collection:
            nid, family = item.get("node"), item.get("family")
            key = (nid, family)
            ipath = ("branches" if direction == "outgoing" else "joins") + f"[{item.get('id')}]"
            if key in declared:
                issues.append(issue("error", "DUPLICATE_BRANCH_JOIN", ipath,
                                    "Only one declaration per node and family is allowed."))
            declared.add(key)
            if family not in {"material", "sequence"} or item.get("mode") not in {"all", "any", "xor"}:
                issues.append(issue("error", "BRANCH_JOIN_TYPE", ipath,
                                    "Family must be material/sequence and mode all/any/xor."))
                continue
            expected = set(flows.get(nid, {}).get(family, []))
            actual = set(item.get("edge_ids", []))
            if len(expected) < 2:
                issues.append(issue("error", "UNNECESSARY_BRANCH_JOIN", ipath,
                                    f"No {direction} {family} fan {'out' if direction == 'outgoing' else 'in'} requires this declaration."))
            if expected != actual:
                issues.append(issue("error", "BRANCH_JOIN_EDGE_SET", ipath + ".edge_ids",
                                    f"Expected exactly {sorted(expected)}, got {sorted(actual)}."))
            if not item.get("source_refs"):
                issues.append(issue("error", "UNSUPPORTED_BRANCH_JOIN", ipath + ".source_refs",
                                    "Branch/join mode must have evidence."))
            for ref in item.get("source_refs", []):
                if ref not in source_map:
                    issues.append(issue("error", "UNKNOWN_SOURCE_REF", ipath + ".source_refs",
                                        f"Undeclared source reference {ref!r}."))
            if item.get("mode") == "xor":
                for eid in actual:
                    if not (edge_map.get(eid, {}).get("condition")):
                        issues.append(issue("error", "XOR_CONDITION_MISSING", ipath,
                                            f"XOR branch edge {eid} requires a source-grounded condition."))
        for nid, families in flows.items():
            for family, ids in families.items():
                if len(ids) > 1 and (nid, family) not in declared:
                    issues.append(issue("error", "UNDECLARED_BRANCH" if direction == "outgoing" else "UNDECLARED_JOIN",
                                        "branches" if direction == "outgoing" else "joins",
                                        f"Node {nid} has undeclared {direction} {family} branch/join: {sorted(ids)}."))

    phases = graph.get("phase_dependencies", [])
    phase_adj = {}
    for dep in phases:
        a, b = dep.get("from_phase"), dep.get("to_phase")
        if not a or not b:
            issues.append(issue("error", "PHASE_ENDPOINT", "phase_dependencies",
                                "Phase dependencies require from_phase and to_phase."))
            continue
        phase_adj.setdefault(a, set()).add(b)
        phase_adj.setdefault(b, set())
        if not dep.get("source_refs"):
            issues.append(issue("error", "UNSUPPORTED_PHASE", "phase_dependencies",
                                f"Phase dependency {a} -> {b} requires evidence."))
        for ref in dep.get("source_refs", []):
            if ref not in source_map:
                issues.append(issue("error", "UNKNOWN_SOURCE_REF", "phase_dependencies",
                                    f"Undeclared phase source reference {ref!r}."))
    phase_nodes = set(phase_adj)
    for component in tarjan(phase_nodes, phase_adj):
        if len(component) > 1 or any(n in phase_adj[n] for n in component):
            issues.append(issue("error", "PHASE_CYCLE", "phase_dependencies",
                                "Phase dependency cycle is ambiguous: " + ", ".join(component)))
    if graph.get("source_semantics") is None:
        issues.append(issue("warning", "SOURCE_SEMANTICS_MISSING", "source_semantics",
                            "No source extraction was supplied; source-to-final comparison cannot be completed."))
    return issues, chart_data


def compare_source(graph):
    expected = graph.get("source_semantics")
    if not isinstance(expected, dict):
        return {"status": "not_verified", "matches": [], "mismatches": [
            {"code": "SOURCE_SEMANTICS_MISSING", "message": "Agent inspection record is absent."}
        ]}
    matches, mismatches = [], []
    expected_nodes = {n.get("id"): n for n in expected.get("nodes", [])}
    actual_nodes = {n.get("id"): n for n in graph.get("nodes", []) if n.get("required")}
    for nid, source in sorted(expected_nodes.items()):
        actual = actual_nodes.get(nid)
        if not actual:
            mismatches.append({"code": "SOURCE_NODE_OMITTED", "node": nid})
            continue
        for field in ("kind", "label", "compartment"):
            if field in source and source.get(field) != actual.get(field):
                mismatches.append({"code": "SOURCE_NODE_CHANGED", "node": nid, "field": field,
                                   "original": source.get(field), "final": actual.get(field)})
                break
        else:
            matches.append({"type": "node", "id": nid})
    expected_edges = {e.get("id"): e for e in expected.get("edges", [])}
    actual_edges = {e.get("id"): e for e in graph.get("edges", [])}
    for eid, source in sorted(expected_edges.items()):
        actual = actual_edges.get(eid)
        if not actual:
            mismatches.append({"code": "SOURCE_RELATION_OMITTED", "edge": eid})
            continue
        source_signature = (source.get("kind"), (source.get("from") or {}).get("node"),
                            (source.get("to") or {}).get("node"), source.get("feedback", False))
        actual_signature = (actual.get("kind"), endpoint(actual, "from")[0], endpoint(actual, "to")[0],
                            actual.get("feedback", False))
        if source_signature != actual_signature:
            mismatches.append({"code": "SOURCE_RELATION_CHANGED", "edge": eid,
                               "original": source_signature, "final": actual_signature})
        else:
            matches.append({"type": "edge", "id": eid})
    for phase in expected.get("phase_dependencies", []):
        if phase not in graph.get("phase_dependencies", []):
            mismatches.append({"code": "SOURCE_PHASE_OMITTED", "phase": phase})
        else:
            matches.append({"type": "phase", "id": f"{phase.get('from_phase')}->{phase.get('to_phase')}"})
    return {
        "status": "match" if not mismatches else "mismatch",
        "basis": "Semantic topology only; no pixel-copy comparison.",
        "review": graph.get("source_review", {}),
        "matches": matches, "mismatches": mismatches,
        "source_refs": sorted(set(expected.get("source_refs", []))),
    }


def node_size(node):
    kind = node.get("kind")
    if kind == "chart":
        return 350, 230
    if kind == "process":
        return 170, 100
    if kind == "measurement":
        return 170, 90
    return 152, 66


def layout_nodes(graph):
    """Rank placement avoids semantic lines crossing unrelated nodes; positions make no claims."""
    compartments = graph.get("compartments", [])
    grouped = {c["id"]: [] for c in compartments}
    charts = []
    for node in graph.get("nodes", []):
        if node.get("kind") == "chart":
            charts.append(node)
        else:
            grouped.setdefault(node.get("compartment"), []).append(node)
    positions = {}
    comp_boxes = []
    y0 = 92
    for comp in compartments:
        members = grouped.get(comp["id"], [])
        member_ids = {n["id"] for n in members}
        ranks = {n["id"]: 0 for n in members}
        # Longest-path ranks in the already-validated, feedback-stripped local DAG.
        for _ in range(max(1, len(members))):
            changed = False
            for edge in graph.get("edges", []):
                if edge.get("feedback"):
                    continue
                source, target = endpoint(edge, "from")[0], endpoint(edge, "to")[0]
                if source in member_ids and target in member_ids and ranks[target] < ranks[source] + 1:
                    ranks[target] = ranks[source] + 1
                    changed = True
            if not changed:
                break
        columns = max(ranks.values(), default=0) + 1
        by_rank = {rank: [n for n in members if ranks[n["id"]] == rank]
                   for rank in range(columns)}
        max_rows = max((len(items) for items in by_rank.values()), default=1)
        width = max(670, columns * 225 + 70)
        height = max(190, max_rows * 120 + 70)
        x0, top = 40, y0
        comp_boxes.append((comp, x0, top, width, height))
        for rank, items in by_rank.items():
            vertical_offset = (max_rows - len(items)) * 60
            for row, node in enumerate(items):
                w, h = node_size(node)
                positions[node["id"]] = {"x": x0 + 45 + rank * 225,
                                         "y": top + 45 + vertical_offset + row * 120, "w": w, "h": h}
        y0 += height + 34
    chart_bottom = y0
    for index, chart in enumerate(charts):
        w, h = node_size(chart)
        x, y = 310 + index * 380, y0 + 10
        positions[chart["id"]] = {"x": x, "y": y, "w": w, "h": h}
        chart_bottom = max(chart_bottom, y + h + 34)
    content_width = max([b[1] + b[3] for b in comp_boxes] +
                        [p["x"] + p["w"] + 40 for n, p in positions.items() if n in {c["id"] for c in charts}] + [800])
    # Square canvas avoids Quick Look's landscape and portrait SVG-thumbnail crops.
    content_height = max(680, chart_bottom + 55)
    canvas_w = canvas_h = max(content_width, content_height)
    return positions, comp_boxes, canvas_w, canvas_h


def text_svg(x, y, value, cls="label", anchor="start", extra=""):
    return f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}" {extra}>{escape(str(value))}</text>'


def render_chart(node, data, x, y):
    w, h = node_size(node)
    left, top, right, bottom = x + 48, y + 38, x + w - 18, y + h - 48
    rows = data["rows"]
    xs, ys = [r["x"] for r in rows], [r["y"] for r in rows]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(0, min(ys)), max(ys)
    if xmax == xmin:
        xmax = xmin + 1
    if ymax == ymin:
        ymax = ymin + 1
    def sx(v):
        return left + (v - xmin) * (right - left) / (xmax - xmin)
    def sy(v):
        return bottom - (v - ymin) * (bottom - top) / (ymax - ymin)
    colors = ["#276fbf", "#e07145", "#36875b", "#8957a5", "#b58900"]
    series_order = []
    for row in rows:
        if row["series"] not in series_order:
            series_order.append(row["series"])
    color = {name: colors[i % len(colors)] for i, name in enumerate(series_order)}
    out = [f'<rect class="chart-frame" x="{x}" y="{y}" width="{w}" height="{h}" rx="8"/>',
           text_svg(x + 16, y + 23, node.get("label", node["id"]), "node-title")]
    out.append(f'<line class="axis" x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}"/>')
    out.append(f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{bottom}"/>')
    for value in (xmin, xmax):
        tx = sx(value)
        out.append(f'<line class="tick" x1="{tx:.2f}" y1="{bottom}" x2="{tx:.2f}" y2="{bottom+4}"/>')
        out.append(text_svg(f"{tx:.2f}", bottom + 16, f"{value:g}", "tick-label", "middle"))
    for value in (ymin, ymax):
        ty = sy(value)
        out.append(f'<line class="tick" x1="{left-4}" y1="{ty:.2f}" x2="{left}" y2="{ty:.2f}"/>')
        out.append(text_svg(left - 7, f"{ty+3:.2f}", f"{value:g}", "tick-label", "end"))
    for name in series_order:
        points = sorted((r for r in rows if r["series"] == name), key=lambda r: (r["x"], r["csv_line"]))
        coords = " ".join(f"{sx(r['x']):.2f},{sy(r['y']):.2f}" for r in points)
        out.append(f'<polyline id="data-{quoteattr(node["id"])[1:-1]}-{series_order.index(name)}" class="data-series" '
                   f'data-series={quoteattr(name)} points="{coords}" stroke="{color[name]}"/>')
        for row in points:
            out.append(f'<circle class="data-point" data-csv-line="{row["csv_line"]}" '
                       f'data-x={quoteattr(str(row["x"]))} data-y={quoteattr(str(row["y"]))} '
                       f'cx="{sx(row["x"]):.2f}" cy="{sy(row["y"]):.2f}" r="3" fill="{color[name]}"/>')
    legend_y = y + 48
    for i, name in enumerate(series_order):
        out.append(f'<line x1="{right-125}" y1="{legend_y+i*17}" x2="{right-105}" y2="{legend_y+i*17}" stroke="{color[name]}" stroke-width="2"/>')
        out.append(text_svg(right - 100, legend_y + 4 + i * 17, name, "legend-label"))
    out.append(text_svg((left + right) / 2, y + h - 24, data["x_label"], "axis-label", "middle"))
    out.append(text_svg(x + 12, (top + bottom) / 2, data["y_label"], "axis-label", "middle",
                        f'transform="rotate(-90 {x+12} {(top+bottom)/2})"'))
    return out


def render_svg(graph, chart_data):
    positions, comp_boxes, width, height = layout_nodes(graph)
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">',
           f'<title>{escape(graph.get("title", graph.get("case_id", "Semantic network")))}</title>',
           '<desc>Layered editable semantic network. Interaction meaning is encoded by data-kind and distinct regulators markers; layout is secondary.</desc>',
           '''<defs>
  <marker id="marker-material" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#263f5f"/></marker>
  <marker id="marker-sequence" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#667085"/></marker>
  <marker id="marker-transport" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#087e8b"/></marker>
  <marker id="marker-activation" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="8" markerHeight="8" orient="auto"><path d="M1 1 L11 6 L1 11" fill="none" stroke="#238636" stroke-width="2"/><path d="M5 3 V9 M2 6 H8" stroke="#238636" stroke-width="1.4"/></marker>
  <marker id="marker-inhibition" viewBox="0 0 10 12" refX="9" refY="6" markerWidth="8" markerHeight="9" orient="auto"><path d="M8 0 V12" stroke="#c9363e" stroke-width="3"/></marker>
  <marker id="marker-catalysis" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="8" markerHeight="8" orient="auto"><path d="M1 1 L11 6 L1 11" fill="none" stroke="#7a5195" stroke-width="2"/><circle cx="3" cy="6" r="2" fill="#fff" stroke="#7a5195"/></marker>
  <marker id="marker-measurement" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><circle cx="5" cy="5" r="3" fill="#fff" stroke="#6f42c1" stroke-width="2"/></marker>
</defs>''',
           '''<style>
.syntaxhigh{fill:none}.bg{fill:#fbfcfe}.compartment{fill:#fff;stroke:#c9d4e3;stroke-width:1.2}.compartment-alt{fill:#f5f8fc}.compartment-label{font:700 15px Arial,Helvetica,sans-serif;fill:#31435a}.title{font:700 21px Arial,Helvetica,sans-serif;fill:#172b4d}.subtitle{font:12px Arial,Helvetica,sans-serif;fill:#52637a}.entity{fill:#eef5ff;stroke:#4472a8;stroke-width:1.4}.process{fill:#fff6df;stroke:#ad7600;stroke-width:1.4}.measurement{fill:#f5efff;stroke:#7653a6;stroke-width:1.4}.chart-frame{fill:#fff;stroke:#8494a7;stroke-width:1.2}.node-title{font:700 12px Arial,Helvetica,sans-serif;fill:#15263b}.label{font:12px Arial,Helvetica,sans-serif;fill:#26374a}.small{font:10px Arial,Helvetica,sans-serif;fill:#52637a}.port{fill:#fff;stroke:#52637a;stroke-width:1}.port-label{font:8px Arial,Helvetica,sans-serif;fill:#52637a}.interaction{fill:none;stroke-width:2}.material_flow{stroke:#263f5f}.sequence{stroke:#667085;stroke-dasharray:7 4}.transport{stroke:#087e8b;stroke-width:2.5}.activation{stroke:#238636;stroke-width:2.2}.inhibition{stroke:#c9363e;stroke-width:2.2}.catalysis{stroke:#7a5195;stroke-width:2;stroke-dasharray:2 3}.measurement-edge{stroke:#6f42c1;stroke-width:1.8;stroke-dasharray:6 3}.edge-label{font:11px Arial,Helvetica,sans-serif;paint-order:stroke;stroke:#fff;stroke-width:4;stroke-linejoin:round}.axis{stroke:#596579;stroke-width:1}.tick{stroke:#596579}.tick-label,.axis-label,.legend-label{font:10px Arial,Helvetica,sans-serif;fill:#46556b}.data-series{fill:none;stroke-width:2}.data-point{stroke:#fff;stroke-width:.6}.feedback-label{font:700 10px Arial,Helvetica,sans-serif;fill:#a33a41}.legend-head{font:700 12px Arial,Helvetica,sans-serif;fill:#26374a}
</style>''',
           '<g id="layer-background" data-layer="background"><rect class="bg" x="0" y="0" width="100%" height="100%"/></g>',
           '<g id="layer-annotations" data-layer="annotations">',
           text_svg(40, 35, graph.get("title", graph.get("case_id", "Semantic network")), "title"),
           text_svg(40, 57, "SYNTHETIC EXAMPLE — NOT EXPERIMENTAL EVIDENCE" if graph.get("synthetic") else graph.get("subtitle", "Source-grounded semantic topology"), "subtitle"),
           '</g>', '<g id="layer-compartments" data-layer="compartments">']
    for index, (comp, x, y, w, h) in enumerate(comp_boxes):
        cls = "compartment compartment-alt" if index % 2 else "compartment"
        out.append(f'<rect id="compartment-{escape(comp["id"])}" class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="12"/>')
        out.append(text_svg(x + 16, y + 25, comp.get("label", comp["id"]), "compartment-label"))
    out.append('</g>')
    for layer, kinds in (("entities", {"entity"}), ("processes", {"process"}), ("measurements", {"measurement"}), ("charts", {"chart"})):
        out.append(f'<g id="layer-{layer}" data-layer="{layer}">')
        for node in graph.get("nodes", []):
            if node.get("kind") not in kinds:
                continue
            p = positions[node["id"]]
            x, y, w, h = p["x"], p["y"], p["w"], p["h"]
            if node.get("kind") == "chart":
                out.append(f'<g id="node-{escape(node["id"])}" data-node-id={quoteattr(node["id"])} data-kind="chart">')
                out.extend(render_chart(node, chart_data[node["id"]], x, y))
                for port in node.get("ports", []):
                    inputs = [q for q in node.get("ports", []) if q.get("direction") == "in"]
                    if port.get("direction") == "in":
                        py = y + (inputs.index(port) + 1) * h / (len(inputs) + 1)
                        out.append(f'<circle id="port-{escape(node["id"])}-{escape(port["id"])}" class="port" cx="{x}" cy="{py:.2f}" r="4" data-port-id={quoteattr(port["id"])} data-direction="in" data-carrier={quoteattr(port["carrier"])}/>')
                out.append('</g>')
                continue
            out.append(f'<g id="node-{escape(node["id"])}" data-node-id={quoteattr(node["id"])} data-kind={quoteattr(node["kind"])} data-compartment={quoteattr(node.get("compartment", ""))} data-source-refs={quoteattr(" ".join(node.get("source_refs", [])))}>')
            shape = f'<rect class="{node["kind"]}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{18 if node["kind"] == "entity" else 8}"/>'
            if node.get("kind") == "measurement":
                shape = f'<path class="measurement" d="M{x},{y+h/2} L{x+20},{y} H{x+w-12} L{x+w},{y+h/2} L{x+w-12},{y+h} H{x+20} Z"/>'
            out.append(shape)
            is_entity = node.get("kind") == "entity"
            out.append(text_svg(x + w / 2, y + (27 if is_entity else 20), node.get("label", node["id"]), "node-title", "middle"))
            subtype = node.get("entity_type") or node.get("phase") or node.get("kind")
            out.append(text_svg(x + w / 2, y + (46 if is_entity else h - 8), subtype, "small", "middle"))
            for port in node.get("ports", []):
                source_like = port.get("direction") == "out"
                px = x + w if source_like else x
                same_side = [q for q in node.get("ports", []) if q.get("direction") == port.get("direction")]
                index = same_side.index(port)
                py = y + (index + 1) * h / (len(same_side) + 1)
                out.append(f'<circle id="port-{escape(node["id"])}-{escape(port["id"])}" class="port" cx="{px:.2f}" cy="{py:.2f}" r="4" data-port-id={quoteattr(port["id"])} data-direction={quoteattr(port["direction"])} data-carrier={quoteattr(port["carrier"])}/>' )
                out.append(text_svg(px + (-7 if source_like else 7), py + 3, port["id"], "port-label", "end" if source_like else "start"))
            out.append('</g>')
        out.append('</g>')
    out.append('<g id="layer-interactions" data-layer="interactions">')
    for edge in graph.get("edges", []):
        sn, sp = endpoint(edge, "from")
        tn, tp = endpoint(edge, "to")
        a, b = positions.get(sn), positions.get(tn)
        if not a or not b:
            continue
        source_node = next(n for n in graph["nodes"] if n["id"] == sn)
        target_node = next(n for n in graph["nodes"] if n["id"] == tn)
        source_ports = [p for p in source_node.get("ports", []) if p.get("direction") == "out"]
        target_ports = [p for p in target_node.get("ports", []) if p.get("direction") == "in"]
        spi = next((i for i, p in enumerate(source_ports) if p["id"] == sp), 0)
        tpi = next((i for i, p in enumerate(target_ports) if p["id"] == tp), 0)
        x1 = a["x"] + a["w"]
        y1 = a["y"] + (spi + 1) * a["h"] / (len(source_ports) + 1)
        x2 = b["x"]
        y2 = b["y"] + (tpi + 1) * b["h"] / (len(target_ports) + 1)
        if x2 < x1:
            bend = max(x1, x2) + 45
            d = f"M{x1:.2f},{y1:.2f} C{bend:.2f},{y1:.2f} {bend:.2f},{y2:.2f} {x2:.2f},{y2:.2f}"
        else:
            mid = (x1 + x2) / 2
            d = f"M{x1:.2f},{y1:.2f} C{mid:.2f},{y1:.2f} {mid:.2f},{y2:.2f} {x2:.2f},{y2:.2f}"
        kind = edge["kind"]
        marker = {"material_flow": "material", "sequence": "sequence", "transport": "transport",
                  "activation": "activation", "inhibition": "inhibition", "catalysis": "catalysis",
                  "measurement": "measurement"}[kind]
        css_kind = "measurement-edge" if kind == "measurement" else kind
        out.append(f'<g id="edge-{escape(edge["id"])}" data-edge-id={quoteattr(edge["id"])} data-kind={quoteattr(kind)} data-from={quoteattr(sn+":"+sp)} data-to={quoteattr(tn+":"+tp)} data-feedback={quoteattr(str(bool(edge.get("feedback"))).lower())} data-source-refs={quoteattr(" ".join(edge.get("source_refs", [])))}>')
        out.append(f'<path class="interaction {css_kind}" d="{d}" marker-end="url(#marker-{marker})"/>')
        label = edge.get("label", kind.replace("_", " "))
        out.append(f'<title>{escape(str(label))}</title>')
        lx, ly = (x1 + x2) / 2, (y1 + y2) / 2 - 7
        color = {"activation": "#238636", "inhibition": "#c9363e", "catalysis": "#7a5195"}.get(kind, "#46556b")
        if kind not in {"material_flow", "transport"}:
            out.append(text_svg(f"{lx:.2f}", f"{ly:.2f}", label, "edge-label", "middle", f'fill="{color}"'))
        if edge.get("feedback"):
            out.append(text_svg(f"{lx:.2f}", f"{ly+14:.2f}", "explicit feedback", "feedback-label", "middle"))
        if edge.get("condition"):
            out.append(text_svg(f"{lx:.2f}", f"{ly+14:.2f}", edge["condition"], "small", "middle"))
        out.append('</g>')
    out.append('</g>')
    out.extend(['<g id="layer-legend" data-layer="legend">', text_svg(40, height - 82, "Interaction semantics", "legend-head")])
    legends = [("material", "material flow", "#263f5f"), ("sequence", "sequence", "#667085"),
               ("transport", "transport", "#087e8b"), ("activation", "activation +", "#238636"),
               ("inhibition", "inhibition ⊣", "#c9363e"), ("catalysis", "catalysis", "#7a5195"),
               ("measurement", "measurement ○", "#6f42c1")]
    for i, (marker, label, color) in enumerate(legends):
        y = 28 + i * 0  # Legend remains a compact horizontal key along the bottom.
        x = 40 + (i % 4) * 220
        by = height - 53 + (i // 4) * 22
        out.append(f'<line x1="{x}" y1="{by}" x2="{x+36}" y2="{by}" stroke="{color}" stroke-width="2" marker-end="url(#marker-{marker})"/>')
        out.append(text_svg(x + 44, by + 4, label, "legend-label"))
    out.append('</g></svg>')
    return "\n".join(out) + "\n", positions


def portable_path(path: Path, base: Path | None = None) -> str:
    """Use portable paths in reports; never leak a local author's home directory."""
    resolved = path.resolve()
    if base is not None:
        try:
            return str(resolved.relative_to(base.resolve()))
        except ValueError:
            pass
    try:
        return "~/" + str(resolved.relative_to(Path.home().resolve()))
    except ValueError:
        return str(resolved)


def portable_text(value) -> str:
    return str(value).replace(str(Path.home().resolve()), "~")[-1600:]


def _executable(path_value):
    if not path_value:
        return None
    path = Path(path_value).expanduser()
    if path.is_file() and os.access(path, os.X_OK):
        return str(path.resolve())
    return None


def discover_browsers():
    """Locate Chrome/Chromium on PATH and in conventional application locations."""
    candidates = []
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                 "chrome", "chrome-headless-shell"):
        found = shutil.which(name)
        if found:
            candidates.append((name, found))
    candidates.extend([
        ("Google Chrome", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ("Chromium", "/Applications/Chromium.app/Contents/MacOS/Chromium"),
    ])
    for variable, suffixes in (
        ("PROGRAMFILES", (r"Google\Chrome\Application\chrome.exe", r"Chromium\Application\chrome.exe")),
        ("PROGRAMFILES(X86)", (r"Google\Chrome\Application\chrome.exe", r"Chromium\Application\chrome.exe")),
        ("LOCALAPPDATA", (r"Google\Chrome\Application\chrome.exe", r"Chromium\Application\chrome.exe")),
    ):
        root = os.environ.get(variable)
        for suffix in suffixes if root else ():
            label = "Google Chrome" if suffix.startswith("Google") else "Chromium"
            candidates.append((label, str(Path(root) / suffix)))
    found, seen = [], set()
    for name, candidate in candidates:
        executable = _executable(candidate)
        if executable and executable not in seen:
            seen.add(executable)
            found.append({"name": name, "path": executable})
    return found


def detect_export_tools():
    """Return actual executable paths, without invoking or installing anything."""
    tools = {name: shutil.which(name) for name in ("rsvg-convert", "inkscape", "magick", "qlmanage")}
    return {**tools, "browsers": discover_browsers()}


def public_tool_detection(tools):
    return {
        "rsvg-convert": portable_path(Path(tools["rsvg-convert"])) if tools.get("rsvg-convert") else None,
        "inkscape": portable_path(Path(tools["inkscape"])) if tools.get("inkscape") else None,
        "magick": portable_path(Path(tools["magick"])) if tools.get("magick") else None,
        "qlmanage": portable_path(Path(tools["qlmanage"])) if tools.get("qlmanage") else None,
        "chrome_or_chromium": [
            {"name": browser["name"], "path": portable_path(Path(browser["path"]))}
            for browser in tools.get("browsers", [])
        ],
    }


def inspect_png(path: Path):
    data = path.read_bytes() if path.is_file() else b""
    signature = data.startswith(b"\x89PNG\r\n\x1a\n")
    eof = data.rstrip().endswith(b"IEND\xaeB`\x82")
    return {
        "valid": bool(signature and eof and len(data) > 45),
        "signature": signature,
        "iend": eof,
        "bytes": len(data),
    }


def inspect_pdf(path: Path):
    """Validate actual PDF structure rather than trusting an exit code or suffix."""
    data = path.read_bytes() if path.is_file() else b""
    signature = data.startswith(b"%PDF-")
    page_count = len(re.findall(rb"/Type\s*/Page(?!s)\b", data))
    eof = data.rstrip().endswith(b"%%EOF")
    result = {
        "valid": bool(signature and page_count > 0 and eof),
        "signature": signature,
        "page_count": page_count,
        "eof": eof,
        "bytes": len(data),
    }
    if result["valid"]:
        result["sha256"] = hashlib.sha256(data).hexdigest()
    return result


def _browser_size(svg_path: Path):
    try:
        root = ET.parse(svg_path).getroot()
        values = []
        for key, fallback in (("width", 1400), ("height", 1400)):
            match = re.match(r"\s*([0-9]+(?:\.[0-9]+)?)", root.get(key, ""))
            values.append(max(1, min(10000, round(float(match.group(1)) if match else fallback))))
        return values
    except (ET.ParseError, OSError, ValueError):
        return [1400, 1400]


def _attempt(command, output_path: Path, inspector):
    try:
        run = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=90)
        if run.returncode != 0:
            return None, {"returncode": run.returncode, "stderr": portable_text(run.stderr)}
        if not output_path.is_file():
            return None, {"returncode": run.returncode, "error": "Exporter returned zero without creating output."}
        checks = inspector(output_path)
        if not checks["valid"]:
            return None, {"returncode": run.returncode, "error": "Output failed structural validation.",
                          "validation": checks}
        return checks, None
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, {"error": portable_text(exc)}


def export_png(svg_path: Path, png_path: Path, tools=None):
    tools = detect_export_tools() if tools is None else tools
    png_path = png_path.resolve()
    png_path.parent.mkdir(parents=True, exist_ok=True)
    attempts = []
    with tempfile.TemporaryDirectory(prefix="srn-png-", dir=str(png_path.parent)) as tmp:
        root = Path(tmp)
        commands = []
        if tools.get("rsvg-convert"):
            commands.append(("rsvg-convert", lambda out: [tools["rsvg-convert"], str(svg_path), "-o", str(out)]))
        if tools.get("inkscape"):
            commands.append(("inkscape", lambda out: [tools["inkscape"], str(svg_path), "--export-type=png",
                                                       f"--export-filename={out}"]))
        if tools.get("magick"):
            commands.append(("magick", lambda out: [tools["magick"], str(svg_path), str(out)]))
        for index, browser in enumerate(tools.get("browsers", [])):
            def browser_command(out, browser=browser, index=index):
                width, height = _browser_size(svg_path)
                return [browser["path"], "--headless", "--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox",
                        "--no-first-run", "--no-default-browser-check", "--hide-scrollbars",
                        f"--user-data-dir={root / ('profile-png-' + str(index))}",
                        f"--window-size={width},{height}", f"--screenshot={out}", svg_path.resolve().as_uri()]
            commands.append((browser["name"], browser_command))
        for index, (name, make_command) in enumerate(commands):
            output = root / f"attempt-{index}.png"
            checks, error = _attempt(make_command(output), output, inspect_png)
            if checks:
                shutil.copyfile(output, png_path)
                return {"status": "success", "format": "png", "exporter": name,
                        "validation": checks, "attempts": attempts}
            attempts.append({"exporter": name, **(error or {"error": "Unknown export failure."})})
        if tools.get("qlmanage"):
            output_dir = root / "qlmanage"
            output_dir.mkdir()
            command = [tools["qlmanage"], "-t", "-s", "1400", "-o", str(output_dir), str(svg_path)]
            output = output_dir / (svg_path.name + ".png")
            checks, error = _attempt(command, output, inspect_png)
            if checks:
                shutil.copyfile(output, png_path)
                return {"status": "success", "format": "png", "exporter": "qlmanage",
                        "validation": checks, "attempts": attempts}
            attempts.append({"exporter": "qlmanage", **(error or {"error": "Unknown export failure."})})
    if not attempts:
        attempts.append({"error": "No supported PNG exporter was detected."})
    return {"status": "unavailable", "format": "png", "attempts": attempts}


def export_pdf(svg_path: Path, pdf_path: Path, tools=None):
    """Export a real, structurally checked PDF using independent installed tools."""
    tools = detect_export_tools() if tools is None else tools
    pdf_path = pdf_path.resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    attempts = []
    with tempfile.TemporaryDirectory(prefix="srn-pdf-", dir=str(pdf_path.parent)) as tmp:
        root = Path(tmp)
        commands = []
        if tools.get("rsvg-convert"):
            commands.append(("rsvg-convert", lambda out: [tools["rsvg-convert"], "-f", "pdf", str(svg_path),
                                                           "-o", str(out)]))
        if tools.get("inkscape"):
            commands.append(("inkscape", lambda out: [tools["inkscape"], str(svg_path), "--export-type=pdf",
                                                       f"--export-filename={out}"]))
        if tools.get("magick"):
            commands.append(("magick", lambda out: [tools["magick"], str(svg_path), str(out)]))
        for index, browser in enumerate(tools.get("browsers", [])):
            def browser_command(out, browser=browser, index=index):
                return [browser["path"], "--headless", "--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox",
                        "--no-first-run", "--no-default-browser-check", "--no-pdf-header-footer",
                        f"--user-data-dir={root / ('profile-pdf-' + str(index))}",
                        f"--print-to-pdf={out}", svg_path.resolve().as_uri()]
            commands.append((browser["name"], browser_command))
        for index, (name, make_command) in enumerate(commands):
            output = root / f"attempt-{index}.pdf"
            checks, error = _attempt(make_command(output), output, inspect_pdf)
            if checks:
                shutil.copyfile(output, pdf_path)
                return {"status": "success", "format": "pdf", "exporter": name,
                        "validation": checks, "attempts": attempts}
            attempts.append({"exporter": name, **(error or {"error": "Unknown export failure."})})
    if not attempts:
        attempts.append({"error": "No supported PDF exporter was detected."})
    return {"status": "unavailable", "format": "pdf", "attempts": attempts}


def primary_source_uncertainties(graph, base_dir):
    primary = graph.get("primary_biological_source", {})
    if not primary.get("required") or graph.get("synthetic"):
        return []
    missing = []
    for role, key in (("primary figure03", "figure"), ("caption", "caption"), ("methods", "methods")):
        sid = primary.get(key)
        source = next((s for s in graph.get("sources", []) if s.get("id") == sid), None)
        if not source:
            missing.append(f"{role} is not declared")
            continue
        path = Path(source.get("path", ""))
        resolved = (base_dir / path).resolve() if not path.is_absolute() else path
        if not path or not resolved.is_file():
            missing.append(f"{role} is unavailable: {source.get('path', '<missing>')}")
    review = graph.get("source_review", {})
    if review.get("status") != "inspected":
        missing.append("source_review is not marked inspected after reading figure03/caption/methods")
    return missing


def contracted_output_path(output_dir: Path, relative_path) -> Path:
    candidate = (output_dir / str(relative_path)).resolve()
    if candidate != output_dir and output_dir not in candidate.parents:
        raise SemanticError(f"Output contract path escapes output directory: {relative_path}")
    return candidate


CORE_CONTRACT_KEYS = {
    "editable_svg", "semantic_graph", "validation_report", "source_comparison",
    "result_json", "export_report", "preview_png",
}


def requested_contract_pdfs(contract, output_dir: Path):
    """Recognize conventional PDF keys and any other string path ending in .pdf."""
    requested = []
    for key, value in contract.items():
        conventional = key in {"export_pdf", "preview_pdf"}
        generic = key not in CORE_CONTRACT_KEYS and isinstance(value, str) and value.lower().endswith(".pdf")
        if (conventional or generic) and isinstance(value, str) and value:
            requested.append({"key": key, "path": contracted_output_path(output_dir, value)})
    return requested


def export_summary(export):
    return {key: export[key] for key in ("status", "format", "exporter", "validation") if key in export}


def build(graph_path: Path, output_dir: Path, preview_png: Path | None,
          preview_pdf: Path | None = None):
    graph_path = graph_path.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    graph = load_json(graph_path)
    issues, chart_data = validate_graph(graph, graph_path.parent)
    errors = [i for i in issues if i["level"] == "error"]
    comparison = compare_source(graph)
    if comparison["status"] == "mismatch":
        for mismatch in comparison["mismatches"]:
            issues.append(issue("error", "SOURCE_COMPARISON_MISMATCH", "source_semantics",
                                json.dumps(mismatch, ensure_ascii=False, sort_keys=True)))
        errors = [i for i in issues if i["level"] == "error"]
    uncertainties = primary_source_uncertainties(graph, graph_path.parent)
    if comparison["status"] == "not_verified":
        uncertainties.append("Source-to-final semantic comparison is not verified.")
    for warning in issues:
        if warning["level"] == "warning":
            text = f"{warning['code']}: {warning['message']}"
            if text not in uncertainties:
                uncertainties.append(text)
    case_id = graph.get("case_id", "unknown")
    contract = graph.get("output_contract", {})
    svg_path = contracted_output_path(output_dir, contract.get("editable_svg", "figure.svg"))
    semantic_path = contracted_output_path(output_dir, contract.get("semantic_graph", "semantic_graph.json"))
    report_path = contracted_output_path(output_dir, contract.get("validation_report", "validation_report.json"))
    comparison_path = contracted_output_path(output_dir, contract.get("source_comparison", "source_comparison.json"))
    export_report_path = contracted_output_path(output_dir, contract.get("export_report", "export_report.json"))
    preview_png = preview_png.resolve() if preview_png else None
    preview_pdf = preview_pdf.resolve() if preview_pdf else None
    pdf_requests = requested_contract_pdfs(contract, output_dir)
    if preview_pdf:
        pdf_requests.insert(0, {"key": "preview_pdf", "path": preview_pdf})
    # One physical path is exported once even when requested by multiple contract keys.
    unique_pdf_requests = []
    pdf_paths_seen = set()
    for request in pdf_requests:
        resolved = request["path"].resolve()
        if resolved not in pdf_paths_seen:
            pdf_paths_seen.add(resolved)
            unique_pdf_requests.append({"keys": [request["key"]], "path": resolved})
        else:
            next(item for item in unique_pdf_requests if item["path"] == resolved)["keys"].append(request["key"])
    pdf_requests = unique_pdf_requests

    positions = {}
    svg_emitted = False
    png_contract_requested = "preview_png" in contract
    png_export = ({"status": "not_supplied", "format": "png"} if png_contract_requested and not preview_png
                  else {"status": "not_requested", "format": "png"})
    pdf_exports = []
    tools = detect_export_tools()
    if png_contract_requested and not preview_png:
        uncertainties.append("Output contract includes preview_png but --preview-png was not supplied.")
    if not errors:
        svg, positions = render_svg(graph, chart_data)
        svg_path.parent.mkdir(parents=True, exist_ok=True)
        svg_path.write_text(svg, encoding="utf-8", newline="\n")
        ET.parse(svg_path)  # Well-formedness gate before delivery.
        svg_emitted = True
        if preview_png:
            png_export = export_png(svg_path, preview_png, tools)
            if png_export["status"] != "success":
                uncertainties.append("PNG preview was requested but no installed SVG exporter produced a valid PNG.")
        for request in pdf_requests:
            export = export_pdf(svg_path, request["path"], tools)
            pdf_exports.append({**request, "export": export})
            if export["status"] != "success":
                uncertainties.append(
                    "PDF output was requested for " + ", ".join(request["keys"]) +
                    " but no installed SVG exporter produced a structurally valid PDF."
                )
    else:
        uncertainties.append("Final SVG was not emitted because semantic validation errors must be fixed first.")
        if preview_png:
            png_export = {"status": "blocked", "format": "png", "reason": "semantic validation failed"}
        for request in pdf_requests:
            pdf_exports.append({**request, "export": {
                "status": "blocked", "format": "pdf", "reason": "semantic validation failed"
            }})

    semantic_output = dict(graph)
    semantic_output["resolved_chart_mappings"] = {
        nid: {key: (portable_path(Path(value), graph_path.parent) if key == "path" else value)
              for key, value in data.items() if key != "rows"}
        for nid, data in chart_data.items()
    }
    dump_json(semantic_path, semantic_output)
    validation = {
        "case_id": case_id,
        "status": "failed" if errors else ("partial" if uncertainties else "passed"),
        "semantic_error_count": len(errors),
        "issues": sorted(issues, key=lambda i: (i["level"], i["code"], i["path"], i["message"])),
        "checks": [
            "endpoint existence and node-kind compatibility", "port direction and carrier compatibility",
            "activation/inhibition distinct markers", "cycles versus explicit feedback",
            "required-node connectivity", "branch/join declarations and XOR conditions",
            "phase dependency acyclicity", "actual CSV headers and numeric rows",
            "source references on required nodes and every interaction", "source-to-render semantic comparison",
        ],
    }
    dump_json(report_path, validation)
    dump_json(comparison_path, comparison)

    png_report_requested = bool(preview_png or png_contract_requested)
    requested_exports = int(png_report_requested) + len(pdf_exports)
    successful_exports = int(png_export["status"] == "success") + sum(
        item["export"]["status"] == "success" for item in pdf_exports
    )
    export_report = {
        "case_id": case_id,
        "status": ("not_requested" if not requested_exports else
                   "success" if successful_exports == requested_exports else
                   "blocked" if errors else "partial"),
        "requested_count": requested_exports,
        "successful_count": successful_exports,
        "detected_tools": public_tool_detection(tools),
        "png": {
            "requested": png_report_requested,
            "path": (portable_path(preview_png, output_dir) if preview_png else
                     portable_path(contracted_output_path(output_dir, contract["preview_png"]), output_dir)
                     if png_contract_requested else None),
            **png_export,
        },
        "pdfs": [
            {
                "contract_keys": item["keys"],
                "path": portable_path(item["path"], output_dir),
                **item["export"],
            }
            for item in pdf_exports
        ],
        "validation": {
            "png": "PNG signature and terminal IEND chunk",
            "pdf": "%PDF- signature, at least one /Type /Page object, and terminal %%EOF",
            "stale_output_policy": "Exporters write to fresh temporary files; only validated output is copied to a requested path.",
        },
    }
    dump_json(export_report_path, export_report)

    def pdf_for_key(key):
        for item in pdf_exports:
            if key in item["keys"] and item["export"]["status"] == "success":
                return portable_path(item["path"], output_dir)
        return None

    preview_emitted = bool(preview_png and png_export.get("status") == "success" and preview_png.is_file())
    paths = {
        "editable_svg": portable_path(svg_path, output_dir) if svg_emitted else None,
        "semantic_graph": portable_path(semantic_path, output_dir),
        "validation_report": portable_path(report_path, output_dir),
        "source_comparison": portable_path(comparison_path, output_dir),
        "export_report": portable_path(export_report_path, output_dir),
        "result_json": portable_path(output_dir / "result.json", output_dir),
        "preview_png": portable_path(preview_png, output_dir) if preview_emitted else None,
        "preview_pdf": pdf_for_key("preview_pdf"),
    }
    sources = []
    for source in graph.get("sources", []):
        item = dict(source)
        value = source.get("path")
        if value:
            p = Path(value)
            resolved = (graph_path.parent / p).resolve() if not p.is_absolute() else p
            item["available"] = resolved.is_file()
            if resolved.is_file():
                item["sha256"] = sha256(resolved)
        sources.append(item)
    primary_pdf = next((item["export"] for item in pdf_exports if item["export"]["status"] != "not_requested"),
                       {"status": "not_requested", "format": "pdf"})
    result = {
        "case_id": case_id,
        "status": "failed" if errors else ("partial" if uncertainties else "success"),
        "sources": sources, "uncertainties": uncertainties,
        "change_records": graph.get("change_records", []), "paths": paths,
        "schema_version": SCHEMA_VERSION,
        "semantic_summary": {
            "required_nodes": sum(bool(n.get("required")) for n in graph.get("nodes", [])),
            "interactions": len(graph.get("edges", [])),
            "feedback_edges": [e.get("id") for e in graph.get("edges", []) if e.get("feedback")],
            "chart_mappings": {nid: {"csv": portable_path(Path(d["path"]), graph_path.parent),
                                      "sha256": d["sha256"], "headers": d["headers"],
                                      "rows": d["row_count"], "x": d["x"], "y": d["y"], "series": d["series"]}
                               for nid, d in chart_data.items()},
            "layout_positions": positions,
        },
        "export_checks": {
            "png": export_summary(png_export),
            "pdf": export_summary(primary_pdf),
            "pdf_outputs": [{"contract_keys": item["keys"], **export_summary(item["export"])}
                            for item in pdf_exports],
            "export_report": paths["export_report"],
            "svg_well_formed": svg_emitted,
            "svg_editable_layers": ["background", "compartments", "entities", "processes",
                                    "measurements", "charts", "interactions", "annotations", "legend"],
        },
    }
    for key, value in contract.items():
        if key in {"editable_svg", "semantic_graph", "validation_report", "source_comparison",
                   "preview_png", "result_json", "export_report"}:
            result[key] = paths.get(key)
        elif key in {"export_pdf", "preview_pdf"} or any(key in item["keys"] for item in pdf_exports):
            result[key] = pdf_for_key(key)
        else:
            candidate = contracted_output_path(output_dir, value)
            result[key] = portable_path(candidate, output_dir) if candidate.is_file() else None
        if key != "result_json" and result[key] is None:
            uncertainty = f"Output contract key {key!r} was not produced: {value}"
            if uncertainty not in result["uncertainties"]:
                result["uncertainties"].append(uncertainty)
    result["result_json"] = paths["result_json"]
    result["status"] = "failed" if errors else ("partial" if result["uncertainties"] else "success")
    dump_json(output_dir / "result.json", result)
    return 1 if errors else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path, help="Source-grounded semantic graph JSON")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--preview-png", type=Path)
    parser.add_argument("--preview-pdf", type=Path, help="Optional real PDF export (requires an installed exporter)")
    args = parser.parse_args(argv)
    try:
        return build(args.graph, args.output_dir, args.preview_png, args.preview_pdf)
    except (OSError, ValueError, SemanticError, ET.ParseError) as exc:
        print(f"semantic-reaction-network: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
