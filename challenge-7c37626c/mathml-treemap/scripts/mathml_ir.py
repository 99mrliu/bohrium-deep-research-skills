#!/usr/bin/env python3
"""Canonical MathML IR, explicit LaTeX rendering, and structural roundtrip checks.

Stdlib only.  Unicode is never compatibility-normalized (in particular, NFKC is
not used).  The IR deliberately has a small, deterministic JSON shape so two
 structures can be compared without comparing XML formatting.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, Iterable, List, Optional, Tuple

SUPPORTED_TAGS = frozenset(
    {
        "math",
        "mrow",
        "mfrac",
        "msub",
        "msup",
        "msubsup",
        "msqrt",
        "mroot",
        "mfenced",
        "munder",
        "mover",
        "munderover",
        "mtable",
        "mtr",
        "mtd",
        "mi",
        "mn",
        "mo",
        "mtext",
        "mstyle",
        "mpadded",
        "mphantom",
        "mspace",
        "menclose",
        "semantics",
        "annotation",
        "annotation-xml",
        "mlabeledtr",
    }
)
TOKEN_TAGS = frozenset({"mi", "mn", "mo", "mtext"})
TRANSPARENT_TAGS = frozenset({"math", "mrow", "mstyle", "mpadded"})

# Deliberate, codepoint-specific TeX spellings.  This is intentionally not a
# Unicode compatibility mapping: distinct source characters remain distinct in
# the IR even when two operators happen to have the same conventional TeX form.
OPERATOR_TEX = {
    "\u2212": "-",
    "\u2213": r"\mp",
    "\u00b1": r"\pm",
    "\u00d7": r"\times",
    "\u00f7": r"\div",
    "\u22c5": r"\cdot",
    "\u2217": r"\ast",
    "\u2264": r"\leq",
    "\u2265": r"\geq",
    "\u2260": r"\neq",
    "\u2248": r"\approx",
    "\u2211": r"\sum",
    "\u220f": r"\prod",
    "\u222b": r"\int",
    "\u221e": r"\infty",
    "\u2192": r"\to",
    "\u2202": r"\partial",
    "\u2207": r"\nabla",
    "\u2062": "",   # invisible times; codepoint remains in IR
    "\u2063": ",",  # invisible comma separates multi-dimensional indices
    "\u2061": "",   # function application has no visible glyph
}

TEXT_ESCAPES = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "_": r"\_",
    "^": r"\^{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "~": r"\~{}",
}


def local_name(name: str) -> str:
    """Return the local part of an ElementTree expanded XML name."""
    return name.rsplit("}", 1)[-1] if "}" in name else name


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def element_to_ir(element: ET.Element) -> Dict[str, Any]:
    """Convert an XML element recursively to the canonical JSON-compatible IR.

    Element local names and all attributes are retained.  Attribute keys retain
    ElementTree's {namespace}name spelling where applicable.  Element.text is
    retained verbatim.  Child elements are ordered; tails are intentionally not
    represented because inter-element layout tails do not change MathML meaning.
    """
    return {
        "tag": local_name(element.tag),
        "attributes": {str(k): str(v) for k, v in element.attrib.items()},
        "text": element.text or "",
        "children": [
            element_to_ir(child)
            for child in list(element)
            if isinstance(child.tag, str)
        ],
    }


def _validate_ir(node: Any, path: str = "$") -> None:
    if not isinstance(node, dict):
        raise ValueError(f"{path}: IR node must be an object")
    if set(node) != {"tag", "attributes", "text", "children"}:
        raise ValueError(
            f"{path}: IR node keys must be tag, attributes, text, children; "
            f"got {sorted(node)}"
        )
    if not isinstance(node["tag"], str) or not node["tag"]:
        raise ValueError(f"{path}.tag: expected a non-empty string")
    if not isinstance(node["attributes"], dict):
        raise ValueError(f"{path}.attributes: expected an object")
    if not all(
        isinstance(k, str) and isinstance(v, str)
        for k, v in node["attributes"].items()
    ):
        raise ValueError(f"{path}.attributes: keys and values must be strings")
    if not isinstance(node["text"], str):
        raise ValueError(f"{path}.text: expected a string")
    if not isinstance(node["children"], list):
        raise ValueError(f"{path}.children: expected an array")
    for index, child in enumerate(node["children"], 1):
        _validate_ir(child, f"{path}.children[{index}]")


def canonicalize_ir(node: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and return a detached canonical node (attribute order is JSON-only)."""
    _validate_ir(node)
    return {
        "tag": node["tag"],
        "attributes": {k: node["attributes"][k] for k in sorted(node["attributes"])},
        "text": node["text"],
        "children": [canonicalize_ir(child) for child in node["children"]],
    }


