#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""adjudicate.py — 多种子统计裁决（tolerance adjudication）

读取事前注册的 tolerances.json 与观测 observations.json，对每个“方法 × 指标”
做统计分解：观测值序列 → n / median / mean / spread(max-min) / MAD，
把偏差拆成随机波动（stochastic fluctuation）与系统偏差（systematic deviation），
并做防篡改校验：tolerances 文件的 mtime 必须早于运行日志的最早 mtime。

用法：
    python3 adjudicate.py --tolerances tolerances.json \
        --observations observations.json --out OUTDIR [--runs LOGDIR]

observations.json：{方法名: {指标名: {"values": [数...], "logs": [路径...]}}}
  - values 为空数组 → 该指标判 missing
  - logs 中的路径（若存在于磁盘）参与 preregistration mtime 校验

判定代数（按优先级，先命中先生效）：
  1. 论文未报告值（paper_value 为 null）        → not_comparable
  2. values 为空                                 → missing
  3. |median - paper| <= tolerance               → within_tolerance
  4. 超差，kind=stochastic，spread>0，且至少一个
     观测值落在容差内                             → stochastic_fluctuation
  5. 超差，且 deviation > 3 × spread             → systematic_deviation
  6. 其余超差情形                                 → exceeds_tolerance
  附加规则：kind=stochastic 且 n==1 → 直接判 insufficient_runs（单点无法谈波动）；
           kind=stochastic 且 n==2 → 正常判定，但附加 insufficient_runs 告警。
  指标在观测中出现但未在 tolerances 注册 → not_comparable + unregistered_metric 告警。

attribution_hint（仅供 agent 参考，最终归因必须结合证据人工判断）：
  within_tolerance → none；stochastic_fluctuation → numerical_noise；
  systematic_deviation → systematic；其余 → none。

防篡改：tolerances 文件 mtime >= （--runs 目录及 logs 字段中）最早日志 mtime
  → preregistration_violation=true，全部结论可信度降级，如实写入输出。

输出：OUTDIR/comparison.json 与 OUTDIR/comparison.md
  （表：方法 / 指标 / 论文值 / 中位 / 容差 / 偏差 / 判定 / 告警）

退出码：
  0  全部判定 ∈ {within_tolerance, stochastic_fluctuation, not_comparable,
     insufficient_runs} 且无违规
  1  存在 systematic_deviation / exceeds_tolerance / missing /
     preregistration_violation
  2  结构错误（输入无法解析等）
