#!/usr/bin/env python3
"""SYNTHETIC demo fixture renderer and tiny SVG-subset PNG previewer.

This is deliberately not a general scientific renderer and is not a QC authority.
The previewer parses the generated SVG so before/after pixel diffs use real artifact
content. It supports only the primitive shapes and bitmap text used by the example.
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from png_diff import write_png

FONT = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10111", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "J": ["00111", "00010", "00010", "00010", "10010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
    "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    "+": ["00000", "00100", "00100", "11111", "00100", "00100", "00000"],
    ">": ["10000", "01000", "00100", "00010", "00100", "01000", "10000"],
    "/": ["00001", "00010", "00010", "00100", "01000", "01000", "10000"],
    ".": ["00000", "00000", "00000", "00000", "00000", "00110", "00110"],
    ",": ["00000", "00000", "00000", "00000", "00110", "00110", "00100"],
    ":": ["00000", "00110", "00110", "00000", "00110", "00110", "00000"],
    "(": ["00010", "00100", "01000", "01000", "01000", "00100", "00010"],
    ")": ["01000", "00100", "00010", "00010", "00010", "00100", "01000"],
    "|": ["00100", "00100", "00100", "00100", "00100", "00100", "00100"],
    "_": ["00000", "00000", "00000", "00000", "00000", "00000", "11111"],
    " ": ["00000"] * 7,
}


def fixture_svg(corrected: bool) -> str:
    """Return the deliberately defective source or its authorized correction."""
    reactor = "REACTOR" if corrected else "VESSEL"
    flow_d = "M230 205 L285 205" if corrected else "M290 205 L235 205"
    flow_from, flow_to = ("feed", "pump") if corrected else ("pump", "feed")
    run_b = 4.0 if corrected else 3.0
    run_b_height = 180 if corrected else 135
    run_b_y = 220 if corrected else 265
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     id="synthetic-dual-gate" width="1000" height="620" viewBox="0 0 1000 620">
  <title id="title">SYNTHETIC FLOW AND CHART - DUAL ARTIFACT QC FIXTURE</title>
  <desc>INVENTED SYNTHETIC DATA. NOT AN OFFICIAL CASE OR SCIENTIFIC ANSWER.</desc>
  <defs>
    <marker id="arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto" markerUnits="strokeWidth">
      <path d="M0 0 L10 4 L0 8 Z" fill="#33445a"/>
    </marker>
  </defs>
  <g id="layer-background" data-qc-layer="background" inkscape:groupmode="layer" inkscape:label="background">
    <rect id="canvas" x="0" y="0" width="1000" height="620" fill="#ffffff"/>
    <rect id="flow-panel" x="35" y="85" width="720" height="250" fill="#f7f9fc" stroke="#c8d1dc"/>
    <rect id="chart-panel" x="775" y="85" width="195" height="440" fill="#f7f9fc" stroke="#c8d1dc"/>
  </g>
  <g id="layer-annotations" data-qc-layer="annotations" inkscape:groupmode="layer" inkscape:label="annotations">
    <text id="banner" x="45" y="42" font-size="22" fill="#8a285c">SYNTHETIC QC FIXTURE - INVENTED DATA</text>
    <text id="flow-heading" x="55" y="120" font-size="18" fill="#1d2d3d">TWO-STEP MATERIAL FLOW</text>
    <text id="sequence" x="55" y="315" font-size="16" fill="#1d2d3d">1 FEED &gt; PUMP    2 PUMP &gt; REACTOR</text>
    <text id="unrelated-note" x="45" y="585" font-size="16" fill="#536273">PRESERVE THIS UNADDRESSED NOTE</text>
    <text id="chart-heading" x="790" y="120" font-size="17" fill="#1d2d3d">SYNTHETIC CHART</text>
    <text id="chart-unit" x="790" y="145" font-size="14" fill="#536273">VALUE / SYN-U</text>
  </g>
  <g id="layer-entities" data-qc-layer="entities" inkscape:groupmode="layer" inkscape:label="entities">
    <g id="entity-feed" data-qc-kind="entity" data-qc-id="feed">
      <rect x="70" y="165" width="160" height="80" rx="8" fill="#e4eef9" stroke="#527a9e" stroke-width="2"/>
      <text id="feed-label" x="150" y="211" text-anchor="middle" font-size="23" fill="#1d2d3d">FEED</text>
    </g>
    <g id="entity-pump" data-qc-kind="entity" data-qc-id="pump">
      <rect x="290" y="165" width="160" height="80" rx="8" fill="#f3e9c8" stroke="#9a772b" stroke-width="2"/>
      <text id="pump-label" x="370" y="211" text-anchor="middle" font-size="23" fill="#1d2d3d">PUMP</text>
    </g>
    <g id="entity-reactor" data-qc-kind="entity" data-qc-id="reactor">
      <rect x="540" y="165" width="170" height="80" rx="8" fill="#d9ebea" stroke="#3d7b74" stroke-width="2"/>
      <text id="reactor-label" x="625" y="211" text-anchor="middle" font-size="23" fill="#1d2d3d">{reactor}</text>
    </g>
  </g>
  <g id="layer-flows" data-qc-layer="flows" inkscape:groupmode="layer" inkscape:label="flows">
    <path id="flow-1" data-qc-kind="edge" data-qc-id="feed_to_pump" data-from="{flow_from}" data-to="{flow_to}" data-order="1"
          d="{flow_d}" fill="none" stroke="#33445a" stroke-width="4" marker-end="url(#arrow)"/>
    <path id="flow-2" data-qc-kind="edge" data-qc-id="pump_to_reactor" data-from="pump" data-to="reactor" data-order="2"
          d="M450 205 L535 205" fill="none" stroke="#33445a" stroke-width="4" marker-end="url(#arrow)"/>
  </g>
  <g id="layer-chart" data-qc-layer="chart" inkscape:groupmode="layer" inkscape:label="chart">
    <line id="chart-baseline" x1="800" y1="400" x2="950" y2="400" stroke="#536273" stroke-width="2"/>
    <line id="chart-y-axis" x1="800" y1="180" x2="800" y2="400" stroke="#536273" stroke-width="2"/>
    <rect id="bar-run-a" data-qc-kind="chart-value" data-qc-id="Measurement|Run A"
          data-series="Measurement" data-key="Run A" data-value="2.5" data-unit="SYN-U"
          x="815" y="287.5" width="45" height="112.5" fill="#527a9e"/>
    <rect id="bar-run-b" data-qc-kind="chart-value" data-qc-id="Measurement|Run B"
          data-series="Measurement" data-key="Run B" data-value="{run_b}" data-unit="SYN-U"
          x="885" y="{run_b_y}" width="45" height="{run_b_height}" fill="#3d7b74"/>
    <text id="bar-a-label" x="837" y="430" text-anchor="middle" font-size="15" fill="#1d2d3d">RUN A</text>
    <text id="bar-b-label" x="907" y="430" text-anchor="middle" font-size="15" fill="#1d2d3d">RUN B</text>
    <text id="bar-a-value" x="837" y="275" text-anchor="middle" font-size="15" fill="#1d2d3d">2.5</text>
    <text id="bar-b-value" x="907" y="{run_b_y - 12}" text-anchor="middle" font-size="15" fill="#1d2d3d">{run_b}</text>
  </g>
  <g id="layer-legend" data-qc-layer="legend" inkscape:groupmode="layer" inkscape:label="legend">
    <g id="legend-flow" data-qc-kind="legend-item" data-qc-id="flow" data-target="feed_to_pump">
      <line x1="55" y1="380" x2="120" y2="380" stroke="#33445a" stroke-width="4" marker-end="url(#arrow)"/>
      <text id="legend-label" x="140" y="386" font-size="16" fill="#1d2d3d">MATERIAL FLOW (SYNTHETIC)</text>
    </g>
    <g id="legend-chart" data-qc-kind="legend-item" data-qc-id="measurement" data-target="bar-run-a">
      <rect x="55" y="425" width="30" height="22" fill="#527a9e"/>
      <text id="legend-chart-label" x="100" y="442" font-size="16" fill="#1d2d3d">MEASUREMENT / SYN-U</text>
    </g>
  </g>
</svg>
'''


def parse_color(value: str | None, default: tuple[int, int, int, int] = (0, 0, 0, 255)) -> tuple[int, int, int, int] | None:
    if not value:
        return default
    value = value.strip()
    if value == "none":
        return None
    if value == "white":
        return (255, 255, 255, 255)
    if value == "black":
        return (0, 0, 0, 255)
    if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16), 255)
    return default


class Preview:
    def __init__(self, width: int, height: int) -> None:
        self.width, self.height = width, height
        self.pixels = bytearray((255, 255, 255, 255)) * (width * height)

    def pixel(self, x: int, y: int, color: tuple[int, int, int, int] | None) -> None:
        if color is None or not (0 <= x < self.width and 0 <= y < self.height):
            return
        pos = (y * self.width + x) * 4
        if color[3] == 255:
            self.pixels[pos:pos + 4] = bytes(color)
        else:
            alpha = color[3] / 255
            for channel in range(3):
                self.pixels[pos + channel] = int(self.pixels[pos + channel] * (1 - alpha) + color[channel] * alpha)
            self.pixels[pos + 3] = 255

    def rect(self, x: float, y: float, width: float, height: float,
             fill: tuple[int, int, int, int] | None, stroke: tuple[int, int, int, int] | None, stroke_width: int = 1) -> None:
        x0, y0, x1, y1 = round(x), round(y), round(x + width), round(y + height)
        for yy in range(max(0, y0), min(self.height, y1)):
            for xx in range(max(0, x0), min(self.width, x1)):
                self.pixel(xx, yy, fill)
        if stroke:
            for thickness in range(stroke_width):
                for xx in range(x0, x1):
                    self.pixel(xx, y0 + thickness, stroke)
                    self.pixel(xx, y1 - 1 - thickness, stroke)
                for yy in range(y0, y1):
                    self.pixel(x0 + thickness, yy, stroke)
                    self.pixel(x1 - 1 - thickness, yy, stroke)

    def line(self, start: tuple[float, float], end: tuple[float, float],
             color: tuple[int, int, int, int] | None, width: int = 1) -> None:
        x0, y0 = round(start[0]), round(start[1])
        x1, y1 = round(end[0]), round(end[1])
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        while True:
            radius = max(0, width // 2)
            for yy in range(y0 - radius, y0 + radius + 1):
                for xx in range(x0 - radius, x0 + radius + 1):
                    self.pixel(xx, yy, color)
            if x0 == x1 and y0 == y1:
                break
            twice = 2 * err
            if twice >= dy:
                err += dy
                x0 += sx
            if twice <= dx:
                err += dx
                y0 += sy

    def polygon(self, points: list[tuple[float, float]], color: tuple[int, int, int, int] | None) -> None:
        if not points or color is None:
            return
        min_x = math.floor(min(p[0] for p in points))
        max_x = math.ceil(max(p[0] for p in points))
        min_y = math.floor(min(p[1] for p in points))
        max_y = math.ceil(max(p[1] for p in points))
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                inside = False
                j = len(points) - 1
                for i in range(len(points)):
                    xi, yi = points[i]
                    xj, yj = points[j]
                    if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                        inside = not inside
                    j = i
                if inside:
                    self.pixel(x, y, color)

    def arrow(self, start: tuple[float, float], end: tuple[float, float], color: tuple[int, int, int, int] | None) -> None:
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy) or 1
        ux, uy = dx / length, dy / length
        px, py = -uy, ux
        tip = end
        base = (end[0] - ux * 14, end[1] - uy * 14)
        self.polygon([tip, (base[0] + px * 7, base[1] + py * 7), (base[0] - px * 7, base[1] - py * 7)], color)

    def text(self, x: float, y: float, content: str, font_size: float,
             color: tuple[int, int, int, int] | None, anchor: str = "start") -> None:
        scale = max(1, round(font_size / 8))
        content = content.upper()
        text_width = len(content) * 6 * scale
        left = round(x - text_width / 2) if anchor == "middle" else round(x - text_width) if anchor == "end" else round(x)
        top = round(y - 7 * scale)
        for char in content:
            glyph = FONT.get(char, ["11111", "10001", "00110", "00100", "00000", "00100", "00000"])
            for row, bits in enumerate(glyph):
                for col, bit in enumerate(bits):
                    if bit == "1":
                        for dy in range(scale):
                            for dx in range(scale):
                                self.pixel(left + col * scale + dx, top + row * scale + dy, color)
            left += 6 * scale


def float_attr(element: ET.Element, name: str, default: float = 0.0) -> float:
    try:
        return float(element.attrib.get(name, default))
    except ValueError:
        return default


def render_svg_png(svg_path: Path, png_path: Path) -> None:
    root = ET.parse(svg_path).getroot()
    view_box = [float(value) for value in root.attrib.get("viewBox", "0 0 1000 620").replace(",", " ").split()]
    preview = Preview(round(view_box[2]), round(view_box[3]))

    def visit(element: ET.Element, inherited_hidden: bool = False) -> None:
        tag = element.tag.rsplit("}", 1)[-1]
        style = element.attrib.get("style", "").replace(" ", "")
        is_hidden = inherited_hidden or element.attrib.get("display") == "none" or "display:none" in style
        if is_hidden or tag in {"defs", "title", "desc", "metadata", "marker"}:
            return
        fill = parse_color(element.attrib.get("fill"), None)
        stroke = parse_color(element.attrib.get("stroke"), None)
        stroke_width = round(float_attr(element, "stroke-width", 1))
        if tag == "rect":
            preview.rect(float_attr(element, "x"), float_attr(element, "y"), float_attr(element, "width"),
                         float_attr(element, "height"), fill, stroke, stroke_width)
        elif tag == "line":
            start = (float_attr(element, "x1"), float_attr(element, "y1"))
            end = (float_attr(element, "x2"), float_attr(element, "y2"))
            preview.line(start, end, stroke or fill, stroke_width)
            if element.attrib.get("marker-end"):
                preview.arrow(start, end, stroke or fill)
        elif tag == "path" and element.attrib.get("d"):
            tokens = re.findall(r"[MLmlZz]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?",
                                element.attrib["d"].replace(",", " "))
            points: list[tuple[float, float]] = []
            index = 0
            while index < len(tokens):
                if tokens[index].upper() in {"M", "L"} and index + 2 < len(tokens):
                    points.append((float(tokens[index + 1]), float(tokens[index + 2])))
                    index += 3
                elif tokens[index].upper() == "Z":
                    break
                else:
                    index += 1
            if len(points) >= 2:
                for start, end in zip(points, points[1:]):
                    preview.line(start, end, stroke or fill, stroke_width)
                if element.attrib.get("marker-end"):
                    preview.arrow(points[-2], points[-1], stroke or fill)
        elif tag == "text":
            content = "".join(element.itertext()).strip()
            preview.text(float_attr(element, "x"), float_attr(element, "y"), content,
                         float_attr(element, "font-size", 16), fill or parse_color("#000000"),
                         element.attrib.get("text-anchor", "start"))
        for child in list(element):
            visit(child, is_hidden)

    visit(root)
    write_png(png_path, preview.width, preview.height, preview.pixels)
