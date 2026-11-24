#!/usr/bin/env python3
"""validate_risk_register.py — 风险登记表 lint + 排序输出。

用法: python3 validate_risk_register.py <risks.json> <out.md>

每条风险必须含 5 字段: risk, trigger_signal, consequence, degradation_path(降级路径),
escalation(转人工节点)；category 限六类（见 references/risk_taxonomy.md）:
设备故障 / 材料批次 / 样本量不足 / 参数越界 / 伦理安全 / 其他。

规则:
  - 缺字段/非法类别 → exit 2，逐条列出；
  - 触发信号近似重复（相似度 ≥0.85）→ 警告（不阻断）；
  - 无 plan_locator 或 locator 不含任何已知版本号 → 警告（不阻断）；
  - 给定 likelihood 与 impact(1-5) 时，按 severity=likelihood×impact 降序输出。

risks.json 模式:
  {"plan_ids": ["v1","v2","v3"],
   "risks": [{"risk": "...", "category": "设备故障", "trigger_signal": "...",
              "consequence": "...", "degradation_path": "...", "escalation": "...",
              "plan_locator": "plans[2].sections.设备", "likelihood": 3, "impact": 4}]}

退出码: 0 成功（可有警告）; 2 校验失败/用法错误; 3 文件不可读。
"""
import difflib
import json
import os
import sys

REQUIRED = ["risk", "trigger_signal", "consequence", "degradation_path", "escalation"]
CATEGORIES = ["设备故障", "材料批次", "样本量不足", "参数越界", "伦理安全", "其他"]
DUP_THRESHOLD = 0.85


def norm(s):
    return "".join(str(s).split())


def validate(data):
    risks = data.get("risks")
    if not isinstance(risks, list) or not risks:
        return None, None, ["risks.json 缺少非空的 risks 数组"]
    plan_ids = [str(p) for p in data.get("plan_ids", [])]
    errors = []
    for i, r in enumerate(risks):
        if not isinstance(r, dict):
            errors.append("risks[%d]: 不是对象" % i)
            continue
        name = r.get("risk", "risks[%d]" % i)
        for f in REQUIRED:
            if not str(r.get(f, "")).strip():
                errors.append("风险「%s」缺必填字段 %s" % (name, f))
        cat = r.get("category")
        if cat not in CATEGORIES:
            errors.append("风险「%s」category 非法: %r（限 %s）" % (name, cat, "/".join(CATEGORIES)))
        for opt in ("likelihood", "impact"):
            if opt in r and not (isinstance(r[opt], int) and 1 <= r[opt] <= 5):
                errors.append("风险「%s」%s 必须是 1-5 整数" % (name, opt))
    return risks, plan_ids, errors


def lint_warnings(risks, plan_ids):
    warnings = []
    # 近似重复触发信号
    for i in range(len(risks)):
        for j in range(i + 1, len(risks)):
            a, b = norm(risks[i].get("trigger_signal", "")), norm(risks[j].get("trigger_signal", ""))
            if a and b:
                sim = difflib.SequenceMatcher(None, a, b).ratio()
                if sim >= DUP_THRESHOLD:
                    warnings.append("近似重复触发信号（相似度 %.2f）: 「%s」≈「%s」——请合并或区分监测口径" % (
                        sim, risks[i].get("risk"), risks[j].get("risk")))
    # 缺计划定位
    for r in risks:
        loc = str(r.get("plan_locator", "")).strip()
        if not loc:
            warnings.append("风险「%s」无 plan_locator，无法挂接到任何版本章节" % r.get("risk"))
        elif plan_ids and not any(p in loc for p in plan_ids):
            warnings.append("风险「%s」的 plan_locator「%s」不含已知版本号（%s）" % (
                r.get("risk"), loc, "/".join(plan_ids)))
    return warnings


def emit_md(path, risks, warnings):
    def sev(r):
        if isinstance(r.get("likelihood"), int) and isinstance(r.get("impact"), int):
            return r["likelihood"] * r["impact"]
        return -1
    ordered = sorted(risks, key=lambda r: (-sev(r), str(r.get("risk"))))
    lines = ["# 风险登记表", ""]
    if warnings:
        lines += ["## Lint 警告（不阻断，须人工处理）", ""]
        for w in warnings:
            lines.append("- ⚠️ " + w)
        lines.append("")
    lines += ["## 风险清单（按 severity = likelihood × impact 降序；无评分者排末位）", ""]
    lines.append("| # | 风险 | 类别 | severity | 触发信号 | 后果 | 降级路径 | 转人工节点 | 定位 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(ordered, 1):
        s = sev(r)
        s_txt = "%d（%d×%d）" % (s, r["likelihood"], r["impact"]) if s >= 0 else "未评分"
        lines.append("| %d | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            i, r.get("risk", ""), r.get("category", ""), s_txt,
            r.get("trigger_signal", ""), r.get("consequence", ""),
            r.get("degradation_path", ""), r.get("escalation", ""),
            r.get("plan_locator", "—")))
    lines.append("")
    lines.append("治理口径：任何「转人工节点」条件被触发时，自动流程必须停止，等待 PI/专家裁决，禁止自动继续。")
    lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("用法: python3 validate_risk_register.py <risks.json> <out.md>\n")
        return 2
    src, out = argv[1], argv[2]
    try:
        with open(src, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        sys.stderr.write("错误: 无法读取或解析 %s: %s\n" % (src, e))
        return 3
    risks, plan_ids, errors = validate(data)
    if errors:
        sys.stderr.write("风险登记校验失败（exit 2）：\n")
        for e in errors:
            sys.stderr.write("  - %s\n" % e)
        return 2
    warnings = lint_warnings(risks, plan_ids)
    for w in warnings:
        sys.stderr.write("警告: %s\n" % w)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    emit_md(out, risks, warnings)
    print("validate_risk_register 完成: %d 条风险, %d 条警告 -> %s" % (len(risks), len(warnings), out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
