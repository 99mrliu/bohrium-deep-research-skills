#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_extraction.py — 校验模型对单个方案版本的结构化抽取结果

用法:
    python3 validate_extraction.py <extraction.json>

抽取文件必须是如下结构（每个方案版本一个文件）:
{
  "plan_id": "string, 非空",
  "budget_items":   [{"name","unit_price","quantity","currency","stated_subtotal"?,"locator"}],
  "schedule_steps": [{"id","name","duration_hours","depends_on":[...],"resource","locator"}],
  "parameters":     [{"name","value","unit","locator"}],
  "materials":      [{"name","quantity","unit","locator"}],
  "samples":        [{"name","count","locator"}]
}

校验规则:
  - 必填键存在且类型正确；数值字段为非负有限数（quantity/count/duration_hours > 0）。
  - 每个 locator 必须是非空字符串（约定: "<plan_id>#<小节>#<行/条目>"，见 references/extraction_schema.md）。
  - schedule_steps 的 id 不得重复；depends_on 必须引用已声明的 step id。
  - currency 为 1–8 个字母/符号的非空字符串。

退出码:
    0  校验通过
    2  存在违规（全部列出到 stderr）或用法错误 / 文件不可读
"""
import json
import math
import sys
from pathlib import Path

REQUIRED_TOP = ["plan_id", "budget_items", "schedule_steps", "parameters", "materials", "samples"]


def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def nonempty_str(x):
    return isinstance(x, str) and x.strip() != ""


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("用法: python3 validate_extraction.py <extraction.json>\n")
        return 2
    path = Path(argv[1])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("错误(exit 2): 无法读取 %s: %s\n" % (path, exc))
        return 2

    violations = []
    if not isinstance(data, dict):
        violations.append("顶层必须是 JSON object")
        data = {}
    for key in REQUIRED_TOP:
        if key not in data:
            violations.append("缺少必填键 '%s'" % key)
    if "plan_id" in data and not nonempty_str(data.get("plan_id")):
        violations.append("plan_id 必须是非空字符串")
    for key in REQUIRED_TOP[1:]:
        if key in data and not isinstance(data[key], list):
            violations.append("'%s' 必须是 list" % key)

    for i, it in enumerate(data.get("budget_items", []) or []):
        tag = "budget_items[%d]" % i
        if not isinstance(it, dict):
            violations.append("%s 必须是 object" % tag)
            continue
        if not nonempty_str(it.get("name")):
            violations.append("%s.name 缺失或非空字符串" % tag)
        if not is_num(it.get("unit_price")) or it.get("unit_price") < 0:
            violations.append("%s.unit_price 必须 >= 0 的有限数, 实际: %r" % (tag, it.get("unit_price")))
        if not is_num(it.get("quantity")) or it.get("quantity") <= 0:
            violations.append("%s.quantity 必须 > 0, 实际: %r" % (tag, it.get("quantity")))
        if not nonempty_str(it.get("currency")) or len(str(it.get("currency"))) > 8:
            violations.append("%s.currency 非法: %r" % (tag, it.get("currency")))
        if "stated_subtotal" in it and (not is_num(it.get("stated_subtotal")) or it.get("stated_subtotal") < 0):
            violations.append("%s.stated_subtotal 必须 >= 0, 实际: %r" % (tag, it.get("stated_subtotal")))
        if not nonempty_str(it.get("locator")):
            violations.append("%s.locator 必须是非空字符串" % tag)

    step_ids = set()
    for i, st in enumerate(data.get("schedule_steps", []) or []):
        tag = "schedule_steps[%d]" % i
        if not isinstance(st, dict):
            violations.append("%s 必须是 object" % tag)
            continue
        if not nonempty_str(st.get("id")):
            violations.append("%s.id 缺失或非空字符串" % tag)
        elif st["id"] in step_ids:
            violations.append("%s.id 重复: %r" % (tag, st["id"]))
        else:
            step_ids.add(st["id"])
        if not nonempty_str(st.get("name")):
            violations.append("%s.name 缺失或非空字符串" % tag)
        if not is_num(st.get("duration_hours")) or st.get("duration_hours") <= 0:
            violations.append("%s.duration_hours 必须 > 0, 实际: %r" % (tag, st.get("duration_hours")))
        if not isinstance(st.get("depends_on"), list) or not all(nonempty_str(d) for d in st.get("depends_on", [])):
            violations.append("%s.depends_on 必须是非空字符串 list（可为空 list）" % tag)
        if not nonempty_str(st.get("resource")):
            violations.append("%s.resource 缺失或非空字符串" % tag)
        if not nonempty_str(st.get("locator")):
            violations.append("%s.locator 必须是非空字符串" % tag)
    for i, st in enumerate(data.get("schedule_steps", []) or []):
        if isinstance(st, dict):
            for d in st.get("depends_on", []) or []:
                if d not in step_ids:
                    violations.append("schedule_steps[%d].depends_on 引用了未声明的步骤 id: %r" % (i, d))

    for i, p in enumerate(data.get("parameters", []) or []):
        tag = "parameters[%d]" % i
        if not isinstance(p, dict):
            violations.append("%s 必须是 object" % tag)
            continue
        if not nonempty_str(p.get("name")):
            violations.append("%s.name 缺失" % tag)
        if not (is_num(p.get("value")) or nonempty_str(p.get("value"))):
            violations.append("%s.value 必须是数值或数值字符串, 实际: %r" % (tag, p.get("value")))
        if not nonempty_str(p.get("unit")):
            violations.append("%s.unit 必须是非空字符串（无单位请写 '1' 并说明）" % tag)
        if not nonempty_str(p.get("locator")):
            violations.append("%s.locator 必须是非空字符串" % tag)

    for i, m in enumerate(data.get("materials", []) or []):
        tag = "materials[%d]" % i
        if not isinstance(m, dict):
            violations.append("%s 必须是 object" % tag)
            continue
        if not nonempty_str(m.get("name")):
            violations.append("%s.name 缺失" % tag)
        if not is_num(m.get("quantity")) or m.get("quantity") <= 0:
            violations.append("%s.quantity 必须 > 0, 实际: %r" % (tag, m.get("quantity")))
        if not nonempty_str(m.get("unit")):
            violations.append("%s.unit 缺失" % tag)
        if not nonempty_str(m.get("locator")):
            violations.append("%s.locator 必须是非空字符串" % tag)

    for i, s in enumerate(data.get("samples", []) or []):
        tag = "samples[%d]" % i
        if not isinstance(s, dict):
            violations.append("%s 必须是 object" % tag)
            continue
        if not nonempty_str(s.get("name")):
            violations.append("%s.name 缺失" % tag)
        if not (isinstance(s.get("count"), int) and not isinstance(s.get("count"), bool) and s.get("count") > 0):
            violations.append("%s.count 必须是正整数, 实际: %r" % (tag, s.get("count")))
        if not nonempty_str(s.get("locator")):
            violations.append("%s.locator 必须是非空字符串" % tag)

    if violations:
        sys.stderr.write("校验失败(exit 2)，共 %d 处违规:\n" % len(violations))
        for v in violations:
            sys.stderr.write("  - %s\n" % v)
        return 2
    print("校验通过: %s (plan_id=%s, 预算行 %d, 步骤 %d, 参数 %d, 物料 %d, 样本 %d)" % (
        path, data.get("plan_id"), len(data.get("budget_items", [])),
        len(data.get("schedule_steps", [])), len(data.get("parameters", [])),
        len(data.get("materials", [])), len(data.get("samples", []))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
