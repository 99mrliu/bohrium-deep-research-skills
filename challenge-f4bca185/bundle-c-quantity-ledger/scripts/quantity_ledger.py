#!/usr/bin/env python3
"""quantity_ledger.py -- literature extraction cleaning with a traceable quantity ledger.

Stdlib only, Python 3.10+.  All numeric work uses decimal.Decimal; binary floats
are never used for parsing, arithmetic or serialisation of quantities.

CLI (all arguments optional, defaults follow the platform runtime contract):
  python3 quantity_ledger.py --case /input/case.json --task /input/task.md \
      --work /app/work --out /app/output

Honest-partial policy: a minimal result.json is written before ingestion; every
later failure upgrades that file with status input_error/partial instead of
losing the run.  Unknown output_contract keys are emitted as null and listed in
"unresolved" rather than being invented.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from decimal import Decimal, Inexact, InvalidOperation, Rounded, localcontext
from pathlib import Path

VERSION = "1.0.0"
CALC_PREC = 80  # guard-digit context; inexact steps are reported, never hidden

# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8-sig", errors="replace")


def dec_plain(d: Decimal) -> str:
    """Exact decimal rendering; trailing zeros normalized; scientific notation
    only outside the everyday readable range."""
    if d.is_zero():
        return "0"
    dn = d.normalize()
    if -9 <= dn.adjusted() <= 21:
        return format(dn, "f")
    return str(dn)


def dec_op(op: str, *args: Decimal):
    """Decimal op under guard precision. Returns (result, rounded_flag)."""
    with localcontext() as ctx:
        ctx.prec = CALC_PREC
        ctx.clear_flags()
        try:
            if op == "mul":
                out = args[0] * args[1]
            elif op == "div":
                out = args[0] / args[1]
            elif op == "add":
                out = args[0] + args[1]
            elif op == "sub":
                out = args[0] - args[1]
            elif op == "pow":
                out = args[0] ** int(args[1])
            else:  # pragma: no cover
                raise ValueError(op)
        except (InvalidOperation, ZeroDivisionError, OverflowError):
            return None, True
        rounded = bool(ctx.flags[Inexact] or ctx.flags[Rounded])
    return out, rounded


class RuleRepo:
    """Machine-readable unit/prefix/target and alias resources."""

    def __init__(self, units_path: Path, aliases_path: Path):
        self.units_doc = json.loads(read_text(units_path))
        self.aliases_doc = json.loads(read_text(aliases_path))
        self.prefixes = self.units_doc["prefixes"]
        self.units = []  # list of dicts + symbol index
        self.by_symbol = {}
        for u in self.units_doc["units"]:
            self.units.append(u)
            for s in u["symbols"]:
                self.by_symbol[s] = u
        self.dims_targets = self.units_doc.get("default_targets", {})

    def alias_map(self):
        out = {}
        for canon, names in self.aliases_doc.get("field_aliases", {}).items():
            for n in names + [canon]:
                out[norm_key(n)] = canon
        return out

    def metric_synonyms(self):
        out = {}
        for canon, names in self.aliases_doc.get("metric_synonyms", {}).items():
            for n in names + [canon]:
                out[norm_key(n)] = canon
        return out


def norm_key(s) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s).strip().lower())


def norm_text(s) -> str:
    return re.sub(r"\s+", " ", str(s).strip())


def normalize_unicode(text: str) -> str:
    t = unicodedata.normalize("NFKC", str(text))
    # mathematical minus -> ascii hyphen (en/em dashes are kept for ranges)
    t = t.replace("−", "-").replace("﹣", "-")
    return t


# ---------------------------------------------------------------------------
# lexical number grammar (see references/lexical-grammar.md)
# ---------------------------------------------------------------------------
SIGN = r"[+-]?"
DIGITS = r"(?:\d[\d  ,.]*|[.,]\d+)(?:[.,]\d+)?"
NUM = rf"{SIGN}{DIGITS}"
SCI = rf"(?:[eE]{SIGN}\d+|[×x]\s*10\^?{SIGN}\d+)"
NUMBER_RE = re.compile(rf"({NUM})({SCI})?")
RANGE_SEP = r"(?:–|—|~|\.\.\.?|to)"  # en/em dash, tilde, .., to


class NumberIssue(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def sig_figs_of(num_text: str):
    m = re.match(rf"{SIGN}(\d[\d   ]*|[.,]\d+)?(?:[.,](\d+))?", num_text)
    digits = re.sub(r"[^0-9]", "", num_text.split("e")[0].split("E")[0])
    digits = digits.lstrip("0")
    return len(digits) if digits else 1


def decimal_from_numeric(num: str) -> Decimal:
    """Convert one numeric token (no exponent) to Decimal or raise NumberIssue."""
    raw = num
    if " " in num or "\u202f" in num:
        # space grouping: first group 1-3 digits, following groups exactly 3
        body = num.lstrip("+-")
        int_part = re.split(r"[.,]", body)[0]
        groups = re.split(r"[ \u202f]", int_part)
        if len(groups) < 2 or not re.fullmatch(r"\d{1,3}", groups[0]) \
                or not all(re.fullmatch(r"\d{3}", g) for g in groups[1:]):
            raise NumberIssue("malformed_number",
                              f"irregular space digit grouping in {raw!r}")
    num = num.replace("\u202f", "").replace(" ", "")
    if not num:
        raise NumberIssue("malformed_number", f"empty numeric token in {raw!r}")
    # comma / dot disambiguation: only unambiguous forms are accepted.
    c, d = num.count(","), num.count(".")
    if c and d:
        # the rightmost separator is the decimal separator, the other groups
        if num.rfind(",") > num.rfind("."):
            if len(num.split(",")[-1]) == 3 and d == 0:
                raise NumberIssue("ambiguous_decimal_comma", raw)
            num = num.replace(".", "").replace(",", ".")
        else:
            num = num.replace(",", "")
    elif c:
        if c > 1:
            groups = num.lstrip("+-").split(",")
            if not all(len(g) == 3 for g in groups[1:]):
                raise NumberIssue("ambiguous_decimal_comma", raw)
            num = num.replace(",", "")
        else:
            head, tail = num.lstrip("+-").split(",")
            if len(tail) == 3 and head not in ("", "0"):
                # "1,234": thousands grouping or decimal comma -> ambiguous
                raise NumberIssue(
                    "ambiguous_decimal_comma",
                    f"{raw!r}: single comma followed by exactly three digits",
                )
            num = num.replace(",", ".")
    try:
        return Decimal(num)
    except InvalidOperation:
        raise NumberIssue("malformed_number", f"cannot parse numeric token {raw!r}")


def parse_number_token(token: str):
    """Parse scalar numeric incl. scientific notation -> (Decimal, sig_figs)."""
    token = token.strip()
    m = re.fullmatch(rf"({NUM})(?:{SCI})?", token)
    if not m:
        raise NumberIssue("malformed_number", f"malformed number {token!r}")
    mantissa = m.group(1)
    value = decimal_from_numeric(mantissa)
    sci = token[len(mantissa):].strip()
    if sci:
        em = re.fullmatch(rf"(?:[eE]({SIGN}\d+)|[×x]\s*10\^?({SIGN}\d+))", sci)
        if not em:
            raise NumberIssue("malformed_number", f"malformed exponent in {token!r}")
        exp = int(em.group(1) or em.group(2))
        value, _ = dec_op("mul", value, Decimal(10) ** exp)
    return value, sig_figs_of(mantissa)


def parse_numeric_text(text: str):
    """Return kind dict for scalar / range / symmetric-uncertainty numerics."""
    t = normalize_unicode(text).strip()
    if not t:
        raise NumberIssue("missing_value", "empty value")
    if "�" in t:
        raise NumberIssue("encoding_replacement_char", "replacement character present")

    # symmetric uncertainty: "1.23 ± 0.05", "1.23 +/- 0.05", "1.23(5)"
    m = re.fullmatch(rf"\s*({NUM}(?:{SCI})?)\s*(?:±|\+/-|\+\-)\s*({NUM}(?:{SCI})?)\s*", t)
    if m:
        value, sf = parse_number_token(m.group(1))
        unc, _ = parse_number_token(m.group(2))
        if unc < 0:
            raise NumberIssue("malformed_number", "negative uncertainty")
        return {"kind": "symmetric", "value": value, "uncertainty": unc,
                "sig_figs": sf, "unc_notation": "plus_minus"}
    m = re.fullmatch(rf"\s*({NUM}(?:{SCI})?)\((\d+)\)\s*", t)
    if m:
        value, sf = parse_number_token(m.group(1))
        mant = m.group(1).split("e")[0].split("E")[0]
        if "." in mant or "," in mant:
            frac = re.split(r"[.,]", mant)[-1]
            scale = Decimal(10) ** (-len(frac))
        else:
            scale = Decimal(1)
        unc, _ = dec_op("mul", Decimal(m.group(2)), scale)
        return {"kind": "symmetric", "value": value, "uncertainty": unc,
                "sig_figs": sf, "unc_notation": "parenthesis_last_digits"}

    # ranges: explicit separators first, then bare '-' via backtracking fullmatch
    m = re.fullmatch(rf"\s*({NUM}(?:{SCI})?)\s*({RANGE_SEP})\s*({NUM}(?:{SCI})?)\s*", t)
    if not m:
        m = re.fullmatch(rf"\s*({NUM}(?:{SCI})?)-({NUM}(?:{SCI})?)\s*", t)
    if m:
        lo, _ = parse_number_token(m.group(1))
        hi, _ = parse_number_token(m.group(3) if m.lastindex and m.lastindex >= 3 else m.group(2))
        out = {"kind": "range", "low": lo, "high": hi, "sig_figs": None}
        if lo > hi:
            out["inverted"] = True
        return out

    value, sf = parse_number_token(t)
    return {"kind": "scalar", "value": value, "sig_figs": sf}


# ---------------------------------------------------------------------------
# unit expression algebra
# ---------------------------------------------------------------------------
UNIT_TOKEN = re.compile(
    r"\s*(?P<op>[/*·⋅])?\s*(?P<sym>1|[A-Za-zµμ°%‰]+)"
    r"(?:\s*(?:\^|\*\*)\s*(?P<exp>[+-]?\d+)|(?P<exp2>[+-]?\d+))?"
)


class UnitIssue(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def unit_factor(u: dict):
    """(factor Decimal, offset Decimal, rounded flag) from rule record."""
    rounded = False
    if "factor_num" in u:
        f, r1 = dec_op("div", Decimal(u["factor_num"]), Decimal(str(u.get("factor_den", "1"))))
        rounded = rounded or r1
    else:
        f = Decimal(u.get("factor", "1"))
    if "offset_num" in u:
        o, r2 = dec_op("div", Decimal(u["offset_num"]), Decimal(str(u.get("offset_den", "1"))))
        rounded = rounded or r2
    else:
        o = Decimal(u.get("offset", "0"))
    return f, o, rounded


def dims_key(dims: dict) -> str:
    return ",".join(f"{k}:{dims[k]}" for k in sorted(dims) if dims[k])


class UnitValue:
    def __init__(self):
        self.dims = {}
        self.factor = Decimal(1)
        self.offset = Decimal(0)
        self.affine = False
        self.rule_ids = []
        self.terms = []
        self.rounded = False

    @property
    def key(self):
        return dims_key(self.dims)


def lookup_symbol(sym: str, repo: RuleRepo):
    """Return (unit rule, Decimal prefix_multiplier, rule_ids)."""
    amb = repo.units_doc.get("ambiguous_symbols", {})
    if sym in amb:
        raise UnitIssue("ambiguous_unit", f"{sym!r}: {amb[sym]}")
    if sym == "1":
        return None, Decimal(1), ["U.dimensionless"]
    if sym in repo.by_symbol:
        return repo.by_symbol[sym], Decimal(1), [repo.by_symbol[sym]["id"]]
    # longest-prefix-first; greek mu accepted for micro
    sym_norm = sym.replace("µ", "μ")
    for p in sorted(repo.prefixes, key=len, reverse=True):
        p_def = repo.prefixes[p]
        for cand in {sym, sym_norm}:
            if cand.startswith(p) and len(cand) > len(p):
                base = cand[len(p):]
                if base in repo.by_symbol and repo.by_symbol[base].get("prefixable"):
                    mult = Decimal(10) ** int(p_def["power"])
                    return repo.by_symbol[base], mult, [p_def["id"], repo.by_symbol[base]["id"]]
    raise UnitIssue("unknown_unit", f"unknown unit symbol {sym!r}")


def parse_unit(expr: str, repo: RuleRepo) -> UnitValue:
    expr = normalize_unicode(expr).strip()
    if expr == "":
        raise UnitIssue("missing_unit", "empty unit expression")
    out = UnitValue()
    pos, sign_next, n_terms = 0, 1, 0
    n = len(expr)
    while pos < n:
        m = UNIT_TOKEN.match(expr, pos)
        if not m or m.end() == pos:
            raise UnitIssue("unknown_unit", f"unit syntax error near {expr[pos:]!r}")
        sym = m.group("sym")
        exp = int(m.group("exp") or m.group("exp2") or 1)
        if m.group("op") == "/":
            sign_next = -1
        elif m.group("op") in ("*", "·", "⋅"):
            sign_next = 1
        power = exp * sign_next
        sign_next = 1
        pos = m.end()
        rule, prefix_mult, ids = lookup_symbol(sym, repo)
        if rule is None:
            continue
        n_terms += 1
        if rule.get("kind") == "affine":
            if n_terms > 1 or power != 1 or expr.strip() != sym:
                raise UnitIssue("affine_in_composite",
                                f"affine unit {sym!r} cannot be composed or raised to powers")
            f, o, r = unit_factor(rule)
            out.factor, out.offset, out.affine = f, o, True
            out.rounded = out.rounded or r
            out.dims = dict(rule["dims"])
            out.rule_ids = ids
            out.terms.append(sym)
            continue
        f, o, r = unit_factor(rule)
        f, r2 = dec_op("mul", f, prefix_mult)
        fp, r3 = dec_op("pow", f, power)
        out.factor, r4 = dec_op("mul", out.factor, fp)
        out.rounded = out.rounded or r or r2 or r3 or r4
        for k, v in rule["dims"].items():
            out.dims[k] = out.dims.get(k, 0) + v * power
            if out.dims[k] == 0:
                del out.dims[k]
        out.rule_ids.extend(ids if power == 1 else ids + [f"U.power^{power}"])
        out.terms.append(f"{sym}^{power}" if power != 1 else sym)
    if pos != n or not out.terms:
        # "1" alone is the dimensionless unit; any other residue is rejected
        if expr.strip() == "1" and not out.terms:
            return out
        raise UnitIssue("unknown_unit", f"cannot parse unit expression {expr!r}")
    return out


def default_target(uv: UnitValue, repo: RuleRepo) -> str:
    if uv.key in repo.dims_targets:
        return repo.dims_targets[uv.key]
    base = {"L": "m", "M": "kg", "T": "s", "I": "A", "Th": "K", "N": "mol"}
    parts = []
    for k in sorted(uv.dims):
        e = uv.dims[k]
        parts.append(base[k] if e == 1 else f"{base[k]}^{e}")
    return " ".join(parts) if parts else "1"


# ---------------------------------------------------------------------------
# quantity parsing + conversion
# ---------------------------------------------------------------------------

def split_value_unit(value_text: str, unit_text):
    """Split '12.3 mg/L' when the unit column is absent."""
    if unit_text not in (None, ""):
        return str(value_text), str(unit_text), False
    t = normalize_unicode(str(value_text)).strip()
    m = re.match(rf"\s*({NUM}(?:{SCI})?(?:\s*(?:±|\+/-|\+\-)\s*{NUM}(?:{SCI})?)?"
                 rf"(?:\s*(?:{RANGE_SEP}|-)\s*{NUM}(?:{SCI})?)?(?:\(\d+\))?)\s+(\S.*)$", t)
    if m:
        return m.group(1), m.group(2).strip(), True
    return str(value_text), "", False


def map_affine_linear(x: Decimal, mult: Decimal, add: Decimal):
    a, r1 = dec_op("mul", x, mult)
    if a is None:
        return None, True
    b, r2 = dec_op("add", a, add)
    return b, r1 or r2


def convert_parsed(parsed: dict, src: UnitValue, tgt: UnitValue, target_expr: str):
    """Convert all numeric components; affine offsets apply to absolute values only."""
    mult, r1 = dec_op("div", src.factor, tgt.factor)
    off_src, r2 = dec_op("sub", src.offset, tgt.offset)
    add, r3 = dec_op("div", off_src, tgt.factor)
    rounded = r1 or r2 or r3 or src.rounded or tgt.rounded
    if mult is None or add is None:
        raise UnitIssue("incompatible_target_unit", "non-finite conversion factor")
    out = {"multiplier": mult, "addend": add, "rounded": rounded, "std": {}}

    def conv(x):
        nonlocal rounded
        v, r = map_affine_linear(x, mult, add)
        rounded = rounded or r
        return v

    kind = parsed["kind"]
    std = out["std"]
    if kind == "scalar":
        std["value"] = conv(parsed["value"])
    elif kind == "range":
        std["low"] = conv(parsed["low"])
        std["high"] = conv(parsed["high"])
        mid, r = dec_op("div", dec_op("add", parsed["low"], parsed["high"])[0], Decimal(2))
        rounded = rounded or r
        std["midpoint_derived"] = conv(mid)
    elif kind == "symmetric":
        std["value"] = conv(parsed["value"])
        # uncertainty is a difference: multiplier only, never an affine offset
        u, r = dec_op("mul", parsed["uncertainty"], abs(mult))
        rounded = rounded or r
        std["uncertainty"] = u
        lo, r1x = dec_op("sub", std["value"], u)
        hi, r2x = dec_op("add", std["value"], u)
        rounded = rounded or r1x or r2x
        std["unc_low_derived"] = lo
        std["unc_high_derived"] = hi
    out["rounded"] = rounded
    return out


def direct_std(parsed: dict):
    """No unit conversion (dimensionless kept as-is or no-op same unit)."""
    std = {}
    if parsed["kind"] == "scalar":
        std["value"] = parsed["value"]
    elif parsed["kind"] == "range":
        std["low"], std["high"] = parsed["low"], parsed["high"]
        mid, _ = dec_op("div", dec_op("add", parsed["low"], parsed["high"])[0], Decimal(2))
        std["midpoint_derived"] = mid
    elif parsed["kind"] == "symmetric":
        std["value"] = parsed["value"]
        std["uncertainty"] = parsed["uncertainty"]
        std["unc_low_derived"], _ = dec_op("sub", parsed["value"], parsed["uncertainty"])
        std["unc_high_derived"], _ = dec_op("add", parsed["value"], parsed["uncertainty"])
    return std


# ---------------------------------------------------------------------------
# ingestion: nested JSON + CSV, with coordinates for every record
# ---------------------------------------------------------------------------
RECORD_LIST_KEYS = {"records", "rows", "data", "extractions", "items", "entries"}
PATH_KEYS = {"path", "file", "filename", "filepath", "csv", "json_path"}


def is_scalar_record_list(obj) -> bool:
    return (isinstance(obj, list) and obj and
            all(isinstance(x, dict) for x in obj) and
            sum(1 for x in obj
                if any(isinstance(v, (str, int, float)) or v is None for v in x.values())) >= max(1, len(obj) // 2))


def discover_file_refs(obj, prefix="$", out=None):
    if out is None:
        out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in PATH_KEYS and isinstance(v, str) and re.search(r"\.(csv|json)$", v, re.I):
                out.append((v, f"{prefix}.{k}"))
            else:
                discover_file_refs(v, f"{prefix}.{k}", out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            discover_file_refs(v, f"{prefix}[{i}]", out)
    return out


def collect_embedded_records(obj, prefix="$", out=None, skip_lists=None):
    if out is None:
        out = []
    if skip_lists is None:
        skip_lists = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}"
            if isinstance(v, list) and is_scalar_record_list(v) and id(v) not in skip_lists:
                if k.lower() in RECORD_LIST_KEYS or prefix != "$":
                    skip_lists.add(id(v))
                    for i, rec in enumerate(v):
                        out.append((rec, f"{p}[{i}]"))
            else:
                collect_embedded_records(v, p, out, skip_lists)
    elif isinstance(obj, list) and id(obj) not in skip_lists:
        for i, v in enumerate(obj):
            collect_embedded_records(v, f"{prefix}[{i}]", out, skip_lists)
    return out


# ---------------------------------------------------------------------------
# output-contract handling
# ---------------------------------------------------------------------------
CONTRACT_HINTS = [
    (("clean", "standard", "normalized", "normalised", "table", "records", "data"), "cleaned"),
    (("anomal",), "anomalies"),
    (("review", "pending", "confirm", "uncertain"), "review"),
    (("ledger", "convers", "unit"), "ledger"),
    (("change", "changelog"), "changes"),
    (("source", "evidence"), "sources"),
    (("status",), "status"),
    (("uncertainty",), "uncertainty"),
    (("summary", "count", "stat"), "summary"),
]


def fill_result(run: dict, case: dict, args) -> dict:
    result = {
        "case_id": run["case_id"],
        "skill": "bundle-c-quantity-ledger",
        "skill_version": VERSION,
        "status": run["status"],
        "summary": run["summary"],
        "sources": run["sources"],
        "uncertainty": run["uncertainty"],
        "change_records": run["changes"],
        "artifacts": run["artifacts"],
        "errors": run["errors"],
    }
    payload = {
        "cleaned": run["cleaned"], "anomalies": run["anomalies"],
        "review": run["review"], "ledger": run["ledger"],
        "changes": run["changes"], "sources": run["sources"],
        "status": run["status"], "uncertainty": run["uncertainty"],
        "summary": run["summary"],
    }
    unresolved = []
    contract = case.get("output_contract") if isinstance(case, dict) else None
    if isinstance(contract, dict):
        keys = list(contract.keys())
    elif isinstance(contract, list):
        keys = [k for k in contract if isinstance(k, str)]
    elif isinstance(contract, str):
        keys = [contract]
    else:
        keys = []
    for key in keys:
        if key in result:
            continue
        desc = contract.get(key) if isinstance(contract, dict) else ""
        # conservative: only the key name itself may trigger a fill; free-text
        # descriptions are never used to guess a mapping.
        target = None
        for needles, name in CONTRACT_HINTS:
            if any(n in str(key).lower() for n in needles):
                target = name
                break
        if target is None:
            result[key] = None
            unresolved.append({"key": key, "reason": "no rule maps this contract key to a generated artifact",
                               "declared_contract": desc if isinstance(desc, (str, int, float, list, dict)) else str(desc)})
        else:
            result[key] = payload[target]
    result["unresolved"] = unresolved
    if unresolved and result["status"] == "success":
        result["status"] = "partial"
    return result


# ---------------------------------------------------------------------------
# main cleaning pipeline
# ---------------------------------------------------------------------------

def process(case_path: Path, task_path: Path, work: Path, out: Path,
            units_path: Path, aliases_path: Path):
    run = {"case_id": None, "status": "input_error", "errors": [], "sources": [],
           "uncertainty": [], "changes": [], "artifacts": {}, "cleaned": [],
           "anomalies": [], "review": [], "ledger": [], "summary": {}}

    def write_result():
        nonlocal run
        case_doc = run.get("_case_doc") if isinstance(run.get("_case_doc"), dict) else {}
        res = fill_result(run, case_doc or {}, None)
        run["artifacts"].setdefault("result_json", "result.json")
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return res

    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    # honest partial saved before any ingestion happens
    run["status"] = "partial"
    run["errors"].append("run started; ingestion not complete")
    write_result()
    run["errors"].clear()

    try:
        repo = RuleRepo(units_path, aliases_path)
    except Exception as e:
        run["status"] = "input_error"
        run["errors"].append(f"rule resources unreadable: {e}")
        write_result()
        return run

    # ---- read case + task
    case_bytes = b""
    try:
        case_bytes = case_path.read_bytes()
    except Exception as e:
        run["status"] = "input_error"
        run["errors"].append(f"case file unreadable: {case_path}: {e}")
        write_result()
        (out / "audit.md").write_text(audit_md(run, case_path, task_path), encoding="utf-8")
        return run
    run["sources"].append({"path": str(case_path), "sha256": sha256_bytes(case_bytes),
                           "format": case_path.suffix.lower().lstrip("."), "records": 0})
    if case_path.suffix.lower() == ".csv":
        case_doc = {"case_id": case_path.stem}
        records_raw = csv_records(case_path, case_path.parent, run)
        case_records = [(r, c) for r, c in records_raw]
    else:
        try:
            case_doc = json.loads(case_bytes.decode("utf-8-sig"))
        except Exception as e:
            run["status"] = "input_error"
            run["errors"].append(f"case JSON malformed: {e}")
            (work / "invalid-case-fragment.txt").write_text(
                case_bytes.decode("utf-8", errors="replace")[:4000], encoding="utf-8")
            write_result()
            (out / "audit.md").write_text(audit_md(run, case_path, task_path), encoding="utf-8")
            return run
        case_records = [(r, f"{case_path}#{c}") for r, c in collect_embedded_records(case_doc)]
        # referenced CSV / nested JSON materials
        for ref, coord in discover_file_refs(case_doc):
            ref_path = Path(ref)
            if not ref_path.is_absolute():
                ref_path = case_path.parent / ref_path
            if not ref_path.exists():
                run["anomalies"].append({"type": "missing_material_file", "reference": ref,
                                         "coordinates": coord, "detail": "referenced file not found"})
                continue
            case_records.extend(load_material(ref_path, run))
    if not isinstance(case_doc, dict):
        case_doc = {"case_id": case_path.stem, "records": case_doc}
    run["_case_doc"] = case_doc
    run["case_id"] = str(case_doc.get("case_id") or case_doc.get("id") or case_path.stem)
    if task_path.exists():
        run["summary"]["task_sha256"] = sha256_bytes(task_path.read_bytes())

    if not case_records:
        run["status"] = "partial"
        run["anomalies"].append({"type": "no_records_found", "detail":
                                 "no extraction records found in embedded JSON or referenced CSV"})
        run["errors"].append("no records ingested")
        finalize_outputs(run, out)
        write_result()
        (out / "audit.md").write_text(audit_md(run, case_path, task_path), encoding="utf-8")
        return run

    alias_map = repo.alias_map()
    metric_syn = repo.metric_synonyms()
    target_overrides = case_doc.get("target_units") or {}
    cleaned = []
    counters = {"rec": 0, "an": 0, "rv": 0, "ch": 0, "cv": 0}

    def anomaly(rec_id, coords, typ, raw, detail, review=True, suggestion=""):
        counters["an"] += 1
        run["anomalies"].append({"id": f"AN{counters['an']:04d}", "record_id": rec_id,
                                 "coordinates": coords, "type": typ,
                                 "raw": raw, "detail": detail})
        if review:
            review_add(rec_id, coords, typ, raw, detail, suggestion)

    def review_add(rec_id, coords, typ, raw, detail, suggestion=""):
        counters["rv"] += 1
        run["review"].append({"id": f"RV{counters['rv']:04d}", "record_id": rec_id,
                              "coordinates": coords, "reason": typ, "raw": raw,
                              "detail": detail, "suggested_action": suggestion})

    def change(rec_id, coords, field, action, rule_id, old, new, note=""):
        counters["ch"] += 1
        run["changes"].append({"id": f"CH{counters['ch']:04d}", "record_id": rec_id,
                               "coordinates": coords, "field": field, "action": action,
                               "rule_id": rule_id, "from": old, "to": new, "note": note})

    for rec, coords in case_records:
        counters["rec"] += 1
        rec_id = str(rec.get("record_id") or rec.get("id") or f"R{counters['rec']:04d}")
        if rec_id in {c["record_id"] for c in cleaned}:
            rec_id = f"R{counters['rec']:04d}"
        src_file = coords.split("#")[0] if "#" in coords else str(case_path)
        entry = {"record_id": rec_id, "input_coordinates": coords,
                 "material": "", "metric": "", "conditions": {},
                 "raw_value": None, "raw_unit": "", "parse_status": "ok", "kind": "",
                 "value": "", "uncertainty": "", "range_low": "", "range_high": "",
                 "unit": "", "std_unit": "", "std_value": "", "std_uncertainty": "",
                 "std_low": "", "std_high": "", "std_midpoint_derived": "",
                 "std_unc_low_derived": "", "std_unc_high_derived": "",
                 "conversion_rule_ids": "", "sig_figs": "", "duplicate_group": "",
                 "record_status": "clean", "review_reasons": [], "extra": {},
                 "raw_record": rec}
        canon = {}
        for k, v in rec.items():
            nk = alias_map.get(norm_key(k))
            if nk is None:
                entry["extra"][k] = v
                continue
            if nk in canon and str(canon[nk]).strip() != str(v).strip():
                review_add(rec_id, coords, "alias_conflict", f"{k}={v!r}",
                           f"two columns map to {nk!r} with different values",
                           "choose the correct source column manually")
                entry["record_status"] = "review"
                entry["extra"][k] = v
                continue
            if nk != k:
                change(rec_id, coords, k, "alias_rename", f"SCHEMA.alias.{nk}", str(k), nk)
            canon[nk] = v
        for fld in ("material", "metric"):
            if canon.get(fld) not in (None, ""):
                entry[fld] = norm_text(canon[fld])
        if entry["metric"]:
            entry["metric"] = metric_syn.get(norm_key(entry["metric"]), entry["metric"])
        entry["conditions"] = {k: norm_text(canon[k]) for k in
                               ("temperature", "pressure", "ph", "solvent", "method", "notes")
                               if canon.get(k) not in (None, "")}
        for k in ("source_id", "page", "table", "figure", "paragraph", "doi"):
            if canon.get(k) not in (None, ""):
                entry["conditions"][k] = norm_text(canon[k])

        raw_value = canon.get("value")
        if raw_value in (None, "") and canon.get("value_low") not in (None, "") and canon.get("value_high") not in (None, ""):
            raw_value = f"{canon['value_low']}..{canon['value_high']}"
            change(rec_id, coords, "value", "split_fields_joined", "SCHEMA.range_fields",
                   f"{canon['value_low']} | {canon['value_high']}", raw_value)
        if raw_value in (None, ""):
            anomaly(rec_id, coords, "missing_value", raw_value,
                    "no value supplied; left empty, never imputed", suggestion="supply value from source")
            entry["parse_status"] = "missing_value"
            entry["record_status"] = "review"
            entry["review_reasons"].append("missing_value")
            entry["raw_value"] = raw_value
            cleaned.append(entry)
            continue
        entry["raw_value"] = str(raw_value)
        value_text, unit_text, extracted = split_value_unit(str(raw_value), canon.get("unit"))
        if extracted:
            change(rec_id, coords, "unit", "unit_extracted_from_value", "LEX.embedded_unit",
                   str(raw_value), unit_text)
        entry["raw_unit"] = unit_text
        try:
            parsed = parse_numeric_text(value_text)
        except NumberIssue as e:
            anomaly(rec_id, coords, e.code, value_text, e.message,
                    suggestion="fix the literal in the extraction; value left unstandardized")
            entry["parse_status"] = e.code
            entry["record_status"] = "review"
            entry["review_reasons"].append(e.code)
            cleaned.append(entry)
            continue
        entry["kind"] = parsed["kind"]
        entry["sig_figs"] = parsed.get("sig_figs") or ""
        if parsed["kind"] == "scalar":
            entry["value"] = dec_plain(parsed["value"])
        elif parsed["kind"] == "range":
            entry["range_low"], entry["range_high"] = dec_plain(parsed["low"]), dec_plain(parsed["high"])
            if parsed.get("inverted"):
                anomaly(rec_id, coords, "invalid_range_order", value_text,
                        "range low > high; bounds kept in original order",
                        suggestion="confirm whether the extraction swapped the bounds")
                entry["parse_status"] = "invalid_range_order"
                entry["record_status"] = "review"
                entry["review_reasons"].append("invalid_range_order")
            else:
                change(rec_id, coords, "value", "range_parsed", "LEX.range", value_text,
                       json.dumps({"low": entry["range_low"], "high": entry["range_high"]}))
        else:
            entry["value"] = dec_plain(parsed["value"])
            entry["uncertainty"] = dec_plain(parsed["uncertainty"])
            change(rec_id, coords, "value", "uncertainty_split", f"LEX.{parsed['unc_notation']}",
                   value_text, json.dumps({"value": entry["value"], "uncertainty": entry["uncertainty"]}),
                   "symmetric uncertainty kept as a separate field; derived bounds are flagged")

        # unit handling
        if not unit_text:
            entry["record_status"] = "review"
            entry["review_reasons"].append("missing_unit")
            review_add(rec_id, coords, "missing_unit", value_text,
                       "value has no unit; standardized columns left empty",
                       "confirm the unit from the original table/figure")
            std = {}
        else:
            try:
                src_uv = parse_unit(unit_text, repo)
                entry["unit"] = unit_text
                tgt_expr = target_overrides.get(entry["metric"]) or target_overrides.get("*") \
                    or default_target(src_uv, repo)
                tgt_uv = parse_unit(tgt_expr, repo)
                if src_uv.key != tgt_uv.key:
                    raise UnitIssue("incompatible_target_unit",
                                    f"dimensions {src_uv.key} cannot convert to {tgt_uv.key}")
                no_op = (src_uv.factor == tgt_uv.factor and src_uv.offset == tgt_uv.offset
                         and not (src_uv.affine or tgt_uv.affine) and unit_text.strip() == tgt_expr.strip())
                if no_op:
                    std = direct_std(parsed)
                    entry["std_unit"] = tgt_expr
                else:
                    cv = convert_parsed(parsed, src_uv, tgt_uv, tgt_expr)
                    std = cv["std"]
                    counters["cv"] += 1
                    mult, add = cv["multiplier"], cv["addend"]
                    ledger = {
                        "id": f"CV{counters['cv']:04d}", "record_id": rec_id,
                        "coordinates": coords, "raw_value": str(raw_value),
                        "raw_unit": unit_text, "target_unit": tgt_expr,
                        "rule_id": "|".join(src_uv.rule_ids + tgt_uv.rule_ids) + "|UC.affine_linear",
                        "component_rules": src_uv.rule_ids + tgt_uv.rule_ids,
                        "formula": f"std = raw * ({dec_plain(mult)}) + ({dec_plain(add)}) "
                                   f"[K-equation base: base = raw*factor + offset; std = (base - target_offset)/target_factor]",
                        "multiplier": dec_plain(mult), "offset": dec_plain(add),
                        "source_factor": dec_plain(src_uv.factor), "source_offset": dec_plain(src_uv.offset),
                        "target_factor": dec_plain(tgt_uv.factor), "target_offset": dec_plain(tgt_uv.offset),
                        "precision_policy": "Decimal 80-digit guard context; no significant-figure rounding; "
                                            "rounded=true marks any inexact Decimal step",
                        "rounded_inexact": cv["rounded"],
                        "value_kind": parsed["kind"],
                        "uncertainty_rule": "offset applied to absolute values only; uncertainty multiplied by |multiplier|"
                        if parsed["kind"] == "symmetric" else "",
                    }
                    for k, v in std.items():
                        ledger[f"std_{k}"] = dec_plain(v) if isinstance(v, Decimal) else v
                    run["ledger"].append(ledger)
                    entry["conversion_rule_ids"] = ledger["rule_id"]
                    entry["std_unit"] = tgt_expr
                    change(rec_id, coords, "value", "unit_converted", ledger["id"],
                           f"{raw_value} {unit_text}", f"target {tgt_expr}",
                           f"multiplier={ledger['multiplier']} offset={ledger['offset']}")
                if src_uv.affine:
                    if parsed["kind"] == "scalar" and std.get("value") is not None and std["value"] < 0:
                        anomaly(rec_id, coords, "negative_absolute_temperature", value_text,
                                "converted absolute temperature below 0 K")
            except UnitIssue as e:
                anomaly(rec_id, coords, e.code, unit_text, e.message,
                        suggestion="add a documented rule to references/units.json or correct the unit")
                entry["record_status"] = "review"
                entry["review_reasons"].append(e.code)
                std = {}
        for k, v in std.items():
            if isinstance(v, Decimal):
                entry[f"std_{k}"] = dec_plain(v)
        if entry["review_reasons"] and entry["record_status"] == "clean":
            entry["record_status"] = "review"
        cleaned.append(entry)

    # ---- conservative duplicate flagging (never auto-merge)
    groups = {}
    for e in cleaned:
        c = e["conditions"]
        signature = (norm_text(e["material"]).lower(), norm_key(e["metric"]),
                     e["std_value"] or e["value"] or e["range_low"], e["std_unit"] or e["raw_unit"],
                     e["std_low"], e["std_high"], e["uncertainty"] or e["std_uncertainty"],
                     json.dumps({k: c.get(k, "") for k in sorted(c) if k not in ("notes",)}, sort_keys=True))
        if not e["material"] or not e["metric"] or not (e["value"] or e["range_low"]):
            continue
        groups.setdefault(signature, []).append(e)
    dup_n = 0
    for sig, members in sorted(groups.items(), key=lambda kv: str(kv[0])):
        if len(members) < 2:
            continue
        dup_n += 1
        gid = f"DUP{dup_n:03d}"
        for m in members:
            m["duplicate_group"] = gid
            m["record_status"] = "review"
            m["review_reasons"].append("duplicate_flag")
        lead = members[0]
        change(lead["record_id"], lead["input_coordinates"], "record", "duplicate_flagged",
               "DEDUP.conservative_key", "", gid,
               "same material+metric+normalized value+unit+conditions+source locators; not merged")
        review_add(lead["record_id"], lead["input_coordinates"], "duplicate_group",
                   gid, f"{len(members)} records share the conservative duplicate key: "
                   + ", ".join(m["input_coordinates"] for m in members),
                   "confirm whether repeated extraction (drop extras) or repeated experiment (keep)")
    run["cleaned"] = cleaned
    n_review = sum(1 for e in cleaned if e["record_status"] == "review")
    run["summary"].update({
        "records_total": len(cleaned), "records_clean": len(cleaned) - n_review,
        "records_review": n_review, "conversions": len(run["ledger"]),
        "anomalies": len(run["anomalies"]), "review_items": len(run["review"]),
        "duplicate_groups": dup_n, "change_records": len(run["changes"]),
        "precision": f"decimal.Decimal, guard precision {CALC_PREC}, no binary floats",
    })
    for e in cleaned:
        src = next((s for s in run["sources"] if s["path"] == e["input_coordinates"].split("#")[0]), None)
    # per-source record counts
    counts = {}
    for e in cleaned:
        path = e["input_coordinates"].split("#")[0]
        counts[path] = counts.get(path, 0) + 1
    for s in run["sources"]:
        s["records"] = counts.get(s["path"], s["records"])
    run["uncertainty"] = [
        {"id": r["id"], "record_id": r["record_id"], "reason": r["reason"],
         "coordinates": r["coordinates"], "detail": r["detail"]} for r in run["review"]]
    run["status"] = "partial" if (n_review or run["anomalies"] or dup_n) else "success"
    finalize_outputs(run, out)
    write_result()
    (out / "audit.md").write_text(audit_md(run, case_path, task_path), encoding="utf-8")
    return run


# ---------------------------------------------------------------------------
# material loaders
# ---------------------------------------------------------------------------

def csv_records(path: Path, base: Path, run: dict):
    data = path.read_bytes()
    run["sources"].append({"path": str(path), "sha256": sha256_bytes(data),
                           "format": "csv", "records": 0})
    text = data.decode("utf-8-sig", errors="replace")
    if not text.strip():
        run["anomalies"].append({"type": "empty_table", "coordinates": f"{path}#csv",
                                 "detail": "CSV file is empty"})
        return []
    reader = csv.DictReader(text.splitlines())
    out = []
    for i, row in enumerate(reader, start=2):
        if all(v in (None, "") for v in row.values()):
            continue
        clean_row = {k: v for k, v in row.items() if k is not None}
        out.append((clean_row, f"{path}#row{i}"))
    return out


def load_material(path: Path, run: dict):
    if path.suffix.lower() == ".csv":
        return csv_records(path, path.parent, run)
    data = path.read_bytes()
    run["sources"].append({"path": str(path), "sha256": sha256_bytes(data),
                           "format": "json", "records": 0})
    try:
        doc = json.loads(data.decode("utf-8-sig"))
    except Exception as e:
        run["anomalies"].append({"type": "malformed_material_json", "coordinates": str(path),
                                 "detail": str(e)})
        return []
    recs = collect_embedded_records(doc)
    return [(r, f"{path}#{c[1:] if c.startswith('$') else c}") for r, c in recs]


# ---------------------------------------------------------------------------
# output writers
# ---------------------------------------------------------------------------
CLEANED_COLUMNS = [
    "record_id", "input_coordinates", "material", "metric", "conditions",
    "raw_value", "raw_unit", "parse_status", "kind", "value", "uncertainty",
    "range_low", "range_high", "unit", "std_unit", "std_value", "std_uncertainty",
    "std_low", "std_high", "std_midpoint_derived", "std_unc_low_derived",
    "std_unc_high_derived", "conversion_rule_ids", "sig_figs", "duplicate_group",
    "record_status", "review_reasons", "extra", "raw_record",
]


def jdump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def dump_csv(path: Path, columns, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            flat = {}
            for c in columns:
                v = r.get(c, "")
                flat[c] = jdump(v) if isinstance(v, (dict, list)) else v
            w.writerow(flat)


def finalize_outputs(run: dict, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    cleaned_rows = [{k: v for k, v in e.items()} for e in run["cleaned"]]
    (out / "cleaned.json").write_text(jdump(cleaned_rows) + "\n", encoding="utf-8")
    for name, obj in [("conversion_ledger", run["ledger"]), ("anomalies", run["anomalies"]),
                      ("review", run["review"]), ("change_log", run["changes"])]:
        (out / f"{name}.json").write_text(jdump(obj) + "\n", encoding="utf-8")
    if run["cleaned"]:
        dump_csv(out / "cleaned.csv", CLEANED_COLUMNS, cleaned_rows)
        run["artifacts"]["cleaned_csv"] = "cleaned.csv"
    else:
        (out / "cleaned.csv").write_text(",".join(CLEANED_COLUMNS) + "\n", encoding="utf-8")
        run["artifacts"]["cleaned_csv"] = "cleaned.csv"
    led_cols = ["id", "record_id", "coordinates", "raw_value", "raw_unit", "target_unit",
                "rule_id", "component_rules", "formula", "multiplier", "offset",
                "source_factor", "source_offset", "target_factor", "target_offset",
                "precision_policy", "rounded_inexact", "value_kind", "uncertainty_rule",
                "std_value", "std_uncertainty", "std_low", "std_high", "std_midpoint_derived",
                "std_unc_low_derived", "std_unc_high_derived"]
    dump_csv(out / "conversion_ledger.csv", led_cols, run["ledger"])
    dump_csv(out / "anomalies.csv", ["id", "record_id", "coordinates", "type", "raw", "detail"], run["anomalies"])
    dump_csv(out / "review.csv", ["id", "record_id", "coordinates", "reason", "raw", "detail", "suggested_action"], run["review"])
    dump_csv(out / "change_log.csv", ["id", "record_id", "coordinates", "field", "action", "rule_id", "from", "to", "note"], run["changes"])
    run["artifacts"].update({
        "cleaned_json": "cleaned.json", "conversion_ledger_json": "conversion_ledger.json",
        "conversion_ledger_csv": "conversion_ledger.csv", "anomalies_json": "anomalies.json",
        "anomalies_csv": "anomalies.csv", "review_json": "review.json", "review_csv": "review.csv",
        "change_log_json": "change_log.json", "change_log_csv": "change_log.csv",
        "audit_md": "audit.md", "result_json": "result.json"})


def audit_md(run: dict, case_path: Path, task_path: Path) -> str:
    s = run["summary"]
    lines = [
        "# Cleaning audit -- quantity ledger", "",
        f"- case_id: `{run['case_id']}`", f"- status: **{run['status']}**",
        f"- skill version: {VERSION} (stdlib Python, Decimal-only arithmetic)",
        f"- case input: `{case_path}`", f"- task input: `{task_path}`", "",
        "## Counts", "",
        f"- records: {s.get('records_total', 0)} (clean {s.get('records_clean', 0)}, review {s.get('records_review', 0)})",
        f"- conversions: {s.get('conversions', 0)}; duplicate groups flagged: {s.get('duplicate_groups', 0)}",
        f"- anomalies: {len(run['anomalies'])}; review items: {len(run['review'])}; change records: {len(run['changes'])}",
        "", "## Sources (sha256)", "",
    ]
    for src in run["sources"]:
        lines.append(f"- `{src['path']}` ({src['format']}): {src['sha256']} -- {src.get('records', 0)} records")
    lines += ["", "## Errors", ""]
    lines += [f"- {e}" for e in run["errors"]] or ["- none"]
    lines += ["", "## Uncertainty / items requiring human confirmation", ""]
    if run["review"]:
        for r in run["review"][:80]:
            lines.append(f"- `{r['id']}` [{r['reason']}] record {r['record_id']} @ `{r['coordinates']}`: {r['detail']}")
        if len(run["review"]) > 80:
            lines.append(f"- ... {len(run['review']) - 80} more in review.json")
    else:
        lines.append("- none")
    lines += ["", "## Method and precision notes", "",
              "- Values are parsed with the grammar in `references/lexical-grammar.md`; ambiguous comma forms and malformed numbers are never guessed.",
              "- Units use the rule table `references/units.json` (rule ids in every ledger row). Unknown or dimensionally incompatible units stay raw and go to review.",
              "- Affine temperature rules (`U.degC`, `U.degF`) apply offsets to absolute values only; uncertainties are scaled by |multiplier| only and remain a separate field.",
              "- Range midpoints and symmetric-uncertainty bounds appear only in `*_derived` columns; they are derived, not reported values.",
              "- Duplicate detection only flags; nothing is merged automatically.",
              "- Every change carries record id + input coordinates + rule id (see change_log.csv).", ""]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------

def main(argv=None):
    here = Path(__file__).resolve().parent
    root = here.parent
    ap = argparse.ArgumentParser(description="Literature extraction cleaning with quantity ledger (Decimal-only).")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--task", default="/input/task.md")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--units", default=str(root / "references" / "units.json"))
    ap.add_argument("--aliases", default=str(root / "references" / "aliases.json"))
    args = ap.parse_args(argv)
    run = process(Path(args.case), Path(args.task), Path(args.work), Path(args.out),
                  Path(args.units), Path(args.aliases))
    return 0 if run["status"] in ("success", "partial") else 2


if __name__ == "__main__":
    sys.exit(main())