def ir_to_element(node: Dict[str, Any]) -> ET.Element:
    """Serialize supported or unsupported IR without silently dropping anything."""
    node = canonicalize_ir(node)
    element = ET.Element(node["tag"], dict(node["attributes"]))
    element.text = node["text"]
    for child in node["children"]:
        element.append(ir_to_element(child))
    return element


def ir_to_mathml(node: Dict[str, Any]) -> str:
    return ET.tostring(ir_to_element(node), encoding="unicode", short_empty_elements=True)


def mathml_to_ir(mathml: str) -> Dict[str, Any]:
    return element_to_ir(ET.fromstring(mathml))


def unsupported_nodes(node: Dict[str, Any], path: str = "$", found: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, str]]:
    if found is None:
        found = []
    tag = node.get("tag", "<missing>")
    if tag not in SUPPORTED_TAGS:
        found.append({"path": path, "tag": str(tag)})
    for index, child in enumerate(node.get("children", []), 1):
        unsupported_nodes(child, f"{path}.children[{index}]", found)
    return found


def compare_ir(expected: Dict[str, Any], actual: Dict[str, Any], path: str = "$") -> List[Dict[str, Any]]:
    """Report every structural difference, including all attribute and child paths."""
    differences: List[Dict[str, Any]] = []
    for field in ("tag", "text"):
        if expected.get(field) != actual.get(field):
            differences.append(
                {
                    "path": f"{path}.{field}",
                    "kind": "value_mismatch",
                    "expected": expected.get(field),
                    "actual": actual.get(field),
                }
            )
    expected_attrs = expected.get("attributes", {})
    actual_attrs = actual.get("attributes", {})
    for key in sorted(set(expected_attrs) | set(actual_attrs)):
        if key not in expected_attrs:
            differences.append(
                {"path": f"{path}.attributes.{key}", "kind": "unexpected_attribute", "actual": actual_attrs[key]}
            )
        elif key not in actual_attrs:
            differences.append(
                {"path": f"{path}.attributes.{key}", "kind": "missing_attribute", "expected": expected_attrs[key]}
            )
        elif expected_attrs[key] != actual_attrs[key]:
            differences.append(
                {
                    "path": f"{path}.attributes.{key}",
                    "kind": "attribute_mismatch",
                    "expected": expected_attrs[key],
                    "actual": actual_attrs[key],
                }
            )
    expected_children = expected.get("children", [])
    actual_children = actual.get("children", [])
    if len(expected_children) != len(actual_children):
        differences.append(
            {
                "path": f"{path}.children",
                "kind": "child_count_mismatch",
                "expected": len(expected_children),
                "actual": len(actual_children),
            }
        )
    for index, (left, right) in enumerate(zip(expected_children, actual_children), 1):
        differences.extend(compare_ir(left, right, f"{path}.children[{index}]"))
    for index in range(len(actual_children) + 1, len(expected_children) + 1):
        differences.append(
            {
                "path": f"{path}.children[{index}]",
                "kind": "missing_child",
                "expected": canonical_json(expected_children[index - 1]),
            }
        )
    for index in range(len(expected_children) + 1, len(actual_children) + 1):
        differences.append(
            {
                "path": f"{path}.children[{index}]",
                "kind": "unexpected_child",
                "actual": canonical_json(actual_children[index - 1]),
            }
        )
    return differences


