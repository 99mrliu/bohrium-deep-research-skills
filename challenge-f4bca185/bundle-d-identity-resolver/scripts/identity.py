"""Identity keys, deterministic candidate blocking, pairwise evidence
scoring and conservative clustering.

Decision states (rule ids D-001..D-009, see references/identity-adjudication.md):
  exact_duplicate     - repeated extraction of the same row (merge)
  likely_duplicate    - same identity and equal value, minor surface diff (merge, logged)
  conflict            - same identity, different measured values (NEVER merged/averaged)
  review              - insufficient or ambiguous evidence (kept separate, queued)
  not_duplicate       - different sample/context/source or independent replicate

Hard guarantees:
  * no pair across different sources is ever merged;
  * no pair across different context keys is ever even compared for merging;
  * conflicting measured values are never averaged; both rows are retained.
"""
from __future__ import annotations

import json
from typing import Any

# evidence weights, exposed for transparency; decisions are rule-driven,
# the score only orders the review queue.
WEIGHTS = {
    "same_source": 3, "same_sample": 3, "same_metric": 2,
    "same_context": 2, "value_equal": 4, "same_locator": 1,
    "same_experiment_label": 1, "full_fingerprint_equal": 2,
}


def sample_key(rec: dict) -> str:
    parts = [
        "m=" + (rec["material"] or "?"),
        "p=" + (rec["phase"] or "-"),
        "d=" + (rec["dopant"] or "-"),
        "c=" + (rec["composition"] or "-"),
        "f=" + (rec["morphology"] or "-"),
    ]
    return "|".join(parts)


def metric_key(rec: dict) -> str:
    return rec["metric"] or "?"


def context_key(rec: dict) -> str:
    ctx = rec.get("context") or {}
    if not any(v is not None for v in ctx.values()):
        return "context:unspecified"
    return "context:" + json.dumps(ctx, sort_keys=True, ensure_ascii=False)


def source_key(rec: dict) -> str:
    return rec["source_key"]


def fingerprint(rec: dict) -> str:
    """Full normalized identity fingerprint (canonical fields + extras)."""
    obj = {
        "material": rec["material"], "phase": rec["phase"], "dopant": rec["dopant"],
        "composition": rec["composition"], "morphology": rec["morphology"],
        "metric": rec["metric"], "value_kind": rec["value_kind"],
        "value": rec["value"], "value_min": rec.get("value_min"),
        "value_max": rec.get("value_max"), "unit": rec["unit"],
        "source": rec["source_key"], "locator": rec["locator"],
        "experiment": rec["experiment_label"], "context": rec["context"],
        "extra": rec.get("extra") or {},
    }
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def block_keys(rec: dict) -> dict[str, str]:
    return {
        "dedup_block": "|".join([source_key(rec), sample_key(rec),
                                 metric_key(rec), context_key(rec)]),
        "xsource_block": "|".join([sample_key(rec), metric_key(rec),
                                   context_key(rec), rec.get("value_token") or "?"]),
    }


# ---------------------------------------------------------------------------

def _value_relation(a: dict, b: dict) -> tuple[str, str]:
    """-> (relation, reason); relation in equal/different/unknown."""
    if a["value_kind"] == "missing" or b["value_kind"] == "missing":
        return "unknown", "missing_value"
    if a["value_kind"] != b["value_kind"]:
        return "unknown", "incompatible_value_kinds"
    if a["value_kind"] == "range":
        if a.get("value_min") == b.get("value_min") and a.get("value_max") == b.get("value_max"):
            return "equal", "range_equal"
        return "different", "range_different"
    if a["value_kind"] == "text":
        if a.get("value_text") == b.get("value_text"):
            return "equal", "text_equal"
        return "different", "text_different"
    # scalar
    an, bn = a.get("value_normalized"), b.get("value_normalized")
    a_un_ok = a.get("unit_status") == "known"
    b_un_ok = b.get("unit_status") == "known"
    if an is not None and bn is not None and a.get("unit_normalized") == b.get("unit_normalized"):
        from lexicon import values_equal  # same-dir module, scripts dir on sys.path
        return ("equal", "value_equal_after_conversion") if values_equal(an, bn) \
            else ("different", "value_different")
    if a_un_ok and b_un_ok and a.get("unit_normalized") != b.get("unit_normalized"):
        return "different", "unit_dimension_mismatch"
    if a["value"] == b["value"]:
        return "equal", "value_equal_raw_unresolved_unit"
    if not a_un_ok or not b_un_ok:
        return "unknown", "unit_unresolved"
    return "different", "value_different"


