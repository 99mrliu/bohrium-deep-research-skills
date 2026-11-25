#!/usr/bin/env python3
"""Self-contained safe numerical and unit verification primitives (stdlib only)."""
from __future__ import annotations

import ast
import json
import math
import re
import xml.etree.ElementTree as ET
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class VerificationError(ValueError):
    """An input or evaluation error that must remain visible as missing evidence."""


@dataclass(frozen=True)
class Unit:
    factor: float
    dims: tuple[tuple[str, float], ...]

    def __mul__(self, other: "Unit") -> "Unit":
        dims: dict[str, float] = dict(self.dims)
        for name, power in other.dims:
            dims[name] = dims.get(name, 0.0) + power
        return Unit(self.factor * other.factor, canonical_dims(dims))

    def __truediv__(self, other: "Unit") -> "Unit":
        dims: dict[str, float] = dict(self.dims)
        for name, power in other.dims:
            dims[name] = dims.get(name, 0.0) - power
        return Unit(self.factor / other.factor, canonical_dims(dims))

    def power(self, exponent: float) -> "Unit":
        return Unit(self.factor ** exponent, canonical_dims({k: v * exponent for k, v in self.dims}))


@dataclass(frozen=True)
class EvalValue:
    value: float
    unit: Unit


DIMENSIONLESS = Unit(1.0, ())
BASE_UNITS: dict[str, Unit] = {
    "m": Unit(1.0, (("length", 1.0),)),
    "s": Unit(1.0, (("time", 1.0),)),
    "g": Unit(0.001, (("mass", 1.0),)),
    "A": Unit(1.0, (("current", 1.0),)),
    "K": Unit(1.0, (("temperature", 1.0),)),
    "mol": Unit(1.0, (("amount", 1.0),)),
    "cd": Unit(1.0, (("luminous_intensity", 1.0),)),
    "rad": DIMENSIONLESS,
    "sr": DIMENSIONLESS,
    "Hz": Unit(1.0, (("time", -1.0),)),
    "N": Unit(1.0, (("length", 1.0), ("mass", 1.0), ("time", -2.0))),
    "Pa": Unit(1.0, (("length", -1.0), ("mass", 1.0), ("time", -2.0))),
    "J": Unit(1.0, (("length", 2.0), ("mass", 1.0), ("time", -2.0))),
    "W": Unit(1.0, (("length", 2.0), ("mass", 1.0), ("time", -3.0))),
    "C": Unit(1.0, (("current", 1.0), ("time", 1.0))),
    "V": Unit(1.0, (("length", 2.0), ("mass", 1.0), ("time", -3.0), ("current", -1.0))),
    "F": Unit(1.0, (("length", -2.0), ("mass", -1.0), ("time", 4.0), ("current", 2.0))),
    "ohm": Unit(1.0, (("length", 2.0), ("mass", 1.0), ("time", -3.0), ("current", -2.0))),
    "Ω": Unit(1.0, (("length", 2.0), ("mass", 1.0), ("time", -3.0), ("current", -2.0))),
    "T": Unit(1.0, (("mass", 1.0), ("time", -2.0), ("current", -1.0))),
    "Wb": Unit(1.0, (("length", 2.0), ("mass", 1.0), ("time", -2.0), ("current", -1.0))),
    "H": Unit(1.0, (("length", 2.0), ("mass", 1.0), ("time", -2.0), ("current", -2.0))),
    "l": Unit(0.001, (("length", 3.0),)),
    "L": Unit(0.001, (("length", 3.0),)),
    "min": Unit(60.0, (("time", 1.0),)),
    "h": Unit(3600.0, (("time", 1.0),)),
    "%": Unit(0.01, ()),
}
PREFIXES = {
    "Y": 1e24, "Z": 1e21, "E": 1e18, "P": 1e15, "T": 1e12,
    "G": 1e9, "M": 1e6, "k": 1e3, "h": 1e2, "da": 1e1,
    "d": 1e-1, "c": 1e-2, "m": 1e-3, "u": 1e-6,
    "µ": 1e-6, "μ": 1e-6, "micro": 1e-6, "n": 1e-9,
    "p": 1e-12, "f": 1e-15, "a": 1e-18, "z": 1e-21, "y": 1e-24,
}


