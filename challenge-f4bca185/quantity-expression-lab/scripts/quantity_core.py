#!/usr/bin/env python3
"""Typed quantity-expression compiler. Python 3 standard library only.

Raw text is tokenized, parsed into a quantity shape and a unit expression tree,
then converted with Decimal arithmetic. This module performs no I/O.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from typing import Any, Dict, List, Optional, Sequence, Tuple

D = Decimal


class QuantityError(ValueError):
    """A safe, machine-readable rejection; never silently repairs input."""

    def __init__(self, code: str, message: str, position: Optional[int] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.position = position


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    position: int
    value: Optional[Decimal] = None


@dataclass(frozen=True)
class NumberConvention:
    region: str = "auto"
    decimal_separator: Optional[str] = None
    thousands_separator: Optional[str] = None

    @classmethod
    def from_spec(cls, spec: Optional[Dict[str, Any]]) -> "NumberConvention":
        if not isinstance(spec, dict):
            return cls()
        region = spec.get("number_region", spec.get("numberRegion",
                    spec.get("numeric_locale", spec.get("locale", "auto"))))
        dec = spec.get("decimal_separator", spec.get("decimalSeparator"))
        group = spec.get("thousands_separator", spec.get("group_separator",
                    spec.get("thousandsSeparator")))
        return cls(str(region or "auto"), str(dec) if dec else None,
                   str(group) if group else None)


def _region_rules(region: str) -> Tuple[Optional[str], Optional[str]]:
    r = region.strip().lower().replace("_", "-")
    if r in ("", "auto", "unspecified", "c"):
        return None, None
    if r in ("decimal-dot", "dot", "en-dot"):
        return ".", None
    if r in ("decimal-comma", "comma"):
        return ",", None
    if r.startswith(("en", "us", "gb", "zh", "ja")) or r in ("us", "uk"):
        return ".", ","
    if r.startswith(("de", "es", "it", "pt", "nl", "da", "el", "tr")):
        return ",", "."
    if r.startswith(("fr", "ru", "sv", "nb", "nn", "fi", "pl", "cs")):
        return ",", "\u00a0"
    raise QuantityError("unknown_number_region",
                        "Number region %r is not registered; use explicit separators." % region)


def _digits(text: str) -> bool:
    return bool(text) and all("0" <= c <= "9" for c in text)


def _valid_grouped_integer(text: str, separator: str) -> bool:
    groups = text.split(separator)
    return (len(groups) >= 2 and 1 <= len(groups[0]) <= 3 and
            _digits(groups[0]) and all(len(g) == 3 and _digits(g) for g in groups[1:]))


def parse_number(text: str, convention: Optional[NumberConvention] = None) -> Decimal:
    """Parse one captured numeric token, rejecting ambiguous/grouping damage."""
    convention = convention or NumberConvention()
    original = text
    text = text.replace("−", "-").replace("＋", "+")
    sign = ""
    if text[:1] in ("+", "-"):
        sign, text = text[0], text[1:]
    if not text or len(text) > 4096:
        raise QuantityError("invalid_number", "Empty or oversized numeric token.")
    exponent = ""
    e_positions = [i for i, c in enumerate(text) if c in "eE"]
    if e_positions:
        if len(e_positions) != 1:
            raise QuantityError("invalid_scientific_notation", "More than one exponent marker: " + original)
        i = e_positions[0]
        text, exponent = text[:i], text[i:]
        exp_digits = exponent[1:]
        if exp_digits[:1] in ("+", "-"):
            exp_digits = exp_digits[1:]
        if not _digits(exp_digits) or len(exp_digits) > 5:
            raise QuantityError("invalid_scientific_notation",
                                "Exponent must be a signed integer of at most five digits: " + original)
    dec, group = convention.decimal_separator, convention.thousands_separator
    auto_dec, auto_group = _region_rules(convention.region)
    dec = dec if dec is not None else auto_dec
    group = group if group is not None else auto_group
    if dec == group and dec is not None:
        raise QuantityError("invalid_number_convention", "Decimal and thousands separators must differ.")
    grouping_chars = {"\u00a0", "\u202f", "'", "’"}
    if group:
        grouping_chars.add(group)
    # Explicit separators define the reading, but malformed grouping still fails.
    if dec or group:
        dec = dec or ("." if "," not in text else ",")
        mantissa = text
        if dec in mantissa:
            if mantissa.count(dec) != 1:
                raise QuantityError("invalid_decimal", "Repeated decimal separator: " + original)
            integer, fraction = mantissa.split(dec)
            if not _digits(fraction):
                raise QuantityError("invalid_decimal", "Decimal fraction must contain digits: " + original)
        else:
            integer, fraction = mantissa, ""
        present_groups = [g for g in grouping_chars if g in integer]
        if len(present_groups) > 1:
            raise QuantityError("ambiguous_grouping", "Mixed thousands separators: " + original)
        if present_groups:
            g = present_groups[0]
            if group and g != group:
                raise QuantityError("invalid_grouping", "Separator conflicts with the supplied region: " + original)
            if not _valid_grouped_integer(integer, g):
                raise QuantityError("invalid_grouping", "Thousands groups must be 1-3 digits then groups of three: " + original)
            integer = integer.replace(g, "")
        if integer and not _digits(integer):
            raise QuantityError("invalid_number", "Unexpected character in integer part: " + original)
        if not integer and not fraction:
            raise QuantityError("invalid_number", "No digits in numeric token: " + original)
        normalized = sign + (integer or "0") + ("." + fraction if fraction else "") + exponent
        try:
            return Decimal(normalized)
        except InvalidOperation:
            raise QuantityError("invalid_number", "Not a Decimal number: " + original)

    # Auto mode: rightmost of two distinct separators is decimal.
    dots, commas = text.count("."), text.count(",")
    if dots and commas:
        dec = "." if text.rfind(".") > text.rfind(",") else ","
        group = "," if dec == "." else "."
        left, right = text.rsplit(dec, 1)
        if not _valid_grouped_integer(left.replace(sign, ""), group) or not _digits(right):
            raise QuantityError("ambiguous_decimal", "Mixed separators have inconsistent grouping: " + original)
        return Decimal(sign + left.replace(group, "") + "." + right + exponent)

    # NBSP/thin-space/apostrophe are unambiguously grouping, never decimals.
    present = [g for g in grouping_chars if g in text]
    if len(present) > 1:
        raise QuantityError("ambiguous_grouping", "Mixed thousands separators: " + original)
    if present:
        g = present[0]
        if not _valid_grouped_integer(text, g):
            raise QuantityError("invalid_grouping", "Malformed thousands groups: " + original)
        text = text.replace(g, "")

    sep = "." if dots else ("," if commas else None)
    if sep:
        n = text.count(sep)
        parts = text.split(sep)
        if n > 1:
            if _valid_grouped_integer(text, sep):
                text = text.replace(sep, "")
            else:
                raise QuantityError("ambiguous_decimal",
                                    "Repeated separator is neither valid grouping nor one decimal: " + original)
        else:
            left, right = parts
            # Leading zero and leading separator always indicate a decimal.
            if left in ("", "0") or len(right) != 3:
                if (left and not _digits(left)) or not _digits(right):
                    raise QuantityError("invalid_number", "Malformed decimal token: " + original)
                text = (left or "0") + "." + right
            else:
                raise QuantityError("ambiguous_decimal",
                                    "A separator before exactly three digits is ambiguous without a region: " + original)
    valid_plain_decimal = (text.count(".") == 1 and
                           all(_digits(part) for part in text.split(".")))
    if not (_digits(text) or valid_plain_decimal):
        raise QuantityError("invalid_number", "Malformed numeric token: " + original)
    try:
        return Decimal(sign + text + exponent)
    except InvalidOperation:
        raise QuantityError("invalid_number", "Not a Decimal number: " + original)


_NUMBER_START = set("0123456789.,")
_GROUPING = set("\u00a0\u202f'’")
_APPROX = set("~≈≃∼")
_RANGE = set("–—")
_SUPERSCRIPTS = {"⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
                 "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9", "⁻": "-", "⁺": "+"}


class Lexer:
    """Small stateful scanner; numeric signs depend on parser position."""

    def __init__(self, text: str, convention: NumberConvention):
        self.text = text
        self.convention = convention
        self.tokens: List[Token] = []

    def _expects_number(self) -> bool:
        if not self.tokens:
            return True
        last = self.tokens[-1]
        return last.kind in ("RANGE", "PM", "APPROX") or last.text == "^"

    def _number(self, i: int) -> int:
        s = self.text
        n = len(s)
        start = i
        if s[i] in "+-−" and self._expects_number():
            i += 1
        # Find mantissa characters. e/E is consumed only for a valid exponent shape.
        while i < n and ((s[i].isascii() and s[i].isdigit()) or s[i] in ".,_"):
            i += 1
        while i < n and s[i] in _GROUPING:
            # Grouping characters belong to a number only between numeric mantissa characters.
            if i + 1 < n and s[i + 1].isdigit() and i > start:
                i += 1
                while i < n and s[i].isdigit():
                    i += 1
            else:
                break
        if i < n and s[i] in "eE":
            j = i + 1
            if j < n and s[j] in "+-−":
                j += 1
            k = j
            while k < n and s[k].isdigit():
                k += 1
            if k > j:
                i = k
        raw = s[start:i]
        if raw in ("", "+", "-", "−"):
            raise QuantityError("invalid_number", "Sign without a number.", start)
        value = parse_number(raw, self.convention)
        self.tokens.append(Token("NUMBER", raw, start, value))
        return i

    def scan(self) -> List[Token]:
        s = self.text
        n = len(s)
        i = 0
        while i < n:
            c = s[i]
            if c.isspace():
                i += 1
                continue
            if len(s) > 16384:
                raise QuantityError("expression_too_long", "Quantity expression exceeds 16384 characters.", i)
            if c in _APPROX:
                self.tokens.append(Token("APPROX", c, i)); i += 1; continue
            if c in "+−-" and self._expects_number():
                i = self._number(i); continue
            if c in _NUMBER_START:
                i = self._number(i); continue
            if c == "±" or s.startswith("+/-", i) or s.startswith("+／-", i):
                width = 1 if c == "±" else 3
                self.tokens.append(Token("PM", s[i:i + width], i)); i += width; continue
            if c in _RANGE or c in "-−":
                self.tokens.append(Token("RANGE", c, i)); i += 1; continue
            if c in "*·⋅×/^()":
                self.tokens.append(Token(c, c, i)); i += 1; continue
            if c in _SUPERSCRIPTS:
                start = i; out = []
                while i < n and s[i] in _SUPERSCRIPTS:
                    out.append(_SUPERSCRIPTS[s[i]]); i += 1
                self.tokens.append(Token("EXPONENT", "".join(out), start)); continue
            if c == "_" or unicodedata.category(c).startswith("L") or c in "°%℃℉":
                start = i; i += 1
                while i < n and (s[i] == "_" or unicodedata.category(s[i]).startswith("L") or s[i] in "°%℃℉"):
                    i += 1
                word = s[start:i]
                kind = "TO" if word.lower() == "to" and self.tokens and self.tokens[-1].kind == "NUMBER" else "ATOM"
                self.tokens.append(Token(kind, word, start)); continue
            raise QuantityError("unexpected_character", "Unexpected character %r." % c, i)
        self.tokens.append(Token("EOF", "", n))
        return self.tokens


# Dimensions are symbolic exponent vectors; units never become identity labels.
# scale is the linear multiplier to the canonical SI realization. offset is used
# only by standalone temperature atoms: base = source * scale + offset.
@dataclass(frozen=True)
class UnitFactor:
    symbol: str
    dimension: Dict[str, int]
    scale: Decimal = D(1)
    offset: Decimal = D(0)
    affine: bool = False


_UNIT_TABLE: Dict[str, UnitFactor] = {}


def _unit(symbol: str, dimension: Dict[str, int], scale: str = "1", offset: str = "0",
          affine: bool = False, aliases: Sequence[str] = (), prefixable: bool = False) -> None:
    item = UnitFactor(symbol, dimension, D(scale), D(offset), affine)
    _UNIT_TABLE[symbol] = item
    for alias in aliases:
        _UNIT_TABLE[alias] = item
    if prefixable:
        _PREFIXABLE.add(symbol)


_PREFIXABLE = set()
_PREFIXES = {
    "n": "1e-9", "µ": "1e-6", "u": "1e-6", "μ": "1e-6", "m": "1e-3",
    "c": "1e-2", "d": "1e-1", "da": "1e1", "h": "1e2", "k": "1e3",
    "M": "1e6", "G": "1e9", "T": "1e12",
}
_unit("s", {"time": 1}, aliases=("sec", "second", "seconds"), prefixable=True)
_unit("min", {"time": 1}, "60", aliases=("minute", "minutes"))
_unit("h", {"time": 1}, "3600", aliases=("hr", "hour", "hours"))
_unit("day", {"time": 1}, "86400", aliases=("d",))
_unit("K", {"temperature": 1}, prefixable=False)
_unit("°C", {"temperature": 1}, "1", "273.15", True,
      aliases=("℃", "degC", "Celsius", "celsius"))
with localcontext() as ctx:
    ctx.prec = 60
    _unit("°F", {"temperature": 1}, str(D(5) / D(9)),
          str(D("459.67") * D(5) / D(9)), True, aliases=("℉", "degF", "Fahrenheit"))
_unit("Pa", {"mass": 1, "length": -1, "time": -2}, prefixable=True)
_unit("bar", {"mass": 1, "length": -1, "time": -2}, "100000", prefixable=True)
_unit("atm", {"mass": 1, "length": -1, "time": -2}, "101325")
_unit("mmHg", {"mass": 1, "length": -1, "time": -2}, "133.322387415",
      aliases=("Torr", "torr"))
_unit("psi", {"mass": 1, "length": -1, "time": -2}, "6894.757293168")
_unit("J", {"mass": 1, "length": 2, "time": -2}, prefixable=True)
_unit("cal", {"mass": 1, "length": 2, "time": -2}, "4.184")
_unit("kcal", {"mass": 1, "length": 2, "time": -2}, "4184")
_unit("Wh", {"mass": 1, "length": 2, "time": -2}, "3600", prefixable=True)
_unit("eV", {"mass": 1, "length": 2, "time": -2}, "1.602176634e-19", prefixable=True)
_unit("m", {"length": 1}, aliases=("metre", "meter"), prefixable=True)
_unit("L", {"length": 3}, "0.001", aliases=("l", "litre", "liter"), prefixable=True)
_unit("mol", {"amount": 1}, prefixable=True)
_unit("M", {"amount": 1, "length": -3}, "1000", prefixable=True)  # molar, exactly mol/L


@dataclass(frozen=True)
class _BaseResolution:
    factor: UnitFactor
    displayed: str


def resolve_atom(atom: str) -> _BaseResolution:
    if atom in _UNIT_TABLE:
        return _BaseResolution(_UNIT_TABLE[atom], _UNIT_TABLE[atom].symbol)
    # Exact non-SI aliases win over prefix interpretation (min, mmHg, M).
    for prefix in ("da", "µ", "u", "μ", "n", "m", "c", "d", "h", "k", "M", "G", "T"):
        if atom.startswith(prefix) and atom[len(prefix):] in _UNIT_TABLE:
            base_name = atom[len(prefix):]
            base = _UNIT_TABLE[base_name]
            if base.symbol not in _PREFIXABLE or base.affine:
                continue
            canonical_prefix = "µ" if prefix in ("u", "μ") else prefix
            return _BaseResolution(UnitFactor(canonical_prefix + base.symbol, dict(base.dimension),
                                              D(_PREFIXES[prefix]) * base.scale),
                                   canonical_prefix + base.symbol)
    raise QuantityError("unknown_unit", "Unregistered unit atom %r; no conversion was guessed." % atom)


def _combine_dimension(a: Dict[str, int], b: Dict[str, int], sign: int = 1) -> Dict[str, int]:
    dims = dict(a)
    for key, value in b.items():
        dims[key] = dims.get(key, 0) + sign * value
        if dims[key] == 0:
            del dims[key]
    return dict(sorted(dims.items()))


def _multiply(a: UnitFactor, b: UnitFactor) -> UnitFactor:
    if a.affine or b.affine:
        raise QuantityError("invalid_affine_compound", "Offset temperature units cannot be compounded.")
    with localcontext() as ctx:
        ctx.prec = 60
        scale = a.scale * b.scale
    return UnitFactor((a.symbol + " " + b.symbol).strip(), _combine_dimension(a.dimension, b.dimension), scale)


def _divide(a: UnitFactor, b: UnitFactor) -> UnitFactor:
    if a.affine or b.affine:
        raise QuantityError("invalid_affine_compound", "Offset temperature units cannot be compounded.")
    with localcontext() as ctx:
        ctx.prec = 60
        scale = a.scale / b.scale
    return UnitFactor(a.symbol + "/" + b.symbol, _combine_dimension(a.dimension, b.dimension, -1), scale)


def _power(a: UnitFactor, exponent: int) -> UnitFactor:
    if a.affine and exponent != 1:
        raise QuantityError("invalid_affine_power", "Offset temperature units only support exponent one.")
    if exponent == 0:
        raise QuantityError("dimensionless_unit", "A zero unit exponent is not a typed measurement unit.")
    dims = {k: v * exponent for k, v in a.dimension.items()}
    with localcontext() as ctx:
        ctx.prec = 60
        scale = a.scale ** exponent
    return UnitFactor(a.symbol + ("^" + str(exponent) if exponent != 1 else ""), dims,
                      scale, a.offset if exponent == 1 else D(0), a.affine)


class UnitParser:
    """Recursive-descent product/quotient/power parser with implicit products."""

    def __init__(self, tokens: Sequence[Token]):
        self.tokens = list(tokens)
        self.i = 0

    def current(self) -> Token:
        return self.tokens[self.i]

    def take(self) -> Token:
        token = self.current(); self.i += 1; return token

    def parse(self) -> UnitFactor:
        if self.current().kind == "EOF":
            raise QuantityError("missing_unit", "A typed quantity requires a unit (or a supplied unit field).")
        result = self.product()
        if self.current().kind != "EOF":
            token = self.current()
            raise QuantityError("invalid_unit_syntax", "Unexpected token %r in unit expression." % token.text,
                                token.position)
        return result

    def product(self) -> UnitFactor:
        result = self.power()
        while True:
            kind = self.current().kind
            if kind in ("*", "·", "⋅", "×"):
                self.take(); result = _multiply(result, self.power()); continue
            if kind == "/":
                self.take(); result = _divide(result, self.power()); continue
            if kind in ("ATOM", "("):
                result = _multiply(result, self.power()); continue
            break
        return result

    def power(self) -> UnitFactor:
        token = self.take()
        if token.kind == "(":
            atom = self.product()
            if self.current().kind != ")":
                raise QuantityError("invalid_unit_syntax", "Unclosed unit parenthesis.", token.position)
            self.take()
            # Parenthesized symbols are preserved semantically, not textually.
        elif token.kind == "ATOM":
            atom = resolve_atom(token.text).factor
        else:
            raise QuantityError("invalid_unit_syntax", "Expected a unit atom, found %r." % token.text,
                                token.position)
        exponent: Optional[int] = None
        if self.current().kind == "^":
            self.take()
            exponent = self.signed_exponent(self.take())
        elif self.current().kind == "EXPONENT":
            text = self.take().text
            try:
                exponent = int(text)
            except ValueError:
                raise QuantityError("invalid_unit_exponent", "Malformed superscript exponent.")
        elif self.current().kind == "RANGE" and self.tokens[self.i + 1].kind == "NUMBER":
            # Common plain-text m-3 exponent notation, valid only after an atom.
            self.take()
            number = self.take()
            exponent = self.signed_exponent(Token("NUMBER", "-" + number.text, number.position,
                                                   -number.value))
        if exponent is not None:
            if abs(exponent) > 20:
                raise QuantityError("invalid_unit_exponent", "Unit exponent magnitude exceeds 20.")
            atom = _power(atom, exponent)
        return atom

    @staticmethod
    def signed_exponent(token: Token) -> int:
        if token.kind != "NUMBER" or token.value != token.value.to_integral_value():
            raise QuantityError("invalid_unit_exponent", "Unit exponent must be an integer.", token.position)
        return int(token.value)


@dataclass(frozen=True)
class Quantity:
    raw: str
    approximate: bool
    value: Decimal
    interval_high: Optional[Decimal]
    uncertainty: Optional[Decimal]
    unit: UnitFactor

    @property
    def kind(self) -> str:
        if self.interval_high is not None:
            return "interval"
        if self.uncertainty is not None:
            return "uncertainty"
        return "point"


@dataclass(frozen=True)
class RoundingPolicy:
    mode: str = "significant_figures"
    digits: int = 12

    @classmethod
    def from_spec(cls, spec: Optional[Dict[str, Any]]) -> "RoundingPolicy":
        if not isinstance(spec, dict):
            return cls()
        data = spec.get("rounding", spec)
        if not isinstance(data, dict):
            return cls()
        mode = str(data.get("mode", data.get("policy", "significant_figures"))).lower().replace("-", "_")
        if mode in ("sigfig", "significant", "significantfigures"):
            mode = "significant_figures"
        if mode in ("decimal", "places", "fixed"):
            mode = "decimal_places"
        amount = data.get("digits", data.get("significant_figures",
                    data.get("places", data.get("decimal_places", 12))))
        try:
            digits = int(amount)
        except (TypeError, ValueError):
            raise QuantityError("invalid_rounding_policy", "Rounding digits/places must be an integer.")
        if mode not in ("significant_figures", "decimal_places", "none"):
            raise QuantityError("invalid_rounding_policy", "Unknown rounding mode %r." % mode)
        if not 0 <= digits <= 50 or (mode == "significant_figures" and digits == 0):
            raise QuantityError("invalid_rounding_policy", "Rounding digits/places outside the supported range.")
        return cls(mode, digits)


def round_decimal(value: Decimal, policy: RoundingPolicy) -> Decimal:
    if not value.is_finite():
        raise QuantityError("nonfinite_result", "Conversion produced a non-finite value.")
    if value.is_zero() or policy.mode == "none":
        return value
    with localcontext() as ctx:
        ctx.prec = max(60, policy.digits + abs(value.adjusted()) + 5)
        if policy.mode == "decimal_places":
            quantum = D(1).scaleb(-policy.digits)
        else:
            quantum = D(1).scaleb(value.adjusted() - policy.digits + 1)
        result = value.quantize(quantum, rounding=ROUND_HALF_EVEN)
    return D(0) if result.is_zero() else result


def format_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise QuantityError("nonfinite_result", "Refusing to format a non-finite result.")
    if value.is_zero():
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def parse_quantity(raw: str, convention: Optional[NumberConvention] = None,
                   unit_hint: Optional[str] = None) -> Quantity:
    if raw is None:
        raise QuantityError("missing_value", "Missing values remain missing, never zero.")
    raw = str(raw).strip()
    if not raw or raw.lower() in ("na", "n/a", "null", "none", "missing", "not reported", "not_reported"):
        raise QuantityError("missing_value", "Missing values remain missing, never zero.")
    if raw in ("—", "–", "-", "−"):
        raise QuantityError("missing_value", "A dash-only measurement is missing, not an interval.")
    tokens = Lexer(raw, convention or NumberConvention()).scan()
    i = 0
    approximate = False
    if tokens[i].kind == "APPROX":
        approximate = True; i += 1
    if tokens[i].kind != "NUMBER":
        raise QuantityError("expected_number", "Quantity must start with a signed numeric value.",
                            tokens[i].position)
    value = tokens[i].value; i += 1
    high = None; uncertainty = None
    if tokens[i].kind in ("RANGE", "TO"):
        i += 1
        if tokens[i].kind != "NUMBER":
            raise QuantityError("expected_interval_endpoint", "Interval requires a second numeric endpoint.",
                                tokens[i].position)
        high = tokens[i].value; i += 1
    if tokens[i].kind == "PM":
        if high is not None:
            raise QuantityError("mixed_quantity_shapes", "Interval and +/- uncertainty cannot share one cell.")
        i += 1
        if tokens[i].kind != "NUMBER":
            raise QuantityError("expected_uncertainty", "+/- requires a numeric magnitude.", tokens[i].position)
        uncertainty = tokens[i].value; i += 1
        if uncertainty < 0:
            raise QuantityError("negative_uncertainty", "Uncertainty magnitude cannot be negative.")
    if high is not None and high < value:
        raise QuantityError("reversed_input_interval", "Input interval endpoints must be low then high.")
    if unit_hint and tokens[i].kind == "EOF":
        hinted = Lexer(str(unit_hint), convention or NumberConvention()).scan()
        tokens = tokens[:-1] + hinted
    unit = UnitParser(tokens[i:]).parse()
    # For affine temperatures, the central value receives the offset while the
    # uncertainty magnitude is multiplied only by abs(multiplier) downstream.
    return Quantity(raw, approximate, value, high, uncertainty, unit)


def transform_linear(endpoint: Decimal, multiplier: Decimal, numerator_offset: Decimal,
                     target_offset: Decimal) -> Decimal:
    """Apply ((endpoint * multiplier) + numerator_offset) - target_offset.

    A negative multiplier is explicitly supported. Callers converting an interval
    must reverse its endpoints, which convert_quantity does below.
    """
    return (endpoint * multiplier) + numerator_offset - target_offset


@dataclass(frozen=True)
class ConvertedQuantity:
    quantity: Quantity
    target: UnitFactor
    values: Tuple[Decimal, ...]
    uncertainty: Optional[Decimal]
    expression: str
    trace: Dict[str, Any]


def convert_quantity(quantity: Quantity, target_unit: str,
                     rounding: Optional[RoundingPolicy] = None) -> ConvertedQuantity:
    rounding = rounding or RoundingPolicy()
    target_tokens = Lexer(target_unit, NumberConvention(region="en-US")).scan()
    target = UnitParser(target_tokens).parse()
    source = quantity.unit
    if source.dimension != target.dimension:
        raise QuantityError("dimension_mismatch",
                            "Source dimension %r cannot convert to target dimension %r." %
                            (source.dimension, target.dimension))
    if target.affine and (source.dimension != {"temperature": 1} or len(source.symbol.split()) != 1):
        raise QuantityError("invalid_affine_target", "Affine targets require a standalone temperature source.")
    with localcontext() as ctx:
        ctx.prec = 60
        multiplier = source.scale / target.scale
        # Dividing the base-unit equation by target.scale folds both source
        # and target offsets into the same normalized target arithmetic.
        numerator_offset = source.offset / target.scale
        target_offset = target.offset / target.scale
        transformed = [transform_linear(v, multiplier, numerator_offset, target_offset)
                       for v in ((quantity.value, quantity.interval_high)
                                 if quantity.interval_high is not None else (quantity.value,))]
        reversed_for_negative = False
        if quantity.interval_high is not None and multiplier < 0:
            transformed.reverse(); reversed_for_negative = True
        uncertainty = quantity.uncertainty * abs(multiplier) if quantity.uncertainty is not None else None
        rounded = tuple(round_decimal(v, rounding) for v in transformed)
        rounded_uncertainty = round_decimal(uncertainty, rounding) if uncertainty is not None else None
    if quantity.interval_high is not None:
        number_text = format_decimal(rounded[0]) + "–" + format_decimal(rounded[1])
    else:
        number_text = format_decimal(rounded[0])
        if rounded_uncertainty is not None:
            number_text += "±" + format_decimal(rounded_uncertainty)
    if quantity.approximate:
        number_text = "≈" + number_text
    trace = {
        "source_dimension": source.dimension,
        "target_dimension": target.dimension,
        "multiplier_source_scale_over_target_scale": format_decimal(multiplier),
        "source_offset_over_target_scale": format_decimal(numerator_offset),
        "target_offset_over_target_scale": format_decimal(target_offset),
        "formula": "target = raw * (" + format_decimal(multiplier) + ") + (" +
                   format_decimal(numerator_offset) + ") - (" + format_decimal(target_offset) + ")",
        "uncertainty_formula": "uncertainty_target = uncertainty_source * abs(multiplier)",
        "interval_reversed_for_negative_multiplier": reversed_for_negative,
        "rounding": {"mode": rounding.mode, "digits_or_places": rounding.digits, "tie_rule": "ROUND_HALF_EVEN"},
    }
    return ConvertedQuantity(quantity, target, rounded, rounded_uncertainty,
                             number_text + " " + target.symbol, trace)
