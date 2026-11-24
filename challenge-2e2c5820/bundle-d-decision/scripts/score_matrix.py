#!/usr/bin/env python3
"""score_matrix.py — 决策矩阵 + 加权排序 + 权重敏感性分析。

用法: python3 score_matrix.py <scores.json> <out_dir> [--weights '{"dim":w,...}']

scores.json 模式见 references/rubric.md：每个可评分版本必须覆盖全部 7 个维度，
每格含 score(0-4) 与 evidence{locator, quote}。空证据 → exit 2 并列出问题格。
版本可标记 {"status":"unscorable","reason":...}，该版不参与排名。

产出:
  <out_dir>/decision_matrix.md  全表（每格带证据）+ 排序 + 敏感性分析
  <out_dir>/ranking.json        权重/总分/排序/敏感性（含 rank flip 列表）

敏感性: 对每个维度权重分别 ±20%，其余权重按比例归一化，重算排名并报告翻转。

退出码: 0 成功; 2 校验失败或用法错误; 3 文件不可读。
"""
import json
import os
import re
import sys

DIMENSIONS = ["hypothesis_variables", "controls", "equipment_materials", "time_cost",
              "parameter_ranges", "risk_anomaly", "ethics_safety"]
DIM_NAMES = {"hypothesis_variables": "假设与变量", "controls": "对照组",
             "equipment_materials": "设备材料", "time_cost": "时间成本",
             "parameter_ranges": "参数范围", "risk_anomaly": "风险与异常",
             "ethics_safety": "伦理与安全"}
DEFAULT_WEIGHTS = {"hypothesis_variables": 0.20, "controls": 0.15, "equipment_materials": 0.15,
                   "time_cost": 0.15, "parameter_ranges": 0.10, "risk_anomaly": 0.15,
                   "ethics_safety": 0.10}
WEIGHTS_RE = re.compile(r"<!--\s*weights:\s*(\{.*?\})\s*-->")


def load_rubric_weights():
    """从脚本相邻的 ../references/rubric.md 读取默认权重，失败则退回内置值。"""
    here = os.path.dirname(os.path.abspath(__file__))
    rubric = os.path.join(here, "..", "references", "rubric.md")
    try:
        with open(rubric, "r", encoding="utf-8") as f:
            m = WEIGHTS_RE.search(f.read())
        if m:
            w = json.loads(m.group(1))
            if set(w) == set(DIMENSIONS):
                return {k: float(v) for k, v in w.items()}
    except (OSError, ValueError):
        pass
    return dict(DEFAULT_WEIGHTS)


def normalize(w):
    s = sum(w.values())
    if s <= 0:
        raise ValueError("权重和必须为正")
    return {k: v / s for k, v in w.items()}


def validate(data):
    """返回 (scorable, unscorable, errors)。"""
    plans = data.get("plans")
    if not isinstance(plans, dict) or not plans:
        return {}, {}, ["scores.json 缺少非空的 plans 对象"]
    scorable, unscorable, errors = {}, {}, []
    for pid, entry in plans.items():
        if isinstance(entry, dict) and entry.get("status") == "unscorable":
            unscorable[pid] = str(entry.get("reason", "材料缺失，无法评分"))
            continue
        dims = entry.get("dimensions") if isinstance(entry, dict) else None
        if not isinstance(dims, dict):
            errors.append("%s: 缺少 dimensions 对象（或标记 status=unscorable）" % pid)
            continue
        for d in DIMENSIONS:
            cell = dims.get(d)
            if not isinstance(cell, dict):
                errors.append("%s/%s: 缺格子" % (pid, d))
                continue
            sc = cell.get("score")
            if not isinstance(sc, int) or isinstance(sc, bool) or not (0 <= sc <= 4):
                errors.append("%s/%s: score 必须是 0-4 整数，实际为 %r" % (pid, d, sc))
            ev = cell.get("evidence")
            if not isinstance(ev, dict) or not str(ev.get("locator", "")).strip() \
                    or not str(ev.get("quote", "")).strip():
                errors.append("%s/%s: evidence.locator 与 evidence.quote 均不能为空" % (pid, d))
        scorable[pid] = dims
    return scorable, unscorable, errors


