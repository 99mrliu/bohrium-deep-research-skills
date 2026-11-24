#!/usr/bin/env python3
"""next_batch.py -- advance a staged search by one decision.

Inputs:
  --plan     search_plan.json produced by plan_search.py
  --results  CSV of finished experiments; header must contain
             round, <one column per parameter>, response.
             A missing file means "no experiments done yet".
  --log      append-only decision log (JSONL), maintained via the same
             canonical-digest convention as search_log.py
  --output   optional path for the decision JSON (also printed to stdout)

Decision logic (deterministic given plan + results):
  1. budget_exhausted         -> STOP
  2. current round incomplete -> EMIT the missing candidates of that round
  3. screening complete       -> EMIT local-refinement candidates around the
                                 current best point (coordinate finite-
                                 difference stepping, step sizes from the
                                 parameter space, bounds clamped, already-
                                 evaluated points dropped, deterministic
                                 fallback to the nearest unvisited grid point)
  4. refinement complete      -> check low_improvement; if triggered, STOP
                                 (confirmation repeats are then reported as
                                 outstanding), else EMIT confirmation repeats
  5. everything done          -> STOP plan_complete

Also checked: boundary_constrained (best point within one step of the bounds
in every dimension) and all_candidates_duplicate.

Every decision -- EMIT or STOP -- is appended to the decision log with a
sha256 digest of the exact results snapshot it was based on, so a third party
can replay the whole search with search_log.py verify.

Exit codes: 0 decision made, 2 bad input, 3 results-schema error.
Never a traceback.
"""

import argparse
import csv
import hashlib
import itertools
import json
import sys

VERSION = "1.0.0"
EPS = 1e-9
IMPROVEMENT_THRESHOLD = 0.02  # relative improvement below this -> STOP

# --- canonical digest helpers (keep in sync with search_log.py) ---

