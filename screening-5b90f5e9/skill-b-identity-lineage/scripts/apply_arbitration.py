#!/usr/bin/env python3
"""apply_arbitration.py - 应用模型对 Tier3 候选对的仲裁结果。

输入:
  /app/work/clusters.json       （identity_resolve.py 的自动簇）
  /app/work/review_queue.json   （待仲裁对）
  /app/work/arbitrations.json   （模型裁决，格式见 templates/arbitration.md）
输出:
  /app/work/clusters.final.json （含 split_decisions 显式留痕）

校验规则:
  - 每条仲裁 rationale 必须非空，否则 exit 3（合并必须有依据）；
  - pair 必须出现在 review_queue.json 中，否则 exit 3；
  - 所有 pending 对都必须被裁决，否则 exit 3（不允许悬而未决静默通过）。

退出码: 0=成功; 2=无待仲裁对（直接定稿自动簇）; 3=校验失败。
"""
import argparse
import json
import sys
from pathlib import Path


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def main() -> int:
    ap = argparse.ArgumentParser(description="应用 Tier3 仲裁 → clusters.final.json")
    ap.add_argument("--work", default="/app/work", help="工作目录 (默认 /app/work)")
    ap.add_argument("--arbitrations", default=None,
                    help="仲裁文件路径 (默认 /app/work/arbitrations.json)")
    args = ap.parse_args()
    work = Path(args.work)

    clusters_path = work / "clusters.json"
    queue_path = work / "review_queue.json"
    if not clusters_path.exists():
        print(json.dumps({"ok": False, "exit": 3,
                          "reason": "clusters.json 不存在，请先运行 identity_resolve.py"},
                         ensure_ascii=False))
        return 3

    auto = json.loads(clusters_path.read_text(encoding="utf-8"))
    pending_pairs = {}
    if queue_path.exists():
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        for p in queue.get("pending_pairs", []):
            pending_pairs[p["pair"]] = p

    arb_path = Path(args.arbitrations) if args.arbitrations else work / "arbitrations.json"

    if not pending_pairs:
        final = {"clusters": auto.get("clusters", []), "split_decisions": [],
                 "arbitrations_applied": [],
                 "stats": {"note": "无 Tier3 待仲裁对，自动簇直接定稿"}}
        (work / "clusters.final.json").write_text(
            json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": True, "exit": 2, "note": "no pending pairs"}, ensure_ascii=False))
        return 2

    if not arb_path.exists():
        print(json.dumps({"ok": False, "exit": 3,
                          "reason": f"存在 {len(pending_pairs)} 个待仲裁对，但仲裁文件不存在: {arb_path}"},
                         ensure_ascii=False))
        return 3

    try:
        arb_doc = json.loads(arb_path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "exit": 3,
                          "reason": f"arbitrations.json 解析失败: {e}"}, ensure_ascii=False))
        return 3
    arbitrations = arb_doc.get("arbitrations") if isinstance(arb_doc, dict) else arb_doc
    if not isinstance(arbitrations, list):
        print(json.dumps({"ok": False, "exit": 3,
                          "reason": "arbitrations 必须是数组"}, ensure_ascii=False))
        return 3

    errors = []
    seen = set()
    for i, a in enumerate(arbitrations):
        pair = a.get("pair")
        decision = a.get("decision")
        rationale = (a.get("rationale") or "").strip()
        if not pair:
            errors.append(f"#{i}: pair 缺失")
        elif pair not in pending_pairs:
            errors.append(f"#{i}: pair 不在待仲裁队列: {pair}")
        if decision not in ("merge", "split"):
            errors.append(f"#{i}: decision 必须是 merge/split: {decision!r}")
        if not rationale:
            errors.append(f"#{i}: rationale 为空（合并/拆分都必须有依据）")
        if pair:
            seen.add(pair)
    missing = [p for p in pending_pairs if p not in seen]
    for p in missing:
        errors.append(f"待仲裁对未被裁决: {p}")
    if errors:
        (work / "arbitration_errors.json").write_text(
            json.dumps({"errors": errors}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": False, "exit": 3, "errors": errors}, ensure_ascii=False))
        return 3

    # 在自动簇基础上并入仲裁 merge
    uf = UnionFind()
    for c in auto.get("clusters", []):
        for m in c["members"]:
            uf.union(c["members"][0], m)
    arb_ev = []  # 平铺存仲裁证据，按端点归属分配，避免并查集根漂移
    split_decisions, applied = [], []
    for a in arbitrations:
        ida, idb = a["pair"].split("|")
        if a["decision"] == "merge":
            uf.union(ida, idb)
            arb_ev.append({"pair": a["pair"], "tier": "tier3+arbitration",
                           "endpoints": [ida, idb],
                           "evidence": {"rationale": a["rationale"],
                                        "scores": pending_pairs[a["pair"]].get("scores")}})
        else:
            split_decisions.append({
                "pair": a["pair"], "rationale": a["rationale"],
                "scores": pending_pairs[a["pair"]].get("scores"),
                "note": "显式判定为不同研究，防误并留痕"})
        applied.append({"pair": a["pair"], "decision": a["decision"]})

    groups = {}
    for c in auto.get("clusters", []):
        for m in c["members"]:
            groups.setdefault(uf.find(m), []).append(m)
    auto_evidence = {}
    for c in auto.get("clusters", []):
        for m in c["members"]:
            auto_evidence[m] = c.get("merge_evidence", [])

    clusters = []
    for root in sorted(groups):
        members = sorted(groups[root])
        member_set = set(members)
        ev, seen_pairs = [], set()
        for m in members:
            for e in auto_evidence.get(m, []):
                if e.get("pair") not in seen_pairs:
                    seen_pairs.add(e.get("pair"))
                    ev.append(e)
        for e in arb_ev:
            if e["endpoints"][0] in member_set or e["endpoints"][1] in member_set:
                ev.append({"pair": e["pair"], "tier": e["tier"], "evidence": e["evidence"]})
        clusters.append({"cluster_id": f"clu-{len(clusters) + 1:03d}",
                         "members": members,
                         "merge_evidence": ev,
                         "origin": "auto+arbitration"})

    final = {"clusters": clusters,
             "split_decisions": split_decisions,
             "arbitrations_applied": applied,
             "stats": {"clusters": len(clusters),
                       "arbitrated_merges": sum(1 for a in applied if a["decision"] == "merge"),
                       "arbitrated_splits": len(split_decisions)}}
    (work / "clusters.final.json").write_text(
        json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "clusters": len(clusters),
                      "merges": final["stats"]["arbitrated_merges"],
                      "splits": len(split_decisions)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(3)
