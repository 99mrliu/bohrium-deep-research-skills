#!/usr/bin/env python3
"""Statistically coupled SVG charts with stable marks and explicit visual scales."""
from __future__ import annotations

import math
import re
from xml.etree import ElementTree as ET

from data_core import DataError, sha256_bytes

DEFAULT_COLORS = ["#3b78a8", "#d17a32", "#428b69", "#8b62a9", "#b34c5e", "#6f7d86"]


def safe_id(prefix, value):
    text = re.sub(r"[^A-Za-z0-9_.-]", lambda m: f"-{ord(m.group()):x}-", str(value))
    return f"{prefix}-{text}"


def validate_color(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise DataError(f"{label} must be #RRGGBB, got {value!r}")
    return value.lower()


def _number(value):
    if value is None or isinstance(value, bool) or (isinstance(value, str) and not value.strip()):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DataError(f"channel value is not numeric: {value!r}") from exc
    if not math.isfinite(number):
        raise DataError("channel numeric value must be finite")
    return number


def interpolate_color(a, b, t):
    av = tuple(int(a[i:i + 2], 16) for i in (1, 3, 5))
    bv = tuple(int(b[i:i + 2], 16) for i in (1, 3, 5))
    values = tuple(round(x + (y - x) * t) for x, y in zip(av, bv))
    return "#" + "".join(f"{value:02x}" for value in values)


def _domain(values, scale, explicit):
    if scale == "categorical":
        observed = sorted({str(value) for value in values if value is not None and value != ""})
        domain = explicit if explicit is not None else observed
        if not isinstance(domain, list) or any(not isinstance(value, str) for value in domain):
            raise DataError("categorical channel domain must be an array of strings")
        return observed, domain
    observed_numbers = [number for value in values if (number := _number(value)) is not None]
    observed = [min(observed_numbers), max(observed_numbers)] if observed_numbers else []
    domain = explicit if explicit is not None else observed
    if len(domain) != 2:
        if not observed and explicit is None:
            return observed, []
        raise DataError("linear channel domain must contain [min,max]")
    domain = [_number(value) for value in domain]
    if None in domain or domain[0] > domain[1]:
        raise DataError("linear channel domain needs two finite ordered values")
    return observed, domain


def build_scales(marks, channels):
    audits = {}
    for channel in ("fill", "size", "edge_width"):
        config = channels.get(channel)
        if config is None:
            continue
        if not isinstance(config, dict) or set(config) - {"column", "scale", "range", "domain", "missing", "out_of_range"}:
            raise DataError(f"channels.{channel} has unsupported options")
        column = config.get("column")
        if not isinstance(column, str) or not column:
            raise DataError(f"channels.{channel}.column is required")
        applicable = [mark for mark in marks if channel in mark["channels"]]
        values = [mark["data"].get(column) for mark in applicable]
        inferred = "categorical" if channel == "fill" and any(isinstance(value, str) and not _is_number(value) for value in values if value not in (None, "")) else "linear"
        scale = config.get("scale", inferred)
        if scale not in {"categorical", "linear"} or (channel != "fill" and scale != "linear"):
            raise DataError(f"invalid scale for {channel}: {scale}")
        observed, domain = _domain(values, scale, config.get("domain"))
        default_ranges = {"fill": DEFAULT_COLORS[:2] if scale == "linear" else DEFAULT_COLORS, "size": [4, 11], "edge_width": [1.2, 5.0]}
        value_range = config.get("range", default_ranges[channel])
        if not isinstance(value_range, list) or not value_range:
            raise DataError(f"channels.{channel}.range must be a non-empty array")
        if channel == "fill":
            value_range = [validate_color(value, f"{channel} range") for value in value_range]
            if scale == "linear" and len(value_range) != 2:
                raise DataError("continuous fill range must have exactly two colors")
            if scale == "categorical" and len(value_range) < len(domain):
                raise DataError("categorical fill range must cover every actual domain category")
        else:
            if len(value_range) != 2 or any(_number(value) is None or _number(value) < 0 for value in value_range):
                raise DataError(f"{channel} range must be two non-negative finite numbers")
            value_range = [_number(value) for value in value_range]
        missing_policy = config.get("missing", "skip")
        out_policy = config.get("out_of_range", "clamp" if scale == "linear" else "skip")
        if channel == "fill":
            if missing_policy != "skip":
                missing_policy = validate_color(missing_policy, f"{channel}.missing")
            if out_policy not in {"skip", "clamp"}:
                out_policy = validate_color(out_policy, f"{channel}.out_of_range")
        else:
            if missing_policy != "skip":
                missing_policy = _number(missing_policy)
                if missing_policy is None or missing_policy < 0:
                    raise DataError(f"{channel}.missing must be skip or non-negative number")
            if out_policy not in {"skip", "clamp"}:
                raise DataError(f"{channel}.out_of_range must be skip or clamp")
        stats = {"missing": 0, "out_of_range": 0, "skipped": 0}
        for mark in applicable:
            raw = mark["data"].get(column)
            state, result = "mapped", None
            if raw is None or raw == "":
                stats["missing"] += 1
                if missing_policy == "skip":
                    state, result = "missing_skip", None
                    stats["skipped"] += 1
                else:
                    state, result = "missing_fallback", missing_policy
            elif scale == "categorical":
                category = str(raw)
                if category not in domain:
                    stats["out_of_range"] += 1
                    if out_policy == "skip":
                        state, result = "out_skip", None
                        stats["skipped"] += 1
                    else:
                        state, result = "out_fallback", out_policy
                else:
                    result = value_range[domain.index(category)]
            else:
                number = _number(raw)
                if not domain:
                    raise DataError(f"{channel} has no usable domain")
                if number < domain[0] or number > domain[1]:
                    stats["out_of_range"] += 1
                    if out_policy == "skip":
                        state, result = "out_skip", None
                        stats["skipped"] += 1
                    else:
                        number = min(domain[1], max(domain[0], number))
                        state = "out_clamped"
                if result is None and state != "out_skip":
                    t = 0.5 if domain[0] == domain[1] else (number - domain[0]) / (domain[1] - domain[0])
                    if channel == "fill":
                        result = interpolate_color(value_range[0], value_range[1], t)
                    else:
                        result = value_range[0] + (value_range[1] - value_range[0]) * t
            mark["encoding"][channel] = {"source": raw, "state": state, "value": result}
            if result is None:
                mark["visible"] = False
        audits[channel] = {
            "column": column, "scale": scale, "observed_domain": observed, "domain": domain,
            "domain_source": "configured" if config.get("domain") is not None else "observed data",
            "range": value_range, "missing_policy": config.get("missing", "skip"),
            "out_of_range_policy": config.get("out_of_range", "clamp" if scale == "linear" else "skip"),
            "degenerate_domain": bool(domain and scale == "linear" and domain[0] == domain[1]),
            **stats,
        }
    return audits


def _is_number(value):
    try:
        return _number(value) is not None
    except DataError:
        return False


def select_feature(chart, observations, samples, groups, features):
    selected = chart.get("feature")
    available = [item["feature"] for item in features]
    if selected is None:
        if len(available) != 1:
            raise DataError("multiple features require chart.feature to select one facet; small multiples are not inferred")
        return available[0]
    if selected not in available:
        raise DataError(f"chart.feature {selected!r} does not exist in raw data")
    return selected


def prepare_marks(chart, observations, samples, groups, features):
    kind = chart.get("type")
    if kind not in {"bar", "scatter"}:
        raise DataError("chart.type must be bar or scatter")
    feature = select_feature(chart, observations, samples, groups, features)
    selected_samples = [dict(s) for s in samples if s["feature"] == feature]
    selected_groups = [dict(g) for g in groups if g["feature"] == feature]
    marks = []
    if kind == "bar":
        if chart.get("x", "group") != "group" or chart.get("y", "group_mean") != "group_mean":
            raise DataError("bar chart x must be group and y must be group_mean")
        for group in selected_groups:
            marks.append({"id": safe_id("bar", f"{feature}-{group['group']}"), "type": "bar", "data": group, "channels": {"fill"}, "encoding": {}, "visible": True})
        for sample in selected_samples:
            marks.append({"id": safe_id("sample", f"{feature}-{sample['group']}-{sample['sample']}"), "type": "circle", "data": sample, "channels": {"fill", "size"}, "encoding": {}, "visible": True})
    else:
        for axis in ("x", "y"):
            if chart.get(axis) not in {"sample_mean", "group_mean", "log2FC", "neg_log10_p"}:
                raise DataError(f"scatter {axis} must identify a derived numeric column")
            for sample in selected_samples:
                _number(sample.get(chart[axis]))
        for sample in selected_samples:
            marks.append({"id": safe_id("point", f"{feature}-{sample['group']}-{sample['sample']}"), "type": "circle", "data": sample, "channels": {"fill", "size"}, "encoding": {}, "visible": True})
    edges = chart.get("edges", [])
    if not isinstance(edges, list):
        raise DataError("chart.edges must be an array")
    if edges and "edge_width" not in chart.get("channels", {}):
        raise DataError("chart.edges requires an explicit channels.edge_width scale")
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict) or set(edge) - {"id", "source", "target", "directed"}:
            raise DataError("edge supports id/source/target/directed only")
        source, target = edge.get("source"), edge.get("target")
        if kind == "bar":
            source_mark = next((mark for mark in marks if mark["type"] == "bar" and mark["data"]["group"] == source), None)
            target_mark = next((mark for mark in marks if mark["type"] == "bar" and mark["data"]["group"] == target), None)
        else:
            source_mark = next((mark for mark in marks if mark["data"].get("sample") == source), None)
            target_mark = next((mark for mark in marks if mark["data"].get("sample") == target), None)
        if source_mark is None or target_mark is None or source == target:
            raise DataError(f"edge {index} has unknown/equal source or target")
        data = dict(source_mark["data"])
        data.update({"source": source, "target": target, "feature": feature})
        edge_id = edge.get("id", f"edge-{index}")
        marks.append({"id": safe_id("edge", f"{feature}-{edge_id}"), "type": "edge", "source_mark": source_mark, "target_mark": target_mark, "directed": bool(edge.get("directed", False)), "data": data, "channels": {"edge_width"}, "encoding": {}, "visible": True})
    if len({mark["id"] for mark in marks}) != len(marks):
        raise DataError("stable mark IDs are not unique; disambiguate raw samples or edge IDs")
    if not chart.get("channels", {}).get("fill"):
        chart.setdefault("channels", {})["fill"] = {"column": "group", "scale": "categorical"}
    return marks, feature


