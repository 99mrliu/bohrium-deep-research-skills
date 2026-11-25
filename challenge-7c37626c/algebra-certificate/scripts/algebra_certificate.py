#!/usr/bin/env python3
"""Standalone local-transition algebra certificate checker and result finalizer.

No Python eval/exec is used for expression parsing. SymPy is the sole non-stdlib
runtime dependency. Both falsified mathematics and unavailable tooling produce
honest certificates; neither is a process error merely because success is blocked.
"""

from __future__ import annotations

import argparse
import ast
import itertools
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    import sympy as sp
except (ImportError, ModuleNotFoundError) as exc:  # graceful, never a fake pass
    sp = None
    SYMPY_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    SYMPY_IMPORT_ERROR = None

SCHEMA_VERSION = "algebra-certificate/v1"
STEP_VERDICTS = (
    "symbolic_equal",
    "falsified",
    "undetermined",
    "invalid_operation",
    "missing_license",
)
ORIGINS = ("paper_explicit", "reader_reconstruction")
OPERATIONS = {
    "expand",
    "factor",
    "simplify",
    "rewrite",
    "cancel",
    "divide",
    "substitute",
    "add",
    "multiply",
    "sqrt_rule",
    "log_rule",
    "power_rule",
}
FUNCTION_NAMES = {"sqrt", "log", "exp", "Abs", "sin", "cos", "tan"}
CONSTANT_NAMES = {"pi", "E", "I"}
PROPERTY_WORDS = {
    "real",
    "positive",
    "negative",
    "nonnegative",
    "nonpositive",
    "nonzero",
    "integer",
}
IDENTIFIER = re.compile(r"\b[A-Za-z_]\w*\b")


class ExpressionError(ValueError):
    """Rejected syntax or an expression outside the safe grammar."""