def finite_number(raw: Any, label: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise VerificationError(f"{label} must be a finite JSON number")
    value = float(raw)
    if not math.isfinite(value):
        raise VerificationError(f"{label} must be finite")
    return value


def canonical_dims(dims: dict[str, float]) -> tuple[tuple[str, float], ...]:
    return tuple(sorted((k, float(v)) for k, v in dims.items() if abs(v) > 1e-14))


def unit_atom(token: str) -> Unit:
    if token in BASE_UNITS:
        return BASE_UNITS[token]
    for prefix in sorted(PREFIXES, key=len, reverse=True):
        if token.startswith(prefix) and token[len(prefix):] in BASE_UNITS:
            base = BASE_UNITS[token[len(prefix):]]
            return Unit(PREFIXES[prefix] * base.factor, base.dims)
    raise VerificationError(f"unsupported unit atom {token!r}; add an explicit supported unit, not a guessed conversion")


def parse_unit(text: Any) -> Unit:
    if not isinstance(text, str) or not text.strip():
        raise VerificationError("unit must be a non-empty string; use '1' for dimensionless")
    original = text
    text = text.strip().replace("µ", "µ").replace("·", "*").replace("⋅", "*")
    text = text.replace("^", "**").replace("²", "**2").replace("³", "**3")
    text = re.sub(r"(?<=[A-Za-zµμΩ%0-9])\s+(?=[A-Za-zµμΩ%])", "*", text)
    text = re.sub(r"\s+", "", text)
    if text in {"1", "unitless", "dimensionless"}:
        return DIMENSIONLESS
    if not re.fullmatch(r"[A-Za-zµμΩ%*/().+\-0-9]+", text):
        raise VerificationError(f"invalid unit syntax {original!r}")
    parser = UnitParser(text)
    return parser.parse()


class UnitParser:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0

    def parse(self) -> Unit:
        value = self.product()
        if self.pos != len(self.text):
            raise VerificationError(f"unexpected unit syntax at {self.text[self.pos:]!r}")
        return value

    def product(self) -> Unit:
        result = self.power()
        while self.pos < len(self.text) and self.text[self.pos] in "*/":
            op = self.text[self.pos]
            self.pos += 1
            rhs = self.power()
            result = result * rhs if op == "*" else result / rhs
        return result

    def power(self) -> Unit:
        if self.pos < len(self.text) and self.text[self.pos] == "(":
            self.pos += 1
            base = self.product()
            if self.pos >= len(self.text) or self.text[self.pos] != ")":
                raise VerificationError("unclosed unit parenthesis")
            self.pos += 1
        else:
            match = re.match(r"[A-Za-zµμΩ%]+", self.text[self.pos:])
            if not match:
                raise VerificationError(f"expected a unit atom at {self.text[self.pos:]!r}")
            self.pos += len(match.group(0))
            base = unit_atom(match.group(0))
        if self.text[self.pos:self.pos + 2] == "**":
            self.pos += 2
            match = re.match(r"[+\-]?(?:\d+(?:\.\d*)?|\.\d+)", self.text[self.pos:])
            if not match:
                raise VerificationError("invalid unit exponent")
            self.pos += len(match.group(0))
            exponent = float(match.group(0))
            if abs(exponent) > 12:
                raise VerificationError("unit exponent magnitude exceeds 12")
            base = base.power(exponent)
        return base


def mathml_expression(mathml: str) -> str:
    """Translate a small Presentation MathML numeric subset to safe AST syntax."""
    if not isinstance(mathml, str) or not mathml.strip():
        raise VerificationError("MathML value must be a non-empty string")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)", mathml, flags=re.I):
        raise VerificationError("DOCTYPE and ENTITY are forbidden in MathML")
    try:
        root = ET.fromstring(mathml)
    except ET.ParseError as exc:
        raise VerificationError(f"invalid MathML: {exc}") from exc

    def tag(node: ET.Element) -> str:
        return node.tag.rsplit("}", 1)[-1]

    def render(node: ET.Element) -> str:
        kind = tag(node)
        children = [c for c in list(node) if isinstance(c.tag, str) and tag(c) not in {"annotation", "annotation-xml"}]
        if kind in {"math", "mrow", "mstyle", "semantics", "mpadded"}:
            return sequence(children)
        if kind == "mn":
            raw = (node.text or "").strip()
            if not re.fullmatch(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?", raw):
                raise VerificationError(f"MathML <mn> is not a finite decimal literal: {raw!r}")
            return raw
        if kind == "mi":
            raw = (node.text or "").strip()
            if raw in {"π", "pi"}:
                return "pi"
            if raw == "e":
                return "e"
            raise VerificationError(f"MathML identifier {raw!r} is not a sourced numeric value")
        if kind == "mo":
            raw = (node.text or "").strip()
            mapping = {"×": "*", "⋅": "*", "·": "*", "÷": "/", "−": "-", "–": "-"}
            raw = mapping.get(raw, raw)
            if raw not in {"+", "-", "*", "/"}:
                raise VerificationError(f"unsupported MathML operator {raw!r}")
            return raw
        if kind == "msup" and len(children) == 2:
            return f"(({render(children[0])})**({render(children[1])}))"
        if kind == "mfrac" and len(children) == 2:
            return f"(({render(children[0])})/({render(children[1])}))"
        if kind == "msqrt" and children:
            return f"sqrt(({sequence(children)}))"
        if kind in {"mfenced"}:
            return f"({sequence(children)})"
        raise VerificationError(f"unsupported MathML element <{kind}>")

    def sequence(children: list[ET.Element]) -> str:
        if not children:
            raise VerificationError("empty MathML numeric expression")
        tokens = [render(child) for child in children]
        result = tokens[0]
        for token in tokens[1:]:
            if token in {"+", "-", "*", "/"}:
                result += token
            elif result and result[-1] in "+-*/":
                result += token
            else:
                result += "*" + token
        return f"({result})"

    return render(root)


def source_locator(quantity: dict[str, Any]) -> str | None:
    source = quantity.get("source")
    locator = quantity.get("source_locator")
    if isinstance(source, dict) and isinstance(source.get("locator"), str):
        locator = source["locator"]
    return locator.strip() if isinstance(locator, str) and locator.strip() else None


def sourced_quantity(raw: Any, name: str, require_source: bool = True) -> EvalValue:
    if not isinstance(raw, dict):
        raise VerificationError(f"quantity {name!r} must be an object")
    if "value" in raw:
        numeric = finite_number(raw["value"], f"{name}.value")
    elif "mathml" in raw or "value_mathml" in raw:
        expression = mathml_expression(raw.get("mathml", raw.get("value_mathml")))
        numeric = evaluate_scalar(expression)
    else:
        raise VerificationError(f"{name} has no raw value; evidence is insufficient (zero is not imputed)")
    scale = finite_number(raw.get("scale", 1.0), f"{name}.scale")
    unit = parse_unit(raw.get("unit"))
    if require_source and not source_locator(raw):
        raise VerificationError(f"{name} lacks source.locator")
    value = numeric * scale * unit.factor
    if not math.isfinite(value):
        raise VerificationError(f"{name} is outside the finite numeric range")
    return EvalValue(value, Unit(1.0, unit.dims))


def display_quantity(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = sourced_quantity(raw, name)
    unit = parse_unit(raw.get("unit"))
    return {
        "name": name,
        "raw_value": raw.get("value"),
        "mathml": raw.get("mathml", raw.get("value_mathml")),
        "scale": raw.get("scale", 1.0),
        "unit": raw.get("unit"),
        "unit_factor_to_SI": unit.factor,
        "canonical_value": value.value,
        "canonical_dimensions": dict(value.unit.dims),
        "source_locator": source_locator(raw),
    }


ALLOWED_FUNCTIONS = {
    "sqrt": math.sqrt, "abs": abs, "exp": math.exp, "ln": math.log,
    "log": math.log, "log10": math.log10, "sin": math.sin,
    "cos": math.cos, "tan": math.tan, "min": min, "max": max,
}
DIMENSIONLESS_FUNCTIONS = {"exp", "ln", "log", "log10", "sin", "cos", "tan"}


class SafeEvaluator(ast.NodeVisitor):
    def __init__(self, variables: dict[str, EvalValue]):
        self.variables = variables
        self.nodes_seen = 0

    def evaluate(self, expression: str) -> EvalValue:
        if not isinstance(expression, str) or not expression.strip():
            raise VerificationError("formula is absent or empty; cannot recalculate")
        if len(expression) > 10000:
            raise VerificationError("formula exceeds 10000 characters")
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise VerificationError(f"invalid formula syntax: {exc.msg}") from exc
        self.nodes_seen = 0
        value = self.visit(tree.body)
        if not math.isfinite(value.value):
            raise VerificationError("formula produced a non-finite result")
        return value

    def generic_visit(self, node: ast.AST) -> Any:
        raise VerificationError(f"forbidden formula syntax: {type(node).__name__}")

    def visit(self, node: ast.AST) -> Any:
        self.nodes_seen += 1
        if self.nodes_seen > 1000:
            raise VerificationError("formula AST exceeds 1000 nodes")
        return super().visit(node)

    def visit_Constant(self, node: ast.Constant) -> EvalValue:
        return EvalValue(finite_number(node.value, "formula literal"), DIMENSIONLESS)

    def visit_Name(self, node: ast.Name) -> EvalValue:
        if node.id in self.variables:
            return self.variables[node.id]
        if node.id == "pi":
            return EvalValue(math.pi, DIMENSIONLESS)
        if node.id == "e":
            return EvalValue(math.e, DIMENSIONLESS)
        raise VerificationError(f"unknown variable or disallowed name {node.id!r}")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> EvalValue:
        value = self.visit(node.operand)
        if isinstance(node.op, ast.USub):
            return EvalValue(-value.value, value.unit)
        if isinstance(node.op, ast.UAdd):
            return value
        raise VerificationError("only unary + and - are allowed")

    def visit_BinOp(self, node: ast.BinOp) -> EvalValue:
        left, right = self.visit(node.left), self.visit(node.right)
        if isinstance(node.op, ast.Add) or isinstance(node.op, ast.Sub):
            if left.unit.dims != right.unit.dims:
                raise VerificationError(f"dimension mismatch in addition/subtraction: {left.unit.dims} versus {right.unit.dims}")
            value = left.value + right.value if isinstance(node.op, ast.Add) else left.value - right.value
            return EvalValue(value, left.unit)
        if isinstance(node.op, ast.Mult):
            return EvalValue(left.value * right.value, left.unit * right.unit)
        if isinstance(node.op, ast.Div):
            if right.value == 0:
                raise VerificationError("division by zero")
            return EvalValue(left.value / right.value, left.unit / right.unit)
        if isinstance(node.op, ast.Pow):
            if right.unit.dims:
                raise VerificationError("exponent must be dimensionless")
            exponent = right.value
            if abs(exponent) > 12:
                raise VerificationError("exponent magnitude exceeds 12")
            if left.unit.dims and abs(exponent - round(exponent)) > 1e-12:
                raise VerificationError("dimensioned base requires an integer exponent")
            if left.value == 0 and exponent < 0:
                raise VerificationError("zero cannot be raised to a negative exponent")
            try:
                return EvalValue(left.value ** exponent, left.unit.power(exponent))
            except (OverflowError, ValueError) as exc:
                raise VerificationError(f"invalid power: {exc}") from exc
        raise VerificationError("only +, -, *, /, and ** are allowed")

    def visit_Call(self, node: ast.Call) -> EvalValue:
        if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_FUNCTIONS:
            raise VerificationError("function is not in the explicit allowlist")
        if node.keywords:
            raise VerificationError("keyword arguments are not allowed")
        name = node.func.id
        args = [self.visit(arg) for arg in node.args]
        if name in {"min", "max"}:
            if not args or any(arg.unit.dims != args[0].unit.dims for arg in args):
                raise VerificationError(f"{name} requires same-dimension arguments")
            fn = min if name == "min" else max
            return EvalValue(fn(arg.value for arg in args), args[0].unit)
        if len(args) != 1:
            raise VerificationError(f"{name} requires exactly one argument")
        arg = args[0]
        if name in DIMENSIONLESS_FUNCTIONS and arg.unit.dims:
            raise VerificationError(f"{name} requires a dimensionless argument")
        unit = DIMENSIONLESS
        if name == "abs":
            unit = arg.unit
        elif name == "sqrt":
            if any(abs(power / 2 - round(power / 2)) > 1e-12 for _, power in arg.unit.dims):
                raise VerificationError("sqrt would produce fractional dimensions")
            unit = arg.unit.power(0.5)
        try:
            return EvalValue(ALLOWED_FUNCTIONS[name](arg.value), unit)
        except (ValueError, OverflowError) as exc:
            raise VerificationError(f"invalid {name} argument: {exc}") from exc


def evaluate_scalar(expression: str) -> float:
    value = SafeEvaluator({}).evaluate(expression)
    if value.unit.dims:
        raise VerificationError("MathML numeric value unexpectedly has dimensions")
    return value.value


def evaluate_formula(expression: str, variables: dict[str, EvalValue]) -> EvalValue:
    return SafeEvaluator(variables).evaluate(expression)


def convert(value: EvalValue, unit_text: str) -> float:
    target = parse_unit(unit_text)
    if value.unit.dims != target.dims:
        raise VerificationError(f"cannot convert result dimensions {dict(value.unit.dims)} to {unit_text!r} with {dict(target.dims)}")
    converted = value.value / target.factor
    if not math.isfinite(converted):
        raise VerificationError("converted result is non-finite")
    return converted


def tolerance_parts(config: Any, reference: float, comparison: float, reported: dict[str, Any] | None = None) -> dict[str, float]:
    if not isinstance(config, dict) or "absolute" not in config or "relative" not in config:
        raise VerificationError("explicit tolerance.absolute and tolerance.relative are required")
    absolute = finite_number(config["absolute"], "tolerance.absolute")
    relative = finite_number(config["relative"], "tolerance.relative")
    if absolute < 0 or relative < 0:
        raise VerificationError("tolerances must be non-negative")
    rounding_absolute = 0.0
    rounding = config.get("rounding", (reported or {}).get("rounding"))
    if "rounding_absolute" in config:
        rounding_absolute = finite_number(config["rounding_absolute"], "tolerance.rounding_absolute")
    elif isinstance(rounding, dict):
        if "absolute" in rounding:
            rounding_absolute = finite_number(rounding["absolute"], "rounding.absolute")
        elif "step" in rounding:
            step = finite_number(rounding["step"], "rounding.step")
            if step < 0:
                raise VerificationError("rounding.step must be non-negative")
            rounding_absolute = step / 2
        elif "decimal_places" in rounding:
            places = rounding["decimal_places"]
            if isinstance(places, bool) or not isinstance(places, int) or not 0 <= places <= 15:
                raise VerificationError("rounding.decimal_places must be an integer from 0 to 15")
            rounding_absolute = 0.5 * 10 ** (-places)
        else:
            raise VerificationError("rounding requires absolute, step, or decimal_places")
    elif rounding is not None:
        raise VerificationError("rounding must be an object")
    if rounding_absolute < 0:
        raise VerificationError("rounding tolerance must be non-negative")
    scale = max(abs(reference), abs(comparison))
    relative_part = relative * scale
    return {
        "absolute": absolute,
        "relative_coefficient": relative,
        "relative_part": relative_part,
        "rounding_absolute": rounding_absolute,
        "total": absolute + relative_part + rounding_absolute,
    }


def near(left: float, right: float, config: Any, unit: str) -> dict[str, Any]:
    tolerance = tolerance_parts(config, left, right)
    residual = abs(left - right)
    return {
        "left": left, "right": right, "unit": unit,
        "absolute_residual": residual,
        "signed_residual_left_minus_right": left - right,
        "tolerance": tolerance,
        "within_tolerance": residual <= tolerance["total"],
    }


def claim_result(claim: Any, variables: dict[str, EvalValue]) -> dict[str, Any]:
    base: dict[str, Any] = {"claim_id": str(claim.get("claim_id", "unnamed_claim")) if isinstance(claim, dict) else "invalid_claim"}
    try:
        if not isinstance(claim, dict):
            raise VerificationError("claim must be an object")
        if not source_locator(claim):
            raise VerificationError("reported claim lacks source.locator")
        formula = claim.get("formula")
        if not isinstance(formula, str) or not formula.strip():
            raise VerificationError("raw formula is unavailable; cannot recalculate")
        reported = claim.get("reported")
        if not isinstance(reported, dict):
            raise VerificationError("reported interval/value and unit are required")
        unit = reported.get("unit")
        parse_unit(unit)
        recomputed = evaluate_formula(formula, variables)
        recomputed_value = convert(recomputed, unit)
        if "lower" in reported or "upper" in reported:
            if "lower" not in reported or "upper" not in reported:
                raise VerificationError("both reported.lower and reported.upper are required")
            lower_num = finite_number(reported["lower"], "reported.lower")
            upper_num = finite_number(reported["upper"], "reported.upper")
        elif "value" in reported:
            lower_num = upper_num = finite_number(reported["value"], "reported.value")
        else:
            raise VerificationError("reported numeric value/interval is unavailable; evidence is insufficient")
        report_scale = finite_number(reported.get("scale", 1.0), "reported.scale")
        lower, upper = sorted((lower_num * report_scale, upper_num * report_scale))
        residual = 0.0 if lower <= recomputed_value <= upper else min(abs(recomputed_value - lower), abs(recomputed_value - upper))
        signed = 0.0 if residual == 0 else (recomputed_value - lower if recomputed_value < lower else recomputed_value - upper)
        tolerance = tolerance_parts(claim.get("tolerance"), recomputed_value, lower if recomputed_value < lower else upper, reported)
        base.update({
            "verdict": "compatible" if residual <= tolerance["total"] else "inconsistent",
            "formula": formula,
            "reported": {"lower": lower, "upper": upper, "unit": unit, "scale": report_scale, "source_locator": source_locator(claim)},
            "recomputed_value": recomputed_value,
            "recomputed_canonical_value": recomputed.value,
            "residual_to_reported_interval": residual,
            "signed_residual_to_nearest_bound": signed,
            "tolerance": tolerance,
            "expanded_reported_interval": [lower - tolerance["total"], upper + tolerance["total"]],
            "comparison": "residual_to_interval <= absolute + relative*max magnitudes + rounding_absolute",
            "note": "Numerical agreement does not validate the model or assumptions.",
        })
    except (VerificationError, TypeError, ValueError) as exc:
        base.update({"verdict": "insufficient_evidence", "error": str(exc)})
    return base


def load_property_document(case: dict[str, Any], case_dir: Path) -> tuple[dict[str, Any], Path | None]:
    ref = case.get("metamorphic_properties", case.get("property_spec"))
    if ref is None:
        return {"properties": [], "fault_injections": case.get("fault_injections", [])}, None
    if isinstance(ref, str):
        path = (case_dir / ref).resolve() if not Path(ref).is_absolute() else Path(ref)
        try:
            with path.open("r", encoding="utf-8") as handle:
                document = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise VerificationError(f"cannot load property spec {path}: {exc}") from exc
        if not isinstance(document, dict):
            raise VerificationError("property spec must be a JSON object")
        return document, path
    if isinstance(ref, list):
        return {"properties": ref, "fault_injections": case.get("fault_injections", [])}, None
    if isinstance(ref, dict):
        return ref, None
    raise VerificationError("metamorphic_properties must be a path, list, or object")


def scenario_quantity(raw: Any, name: str) -> EvalValue:
    return sourced_quantity(raw, name, require_source=False)


def variable_set(raw_quantities: dict[str, Any], require_source: bool = True) -> tuple[dict[str, EvalValue], list[dict[str, Any]], list[str]]:
    variables: dict[str, EvalValue] = {}
    displays: list[dict[str, Any]] = []
    errors: list[str] = []
    if not isinstance(raw_quantities, dict):
        return variables, displays, ["quantities must be an object"]
    for name, raw in raw_quantities.items():
        try:
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_]\w*", name):
                raise VerificationError(f"invalid quantity variable name {name!r}")
            variables[name] = sourced_quantity(raw, name, require_source=require_source)
            displays.append(display_quantity(raw, name))
        except (VerificationError, TypeError) as exc:
            errors.append(str(exc))
    return variables, displays, errors


def apply_mutation(raw_quantities: dict[str, Any], mutation: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    changed = deepcopy(raw_quantities)
    target = mutation.get("target", mutation.get("scale_variable"))
    if target not in changed:
        raise VerificationError(f"mutation target {target!r} is unavailable")
    original = changed[target]
    if not isinstance(original, dict):
        raise VerificationError("mutation target must be a quantity object")
    detail: dict[str, Any] = {"target": target, "before": deepcopy(original)}
    kind = mutation.get("kind", mutation.get("operation"))
    if kind in {"dimensional_prefix_mutation", "unit_prefix", "relabel_unit"}:
        replacement = mutation.get("replacement_unit")
        if not isinstance(replacement, str):
            raise VerificationError("dimensional/prefix mutation requires replacement_unit")
        old_unit = parse_unit(original.get("unit"))
        new_unit = parse_unit(replacement)
        if old_unit.dims != new_unit.dims:
            raise VerificationError("prefix mutation must preserve dimensions; use a dimensional inconsistency test separately")
        changed[target]["unit"] = replacement
        detail.update({"operation": "relabel_unit_without_changing_raw_value", "after": deepcopy(changed[target]), "canonical_mutation_factor": old_unit.factor / new_unit.factor})
    elif kind in {"scale", "multiply"}:
        factor = finite_number(mutation.get("factor"), "mutation.factor")
        changed[target]["scale"] = finite_number(original.get("scale", 1.0), "original.scale") * factor
        detail.update({"operation": "multiply_scale", "factor": factor, "after": deepcopy(changed[target])})
    elif kind == "convert_value_and_unit":
        replacement = mutation.get("replacement_unit")
        old_unit = parse_unit(original.get("unit"))
        new_unit = parse_unit(replacement)
        if old_unit.dims != new_unit.dims:
            raise VerificationError("conversion dimensions differ")
        value = sourced_quantity(original, target)
        changed[target]["value"] = value.value / (new_unit.factor * finite_number(original.get("scale", 1.0), "scale"))
        changed[target]["unit"] = replacement
        changed[target].pop("mathml", None)
        changed[target].pop("value_mathml", None)
        detail.update({"operation": "valid_unit_conversion_control", "canonical_mutation_factor": 1.0, "after": deepcopy(changed[target])})
    else:
        raise VerificationError(f"unsupported mutation kind {kind!r}")
    return changed, detail


def property_context(raw_quantities: dict[str, Any]) -> dict[str, EvalValue]:
    # Mutation operands are intentionally scenario-defined; baseline sources were checked separately.
    variables, _, errors = variable_set(raw_quantities, require_source=False)
    if errors:
        raise VerificationError("; ".join(errors))
    return variables


def evaluate_property(prop: dict[str, Any], raw_quantities: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"property_id": str(prop.get("property_id", "unnamed_property")), "kind": prop.get("kind")}
    try:
        if not isinstance(prop.get("property_id"), str) or not prop["property_id"].strip():
            raise VerificationError("property_id is required")
        if not source_locator(prop):
            raise VerificationError("independently authored property requires source.locator identifying its authorship")
        if not isinstance(prop.get("independence_statement"), str) or not prop["independence_statement"].strip():
            raise VerificationError("property requires an independence_statement; no property is auto-invented")
        variables = property_context(raw_quantities)
        kind = prop.get("kind")
        if kind == "scale_invariance":
            formula = prop.get("formula")
            target = prop.get("scale_variable")
            multipliers = prop.get("multipliers")
            if not isinstance(multipliers, list) or not multipliers:
                raise VerificationError("scale_invariance requires non-empty multipliers")
            unit = prop.get("output_unit")
            base = convert(evaluate_formula(formula, variables), unit)
            comparisons = []
            for multiplier_raw in multipliers:
                multiplier = finite_number(multiplier_raw, "scale multiplier")
                targets = prop.get("scale_variables", [target])
                if not isinstance(targets, list) or not targets:
                    raise VerificationError("scale_invariance requires scale_variable or non-empty scale_variables")
                changed = deepcopy(raw_quantities)
                for scale_target in targets:
                    changed, _ = apply_mutation(changed, {"target": scale_target, "kind": "scale", "factor": multiplier})
                mutated = convert(evaluate_formula(formula, property_context(changed)), unit)
                comparison = near(base, mutated, prop.get("tolerance"), unit)
                comparison["multiplier"] = multiplier
                comparisons.append(comparison)
            result.update({"verdict": "passed" if all(c["within_tolerance"] for c in comparisons) else "failed", "baseline": base, "output_unit": unit, "comparisons": comparisons})
        elif kind == "monotonic_direction_over_sweep":
            formula = prop.get("formula")
            target = prop.get("sweep_variable")
            values = prop.get("sweep_values")
            if not isinstance(values, list) or len(values) < 2:
                raise VerificationError("monotonic sweep requires at least two sourced/authored scenario values")
            unit = prop.get("output_unit")
            direction = prop.get("expected_direction")
            if direction not in {"strictly_increasing", "strictly_decreasing", "nondecreasing", "nonincreasing"}:
                raise VerificationError("expected_direction must be explicit")
            points = []
            for index, raw in enumerate(values):
                changed = deepcopy(raw_quantities)
                changed[target] = deepcopy(raw)
                evaluate = evaluate_formula(formula, property_context(changed))
                output = convert(evaluate, unit)
                points.append({"index": index, "input": deepcopy(raw), "output": output, "canonical_output": evaluate.value})
            steps = []
            for left, right in zip(points, points[1:]):
                delta = right["output"] - left["output"]
                tol = tolerance_parts(prop.get("tolerance"), left["output"], right["output"])
                if direction == "strictly_increasing":
                    passed = delta > tol["total"]
                elif direction == "strictly_decreasing":
                    passed = delta < -tol["total"]
                elif direction == "nondecreasing":
                    passed = delta >= -tol["total"]
                else:
                    passed = delta <= tol["total"]
                steps.append({"left_index": left["index"], "right_index": right["index"], "delta": delta, "tolerance": tol, "within_tolerance": passed})
            result.update({"verdict": "passed" if all(s["within_tolerance"] for s in steps) else "failed", "expected_direction": direction, "output_unit": unit, "points": points, "steps": steps, "plot_requested": bool(prop.get("plot", False))})
        elif kind == "limit":
            formula = prop.get("formula")
            target = prop.get("limit_variable")
            approaches = prop.get("approach_values")
            if not isinstance(approaches, list) or not approaches:
                raise VerificationError("limit requires approach_values as an explicit finite sequence")
            expected_raw = prop.get("expected")
            if not isinstance(expected_raw, dict):
                raise VerificationError("limit requires an independently authored expected quantity")
            unit = expected_raw.get("unit")
            expected = convert(scenario_quantity(expected_raw, "expected limit"), unit)
            sequence = []
            for index, raw in enumerate(approaches):
                changed = deepcopy(raw_quantities)
                changed[target] = deepcopy(raw)
                actual = convert(evaluate_formula(formula, property_context(changed)), unit)
                comparison = near(actual, expected, prop.get("tolerance"), unit)
                comparison.update({"index": index, "approach": deepcopy(raw)})
                sequence.append(comparison)
            # A finite approach sequence is evidence about the supplied limit test, not a proof of a mathematical limit.
            result.update({"verdict": "passed" if sequence[-1]["within_tolerance"] else "failed", "expected": expected, "output_unit": unit, "sequence": sequence, "caveat": "Passing a finite approach sequence is not a proof of a limit."})
        elif kind == "expected_transformed_relation":
            mutations = prop.get("mutations", [])
            if not isinstance(mutations, list):
                raise VerificationError("mutations must be a list")
            changed = deepcopy(raw_quantities)
            mutation_details = []
            for mutation in mutations:
                changed, detail = apply_mutation(changed, mutation)
                mutation_details.append(detail)
            unit = prop.get("output_unit")
            left = convert(evaluate_formula(prop.get("left_formula"), property_context(changed)), unit)
            right = convert(evaluate_formula(prop.get("right_formula"), variables), unit)
            comparison = near(left, right, prop.get("tolerance"), unit)
            result.update({"verdict": "passed" if comparison["within_tolerance"] else "failed", "output_unit": unit, "mutations": mutation_details, "comparison": comparison})
        else:
            raise VerificationError(f"unsupported or absent property kind {kind!r}")
    except (VerificationError, TypeError, ValueError) as exc:
        result.update({"verdict": "insufficient_evidence", "error": str(exc)})
    return result


def source_overall(claims: list[dict[str, Any]]) -> str:
    if not claims or any(c.get("verdict") == "insufficient_evidence" for c in claims):
        return "insufficient_evidence"
    if any(c.get("verdict") == "inconsistent" for c in claims):
        return "inconsistent_with_recomputed_value"
    return "compatible_within_tolerance"


def evaluate_analysis(case: dict[str, Any], case_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    case_id = case.get("case_id")
    analysis: dict[str, Any] = {
        "case_id": case_id,
        "source_claim_verdict": "insufficient_evidence",
        "diagnostic_fault_injection_verdict": {"overall": "not_run", "faults": []},
        "claims": [], "intermediate_input_values": [], "property_results": [],
        "warnings": [], "errors": [], "evidence_gaps": [],
        "method_note": "Equality within tolerance does not validate a model, its assumptions, or a source; invariants are independent only if not derived from the claimed result.",
    }
    variables, displays, errors = variable_set(case.get("quantities", {}), require_source=True)
    analysis["intermediate_input_values"] = displays
    analysis["errors"].extend(errors)
    raw_claims = case.get("reported_claims", [])
    if not isinstance(raw_claims, list) or not raw_claims:
        analysis["evidence_gaps"].append("No reported claims with raw values/formulas were supplied.")
        raw_claims = []
    claims = [claim_result(claim, variables) for claim in raw_claims]
    analysis["claims"] = claims
    analysis["source_claim_verdict"] = source_overall(claims)
    try:
        document, spec_path = load_property_document(case, case_dir)
    except VerificationError as exc:
        analysis["errors"].append(str(exc))
        document, spec_path = {"properties": []}, None
    analysis["property_spec_path"] = str(spec_path) if spec_path else None
    raw_properties = document.get("properties", [])
    if not isinstance(raw_properties, list):
        analysis["errors"].append("property spec properties must be a list")
        raw_properties = []
    properties = [evaluate_property(prop, case.get("quantities", {})) if isinstance(prop, dict) else {"verdict": "insufficient_evidence", "error": "property must be an object"} for prop in raw_properties]
    analysis["property_results"] = properties
    if not properties:
        analysis["evidence_gaps"].append("No independently authored metamorphic properties: result remains partial, not vacuous success.")
    elif any(p.get("verdict") == "insufficient_evidence" for p in properties):
        analysis["evidence_gaps"].append("At least one authored property could not be evaluated.")

    faults = document.get("fault_injections", case.get("fault_injections", []))
    if not isinstance(faults, list):
        analysis["errors"].append("fault_injections must be a list")
        faults = []
    fault_results = []
    for raw_fault in faults:
        fault_result: dict[str, Any] = {"fault_id": str(raw_fault.get("fault_id", "unnamed_fault")) if isinstance(raw_fault, dict) else "invalid_fault"}
        try:
            if not isinstance(raw_fault, dict):
                raise VerificationError("fault injection must be an object")
            mutated, mutation_detail = apply_mutation(case.get("quantities", {}), raw_fault)
            mutated_variables, mutated_displays, mutation_errors = variable_set(mutated, require_source=True)
            if mutation_errors:
                raise VerificationError("; ".join(mutation_errors))
            mutated_claims = [claim_result(claim, mutated_variables) for claim in raw_claims]
            mutated_properties = [evaluate_property(prop, mutated) for prop in raw_properties if isinstance(prop, dict)]
            detections = []
            for baseline, altered in zip(claims, mutated_claims):
                if baseline.get("verdict") == "compatible" and altered.get("verdict") == "inconsistent":
                    detections.append({"kind": "source_claim_transition", "id": baseline.get("claim_id"), "before": "compatible", "after": "inconsistent", "altered_residual": altered.get("residual_to_reported_interval")})
            for baseline, altered in zip(properties, mutated_properties):
                if baseline.get("verdict") == "passed" and altered.get("verdict") == "failed":
                    detections.append({"kind": "metamorphic_property_transition", "id": baseline.get("property_id"), "before": "passed", "after": "failed"})
            expected = raw_fault.get("expect", "detected")
            if expected != "detected":
                raise VerificationError("only expect='detected' is supported for deliberate faults; use convert_value_and_unit as a separate control")
            verdict = "fault_detected" if detections else "fault_not_detected"
            fault_result.update({
                "verdict": verdict, "mutation": mutation_detail, "detections": detections,
                "mutated_input_values": mutated_displays,
                "mutated_claim_results": mutated_claims,
                "mutated_property_results": mutated_properties,
                "attribution": "deliberate synthetic mutation only; not evidence against the paper or source",
            })
        except (VerificationError, TypeError, ValueError) as exc:
            fault_result.update({"verdict": "insufficient_evidence", "error": str(exc), "attribution": "diagnostic only"})
        fault_results.append(fault_result)
    if fault_results:
        if any(f.get("verdict") == "insufficient_evidence" for f in fault_results):
            overall = "insufficient_evidence"
        elif all(f.get("verdict") == "fault_detected" for f in fault_results):
            overall = "all_injected_faults_detected"
        elif any(f.get("verdict") == "fault_detected" for f in fault_results):
            overall = "some_injected_faults_not_detected"
        else:
            overall = "injected_faults_not_detected"
    else:
        overall = "no_fault_injections"
    analysis["diagnostic_fault_injection_verdict"] = {"overall": overall, "faults": fault_results}

    failed_properties = [p for p in properties if p.get("verdict") == "failed"]
    complete = bool(claims) and bool(properties) and not errors and not analysis["evidence_gaps"] and all(c.get("verdict") != "insufficient_evidence" for c in claims) and all(p.get("verdict") != "insufficient_evidence" for p in properties)
    analysis["recommended_status"] = "complete" if complete else "partial"
    if complete and (analysis["source_claim_verdict"] == "inconsistent_with_recomputed_value" or failed_properties):
        analysis["outcome"] = "falsifying_discrepancy_found"
    elif complete:
        analysis["outcome"] = "numerically_compatible_with_supplied_checks"
    else:
        analysis["outcome"] = "insufficient_evidence_for_complete_verification"
    if failed_properties:
        analysis["outcome_detail"] = "At least one independent invariant failed; inspect rather than attributing this to injected faults."
    analysis["claim_caveat"] = "A compatible source claim is not model validation. A failed property can falsify a stated expectation but does not by itself identify which assumption is wrong."
    return analysis, properties
