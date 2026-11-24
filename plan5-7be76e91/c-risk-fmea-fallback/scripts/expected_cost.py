#!/usr/bin/env python3
"""expected_cost.py — 风险调整期望代价（确定性，纯 stdlib）。

公式（每方案）：
  expected_risk_cost  = Σ_i  P(likelihood_i) × consequence_cost_cny_i
  expected_risk_time  = Σ_i  P(likelihood_i) × consequence_time_days_i
  mitigation_cost     = Σ_i  mitigation_cost_cny_i（仅计入带 cost 字段的缓解）
  mitigation_time     = Σ_i  mitigation_time_days_i
  risk_adjusted_cost  = base_cost_cny + expected_risk_cost + mitigation_cost
  risk_adjusted_time  = base_time_days + expected_risk_time + mitigation_time

说明：缓解投入是确定发生的支出，故为加项；缓解对风险的削减效果通过
登记时调低 likelihood/consequence 体现（定级责任在模型，见 risk_method.md）。

likelihood→概率映射内置 {1:0.05, 2:0.15, 3:0.35, 4:0.6, 5:0.85}；
单条风险可用 "likelihood_prob_override": <0..1> 覆盖，覆盖将在输出中声明。

退出码：
  0 = 成功
  2 = 输入/用法错误（base 缺失、JSON 非法、likelihood 越界、override 越界）
  3 = 保留（本脚本无质量门）

用法：
  单方案：--register r.json --base base.json --outdir DIR
  多方案对比：--register r1.json --register r2.json ... --base base.json --outdir DIR
    额外写出 comparison.json / comparison.md（按 risk_adjusted_cost 升序排序）。
"""
import argparse
import json
import sys
from pathlib import Path

EXIT_OK, EXIT_USAGE, EXIT_GATE = 0, 2, 3
DEFAULT_PROB_MAP = {1: 0.05, 2: 0.15, 3: 0.35, 4: 0.6, 5: 0.85}


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


def num(v, default=0.0):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else default


def usage_error(msg):
    print(f"ERROR(exit 2): {msg}", file=sys.stderr)
    sys.exit(EXIT_USAGE)


def compute_plan(register_path, base_entry):
    data = load_json(register_path, "risk_register")
    if not isinstance(data, dict) or not isinstance(data.get("risks"), list):
        usage_error(f"risk_register 必须是含 risks 列表的 JSON 对象: {register_path}")
    plan_id = data.get("plan_id") or Path(register_path).stem
    items, overrides = [], []
    exp_cost = exp_time = mit_cost = mit_time = 0.0
    for idx, r in enumerate(data["risks"]):
        if not isinstance(r, dict):
            usage_error(f"{register_path} risks[{idx}] 不是 JSON 对象")
        rid = r.get("risk_id", f"<missing-{idx}>")
        lv = r.get("likelihood")
        if not isinstance(lv, int) or isinstance(lv, bool) or not (1 <= lv <= 5):
            usage_error(f"{register_path} {rid}: likelihood 必须是 1..5 整数，得到 {lv!r}")
        ov = r.get("likelihood_prob_override")
        if ov is not None:
            if not isinstance(ov, (int, float)) or isinstance(ov, bool) or not (0.0 <= float(ov) <= 1.0):
                usage_error(f"{register_path} {rid}: likelihood_prob_override 必须在 [0,1]，得到 {ov!r}")
            prob = float(ov)
            overrides.append({"risk_id": rid, "likelihood": lv, "prob_override": prob})
        else:
            prob = DEFAULT_PROB_MAP[lv]
        cc = num(r.get("consequence_cost_cny"))
        ct = num(r.get("consequence_time_days"))
        mc = num(r.get("mitigation_cost_cny"))
        mt = num(r.get("mitigation_time_days"))
        exp_cost += prob * cc
        exp_time += prob * ct
        mit_cost += mc
        mit_time += mt
        items.append({
            "risk_id": rid,
            "likelihood": lv,
            "prob": prob,
            "prob_source": "override" if ov is not None else "builtin_map",
            "consequence_cost_cny": cc,
            "consequence_time_days": ct,
            "expected_cost_cny": round(prob * cc, 4),
            "expected_time_days": round(prob * ct, 4),
            "mitigation_cost_cny": mc,
            "mitigation_time_days": mt,
        })
    base_cost = num(base_entry["base_cost_cny"])
    base_time = num(base_entry["base_time_days"])
    return {
        "plan_id": plan_id,
        "base_cost_cny": base_cost,
        "base_time_days": base_time,
        "base_source": base_entry.get("base_source", ""),
        "expected_risk_cost_cny": round(exp_cost, 4),
        "expected_risk_time_days": round(exp_time, 4),
        "mitigation_cost_cny": round(mit_cost, 4),
        "mitigation_time_days": round(mit_time, 4),
        "risk_adjusted_cost_cny": round(base_cost + exp_cost + mit_cost, 4),
        "risk_adjusted_time_days": round(base_time + exp_time + mit_time, 4),
        "likelihood_prob_map": {str(k): v for k, v in sorted(DEFAULT_PROB_MAP.items())},
        "prob_overrides": overrides,
        "items": items,
    }


