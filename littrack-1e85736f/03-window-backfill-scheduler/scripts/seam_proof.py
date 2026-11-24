#!/usr/bin/env python3
"""seam_proof.py — 逐接缝证明窗口链连续无缝（无 gap、无 overlap）。

对 chain 中每一对相邻窗口 (prev, next) 验证 prev.end == next.start：
- gap_seconds      = max(0, next.start - prev.end)
- overlap_seconds  = max(0, prev.end - next.start)
- pass             = (gap_seconds == 0 and overlap_seconds == 0)

用法：
  python3 seam_proof.py --plan window_plan.json --out seam_proof.json
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from window_common import dump_json, load_json, parse_instant  # noqa: E402


def prove(plan):
    chain = plan.get("chain", []) or []
    seams = []
    for prev, nxt in zip(chain, chain[1:]):
        pe = parse_instant(prev.get("end"))
        ns = parse_instant(nxt.get("start"))
        if pe is None or ns is None:
            seams.append({
                "seam": "%s -> %s" % (prev.get("id"), nxt.get("id")),
                "pass": False,
                "error": "窗口端点无法解析",
            })
            continue
        delta = (ns - pe).total_seconds()
        gap = max(0.0, delta)
        overlap = max(0.0, -delta)
        seams.append({
            "seam": "%s -> %s" % (prev.get("id"), nxt.get("id")),
            "prev_end": prev.get("end"),
            "next_start": nxt.get("start"),
            "equal": pe == ns,
            "gap_seconds": gap,
            "overlap_seconds": overlap,
            "pass": gap == 0.0 and overlap == 0.0,
        })
    return {
        "rule": "对每条接缝要求 prev.end == next.start（gap_seconds=0 且 overlap_seconds=0）",
        "seams": seams,
        "overall_pass": bool(seams) and all(s.get("pass") for s in seams),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="窗口链接缝证明")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    proof = prove(load_json(args.plan))
    proof["inputs"] = {"window_plan": args.plan}
    dump_json(proof, args.out)
    print("seam_proof -> %s | overall_pass=%s (%d seams)"
          % (args.out, proof["overall_pass"], len(proof["seams"])))
    return 0 if proof["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
