#!/usr/bin/env python3
"""entity_match.py — 确定性 blocking + 多特征打分 + 三档判定。

输入两侧必须是 name_norm.py 的产物(含 tokens/core_tokens/kind 等字段)。
所有阈值与特征权重均来自 policy JSON,脚本内不硬编码。

三档:
  auto      score >= thresholds.high 且无强制 flag
  candidate thresholds.low <= score < thresholds.high,或存在强制 flag
            (order_variant / suffix_conflict)——永不静默合并,必须连同事
            特征分解与全部备选一起列出
  non_match 其余(含从未进入任何 block 配对者)

退出码:0 正常;1 数据违规;2 用法错误(文件缺失等)。仅标准库。
"""
import argparse
import json
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_USAGE = 2

FEATURE_KEYS = ["exact_norm", "core_eq", "core_containment",
                "token_jaccard", "initial_surname"]
FORCING_FLAGS = {"order_variant", "suffix_conflict"}


# ---------------------------------------------------------------- features
def features(a, b):
    ta, tb = set(a["tokens"]), set(b["tokens"])
    ca, cb = set(a["core_tokens"]), set(b["core_tokens"])
    f = {
        "exact_norm": 1.0 if a["normalized"] == b["normalized"] else 0.0,
        "core_eq": 1.0 if (a["core"] and a["core"] == b["core"]) else 0.0,
        "core_containment": 1.0 if (ca and cb and (ca <= cb or cb <= ca)) else 0.0,
        "token_jaccard": (len(ta & tb) / len(ta | tb)) if (ta or tb) else 0.0,
        "initial_surname": 0.0,
    }
    if (a.get("kind") == "person" and b.get("kind") == "person"
            and a["tokens"] and b["tokens"]):
        ia = (a["tokens"][0][0], a["tokens"][-1])
        ib = (b["tokens"][0][0], b["tokens"][-1])
        f["initial_surname"] = 1.0 if ia == ib else 0.0
    return f


def score_pair(f, weights):
    """Weighted sum; exact normalized equality saturates the score to 1.0
    (documented in references/match_policy.md)."""
    if f["exact_norm"] == 1.0:
        return 1.0
    return round(sum(weights.get(k, 0.0) * f.get(k, 0.0) for k in FEATURE_KEYS), 4)


def flags_for(a, b):
    """Non-score safety flags. Both force the candidate band."""
    flags = []
    if (a.get("kind") == "person" and b.get("kind") == "person"
            and sorted(a["tokens"]) == sorted(b["tokens"])
            and a["tokens"] != b["tokens"]):
        flags.append("order_variant")  # e.g. "Zhang Wei" vs "Wei Zhang"
    if (a.get("canonical_suffix") and b.get("canonical_suffix")
            and a["canonical_suffix"] != b["canonical_suffix"]
            and a["core"] and a["core"] == b["core"]):
        flags.append("suffix_conflict")  # e.g. "Globex Ltd." vs "Globex GmbH"
    return flags


def decide(score, flags, thresholds):
    if FORCING_FLAGS & set(flags):
        return "candidate"
    if score >= thresholds["high"]:
        return "auto"
    if score >= thresholds["low"]:
        return "candidate"
    return "non_match"


# ---------------------------------------------------------------- blocking
def block_keys(e):
    keys = set()
    toks = e.get("tokens", [])
    if toks:
        keys.add("T:" + " ".join(sorted(toks)))
        for t in toks:
            if len(t) > 1:
                keys.add("W:" + t)
    ct = e.get("core_tokens", [])
    if ct and ct != toks:
        keys.add("C:" + " ".join(sorted(ct)))
    if e.get("kind") == "person" and toks:
        keys.add("S:" + toks[-1])
    return keys


def echo(e):
    return {k: e[k] for k in ("id", "raw", "normalized", "role", "kind")
            if k in e}