def continuous_axis(values, include_zero=False):
    numbers = [_number(value) for value in values]
    if not numbers:
        raise DataError("cannot construct numeric axis without finite values")
    low, high = min(numbers), max(numbers)
    if include_zero:
        low, high = min(0, low), max(0, high)
    if low == high:
        padding = max(1, abs(low) * 0.1)
        return low - padding, high + padding
    padding = (high - low) * 0.08
    return low - (0 if include_zero and low == 0 else padding), high + padding


def text(parent, element_id, x, y, value, size=14, anchor="start", weight="400", fill="#263746"):
    node = ET.SubElement(parent, "text", {"id": element_id, "x": str(x), "y": str(y), "font-family": "Arial, sans-serif", "font-size": str(size), "font-weight": weight, "text-anchor": anchor, "fill": fill})
    node.text = str(value)
    return node


def fmt(value):
    return "missing" if value is None else f"{float(value):.6g}"


def render_chart(chart, observations, samples, groups, features):
    if not isinstance(chart, dict) or set(chart) - {"type", "feature", "title", "width", "height", "x", "y", "error", "channels", "edges"}:
        raise DataError("unsupported chart configuration field")
    chart = {**chart, "channels": dict(chart.get("channels", {}))}
    marks, feature = prepare_marks(chart, observations, samples, groups, features)
    scales = build_scales(marks, chart["channels"])
    width, height = int(chart.get("width", 1100)), int(chart.get("height", 680))
    if width < 800 or height < 500:
        raise DataError("chart canvas must be at least 800x500 for axes and honest legends")
    left, top, bottom, right = 95, 75, 92, width - 280
    plot_w, plot_h = right - left, height - top - bottom
    root = ET.Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "width": str(width), "height": str(height), "viewBox": f"0 0 {width} {height}", "role": "img"})
    ET.SubElement(root, "title").text = chart.get("title", f"{feature}: raw-data-derived {chart['type']} chart")
    ET.SubElement(root, "desc").text = "Statistics and all visual channels are computed from the raw dataset. See data_audit.json for scales."
    defs = ET.SubElement(root, "defs")
    marker = ET.SubElement(defs, "marker", {"id": "edge-arrow", "markerWidth": "9", "markerHeight": "7", "refX": "8", "refY": "3.5", "orient": "auto"})
    ET.SubElement(marker, "path", {"d": "M 0 0 L 9 3.5 L 0 7 z", "fill": "#667985"})
    ET.SubElement(root, "rect", {"id": "background", "width": str(width), "height": str(height), "fill": "#ffffff"})
    text(root, "chart-title", left, 36, chart.get("title", f"{feature}: {chart['type']}"), 21, weight="700")
    axes = ET.SubElement(root, "g", {"id": "axes"})
    kind = chart["type"]
    coords = {}
    ticks = []
    if kind == "bar":
        bars = [mark for mark in marks if mark["type"] == "bar"]
        ordered_groups = [mark["data"]["group"] for mark in bars]
        group_positions = {group: left + (index + 0.5) * plot_w / max(1, len(bars)) for index, group in enumerate(ordered_groups)}
        error_field = chart.get("error", "group_sem")
        if error_field not in {"group_sem", "group_sd", "none"}:
            raise DataError("bar error must be group_sem, group_sd or none")
        y_values = []
        for mark in bars:
            data = mark["data"]
            y_values.append(data["group_mean"])
            if error_field != "none" and data.get(error_field) is not None:
                y_values.extend([data["group_mean"] - data[error_field], data["group_mean"] + data[error_field]])
        low, high = continuous_axis(y_values, include_zero=True)
        def yscale(value):
            return top + (high - value) / (high - low) * plot_h
        for mark in marks:
            data = mark["data"]
            if mark["type"] == "bar":
                coords[mark["id"]] = (group_positions[data["group"]], yscale(data["group_mean"]))
            elif mark["type"] == "circle":
                group_samples = [m for m in marks if m["type"] == "circle" and m["data"]["group"] == data["group"]]
                index = group_samples.index(mark)
                offset = (index - (len(group_samples) - 1) / 2) * 13
                coords[mark["id"]] = (group_positions[data["group"]] + offset, yscale(data["sample_mean"]))
            else:
                coords[mark["id"]] = (0, 0)
        x_label, y_label = "group", "mean of independent sample means"
        ticks = ordered_groups
    else:
        x_values = [mark["data"][chart["x"]] for mark in marks if mark["type"] == "circle"]
        y_values = [mark["data"][chart["y"]] for mark in marks if mark["type"] == "circle"]
        x_low, x_high = continuous_axis(x_values)
        y_low, y_high = continuous_axis(y_values)
        def xscale(value):
            return left + (value - x_low) / (x_high - x_low) * plot_w
        def yscale(value):
            return top + (y_high - value) / (y_high - y_low) * plot_h
        for mark in marks:
            coords[mark["id"]] = (xscale(mark["data"][chart["x"]]), yscale(mark["data"][chart["y"]])) if mark["type"] == "circle" else (0, 0)
        low, high = y_low, y_high
        x_label, y_label = chart["x"], chart["y"]
        ticks = [x_low + i * (x_high - x_low) / 5 for i in range(6)]
    # Actual numeric y ticks and grid lines.
    for index in range(6):
        value = low + index * (high - low) / 5
        y = yscale(value)
        ET.SubElement(axes, "line", {"x1": str(left), "x2": str(right), "y1": str(y), "y2": str(y), "stroke": "#e1e7eb"})
        text(axes, f"y-tick-{index}", left - 10, y + 4, fmt(value), 12, "end")
    ET.SubElement(axes, "line", {"x1": str(left), "x2": str(left), "y1": str(top), "y2": str(top + plot_h), "stroke": "#546470"})
    ET.SubElement(axes, "line", {"x1": str(left), "x2": str(right), "y1": str(top + plot_h), "y2": str(top + plot_h), "stroke": "#546470"})
    for index, value in enumerate(ticks):
        x = group_positions[value] if kind == "bar" else xscale(value)
        text(axes, f"x-tick-{index}", x, top + plot_h + 24, value if kind == "bar" else fmt(value), 12, "middle")
    text(axes, "x-axis-title", (left + right) / 2, height - 30, x_label, 14, "middle", "600")
    y_title = text(axes, "y-axis-title", 22, (top + top + plot_h) / 2, y_label, 14, "middle", "600")
    y_title.set("transform", f"rotate(-90 22 {(top + top + plot_h) / 2})")
    # Edge marks are below node marks and use their configured width mapping.
    for mark in marks:
        if mark["type"] != "edge" or not mark["visible"]:
            continue
        source = coords[mark["source_mark"]["id"]]
        target = coords[mark["target_mark"]["id"]]
        if kind == "bar":
            source = (source[0] + (40 if target[0] >= source[0] else -40), source[1])
            target = (target[0] - (40 if target[0] >= source[0] else -40), target[1])
        attrs = {"id": mark["id"], "data-mark-type": "edge", "x1": str(source[0]), "y1": str(source[1]), "x2": str(target[0]), "y2": str(target[1]), "stroke": "#667985", "stroke-width": str(mark["encoding"]["edge_width"]["value"]), "fill": "none"}
        if mark["directed"]:
            attrs["marker-end"] = "url(#edge-arrow)"
        ET.SubElement(root, "line", attrs)
    for mark in marks:
        if mark["type"] == "edge" or not mark["visible"]:
            continue
        x, y = coords[mark["id"]]
        fill = mark["encoding"]["fill"]["value"]
        if mark["type"] == "bar":
            zero_y = yscale(max(low, min(high, 0)))
            rect_y, rect_h = min(y, zero_y), abs(zero_y - y)
            ET.SubElement(root, "rect", {"id": mark["id"], "data-mark-type": "bar", "data-feature": feature, "data-group": str(mark["data"]["group"]), "x": str(x - 40), "y": str(rect_y), "width": "80", "height": str(rect_h), "fill": fill, "stroke": "#334853", "stroke-width": "1.2"})
            error_field = chart.get("error", "group_sem")
            has_error = error_field != "none" and mark["data"].get(error_field) is not None
            label_y = rect_y - 8
            if has_error:
                label_y = min(rect_y, yscale(mark["data"]["group_mean"] + mark["data"][error_field])) - 12
            text(root, f"{mark['id']}-value", x, label_y, fmt(mark["data"]["group_mean"]), 12, "middle", "600")
            if has_error:
                error = mark["data"][error_field]
                y1, y2 = yscale(mark["data"]["group_mean"] - error), yscale(mark["data"]["group_mean"] + error)
                ET.SubElement(root, "line", {"id": f"{mark['id']}-error", "x1": str(x), "x2": str(x), "y1": str(y1), "y2": str(y2), "stroke": "#243642", "stroke-width": "1.5"})
                for suffix, cap_y in (("lower", y1), ("upper", y2)):
                    ET.SubElement(root, "line", {"id": f"{mark['id']}-error-{suffix}", "x1": str(x - 8), "x2": str(x + 8), "y1": str(cap_y), "y2": str(cap_y), "stroke": "#243642"})
        else:
            radius = mark["encoding"].get("size", {}).get("value", 5)
            ET.SubElement(root, "circle", {"id": mark["id"], "data-mark-type": "sample", "data-feature": feature, "data-sample": str(mark["data"]["sample"]), "cx": str(x), "cy": str(y), "r": str(radius), "fill": fill, "stroke": "#ffffff", "stroke-width": "1.4", "opacity": "0.9"})
    render_legends(root, scales, width - 245, top)
    svg = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    registry = [{"id": mark["id"], "type": mark["type"], "visible": mark["visible"], "feature": mark["data"].get("feature"), "sample": mark["data"].get("sample"), "group": mark["data"].get("group"), "encoding": mark["encoding"]} for mark in marks]
    if not any(mark["visible"] and mark["type"] in {"bar", "circle"} for mark in marks):
        raise DataError("all data marks were skipped by channel missing/out-of-range policies")
    return svg, {"scales": scales, "mark_registry": registry, "selected_feature": feature, "chart_type": kind}


