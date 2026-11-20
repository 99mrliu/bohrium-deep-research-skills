#!/usr/bin/env python3
"""plan.py — 把通过校验的 decomposition.json 编译为分波次检索计划。

用法:
  python3 plan.py --decomposition /app/work/decomposition.json --work /app/work \
      [--input-dir /input] [--max-calls 15]

编译规则:
  W1 定界: 1 个动作(盘点输入快照索引), 置于最前;
  W2 主检索: 按 DAG 分层, 同层 SQ 的动作并行编号;
  W3 缺口补检: 初始为空, coverage.py 判定 gap 后由 Agent 手工添加;
  每个动作: id, wave, sq, query(zh/en), source, dedup_key, stop_rule, budget_calls。
  --input-dir 给定时会检查 source 是否为已存在的输入文件; 检索工具源标 source_kind=tool。
总预算: max_calls(默认15); 超预算动作标 deferred=true 并给理由。
"""
import argparse, json, os, re, sys

def dep_layers(sqs):
    deps = {s["id"]: set(s.get("depends_on", [])) for s in sqs}
    depth, seen = {}, set()
    def dep_d(sid):
        if sid in depth:
            return depth[sid]
        if sid in seen:
            return 0
        seen.add(sid)
        depth[sid] = 1 + max([dep_d(x) for x in deps[sid]], default=-1)
        return depth[sid]
    layers = {}
    for s in sqs:
        layers.setdefault(dep_d(s["id"]), []).append(s["id"])
    return [layers[k] for k in sorted(layers)]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--decomposition", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--input-dir", default=None)
    ap.add_argument("--max-calls", type=int, default=15)
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    d = json.load(open(args.decomposition, encoding="utf-8"))
    sqs = {s["id"]: s for s in d["sqs"]}
    input_files = set()
    if args.input_dir and os.path.isdir(args.input_dir):
        for root, _, names in os.walk(args.input_dir):
            for n in names:
                input_files.add(os.path.relpath(os.path.join(root, n), args.input_dir))
    def classify_source(sq):
        """检索源: 优先输入快照文件, 否则标注为检索工具。"""
        return {"source_kind": "snapshot" if input_files else "tool",
                "source_hint": sorted(input_files)[:6] if input_files else "agent 可用检索工具",
                "unavailable_sources": []}
    actions = []
    # W1 定界
    actions.append({"id": "W1-A1", "wave": 1, "sq": None, "purpose": "定界: 盘点输入快照,建立记录索引",
                    "source": sorted(input_files) if input_files else "检索工具(宽检索)",
                    "stop_rule": "得到快照记录清单或宽检索首屏", "budget_calls": 1,
                    "dedup_key": None})
    layers = dep_layers(d["sqs"])
    n = 0
    for li, layer in enumerate(layers):
        for sid in layer:
            s = sqs[sid]
            n += 1
            acc = s.get("acceptance", "")
            km = re.search(r"≥\s*(\d+)", acc)
            k = int(km.group(1)) if km else 3
            q = s.get("queries", {})
            src = classify_source(s)
            actions.append({
                "id": "W2-A%d" % n, "wave": 2, "sq": sid,
                "query_zh": (q.get("zh") or [""])[0], "query_en": (q.get("en") or [""])[0],
                "layer": li, "source_kind": src["source_kind"], "source_hint": src["source_hint"],
                "stop_rule": "相关命中>=%d 或连续2轮新增相关=0" % k,
                "budget_calls": 2, "dedup_key": "doi 或 首作者+年份+标题前缀",
                "acceptance": acc})
    plan = {"research_question": d.get("research_question"),
            "time_window": d.get("time_window"),
            "waves": {"W1": "定界", "W2": "主检索(%d 层)" % len(layers), "W3": "缺口补检(按需)"},
            "actions": actions,
            "budget": {"max_calls": args.max_calls, "planned_calls": sum(a["budget_calls"] for a in actions)},
            "saturation_rule": "连续 2 轮 new_relevant=0 -> 该 SQ saturated",
            "stop_rules": ["全部 SQ 达 acceptance 或 saturated -> evidence_sufficient",
                           "连续 2 轮全局新增相关=0 且有 SQ 未达标 -> marginal_gain_low",
                           "接口连续失败>=2 次 -> handoff_to_human"]}
    over = plan["budget"]["planned_calls"] - plan["budget"]["max_calls"]
    if over > 0:
        for a in reversed(actions):
            if a.get("wave") == 2 and a.get("budget_calls", 0) > 1:
                a["budget_calls"] -= 1
                a["deferred"] = True
                a["deferred_reason"] = "总预算压缩: 该动作降级为 1 次调用, 更多轮次由停止判据决定"
                over -= 1
            if over <= 0:
                break
        plan["budget"]["planned_calls"] = sum(a["budget_calls"] for a in actions)
    path = os.path.join(args.work, "retrieval_plan.json")
    json.dump(plan, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps({"ok": True, "waves": 3, "actions": len(actions),
                      "budget": plan["budget"]}, ensure_ascii=False))

if __name__ == "__main__":
    main()
