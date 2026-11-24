#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""spec_merge.py -- 合并多来源 spec，显式裁决冲突，产出唯一规格账本。

优先级（高在前）：task.md 明示规则 > 投稿须知/补充规定 > 模板实测。
同 id 不同值 -> 保留高优先级项，并把落选值记入 conflicts[]（溯源齐全），
绝不静默取其一。冲突必须在 result.json 的 uncertainties 中点名。

用法:
  python3 spec_merge.py --out merged_spec.json \
      task_spec.json:100 guide_spec.json:50 template_spec.json:10
（路径:优先级，数值越大优先级越高）
"""
import argparse, json, sys

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("specs", nargs="+", help="spec.json:priority")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    loaded = []
    for arg in a.specs:
        path, _, prio = arg.rpartition(":")
        prio = int(prio) if prio else 0
        with open(path, encoding="utf-8") as f:
            spec = json.load(f)
        loaded.append((prio, path, spec))

    def equiv(x, y):
        """数值在 1% 或 0.05 绝对容差内视为同值（吸收 twips 换算的舍入噪声）。"""
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            return abs(float(x) - float(y)) <= max(0.05, 0.01 * max(abs(float(x)), abs(float(y))))
        return json.dumps(x, ensure_ascii=False, sort_keys=True) == json.dumps(y, ensure_ascii=False, sort_keys=True)

    by_id = {}
    for prio, path, spec in loaded:
        for it in spec.get("items", []):
            by_id.setdefault(it["id"], []).append((prio, path, it))

    merged, conflicts = [], []
    for iid in sorted(by_id):
        cands = sorted(by_id[iid], key=lambda t: -t[0])
        best_prio, best_path, best = cands[0]
        diff_val = [c for c in cands if not equiv(c[2]["value"], best["value"])]
        winner = dict(best)
        winner["priority"] = best_prio
        if diff_val:
            winner["status"] = "conflict-resolved"
            conflicts.append({
                "id": iid,
                "adopted": {"value": best["value"], "unit": best["unit"],
                            "source": best["source"], "priority": best_prio},
                "rejected": [{"value": c[2]["value"], "unit": c[2]["unit"],
                              "source": c[2]["source"], "priority": c[0]}
                             for c in diff_val],
                "policy": "高优先级来源胜出；若任务说明与模板冲突，以任务说明为准并在 uncertainties 声明"})
        merged.append(winner)

    sources = []
    for prio, path, spec in sorted(loaded, key=lambda t: -t[0]):
        for s in spec.get("sources", []):
            s = dict(s)
            s["priority"] = prio
            sources.append(s)
    out = {"spec_version": "1.0", "generator": "spec_merge.py",
           "sources": sources, "items": merged, "conflicts": conflicts}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("merged items: %d, conflicts: %d -> %s" % (len(merged), len(conflicts), a.out))
    if conflicts:
        sys.exit(1)  # 有冲突：不阻断，但调用方必须在 uncertainties 声明

if __name__ == "__main__":
    main()