def json_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def json_load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_declarations(value: Any, field: str) -> list[str]:
    """Normalize arrays, strings, and simple symbol->property objects."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        if not all(isinstance(item, str) for item in value):
            raise ExpressionError(f"{field} array entries must be strings")
        return [item for item in value if item.strip()]
    if isinstance(value, dict):
        declarations: list[str] = []
        for symbol, raw in value.items():
            if not isinstance(symbol, str) or not symbol.isidentifier():
                raise ExpressionError(f"{field} object key is not a symbol: {symbol!r}")
            if isinstance(raw, str):
                pieces = [p.strip() for p in raw.split(";") if p.strip()]
            elif isinstance(raw, list) and all(isinstance(p, str) for p in raw):
                pieces = raw
            else:
                raise ExpressionError(f"{field}.{symbol} must be a string or string array")
            for piece in pieces:
                if re.search(r"[<>!=]=?", piece):
                    declarations.append(piece)
                else:
                    words = piece.replace(",", " ").split()
                    declarations.extend(f"{symbol} {word}" for word in words)
        return declarations
    raise ExpressionError(f"{field} must be a string, string array, or object")


def symbol_properties(declarations: Iterable[str]) -> dict[str, dict[str, bool]]:
    properties: dict[str, dict[str, bool]] = {}
    for declaration in declarations:
        match = re.fullmatch(
            r"\s*([A-Za-z_]\w*)\s+((?:(?:real|positive|negative|nonnegative|nonpositive|nonzero|integer)\s*)+)",
            declaration,
        )
        if match:
            name, words = match.groups()
            for prop in words.split():
                target = properties.setdefault(name, {})
                target[prop] = True
                if prop in {"positive", "negative", "nonnegative", "nonpositive", "integer"}:
                    target["real"] = True
                if prop in {"positive", "negative"}:
                    target["nonzero"] = True
            continue
        relation = re.fullmatch(
            r"\s*([A-Za-z_]\w*)\s*(>=|<=|!=|==|>|<|=)\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*",
            declaration,
        )
        reverse = False
        if not relation:
            relation = re.fullmatch(
                r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(>=|<=|!=|==|>|<|=)\s*([A-Za-z_]\w*)\s*",
                declaration,
            )
            reverse = True
        if relation:
            first, operator, third = relation.groups()
            name, number = (third, first) if reverse else (first, third)
            if reverse:
                operator = {">": "<", "<": ">", ">=": "<=", "<=": ">="}.get(operator, operator)
            if number in {"0", "+0", "-0", "0.0", "+0.0", "-0.0"}:
                target = properties.setdefault(name, {})
                if operator == ">":
                    target.update(positive=True, real=True, nonzero=True)
                elif operator == "<":
                    target.update(negative=True, real=True, nonzero=True)
                elif operator == ">=":
                    target.update(nonnegative=True, real=True)
                elif operator == "<=":
                    target.update(nonpositive=True, real=True)
                elif operator == "!=":
                    target["nonzero"] = True
                elif operator in {"=", "=="}:
                    # x = 0 intentionally overrides a nonzero claim nowhere; the
                    # contradictory declarations will be left to SymPy/sampling.
                    target.update(real=True)
    return properties


class SafeParser:
    """Restricted AST-to-SymPy parser with original operations left unevaluated."""

    def __init__(self, declarations: list[str]):
        if sp is None:
            raise ExpressionError("SymPy is unavailable")
        self.declarations = declarations
        self.properties = symbol_properties(declarations)
        self.symbols: dict[str, Any] = {}

    def _symbol(self, name: str) -> Any:
        if name not in self.symbols:
            self.symbols[name] = sp.Symbol(name, **self.properties.get(name, {}))
        return self.symbols[name]

    def parse(self, text: Any) -> Any:
        if not isinstance(text, str) or not text.strip():
            raise ExpressionError("expression must be a nonempty string")
        if len(text) > 20000:
            raise ExpressionError("expression exceeds 20,000 characters")
        # Python and mathematical exponent precedence coincide after this mapping.
        normalized = text.replace("^", "**")
        try:
            tree = ast.parse(normalized.strip(), mode="eval")
        except (SyntaxError, ValueError) as exc:
            raise ExpressionError(f"unsafe/invalid expression syntax: {exc}") from exc
        return self._node(tree.body)

    def _node(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or node.value is None or not isinstance(node.value, (int, float)):
                raise ExpressionError("only real integer/float literals are allowed")
            if isinstance(node.value, float) and not math.isfinite(node.value):
                raise ExpressionError("nonfinite numeric literal is not allowed")
            return sp.Integer(node.value) if isinstance(node.value, int) else sp.Float(node.value)
        if isinstance(node, ast.Name):
            if node.id in CONSTANT_NAMES:
                return {"pi": sp.pi, "E": sp.E, "I": sp.I}[node.id]
            if node.id in FUNCTION_NAMES:
                raise ExpressionError(f"function {node.id} must be called with arguments")
            return self._symbol(node.id)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = self._node(node.operand)
            if isinstance(node.op, ast.UAdd):
                return value
            return sp.Mul(sp.Integer(-1), value, evaluate=False)
        if isinstance(node, ast.BinOp):
            left = self._node(node.left)
            right = self._node(node.right)
            if isinstance(node.op, ast.Add):
                return sp.Add(left, right, evaluate=False)
            if isinstance(node.op, ast.Sub):
                return sp.Add(left, sp.Mul(sp.Integer(-1), right, evaluate=False), evaluate=False)
            if isinstance(node.op, ast.Mult):
                return sp.Mul(left, right, evaluate=False)
            if isinstance(node.op, ast.Div):
                return sp.Mul(left, sp.Pow(right, sp.Integer(-1), evaluate=False), evaluate=False)
            if isinstance(node.op, ast.Pow):
                # Prevent resource-exhaustion literals without limiting symbolic exponents.
                if right.is_Integer is True and abs(int(right)) > 1000:
                    raise ExpressionError("literal exponent magnitude exceeds 1000")
                return sp.Pow(left, right, evaluate=False)
            raise ExpressionError(f"operator {type(node.op).__name__} is not allowed")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id
            if name not in FUNCTION_NAMES or node.keywords:
                raise ExpressionError("only allowlisted functions with positional arguments are allowed")
            args = [self._node(arg) for arg in node.args]
            expected = 1
            if len(args) != expected:
                raise ExpressionError(f"{name} requires exactly one argument")
            arg = args[0]
            if name == "sqrt":
                return sp.Pow(arg, sp.Rational(1, 2), evaluate=False)
            functions = {
                "log": sp.log,
                "exp": sp.exp,
                "Abs": sp.Abs,
                "sin": sp.sin,
                "cos": sp.cos,
                "tan": sp.tan,
            }
            try:
                return functions[name](arg, evaluate=False)
            except (TypeError, ValueError) as exc:
                raise ExpressionError(f"cannot construct {name}: {exc}") from exc
        raise ExpressionError(f"AST node {type(node).__name__} is not allowed")

    def comparison(self, declaration: str) -> Any:
        if sp is None:
            raise ExpressionError("SymPy is unavailable")
        match = re.fullmatch(r"\s*(.+?)\s*(>=|<=|!=|==|>|<|=)\s*(.+?)\s*", declaration)
        if not match:
            raise ExpressionError(f"not a property word or single comparison: {declaration!r}")
        left_text, operator, right_text = match.groups()
        left, right = self.parse(left_text), self.parse(right_text)
        operators = {
            ">": sp.Gt,
            ">=": sp.Ge,
            "<": sp.Lt,
            "<=": sp.Le,
            "!=": sp.Ne,
            "=": sp.Eq,
            "==": sp.Eq,
        }
        return operators[operator](left, right, evaluate=False)


def declarations_for_step(step: dict[str, Any]) -> list[str]:
    declarations = normalize_declarations(step.get("assumptions"), "assumptions")
    declarations.extend(normalize_declarations(step.get("domain"), "domain"))
    return declarations


def explicit_nonzero_factors(step: dict[str, Any], parser: SafeParser) -> tuple[list[Any], list[str]]:
    raw = step.get("nonzero_factors", [])
    if raw is None:
        raw = []
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ExpressionError("nonzero_factors must be an array of expressions")
    factors: list[Any] = []
    declarations: list[str] = []
    for text in raw:
        factors.append(parser.parse(text))
        declarations.append(f"nonzero license declared for ({text})")
    return factors, declarations


def expression_is_nonzero(expr: Any, declared_factors: list[Any]) -> bool:
    if expr.is_zero is False:
        return True
    if expr.is_positive is True or expr.is_negative is True:
        return True
    for factor in declared_factors:
        try:
            if sp.simplify(sp.Add(expr, -factor, evaluate=False)) == 0:
                return True
            # A product declared nonzero also licenses its exact positive powers.
            if expr.is_Pow and expr.exp.is_Integer is True and int(expr.exp) > 0:
                if sp.simplify(sp.Add(expr.base, -factor, evaluate=False)) == 0:
                    return True
        except (TypeError, ValueError, NotImplementedError):
            continue
    return False


def expression_is_positive(expr: Any) -> bool:
    return expr.is_positive is True


def expression_is_nonnegative(expr: Any) -> bool:
    return expr.is_nonnegative is True or expr.is_positive is True


def domain_audit(step: dict[str, Any], expressions: Iterable[Any], nonzero_factors: list[Any]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for expression in expressions:
        for node in sp.preorder_traversal(expression):
            if node.is_Pow:
                exponent = node.exp
                base = node.base
                if exponent.is_Integer is True and int(exponent) < 0:
                    if not expression_is_nonzero(base, nonzero_factors):
                        message = f"division/negative power denominator ({base}) lacks a nonzero declaration"
                        if message not in seen:
                            errors.append(message)
                            seen.add(message)
                elif exponent.is_number and exponent.is_integer is not True:
                    is_half = exponent == sp.Rational(1, 2)
                    if exponent.is_Float is True:
                        try:
                            is_half = sp.Rational(str(exponent)) == sp.Rational(1, 2)
                        except (ValueError, TypeError):
                            is_half = False
                    if is_half:
                        if not expression_is_nonnegative(base):
                            message = f"real square-root radicand ({base}) lacks a nonnegative declaration"
                            if message not in seen:
                                errors.append(message)
                                seen.add(message)
                    elif not expression_is_positive(base):
                        message = f"real noninteger power base ({base}) lacks a positive declaration"
                        if message not in seen:
                            errors.append(message)
                            seen.add(message)
            if node.func == sp.log:
                argument = node.args[0]
                if not expression_is_positive(argument):
                    message = f"real logarithm argument ({argument}) lacks a positive declaration"
                    if message not in seen:
                        errors.append(message)
                        seen.add(message)
    if step.get("operation") == "cancel" and nonzero_factors:
        # Explicit factors are already used by denominator checks. This note is not
        # an error: cancellation can be licensed by an ordinary x != 0 declaration.
        pass
    return errors


def symbolic_zero(lhs: Any, rhs: Any) -> tuple[bool, list[str]]:
    notes: list[str] = []
    difference = sp.Add(lhs, sp.Mul(sp.Integer(-1), rhs, evaluate=False), evaluate=False)
    attempts = (
        ("simplify(lhs-rhs)", lambda: sp.simplify(difference)),
        ("expand(lhs-rhs)", lambda: sp.expand(difference)),
        ("factor(lhs-rhs)", lambda: sp.factor(difference)),
        ("trigsimp(lhs-rhs)", lambda: sp.trigsimp(difference)),
        ("powsimp(lhs-rhs)", lambda: sp.powsimp(difference, force=False)),
    )
    for label, function in attempts:
        try:
            reduced = function()
            text = str(reduced)
            notes.append(f"{label} -> {text[:500]}")
            if reduced == 0 or reduced.is_zero is True:
                return True, notes
        except (TypeError, ValueError, NotImplementedError, RecursionError) as exc:
            notes.append(f"{label} raised {type(exc).__name__}: {exc}")
    return False, notes


def _satisfied(relation: Any, assignment: dict[Any, Any]) -> bool | None:
    try:
        value = relation.subs(assignment, simultaneous=True)
        value = sp.simplify(value)
        if value is sp.true:
            return True
        if value is sp.false:
            return False
        # bool(None/False) is deliberately not converted into mathematical false.
        if isinstance(value, bool):
            return None
        evaluated = value.evalf(40)
        if evaluated is sp.true:
            return True
        if evaluated is sp.false:
            return False
        return None
    except (TypeError, ValueError, NotImplementedError, ZeroDivisionError):
        return None


def candidate_values(declarations: list[str]) -> list[Any]:
    values = {sp.Rational(-5), sp.Rational(-3), sp.Rational(-2), sp.Rational(-1),
              sp.Rational(-1, 2), sp.Rational(0), sp.Rational(1, 2), sp.Rational(1),
              sp.Rational(2), sp.Rational(3), sp.Rational(5)}
    for declaration in declarations:
        for number in re.findall(r"(?<![A-Za-z_])\d+(?:\.\d+)?", declaration):
            try:
                rational = sp.Rational(number)
                values.update((rational - 1, rational, rational + 1, -rational))
            except (ValueError, TypeError):
                pass
    return sorted(values, key=lambda item: (abs(float(item)), float(item)))


def _replace_preserving_operations(expression: Any, assignment: dict[Any, Any]) -> Any:
    """Evaluate bottom-up without SymPy.subs cancelling a denominator first.

    In particular, ordinary substitution turns unevaluated x**2*x**(-1) into 0
    at x=0. Here the original child x**(-1) is evaluated first and becomes zoo,
    so the outer original expression is correctly recorded as undefined.
    """
    if expression.is_Symbol:
        return assignment.get(expression, expression)
    if expression.is_Atom:
        return expression
    args = [_replace_preserving_operations(arg, assignment) for arg in expression.args]
    if expression.is_Add:
        return sp.Add(*args, evaluate=False)
    if expression.is_Mul:
        return sp.Mul(*args, evaluate=False)
    if expression.is_Pow:
        base, exponent = args
        if base == 0 and exponent.is_number and exponent.is_negative is True:
            return sp.zoo
        return sp.Pow(base, exponent, evaluate=False)
    if expression.func == sp.log:
        return sp.log(args[0])
    if expression.func in {sp.exp, sp.sin, sp.cos, sp.tan, sp.Abs}:
        return expression.func(args[0])
    try:
        return expression.func(*args, evaluate=False)
    except TypeError:
        return expression.func(*args)


def _value_at(expression: Any, assignment: dict[Any, Any]) -> tuple[Any, bool, str | None]:
    try:
        value = _replace_preserving_operations(expression, assignment)
        # Test before simplify, since simplify(0*zoo) would erase evidence of the
        # original undefined denominator by returning nan (or another value).
        if value.has(sp.nan, sp.zoo, sp.oo, -sp.oo) or value.is_finite is False:
            return value, False, "undefined or nonfinite"
        value = sp.simplify(value)
        if value.has(sp.nan, sp.zoo, sp.oo, -sp.oo) or value.is_finite is False:
            return value, False, "undefined or nonfinite"
        numeric = sp.N(value, 40)
        if numeric.has(sp.nan, sp.zoo, sp.oo, -sp.oo):
            return value, False, "numerically undefined or nonfinite"
        return value, True, None
    except (TypeError, ValueError, NotImplementedError, ZeroDivisionError, OverflowError) as exc:
        return None, False, f"{type(exc).__name__}: {exc}"


def counterexample_search(
    parser: SafeParser,
    constraints: list[Any],
    lhs: Any,
    rhs: Any,
    limit: int = 2000,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    symbols = sorted(parser.symbols.values(), key=lambda symbol: symbol.name)
    if not symbols:
        return None, {"method": "deterministic_assumption_respecting_rationals", "assignments_tested": 0}
    values = candidate_values(parser.declarations)
    tested = 0
    skipped = 0
    rows = itertools.product(values, repeat=len(symbols))
    for row in itertools.islice(rows, limit):
        assignment = dict(zip(symbols, row))
        satisfaction = [_satisfied(constraint, assignment) for constraint in constraints]
        if any(value is False for value in satisfaction):
            continue
        if any(value is None for value in satisfaction):
            skipped += 1
            continue
        tested += 1
        left, left_defined, left_error = _value_at(lhs, assignment)
        right, right_defined, right_error = _value_at(rhs, assignment)
        if not left_defined and not right_defined:
            continue
        printable_assignment = {symbol.name: str(value) for symbol, value in assignment.items()}
        if left_defined != right_defined:
            return {
                "assignment": printable_assignment,
                "lhs_value": str(left),
                "rhs_value": str(right),
                "reason": f"exactly one side is defined: lhs={left_error or 'defined'}; rhs={right_error or 'defined'}",
            }, {"method": "deterministic_assumption_respecting_rationals", "assignments_tested": tested,
                "assignments_with_undetermined_constraints": skipped}
        try:
            exact_difference = sp.simplify(sp.Add(left, -right, evaluate=False))
            if exact_difference == 0 or exact_difference.is_zero is True:
                continue
        except (TypeError, ValueError, NotImplementedError):
            exact_difference = None
        try:
            residual = complex(sp.N(sp.Add(left, -right, evaluate=False), 50))
            equal = abs(residual) <= 1e-24 * max(1.0, abs(complex(sp.N(left, 40))), abs(complex(sp.N(right, 40))))
        except (TypeError, ValueError, NotImplementedError, OverflowError):
            # Exact inequality is accepted only when both values are distinct and
            # exactly comparable; a Boolean False alone is not a counterexample.
            equal_relation = sp.Eq(left, right)
            if equal_relation is sp.true:
                equal = True
            elif equal_relation is sp.false and left.is_number is True and right.is_number is True:
                equal = False
            else:
                continue
        if not equal:
            return {
                "assignment": printable_assignment,
                "lhs_value": str(left),
                "rhs_value": str(right),
                "reason": "concrete values differ under the declared assumptions",
            }, {"method": "deterministic_assumption_respecting_rationals", "assignments_tested": tested,
                "assignments_with_undetermined_constraints": skipped}
    return None, {"method": "deterministic_assumption_respecting_rationals", "assignments_tested": tested,
                  "assignments_with_undetermined_constraints": skipped, "search_bounded": True}


def dependency_errors(steps: list[Any]) -> dict[int, list[str]]:
    errors: dict[int, list[str]] = {index: [] for index in range(len(steps))}
    id_indices: dict[str, list[int]] = {}
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            errors[index].append("step must be an object")
            continue
        step_id = step.get("id")
        if not isinstance(step_id, str) or not step_id:
            errors[index].append("id must be a nonempty string")
        else:
            id_indices.setdefault(step_id, []).append(index)
        dependencies = step.get("dependencies")
        if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
            errors[index].append("dependencies must be an array of step IDs")
    for indices in id_indices.values():
        if len(indices) > 1:
            for index in indices:
                errors[index].append("duplicate step id")
    known = set(id_indices)
    graph: dict[int, list[int]] = {}
    for index, step in enumerate(steps):
        if not isinstance(step, dict) or not isinstance(step.get("dependencies"), list):
            graph[index] = []
            continue
        graph[index] = []
        for dependency in step["dependencies"]:
            if dependency not in known:
                errors[index].append(f"unknown dependency: {dependency}")
                continue
            if len(id_indices[dependency]) == 1:
                graph[index].append(id_indices[dependency][0])
    state: dict[int, int] = {}

    def visit(index: int) -> None:
        if state.get(index) == 1:
            return
        if state.get(index) == 2:
            return
        state[index] = 1
        for dependency in graph.get(index, []):
            if state.get(dependency) == 1:
                errors[index].append("dependency cycle detected")
                errors[dependency].append("dependency cycle detected")
            else:
                visit(dependency)
        state[index] = 2

    for index in range(len(steps)):
        visit(index)
    return errors


def validate_step(step: Any) -> list[str]:
    if not isinstance(step, dict):
        return ["step must be an object"]
    errors: list[str] = []
    required_strings = ("justification", "source_locator")
    for field in required_strings:
        if not isinstance(step.get(field), str) or not step.get(field).strip():
            errors.append(f"{field} must be a nonempty string")
    if not isinstance(step.get("id"), str) or not step.get("id"):
        errors.append("id must be a nonempty string")
    if not any(field in step for field in ("lhs", "source")):
        errors.append("lhs/source expression is required")
    if not any(field in step for field in ("rhs", "target")):
        errors.append("rhs/target expression is required")
    if step.get("operation") not in OPERATIONS:
        errors.append(f"unknown operation: {step.get('operation')!r}")
    if step.get("origin") not in ORIGINS:
        errors.append(f"origin must be one of {', '.join(ORIGINS)}")
    for field in ("assumptions", "domain"):
        if field not in step:
            errors.append(f"{field} declaration field is required (use [] when none)")
    if not isinstance(step.get("required", True), bool):
        errors.append("required must be Boolean")
    return errors


def base_step_result(step: Any, index: int) -> dict[str, Any]:
    if not isinstance(step, dict):
        return {"index": index, "id": f"step[{index}]", "origin": "unknown", "required": True}
    return {
        "index": index,
        "id": step.get("id", f"step[{index}]"),
        "origin": step.get("origin", "unknown"),
        "operation": step.get("operation"),
        "justification": step.get("justification"),
        "source_locator": step.get("source_locator"),
        "assumptions": step.get("assumptions"),
        "domain": step.get("domain"),
        "dependencies": step.get("dependencies"),
        "required": step.get("required", True),
        "lhs": step.get("lhs", step.get("source")),
        "rhs": step.get("rhs", step.get("target")),
    }


def verify_step(step: Any, index: int, structural_errors: list[str]) -> dict[str, Any]:
    result = base_step_result(step, index)
    errors = validate_step(step) + structural_errors
    result["domain_errors"] = []
    result["assumption_errors"] = []
    result["counterexample"] = None
    result["symbolic_checks"] = []
    if errors:
        result.update(status="invalid_operation", explanation="; ".join(errors))
        return result
    try:
        declarations = declarations_for_step(step)
    except ExpressionError as exc:
        result.update(status="invalid_operation", explanation=str(exc))
        return result
    result["normalized_assumptions"] = declarations
    parser = SafeParser(declarations)
    try:
        lhs = parser.parse(step.get("lhs", step.get("source")))
        rhs = parser.parse(step.get("rhs", step.get("target")))
        nonzero_factors, factor_notes = explicit_nonzero_factors(step, parser)
    except (ExpressionError, TypeError, ValueError) as exc:
        result.update(status="invalid_operation", explanation=str(exc))
        return result
    constraints: list[Any] = []
    assumption_errors: list[str] = []
    for declaration in declarations:
        if re.fullmatch(
            r"\s*[A-Za-z_]\w*\s+(?:(?:real|positive|negative|nonnegative|nonpositive|nonzero|integer)\s*)+",
            declaration,
        ):
            # Property sequences were applied to symbols; any remaining words are
            # parsed one at a time only to enforce the closed vocabulary.
            match_name = re.match(r"\s*([A-Za-z_]\w*)\s+(.+)", declaration)
            words = match_name.group(2).split() if match_name else []
            unknown = [word for word in words if word not in PROPERTY_WORDS]
            if unknown:
                assumption_errors.append(f"unknown property words in {declaration!r}: {unknown}")
            continue
        try:
            constraints.append(parser.comparison(declaration))
        except ExpressionError as exc:
            assumption_errors.append(str(exc))
    result["assumption_errors"] = assumption_errors
    result["declared_nonzero_factors"] = factor_notes
    result["domain_errors"] = domain_audit(step, (lhs, rhs), nonzero_factors)
    equal, symbolic_notes = symbolic_zero(lhs, rhs)
    result["symbolic_checks"] = symbolic_notes
    counterexample: dict[str, Any] | None = None
    sampling: dict[str, Any] = {"method": "not needed after symbolic proof", "assignments_tested": 0}
    # Counterexample search is mandatory after inconclusive simplification and is
    # also run after a domain-flagged proof to expose illegal cancellation.
    if not equal or result["domain_errors"] or assumption_errors:
        counterexample, sampling = counterexample_search(parser, constraints, lhs, rhs)
    result["sampling"] = sampling
    result["counterexample"] = counterexample
    if counterexample is not None:
        verdict = "falsified"
        explanation = "Concrete assumption-respecting counterexample found; numeric sampling was used only to falsify."
    elif assumption_errors:
        verdict = "undetermined"
        explanation = "Some assumptions could not be parsed or decided: " + "; ".join(assumption_errors)
    elif result["domain_errors"]:
        verdict = "missing_license"
        explanation = "Domain/side-condition licenses are incomplete: " + "; ".join(result["domain_errors"])
    elif equal:
        verdict = "symbolic_equal"
        explanation = "SymPy proved lhs-rhs = 0 and all original-expression domain licenses hold. No numeric proof was used."
    else:
        verdict = "undetermined"
        explanation = "Symbolic simplification was inconclusive and bounded assumption-respecting sampling found no counterexample. Numeric agreement is not proof."
    result.update(status=verdict, explanation=explanation)
    return result


def unavailable_certificate(derivation: Any, reason: str) -> dict[str, Any]:
    steps = derivation.get("steps", []) if isinstance(derivation, dict) else []
    results = []
    if isinstance(steps, list):
        for index, step in enumerate(steps):
            item = base_step_result(step, index)
            item.update(
                status="undetermined",
                explanation=f"SymPy unavailable; no mathematical check attempted: {reason}",
                assumptions=step.get("assumptions") if isinstance(step, dict) else None,
                domain=step.get("domain") if isinstance(step, dict) else None,
                domain_errors=[],
                assumption_errors=[],
                counterexample=None,
                symbolic_checks=[],
            )
            results.append(item)
    return {
        "schema_version": SCHEMA_VERSION,
        "overall_status": "unavailable",
        "success": False,
        "sympy_available": False,
        "sympy_error": reason,
        "case_id": derivation.get("case_id") if isinstance(derivation, dict) else None,
        "paper": derivation.get("paper") if isinstance(derivation, dict) else None,
        "source_status": derivation.get("status") if isinstance(derivation, dict) else "invalid",
        "step_count": len(results),
        "required_step_count": sum(1 for item in results if item.get("required", True)),
        "steps": results,
    }


def summarize_certificate(certificate: dict[str, Any]) -> str:
    counts = {verdict: 0 for verdict in STEP_VERDICTS}
    for step in certificate.get("steps", []):
        verdict = step.get("status")
        if verdict in counts:
            counts[verdict] += 1
    detail = ", ".join(f"{name}={count}" for name, count in counts.items())
    return f"overall={certificate.get('overall_status', 'undetermined')}; {detail}; {certificate.get('step_count', 0)} total steps"


def check_derivation(derivation: Any, simulate_no_sympy: bool = False) -> dict[str, Any]:
    if sp is None or simulate_no_sympy:
        reason = "simulated by --simulate-no-sympy" if simulate_no_sympy else (SYMPY_IMPORT_ERROR or "import failed")
        return unavailable_certificate(derivation, reason)
    certificate: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "overall_status": "undetermined",
        "success": False,
        "sympy_available": True,
        "sympy_version": sp.__version__,
        "case_id": derivation.get("case_id") if isinstance(derivation, dict) else None,
        "paper": derivation.get("paper") if isinstance(derivation, dict) else None,
        "source_status": derivation.get("status") if isinstance(derivation, dict) else "invalid",
        "steps": [],
        "structural_errors": [],
    }
    if not isinstance(derivation, dict) or not isinstance(derivation.get("steps"), list):
        certificate["structural_errors"].append("derivation must be an object with a steps array")
        certificate["step_count"] = 0
        certificate["required_step_count"] = 0
        return certificate
    steps = derivation["steps"]
    structural = dependency_errors(steps)
    certificate["steps"] = [verify_step(step, index, structural[index]) for index, step in enumerate(steps)]
    certificate["step_count"] = len(steps)
    required = [step for step in certificate["steps"] if step.get("required", True)]
    certificate["required_step_count"] = len(required)
    if not steps or derivation.get("status") == "insufficient_evidence":
        certificate["overall_status"] = "undetermined"
        certificate["structural_errors"].append(
            "No certifiable transitions; missing formula evidence is insufficient, never a vacuous pass."
        )
    elif not required:
        certificate["overall_status"] = "undetermined"
        certificate["structural_errors"].append("No required steps means there is no required derivation to certify.")
    elif any(step["status"] == "falsified" for step in required):
        certificate["overall_status"] = "falsified"
    elif any(step["status"] == "invalid_operation" for step in required):
        certificate["overall_status"] = "invalid_operation"
    elif any(step["status"] == "missing_license" for step in required):
        certificate["overall_status"] = "missing_license"
    elif any(step["status"] == "undetermined" for step in required):
        certificate["overall_status"] = "undetermined"
    elif all(step["status"] == "symbolic_equal" for step in required):
        certificate["overall_status"] = "symbolic_equal"
        certificate["success"] = True
    certificate["certificate_summary"] = summarize_certificate(certificate)
    return certificate


def markdown_certificate(certificate: dict[str, Any]) -> str:
    lines = [
        "# Algebraic derivation certificate",
        "",
        f"**Overall:** `{certificate.get('overall_status', 'undetermined')}`  ",
        f"**SymPy available:** `{certificate.get('sympy_available', False)}`  ",
        "**Numeric sampling can falsify only; it is never a proof.**",
        "",
    ]
    if certificate.get("sympy_error"):
        lines.extend([f"Unavailable dependency: `{certificate['sympy_error']}`", ""])
    errors = certificate.get("structural_errors", [])
    if errors:
        lines.extend(["## Structural notes", ""] + [f"- {item}" for item in errors] + [""])
    for origin, title in (
        ("paper_explicit", "Paper-explicit transitions"),
        ("reader_reconstruction", "Reader-reconstructed transitions"),
        ("unknown", "Unclassified transitions"),
    ):
        selected = [step for step in certificate.get("steps", []) if step.get("origin") == origin]
        lines.extend([f"## {title}", ""])
        if not selected:
            lines.extend(["None.", ""])
            continue
        for step in selected:
            lines.extend([
                f"### {step.get('id')}: `{step.get('status')}`",
                "",
                f"- Operation: `{step.get('operation')}`",
                f"- Source locator: {step.get('source_locator')}",
                f"- Dependencies: `{step.get('dependencies')}`",
                f"- Required: `{step.get('required', True)}`",
                f"- LHS/source: `{step.get('lhs')}`",
                f"- RHS/target: `{step.get('rhs')}`",
                f"- Justification: {step.get('justification')}",
                f"- Declared assumptions: `{step.get('normalized_assumptions', step.get('assumptions'))}`",
                f"- Domain declarations: `{step.get('domain')}`",
                f"- Explanation: {step.get('explanation')}",
            ])
            for item in step.get("domain_errors", []):
                lines.append(f"- **Domain error:** {item}")
            for item in step.get("assumption_errors", []):
                lines.append(f"- **Assumption error:** {item}")
            if step.get("symbolic_checks"):
                lines.append("- Symbolic checks:")
                lines.extend(f"    - {note}" for note in step["symbolic_checks"])
            if step.get("sampling"):
                lines.append(f"- Sampling: `{step['sampling']}`")
            if step.get("counterexample"):
                lines.append(f"- **Counterexample:** `{step['counterexample']}`")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# -------------------------- dynamic output contract --------------------------


def _walk_json_objects(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json_objects(child)


def read_output_contract(task_path: Path) -> dict[str, Any]:
    text = task_path.read_text(encoding="utf-8")
    candidates: list[Any] = []
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            value, _ = decoder.raw_decode(text[match.start():])
            candidates.append(value)
        except json.JSONDecodeError:
            continue
    for candidate in candidates:
        for item in _walk_json_objects(candidate):
            contract = item.get("output_contract")
            if isinstance(contract, dict):
                return normalize_contract(contract)
            if "required_fields" in item and "status_enum" in item:
                return normalize_contract(item)
    # Last-resort extraction for a contract whose JSON values occur separately.
    contract: dict[str, Any] = {}
    for key in ("required_fields", "status_enum"):
        match = re.search(rf'[\"\']{key}[\"\']\s*:\s*(\[[^\]]*\])', text)
        if match:
            try:
                contract[key] = json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
    match = re.search(r'[\"\']field_types[\"\']\s*:\s*(\{.*?\})', text, re.DOTALL)
    if match:
        try:
            contract["field_types"] = json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    if "required_fields" in contract:
        return normalize_contract(contract)
    return normalize_contract({})


def normalize_contract(contract: dict[str, Any]) -> dict[str, Any]:
    required = contract.get("required_fields", ["status"])
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        raise ValueError("output_contract.required_fields must be an array of strings")
    required = list(dict.fromkeys(required))
    field_types = contract.get("field_types", {})
    if not isinstance(field_types, dict):
        raise ValueError("output_contract.field_types must be an object")
    statuses = contract.get("status_enum", ["success", "partial", "failed"])
    if not isinstance(statuses, list) or not statuses or not all(isinstance(item, str) for item in statuses):
        raise ValueError("output_contract.status_enum must be a nonempty string array")
    if "status" not in required:
        # The runtime demands status_enum compliance without adding contract-outside
        # fields. Most tasks require status explicitly; otherwise no status is added.
        pass
    return {"required_fields": required, "field_types": field_types, "status_enum": statuses}


def discover_case_id(input_dir: Path, task_path: Path, answers: Any = None) -> str:
    for filename in ("case.json", "input.json", "task.json", "metadata.json"):
        path = input_dir / filename
        if path.is_file():
            try:
                value = json_load(path)
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(value, dict) and isinstance(value.get("case_id"), (str, int)):
                return str(value["case_id"])
    text = task_path.read_text(encoding="utf-8")
    match = re.search(r'["\']?case_id["\']?\s*[:=]\s*["\']([^"\'\n]+)["\']', text)
    if match:
        return match.group(1)
    match = re.search(r"\bcase[_ -]?id\s*(?:is|:)\s*`?([A-Za-z0-9_.:-]+)", text, re.IGNORECASE)
    if match:
        return match.group(1)
    if isinstance(answers, dict) and isinstance(answers.get("case_id"), (str, int)):
        return str(answers["case_id"])
    return "unknown_case"


def expected_type(raw: Any) -> Any:
    if isinstance(raw, dict):
        raw = raw.get("type", "string")
    if isinstance(raw, list):
        return raw
    aliases = {"str": "string", "list": "array", "dict": "object", "int": "integer", "float": "number", "bool": "boolean"}
    return aliases.get(raw, raw if isinstance(raw, str) else "string")


def type_accepts(raw: Any, value: Any) -> bool:
    types = expected_type(raw)
    if not isinstance(types, list):
        types = [types]
    return any(_single_type_accepts(item, value) for item in types)


def _single_type_accepts(kind: str, value: Any) -> bool:
    if kind == "string":
        return isinstance(value, str)
    if kind == "array":
        return isinstance(value, list)
    if kind == "object":
        return isinstance(value, dict)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    if kind == "null":
        return value is None
    return False


def coerce_value(raw_type: Any, value: Any) -> Any | None:
    if type_accepts(raw_type, value):
        return value
    types = expected_type(raw_type)
    if not isinstance(types, list):
        types = [types]
    for kind in types:
        try:
            if kind == "string" and isinstance(value, (str, int, float)) and not isinstance(value, bool):
                return str(value)
            if kind == "integer" and isinstance(value, float) and value.is_integer() and math.isfinite(value):
                return int(value)
        except (ValueError, TypeError, OverflowError):
            pass
    return None


def placeholder(raw_type: Any, final: bool) -> Any:
    types = expected_type(raw_type)
    if isinstance(types, list) and "null" in types:
        return None
    kind = types[0] if isinstance(types, list) else types
    if kind == "string":
        return "insufficient evidence: required agent-authored value missing" if final else "insufficient evidence: analysis incomplete"
    if kind == "array":
        return []
    if kind == "object":
        return {}
    if kind == "number" or kind == "integer":
        return 0
    if kind == "boolean":
        return False
    if kind == "null":
        return None
    return "insufficient evidence: analysis incomplete"


def select_status(statuses: list[str], desired: str) -> str:
    candidates = {
        "success": ("success", "completed", "complete", "passed", "pass", "ok"),
        "partial": ("partial", "incomplete", "undetermined", "needs_review", "pending", "unavailable"),
        "failed": ("failed", "failure", "falsified", "invalid", "error"),
    }[desired]
    lowered = {status.lower(): status for status in statuses}
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    if desired == "partial":
        # Prefer any non-success/non-failure member for unknown custom vocabularies.
        for status in statuses:
            low = status.lower()
            if low not in {"success", "passed", "complete", "completed", "failed", "failure"}:
                return status
        return statuses[-1]
    if desired == "success":
        return statuses[0]
    return statuses[-1]


def answer_for_field(answers: dict[str, Any], field: str) -> tuple[bool, Any]:
    fields = answers.get("fields") if isinstance(answers.get("fields"), dict) else {}
    if field in answers:
        return True, answers[field]
    if field in fields:
        return True, fields[field]
    aliases = {
        "final_answer": ("answer",),
        "conclusion": ("answer",),
        "answer": ("final_answer", "conclusion"),
        "derivation_summary": ("derivation", "derivation_answer"),
        "derivation_answer": ("derivation", "derivation_summary"),
        "certificate_summary": ("certificate_answer",),
        "certificate_answer": ("certificate_summary",),
    }
    for source in aliases.get(field, ()):
        if source in answers:
            return True, answers[source]
        if source in fields:
            return True, fields[source]
    return False, None


def initialize_result(task_path: Path, input_dir: Path, output_path: Path, case_id: str | None = None) -> dict[str, Any]:
    contract = read_output_contract(task_path)
    fields = contract["required_fields"]
    result: dict[str, Any] = {"case_id": case_id or discover_case_id(input_dir, task_path)}
    for field in fields:
        if field == "case_id":
            continue
        raw_type = contract["field_types"].get(field, "string")
        if field == "status":
            result[field] = select_status(contract["status_enum"], "partial")
        else:
            result[field] = placeholder(raw_type, final=False)
    json_dump(output_path, result)
    return result


def finalize_result(
    task_path: Path,
    input_dir: Path,
    answers_path: Path,
    certificate_path: Path,
    derivation_md_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    # Always leave a fresh, typed partial before loading later evidence.
    initialize_result(task_path, input_dir, output_path)
    contract = read_output_contract(task_path)
    answers_valid = True
    try:
        answers = json_load(answers_path)
        if not isinstance(answers, dict):
            answers_valid = False
            answers = {}
    except (OSError, json.JSONDecodeError):
        answers_valid = False
        answers = {}
    try:
        certificate = json_load(certificate_path)
        if not isinstance(certificate, dict):
            certificate = {"overall_status": "undetermined", "steps": []}
    except (OSError, json.JSONDecodeError):
        certificate = {"overall_status": "undetermined", "steps": []}
    markdown = ""
    try:
        markdown = derivation_md_path.read_text(encoding="utf-8")
    except OSError:
        pass
    required_steps = [step for step in certificate.get("steps", []) if isinstance(step, dict) and step.get("required", True)]
    certificate_complete = (
        certificate.get("overall_status") == "symbolic_equal"
        and certificate.get("success") is True
        and bool(required_steps)
        and all(step.get("status") == "symbolic_equal" for step in required_steps)
    )
    result: dict[str, Any] = {"case_id": discover_case_id(input_dir, task_path, answers)}
    values_complete = True
    for field in contract["required_fields"]:
        if field == "case_id":
            continue
        raw_type = contract["field_types"].get(field, "string")
        if field == "status":
            continue
        if field in {"certificate", "certificate_json", "derivation_certificate"}:
            value = certificate
            found = True
        elif field == "certificate_summary":
            # Certificate result is authoritative even if an answer made a claim.
            value = summarize_certificate(certificate)
            found = True
        elif field in {"derivation_md", "derivation_markdown"}:
            value = markdown
            found = bool(markdown)
        else:
            found, value = answer_for_field(answers, field)
            if not found and field in {"derivation", "derivation_summary"} and markdown:
                value, found = markdown, True
        coerced = coerce_value(raw_type, value) if found else None
        if coerced is None:
            result[field] = placeholder(raw_type, final=True)
            values_complete = False
        else:
            result[field] = coerced
            if isinstance(coerced, str) and coerced.startswith("insufficient evidence:"):
                values_complete = False
    success = certificate_complete and answers_valid and values_complete
    if success:
        desired = "success"
    elif certificate.get("overall_status") in {"falsified", "invalid_operation"}:
        desired = "failed"
    else:
        desired = "partial"
    if "status" in contract["required_fields"]:
        result["status"] = select_status(contract["status_enum"], desired)
    # Restore required-field order while always keeping case_id as requested.
    ordered = {"case_id": result["case_id"]}
    for field in contract["required_fields"]:
        if field != "case_id":
            ordered[field] = result[field]
    json_dump(output_path, ordered)
    return ordered


def command_check(args: argparse.Namespace) -> int:
    derivation_path = Path(args.derivation)
    certificate_path = Path(args.certificate)
    markdown_path = Path(args.derivation_md)
    try:
        derivation = json_load(derivation_path)
        certificate = check_derivation(derivation, args.simulate_no_sympy)
    except (OSError, json.JSONDecodeError) as exc:
        certificate = {
            "schema_version": SCHEMA_VERSION,
            "overall_status": "invalid_operation",
            "success": False,
            "sympy_available": sp is not None and not args.simulate_no_sympy,
            "structural_errors": [f"Cannot load derivation: {type(exc).__name__}: {exc}"],
            "steps": [],
            "step_count": 0,
            "required_step_count": 0,
        }
    certificate.setdefault("certificate_summary", summarize_certificate(certificate))
    json_dump(certificate_path, certificate)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(markdown_certificate(certificate), encoding="utf-8")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="check an agent-authored derivation")
    check.add_argument("--derivation", required=True)
    check.add_argument("--certificate", required=True)
    check.add_argument("--derivation-md", required=True)
    check.add_argument("--simulate-no-sympy", action="store_true", help="exercise graceful unavailable handling")
    check.set_defaults(function=command_check)

    initial = subparsers.add_parser("init-result", help="write an early typed partial result")
    initial.add_argument("--task", required=True)
    initial.add_argument("--input-dir", required=True)
    initial.add_argument("--output", required=True)
    initial.add_argument("--case-id")
    initial.set_defaults(function=lambda args: (
        initialize_result(Path(args.task), Path(args.input_dir), Path(args.output), args.case_id), 0
    )[1])

    final = subparsers.add_parser("finalize", help="map authored answers and certificate into output contract")
    final.add_argument("--task", required=True)
    final.add_argument("--input-dir", required=True)
    final.add_argument("--answers", required=True)
    final.add_argument("--certificate", required=True)
    final.add_argument("--derivation-md", required=True)
    final.add_argument("--output", required=True)
    final.set_defaults(function=lambda args: (
        finalize_result(Path(args.task), Path(args.input_dir), Path(args.answers), Path(args.certificate),
                        Path(args.derivation_md), Path(args.output)), 0
    )[1])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.function(args))


if __name__ == "__main__":
    raise SystemExit(main())
