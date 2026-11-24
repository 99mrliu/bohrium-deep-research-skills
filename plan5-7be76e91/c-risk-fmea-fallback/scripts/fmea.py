#!/usr/bin/env python3
"""fmea.py — FMEA 分级台账（确定性，纯 stdlib）。

读取单个方案的 risk_register.json，做字段校验与 S×L×D 分级，
输出 fmea.json + fmea.md。

退出码：
  0 = 成功（允许 warning，无缺陷）
  2 = 输入/用法错误（文件缺失、JSON 解析失败、阈值文件非法）
  3 = 质量门拦截（缺陷清单写 stdout，产物仍尽量写出）

缺陷（defect）：
  - 必填字段缺失或类型错误（risk_id/title/trigger_condition/consequence_magnitude/
    severity/likelihood/detectability/mitigation/fallback_ref/evidence_source）
  - severity/likelihood/detectability 不是 1..5 的整数（按 references 锚点范围校验）
  - trigger_condition 或 consequence_magnitude 为空字符串/null
  - risk_id 重复
  - critical/high 级风险的 mitigation 为空
警告（warning，不影响退出码）：
  - consequence_magnitude 不含数字（疑似缺「量级+单位」）
  - critical/high 级风险 fallback_ref 为空（回退完备性由 fallback_graph.py 判定）
"""
import argparse
import json
import sys
from pathlib import Path

EXIT_OK, EXIT_USAGE, EXIT_GATE = 0, 2, 3

REQUIRED_FIELDS = [
    "risk_id", "title", "trigger_condition", "consequence_magnitude",
    "severity", "likelihood", "detectability",
    "mitigation", "fallback_ref", "evidence_source",
]
DEFAULT_THRESHOLDS_PATH = Path(__file__).resolve().parent.parent / "references" / "thresholds.json"

GRADE_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


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


def load_thresholds(path):
    data = load_json(path, "阈值")
    defaults = {
        "critical_if_severity_gte": 5,
        "high_if_severity_gte": 4,
        "high_if_rpn_gte": 60,
        "medium_if_rpn_gte": 25,
    }
    th = {}
    for k, dflt in defaults.items():
        v = data.get(k, dflt)
        if not isinstance(v, int) or isinstance(v, bool):
            print(f"ERROR(exit 2): 阈值 {k} 必须为整数，得到 {v!r}", file=sys.stderr)
            sys.exit(EXIT_USAGE)
        th[k] = v
    return th


def grade_of(severity, rpn, th):
    if severity >= th["critical_if_severity_gte"]:
        return "critical"
    if severity >= th["high_if_severity_gte"] or rpn >= th["high_if_rpn_gte"]:
        return "high"
    if rpn >= th["medium_if_rpn_gte"]:
        return "medium"
    return "low"


def is_blank(v):
    return v is None or (isinstance(v, str) and v.strip() == "")