def totals(scorable, weights):
    return {pid: sum(cell["score"] * weights[d] for d, cell in dims.items())
            for pid, dims in scorable.items()}


def ranking(t):
    order = sorted(t, key=lambda p: (-t[p], p))
    return {p: i + 1 for i, p in enumerate(order)}, order


def sensitivity(scorable, weights):
    """每维 ±20% 扰动，其余按比例归一化。返回每版稳定性与翻转列表。"""
    base_t = totals(scorable, weights)
    base_rank, base_order = ranking(base_t)
    scenarios = []
    for dim in DIMENSIONS:
        for sign, label in ((1.2, "+20%"), (0.8, "-20%")):
            w2 = dict(weights)
            w2[dim] = weights[dim] * sign
            # 其余维度按比例缩放，使总和为 1
            rest = 1.0 - w2[dim]
            rest_orig = 1.0 - weights[dim]
            for d in DIMENSIONS:
                if d != dim:
                    w2[d] = weights[d] * (rest / rest_orig if rest_orig > 0 else 0)
            t2 = totals(scorable, w2)
            r2, order2 = ranking(t2)
            scenarios.append({"scenario": "%s %s" % (DIM_NAMES[dim], label),
                              "dimension": dim, "delta": label,
                              "order": order2, "ranks": r2, "totals": t2})
    stability, flips = {}, []
    for pid in scorable:
        ranks = [s["ranks"][pid] for s in scenarios] + [base_rank[pid]]
        stability[pid] = {"baseline_rank": base_rank[pid],
                          "best_rank": min(ranks), "worst_rank": max(ranks),
                          "rank_counts": {str(r): [s["ranks"][pid] for s in scenarios].count(r)
                                          for r in sorted(set(ranks))}}
    for s in scenarios:
        if s["order"] != base_order:
            changed = {pid: {"baseline": base_rank[pid], "scenario": s["ranks"][pid]}
                       for pid in scorable if base_rank[pid] != s["ranks"][pid]}
            flips.append({"scenario": s["scenario"], "new_order": s["order"], "changed_ranks": changed})
    return {"baseline": {"order": base_order, "ranks": base_rank, "totals": base_t},
            "scenarios_run": len(scenarios), "stability": stability, "rank_flips": flips}