def compare_pair(a: dict, b: dict) -> dict:
    """Deterministic pairwise adjudication with explainable evidence."""
    ev = {
        "same_source": a["source_key"] == b["source_key"],
        "same_sample": sample_key(a) == sample_key(b),
        "same_metric": metric_key(a) == metric_key(b),
        "same_context": context_key(a) == context_key(b),
        "same_locator": bool(a["locator"]) and a["locator"] == b["locator"],
        "same_experiment_label": bool(a["experiment_label"])
        and a["experiment_label"] == b["experiment_label"],
        "full_fingerprint_equal": fingerprint(a) == fingerprint(b),
    }
    relation, reason = _value_relation(a, b)
    ev["value_relation"] = relation
    score = sum(WEIGHTS[k] for k in
                ("same_source", "same_sample", "same_metric", "same_context",
                 "same_locator", "same_experiment_label", "full_fingerprint_equal")
                if ev[k])
    if relation == "equal":
        score += WEIGHTS["value_equal"]

    labels_a, labels_b = a["experiment_label"], b["experiment_label"]
    both_labels = bool(labels_a) and bool(labels_b) and labels_a != labels_b

    state, rule, why = "review", "D-004", "insufficient evidence"
    if not ev["same_source"]:
        state, rule, why = "not_duplicate", "D-006", "different sources are never merged"
    elif not (ev["same_sample"] and ev["same_metric"] and ev["same_context"]):
        state, rule, why = "not_duplicate", "D-007", "different sample, metric or context"
    elif both_labels:
        state, rule, why = "not_duplicate", "D-005", (
            "distinct experiment labels within one study = independent replicate; "
            f"values relation: {relation}")
    elif ev["full_fingerprint_equal"]:
        state, rule, why = "exact_duplicate", "D-001", "identical normalized row (repeated extraction)"
    elif relation == "equal":
        if ev["same_locator"] is False and a["locator"] and b["locator"]:
            state, rule, why = "review", "D-004", (
                "same identity and value but different locators: possible independent "
                "replicate or repeated extraction; human decision required")
        else:
            state, rule, why = "likely_duplicate", "D-002", (
                f"same identity and equal value ({reason}), only surface differences")
    elif relation == "different":
        state, rule, why = "conflict", "D-003", (
            f"same identity but different measured values ({reason}); "
            "both retained, never averaged")
    else:
        state, rule, why = "review", "D-004", f"cannot compare values: {reason}"

    return {
        "pair": [a["record_id"], b["record_id"]],
        "state": state, "rule": rule, "reason": why,
        "score": score, "evidence": ev,
    }


def generate_candidates(records: list[dict]) -> list[dict]:
    """Two deterministic blocking passes. Comparisons only inside blocks."""
    from collections import defaultdict
    blocks: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        if r.get("blockable", True):
            blocks[block_keys(r)["dedup_block"]].append(r)
    xblocks: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        if r.get("blockable", True) and r.get("value_token"):
            xblocks[block_keys(r)["xsource_block"]].append(r)

    out: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def _pairs(members: list[dict]):
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = sorted((members[i], members[j]),
                              key=lambda x: x["record_id"])
                key = (a["record_id"], b["record_id"])
                if key not in seen:
                    seen.add(key)
                    out.append(compare_pair(a, b))

    for key in sorted(blocks):
        _pairs(sorted(blocks[key], key=lambda r: r["record_id"]))
    for key in sorted(xblocks):
        members = sorted(xblocks[key], key=lambda r: r["record_id"])
        srcs = {m["source_key"] for m in members}
        if len(srcs) > 1:
            _pairs(members)  # cross-source corroboration note, never merges
    out.sort(key=lambda c: (c["state"], c["pair"][0], c["pair"][1]))
    return out