def main():
    ap = argparse.ArgumentParser(
        description="FMEA 分级：校验 risk_register.json 并按 S×L×D 分为 critical/high/medium/low。"
                    "退出码 0 成功 / 2 输入错误 / 3 质量门缺陷。")
    ap.add_argument("--register", required=True, help="单个方案的 risk_register.json 路径")
    ap.add_argument("--outdir", required=True, help="产物输出目录（fmea.json / fmea.md）")
    ap.add_argument("--thresholds", default=str(DEFAULT_THRESHOLDS_PATH),
                    help="阈值 JSON（默认 references/thresholds.json；覆盖将在输出中声明）")
    ap.add_argument("--note", default=None,
                    help="可选：嵌入 JSON/Markdown 产物顶部的标注（示例产物必须传合成示例标注）")
    args = ap.parse_args()

    thresholds_used_override = (Path(args.thresholds).resolve() != DEFAULT_THRESHOLDS_PATH)
    th = load_thresholds(args.thresholds)
    data = load_json(args.register, "risk_register")

    defects, warnings = [], []
    if not isinstance(data, dict) or not isinstance(data.get("risks"), list):
        print("ERROR(exit 2): risk_register 必须是含 risks 列表的 JSON 对象", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    plan_id = data.get("plan_id", "")
    if is_blank(plan_id):
        defects.append("plan_id 缺失或为空")

    seen_ids = set()
    rows = []
    for idx, r in enumerate(data["risks"]):
        loc = f"risks[{idx}]"
        if not isinstance(r, dict):
            defects.append(f"{loc}: 不是 JSON 对象")
            continue
        rid = r.get("risk_id", f"<missing-{idx}>")
        for fld in REQUIRED_FIELDS:
            if fld not in r:
                defects.append(f"{loc}({rid}): 缺必填字段 {fld}")
        if rid in seen_ids:
            defects.append(f"{loc}: risk_id 重复: {rid}")
        seen_ids.add(rid)
        if is_blank(r.get("trigger_condition")):
            defects.append(f"{loc}({rid}): trigger_condition 为空（禁止「存在一定风险」式空话）")
        if is_blank(r.get("consequence_magnitude")):
            defects.append(f"{loc}({rid}): consequence_magnitude 为空（必须给量级+单位）")
        elif isinstance(r.get("consequence_magnitude"), str) and not any(
                ch.isdigit() for ch in r["consequence_magnitude"]):
            warnings.append(f"{loc}({rid}): consequence_magnitude 不含数字，疑似缺量级+单位")
        sld = {}
        for fld in ("severity", "likelihood", "detectability"):
            v = r.get(fld)
            if not isinstance(v, int) or isinstance(v, bool) or not (1 <= v <= 5):
                defects.append(f"{loc}({rid}): {fld} 必须是 1..5 的整数（references 锚点范围），得到 {v!r}")
            else:
                sld[fld] = v
        if len(sld) == 3:
            rpn = sld["severity"] * sld["likelihood"] * sld["detectability"]
            grade = grade_of(sld["severity"], rpn, th)
            if grade in ("critical", "high"):
                if is_blank(r.get("mitigation")):
                    defects.append(f"{loc}({rid}): {grade} 级风险缺 mitigation（缓解措施）")
                if is_blank(r.get("fallback_ref")):
                    warnings.append(f"{loc}({rid}): {grade} 级风险 fallback_ref 为空，将由 fallback_graph.py 判定")
            rows.append({
                "risk_id": rid,
                "title": r.get("title", ""),
                "severity": sld["severity"],
                "likelihood": sld["likelihood"],
                "detectability": sld["detectability"],
                "rpn": rpn,
                "grade": grade,
                "has_mitigation": not is_blank(r.get("mitigation")),
                "fallback_ref": r.get("fallback_ref") if not is_blank(r.get("fallback_ref")) else None,
            })

    rows.sort(key=lambda x: (GRADE_ORDER[x["grade"]], -x["rpn"], x["risk_id"]))
    counts = {g: sum(1 for r in rows if r["grade"] == g) for g in GRADE_ORDER}

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    ledger = {
        "plan_id": plan_id,
        "tool": "fmea.py",
        "thresholds": th,
        "thresholds_source": ("override:" + Path(args.thresholds).name) if thresholds_used_override
                             else "builtin:references/thresholds.json",
        "grade_counts": counts,
        "risks": rows,
        "warnings": sorted(warnings),
        "defects": sorted(defects),
        "verdict": "FAIL" if defects else "PASS",
    }
    if args.note is not None:
        ledger["note"] = args.note
    (outdir / "fmea.json").write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        f"# FMEA 分级台账 — 方案 {plan_id}",
        "",
        f"- 工具: fmea.py（确定性）",
        f"- 阈值来源: {ledger['thresholds_source']}",
        f"- 阈值: critical if S>={th['critical_if_severity_gte']}; "
        f"high if S>={th['high_if_severity_gte']} 或 RPN>={th['high_if_rpn_gte']}; "
        f"medium if RPN>={th['medium_if_rpn_gte']}",
        f"- 统计: critical={counts['critical']} high={counts['high']} "
        f"medium={counts['medium']} low={counts['low']}",
        f"- 结论: **{ledger['verdict']}**",
        "",
        "| risk_id | S | L | D | RPN | 等级 | 有缓解 | fallback_ref | 标题 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['risk_id']} | {r['severity']} | {r['likelihood']} | {r['detectability']} "
            f"| {r['rpn']} | {r['grade']} | {'是' if r['has_mitigation'] else '否'} "
            f"| {r['fallback_ref'] or '—'} | {r['title']} |")
    if warnings:
        lines += ["", "## 警告"] + [f"- {w}" for w in sorted(warnings)]
    if defects:
        lines += ["", "## 缺陷（质量门 exit 3）"] + [f"- {d}" for d in sorted(defects)]
    md_text = "\n".join(lines) + "\n"
    if args.note is not None:
        md_text = f"> {args.note}\n\n" + md_text
    (outdir / "fmea.md").write_text(md_text, encoding="utf-8")

    if defects:
        print("FMEA 质量门拦截（exit 3），缺陷清单：")
        for d in sorted(defects):
            print(f"  DEFECT: {d}")
        sys.exit(EXIT_GATE)
    print(f"FMEA PASS: plan={plan_id} risks={len(rows)} "
          f"critical={counts['critical']} high={counts['high']} -> {outdir}/fmea.json")
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
