#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""triage.py — 异常分类处置表执行器。

输入一个异常情况描述文件（JSON），按 references/exception_playbook.md 的
规则输出处置动作 JSON：占位写法、缺口清单条目、result.json 应更新的
uncertainty/status 建议。未知类型给出保守默认（标待确认 + 列缺口 +
继续其余部分），不中断流程。

输入 JSON 形态（单个对象或对象数组）：
  {"type": "material_missing", "detail": "缺少申请人近三年论文清单",
   "location": "研究基础"}   # detail/location 可选

已知类型：pdf_unreadable / material_missing / material_conflict /
oversized_input / format_conflict / citation_unverifiable / budget_exhausted

退出码：0 成功（含未知类型的保守默认）；1 输入/环境错误。
"""
import argparse
import json
import sys

PLACEHOLDER = "【待申请人确认：%s】"

# 与 references/exception_playbook.md 对应的处置规则表
RULES = {
    "pdf_unreadable": {
        "识别特征": "PDF 加密、无文本层或 pdftotext 输出为空/乱码",
        "actions": [
            "先用 pdftotext 重试并记录命令与退出码；失败则声明该 PDF 不可读",
            "在对应章节写入占位：" + PLACEHOLDER % "材料《文件名》不可读，请提供可读版本或关键内容摘录",
            "不得按文件名或领域标签补造该材料内容",
        ],
        "gap_entry": "材料不可读：{detail}（{location}）——对应章节留占位，待可读版本",
        "uncertainty": "存在不可读材料，相关章节内容为占位，非成稿。",
        "status_advice": "partial",
    },
    "material_missing": {
        "识别特征": "case/task 引用的材料文件在 /input 中不存在，或组织方声明申请人证据缺失",
        "actions": [
            "在对应章节写入占位：" + PLACEHOLDER % "请补充：{detail}",
            "把缺失项逐条写入缺口清单，禁止编造申请人成果",
            "继续完成其余有材料支撑的章节",
        ],
        "gap_entry": "材料缺失：{detail}（{location}）",
        "uncertainty": "组织方/案例材料未提供 {detail}，相关部分以占位处理。",
        "status_advice": "partial",
    },
    "material_conflict": {
        "识别特征": "两份材料对同一事实给出相互矛盾的陈述（数字、日期、结论）",
        "actions": [
            "两份陈述都如实记录并标注各自来源，不擅自取舍",
            "在正文写入占位：" + PLACEHOLDER % "材料间存在冲突（{detail}），请确认以哪份为准",
            "冲突项写入缺口清单与 uncertainty",
        ],
        "gap_entry": "材料冲突：{detail}（{location}）——两份来源矛盾，待确认",
        "uncertainty": "材料冲突未决：{detail}。",
        "status_advice": "partial",
    },
    "oversized_input": {
        "识别特征": "材料体积超出单次请求可处理范围（长 PDF/多文件）",
        "actions": [
            "按章节/页码切片读取，每片读毕立即把要点落盘到 /app/work 笔记文件",
            "优先读摘要、结论、图表标题等高信息密度部分",
            "用 budget_ledger.py tick 记账；逼近 70% 阈值时按降级建议收尾",
        ],
        "gap_entry": "超长输入：{detail}（{location}）——仅处理了部分切片，未覆盖部分列入缺口",
        "uncertainty": "输入超长，仅基于已读取切片成稿，覆盖范围见缺口清单。",
        "status_advice": "partial",
    },
    "format_conflict": {
        "识别特征": "案例要求的交付格式与默认产出形态不一致（如指定 docx/特定模板）",
        "actions": [
            "以案例 output_contract 与 task.md 为准调整交付文件清单",
            "无法生成的格式：交付可编辑源文件（md/文本）并在 result.json 说明",
            "Office 类产物尽量附真实渲染的 PDF/PNG 预览；渲染工具缺失时诚实声明",
        ],
        "gap_entry": "格式冲突：{detail}（{location}）——以替代格式交付，待确认是否可接受",
        "uncertainty": "交付格式与要求存在偏差：{detail}。",
        "status_advice": "partial",
    },
    "citation_unverifiable": {
        "识别特征": "论断/数字/引用在已读材料中找不到出处，或来源无法核验",
        "actions": [
            "该论断标注“未核验”并移入 uncertainty，不得作为既定事实写入正文",
            "引用条目保留可得的全部线索（作者/题名/年份），标注“未核验”",
            "严禁编造 DOI、页码或文献条目",
        ],
        "gap_entry": "引用未核验：{detail}（{location}）",
        "uncertainty": "以下论断/引用未核验：{detail}。",
        "status_advice": "partial",
    },
    "budget_exhausted": {
        "识别特征": "budget_ledger.py 报告 warn/critical，或预算已耗尽",
        "actions": [
            "立即执行 degradation_advice：停止扩写，补全合同字段",
            "已完成部分照常交付；未完成部分以占位 + 缺口清单呈现",
            "checkpoint.py save 保存快照后，contract_probe.py --validate 复核再交付",
        ],
        "gap_entry": "预算耗尽：{detail}（{location}）——该部分未完成",
        "uncertainty": "预算耗尽，部分内容未完成，边界见缺口清单。",
        "status_advice": "partial",
    },
}

DEFAULT_RULE = {
    "识别特征": "未知异常类型",
    "actions": [
        "保守默认：把异常事实如实写入 uncertainty，标注待确认",
        "在受影响章节写入占位：" + PLACEHOLDER % "出现异常（{type}）：{detail}，请确认处理方式",
        "把异常写入缺口清单，继续完成其余不受影响的部分",
        "不静默失败，不编造完成状态",
    ],
    "gap_entry": "未分类异常（{type}）：{detail}（{location}）——待确认",
    "uncertainty": "发生未分类异常（{type}）：{detail}。",
    "status_advice": "partial",
}


def eprint(msg):
    sys.stderr.write(msg + "\n")


def render(template, exc):
    return template.format(
        type=exc.get("type", "unknown"),
        detail=str(exc.get("detail", "")).strip() or "（未提供细节）",
        location=str(exc.get("location", "")).strip() or "位置未标注",
    )


def handle(exc):
    etype = exc.get("type")
    rule = RULES.get(etype, DEFAULT_RULE)
    known = etype in RULES
    actions = [render(a, exc) for a in rule["actions"]]
    return {
        "input": exc,
        "known_type": known,
        "disposition": "playbook_rule" if known else "conservative_default",
        "actions": actions,
        "gap_entry": render(rule["gap_entry"], exc),
        "result_json_update": {
            "append_uncertainty": render(rule["uncertainty"], exc),
            "append_gaps": render(rule["gap_entry"], exc),
            "status_advice": rule["status_advice"],
        },
    }


def main():
    ap = argparse.ArgumentParser(
        description="异常分类处置：读异常描述 JSON，输出处置动作 JSON。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="退出码：0 成功（未知类型给保守默认）；1 输入或环境错误。")
    ap.add_argument("--input", required=True, help="异常描述 JSON 文件（对象或对象数组）")
    ap.add_argument("--out", default=None, help="处置动作输出路径（默认打印到 stdout）")
    args = ap.parse_args()

    try:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        eprint("错误：文件不存在：%s" % args.input)
        sys.exit(1)
    except (json.JSONDecodeError, OSError) as exc:
        eprint("错误：无法读取/解析 %s：%s" % (args.input, exc))
        sys.exit(1)

    if isinstance(data, dict):
        items = [data]
    elif isinstance(data, list) and all(isinstance(x, dict) for x in data):
        items = data
    else:
        eprint("错误：输入必须是 JSON 对象或对象数组。")
        sys.exit(1)
    if not items:
        eprint("错误：输入为空，没有需要处置的异常。")
        sys.exit(1)

    report = {
        "exceptions_total": len(items),
        "known": sum(1 for x in items if x.get("type") in RULES),
        "results": [handle(x) for x in items],
    }
    report["unknown"] = report["exceptions_total"] - report["known"]

    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as exc:
            eprint("错误：无法写入 %s：%s" % (args.out, exc))
            sys.exit(1)
        print("处置动作已写出：%s（异常 %d 个：已知 %d / 未知 %d）" % (
            args.out, report["exceptions_total"], report["known"], report["unknown"]))
    else:
        sys.stdout.write(text)
    sys.exit(0)


if __name__ == "__main__":
    main()
