#!/usr/bin/env python3
"""Structural signature extraction for MathML trees and publisher alttext TeX.

A signature is a canonical feature multiset that preserves structure
(fractions, scripts, radicals, fences) and symbol identity, without
committing to a LaTeX dialect. Two representations of the same formula agree
on the multiset; a dropped superscript, merged symbol or lost denominator
changes it. Stdlib only (Python 3.9+).
"""
import re
import xml.etree.ElementTree as ET
from collections import Counter

GREEK = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon",
    "ζ": "zeta", "η": "eta", "θ": "theta", "ι": "iota", "κ": "kappa",
    "λ": "lambda", "μ": "mu", "ν": "nu", "ξ": "xi", "π": "pi", "ρ": "rho",
    "σ": "sigma", "τ": "tau", "υ": "upsilon", "φ": "phi", "χ": "chi",
    "ψ": "psi", "ω": "omega",
    "Γ": "Gamma", "Δ": "Delta", "Θ": "Theta", "Λ": "Lambda", "Ξ": "Xi",
    "Π": "Pi", "Σ": "Sigma", "Φ": "Phi", "Ψ": "Psi", "Ω": "Omega",
}

OPERATORS = {"=": "eq", "+": "plus", "−": "minus", "-": "minus",
             "·": "cdot", "×": "times", "(": "lparen", ")": "rparen"}

# TeX command -> structural feature emitted by latex_signature. Commands that
# name functions (exp, sin, ...) are NOT listed: they fall through to the
# sym: branch so that <mi>exp</mi> and \exp agree on the symbol "exp".
TEX_FEATURES = {
    "frac": "FRAC", "dfrac": "FRAC", "tfrac": "FRAC",
    "sqrt": "SQRT", "overline": "OVERLINE", "vec": "VEC",
    "left": None, "right": None, "mathrm": None, "text": None,
    "boldsymbol": None, "mathbf": None,
}


def local(tag):
    return tag.rsplit("}", 1)[-1]


def norm_symbol(text):
    # Greek code points map to names; ASCII letters keep adjacency so that
    # multi-letter identifiers ("exp") stay one symbol.
    return "".join(GREEK.get(ch, ch) for ch in (text or "").strip())


def mathml_signature(node, counter):
    """Accumulate structural features of a MathML element into `counter`."""
    tag = local(node.tag)
    if tag in ("mfrac",):
        counter["FRAC"] += 1
    elif tag == "msqrt":
        counter["SQRT"] += 1
    elif tag == "mroot":
        counter["ROOT"] += 1
    elif tag in ("msub", "msup", "msubsup"):
        counter[tag.upper()] += 1
    elif tag == "mtable":
        counter["MATRIX"] += 1
    elif tag == "mfenced":
        counter["FENCE"] += 1
    elif tag == "munderover":
        counter["UNDEROVER"] += 1
    elif tag == "mi":
        counter["sym:" + norm_symbol(node.text)] += 1
    elif tag == "mn":
        counter["num:" + (node.text or "").strip()] += 1
    elif tag == "mo":
        t = (node.text or "").strip()
        counter["op:" + OPERATORS.get(t, t or "invisible")] += 1
    elif tag == "mtext":
        # Short alphanumeric mtext (e.g. the "B" of k_B) usually marks a
        # subscript symbol in publisher markup and corresponds to \mathrm{B}
        # in alttext; longer runs are prose text.
        t = (node.text or "").strip()
        key = "sym:" + norm_symbol(t) if re.fullmatch(r"[A-Za-z0-9]{1,3}", t) \
            else "text:" + t
        counter[key] += 1
    for child in node:
        mathml_signature(child, counter)


def tex_groups(s):
    """Yield top-level tokens of a small TeX subset: \\cmd, {group}, or char."""
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if ch.isspace():
            i += 1
            continue
        if ch == "\\":
            m = re.match(r"\\([a-zA-Z]+|.)", s[i:])
            cmd = m.group(1)
            yield ("cmd", cmd)
            i += 1 + len(cmd)
            continue
        if ch == "{":
            depth, j = 1, i + 1
            while j < n and depth:
                depth += (s[j] == "{") - (s[j] == "}")
                j += 1
            yield ("group", s[i + 1:j - 1])
            i = j
            continue
        yield ("char", ch)
        i += 1


def latex_signature(tex, counter):
    """Approximate structural features from a TeX string (alttext)."""
    tokens = list(tex_groups(tex or ""))
    i = 0
    while i < len(tokens):
        kind, val = tokens[i]
        if kind == "cmd":
            low = val.lower()
            if low in TEX_FEATURES:
                feat = TEX_FEATURES[low]
                if feat:
                    counter[feat] += 1
            elif low in set(GREEK.values()):
                counter["sym:" + low] += 1
            elif val and val[0].isalpha() and len(val) > 1:
                counter["sym:" + val] += 1
            else:
                counter["op:" + val] += 1
        elif kind == "char":
            if val == "_":
                counter["MSUB"] += 1
            elif val == "^":
                counter["MSUP"] += 1
            elif val.isdigit():
                counter["num:" + val] += 1
            elif val.isalpha():
                counter["sym:" + val] += 1
            elif val in OPERATORS:
                counter["op:" + OPERATORS[val]] += 1
        elif kind == "group":
            latex_signature(val, counter)
        i += 1


def compare_multisets(a, b):
    """Return (match, missing_in_b, extra_in_b) for Counter a vs Counter b."""
    missing = dict((a - b))
    extra = dict((b - a))
    return (not missing and not extra), missing, extra


def find_math_nodes(root):
    """Yield every math element (any namespace) under root."""
    for el in root.iter():
        if local(el.tag) == "math":
            yield el
