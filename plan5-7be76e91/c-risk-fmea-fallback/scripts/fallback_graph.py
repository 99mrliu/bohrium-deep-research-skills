#!/usr/bin/env python3
"""fallback_graph.py — 回退路径图完备性校验（确定性，纯 stdlib）。

构建「失败场景(critical/high 风险) → 回退动作」有向图：
  边1: risk.fallback_ref -> fallback_actions[].action_id
  边2: fallback_actions[].on_failure_ref -> 另一回退动作（回退自身失败时的下一级，可选）

校验（缺陷 → exit 3，缺陷清单写 stdout，产物仍写出）：
  - critical/high 风险 fallback_ref 为空或指向不存在的 action_id（断链/悬空）
  - 回退动作缺必填字段 {action_id, description, adds_cost, adds_time, requires_expert_confirm}
  - action_id 重复
  - 回退链成环（沿 on_failure_ref 检测到环）
  - S>=5(critical) 且 mitigation 为空（不可行建议，需专家确认）

三态 verdict（无缺陷时）：
  - needs_expert:      任一 critical/high 回退路径上的动作 requires_expert_confirm=true
  - acceptable_risk:   其余情况（全部关键风险有缓解+完整回退链）
有缺陷时 verdict = infeasible_without_change。

输出 fallback.json + fallback.md（含每关键场景替代路径叙述骨架）。

退出码：0 成功 / 2 输入错误 / 3 质量门缺陷。
"""
import argparse
import json
import sys
from pathlib import Path

EXIT_OK, EXIT_USAGE, EXIT_GATE = 0, 2, 3
ACTION_REQUIRED = ["action_id", "description", "adds_cost", "adds_time", "requires_expert_confirm"]


def load_json(path, what):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR(exit 2): {what} 文件不存在: {path}", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    except json.JSONDecodeError as e:
        print(f"ERROR(exit 2): {what} JSON 解析失败: {path}: {e}", file=sys.stderr)
        sys.exit(EXIT_USAGE)


def is_blank(v):
    return v is None or (isinstance(v, str) and v.strip() == "")


def find_cycle(nodes, edges):
    """确定性环检测：按节点排序做三色 DFS，返回找到的第一个环（节点列表）或 None。"""
    color = {n: 0 for n in nodes}  # 0 白 1 灰 2 黑
    stack = []

    def dfs(u):
        color[u] = 1
        stack.append(u)
        for v in sorted(edges.get(u, [])):
            if v not in color:
                continue
            if color[v] == 1:
                return stack[stack.index(v):] + [v]
            if color[v] == 0:
                r = dfs(v)
                if r:
                    return r
        stack.pop()
        color[u] = 2
        return None

    for n in sorted(nodes):
        if color[n] == 0:
            r = dfs(n)
            if r:
                return r
    return None