def render_plan_md(p):
    lines = [
        f"# 风险调整期望代价台账 — 方案 {p['plan_id']}",
        "",
        "- 公式: risk_adjusted = base + Σ P(L)×后果 + 缓解投入（缓解为确定支出，记加项）",
        f"- likelihood→概率映射: {p['likelihood_prob_map']}",
        "",
        f"| 项 | 成本 (CNY) | 时间 (天) |",
        f"|---|---|---|",
        f"| base（情景给定） | {p['base_cost_cny']} | {p['base_time_days']} |",
        f"| 期望风险代价 Σ P(L)×后果 | {p['expected_risk_cost_cny']} | {p['expected_risk_time_days']} |",
        f"| 缓解投入合计 | {p['mitigation_cost_cny']} | {p['mitigation_time_days']} |",
        f"| **风险调整合计** | **{p['risk_adjusted_cost_cny']}** | **{p['risk_adjusted_time_days']}** |",
        "",
        "| risk_id | L | P(L) | 来源 | 后果成本 | 期望成本 | 缓解成本 |",
        "|---|---|---|---|---|---|---|",
    ]
    for it in p["items"]:
        lines.append(
            f"| {it['risk_id']} | {it['likelihood']} | {it['prob']} | {it['prob_source']} "
            f"| {it['consequence_cost_cny']} | {it['expected_cost_cny']} | {it['mitigation_cost_cny']} |")
    if p["prob_overrides"]:
        lines += ["", "## 概率覆盖声明"] + [
            f"- {o['risk_id']}: L={o['likelihood']} 覆盖为 P={o['prob_override']}" for o in p["prob_overrides"]]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(
        description="风险调整期望代价：base + ΣP(L)×后果 + 缓解投入；多 --register 时输出方案对比排序。"
                    "退出码 0 成功 / 2 输入错误。")
    ap.add_argument("--register", required=True, action="append",
                    help="risk_register.json 路径（可重复，≥2 个时输出对比）")
    ap.add_argument("--base", required=True,
                    help='base 输入 JSON：{"plans": {"P1": {"base_cost_cny":..,"base_time_days":..,"base_source":..}}}')
    ap.add_argument("--outdir", required=True, help="产物输出目录")
    ap.add_argument("--note", default=None,
                    help="可选：嵌入 JSON/Markdown 产物顶部的标注（示例产物必须传合成示例标注）")
    args = ap.parse_args()

    base_all = load_json(args.base, "base 输入")
    plans_base = base_all.get("plans") if isinstance(base_all, dict) else None
    if not isinstance(plans_base, dict):
        usage_error("base 输入必须是含 plans 对象的 JSON")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    results = []
    for reg in args.register:
        head = load_json(reg, "risk_register")
        pid = head.get("plan_id") or Path(reg).stem
        if pid not in plans_base:
            usage_error(f"base 输入缺失方案 {pid}（输入 base 缺失 → exit 2）")
        entry = plans_base[pid]
        if not isinstance(entry, dict) or "base_cost_cny" not in entry or "base_time_days" not in entry:
            usage_error(f"base 输入方案 {pid} 缺 base_cost_cny/base_time_days（输入 base 缺失 → exit 2）")
        results.append(compute_plan(reg, entry))

    for p in results:
        if args.note is not None:
            p["note"] = args.note
        (outdir / f"expected_cost_{p['plan_id']}.json").write_text(
            json.dumps(p, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        plan_md = render_plan_md(p)
        if args.note is not None:
            plan_md = f"> {args.note}\n\n" + plan_md
        (outdir / f"expected_cost_{p['plan_id']}.md").write_text(plan_md, encoding="utf-8")

    if len(results) >= 2:
        ranking = sorted(results, key=lambda p: (p["risk_adjusted_cost_cny"],
                                                 p["risk_adjusted_time_days"], p["plan_id"]))
        comp = {
            "tool": "expected_cost.py",
            "criterion": "risk_adjusted_cost_cny 升序（并列看 time，再并列看 plan_id）",
            "ranking": [{"rank": i + 1, "plan_id": p["plan_id"],
                         "risk_adjusted_cost_cny": p["risk_adjusted_cost_cny"],
                         "risk_adjusted_time_days": p["risk_adjusted_time_days"]}
                        for i, p in enumerate(ranking)],
        }
        if args.note is not None:
            comp["note"] = args.note
        (outdir / "comparison.json").write_text(
            json.dumps(comp, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        lines = [
            "# 方案间风险调整代价对比",
            "",
            f"- 排序准则: {comp['criterion']}",
            "",
            "| 名次 | plan_id | 风险调整成本 (CNY) | 风险调整时间 (天) |",
            "|---|---|---|---|",
        ]
        for row in comp["ranking"]:
            lines.append(f"| {row['rank']} | {row['plan_id']} "
                         f"| {row['risk_adjusted_cost_cny']} | {row['risk_adjusted_time_days']} |")
        comp_md = "\n".join(lines) + "\n"
        if args.note is not None:
            comp_md = f"> {args.note}\n\n" + comp_md
        (outdir / "comparison.md").write_text(comp_md, encoding="utf-8")

    for p in results:
        print(f"OK: {p['plan_id']} risk_adjusted_cost={p['risk_adjusted_cost_cny']} CNY, "
              f"time={p['risk_adjusted_time_days']} d")
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
