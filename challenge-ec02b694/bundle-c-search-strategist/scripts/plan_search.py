#!/usr/bin/env python3
"""plan_search.py -- budget-aware sequential search planner (deterministic).

Reads a parameter-space JSON + an experiment-point budget + the number of
already-existing history points, and emits search_plan.json describing:

  * which strategy was chosen and why (explicit decision table);
  * the candidate points of every round whose points can be fixed in advance
    (screening / full grid), all numerically determined by a fixed seed;
  * the deterministic generation rule for data-dependent rounds
    (local refinement / confirmation repeats), instantiated later by
    next_batch.py and pinned down in the append-only decision log;
  * per-round and global stopping criteria;
  * the reproduction seed.

Strategy decision table (applied in order):
  1. budget <= 0                     -> strategy "none" (no rounds).
  2. feasible combinations <= budget -> strategy "full_grid".
  3. budget < 4                      -> strategy "screening_only"
       (seeded LHS over the whole budget; confirmation repeats skipped).
  4. otherwise                       -> strategy "staged_sequential":
       screening (seeded LHS, ~40% of budget, min 2)
       -> local refinement (coordinate finite-difference stepping around the
          current best point, step sizes respect each parameter's `step`)
       -> confirmation repeats (>= 2 replicates of the best point to estimate
          noise).

Pure Python 3 standard library, no network.  Any malformed input produces a
JSON error object on stdout and a non-zero exit code -- never a traceback.
"""

import argparse
import itertools
import json
import math
import random
import sys

VERSION = "1.0.0"
EPS = 1e-9


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


def parse_space(space):
    if not isinstance(space, dict):
        fail("parameter space must be a JSON object")
    raw = space.get("parameters")
    if not isinstance(raw, list) or not raw:
        fail("parameter space must contain a non-empty 'parameters' list")
    params = []
    seen_names = set()
    for i, p in enumerate(raw):
        if not isinstance(p, dict):
            fail("parameter #%d is not an object" % i)
        try:
            name = str(p["name"])
            lower = float(p["lower"])
            upper = float(p["upper"])
            step = float(p["step"])
        except KeyError as exc:
            fail("parameter #%d missing field %s" % (i, exc))
        except (TypeError, ValueError):
            fail("parameter #%d has non-numeric lower/upper/step" % i)
        if name in seen_names:
            fail("duplicate parameter name: %s" % name)
        seen_names.add(name)
        if not lower < upper:
            fail("parameter '%s': lower must be < upper" % name)
        if step <= 0:
            fail("parameter '%s': step must be > 0" % name)
        n_levels = int(math.floor((upper - lower) / step + EPS)) + 1
        params.append({
            "name": name,
            "lower": lower,
            "upper": upper,
            "step": step,
            "unit": str(p.get("unit", "")),
            "kind": str(p.get("type", "continuous")),
            "n_levels": n_levels,
        })
    objective = str(space.get("objective", "maximize")).lower()
    if objective not in ("maximize", "minimize"):
        fail("objective must be 'maximize' or 'minimize', got: %s" % objective)
    return params, objective


def levels(p):
    return [round(p["lower"] + i * p["step"], 10) for i in range(p["n_levels"])]


def feasible_combinations(params):
    total = 1
    for p in params:
        total *= p["n_levels"]
    return total


def snap(v, p):
    """Snap a raw value to the parameter's step grid and clamp to bounds."""
    k = round((v - p["lower"]) / p["step"])
    v = p["lower"] + k * p["step"]
    return round(min(max(v, p["lower"]), p["upper"]), 10)


def pkey(point, params):
    return tuple(point[p["name"]] for p in params)


def nudge(params, point, seen):
    """Deterministically move a duplicate point to a nearby free grid point.

    Scans coordinate neighbourhoods at radius 1, then 2, in a fixed
    lexicographic order.  Returns the original (duplicated) point only if no
    free neighbour exists; callers record that fact.
    """
    names = [p["name"] for p in params]
    for radius in (1, 2):
        offsets = range(-radius, radius + 1)
        for combo in itertools.product(offsets, repeat=len(params)):
            if all(o == 0 for o in combo):
                continue
            cand = {}
            ok = True
            for p, o in zip(params, combo):
                v = point[p["name"]] + o * p["step"]
                if v < p["lower"] - EPS or v > p["upper"] + EPS:
                    ok = False
                    break
                cand[p["name"]] = round(v, 10)
            if ok and tuple(cand[n] for n in names) not in seen:
                return cand, True
    return point, False