def render_legends(root, scales, x, y):
    legend = ET.SubElement(root, "g", {"id": "legends", "data-generated-from": "actual scale mappings"})
    cursor = y
    for channel, scale in scales.items():
        text(legend, f"legend-{channel}-title", x, cursor, f"{channel}: {scale['column']}", 14, weight="700")
        cursor += 24
        domain = scale["domain"]
        if channel == "fill" and scale["scale"] == "categorical":
            for index, category in enumerate(domain):
                ET.SubElement(legend, "rect", {"id": f"legend-fill-swatch-{index}", "x": str(x), "y": str(cursor - 12), "width": "16", "height": "16", "fill": scale["range"][index]})
                text(legend, f"legend-fill-label-{index}", x + 24, cursor, category, 12)
                cursor += 23
        elif channel == "fill":
            gradient = ET.SubElement(root.find("defs"), "linearGradient", {"id": "fill-scale-gradient", "x1": "0%", "x2": "100%"})
            ET.SubElement(gradient, "stop", {"offset": "0%", "stop-color": scale["range"][0]})
            ET.SubElement(gradient, "stop", {"offset": "100%", "stop-color": scale["range"][1]})
            ET.SubElement(legend, "rect", {"id": "legend-fill-gradient", "x": str(x), "y": str(cursor - 12), "width": "140", "height": "16", "fill": "url(#fill-scale-gradient)"})
            if domain:
                text(legend, "legend-fill-min", x, cursor + 17, fmt(domain[0]), 11)
                text(legend, "legend-fill-max", x + 140, cursor + 17, fmt(domain[1]), 11, "end")
            cursor += 44
        else:
            if not domain:
                text(legend, f"legend-{channel}-empty", x, cursor, "all values missing", 11)
                cursor += 24
                continue
            indices = [0] if domain[0] == domain[-1] else [0, len(domain) - 1]
            for index in indices:
                value = domain[index]
                t = 0.5 if domain[0] == domain[1] else (value - domain[0]) / (domain[1] - domain[0])
                mapped = scale["range"][0] + (scale["range"][1] - scale["range"][0]) * t
                if channel == "size":
                    ET.SubElement(legend, "circle", {"id": f"legend-size-{index}", "cx": str(x + 14), "cy": str(cursor), "r": str(mapped), "fill": "#8a9aa5", "stroke": "#43545f"})
                else:
                    ET.SubElement(legend, "line", {"id": f"legend-edge-{index}", "x1": str(x), "x2": str(x + 34), "y1": str(cursor), "y2": str(cursor), "stroke": "#667985", "stroke-width": str(mapped)})
                text(legend, f"legend-{channel}-label-{index}", x + 46, cursor + 4, fmt(value), 11)
                cursor += 26
        text(legend, f"legend-{channel}-domain", x, cursor, f"domain: {scale['domain_source']}", 10, fill="#657680")
        cursor += 20


def write_renderings(svg_bytes, svg_path, png_path, pdf_path):
    try:
        import pymupdf
        svg_path.write_bytes(svg_bytes)
        document = pymupdf.open(stream=svg_bytes, filetype="svg")
        pdf_bytes = document.convert_to_pdf()
        pdf_path.write_bytes(pdf_bytes)
        pdf = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        pdf[0].get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False).save(str(png_path))
    except Exception as exc:
        raise DataError(f"actual SVG/PNG/PDF export failed: {exc}") from exc
