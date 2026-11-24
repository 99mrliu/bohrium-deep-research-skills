#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_probe.py — 合同探测器：启动保底落盘 + 交付前合同符合性校验。

两种模式（二选一，默认探测模式）：

1) 探测模式（默认）：读取 case.json，提取 case_id、output_contract 字段清单与
   写作要求摘要；立即在输出目录写出一份"保底" result.json（status=partial，
   全部 output_contract 字段以诚实空值/占位填充，case_id 原样保留）以及
   plan.json（要素清单 + 交付文件计划 + 预算分配建议）。

2) 校验模式（--validate）：对已有 result.json 做合同符合性检查：
   - case_id 与 case.json 精确一致；
   - output_contract 全部字段都在（不硬编码字段名，运行时读取）；
   - status 枚举合法（success/partial/unable_to_determine/refused）；
   - status=partial 时必须有非空 reason 与缺口说明。
   不合法时逐条列出问题并以退出码 1 退出；合法退出码 0。

退出码：0 成功；1 合同校验不通过；2 输入/环境错误（文件缺失、JSON 损坏等）。

确定性：除 --now 显式传入的时间外不读取任何环境状态；多次运行（相同参数）
产出字节一致。
"""
import argparse
import json
import sys
import os

VALID_STATUS = ("success", "partial", "unable_to_determine", "refused")

# 已知语义字段的诚实占位；未知字段统一用 null 并在 uncertainty 中声明。
KNOWN_PLACEHOLDERS = {
    "status": "partial",
    "sources": [],
    "deliverables": [],
    "uncertainty": [],
    "change_record": [],
    "gaps": [],
    "summary": "",
    "reason": "",
}

BUDGET_ADVICE = {
    "read_materials": {"requests_pct": 20, "seconds_pct": 25,
                       "note": "读取 case.json/task.md 与全部材料文件，建立材料清单"},
    "drafting": {"requests_pct": 45, "seconds_pct": 40,
                 "note": "按要素清单逐章成稿，每完成一节就地更新 result.json"},
    "review": {"requests_pct": 20, "seconds_pct": 20,
               "note": "对照 output_contract 与四态标注回检，修补缺口"},
    "reserve": {"requests_pct": 15, "seconds_pct": 15,
                "note": "保底余量：异常处置、最终校验与交付"},
}


def eprint(msg):
    sys.stderr.write(msg + "\n")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        eprint("错误：文件不存在：%s" % path)
        sys.exit(2)
    except json.JSONDecodeError as exc:
        eprint("错误：JSON 解析失败 %s：%s" % (path, exc))
        sys.exit(2)
    except OSError as exc:
        eprint("错误：无法读取 %s：%s" % (path, exc))
        sys.exit(2)


def write_json(path, obj):
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
    except OSError as exc:
        eprint("错误：无法写入 %s：%s" % (path, exc))
        sys.exit(2)


def extract_contract_fields(case):
    """从 case.json 提取 output_contract 字段名清单（运行时读取，绝不硬编码）。

    支持 dict（键为字段名）或 list（元素为字段名字符串）两种形态。
    """
    contract = case.get("output_contract")
    if contract is None:
        return None
    if isinstance(contract, dict):
        return sorted(contract.keys())
    if isinstance(contract, list):
        fields = [x for x in contract if isinstance(x, str)]
        return sorted(fields) if fields else None
    return None


def extract_requirements_summary(case):
    """提取写作要求摘要：优先 requirements/writing_requirements 字段，
    否则列出 case.json 顶层键作为线索。"""
    for key in ("writing_requirements", "requirements", "task_requirements"):
        val = case.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, list) and val:
            return "；".join(str(x) for x in val)
    keys = sorted(k for k in case.keys() if k != "output_contract")
    return "（case.json 未含显式写作要求字段；顶层键：%s；详见 /input/task.md）" % "、".join(keys)


def default_elements(case):
    """七要素清单：以案例给定为准，否则用默认七要素。"""
    for key in ("elements", "required_elements", "sections"):
        val = case.get(key)
        if isinstance(val, list) and val and all(isinstance(x, str) for x in val):
            return list(val)
    return ["立项依据", "科学问题", "研究目标", "研究内容",
            "技术路线", "创新点", "研究基础与可行性"]


def build_fallback_result(case_id, fields):
    """构造保底 result.json：全部合同字段以诚实空值/占位填充。"""
    result = {}
    unknown_fields = []
    for name in fields:
        if name in KNOWN_PLACEHOLDERS:
            value = KNOWN_PLACEHOLDERS[name]
            # 列表/字符串占位要做拷贝，避免共享引用
            result[name] = list(value) if isinstance(value, list) else value
        else:
            result[name] = None
            unknown_fields.append(name)
    # 保证关键语义字段存在并诚实
    result["case_id"] = case_id
    result["status"] = "partial"
    result["reason"] = "初始化保底：材料尚未读取，先落合法 result.json，随后就地迭代改进。"
    uncertainty = result.get("uncertainty")
    if isinstance(uncertainty, list):
        uncertainty.append("本结果为初始化保底版本，全部实质内容待补充。")
        for f in unknown_fields:
            uncertainty.append("合同字段 %s 语义未知，以 null 占位，待按案例 output_contract 说明补全。" % f)
        result["uncertainty"] = uncertainty
    return result


def cmd_probe(args):
    case = load_json(args.case)
    case_id = case.get("case_id")
    if not isinstance(case_id, str) or not case_id:
        eprint("错误：case.json 缺少字符串字段 case_id。")
        sys.exit(2)
    fields = extract_contract_fields(case)
    if not fields:
        eprint("错误：case.json 未提供可用的 output_contract（应为 dict 或字符串 list）。")
        sys.exit(2)

    out_dir = args.output_dir
    result = build_fallback_result(case_id, fields)
    result["started_at"] = args.now
    write_json(os.path.join(out_dir, "result.json"), result)

    plan = {
        "case_id": case_id,
        "contract_fields": fields,
        "requirements_summary": extract_requirements_summary(case),
        "elements": default_elements(case),
        "deliverable_plan": [
            {"path": "result.json", "role": "合同结果文件（先落 partial，就地迭代）"},
            {"path": "proposal_draft.md", "role": "申请书章节稿（按要素清单逐节成稿）"},
            {"path": "element_mapping.md", "role": "要素对照说明（章节稿↔七要素/案例要求）"},
            {"path": "sources.md", "role": "来源台账（每条论断/数字/引用的出处与四态标注）"},
        ],
        "budget_allocation_advice": BUDGET_ADVICE,
        "discipline": "材料清单一出来 60 秒内先落本保底 result.json；此后每次改进就地更新并 checkpoint。",
    }
    write_json(os.path.join(out_dir, "plan.json"), plan)

    print("case_id: %s" % case_id)
    print("output_contract 字段（%d 个）: %s" % (len(fields), "、".join(fields)))
    print("写作要求摘要: %s" % plan["requirements_summary"])
    print("已写出保底 result.json（status=partial）: %s" % os.path.join(out_dir, "result.json"))
    print("已写出 plan.json: %s" % os.path.join(out_dir, "plan.json"))
    sys.exit(0)


def cmd_validate(args):
    case = load_json(args.case)
    case_id = case.get("case_id")
    if not isinstance(case_id, str) or not case_id:
        eprint("错误：case.json 缺少字符串字段 case_id。")
        sys.exit(2)
    fields = extract_contract_fields(case)
    if not fields:
        eprint("错误：case.json 未提供可用的 output_contract。")
        sys.exit(2)
    result = load_json(args.result)

    problems = []

    # 1. case_id 精确一致
    rid = result.get("case_id")
    if rid != case_id:
        problems.append("case_id 不一致：result.json=%r，case.json=%r（要求精确一致）" % (rid, case_id))

    # 2. 全部合同字段在场
    for name in fields:
        if name not in result:
            problems.append("缺失合同字段：%s" % name)

    # 3. status 枚举合法
    status = result.get("status")
    if status not in VALID_STATUS:
        problems.append("status 非法：%r（合法枚举：%s）" % (status, "/".join(VALID_STATUS)))

    # 4. partial 必须有 reason 与缺口说明
    if status == "partial":
        reason = result.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            problems.append("status=partial 但 reason 缺失或为空（必须说明为何未完成）")
        gap_ok = False
        unc = result.get("uncertainty")
        if isinstance(unc, list) and any(isinstance(x, str) and x.strip() for x in unc):
            gap_ok = True
        gaps = result.get("gaps")
        if isinstance(gaps, list) and any(isinstance(x, str) and x.strip() for x in gaps):
            gap_ok = True
        if not gap_ok:
            problems.append("status=partial 但无缺口说明（uncertainty 或 gaps 至少其一为非空字符串列表）")

    # 5. sources 若存在须为列表
    if "sources" in result and not isinstance(result["sources"], list):
        problems.append("sources 应为列表，实际类型：%s" % type(result["sources"]).__name__)

    if problems:
        print("合同校验未通过（%d 项问题）：" % len(problems))
        for i, p in enumerate(problems, 1):
            print("  %d. %s" % (i, p))
        sys.exit(1)
    print("合同校验通过：case_id 一致；%d 个合同字段齐全；status=%s 合法。" % (len(fields), status))
    sys.exit(0)


def main():
    ap = argparse.ArgumentParser(
        description="合同探测器：默认写出保底 result.json 与 plan.json；--validate 校验已有 result.json。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="退出码：0 成功/校验通过；1 校验不通过；2 输入或环境错误。")
    ap.add_argument("--case", default="/input/case.json",
                    help="case.json 路径（默认 /input/case.json）")
    ap.add_argument("--output-dir", default="/app/output",
                    help="输出目录（默认 /app/output）")
    ap.add_argument("--now", default="1970-01-01T00:00:00Z",
                    help="写入 started_at 的时间戳（ISO8601）；为保证确定性，默认固定值，"
                         "真实运行时应由调用方传入当前时间")
    ap.add_argument("--validate", action="store_true",
                    help="校验模式：检查已有 result.json 是否符合合同")
    ap.add_argument("--result", default=None,
                    help="校验模式下的 result.json 路径（默认 <output-dir>/result.json）")
    args = ap.parse_args()
    if args.validate:
        if args.result is None:
            args.result = os.path.join(args.output_dir, "result.json")
        cmd_validate(args)
    else:
        cmd_probe(args)


if __name__ == "__main__":
    main()