def lhs_points(params, n, seed):
    """Seeded Latin-hypercube sample snapped to each parameter's step grid.

    Fully determined by (params, n, seed): random.Random(seed) drives both the
    per-dimension stratum permutation and the within-stratum uniform offset.
    """
    rng = random.Random(seed)
    cols = []
    for p in params:
        strata = list(range(n))
        rng.shuffle(strata)
        col = []
        for s in strata:
            frac = (s + rng.random()) / n
            col.append(snap(p["lower"] + frac * (p["upper"] - p["lower"]), p))
        cols.append(col)
    points, seen = [], set()
    nudged = 0
    for i in range(n):
        pt = {params[j]["name"]: cols[j][i] for j in range(len(params))}
        key = pkey(pt, params)
        if key in seen:
            pt, moved = nudge(params, pt, seen)
            if moved:
                nudged += 1
        seen.add(pkey(pt, params))
        points.append(pt)
    return points, nudged


def grid_points(params, cap=200000):
    total = feasible_combinations(params)
    if total > cap:
        return None
    names = [p["name"] for p in params]
    return [dict(zip(names, combo))
            for combo in itertools.product(*(levels(p) for p in params))]


def build_plan(space, budget, history, seed):
    params, objective = parse_space(space)
    combos = feasible_combinations(params)
    plan = {
        "schema_version": VERSION,
        "seed": seed,
        "objective": objective,
        "budget": budget,
        "history_points": history,
        "parameters": params,
        "feasible_combinations": combos,
        "decision_table": [
            {"rule": 1, "condition": "budget <= 0", "strategy": "none"},
            {"rule": 2, "condition": "feasible_combinations <= budget",
             "strategy": "full_grid"},
            {"rule": 3, "condition": "budget < 4",
             "strategy": "screening_only"},
            {"rule": 4, "condition": "otherwise",
             "strategy": "staged_sequential"},
        ],
        "rounds": [],
    }
    if budget <= 0:
        plan["strategy"] = "none"
        plan["strategy_rationale"] = (
            "rule 1 fired: experiment budget is %d; no new points can be run. "
            "Only the %d existing history points are available." % (budget, history))
        plan["global_stop_criteria"] = []
        return plan

    if combos <= budget:
        plan["strategy"] = "full_grid"
        plan["strategy_rationale"] = (
            "rule 2 fired: feasible combinations (%d) <= budget (%d), so an "
            "exhaustive grid is affordable and dominates any sampler." % (combos, budget))
        pts = grid_points(params)
        plan["rounds"].append({
            "round": 1, "name": "full_grid", "n_points": len(pts),
            "budget_share": 1.0, "candidates": pts,
            "candidates_determined": True,
            "stop_criteria": ["budget_exhausted"],
        })
        plan["global_stop_criteria"] = ["budget_exhausted"]
        return plan

    if budget < 4:
        pts, nudged = lhs_points(params, budget, seed)
        plan["strategy"] = "screening_only"
        plan["strategy_rationale"] = (
            "rule 3 fired: budget (%d) too small for the three-stage design "
            "(screening + refinement + >=2 confirmation repeats); spending the "
            "whole budget on a seeded LHS screening round." % budget)
        plan["rounds"].append({
            "round": 1, "name": "screening_lhs", "n_points": len(pts),
            "budget_share": 1.0, "candidates": pts,
            "candidates_determined": True, "lhs_duplicates_nudged": nudged,
            "stop_criteria": ["budget_exhausted"],
        })
        plan["global_stop_criteria"] = ["budget_exhausted"]
        return plan

    # rule 4: staged sequential design
    n_screen = max(2, int(round(0.4 * budget)))
    n_screen = min(n_screen, budget - 2)          # keep room for confirmation
    n_confirm = max(2, int(round(0.2 * budget)))
    n_confirm = min(n_confirm, budget - n_screen - 1)
    n_refine = budget - n_screen - n_confirm
    if n_refine < 1:                               # defensive; keep >=1 refine
        n_confirm = max(2, n_confirm + n_refine - 1)
        n_refine = budget - n_screen - n_confirm
    pts, nudged = lhs_points(params, n_screen, seed)
    plan["strategy"] = "staged_sequential"
    plan["strategy_rationale"] = (
        "rule 4 fired: %d combinations exceed the budget (%d). Budget split: "
        "screening %d (%.0f%%), local refinement %d, confirmation repeats %d. "
        "%d history points are recorded for context but do not consume the new "
        "budget." % (combos, budget, n_screen, 100.0 * n_screen / budget,
                     n_refine, n_confirm, history))
    plan["rounds"] = [
        {
            "round": 1, "name": "screening_lhs", "n_points": n_screen,
            "budget_share": round(n_screen / budget, 4),
            "candidates": pts, "candidates_determined": True,
            "lhs_duplicates_nudged": nudged,
            "generation_rule": "seeded Latin hypercube, random.Random(%d), "
                               "stratified per dimension, snapped to step grid" % seed,
            "stop_criteria": ["budget_exhausted"],
        },
        {
            "round": 2, "name": "local_refinement", "n_points": n_refine,
            "budget_share": round(n_refine / budget, 4),
            "candidates": None, "candidates_determined": False,
            "generation_rule": (
                "coordinate finite-difference stepping around the current best "
                "point: for each dimension in plan order try -step then +step, "
                "clamp to bounds, drop already-evaluated points, take the first "
                "n_points survivors; if none survive, fall back to the nearest "
                "unvisited grid point (deterministic expanding-radius scan). "
                "next_batch.py instantiates this rule; the exact points are "
                "pinned in the decision log and are reproducible from the seed "
                "plus the results CSV."),
            "stop_criteria": ["budget_exhausted", "low_improvement",
                              "boundary_constrained", "all_candidates_duplicate"],
        },
        {
            "round": 3, "name": "confirmation_repeat", "n_points": n_confirm,
            "budget_share": round(n_confirm / budget, 4),
            "candidates": None, "candidates_determined": False,
            "generation_rule": (
                "re-run the current best point >= 2 times (identical "
                "coordinates, distinct replicate ids) to estimate noise."),
            "stop_criteria": ["budget_exhausted"],
        },
    ]
    plan["global_stop_criteria"] = [
        {"name": "budget_exhausted",
         "definition": "evaluated new points >= budget"},
        {"name": "low_improvement",
         "definition": "relative improvement of the best response between the "
                       "last two completed search rounds < 2%; when it fires "
                       "before the confirmation round, the repeats are skipped "
                       "and reported as outstanding confirmation items"},
        {"name": "boundary_constrained",
         "definition": "the current best point lies within one step of the "
                       "bounds in EVERY dimension"},
        {"name": "all_candidates_duplicate",
         "definition": "every generated candidate was already evaluated and "
                       "no unvisited fallback grid point exists"},
    ]
    plan["replay_instructions"] = (
        "Re-run plan_search.py with the same --space/--budget/--history/--seed "
        "to reproduce this plan byte-for-byte. Re-run next_batch.py with this "
        "plan and the same results CSV to reproduce every emitted batch; "
        "search_log.py --verify re-checks the append-only decision log.")
    return plan


def main(argv=None):
    ap = argparse.ArgumentParser(description="deterministic search planner")
    ap.add_argument("--space", required=True, help="parameter space JSON")
    ap.add_argument("--budget", required=True, help="experiment-point budget (int)")
    ap.add_argument("--history", default="0", help="existing history points (int)")
    ap.add_argument("--seed", default="2024", help="reproduction seed (int)")
    ap.add_argument("--output", help="write search_plan.json here (default: stdout)")
    args = ap.parse_args(argv)
    try:
        budget = int(str(args.budget))
        history = int(str(args.history))
        seed = int(str(args.seed))
    except ValueError:
        fail("--budget/--history/--seed must be integers")
    if history < 0:
        fail("--history must be >= 0")
    space = load_json(args.space)
    plan = build_plan(space, budget, history, seed)
    text = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as exc:
            fail("cannot write %s: %s" % (args.output, exc))
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # last-resort guard: never leak a traceback
        fail("unexpected error: %s: %s" % (type(exc).__name__, exc), code=2)
