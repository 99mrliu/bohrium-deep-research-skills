#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cost_model.py — 从 case.json 的资源/价格/预约契约字段和/或材料文本中解析成本模型。

输出 cost_model.json：每个量带显式单位声明。
单位一致性规则（详见 references/unit-rules.md）：
  - 契约单位 == 声明单位：直接采用；
  - 契约单位 != 声明单位，但契约自带 unit_conversions 白名单给出换算关系：换算并记录
    conversions_applied（绝不静默换算）；
  - 契约单位 != 声明单位，且换算关系缺失：拒绝（exit 2），写出拒绝 JSON 并播种
    uncertainty。
任何输入不得 traceback 崩溃；金额/时间用 Decimal 语义，输出保留两位小数。

退出码：0 = ok/partial 已落盘；2 = 单位不自洽拒绝；3 = 数值非法（如预算为负）；
1 = 内部错误（仍会尽量落盘错误 JSON）。
"""

import argparse
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

SCHEMA_VERSION = "cost-model/1.0"

# 成本模型字段 -> 声明单位（本技能的单位口径）
DECLARED_UNITS = {
    "machine_rate": "CNY/hour",        # 机时费率：元/小时
    "consumable_price": "CNY/portion",  # 耗材单价：元/份
    "sample_prep_time": "hour/sample",  # 单样品制备时间：小时/样品
    "daily_machine_hours": "hour/day",  # 每日可用机时（预约窗口）：小时/天
    "budget": "CNY",                    # 总预算：元
    "deadline": "working_day",          # 截止：工作日
    "typical_run_hours": "hour",        # 单 run 机时口径声明：小时
}

REQUIRED_FIELDS = ["machine_rate", "consumable_price", "daily_machine_hours",
                   "budget", "deadline"]

CENT = Decimal("0.01")


def D(x):
    """安全转 Decimal；失败返回 None。"""
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return None


def q2(d):
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def fmt(d):
    """Decimal -> 紧凑字符串（不带尾零），供算术痕迹使用。"""
    return format(d.normalize(), "f")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except Exception as e:  # noqa: BLE001 —— 任何读取失败都不许崩溃
        return None, "无法读取 JSON 文件 %s: %s" % (path, e)


# ---------------------------------------------------------------------------
# 材料文本解析（兜底）：只识别显式带声明单位的写法，绝不猜测。
# ---------------------------------------------------------------------------
TEXT_PATTERNS = [
    # (字段, 正则, 文本中出现的单位 -> 声明单位)
    ("machine_rate", re.compile(r"机时[^0-9]{0,12}(\d+(?:\.\d+)?)\s*元\s*/\s*(小时|h)\b"), None),
    ("machine_rate", re.compile(r"(\d+(?:\.\d+)?)\s*元\s*/\s*(小时|h)\b[^。]{0,10}机时"), None),
    ("consumable_price", re.compile(r"耗材[^0-9]{0,12}(\d+(?:\.\d+)?)\s*元\s*/\s*份"), None),
    ("consumable_price", re.compile(r"(\d+(?:\.\d+)?)\s*元\s*/\s*份"), None),
    ("daily_machine_hours", re.compile(r"每日[^0-9]{0,12}(\d+(?:\.\d+)?)\s*(小时|h)\b"), None),
    ("sample_prep_time", re.compile(r"(?:单样品|每个样品|样品制备)[^0-9]{0,12}(\d+(?:\.\d+)?)\s*(小时|h)\b"), None),
    ("budget", re.compile(r"(?:总)?预算[^0-9]{0,12}(\d+(?:\.\d+)?)\s*元"), None),
    ("deadline", re.compile(r"(\d+)\s*个工作日"), None),
]

# 文本单位别名 -> 声明单位（仅限与声明单位同义的写法，不含跨尺度换算）
TEXT_UNIT_ALIAS = {"小时": "hour", "h": "hour", "元": "CNY", "份": "portion",
                   "工作日": "working_day", "天": "day"}


def parse_materials_text(materials_dir, fields, uncertainty):
    """从材料文本兜底补齐缺失字段。只接受与声明单位同义的单位写法。"""
    p = Path(materials_dir)
    if not p.is_dir():
        uncertainty.append("材料目录不存在或不可读：%s；文本兜底解析跳过。" % materials_dir)
        return
    for fpath in sorted(p.rglob("*")):
        if not fpath.is_file():
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            uncertainty.append("材料文件读取失败 %s: %s" % (fpath, e))
            continue
        for field, pat, _ in TEXT_PATTERNS:
            if field in fields:
                continue
            m = pat.search(text)
            if not m:
                continue
            value = D(m.group(1))
            if value is None:
                continue
            fields[field] = {
                "value": fmt(value),
                "unit": DECLARED_UNITS[field],
                "source": "materials:%s" % fpath.name,
            }


# ---------------------------------------------------------------------------
# 契约字段解析 + 单位一致性检查
# ---------------------------------------------------------------------------
def resolve_field(name, entry, contract_conversions, conversions_applied, source):
    """
    返回 (status, value_Decimal_or_None, message)
    status ∈ {"ok", "converted", "reject", "missing", "invalid"}
    """
    declared = DECLARED_UNITS[name]
    if entry is None:
        return ("missing", None, "契约未提供字段 %s" % name)
    if isinstance(entry, dict):
        raw_value = entry.get("value")
        unit = entry.get("unit")
    else:
        raw_value, unit = entry, None
    value = D(raw_value)
    if value is None:
        return ("invalid", None, "字段 %s 的数值无法解析：%r" % (name, raw_value))
    if unit is None:
        # 单位缺失：按声明单位处理，但必须显式记录（非静默）
        conversions_applied.append({
            "field": name,
            "note": "契约未显式给出单位，按声明单位 %s 处理（已记录假设，未做任何换算）" % declared,
            "source": source,
        })
        return ("ok", value, None)
    if unit == declared:
        return ("ok", value, None)
    # 单位不一致：查契约自带换算白名单
    conv = contract_conversions.get(unit)
    if isinstance(conv, dict) and conv.get("to") == declared and D(conv.get("divide_by")) not in (None, Decimal("0")):
        factor = D(conv["divide_by"])
        converted = value / factor
        conversions_applied.append({
            "field": name,
            "note": "单位 %s 经契约白名单换算为 %s：%s %s / %s = %s %s"
                    % (unit, declared, fmt(value), unit, fmt(factor), fmt(converted), declared),
            "source": source,
        })
        return ("converted", converted, None)
    return ("reject", None,
            "字段 %s 使用单位 %r，与声明单位 %r 不一致，且契约未提供 unit_conversions "
            "换算关系；按单位规则拒绝，绝不静默换算" % (name, unit, declared))


def main():
    ap = argparse.ArgumentParser(description="解析资源/价格/预约契约为 cost_model.json")
    ap.add_argument("--case", help="case.json 路径（用于读取材料路径）")
    ap.add_argument("--contract", help="资源预约契约 JSON 路径（缺省时从 case.json 推断）")
    ap.add_argument("--materials", help="材料目录（文本兜底解析；缺省时从 case.json 推断）")
    ap.add_argument("--out", required=True, help="输出 cost_model.json 路径")
    args = ap.parse_args()

    out_path = Path(args.out)
    uncertainty = []
    conversions_applied = []
    fields = {}
    case_data = None

    def emit(payload, code):
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"status": "error", "error": "无法写输出: %s" % e},
                             ensure_ascii=False))
        return code

    try:
        if args.case:
            case_data, err = load_json(args.case)
            if err:
                uncertainty.append(err)

        materials_info = (case_data or {}).get("materials", {}) if isinstance(case_data, dict) else {}
        contract_path = args.contract or materials_info.get("resource_contract")
        materials_dir = args.materials
        if not materials_dir:
            notice = materials_info.get("lab_notice")
            if notice:
                materials_dir = str(Path(notice).parent)

        if not contract_path:
            uncertainty.append("未找到资源契约路径（--contract 与 case.json.materials.resource_contract 均缺失）。")
        else:
            contract, err = load_json(contract_path)
            if err:
                uncertainty.append(err)
                contract = None
            if isinstance(contract, dict):
                contract_conversions = contract.get("unit_conversions") or {}
                if not isinstance(contract_conversions, dict):
                    contract_conversions = {}
                    uncertainty.append("契约 unit_conversions 不是对象，已忽略。")
                src = "contract:%s" % Path(contract_path).name
                for name in DECLARED_UNITS:
                    status, value, msg = resolve_field(
                        name, contract.get(name), contract_conversions,
                        conversions_applied, src)
                    if status == "reject":
                        payload = {
                            "schema_version": SCHEMA_VERSION,
                            "status": "refused",
                            "reason": msg,
                            "declared_units": DECLARED_UNITS,
                            "uncertainty": uncertainty + [
                                "成本模型未建立：单位不自洽。下游 plan_costing/pareto 不应运行，"
                                "result.json 的 status 应为 refused 或 partial，并把本拒绝原因写入 uncertainty。"
                            ],
                        }
                        return emit(payload, 2)
                    if status in ("ok", "converted"):
                        fields[name] = {"value": fmt(value), "unit": DECLARED_UNITS[name],
                                        "source": src}
                    elif status == "invalid":
                        uncertainty.append(msg)
            else:
                uncertainty.append("契约文件不是 JSON 对象，已跳过：%s" % contract_path)

        # 文本兜底补齐缺失字段
        if materials_dir:
            parse_materials_text(materials_dir, fields, uncertainty)
        else:
            missing = [f for f in REQUIRED_FIELDS if f not in fields]
            if missing:
                uncertainty.append("无材料目录可供文本兜底；仍缺字段：%s" % ", ".join(missing))

        # 数值合法性检查（预算为负等）
        for name, entry in list(fields.items()):
            v = D(entry["value"])
            if v is None:
                uncertainty.append("字段 %s 数值非法：%r" % (name, entry["value"]))
                del fields[name]
                continue
            if name in ("budget", "machine_rate", "consumable_price") and v < 0:
                payload = {
                    "schema_version": SCHEMA_VERSION,
                    "status": "refused",
                    "reason": "字段 %s 为负数（%s %s），契约数值非法，拒绝建模。" % (name, fmt(v), entry["unit"]),
                    "declared_units": DECLARED_UNITS,
                    "fields": fields,
                    "conversions_applied": conversions_applied,
                    "uncertainty": uncertainty,
                }
                return emit(payload, 3)
            if name in ("daily_machine_hours", "deadline") and v <= 0:
                payload = {
                    "schema_version": SCHEMA_VERSION,
                    "status": "refused",
                    "reason": "字段 %s 必须为正数，实际为 %s %s，拒绝建模。" % (name, fmt(v), entry["unit"]),
                    "declared_units": DECLARED_UNITS,
                    "fields": fields,
                    "conversions_applied": conversions_applied,
                    "uncertainty": uncertainty,
                }
                return emit(payload, 3)

        missing_required = [f for f in REQUIRED_FIELDS if f not in fields]
        status = "ok" if not missing_required else "partial"
        if missing_required:
            uncertainty.append("必需字段缺失：%s；成本模型为 partial，下游核算需在 result.json 中如实声明。"
                               % ", ".join(missing_required))

        payload = {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "declared_units": DECLARED_UNITS,
            "fields": fields,
            "conversions_applied": conversions_applied,
            "uncertainty": uncertainty,
        }
        return emit(payload, 0)
    except Exception as e:  # noqa: BLE001 —— 任何输入不得 traceback
        payload = {
            "schema_version": SCHEMA_VERSION,
            "status": "error",
            "error": "内部错误：%s: %s" % (type(e).__name__, e),
            "uncertainty": uncertainty,
        }
        return emit(payload, 1)


if __name__ == "__main__":
    sys.exit(main())