# ---------------------------------------------------------------------------

def _representative(members: list[dict]) -> dict:
    """Deterministic: most complete row, then converted value present,
    then smallest record_id. Representative is always a real member row;
    values are never mixed across members."""
    def completeness(r: dict) -> tuple:
        filled = sum(1 for k in ("value", "unit", "locator", "experiment_label",
                                 "material", "phase", "dopant", "composition",
                                 "morphology") if r.get(k) not in (None, ""))
        conv = 1 if r.get("value_normalized") is not None else 0
        return (-filled, -conv, r["record_id"])
    return sorted(members, key=completeness)[0]


def cluster_records(records: list[dict], candidates: list[dict]) -> list[dict]:
    """Union-Find over merge-approved pairs only (exact/likely duplicates)."""
    parent = {r["record_id"]: r["record_id"] for r in records}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for c in candidates:
        if c["state"] in ("exact_duplicate", "likely_duplicate"):
            union(c["pair"][0], c["pair"][1])

    groups: dict[str, list[dict]] = {}
    for r in records:
        groups.setdefault(find(r["record_id"]), []).append(r)

    clusters = []
    for root in sorted(groups, key=lambda k: min(m["record_id"] for m in groups[k])):
        members = sorted(groups[root], key=lambda m: m["record_id"])
        rep = _representative(members)
        for m in members:
            m["role"] = "representative" if m["record_id"] == rep["record_id"] else "member"
        clusters.append({
            "cluster_id": None,  # assigned below
            "representative": rep,
            "members": members,
            "size": len(members),
            "merge_rule": ("D-001/D-002" if len(members) > 1 else "singleton"),
        })
    for i, c in enumerate(clusters, 1):
        c["cluster_id"] = f"cl-{i:04d}"
        c["experiment_id"] = f"exp-{i:04d}"
    return clusters


# ---------------------------------------------------------------------------

def run_invariants(clusters: list[dict], candidates: list[dict]) -> list[dict]:
    """Self-checks executed on every run; any failure degrades status."""
    checks = []

    def _ok(name: str, cond: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(cond), "detail": detail})

    conflict_pairs = {tuple(sorted(c["pair"])) for c in candidates
                      if c["state"] == "conflict"}
    cross_source_viol = 0
    mixed_context_viol = 0
    conflict_merged_viol = 0
    rep_not_member_viol = 0
    member_loss_viol = 0
    for c in clusters:
        srcs = {m["source_key"] for m in c["members"]}
        ctxs = {context_key(m) for m in c["members"]}
        ids = [m["record_id"] for m in c["members"]]
        if len(srcs) > 1:
            cross_source_viol += 1
        if len(ctxs) > 1:
            mixed_context_viol += 1
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                if tuple(sorted((ids[i], ids[j]))) in conflict_pairs:
                    conflict_merged_viol += 1
        if c["representative"]["record_id"] not in ids:
            rep_not_member_viol += 1
        if c["size"] != len(c["members"]):
            member_loss_viol += 1
    _ok("no_cross_source_merge", cross_source_viol == 0,
        f"{cross_source_viol} violation(s)")
    _ok("no_cross_context_merge", mixed_context_viol == 0,
        f"{mixed_context_viol} violation(s)")
    _ok("conflict_never_merged", conflict_merged_viol == 0,
        f"{conflict_merged_viol} violation(s)")
    _ok("representative_is_member_row", rep_not_member_viol == 0,
        f"{rep_not_member_viol} violation(s)")
    _ok("member_rows_retained", member_loss_viol == 0,
        f"{member_loss_viol} violation(s)")
    return checks