def emit_md(path, scorable, unscorable, weights, sens):
    base = sens["baseline"]
    lines = ["# 决策矩阵（每格: 分数 ｜ 证据定位 ｜ 原文引文）", ""]
    header = "| 维度（权重） | " + " | ".join(scorable) + " |"
    lines += [header, "|" + "---|" * (len(scorable) + 1)]
    for d in DIMENSIONS:
        row = ["%s（%.2f）" % (DIM_NAMES[d], weights[d])]
        for pid, dims in scorable.items():
            cell = dims[d]
            ev = cell["evidence"]
            row.append("**%d** ｜ %s ｜ “%s”" % (cell["score"], ev["locator"], ev["quote"]))
        lines.append("| " + " | ".join(row) + " |")
    lines.append("| **加权总分** | " + " | ".join("**%.3f**" % base["totals"][p] for p in scorable) + " |")
    lines.append("| **基准排名** | " + " | ".join("第 %d" % base["ranks"][p] for p in scorable) + " |")
    lines.append("")
    lines.append("## 排序结论")
    lines.append("")
    for i, pid in enumerate(base["order"], 1):
        lines.append("%d. %s（%.3f）" % (i, pid, base["totals"][pid]))
    if unscorable:
        lines.append("")
        lines.append("未评分版本（材料缺失，不猜）：")
        for pid, reason in unscorable.items():
            lines.append("- %s：%s" % (pid, reason))
    lines += ["", "## 权重敏感性分析（每维 ±20%%，其余归一化，共 %d 种情景）" % sens["scenarios_run"], ""]
    lines.append("| 版本 | 基准排名 | 最好 | 最差 | 各排名出现次数 |")
    lines.append("|---|---|---|---|---|")
    for pid in scorable:
        st = sens["stability"][pid]
        counts = "，".join("第%s×%s" % (r, c) for r, c in sorted(st["rank_counts"].items()))
        lines.append("| %s | 第%d | 第%d | 第%d | %s |" % (
            pid, st["baseline_rank"], st["best_rank"], st["worst_rank"], counts))
    lines.append("")
    if sens["rank_flips"]:
        lines.append("### 检测到的排名翻转（rank flips）")
        lines.append("")
        for f in sens["rank_flips"]:
            ch = "，".join("%s: 第%d→第%d" % (p, v["baseline"], v["scenario"])
                           for p, v in f["changed_ranks"].items())
            lines.append("- 情景 **%s**：新顺序 %s（%s）" % (f["scenario"], " > ".join(f["new_order"]), ch))
        lines.append("")
        lines.append("结论：排序对上述情景中的权重扰动**不稳健**，裁决时应以条件清单锁定分歧维度，"
                     "而非把基准排序当作无争议事实。")
    else:
        lines.append("未检测到排名翻转：排序对单维 ±20% 权重扰动稳健。")
    lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        sys.stderr.write('用法: python3 score_matrix.py <scores.json> <out_dir> [--weights \'{"dim":w,...}\']\n')
        return 2
    src, out_dir = args
    weights = load_rubric_weights()
    if "--weights" in argv:
        i = argv.index("--weights")
        try:
            override = json.loads(argv[i + 1])
            weights.update({k: float(v) for k, v in override.items()})
        except (IndexError, ValueError, TypeError) as e:
            sys.stderr.write("错误: --weights 解析失败: %s\n" % e)
            return 2
    unknown = set(weights) - set(DIMENSIONS)
    if unknown:
        sys.stderr.write("错误: 未知权重维度: %s\n" % ", ".join(sorted(unknown)))
        return 2
    weights = normalize({d: weights.get(d, 0.0) for d in DIMENSIONS})
    try:
        with open(src, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        sys.stderr.write("错误: 无法读取或解析 %s: %s\n" % (src, e))
        return 3

    scorable, unscorable, errors = validate(data)
    if errors:
        sys.stderr.write("scores.json 校验失败（exit 2），问题格如下：\n")
        for e in errors:
            sys.stderr.write("  - %s\n" % e)
        return 2
    if len(scorable) < 2:
        sys.stderr.write("错误: 可评分版本不足 2 个，无法排序。\n")
        return 2

    sens = sensitivity(scorable, weights)
    os.makedirs(out_dir, exist_ok=True)
    md_path = os.path.join(out_dir, "decision_matrix.md")
    emit_md(md_path, scorable, unscorable, weights, sens)
    ranking_doc = {
        "版本排序": [{"rank": i, "plan": p, "weighted_total": round(sens["baseline"]["totals"][p], 4)}
                     for i, p in enumerate(sens["baseline"]["order"], 1)],
        "weights": weights,
        "totals": sens["baseline"]["totals"],
        "unscorable": unscorable,
        "sensitivity": {"scenarios_run": sens["scenarios_run"],
                        "stability": sens["stability"],
                        "rank_flips": sens["rank_flips"]},
    }
    with open(os.path.join(out_dir, "ranking.json"), "w", encoding="utf-8") as f:
        json.dump(ranking_doc, f, ensure_ascii=False, indent=2)
    print("score_matrix 完成: 排序 %s, 情景 %d 个, 翻转 %d 次 -> %s" % (
        " > ".join(sens["baseline"]["order"]), sens["scenarios_run"],
        len(sens["rank_flips"]), out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
