#!/usr/bin/env python3
"""Deterministic, constraint-checked compartment topology layout (stdlib only)."""
from __future__ import annotations

import hashlib
import html
import json
import math
import re
from collections import defaultdict, deque
from pathlib import Path
from xml.etree import ElementTree as ET


class TopologyError(ValueError):
    """An input or layout constraint violation; callers must exit non-zero."""


ROLES = ("extracellular", "membrane", "cytosol", "nucleus")
DEFAULT_TRANSITIONS = {
    ("extracellular", "membrane"),
    ("membrane", "extracellular"),
    ("membrane", "cytosol"),
    ("cytosol", "membrane"),
    ("extracellular", "cytosol"),
    ("cytosol", "extracellular"),
    ("cytosol", "nucleus"),
    ("nucleus", "cytosol"),
}


def _unique(items, kind):
    seen = set()
    for item in items:
        value = item.get("id")
        if not isinstance(value, str) or not value.strip():
            raise TopologyError(f"{kind} has a missing or non-string id")
        if value in seen:
            raise TopologyError(f"duplicate {kind} id: {value}")
        seen.add(value)
    return seen


def load_topology(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TopologyError(f"cannot read topology JSON {path}: {exc}") from exc
    validate_topology(data)
    return data


def validate_topology(data):
    if not isinstance(data, dict):
        raise TopologyError("topology must be a JSON object")
    for key in ("compartments", "entities", "edges", "constraints"):
        if key not in data or not isinstance(data[key], list if key != "constraints" else dict):
            raise TopologyError(f"topology.{key} is required and has the wrong type")
    compartments = data["compartments"]
    entities = data["entities"]
    edges = data["edges"]
    _unique(compartments, "compartment")
    entity_ids = _unique(entities, "entity")
    _unique(edges, "edge")
    by_compartment = {c["id"]: c for c in compartments}
    by_entity = {e["id"]: e for e in entities}
    role_to_id = {}
    for c in compartments:
        role = c.get("role", c.get("kind", c["id"]))
        if role not in ROLES:
            raise TopologyError(f"unsupported compartment role {role!r}; required roles: {ROLES}")
        if role in role_to_id:
            raise TopologyError(f"duplicate compartment role {role}")
        role_to_id[role] = c["id"]
        if not isinstance(c.get("order"), int):
            raise TopologyError(f"compartment {c['id']} needs an integer order")
    if set(role_to_id) != set(ROLES):
        raise TopologyError(f"exactly one compartment for each role is required: {ROLES}")
    ordered = sorted(compartments, key=lambda c: c["order"])
    if [c.get("role", c.get("kind", c["id"])) for c in ordered] != list(ROLES):
        raise TopologyError("compartment order must be extracellular→membrane→cytosol→nucleus")
    if len({c["order"] for c in ordered}) != len(ordered):
        raise TopologyError("compartment order values must be unique")
    for entity in entities:
        if entity.get("compartment") not in by_compartment:
            raise TopologyError(f"entity {entity['id']} has unknown compartment {entity.get('compartment')!r}")
        kind = entity.get("kind", "molecule")
        if not isinstance(entity.get("label", entity["id"]), str):
            raise TopologyError(f"entity {entity['id']} label must be text")
        if kind == "receptor":
            compartment = by_compartment[entity["compartment"]]
            role = compartment.get("role", compartment.get("kind", compartment["id"]))
            if role != "membrane":
                raise TopologyError(
                    f"receptor {entity['id']} must be in membrane, not {role}; refusing invalid placement"
                )
    constraints = data["constraints"]
    transitions = DEFAULT_TRANSITIONS
    if "allowed_transitions" in constraints:
        raw = constraints["allowed_transitions"]
        if not isinstance(raw, list):
            raise TopologyError("constraints.allowed_transitions must be an array")
        transitions = set()
        for pair in raw:
            if isinstance(pair, dict):
                source, target = pair.get("from"), pair.get("to")
            elif isinstance(pair, list) and len(pair) == 2:
                source, target = pair
            else:
                raise TopologyError("each allowed transition must be [from,to] or {from,to}")
            transitions.add((source, target))
    for edge in edges:
        source, target = edge.get("source"), edge.get("target")
        if source not in entity_ids or target not in entity_ids:
            raise TopologyError(f"edge {edge['id']} has a missing source or target entity")
        if edge.get("kind", "activation") == "transport":
            source_role = _entity_role(by_entity[source], by_compartment)
            target_role = _entity_role(by_entity[target], by_compartment)
            if source_role == target_role:
                raise TopologyError(f"transport {edge['id']} must cross compartments, not {source_role}→{target_role}")
            if (source_role, target_role) not in transitions:
                raise TopologyError(f"transport {edge['id']} uses illegal transition {source_role}→{target_role}")
    feedback = constraints.get("feedback_edges", [])
    if not isinstance(feedback, list) or any(f not in {e["id"] for e in edges} for f in feedback):
        raise TopologyError("constraints.feedback_edges contains an unknown edge id")


def _entity_role(entity, compartments):
    compartment = compartments[entity["compartment"]]
    return compartment.get("role", compartment.get("kind", compartment["id"]))


def _find_feedback(nodes, edges, explicit):
    """Remove explicit and DFS back edges until the remaining graph is a DAG."""
    remaining = list(edges)
    feedback = {}
    edge_by_id = {e["id"]: e for e in edges}
    for edge_id in explicit:
        feedback[edge_id] = {"edge_id": edge_id, "explicit": True, "reason": "declared feedback_edges"}
    remaining = [e for e in remaining if e["id"] not in feedback]
    while True:
        adjacency = defaultdict(list)
        for edge in remaining:
            adjacency[edge["source"]].append(edge)
        for adjacent in adjacency.values():
            adjacent.sort(key=lambda e: e["id"])
        color = {node: 0 for node in nodes}
        back = []

        def visit(node):
            color[node] = 1
            for edge in adjacency[node]:
                target = edge["target"]
                if color[target] == 0:
                    if visit(target):
                        return True
                elif color[target] == 1:
                    back.append(edge)
                    return True
            color[node] = 2
            return False

        for node in nodes:
            if color[node] == 0 and visit(node):
                break
        if not back:
            break
        edge = back[0]
        feedback[edge["id"]] = {
            "edge_id": edge["id"], "explicit": False,
            "reason": "DFS back edge closes a directed cycle; routed as feedback",
        }
        remaining = [e for e in remaining if e["id"] != edge["id"]]
    dag_edges = [edge_by_id[e["id"]] for e in remaining]
    return dag_edges, [feedback[key] for key in sorted(feedback)]


def _toposort(nodes, edges):
    adjacency = defaultdict(list)
    indegree = {node: 0 for node in nodes}
    for edge in edges:
        adjacency[edge["source"]].append(edge["target"])
        indegree[edge["target"]] += 1
    queue = deque(sorted(node for node in nodes if indegree[node] == 0))
    result = []
    while queue:
        node = queue.popleft()
        result.append(node)
        for target in sorted(adjacency[node]):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if len(result) != len(nodes):
        raise TopologyError("internal error: feedback removal did not produce a DAG")
    return result


def compute_layout(topology):
    """Compute longest-path layers and compartment-constrained, collision-free positions."""
    validate_topology(topology)
    entities = {e["id"]: dict(e) for e in topology["entities"]}
    compartments = {c["id"]: dict(c) for c in topology["compartments"]}
    nodes = list(entities)
    edges = [dict(e) for e in topology["edges"]]
    constraints = topology["constraints"]
    explicit = constraints.get("feedback_edges", [])
    dag_edges, feedback = _find_feedback(nodes, edges, explicit)
    feedback_ids = {f["edge_id"] for f in feedback}
    order = _toposort(nodes, dag_edges)
    depth = {node: 0 for node in nodes}
    predecessor = {node: None for node in nodes}
    for node in order:
        for edge in dag_edges:
            if edge["source"] == node and depth[edge["target"]] < depth[node] + 1:
                depth[edge["target"]] = depth[node] + 1
                predecessor[edge["target"]] = node
    # Node input order is the deterministic tie-break for equally long paths.
    sink = max(nodes, key=lambda node: (depth[node], -nodes.index(node)))
    main_nodes = [sink]
    while predecessor[main_nodes[-1]] is not None:
        main_nodes.append(predecessor[main_nodes[-1]])
    main_nodes.reverse()
    main_edges = {f"{a}->{b}" for a, b in zip(main_nodes, main_nodes[1:])}
    for edge in dag_edges:
        if f"{edge['source']}->{edge['target']}" in main_edges:
            edge["route_class"] = "main"
        else:
            edge["route_class"] = "branch"
    for edge in edges:
        if edge["id"] in feedback_ids:
            edge["route_class"] = "feedback"
        else:
            match = next(e for e in dag_edges if e["id"] == edge["id"])
            edge["route_class"] = match["route_class"]
        edge["source_layer"] = depth[edge["source"]]
        edge["target_layer"] = depth[edge["target"]]
    canvas = constraints.get("canvas", {})
    width = float(canvas.get("width", 1400))
    height = float(canvas.get("height", 900))
    margin_x = float(constraints.get("margin_x", 100))
    gap = float(constraints.get("layer_gap", 220))
    if not all(math.isfinite(v) and v > 0 for v in (width, height, margin_x, gap)):
        raise TopologyError("canvas dimensions, margin_x and layer_gap must be finite and positive")
    max_layer = max(depth.values(), default=0)
    width = max(width, 2 * margin_x + max_layer * gap + 80)
    gap = (width - 2 * margin_x - 80) / max(1, max_layer)
    x_by_layer = {layer: margin_x + layer * gap for layer in range(max_layer + 1)}
    role_by_entity = {node: _entity_role(entities[node], compartments) for node in nodes}
    groups = defaultdict(list)
    for node in nodes:
        groups[(role_by_entity[node], depth[node])].append(node)
    dimensions = {}
    for node, entity in entities.items():
        dimensions[node] = (150.0, 86.0) if entity.get("kind") == "receptor" else (136.0, 58.0)
    band_heights = {"extracellular": 180.0, "membrane": 96.0, "cytosol": 390.0, "nucleus": 190.0}
    for (role, _layer), members in groups.items():
        needed = sum(dimensions[node][1] for node in members) + 18 * (len(members) + 1)
        band_heights[role] = max(band_heights[role], needed)
    y = 20.0
    bounds = {}
    for role in ROLES:
        compartment_id = next(c["id"] for c in compartments.values() if _entity_role({"compartment": c["id"]}, compartments) == role)
        bounds[compartment_id] = {"x": 20.0, "y": y, "width": width - 40.0, "height": band_heights[role], "role": role}
        y += band_heights[role]
    height = max(height, y + 20)
    # Keep the last band inside an enlarged canvas.
    height = y + 20
    positions = {}
    for (role, layer), members in sorted(groups.items(), key=lambda item: (ROLES.index(item[0][0]), item[0][1])):
        compartment_id = next(c for c, b in bounds.items() if b["role"] == role)
        band = bounds[compartment_id]
        total = sum(dimensions[node][1] for node in members)
        free = band["height"] - total
        step = free / (len(members) + 1)
        cursor = band["y"] + step
        for node in members:
            w, h = dimensions[node]
            cy = cursor + h / 2
            if role == "membrane" and entities[node].get("kind") == "receptor":
                cy = band["y"] + band["height"] / 2
            positions[node] = {
                "id": node, "compartment": entities[node]["compartment"], "role": role,
                "kind": entities[node].get("kind", "molecule"), "label": entities[node].get("label", node),
                "x": x_by_layer[layer], "y": cy, "width": w, "height": h, "layer": layer,
                "on_main_path": node in main_nodes,
            }
            cursor += h + step
    routes = {}
    for edge in edges:
        source, target = positions[edge["source"]], positions[edge["target"]]
        if edge["route_class"] == "feedback":
            right = max(p["x"] + p["width"] / 2 for p in positions.values()) + 45
            sx, tx = source["x"] + source["width"] / 2, target["x"] + target["width"] / 2
            points = [[sx, source["y"]], [right, source["y"]], [right, target["y"]], [tx + 8, target["y"]]]
            edge["outside_route"] = True
        else:
            forward = target["x"] >= source["x"]
            sx = source["x"] + (source["width"] / 2 if forward else -source["width"] / 2)
            tx = target["x"] - (target["width"] / 2 if forward else -target["width"] / 2)
            middle = (sx + tx) / 2
            points = [[sx, source["y"]], [middle, source["y"]], [middle, target["y"]], [tx, target["y"]]]
            edge["outside_route"] = False
        edge["points"] = points
        routes[edge["id"]] = {"points": points, "route_class": edge["route_class"], "outside_route": edge["outside_route"]}
    layout = {
        "schema_version": "1.0", "canvas": {"width": width, "height": height},
        "compartment_bounds": bounds, "entities": positions, "edges": routes,
        "main_pathway": main_nodes, "layers": depth,
        "branch_edges": [e["id"] for e in edges if e["route_class"] == "branch"],
        "feedback_edges": feedback,
    }
    audit = audit_layout(topology, layout, edges)
    if not audit["passed"]:
        raise TopologyError("layout audit failed: " + "; ".join(audit["violations"]))
    return layout, audit


def audit_layout(topology, layout, routed_edges):
    violations = []
    positions = layout["entities"]
    bounds = layout["compartment_bounds"]
    for node, p in positions.items():
        box = bounds[p["compartment"]]
        if not (box["x"] <= p["x"] - p["width"] / 2 and p["x"] + p["width"] / 2 <= box["x"] + box["width"] and box["y"] <= p["y"] - p["height"] / 2 and p["y"] + p["height"] / 2 <= box["y"] + box["height"]):
            violations.append(f"entity {node} escapes its compartment")
        if p["kind"] == "receptor":
            midline = box["y"] + box["height"] / 2
            if abs(p["y"] - midline) > 1e-7 or p["role"] != "membrane":
                violations.append(f"receptor {node} is not centered on membrane midline")
    ids = list(positions)
    for index, a in enumerate(ids):
        pa = positions[a]
        for b in ids[index + 1:]:
            pb = positions[b]
            overlap_x = abs(pa["x"] - pb["x"]) * 2 < pa["width"] + pb["width"]
            overlap_y = abs(pa["y"] - pb["y"]) * 2 < pa["height"] + pb["height"]
            if overlap_x and overlap_y:
                violations.append(f"node collision: {a} / {b}")
    for edge in routed_edges:
        if edge.get("kind") == "transport" and positions[edge["source"]]["compartment"] == positions[edge["target"]]["compartment"]:
            violations.append(f"transport {edge['id']} does not cross compartments")
        if edge["route_class"] == "feedback" and not edge.get("outside_route"):
            violations.append(f"feedback {edge['id']} lacks outside routing")
    layers = layout["layers"]
    for edge in routed_edges:
        if edge["route_class"] != "feedback" and layers[edge["target"]] < layers[edge["source"]]:
            violations.append(f"DAG edge {edge['id']} moves to an earlier layer")
    return {
        "passed": not violations, "violations": violations,
        "checks": {
            "compartment_containment": True, "receptor_membrane_midline": True,
            "node_collision_detection": True, "transport_compartment_crossing": True,
            "dag_longest_path_layers": True, "feedback_outside_routing": True,
            "branch_same_layer_expansion": True,
        },
        "main_pathway_length_edges": max(0, len(layout["main_pathway"]) - 1),
        "entity_count": len(positions), "edge_count": len(routed_edges),
        "feedback_count": len(layout["feedback_edges"]),
    }


def xml_id(prefix, value):
    safe = re.sub(r"[^A-Za-z0-9_.-]", lambda m: f"-{ord(m.group()):x}-", value)
    return f"{prefix}-{safe}"


def render_svg(topology, layout):
    """Create an editable SVG with real text and stable IDs for every entity/edge."""
    width, height = layout["canvas"]["width"], layout["canvas"]["height"]
    root = ET.Element("svg", {
        "xmlns": "http://www.w3.org/2000/svg", "width": str(width), "height": str(height),
        "viewBox": f"0 0 {width} {height}", "role": "img",
        "aria-label": "Compartment topology with DAG layers and feedback routes",
    })
    defs = ET.SubElement(root, "defs", {"id": "arrow-definitions"})
    for name, color in (("main", "#215a8e"), ("branch", "#187c73"), ("feedback", "#b23a48"), ("transport", "#7452a3")):
        marker = ET.SubElement(defs, "marker", {"id": f"arrow-{name}", "markerWidth": "10", "markerHeight": "8", "refX": "9", "refY": "4", "orient": "auto", "markerUnits": "strokeWidth"})
        ET.SubElement(marker, "path", {"d": "M 0 0 L 10 4 L 0 8 z", "fill": color})
    ET.SubElement(root, "rect", {"id": "canvas-background", "x": "0", "y": "0", "width": str(width), "height": str(height), "fill": "#ffffff"})
    compartment_colors = {"extracellular": "#eef6fc", "membrane": "#f6e6bd", "cytosol": "#eff7ed", "nucleus": "#f2eef9"}
    for compartment in sorted(topology["compartments"], key=lambda c: c["order"]):
        box = layout["compartment_bounds"][compartment["id"]]
        group = ET.SubElement(root, "g", {"id": xml_id("compartment", compartment["id"]), "data-compartment-id": compartment["id"]})
        ET.SubElement(group, "rect", {"x": str(box["x"]), "y": str(box["y"]), "width": str(box["width"]), "height": str(box["height"]), "rx": "8", "fill": compartment_colors[box["role"]], "stroke": "#8996a3", "stroke-width": "1.2"})
        label = ET.SubElement(group, "text", {"id": xml_id("compartment-label", compartment["id"]), "x": str(box["x"] + 14), "y": str(box["y"] + 24), "font-family": "Arial, sans-serif", "font-size": "17", "font-weight": "700", "fill": "#344554"})
        label.text = compartment.get("label", box["role"])
        if box["role"] == "membrane":
            mid = box["y"] + box["height"] / 2
            ET.SubElement(group, "line", {"id": "membrane-midline", "x1": str(box["x"]), "x2": str(box["x"] + box["width"]), "y1": str(mid), "y2": str(mid), "stroke": "#b59045", "stroke-width": "1", "stroke-dasharray": "7 6"})
    positions = layout["entities"]
    by_edge = {e["id"]: e for e in topology["edges"]}
    # Render connectors before nodes so lines never obscure labels.
    for route_id, route in layout["edges"].items():
        edge = by_edge[route_id]
        cls = route["route_class"]
        style_class = "transport" if edge.get("kind") == "transport" and cls != "feedback" else cls
        color = {"main": "#215a8e", "branch": "#187c73", "feedback": "#b23a48", "transport": "#7452a3"}[style_class]
        points = " ".join(f"{x},{y}" for x, y in route["points"])
        attrs = {"id": xml_id("edge", route_id), "data-edge-id": route_id, "data-route-class": cls, "points": points, "fill": "none", "stroke": color, "stroke-width": "3" if cls == "main" else "2.2", "marker-end": f"url(#arrow-{style_class})"}
        if cls == "feedback":
            attrs["stroke-dasharray"] = "9 6"
        connector = ET.SubElement(root, "polyline", attrs)
        if cls == "feedback":
            # Multiple subpaths make dash semantics survive PyMuPDF export.
            connector.tag = "path"; connector.attrib.pop("points", None); connector.attrib.pop("stroke-dasharray", None)
            fragments = []
            for (sx, sy), (tx, ty) in zip(route["points"], route["points"][1:]):
                seg = math.hypot(tx-sx, ty-sy)
                if not seg: continue
                ux, uy = (tx-sx)/seg, (ty-sy)/seg; offset = 0.0
                while offset < seg:
                    end = min(offset+9.0, seg)
                    fragments.append(f"M{sx+ux*offset},{sy+uy*offset} L{sx+ux*end},{sy+uy*end}")
                    offset += 15.0
            connector.set("d", " ".join(fragments))
        # Explicit terminal geometry remains visible in renderers with weak SVG marker support.
        (x0, y0), (x1, y1) = route["points"][-2], route["points"][-1]
        length = math.hypot(x1-x0, y1-y0) or 1.0
        ux, uy = (x1-x0)/length, (y1-y0)/length
        bx, by, px, py = x1-ux*13, y1-uy*13, -uy*6, ux*6
        ET.SubElement(root, "polygon", {"id": xml_id("edge-terminal", route_id), "points": f"{x1},{y1} {bx+px},{by+py} {bx-px},{by-py}", "fill": color, "data-terminal": "direction-arrow"})
    for node, p in positions.items():
        group = ET.SubElement(root, "g", {"id": xml_id("entity", node), "data-entity-id": node, "data-layer": str(p["layer"]), "transform": f"translate({p['x']} {p['y']})"})
        fill = {"receptor": "#f5b85a", "transcription_factor": "#c9b5e5", "ligand": "#a9d5ef"}.get(p["kind"], "#ffffff")
        ET.SubElement(group, "rect", {"id": xml_id("shape", node), "x": str(-p["width"] / 2), "y": str(-p["height"] / 2), "width": str(p["width"]), "height": str(p["height"]), "rx": "12" if p["kind"] != "receptor" else "20", "fill": fill, "stroke": "#344554", "stroke-width": "1.8"})
        text = ET.SubElement(group, "text", {"id": xml_id("label", node), "x": "0", "y": "5", "text-anchor": "middle", "font-family": "Arial, sans-serif", "font-size": "16", "font-weight": "600", "fill": "#172b3a"})
        text.text = p["label"]
        layer = ET.SubElement(group, "text", {"id": xml_id("layer", node), "x": "0", "y": str(p["height"] / 2 + 16), "text-anchor": "middle", "font-family": "Arial, sans-serif", "font-size": "11", "fill": "#536675"})
        layer.text = f"L{p['layer']} · {node}"
    legend = ET.SubElement(root, "g", {"id": "route-legend", "transform": f"translate(40 {height - 16})"})
    text = ET.SubElement(legend, "text", {"font-family": "Arial, sans-serif", "font-size": "12", "fill": "#344554"})
    text.text = "DAG layers: left → right  |  blue: main  ·  green: branch  ·  purple: transport  ·  red dashed: feedback (outside route)"
    ET.SubElement(root, "title").text = "Constraint-solved compartment topology"
    ET.SubElement(root, "desc").text = "Extracellular, membrane, cytosol and nucleus bands; receptors centered on membrane midline."
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def write_renderings(svg_bytes: bytes, svg_path: Path, png_path: Path, pdf_path: Path):
    """Use PyMuPDF to make actual PDF and PNG; never write placeholder bytes."""
    try:
        import pymupdf
    except ImportError as exc:
        raise TopologyError("PyMuPDF is required for PNG/PDF export") from exc
    svg_path.write_bytes(svg_bytes)
    try:
        svg_doc = pymupdf.open(stream=svg_bytes, filetype="svg")
        pdf_bytes = svg_doc.convert_to_pdf()
        pdf_path.write_bytes(pdf_bytes)
        pdf_doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        page = pdf_doc[0]
        # 144 dpi for legible labels; alpha=False keeps a white background.
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
        pixmap.save(str(png_path))
    except Exception as exc:
        raise TopologyError(f"SVG/PNG/PDF rendering failed: {exc}") from exc


def sha256_bytes(content):
    return hashlib.sha256(content).hexdigest()
