"""Lexicon loading and cautious normalization utilities (stdlib only).

Normalization philosophy: only surface-level, lossless-ish transforms
(unicode folding, case folding, whitespace/punctuation collapse) plus
exact full-string lexicon alias lookup. We never fuzzy-match chemical
names: different salts, hydrates, stoichiometries, dopants or phases
stay different unless a human lists them as aliases.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path

DEFAULT_LEXICON_PATH = Path(__file__).resolve().parent.parent / "references" / "synonyms.json"

_SUBSCRIPT = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
_UNICODE_MINUS = {"−": "-", "–": "-", "—": "-", "‐": "-", "‑": "-"}

MISSING_TOKENS = {
    "", "na", "n/a", "n.a.", "none", "null", "nan", "-", "--", "---",
    "not reported", "not available", "unknown", "unreported", "nr",
    "n.d.", "nd", "?", "missing", "未报告", "未知", "缺失", "无",
}


def load_lexicon(path: str | Path | None = None) -> dict:
    p = Path(path) if path else DEFAULT_LEXICON_PATH
    with open(p, "r", encoding="utf-8") as fh:
        lex = json.load(fh)
    lex["_path"] = str(p)
    lex["_version"] = lex.get("lexicon_version", "unknown")
    return lex


def round_sig(x: float, digits: int = 12) -> float:
    """Deterministic rounding to avoid float noise in conversions."""
    return float(f"{x:.{digits}g}")


def normalize_text(s: object) -> str | None:
    """NFKC fold, sub/superscript digits, unicode minus, whitespace collapse."""
    if s is None:
        return None
    t = unicodedata.normalize("NFKC", str(s))
    t = t.translate(_SUBSCRIPT).translate(_SUPERSCRIPT)
    for k, v in _UNICODE_MINUS.items():
        t = t.replace(k, v)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def norm_token(s: object) -> str | None:
    """Cautious token key: casefold + separator unification. Never strips
    dopants, hydration dots or stoichiometric digits."""
    t = normalize_text(s)
    if t is None:
        return None
    t = t.casefold()
    # unify middot variants used in hydrates to ascii dot
    t = t.replace("·", ".").replace("•", ".")
    # remove spaces adjacent to structural punctuation only
    t = re.sub(r"\s*([:/.,;()\[\]+%])\s*", r"\1", t)
    t = re.sub(r"\s*-\s*", "-", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def build_field_map(lex: dict) -> dict[str, str]:
    """normalized alias -> canonical field name."""
    out: dict[str, str] = {}
    for canon, aliases in lex.get("field_aliases", {}).items():
        for a in aliases:
            out[norm_token(a)] = canon
    return out


# --------------------------------------------------------------------------
# material identity

_PHASE_WORD_RE_TEMPLATE = r"(?<![a-z0-9]){phase}(?![a-z0-9])"
_DOPED_PATTERNS = [
    # "N-doped TiO2", "N doped TiO2"
    re.compile(r"^(?P<dopant>[a-z][a-z0-9.,/+%() ]*?)[- ]doped\s+(?P<base>.+)$"),
    # "TiO2 doped with N"
    re.compile(r"^(?P<base>.+?)\s+doped with\s+(?P<dopant>.+)$"),
    # "TiO2:N", "TiO2 : N, C"
    re.compile(r"^(?P<base>[^:：]+)[:：]\s*(?P<dopant>[a-z][a-z0-9., +\-()x%]*?)$"),
    # "N-TiO2" (short dopant prefix)
    re.compile(r"^(?P<dopant>[a-z]{1,2}(?:,[a-z]{1,2})*)-(?P<base>[A-Za-z0-9].+)$"),
]


def canonical_material(raw: object, lex: dict) -> dict:
    """Resolve a raw material string to identity parts.

    Returns dict with keys: canonical, display, phase, dopant, matched_alias,
    notes. Different phases/dopants are surfaced as separate parts and never
    folded into the canonical material itself.
    """
    notes: list[str] = []
    aliases = lex.get("material_aliases", {})
    phases = lex.get("phase_aliases", {})

    display = normalize_text(raw)
    if display is None or display == "":
        return {"canonical": None, "display": None, "phase": None,
                "dopant": None, "matched_alias": None,
                "notes": ["empty_material"]}

    token = norm_token(display) or ""

    # extract dopant (identity-relevant, kept separately)
    dopant = None
    base_token = token
    for pat in _DOPED_PATTERNS:
        m = pat.match(base_token)
        if m:
            cand = norm_token(m.group("dopant"))
            base = m.group("base").strip()
            if cand and base and (base != base_token or len(base_token) <= 60):
                dopant = cand
                base_token = norm_token(base) or base_token
                notes.append("dopant_split")
                break

    # extract phase word anywhere as standalone word
    phase = None
    for p_alias in sorted(phases, key=len, reverse=True):
        p_canon = phases[p_alias]
        rx = re.compile(_PHASE_WORD_RE_TEMPLATE.format(phase=re.escape(p_alias)))
        if rx.search(base_token):
            phase = p_canon
            stripped = rx.sub(" ", base_token)
            stripped = re.sub(r"\(\s*\)|\[\s*\]", " ", stripped)
            stripped = re.sub(r"[\s\-:/]+$", "", stripped)
            stripped = re.sub(r"^[\s\-:/]+", "", stripped)
            base_token = norm_token(stripped) or base_token
            notes.append("phase_split")
            break

    # exact full-string alias lookup only
    canonical = aliases.get(base_token)
    matched_alias = base_token if canonical else None
    if canonical is None:
        canonical = base_token  # unknown name: stable identity is its own normalized token
        notes.append("lexicon_miss")

    return {"canonical": canonical, "display": display, "phase": phase,
            "dopant": dopant, "matched_alias": matched_alias, "notes": notes}


def canonical_metric(raw: object, lex: dict) -> dict:
    token = norm_token(raw)
    if token is None:
        return {"canonical": None, "display": None, "matched_alias": None}
    for canon, aliases in lex.get("metric_aliases", {}).items():
        if token == norm_token(canon) or token in (norm_token(a) for a in aliases):
            return {"canonical": canon, "display": normalize_text(raw),
                    "matched_alias": token}
    return {"canonical": token, "display": normalize_text(raw),
            "matched_alias": None}


def canonical_phase(raw: object, lex: dict) -> str | None:
    token = norm_token(raw)
    if token is None:
        return None
    return lex.get("phase_aliases", {}).get(token, token)


# --------------------------------------------------------------------------
# values and units

_SCALAR_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
_RANGE_RE = re.compile(
    r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"\s*(?:\.\.|-{1,2}|~|–|—|to)\s*"
    r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)$"
)
_VALUE_UNIT_RE = re.compile(
    r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([a-zA-Zµμ°%Å/][a-zA-Zµμ°%Å0-9/^._-]*)$"
)


def parse_value(raw: object) -> dict:
    """Parse a measurement value. Returns kind: missing|scalar|range|text.
    Missing tokens become kind=missing with value None (stays null)."""
    t = normalize_text(raw)
    if t is None:
        return {"kind": "missing", "value": None, "raw": None, "explicit": False}
    if t.casefold() in MISSING_TOKENS:
        return {"kind": "missing", "value": None, "raw": t, "explicit": True}
    t_num = t.replace(",", "") if re.fullmatch(r"[+-]?\d{1,3}(,\d{3})+(\.\d+)?", t) else t
    if _SCALAR_RE.match(t_num):
        return {"kind": "scalar", "value": round_sig(float(t_num)), "raw": t,
                "explicit": False}
    m = _RANGE_RE.match(t_num)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        if lo > hi:
            lo, hi = hi, lo
        return {"kind": "range", "value": None, "min": round_sig(lo),
                "max": round_sig(hi), "raw": t, "explicit": False}
    return {"kind": "text", "value": None, "raw": t, "explicit": False}


def split_value_unit(raw: object) -> tuple[str, str] | None:
    """'3.2 eV' -> ('3.2', 'eV'). Only unambiguous scalar+unit strings."""
    t = normalize_text(raw)
    if not t:
        return None
    m = _VALUE_UNIT_RE.match(t)
    if m:
        return m.group(1), m.group(2)
    return None


def normalize_unit(raw: object, lex: dict) -> dict:
    """Resolve unit string to lexicon entry. status: known|unknown|missing."""
    t = normalize_text(raw)
    if t is None or t.casefold() in MISSING_TOKENS:
        return {"status": "missing", "unit_raw": t, "entry": None}
    key = t.replace("µ", "u").replace("μ", "u").casefold()
    key = re.sub(r"\s+", " ", key).strip()
    alias = lex.get("unit_aliases", {})
    if key in alias:
        key = alias[key]
    if key.endswith(" ") is False:
        key2 = key.replace(" ", "")
        if key2 in alias:
            key = alias[key2]
    entry = lex.get("units", {}).get(key) or lex.get("units", {}).get(key.replace(" ", ""))
    if entry is None:
        return {"status": "unknown", "unit_raw": t, "entry": None}
    return {"status": "known", "unit_raw": t, "entry": entry, "unit_key": key}


def convert_value(value: float, unit_info: dict, target_dimension: str | None,
                  target_unit: str | None, lex: dict) -> dict | None:
    """Convert scalar to canonical unit when dimension matches. Returns None
    when conversion is impossible; caller keeps the original value."""
    if value is None or unit_info.get("status") != "known":
        return None
    entry = unit_info["entry"]
    if target_dimension and entry.get("dimension") != target_dimension:
        return None
    if not target_unit or entry.get("canonical") != target_unit:
        return None
    factor = float(entry.get("factor", 1.0))
    offset = float(entry.get("offset", 0.0))
    new_val = round_sig(value * factor + offset)
    formula = f"value * {factor:g} + {offset:g}"
    if factor == 1.0 and offset == 0.0:
        formula = "identity (unit already canonical)"
    return {"value": new_val, "unit": entry["canonical"], "formula": formula,
            "factor": factor, "offset": offset}


def values_equal(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)
