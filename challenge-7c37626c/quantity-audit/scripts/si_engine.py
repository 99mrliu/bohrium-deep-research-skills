#!/usr/bin/env python3
"""Exact SI dimensional engine: unit registry, compound-unit parser with
fractional group powers, and dimension algebra over rational exponents.

Dimension vectors are dicts over the five SI base dims L, M, T, I, Th with
fractions.Fraction exponents, so (V cm^-1)^-1/2 is exact, not float-rounded.
Stdlib only.
"""
import re
from fractions import Fraction

Q_E = 1.602176634e-19   # elementary charge, C (SI defining constant)
K_B_EV = 8.617333262e-5  # Boltzmann constant, eV/K (exact from SI definitions)

DIMS = ("L", "M", "T", "I", "Th")

# unit -> (magnitude in SI base units, dim vector)
REGISTRY = {
    "m":  (1.0,          {"L": 1}),
    "cm": (1e-2,         {"L": 1}),
    "mm": (1e-3,         {"L": 1}),
    "um": (1e-6,         {"L": 1}),
    "nm": (1e-9,         {"L": 1}),
    "km": (1e3,          {"L": 1}),
    "s":  (1.0,          {"T": 1}),
    "min": (60.0,        {"T": 1}),
    "h":  (3600.0,       {"T": 1}),
    "kg": (1.0,          {"M": 1}),
    "g":  (1e-3,         {"M": 1}),
    "A":  (1.0,          {"I": 1}),
    "K":  (1.0,          {"Th": 1}),
    "C":  (1.0,          {"T": 1, "I": 1}),
    "V":  (1.0,          {"M": 1, "L": 2, "T": -3, "I": -1}),
    "J":  (1.0,          {"M": 1, "L": 2, "T": -2}),
    "N":  (1.0,          {"M": 1, "L": 1, "T": -2}),
    "W":  (1.0,          {"M": 1, "L": 2, "T": -3}),
    "Pa": (1.0,          {"M": 1, "L": -1, "T": -2}),
    "ohm": (1.0,         {"M": 1, "L": 2, "T": -3, "I": -2}),
    "eV": (Q_E,          {"M": 1, "L": 2, "T": -2}),
    "count": (1.0,       {}),
    "":     (1.0,        {}),
    "1":    (1.0,        {}),
}

CODATA = {
    "q":   (Q_E, "C"),
    "e":   (Q_E, "C"),
    "k_B": (K_B_EV, "eV/K"),
    "k_B_J": (1.380649e-23, "J/K"),
    "c":   (299792458.0, "m/s"),
    "h":   (6.62607015e-34, "J s"),
    "N_A": (6.02214076e23, "count"),
    "m_e": (9.1093837015e-31, "kg"),
}


class UnitError(ValueError):
    pass


def _zero(dim):
    return {k: v for k, v in dim.items() if v}


def dim_add(a, b):
    out = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, 0) + v
    return _zero(out)


def dim_scale(a, p):
    return _zero({k: v * p for k, v in a.items()})


def dim_eq(a, b):
    return _zero(dict(a)) == _zero(dict(b))


def dim_str(dim):
    if not _zero(dict(dim)):
        return "1"
    return " ".join("%s^%s" % (k, dim[k]) for k in DIMS if k in dim)


def _pow_str(s):
    s = s.strip().replace("−", "-")
    if "/" in s:
        num, den = s.split("/", 1)
        return Fraction(int(num), int(den))
    return Fraction(int(s))


def parse_unit(unit):
    """Parse compound units: 'cm^2 V^-1 s^-1', 'eV/K', '(V cm^-1)^-1/2'.

    Returns (magnitude_in_SI, dim_vector). Raises UnitError on unknown
    spellings — callers must report the spelling, never guess.
    """
    s = (unit or "").strip()
    if s in REGISTRY:
        mag, dim = REGISTRY[s]
        return mag, _zero({k: Fraction(v) for k, v in dim.items()})
    mag, dim = _parse_product(s, sign=1)
    return mag, _zero(dim)


def _parse_product(s, sign=1):
    tokens = _unit_tokens(s)
    if not tokens:
        raise UnitError("empty unit")
    mag, dim = 1.0, {}
    for tok in tokens:
        if tok == "/":
            sign = -sign
            continue
        if tok.startswith("("):
            close = tok.rfind(")")
            inner = tok[1:close]
            inner_mag, inner_dim = _parse_product(inner, sign=1)
            power = Fraction(sign)
            rest = tok[close + 1:]
            if rest.startswith("^"):
                power = Fraction(sign) * _pow_str(rest[1:])
            mag *= inner_mag ** float(power)
            dim = dim_add(dim, dim_scale(inner_dim, power))
            continue
        m = re.match(r"^([A-Za-zμ]+|\d)(?:\^([−\-]?\d+(?:/\d+)?))?$", tok)
        if not m:
            raise UnitError("unparseable unit token %r" % tok)
        name = m.group(1)
        if name not in REGISTRY:
            raise UnitError("unknown unit %r" % name)
        power = Fraction(sign) * (_pow_str(m.group(2)) if m.group(2) else Fraction(1))
        u_mag, u_dim = REGISTRY[name]
        mag *= u_mag ** float(power)
        dim = dim_add(dim, dim_scale({k: Fraction(v) for k, v in u_dim.items()}, power))
    return mag, dim


def _unit_tokens(s):
    """Split on whitespace and '·'; keep '(...)' groups with their '^power'."""
    out, i, n = [], 0, len(s)
    while i < n:
        ch = s[i]
        if ch.isspace() or ch == "·":
            i += 1
            continue
        if ch == "/":
            out.append("/")
            i += 1
            continue
        if ch == "(":
            depth, j = 1, i + 1
            while j < n and depth:
                depth += (s[j] == "(") - (s[j] == ")")
                j += 1
            if depth:
                raise UnitError("unbalanced parenthesis in unit %r" % s)
            while j < n and (s[j] == "^" or s[j] in "-−0123456789/"):
                j += 1
            out.append(s[i:j])
            i = j
            continue
        j = i
        while j < n and not s[j].isspace() and s[j] not in "/·":
            j += 1
        out.append(s[i:j])
        i = n if j == i else j
    return out


def to_si(value, unit):
    mag, dim = parse_unit(unit)
    return float(value) * mag, dim


def from_si(si_value, unit):
    mag, _ = parse_unit(unit)
    return si_value / mag
