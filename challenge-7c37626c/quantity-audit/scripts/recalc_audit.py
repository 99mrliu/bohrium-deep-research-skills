#!/usr/bin/env python3
"""Audit engine: evaluate each claim's formula in SI, check dimensions,
compare the recomputed value with the reported value, and write the audit
ledger. Verdicts: PASS, MISMATCH, DIM_MISMATCH, BLOCKED, UNPARSEABLE.
Stdlib only.
"""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from latex_ast import parse_formula, ast_symbols, ParseError_
from si_engine import (CODATA, UnitError, dim_add, dim_eq, dim_scale,
                       dim_str, parse_unit, to_si, from_si)


class EvalError(ValueError):
    pass


def evaluate(node, env):
    """Return (si_value, dim_vector). env: name -> (si_value, dim)."""
    tag = node[0]
    if tag == "num":
        return node[1], {}
    if tag == "sym":
        name = node[1]
        if name in env:
            return env[name]
        if name in CODATA:
            v, u = CODATA[name]
            return to_si(v, u)
        raise EvalError("unbound symbol %r (no value in binding, not a known "
                        "CODATA constant)" % name)
    if tag == "add":
        va, da = evaluate(node[1], env)
        vb, db = evaluate(node[2], env)
        if not dim_eq(da, db):
            raise EvalError("addition of incompatible dims [%s] + [%s]"
                            % (dim_str(da), dim_str(db)))
        return va + vb, da
    if tag == "mul":
        va, da = evaluate(node[1], env)
        vb, db = evaluate(node[2], env)
        return va * vb, dim_add(da, db)
    if tag == "div":
        va, da = evaluate(node[1], env)
        vb, db = evaluate(node[2], env)
        if vb == 0:
            raise EvalError("division by zero")
        return va / vb, dim_add(da, dim_scale(db, -1))
    if tag == "pow":
        va, da = evaluate(node[1], env)
        ve, de = evaluate(node[2], env)
        if de:
            raise EvalError("exponent carries dimensions [%s]" % dim_str(de))
        if node[2][0] != "num":
            raise EvalError("non-literal exponent not auditable")
        from fractions import Fraction
        p = Fraction(ve).limit_denominator(1000)
        return va ** float(ve), dim_scale(da, p)
    if tag == "func":
        name, arg = node[1], node[2]
        va, da = evaluate(arg, env)
        if da:
            raise EvalError("%s() of a dimensional quantity [%s]"
                            % (name, dim_str(da)))
        fn = {"exp": math.exp, "log": math.log10, "ln": math.log,
              "sin": math.sin, "cos": math.cos, "tan": math.tan,
              "abs": abs}.get(name)
        if fn is None:
            raise EvalError("unsupported function %s" % name)
        return fn(va), {}
    if tag == "apply":
        # f(x) on the LHS names the dependent symbol; RHS expressions carry
        # the computation. When an apply appears inside an expression it is
        # not evaluable without a model of f -> BLOCKED.
        raise EvalError("application %s(...) not evaluable" % (node[1],))
    raise EvalError("unknown AST node %r" % (node,))


def lhs_symbol(lhs_ast):
    if lhs_ast is None:
        return None
    if lhs_ast[0] == "sym":
        return lhs_ast[1]
    if lhs_ast[0] == "apply" and lhs_ast[1][0] == "sym":
        return lhs_ast[1][1]
    return None


