#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recalc_schedule.py — 进度确定性实算：DAG + 关键路径 + 资源占用

用法:
    python3 recalc_schedule.py <extraction.json> <out.md>
                               [--case case.json] [--deadline-hours H]
                               [--json-out OUT.json]

流程（全部由脚本实算）:
    1. 由 depends_on 建 DAG；Kahn 拓扑排序，发现环 → exit 2 并列出成环节点。
    2. 前向递推: ES = max(前置 EF, 0)，EF = ES + duration（Decimal）。
    3. 总工期 = max(EF)。关键路径: 从 EF 最大的节点回溯，每步取 EF 最大的前置，
       以显式链式打印（如 S1(0→24) → S2(24→72) → ...），估计可解释、可复现。
    4. 按 resource 汇总占用小时。
    5. 截止时间窗: --deadline-hours 优先；否则若给 --case 则在 case.json 中查找
       键名匹配 deadline/window/截止/窗口 的数值。verdict: 满足 / 超出 / unverified_no_deadline，
       delta = 总工期 - 时限。

退出码:
    0  成功
    2  用法错误 / 文件不可读 / 依赖环 / 数据无法实算
"""
import argparse
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

DEADLINE_KEY = re.compile(r"deadline|window|截止|窗口", re.IGNORECASE)


def dec(x):
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError):
        return None


def fmt(d):
    if d == d.to_integral_value():
        return str(int(d))
    return str(d.quantize(Decimal("0.01")))


def find_deadline(case):
    hits = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                p = "%s.%s" % (path, k) if path else str(k)
                if isinstance(v, (int, float)) and not isinstance(v, bool) and DEADLINE_KEY.search(str(k)):
                    d = dec(v)
                    if d is not None and d > 0:
                        hits.append((p, d))
                walk(v, p)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, "%s[%d]" % (path, i))

    walk(case, "")
    if not hits:
        return None, None
    hits.sort(key=lambda t: 0 if re.search(r"deadline|截止", t[0], re.IGNORECASE) else 1)
    return hits[0][1], hits[0][0]


def main(argv):
    ap = argparse.ArgumentParser(description="进度确定性实算（DAG/关键路径）")
    ap.add_argument("extraction")
    ap.add_argument("out")
    ap.add_argument("--case", default=None)
    ap.add_argument("--deadline-hours", default=None)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv[1:])

    try:
        ext = json.loads(Path(args.extraction).read_text(encoding="utf-8"), parse_float=Decimal)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("错误(exit 2): 读取 extraction 失败: %s\n" % exc)
        return 2

    plan_id = ext.get("plan_id", "<unknown>")
    steps = ext.get("schedule_steps", [])
    if not steps:
        sys.stderr.write("错误(exit 2): extraction 中没有 schedule_steps\n")
        return 2

    nodes = {}
    for st in steps:
        sid = st.get("id")
        dur = dec(st.get("duration_hours"))
        if sid is None or dur is None or dur <= 0:
            sys.stderr.write("错误(exit 2): 步骤 %r 的 duration_hours 无法实算: %r\n" % (sid, st.get("duration_hours")))
            return 2
        nodes[sid] = {"id": sid, "name": st.get("name", sid), "dur": dur,
                      "deps": list(st.get("depends_on", []) or []),
                      "resource": str(st.get("resource", "?")), "locator": st.get("locator", "")}
    for sid, n in nodes.items():
        for d in n["deps"]:
            if d not in nodes:
                sys.stderr.write("错误(exit 2): 步骤 %s 依赖未声明的步骤 %s\n" % (sid, d))
                return 2

    # Kahn 拓扑
    indeg = {sid: len(n["deps"]) for sid, n in nodes.items()}
    children = {sid: [] for sid in nodes}
    for sid, n in nodes.items():
        for d in n["deps"]:
            children[d].append(sid)
    queue = sorted([s for s, dg in indeg.items() if dg == 0])
    topo = []
    while queue:
        s = queue.pop(0)
        topo.append(s)
        for c in sorted(children[s]):
            indeg[c] -= 1
            if indeg[c] == 0:
                queue.append(c)
        queue.sort()
    if len(topo) != len(nodes):
        cyclic = sorted([s for s, dg in indeg.items() if dg > 0])
        sys.stderr.write("错误(exit 2): 检测到依赖环，无法拓扑排序。成环节点: %s\n" % ", ".join(cyclic))
        return 2

    # ES/EF 前向递推
    for sid in topo:
        n = nodes[sid]
        es = max([nodes[d]["ef"] for d in n["deps"]], default=Decimal(0))
        n["es"], n["ef"] = es, es + n["dur"]
    total = max(n["ef"] for n in nodes.values())

    # 关键路径回溯（每步取 EF 最大的前置；并列取 id 较小者，确定可复现）
    end = min([n for n in nodes.values() if n["ef"] == total], key=lambda n: n["id"])
    chain = [end]
    cur = end
    while cur["deps"]:
        cur = min((nodes[d] for d in cur["deps"]), key=lambda n: (-n["ef"], n["id"]))
        chain.append(cur)
    chain.reverse()
    chain_str = " → ".join("%s(%s→%s)" % (n["id"], fmt(n["es"]), fmt(n["ef"])) for n in chain)

    # 资源占用
    busy = {}
    for n in nodes.values():
        busy[n["resource"]] = busy.get(n["resource"], Decimal(0)) + n["dur"]

    # 时限
    deadline, dl_source = (dec(args.deadline_hours), "--deadline-hours") if args.deadline_hours is not None else (None, None)
    if deadline is None and args.case:
        try:
            case = json.loads(Path(args.case).read_text(encoding="utf-8"))
            deadline, dl_source = find_deadline(case)
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write("警告: 读取 --case 失败: %s\n" % exc)
    if deadline is None:
        verdict, delta = "unverified_no_deadline", None
    else:
        delta = total - deadline
        verdict = "超出" if total > deadline else "满足"

    md = []
    md.append("# 进度实算报告 — %s" % plan_id)
    md.append("")
    md.append("> 本报告全部由脚本实算生成（拓扑排序 + 前向递推），可重跑复现。")
    md.append("")
    md.append("## 各步骤最早开始/完成（小时）")
    md.append("")
    md.append("| 步骤 | 名称 | 时长 | 依赖 | 资源 | ES | EF |")
    md.append("|---|---|---|---|---|---|---|")
    for sid in topo:
        n = nodes[sid]
        md.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            sid, n["name"], fmt(n["dur"]), ",".join(n["deps"]) or "—", n["resource"], fmt(n["es"]), fmt(n["ef"])))
    md.append("")
    md.append("## 关键路径")
    md.append("")
    md.append("`%s`" % chain_str)
    md.append("")
    md.append("- 总工期 = max(EF) = **%s 小时**" % fmt(total))
    md.append("")
    md.append("## 资源占用（忙时合计）")
    md.append("")
    for r in sorted(busy):
        md.append("- %s: %s 小时" % (r, fmt(busy[r])))
    md.append("")
    if deadline is not None:
        md.append("## 时限判定")
        md.append("")
        md.append("- 时限: **%s 小时**（来源: `%s`）" % (fmt(deadline), dl_source))
        md.append("- delta = 总工期 - 时限 = %s - %s = **%s 小时**" % (fmt(total), fmt(deadline), fmt(delta)))
        md.append("- 结论: **%s**（%s %s 小时）" % (verdict, "超出" if total > deadline else "余量", fmt(abs(delta))))
    else:
        md.append("## 时限判定")
        md.append("")
        md.append("- 未找到时限 → 结论 **unverified_no_deadline**（不编造时限）")
    md.append("")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(md), encoding="utf-8")

    class Enc(json.JSONEncoder):
        def default(self, o):
            if isinstance(o, Decimal):
                return str(o)
            return super().default(o)

    if args.json_out:
        payload = {"kind": "schedule", "plan_id": plan_id,
                   "steps": [{"id": n["id"], "name": n["name"], "duration_hours": n["dur"],
                              "depends_on": n["deps"], "resource": n["resource"],
                              "es": n["es"], "ef": n["ef"]} for n in (nodes[s] for s in topo)],
                   "critical_path": [n["id"] for n in chain],
                   "critical_path_str": chain_str,
                   "total_hours": total,
                   "resource_busy_hours": busy,
                   "deadline_hours": deadline, "deadline_source": dl_source,
                   "verdict": verdict, "delta_hours": delta}
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(payload, ensure_ascii=False, indent=2, cls=Enc), encoding="utf-8")

    print("进度实算 [%s]: 总工期 %s h; 关键路径 %s" % (plan_id, fmt(total), chain_str))
    print("  时限 %s → 结论 %s%s" % (
        ("%s h (%s)" % (fmt(deadline), dl_source)) if deadline is not None else "未找到",
        verdict, (" delta=%s h" % fmt(delta)) if delta is not None else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