仅使用 Python3 标准库。
"""

import argparse
import json
import os
import statistics
import sys
from datetime import datetime, timezone

J_OK = {"within_tolerance", "stochastic_fluctuation", "not_comparable",
        "insufficient_runs"}
J_BAD = {"systematic_deviation", "exceeds_tolerance", "missing"}

HINTS = {
    "within_tolerance": "none",
    "stochastic_fluctuation": "numerical_noise",
    "systematic_deviation": "systematic",
    "exceeds_tolerance": "none",
    "not_comparable": "none",
    "missing": "none",
    "insufficient_runs": "none",
}


def fail(msg):
    print(f"[adjudicate] ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path, what):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        fail(f"无法读取 {what}（{path}）：{e}")


def collect_log_mtimes(runs_dir, extra_logs):
    """收集日志文件 mtime：--runs 目录递归 + observations 里的 logs 路径。"""
    mtimes = []
    if runs_dir:
        if not os.path.isdir(runs_dir):
            fail(f"--runs 目录不存在：{runs_dir}")
        for root, _dirs, files in os.walk(runs_dir):
            for fn in files:
                try:
                    mtimes.append(os.path.getmtime(os.path.join(root, fn)))
                except OSError:
                    pass
    for p in extra_logs:
        if isinstance(p, str) and os.path.isfile(p):
            try:
                mtimes.append(os.path.getmtime(p))
            except OSError:
                pass
    return mtimes


def judge(kind, paper_num, tol, values):
    """返回 (judgment, alerts[], stats dict)。判定代数见模块 docstring。"""
    stats = {"n": 0, "median": None, "mean": None, "spread": None,
             "mad": None, "deviation_abs": None, "deviation_rel": None}
    alerts = []
    if paper_num is None or tol is None:
        return "not_comparable", alerts, stats
    if not values:
        return "missing", alerts, stats

    n = len(values)
    med = statistics.median(values)
    mean = statistics.fmean(values)
    spread = max(values) - min(values)
    mad = statistics.median([abs(v - med) for v in values])
    dev_abs = abs(med - paper_num)
    dev_rel = abs(dev_abs / paper_num) if paper_num != 0 else None
    stats.update(n=n, median=med, mean=mean, spread=spread, mad=mad,
                 deviation_abs=dev_abs, deviation_rel=dev_rel)

    if kind == "stochastic" and n == 1:
        return "insufficient_runs", alerts, stats

    if dev_abs <= tol:
        judgment = "within_tolerance"
    elif (kind == "stochastic" and spread > 0
          and any(abs(v - paper_num) <= tol for v in values)):
        judgment = "stochastic_fluctuation"
    elif dev_abs > 3 * spread:
        judgment = "systematic_deviation"
    else:
        judgment = "exceeds_tolerance"

    if kind == "stochastic" and n < 3:
        alerts.append("insufficient_runs")
    return judgment, alerts, stats


def fmt(x):
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:.6g}"
    return str(x)


def main():
    ap = argparse.ArgumentParser(description="多种子统计裁决：偏差=随机分量+系统分量。")
    ap.add_argument("--tolerances", required=True)
    ap.add_argument("--observations", required=True)
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--runs", default=None,
                    help="运行日志目录（用于 preregistration mtime 校验）")
    args = ap.parse_args()

    tol_doc = load_json(args.tolerances, "tolerances")
    obs = load_json(args.observations, "observations")
    if not isinstance(tol_doc, dict) or not isinstance(tol_doc.get("items"), list):
        fail("tolerances.json 结构非法（缺 items）")
    if not isinstance(obs, dict):
        fail("observations.json 必须是 {方法名: {指标名: {...}}} 的对象")

    tol_items = {it["name"]: it for it in tol_doc["items"]}

    # ---- 防篡改校验：容差文件 mtime 必须早于最早日志 mtime ----
    extra_logs = []
    for _method, metrics in obs.items():
        if not isinstance(metrics, dict):
            continue
        for _metric, rec in metrics.items():
            if isinstance(rec, dict):
                extra_logs.extend(rec.get("logs") or [])
    log_mtimes = collect_log_mtimes(args.runs, extra_logs)
    violation = False
    tol_mtime = os.path.getmtime(args.tolerances)
    earliest_log = min(log_mtimes) if log_mtimes else None
    if earliest_log is not None and tol_mtime >= earliest_log:
        violation = True

    # ---- 逐 方法 × 指标 裁决 ----
    comparisons = []
    for method in sorted(obs):
        metrics = obs[method]
        if not isinstance(metrics, dict):
            fail(f"observations[{method!r}] 不是对象")
        metric_names = sorted(set(metrics) | set(tol_items))
        for mname in metric_names:
            rec = metrics.get(mname)
            tit = tol_items.get(mname)
            alerts = []
            if tit is None:
                # 观测里出现但未注册容差：不得现编容差，判 not_comparable
                comparisons.append({
                    "method": method, "metric": mname,
                    "paper_value": None, "kind": None, "tolerance_abs": None,
                    "n": (len(rec.get("values", [])) if isinstance(rec, dict) else 0),
                    "median": None, "mean": None, "spread": None, "mad": None,
                    "deviation_abs": None, "deviation_rel": None,
                    "judgment": "not_comparable",
                    "alerts": ["unregistered_metric"],
                    "attribution_hint": "none",
                })
                continue
            paper_num = tit.get("paper_value_num")
            tol = tit.get("tolerance_abs")
            kind = tit.get("kind", "deterministic")
            if rec is None:
                judgment, stats = "missing", {"n": 0, "median": None, "mean": None,
                                              "spread": None, "mad": None,
                                              "deviation_abs": None,
                                              "deviation_rel": None}
            else:
                values = rec.get("values", [])
                if not isinstance(values, list) or not all(
                        isinstance(v, (int, float)) and not isinstance(v, bool)
                        for v in values):
                    fail(f"observations[{method!r}][{mname!r}].values 必须是数值数组")
                judgment, alerts, stats = judge(kind, paper_num, tol, values)
            comparisons.append({
                "method": method, "metric": mname,
                "paper_value": tit.get("paper_value"),
                "unit": tit.get("unit", ""),
                "kind": kind,
                "aggregation": tit.get("aggregation"),
                "tolerance_abs": tol,
                "derivation": tit.get("derivation"),
                **stats,
                "judgment": judgment,
                "alerts": alerts,
                "attribution_hint": HINTS[judgment],
            })

    bad = [c for c in comparisons if c["judgment"] in J_BAD]
    summary = {
        "total": len(comparisons),
        "within_tolerance": sum(c["judgment"] == "within_tolerance" for c in comparisons),
        "stochastic_fluctuation": sum(c["judgment"] == "stochastic_fluctuation" for c in comparisons),
        "systematic_deviation": sum(c["judgment"] == "systematic_deviation" for c in comparisons),
        "exceeds_tolerance": sum(c["judgment"] == "exceeds_tolerance" for c in comparisons),
        "not_comparable": sum(c["judgment"] == "not_comparable" for c in comparisons),
        "missing": sum(c["judgment"] == "missing" for c in comparisons),
        "insufficient_runs": sum(c["judgment"] == "insufficient_runs" for c in comparisons),
    }

    out_doc = {
        "_schema": "tolerance-court/comparison/v1",
        "created_at": utc_now(),
        "tolerances_file": os.path.abspath(args.tolerances),
        "tolerances_created_at": tol_doc.get("created_at"),
        "tolerances_change_records": tol_doc.get("change_records", []),
        "observations_file": os.path.abspath(args.observations),
        "runs_dir": os.path.abspath(args.runs) if args.runs else None,
        "earliest_log_mtime": earliest_log,
        "tolerances_mtime": tol_mtime,
        "preregistration_violation": violation,
        "summary": summary,
        "comparisons": comparisons,
    }

    os.makedirs(args.out, exist_ok=True)
    out_json = os.path.join(args.out, "comparison.json")
    out_md = os.path.join(args.out, "comparison.md")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(out_doc, f, ensure_ascii=False, indent=2)
        f.write("\n")

    lines = []
    lines.append("# 容差裁决报告（tolerance adjudication）\n")
    lines.append(f"- 生成时间：{out_doc['created_at']}")
    lines.append(f"- 容差注册时间：{fmt(tol_doc.get('created_at'))}")
    lines.append(f"- preregistration_violation：**{str(violation).lower()}**"
                 + ("（容差文件不早于运行日志：判定可信度降级，须如实写入 result.json）"
                    if violation else ""))
    if tol_doc.get("change_records"):
        lines.append(f"- 容差文件曾被覆盖重建 {len(tol_doc['change_records'])} 次"
                     "（change_records 见 comparison.json）")
    lines.append("")
    lines.append("| 方法 | 指标 | 论文值 | 中位 | 容差 | 偏差(abs) | 判定 | 告警 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for c in comparisons:
        alerts = ",".join(c["alerts"]) if c["alerts"] else ""
        lines.append(
            f"| {c['method']} | {c['metric']} | {fmt(c.get('paper_value'))} "
            f"| {fmt(c.get('median'))} | ±{fmt(c.get('tolerance_abs'))} "
            f"| {fmt(c.get('deviation_abs'))} | **{c['judgment']}** | {alerts} |")
    lines.append("")
    lines.append("## 汇总\n")
    for k, v in summary.items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("> attribution_hint 仅为机械建议（numerical_noise / systematic / none），"
                 "最终归因由 agent 结合证据决定；合成代码 ≠ 作者原代码，"
                 "合成数据上的 within_tolerance 不能写成论文数值复现。")
    lines.append("")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[adjudicate] {summary['total']} 项裁决 → {out_json} / {out_md}")
    for k in ("within_tolerance", "stochastic_fluctuation", "systematic_deviation",
              "exceeds_tolerance", "not_comparable", "missing", "insufficient_runs"):
        print(f"  {k}: {summary[k]}")
    print(f"  preregistration_violation: {violation}")

    if violation or bad:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