def roundtrip_ir(node: Dict[str, Any]) -> Dict[str, Any]:
    """Perform IR -> MathML -> IR and return all discrepancies and unsupported nodes."""
    expected = canonicalize_ir(node)
    unsupported = unsupported_nodes(expected)
    mathml = ir_to_mathml(expected)
    try:
        actual = canonicalize_ir(mathml_to_ir(mathml))
        differences = compare_ir(expected, actual)
        parse_error = None
    except (ET.ParseError, ValueError) as exc:
        actual = None
        differences = [{"path": "$", "kind": "roundtrip_parse_error", "actual": str(exc)}]
        parse_error = str(exc)
    if differences:
        status = "mismatch"
    elif unsupported:
        status = "unsupported"
    else:
        status = "pass"
    return {
        "status": status,
        "supported_subset": not unsupported,
        "canonical_equal": not differences,
        "mathml": mathml,
        "discrepancies": differences,
        "unsupported_nodes": unsupported,
        "parse_error": parse_error,
        "canonical_ir_utf8_bytes": len(canonical_json(expected).encode("utf-8")),
        "roundtripped_ir": actual,
    }


def _escape_text(text: str) -> str:
    return "".join(TEXT_ESCAPES.get(char, char) for char in text)


def _render_operator(text: str) -> str:
    return "".join(OPERATOR_TEX.get(char, _escape_text(char)) for char in text)


def _fence(fence: str) -> str:
    if not fence:
        return "."
    # MathML fence attributes are strings.  Preserve their order and use an
    # explicit codepoint mapping rather than normalizing bracket lookalikes.
    rendered = _render_operator(fence)
    if rendered == "{":
        return r"\{"
    if rendered == "}":
        return r"\}"
    return rendered