def audit_claim(claim):
    cid = claim.get("claim_id", "?")
    row = {"claim_id": cid, "verdict": None, "detail": {}}
    try:
        lhs, rhs = parse_formula(claim["formula_latex"])
    except ParseError_ as exc:
        row["verdict"] = "UNPARSEABLE"
        row["detail"]["parser_error"] = str(exc)
        return row
    except KeyError:
        row["verdict"] = "BLOCKED"
        row["detail"]["reason"] = "claim has no formula_latex"
        return row

    binding = claim.get("binding") or {}
    env = {}
    unknown = []
    for sym in sorted(ast_symbols(rhs)):
        if sym in CODATA:
            continue
        spec = binding.get(sym)
        if spec is None:
            unknown.append("%s (no binding entry)" % sym)
            continue
        if spec.get("unknown"):
            unknown.append("%s (marked unknown; sought at %s)"
                           % (sym, spec.get("sought_at", "unspecified")))
            continue
        try:
            env[sym] = to_si(spec["value"], spec.get("unit", ""))
        except UnitError as exc:
            row["verdict"] = "BLOCKED"
            row["detail"]["reason"] = "unit for %s: %s" % (sym, exc)
            return row
        except KeyError:
            unknown.append("%s (binding lacks 'value')" % sym)
    if unknown:
        row["verdict"] = "BLOCKED"
        row["detail"]["missing"] = unknown
        return row

    try:
        rhs_val, rhs_dim = evaluate(rhs, env)
    except EvalError as exc:
        row["verdict"] = "BLOCKED"
        row["detail"]["reason"] = str(exc)
        return row

    det = row["detail"]
    det["rhs_si_value"] = "%.6g" % rhs_val
    det["rhs_dim"] = dim_str(rhs_dim)
    det["lhs_symbol"] = lhs_symbol(lhs)

    reported = claim.get("reported")
    if not reported:
        row["verdict"] = "PASS_COMPUTED_ONLY"
        det["note"] = "no reported value to compare; recomputation recorded"
        return row
    try:
        _, rep_dim = parse_unit(reported.get("unit", ""))
    except UnitError as exc:
        row["verdict"] = "BLOCKED"
        det["reason"] = "reported unit: %s" % exc
        return row
    det["dims_match"] = dim_eq(rhs_dim, rep_dim)
    if not det["dims_match"]:
        row["verdict"] = "DIM_MISMATCH"
        det["reported_dim"] = dim_str(rep_dim)
        return row
    rep_in_rep_unit = reported.get("value")
    recomputed_in_rep_unit = from_si(rhs_val, reported.get("unit", ""))
    det["recomputed_in_reported_unit"] = "%.6g" % recomputed_in_rep_unit
    det["reported_value"] = rep_in_rep_unit
    det["reported_unit"] = reported.get("unit", "")
    if rep_in_rep_unit in (None, 0):
        rel = float("inf") if recomputed_in_rep_unit else 0.0
    else:
        rel = abs(recomputed_in_rep_unit - rep_in_rep_unit) / abs(rep_in_rep_unit)
    det["relative_error"] = "%.3g" % rel
    tol = float(claim.get("tolerance_rel", 0.02))
    det["tolerance_rel"] = tol
    row["verdict"] = "PASS" if rel <= tol else "MISMATCH"
    if rel > tol:
        om = math.log10(abs(recomputed_in_rep_unit) / abs(rep_in_rep_unit)) \
            if rep_in_rep_unit else float("nan")
        det["order_of_magnitude_shift"] = "%.2f decades" % om
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--claims", required=True)
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    args = ap.parse_args()
    claims = json.loads(Path(args.claims).read_text(encoding="utf-8"))
    rows = [audit_claim(c) for c in claims.get("claims", [])]
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    ledger = {"claims_source": args.claims, "verdict_counts": counts, "rows": rows}
    work, out = Path(args.work), Path(args.out)
    work.mkdir(parents=True, exist_ok=True)
    (work / "audit_ledger.json").write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in rows:
        print("%-28s %s" % (r["claim_id"], r["verdict"]))
    print("ledger -> %s" % (work / "audit_ledger.json"))

    # Fold into result.json when present (keeps contract fields untouched).
    rp = out / "result.json"
    if rp.exists():
        result = json.loads(rp.read_text(encoding="utf-8"))
        blocked = [r["claim_id"] for r in rows if r["verdict"] in ("BLOCKED", "UNPARSEABLE")]
        if not rows:
            result["status"] = "insufficient_evidence"
        elif blocked:
            result["status"] = "partial"
        else:
            result["status"] = "success"
        result.setdefault("answers", {})["audit"] = {
            "verdict_counts": counts,
            "ledger_path": str(work / "audit_ledger.json"),
        }
        result.setdefault("uncertainty", {})["blocked_claims"] = blocked
        result.setdefault("artifacts", {})["audit_ledger"] = str(work / "audit_ledger.json")
        rp.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                      encoding="utf-8")
        print("result.json status -> %s" % result["status"])


if __name__ == "__main__":
    main()
