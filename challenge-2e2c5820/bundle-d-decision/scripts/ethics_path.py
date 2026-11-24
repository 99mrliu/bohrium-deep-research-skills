#!/usr/bin/env python3
"""ethics_path.py — 伦理/安全审批路径规则分类器。

用法: python3 ethics_path.py <involvement.json> <out.md>

involvement.json 模式（按版本逐项判定，状态词: true / false / "undetermined"）:
  {"plans": {"v1": {"动物实验": true, "人体样本": false, "危险试剂": true, "个人数据": false},
             "v2": {"动物实验": "undetermined", ...}}}

关键语义（不可违反）:
  - true        → 审批是**前置条件**，措辞一律为「需办理」，绝不写「已批准」；
  - undetermined → 列为**确认项**，须责任专家确认后方可判定，绝不按「不涉及」处理；
  - false       → 不涉及（须另有证据支撑，本脚本不采信无证据的 false）。

规则表: ../references/ethics_rules.json（通用模板，具体以机构规定为准）。

退出码: 0 成功; 2 用法错误/输入模式非法; 3 文件不可读。
"""
import json
import os
import sys

STATUS_UNDETERMINED = {"undetermined", "undetermined ", "未定", "unknown", "null", "none", ""}


def load_rules():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "..", "references", "ethics_rules.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        sys.stderr.write("错误: 无法读取规则表 %s: %s\n" % (path, e))
        sys.exit(3)


def classify(value):
    if value is True:
        return "involved"
    if value is False:
        return "not_involved"
    if value is None:
        return "undetermined"
    s = str(value).strip().lower()
    if s in ("true", "yes", "是", "涉及"):
        return "involved"
    if s in ("false", "no", "否", "不涉及"):
        return "not_involved"
    return "undetermined"


def emit(plan_id, states, rules):
    cats = rules["categories"]
    lines = ["## 版本 %s" % plan_id, ""]
    blockers, confirms = [], []
    for cat, value in states.items():
        st = classify(value)
        rule = cats.get(cat)
        if st == "involved":
            if rule is None:
                lines.append("- **%s**：判定为【涉及】，但规则表无此类别 → 转人工判定审批路径。" % cat)
                blockers.append(cat)
                continue
            d = rule["duration_weeks"]
            lines.append("- **%s**：涉及 → **需办理** %s（前置条件，未办结不得启动相关操作；本表不代表已批准）。"
                         % (cat, rule["approval_level"]))
            lines.append("  - 典型材料：%s" % "；".join(rule["typical_materials"]))
            lines.append("  - 典型周期：约 %d–%d 周。%s" % (d[0], d[1], rule.get("note", "")))
            blockers.append(cat)
        elif st == "undetermined":
            lines.append("- **%s**：状态未定 → **确认项**：须由责任专家/机构主管部门书面确认是否涉及，"
                         "确认前一律按“可能涉及”管理，禁止按“不涉及”推进。" % cat)
            confirms.append(cat)
        else:
            lines.append("- **%s**：不涉及（以材料证据为准；若后续证据变化须重新判定）。" % cat)
    lines.append("")
    if blockers:
        lines.append("该版审批前置项：%s——均标注「需办理」，任何一项未完成，该版结论最高只能为「有条件可行」。"
                     % "、".join(blockers))
    if confirms:
        lines.append("该版确认项：%s——确认结果可能追加审批前置项，时间线须预留余量。" % "、".join(confirms))
    if not blockers and not confirms:
        lines.append("该版无伦理/安全审批前置项。")
    lines.append("")
    return lines


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("用法: python3 ethics_path.py <involvement.json> <out.md>\n")
        return 2
    src, out = argv[1], argv[2]
    rules = load_rules()
    try:
        with open(src, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        sys.stderr.write("错误: 无法读取或解析 %s: %s\n" % (src, e))
        return 3
    plans = data.get("plans")
    if not isinstance(plans, dict) or not plans:
        sys.stderr.write("错误: involvement.json 缺少非空的 plans 对象（exit 2）\n")
        return 2
    lines = ["# 伦理与安全审批路径（规则分类器输出）", "",
             "> 依据 references/ethics_rules.json：通用模板，具体以机构规定为准。"
             "凡「需办理」均为前置条件，绝不表述为「已批准」；凡「undetermined」均为确认项。", ""]
    for pid in sorted(plans):
        states = plans[pid]
        if not isinstance(states, dict):
            sys.stderr.write("错误: plans.%s 不是对象（exit 2）\n" % pid)
            return 2
        lines += emit(pid, states, rules)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("ethics_path 完成: %d 个版本 -> %s" % (len(plans), out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