def main():
    ap = argparse.ArgumentParser(
        description="回退路径完备性校验：critical/high 风险必须有有效回退，回退链不得成环；"
                    "输出三态 verdict。退出码 0 成功 / 2 输入错误 / 3 缺陷。")
    ap.add_argument("--register", required=True, help="risk_register.json（含 risks 与 fallback_actions）")
    ap.add_argument("--fmea", required=True, help="fmea.py 产出的 fmea.json（提供分级结果）")
    ap.add_argument("--outdir", required=True, help="产物输出目录（fallback.json / fallback.md）")
    ap.add_argument("--note", default=None,
                    help="可选：嵌入 JSON/Markdown 产物顶部的标注（示例产物必须传合成示例标注）")
    args = ap.parse_args()

    reg = load_json(args.register, "risk_register")
    fmea = load_json(args.fmea, "fmea 台账")
    if not isinstance(reg, dict) or not isinstance(reg.get("risks"), list):
        print("ERROR(exit 2): risk_register 必须是含 risks 列表的 JSON 对象", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    if not isinstance(fmea, dict) or not isinstance(fmea.get("risks"), list):
        print("ERROR(exit 2): fmea.json 缺少 risks 列表，请先运行 fmea.py", file=sys.stderr)
        sys.exit(EXIT_USAGE)

    plan_id = reg.get("plan_id", fmea.get("plan_id", ""))
    defects = []
    grade_by_id = {r["risk_id"]: r["grade"] for r in fmea["risks"] if "risk_id" in r}
    reg_by_id = {r.get("risk_id"): r for r in reg["risks"] if isinstance(r, dict)}

    actions = reg.get("fallback_actions", [])
    if actions is None:
        actions = []
    if not isinstance(actions, list):
        print("ERROR(exit 2): fallback_actions 必须是列表", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    action_map = {}
    for i, a in enumerate(actions):
        if not isinstance(a, dict):
            defects.append(f"fallback_actions[{i}]: 不是 JSON 对象")
            continue
        aid = a.get("action_id", f"<missing-{i}>")
        for fld in ACTION_REQUIRED:
            if fld not in a:
                defects.append(f"fallback_actions[{i}]({aid}): 缺必填字段 {fld}")
        if aid in action_map:
            defects.append(f"fallback_actions[{i}]: action_id 重复: {aid}")
        if "requires_expert_confirm" in a and not isinstance(a["requires_expert_confirm"], bool):
            defects.append(f"fallback_actions[{i}]({aid}): requires_expert_confirm 必须是布尔值")
        action_map[aid] = a

    # 图：节点 = critical/high 风险 + 回退动作；边 = fallback_ref / on_failure_ref
    nodes, edges = set(), {}
    critical_high = sorted([rid for rid, g in grade_by_id.items() if g in ("critical", "high")])
    for rid in critical_high:
        r = reg_by_id.get(rid, {})
        nodes.add(rid)
        ref = r.get("fallback_ref")
        if is_blank(ref):
            defects.append(f"{rid}({grade_by_id[rid]}): 关键失败场景无回退路径（fallback_ref 为空）")
            continue
        if ref not in action_map:
            defects.append(f"{rid}({grade_by_id[rid]}): fallback_ref 悬空，指向不存在的动作 {ref!r}")
            continue
        nodes.add(ref)
        edges.setdefault(rid, []).append(ref)
        if grade_by_id[rid] == "critical" and is_blank(r.get("mitigation")):
            defects.append(f"{rid}: severity>=5 且 mitigation 为空 → 不可行建议（需专家确认）")
    for aid, a in action_map.items():
        nxt = a.get("on_failure_ref")
        if is_blank(nxt):
            continue
        nodes.add(aid)
        if nxt not in action_map:
            defects.append(f"动作 {aid}: on_failure_ref 悬空，指向不存在的动作 {nxt!r}")
            continue
        nodes.add(nxt)
        edges.setdefault(aid, []).append(nxt)

    cycle = find_cycle(nodes, edges)
    if cycle:
        defects.append("回退链成环: " + " -> ".join(cycle))

    # 每关键场景替代路径叙述骨架 + needs_expert 判定
    paths = []
    needs_expert = False
    for rid in critical_high:
        r = reg_by_id.get(rid, {})
        chain, cur, seen = [], r.get("fallback_ref"), set()
        while not is_blank(cur) and cur in action_map and cur not in seen:
            seen.add(cur)
            a = action_map[cur]
            chain.append(cur)
            if a.get("requires_expert_confirm") is True:
                needs_expert = True
            cur = a.get("on_failure_ref")
        paths.append({
            "risk_id": rid,
            "grade": grade_by_id[rid],
            "title": r.get("title", ""),
            "trigger_condition": r.get("trigger_condition", ""),
            "fallback_chain": chain,
            "chain_complete": bool(chain) and (is_blank(action_map.get(chain[-1], {}).get("on_failure_ref"))
                                               or action_map.get(chain[-1], {}).get("on_failure_ref") in action_map),
        })

    if defects:
        verdict = "infeasible_without_change"
    elif needs_expert:
        verdict = "needs_expert"
    else:
        verdict = "acceptable_risk"

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    doc = {
        "plan_id": plan_id,
        "tool": "fallback_graph.py",
        "critical_high_risks": critical_high,
        "fallback_actions": sorted(action_map.keys()),
        "edges": {k: sorted(v) for k, v in sorted(edges.items())},
        "cycle": cycle,
        "paths": paths,
        "defects": sorted(defects),
        "verdict": verdict,
    }
    if args.note is not None:
        doc["note"] = args.note
    (outdir / "fallback.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    verdict_cn = {"acceptable_risk": "可接受风险", "needs_expert": "需专家确认",
                  "infeasible_without_change": "不变更则不可行（建议，需专家确认）"}
    lines = [
        f"# 回退路径校验 — 方案 {plan_id}",
        "",
        f"- 工具: fallback_graph.py（确定性）",
        f"- 关键场景(critical/high)数: {len(critical_high)}",
        f"- 回退动作数: {len(action_map)}",
        f"- **verdict: {verdict}（{verdict_cn[verdict]}）**",
        "",
        "## 关键失败场景的替代路径（叙述骨架，供 result.json 引用）",
    ]
    if not paths:
        lines.append("- （无 critical/high 风险，无需回退路径）")
    for p in paths:
        lines.append(f"### {p['risk_id']} [{p['grade']}] {p['title']}")
        lines.append(f"- 触发条件: {p['trigger_condition'] or '（空，缺陷）'}")
        if p["fallback_chain"]:
            lines.append(f"- 回退链: {' -> '.join(p['fallback_chain'])}")
            for aid in p["fallback_chain"]:
                a = action_map[aid]
                lines.append(
                    f"  - {aid}: {a.get('description', '')} "
                    f"（增支 {a.get('adds_cost', '?')}，增时 {a.get('adds_time', '?')}，"
                    f"需专家确认: {a.get('requires_expert_confirm', '?')}）")
        else:
            lines.append("- 回退链: （无 → 缺陷）")
        lines.append(f"- 叙述骨架: 若「{p['trigger_condition'] or '触发条件待补'}」发生，"
                     f"则启用 {(' -> '.join(p['fallback_chain'])) or '（回退缺失，须先补齐）'}；"
                     f"由此产生的额外代价计入 expected_cost 对比。")
        lines.append("")
    if cycle:
        lines.append(f"## 环检测\n- 检出环: {' -> '.join(cycle)}")
    if defects:
        lines += ["## 缺陷（质量门 exit 3）"] + [f"- {d}" for d in sorted(defects)]
    md_text = "\n".join(lines) + "\n"
    if args.note is not None:
        md_text = f"> {args.note}\n\n" + md_text
    (outdir / "fallback.md").write_text(md_text, encoding="utf-8")

    if defects:
        print(f"回退校验质量门拦截（exit 3），verdict={verdict}，缺陷清单：")
        for d in sorted(defects):
            print(f"  DEFECT: {d}")
        sys.exit(EXIT_GATE)
    print(f"fallback PASS: plan={plan_id} verdict={verdict} "
          f"critical/high={len(critical_high)} actions={len(action_map)} -> {outdir}/fallback.json")
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
