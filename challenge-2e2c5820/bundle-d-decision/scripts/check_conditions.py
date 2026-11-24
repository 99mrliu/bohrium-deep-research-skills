#!/usr/bin/env python3
"""check_conditions.py — 裁决与条件清单一致性 lint。

用法: python3 check_conditions.py <conditions.json> <verdict> <out.md>

<verdict> 为全案总体裁决: 可行 / 有条件可行 / 不可行 / auto（auto 表示只做逐版 lint）。

conditions.json 模式（逐版给出裁决）:
  {"plans": {
     "v2": {"verdict": "有条件可行",
            "conditions": [{"description": "...", "owner": "...", "verification_method": "...",
                            "blocking": true, "linked_item": "..."}],
            "gating_reasons": []},
     "v1": {"verdict": "可行", "conditions": [], "gating_reasons": []},
     "v9": {"verdict": "不可行", "conditions": [], "gating_reasons": ["..."]}}}

Lint 规则:
  - 版本裁决 = 有条件可行: 每条 condition 必须有 description/owner(责任方)/verification_method/
    blocking(bool)/linked_item，且至少 1 条 → 否则 exit 2 并列出；
  - 版本裁决 = 可行 但 conditions 非空 → 警告（自相矛盾）；
  - 版本裁决 = 不可行 → 必须 ≥1 条 gating_reason，否则 exit 2；
  - 总体裁决 = 有条件可行: 全案须至少存在 1 条条件；
  - 总体裁决 = 可行: 任何版本存在条件 → 警告；
  - 总体裁决 = 不可行: 全案须 ≥1 条 gating_reason。

产出: <out.md>（建议命名 条件清单.md）。退出码: 0 成功（可有警告）; 2 校验失败/用法错误; 3 文件不可读。
"""
import json
import os
import sys

VERDICTS = ["可行", "有条件可行", "不可行", "auto"]
COND_FIELDS = ["description", "owner", "verification_method", "blocking", "linked_item"]


def lint_plan(pid, entry):
    errors, warnings = [], []
    verdict = entry.get("verdict")
    if verdict not in VERDICTS[:-1]:
        return ["%s: verdict 非法 %r（限 可行/有条件可行/不可行）" % (pid, verdict)], warnings
    conds = entry.get("conditions", [])
    gating = entry.get("gating_reasons", [])
    if not isinstance(conds, list) or not isinstance(gating, list):
        return ["%s: conditions 与 gating_reasons 必须是数组" % pid], warnings
    if verdict == "有条件可行":
        if not conds:
            errors.append("%s: 裁决为有条件可行但 conditions 为空" % pid)
        for i, c in enumerate(conds):
            if not isinstance(c, dict):
                errors.append("%s/conditions[%d]: 不是对象" % (pid, i))
                continue
            for f in COND_FIELDS:
                if f == "blocking":
                    if not isinstance(c.get("blocking"), bool):
                        errors.append("%s/conditions[%d]: blocking 必须是布尔值" % (pid, i))
                elif not str(c.get(f, "")).strip():
                    errors.append("%s/conditions[%d]: 缺字段 %s（责任方/验证方法/关联项均不得为空）" % (pid, i, f))
    elif verdict == "可行":
        if conds:
            warnings.append("%s: 裁决为「可行」但附带了 %d 条条件——自相矛盾，"
                            "应改为「有条件可行」或清空条件" % (pid, len(conds)))
    elif verdict == "不可行":
        if not gating:
            errors.append("%s: 裁决为不可行但缺少 gating_reasons（至少 1 条）" % pid)
    return errors, warnings


def main(argv):
    if len(argv) != 4:
        sys.stderr.write("用法: python3 check_conditions.py <conditions.json> <verdict> <out.md>\n")
        sys.stderr.write("  verdict ∈ {可行, 有条件可行, 不可行, auto}\n")
        return 2
    src, overall, out = argv[1], argv[2], argv[3]
    if overall not in VERDICTS:
        sys.stderr.write("错误: verdict 必须是 %s 之一\n" % "/".join(VERDICTS))
        return 2
    try:
        with open(src, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        sys.stderr.write("错误: 无法读取或解析 %s: %s\n" % (src, e))
        return 3
    plans = data.get("plans")
    if not isinstance(plans, dict) or not plans:
        sys.stderr.write("错误: conditions.json 缺少非空的 plans 对象（exit 2）\n")
        return 2

    all_errors, all_warnings = [], []
    for pid in sorted(plans):
        e, w = lint_plan(pid, plans[pid])
        all_errors += e
        all_warnings += w

    total_conds = sum(len(plans[p].get("conditions", [])) for p in plans)
    total_gating = sum(len(plans[p].get("gating_reasons", [])) for p in plans)
    if overall == "有条件可行" and total_conds == 0:
        all_errors.append("总体裁决为「有条件可行」但全案无任何条件")
    if overall == "可行" and total_conds > 0:
        all_warnings.append("总体裁决为「可行」但全案存在 %d 条条件——不一致" % total_conds)
    if overall == "不可行" and total_gating == 0:
        all_errors.append("总体裁决为「不可行」但全案无 gating_reasons")

    if all_errors:
        sys.stderr.write("条件清单校验失败（exit 2）：\n")
        for e in all_errors:
            sys.stderr.write("  - %s\n" % e)
        return 2
    for w in all_warnings:
        sys.stderr.write("警告: %s\n" % w)

    lines = ["# 条件清单（裁决治理）", "",
             "总体裁决：**%s**" % overall, ""]
    if all_warnings:
        lines.append("## Lint 警告")
        lines += ["- ⚠️ " + w for w in all_warnings] + [""]
    for pid in sorted(plans):
        entry = plans[pid]
        lines += ["## 版本 %s — 裁决：%s" % (pid, entry.get("verdict")), ""]
        conds = entry.get("conditions", [])
        if conds:
            lines.append("| # | 条件 | 责任方 | 验证方法 | 阻断性 | 关联项 |")
            lines.append("|---|---|---|---|---|---|")
            for i, c in enumerate(conds, 1):
                lines.append("| %d | %s | %s | %s | %s | %s |" % (
                    i, c.get("description", ""), c.get("owner", ""),
                    c.get("verification_method", ""),
                    "阻断（未满足不得启动）" if c.get("blocking") else "非阻断（并行跟踪）",
                    c.get("linked_item", "")))
            lines.append("")
        for g in entry.get("gating_reasons", []):
            lines.append("- 门槛原因：%s" % g)
        if entry.get("gating_reasons"):
            lines.append("")
    lines.append("治理口径：阻断性条件未关闭前，对应版本不得表述为「可行」；"
                 "确认项未被责任方书面关闭前，不得表述为「已批准/已确认」。")
    lines.append("")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("check_conditions 完成: %d 个版本, %d 条条件, %d 条警告 -> %s" % (
        len(plans), total_conds, len(all_warnings), out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