def canonical_json(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def results_digest(rows):
    return hashlib.sha256(canonical_json(rows).encode("utf-8")).hexdigest()

# --- end of duplicated helpers ---


def fail(msg, code=2):
    sys.stdout.write(json.dumps({"status": "error", "error": msg},
                                ensure_ascii=False, indent=2) + "\n")
    sys.exit(code)


def load_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        fail("file not found: %s" % path)
    except json.JSONDecodeError as exc:
        fail("invalid JSON in %s: %s" % (path, exc))
    except OSError as exc:
        fail("cannot read %s: %s" % (path, exc))


def load_results(path, params):
    """Parse the results CSV.  Missing file -> zero rows."""
    names = [p["name"] for p in params]
    required = ["round"] + names + ["response"]
    import os
    if not os.path.exists(path):
        return [], []
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                fail("results CSV %s has no header" % path, code=3)
            missing = [c for c in required if c not in reader.fieldnames]
            if missing:
                fail("results CSV %s is missing required column(s): %s "
                     "(required: %s)" % (path, ", ".join(missing),
                                         ", ".join(required)), code=3)
            rows, warnings = [], []
            for lineno, raw in enumerate(reader, 2):
                try:
                    row = {"round": int(float(raw["round"]))}
                    for n in names:
                        row[n] = float(raw[n])
                    row["response"] = float(raw["response"])
                except (TypeError, ValueError):
                    warnings.append("line %d skipped (non-numeric value)" % lineno)
                    continue
                rows.append(row)
            return rows, warnings
    except OSError as exc:
        fail("cannot read results CSV %s: %s" % (path, exc), code=3)


def pkey_from_values(point, params):
    return tuple(round(float(point[p["name"]]), 10) for p in params)


def is_better(a, b, objective):
    return a > b if objective == "maximize" else a < b


def best_of(rows, objective):
    if not rows:
        return None
    best = rows[0]
    for r in rows[1:]:
        if is_better(r["response"], best["response"], objective):
            best = r
    return best


def refinement_candidates(plan, rows):
    """Coordinate finite-difference stepping around the current best point."""
    params = plan["parameters"]
    objective = plan["objective"]
    best = best_of(rows, objective)
    if best is None:
        return [], None, "no evaluated points yet"
    seen = {pkey_from_values(r, params) for r in rows}
    cand = []
    for p in params:                      # fixed dimension order
        for direction in (-1.0, 1.0):     # -step first, then +step
            pt = {q["name"]: best[q["name"]] for q in params}
            v = best[p["name"]] + direction * p["step"]
            if v < p["lower"] - EPS or v > p["upper"] + EPS:
                continue
            pt[p["name"]] = round(v, 10)
            key = pkey_from_values(pt, params)
            if key not in seen:
                seen.add(key)
                cand.append(pt)
    return cand, best, "coordinate finite-difference stepping around best point"


def fallback_unvisited(plan, rows):
    """Nearest unvisited grid point to the best point (deterministic scan)."""
    params = plan["parameters"]
    best = best_of(rows, plan["objective"])
    seen = {pkey_from_values(r, params) for r in rows}
    names = [p["name"] for p in params]
    center = [best[n] for n in names]
    all_pts = itertools.product(*[
        [round(p["lower"] + i * p["step"], 10) for i in range(p["n_levels"])]
        for p in params])
    best_pt, best_d = None, None
    for combo in all_pts:
        if combo in seen:
            continue
        d = sum((a - b) ** 2 for a, b in zip(combo, center))
        if best_d is None or d < best_d:
            best_pt, best_d = dict(zip(names, combo)), d
    return best_pt


def boundary_state(plan, best):
    if best is None:
        return {"triggered": False, "within_one_step_dims": []}
    dims = []
    for p in plan["parameters"]:
        v = best[p["name"]]
        if (v - p["lower"] < p["step"] - EPS or
                p["upper"] - v < p["step"] - EPS):
            dims.append(p["name"])
    return {"triggered": len(dims) == len(plan["parameters"]),
            "within_one_step_dims": dims}


def append_log(log_path, round_no, points, rows, decision, criteria):
    import os
    seq = 1
    if os.path.exists(log_path):
        try:
            with open(log_path, encoding="utf-8") as fh:
                last = None
                for line in fh:
                    line = line.strip()
                    if line:
                        last = line
            if last is not None:
                seq = int(json.loads(last).get("seq", 0)) + 1
        except (OSError, ValueError, AttributeError):
            fail("decision log %s is unreadable; refusing to append" % log_path)
    record = {
        "seq": seq,
        "round": round_no,
        "points": points,
        "results": rows,
        "results_digest": results_digest(rows),
        "decision": decision,
        "criterion_states": criteria,
    }
    try:
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(canonical_json(record) + "\n")
    except OSError as exc:
        fail("cannot append to log %s: %s" % (log_path, exc))
    return seq


def improvement_between(rows, round_a, round_b, objective):
    ra = [r for r in rows if r["round"] == round_a]
    rb = [r for r in rows if r["round"] == round_b]
    if not ra or not rb:
        return None
    ba = best_of(ra, objective)["response"]
    bb = best_of(rb, objective)["response"]
    denom = max(abs(ba), 1e-12)
    return ((bb - ba) / denom) if objective == "maximize" else ((ba - bb) / denom)


def decide(plan, rows, warnings):
    params = plan["parameters"]
    objective = plan.get("objective", "maximize")
    budget = int(plan.get("budget", 0))
    used = len(rows)
    remaining = budget - used
    strategy = plan.get("strategy", "unknown")
    rounds = plan.get("rounds") or []
    best = best_of(rows, objective)
    bstate = boundary_state(plan, best)

    criteria = {
        "budget_exhausted": {"used": used, "budget": budget,
                             "triggered": used >= budget},
        "low_improvement": {"applicable": False, "value": None,
                            "threshold": IMPROVEMENT_THRESHOLD,
                            "triggered": False},
        "boundary_constrained": bstate,
        "all_candidates_duplicate": {"triggered": False},
    }

    def stop(criterion, round_no, reason):
        criteria_key = criterion if criterion in criteria else None
        if criteria_key:
            criteria[criteria_key]["triggered"] = True
        return {
            "status": "STOP", "stop_criterion": criterion,
            "next_round": round_no, "points": [], "rationale": reason,
            "criterion_states": criteria,
            "budget": {"total": budget, "used": used, "remaining": remaining},
            "warnings": warnings,
            "best_point": best,
        }

    def emit(round_no, stage, points, reason):
        return {
            "status": "CONTINUE", "stop_criterion": None,
            "next_round": round_no, "stage": stage, "points": points,
            "rationale": reason, "criterion_states": criteria,
            "budget": {"total": budget, "used": used, "remaining": remaining},
            "warnings": warnings,
            "best_point": best,
        }

    if strategy == "none":
        return stop("no_budget", 0,
                    "plan strategy is 'none' (budget was <= 0); nothing to run")
    if used >= budget:
        return stop("budget_exhausted", rounds[-1]["round"] if rounds else 0,
                    "evaluated %d of %d new points; budget exhausted"
                    % (used, budget))
    if not rounds:
        return stop("empty_plan", 0, "plan contains no rounds")

    names = [p["name"] for p in params]
    counts = {rd["round"]: sum(1 for r in rows if r["round"] == rd["round"])
              for rd in rounds}

    # --- full grid / screening-only: fixed candidate lists ----------------
    if strategy in ("full_grid", "screening_only"):
        rd = rounds[0]
        candidates = rd.get("candidates") or []
        seen = {pkey_from_values(r, params) for r in rows}
        todo = [c for c in candidates
                if tuple(round(float(c[n]), 10) for n in names) not in seen]
        if not todo:
            return stop("plan_complete", rd["round"],
                        "all %d planned candidates evaluated" % len(candidates))
        batch = todo[:remaining]
        return emit(rd["round"], rd["name"], batch,
                    "emitting %d of %d remaining planned %s candidates"
                    % (len(batch), len(todo), rd["name"]))

    # --- staged sequential -------------------------------------------------
    r1, r2, r3 = (rounds + [None, None, None])[:3]
    if r1 and counts.get(r1["round"], 0) < r1["n_points"]:
        candidates = r1.get("candidates") or []
        seen = {pkey_from_values(r, params) for r in rows}
        todo = [c for c in candidates
                if tuple(round(float(c[n]), 10) for n in names) not in seen]
        batch = todo[:remaining]
        if not batch:
            return stop("all_candidates_duplicate", r1["round"],
                        "every screening candidate was already evaluated")
        return emit(r1["round"], r1["name"], batch,
                    "screening round incomplete (%d/%d); emitting %d seeded-LHS "
                    "candidate(s)" % (counts.get(r1["round"], 0),
                                      r1["n_points"], len(batch)))

    if r2 and counts.get(r2["round"], 0) < r2["n_points"]:
        if bstate["triggered"]:
            return stop("boundary_constrained", r2["round"],
                        "best point is within one step of the bounds in every "
                        "dimension (%s); local refinement cannot move"
                        % ", ".join(bstate["within_one_step_dims"]))
        cand, _, how = refinement_candidates(plan, rows)
        need = min(r2["n_points"] - counts.get(r2["round"], 0), remaining)
        batch = cand[:need]
        rule = how
        if not batch:
            fb = fallback_unvisited(plan, rows)
            if fb is None:
                return stop("all_candidates_duplicate", r2["round"],
                            "all refinement candidates duplicate evaluated "
                            "points and no unvisited grid point exists")
            batch, rule = [fb], ("fallback: nearest unvisited grid point "
                                 "(deterministic expanding scan)")
        return emit(r2["round"], r2["name"], batch,
                    "screening complete; %s; emitting %d point(s)"
                    % (rule, len(batch)))

    if r3 and counts.get(r3["round"], 0) < r3["n_points"]:
        imp = improvement_between(rows, r1["round"], r2["round"], objective) \
            if r1 and r2 else None
        criteria["low_improvement"].update(
            {"applicable": imp is not None, "value": imp,
             "triggered": imp is not None and imp < IMPROVEMENT_THRESHOLD})
        if imp is not None and imp < IMPROVEMENT_THRESHOLD:
            return stop("low_improvement", r3["round"],
                        "relative improvement of the best response from round "
                        "%d to round %d is %.4f%% (< %.0f%%); search converged. "
                        "Confirmation repeats of the best point are still "
                        "recommended and must be tracked as confirmation items."
                        % (r1["round"], r2["round"], imp * 100,
                           IMPROVEMENT_THRESHOLD * 100))
        need = min(r3["n_points"] - counts.get(r3["round"], 0), remaining)
        base = {n: best[n] for n in names}
        k0 = counts.get(r3["round"], 0)
        batch = [dict(base, replicate=k0 + i + 1) for i in range(need)]
        return emit(r3["round"], r3["name"], batch,
                    "refinement improved the best response by %.2f%% (>= %.0f%%); "
                    "emitting %d confirmation repeat(s) of the best point to "
                    "estimate noise"
                    % ((imp or 0.0) * 100, IMPROVEMENT_THRESHOLD * 100,
                       len(batch)))

    return stop("plan_complete", rounds[-1]["round"],
                "all planned rounds completed")


def main(argv=None):
    ap = argparse.ArgumentParser(description="advance a staged search")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--output", default=None)
    args = ap.parse_args(argv)
    plan = load_json(args.plan)
    if not isinstance(plan, dict) or "parameters" not in plan:
        fail("%s does not look like a search_plan.json (missing 'parameters')"
             % args.plan)
    rows, warnings = load_results(args.results, plan["parameters"])
    decision = decide(plan, rows, warnings)
    decision["schema_version"] = VERSION
    seq = append_log(args.log, decision.get("next_round", 0),
                     decision["points"], rows,
                     ("%s (%s): %s" % (decision["status"],
                                       decision.get("stop_criterion") or
                                       decision.get("stage", "-"),
                                       decision["rationale"])),
                     decision["criterion_states"])
    decision["log_seq"] = seq
    text = json.dumps(decision, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as exc:
            fail("cannot write %s: %s" % (args.output, exc))
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # last-resort guard: never leak a traceback
        fail("unexpected error: %s: %s" % (type(exc).__name__, exc), code=2)