# ---------------------------------------------------------------- matching
def run_match(left, right, policy):
    th = policy["thresholds"]
    weights = policy["weights"]

    rblocks = {}
    for j, e in enumerate(right):
        for k in block_keys(e):
            rblocks.setdefault(k, []).append(j)

    pair_idx = set()
    for i, e in enumerate(left):
        for k in block_keys(e):
            for j in rblocks.get(k, []):
                pair_idx.add((i, j))

    pairs = []
    for i, j in sorted(pair_idx):
        f = features(left[i], right[j])
        s = score_pair(f, weights)
        fl = flags_for(left[i], right[j])
        pairs.append({
            "left_index": i, "right_index": j,
            "left": echo(left[i]), "right": echo(right[j]),
            "score": s, "features": f, "flags": fl,
            "band": decide(s, fl, th),
        })

    auto_matches = [{
        "left": p["left"], "right": p["right"],
        "score": p["score"], "features": p["features"],
    } for p in pairs if p["band"] == "auto"]

    cand_by_left = {}
    for p in pairs:
        if p["band"] != "candidate":
            continue
        cand_by_left.setdefault(p["left_index"], {
            "left": p["left"], "alternatives": [],
        })["alternatives"].append({
            "right": p["right"], "score": p["score"],
            "features": p["features"], "flags": p["flags"],
        })
    candidate_pairs = []
    for i in sorted(cand_by_left):
        grp = cand_by_left[i]
        grp["alternatives"].sort(key=lambda a: (-a["score"], a["right"].get("raw", "")))
        candidate_pairs.append(grp)

    matched_left = {p["left_index"] for p in pairs if p["band"] in ("auto", "candidate")}
    matched_right = {p["right_index"] for p in pairs if p["band"] in ("auto", "candidate")}
    non_matches = ([{"side": "left", "entity": echo(e)}
                    for i, e in enumerate(left) if i not in matched_left]
                   + [{"side": "right", "entity": echo(e)}
                      for j, e in enumerate(right) if j not in matched_right])

    return {
        "policy": policy,
        "auto_matches": auto_matches,
        "candidate_pairs": candidate_pairs,
        "non_matches": non_matches,
        "statistics": {
            "left_count": len(left),
            "right_count": len(right),
            "pairs_scored": len(pairs),
            "auto_count": len(auto_matches),
            "candidate_left_count": len(candidate_pairs),
            "candidate_pair_count": sum(len(g["alternatives"]) for g in candidate_pairs),
            "non_match_count": len(non_matches),
        },
        "_pairs": pairs,  # internal, stripped before writing
    }


def load_json(path, what, expect=None):
    p = Path(path)
    if not p.is_file():
        print(f"error: {what} file not found: {path}", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"error: {what} is not valid UTF-8 JSON: {e}", file=sys.stderr)
        sys.exit(EXIT_VIOLATION)
    if expect == "list" and not isinstance(data, list):
        print(f"error: {what} must be a JSON list", file=sys.stderr)
        sys.exit(EXIT_VIOLATION)
    if expect == "dict" and not isinstance(data, dict):
        print(f"error: {what} must be a JSON object", file=sys.stderr)
        sys.exit(EXIT_VIOLATION)
    return data


def load_entities(path, what):
    data = load_json(path, what)
    entries = data.get("names") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        print(f"error: {what} must be a name_norm output object or a JSON list",
              file=sys.stderr)
        sys.exit(EXIT_VIOLATION)
    for idx, e in enumerate(entries):
        if not isinstance(e, dict) or "tokens" not in e or "normalized" not in e:
            print(f"error: {what} entry {idx} lacks normalized fields; "
                  f"run scripts/name_norm.py first", file=sys.stderr)
            sys.exit(EXIT_VIOLATION)
    return entries


def load_policy(path):
    policy = load_json(path, "policy", expect="dict")
    try:
        th = policy["thresholds"]
        weights = policy["weights"]
        high, low = float(th["high"]), float(th["low"])
    except (KeyError, TypeError, ValueError) as e:
        print(f"error: policy must define numeric thresholds.high/low and "
              f"weights: {e}", file=sys.stderr)
        sys.exit(EXIT_VIOLATION)
    if not (0.0 <= low < high):
        print("error: policy requires 0 <= thresholds.low < thresholds.high",
              file=sys.stderr)
        sys.exit(EXIT_VIOLATION)
    unknown = set(weights) - set(FEATURE_KEYS)
    if unknown:
        print(f"error: policy weights reference unknown features: "
              f"{sorted(unknown)} (known: {FEATURE_KEYS})", file=sys.stderr)
        sys.exit(EXIT_VIOLATION)
    return {"thresholds": {"high": high, "low": low},
            "weights": {k: float(v) for k, v in weights.items()}}


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Blocking + multi-feature scoring + three-band decision.")
    ap.add_argument("--left", required=True, help="normalized entity list A (name_norm output)")
    ap.add_argument("--right", required=True, help="normalized entity list B (name_norm output)")
    ap.add_argument("--policy", required=True, help="match policy JSON (thresholds + weights)")
    ap.add_argument("--output", required=True, help="match report JSON path")
    args = ap.parse_args(argv)

    left = load_entities(args.left, "left entities")
    right = load_entities(args.right, "right entities")
    policy = load_policy(args.policy)

    if not left or not right:
        print("warning: empty entity list on at least one side; "
              "all entities will be non-matches", file=sys.stderr)

    report = run_match(left, right, policy)
    report.pop("_pairs", None)
    Path(args.output).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    st = report["statistics"]
    print(f"auto={st['auto_count']} candidate_groups={st['candidate_left_count']} "
          f"non_match={st['non_match_count']} pairs_scored={st['pairs_scored']} "
          f"-> {args.output}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