class _Renderer:
    def __init__(self) -> None:
        self.issues: List[Dict[str, str]] = []

    def issue(self, path: str, kind: str, detail: str) -> None:
        self.issues.append({"path": path, "kind": kind, "detail": detail})

    def marker(self, tag: str) -> str:
        return r"\text{[UNSUPPORTED MathML:" + _escape_text(tag) + "]}"

    def invalid(self, path: str, tag: str, expected: str, actual: int) -> str:
        detail = f"expected {expected} children, got {actual}"
        self.issue(path, "invalid_arity", f"{tag}: {detail}")
        return r"\text{[INVALID MathML " + tag + ": " + detail + "]}"

    def children(self, node: Dict[str, Any], path: str) -> List[str]:
        return [
            self.node(child, f"{path}.children[{index}]")
            for index, child in enumerate(node["children"], 1)
        ]

    def joined(self, node: Dict[str, Any], path: str) -> str:
        return " ".join(part for part in self.children(node, path) if part)

    def fixed_children(self, node: Dict[str, Any], path: str, count: int) -> Optional[List[str]]:
        children = self.children(node, path)
        if len(children) != count:
            return None
        return children

    def node(self, node: Dict[str, Any], path: str = "$") -> str:
        tag = node["tag"]
        attrs = node["attributes"]
        children = node["children"]
        if tag in TRANSPARENT_TAGS:
            return self.joined(node, path)
        if tag == "semantics":
            visible = [child for child in children if child["tag"] not in {"annotation", "annotation-xml"}]
            if not visible:
                self.issue(path, "missing_semantics_body", "semantics has no presentation/content body")
                return r"\text{[MISSING MathML semantics body]}"
            # annotations stay in the IR and roundtrip report but are metadata,
            # not additional visible mathematical operands.
            return " ".join(self.node(child, f"{path}.children[{index}]") for index, child in enumerate(visible, 1))
        if tag in {"annotation", "annotation-xml"}:
            return ""
        if tag == "mphantom":
            return r"\phantom{" + self.joined(node, path) + "}"
        if tag == "mspace":
            return r"\;"
        if tag == "menclose":
            body = self.joined(node, path)
            notation = attrs.get("notation", "longdiv")
            if "radical" in notation.split():
                return r"\sqrt{" + body + "}"
            if "box" in notation.split() or "roundedbox" in notation.split():
                return r"\boxed{" + body + "}"
            self.issue(path, "unrendered_enclose_notation", notation)
            return r"\text{[MathML menclose:" + _escape_text(notation) + "]}" + "{" + body + "}"
        if tag in TOKEN_TAGS:
            own = node["text"].strip()
            if children:
                # Unusual mixed token content is rendered in order after own
                # text and reported rather than silently discarded.
                self.issue(path, "mixed_token_content", f"{tag} contains child elements")
                own += " ".join(self.children(node, path))
            if tag == "mtext":
                return r"\text{" + _escape_text(own) + "}"
            if tag == "mo":
                return _render_operator(own)
            if tag == "mi" and len(own) > 1:
                return r"\mathit{" + _escape_text(own) + "}"
            return _escape_text(own)
        if tag == "mfrac":
            parts = self.fixed_children(node, path, 2)
            return self.invalid(path, tag, "2", len(children)) if parts is None else r"\frac{" + parts[0] + "}{" + parts[1] + "}"
        if tag in {"msub", "msup", "msubsup"}:
            count = 3 if tag == "msubsup" else 2
            parts = self.fixed_children(node, path, count)
            if parts is None:
                return self.invalid(path, tag, str(count), len(children))
            if tag == "msub":
                return "{" + parts[0] + "}_{" + parts[1] + "}"
            if tag == "msup":
                return "{" + parts[0] + "}^{" + parts[1] + "}"
            return "{" + parts[0] + "}_{" + parts[1] + "}^{" + parts[2] + "}"
        if tag == "msqrt":
            parts = self.fixed_children(node, path, 1)
            return self.invalid(path, tag, "1", len(children)) if parts is None else r"\sqrt{" + parts[0] + "}"
        if tag == "mroot":
            parts = self.fixed_children(node, path, 2)
            return self.invalid(path, tag, "2", len(children)) if parts is None else r"\sqrt[" + parts[1] + "]{" + parts[0] + "}"
        if tag == "mfenced":
            parts = self.children(node, path)
            separators = [c for c in attrs.get("separators", ",") if not c.isspace()]
            body = ""
            for index, part in enumerate(parts):
                if index:
                    separator = separators[min(index - 1, len(separators) - 1)] if separators else ""
                    body += " " + _render_operator(separator) + " "
                body += part
            return r"\left" + _fence(attrs.get("open", "(")) + body + r"\right" + _fence(attrs.get("close", ")"))
        if tag in {"munder", "mover", "munderover"}:
            count = 3 if tag == "munderover" else 2
            parts = self.fixed_children(node, path, count)
            if parts is None:
                return self.invalid(path, tag, str(count), len(children))
            if tag == "munder":
                return r"\underset{" + parts[1] + "}{" + parts[0] + "}"
            if tag == "mover":
                return r"\overset{" + parts[1] + "}{" + parts[0] + "}"
            return r"\underset{" + parts[1] + r"}{\overset{" + parts[2] + "}{" + parts[0] + "}}"
        if tag == "mtable":
            rows: List[str] = []
            for index, child in enumerate(children, 1):
                if child["tag"] not in {"mtr", "mlabeledtr"}:
                    self.issue(f"{path}.children[{index}]", "invalid_table_child", child["tag"])
                    rows.append(self.marker(child["tag"]))
                else:
                    rows.append(self.node(child, f"{path}.children[{index}]"))
            return r"\begin{matrix}" + r" \\ ".join(rows) + r"\end{matrix}"
        if tag in {"mtr", "mlabeledtr"}:
            return " & ".join(self.children(node, path))
        if tag == "mtd":
            return self.joined(node, path)
        self.issue(path, "unsupported_tag", tag)
        return self.marker(tag)


def render_latex(node: Dict[str, Any]) -> Tuple[str, List[Dict[str, str]]]:
    """Render without silently omitting malformed or unsupported MathML."""
    canonical = canonicalize_ir(node)
    renderer = _Renderer()
    return renderer.node(canonical), renderer.issues


def independent_text_check(generated_latex: str, publisher_text: Optional[str]) -> Dict[str, Any]:
    """Advisory comparison only; publisher text is never used as generated truth."""
    if publisher_text is None:
        return {
            "status": "absent",
            "publisher_text": None,
            "authoritative": False,
            "note": "No publisher alttext/tex-math was associated with this math node.",
        }
    if publisher_text == generated_latex:
        status = "exact_match"
    elif " ".join(publisher_text.split()) == " ".join(generated_latex.split()):
        status = "whitespace_match"
    else:
        status = "mismatch"
    return {
        "status": status,
        "publisher_text": publisher_text,
        "authoritative": False,
        "note": "Independent advisory comparison; equality does not replace IR roundtrip or scientific interpretation.",
    }
