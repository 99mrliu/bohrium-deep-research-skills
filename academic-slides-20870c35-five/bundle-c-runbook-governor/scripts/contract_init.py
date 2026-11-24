#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_init.py —— Phase 0：防御性契约接管（仅 Python3 标准库，无网络依赖）。

这是 deck-runbook-governor 的治理起点：在任何模型判断之前，先把"这个案例到底
要求交付什么"钉死成确定性文件。读取 case.json，在 --out 目录产出：

  contract.json       规范化契约：case_id、output_contract 点路径展开清单
                      （保留每字段原始声明文本）、slide-workorder 字段抽取
                      （audience / duration_min / slide_count / mode /
                      template / starting_deck / export_formats）、
                      材料清单（逐个 SHA-256 + 字节数）、必交产物字段识别
  result.json         交付骨架：真实 case_id、全部契约顶层字段以 "PENDING"
                      占位、status="partial"（诚实占位）、sources/uncertainty/
                      limitations/change_log 初始化
  budget_ledger.json  64 请求 / 900 秒在五个模型消费阶段上的配额 + 每阶段
                      机动 reserve，usage 空表待 agent 逐阶段回填

退出码：
  0  成功
  2  用法 / IO / 契约错误（case.json 缺失、JSON 损坏、顶层非对象、case_id
     或 output_contract 不可用）；此时仍尽力在 --out 写出 status=blocked
     且带 blocked_reason 的 result.json，然后退出 2。

确定性：产物不含随机数与时间戳，同一 case.json 重复运行字节一致。
"""

import argparse
import hashlib
import json
import os
import sys

BUDGET_CAPS = {"model_requests": 64, "wall_seconds": 900,
               "tokens_per_response": 16384}

# 64 = 55 quota + 9 reserve；900 = 810 quota + 90 reserve。逐阶段 reserve
# 只允许在本阶段配额耗尽后向本阶段 reserve 支取，跨阶段挪用见
# references/budget-protocol.md 的降级顺序。
PHASE_QUOTA = [
    {"phase": "p1_source_index", "quota_requests": 12, "reserve_requests": 2,
     "quota_seconds": 180, "reserve_seconds": 20,
     "note": "pdftotext/pdftoppm 索引与主线提取；每页文本先落盘再判断"},
    {"phase": "p2_storyboard", "quota_requests": 8, "reserve_requests": 1,
     "quota_seconds": 110, "reserve_seconds": 10,
     "note": "听众建模 + 页级 storyboard，一次响应成型"},
    {"phase": "p3_deck_build", "quota_requests": 13, "reserve_requests": 2,
     "quota_seconds": 200, "reserve_seconds": 20,
     "note": "模板内建 deck + 讲稿备注；每页保留证据定位"},
    {"phase": "p4_render_qa", "quota_requests": 10, "reserve_requests": 2,
     "quota_seconds": 150, "reserve_seconds": 20,
     "note": "soffice 导出 + PNG 预览 + 至多两轮修复回路"},
    {"phase": "p5_delivery", "quota_requests": 12, "reserve_requests": 2,
     "quota_seconds": 170, "reserve_seconds": 20,
     "note": "回填 result.json + delivery_gate 门控与修复；先存快照再改"},
]

PHASE0_NOTE = ("Phase 0（契约接管）由 contract_init.py 脚本完成，"
               "不消耗模型请求；模型只读本脚本产物，不手写契约字段名。")

# result.json 骨架中的保留键：契约字段与之同名时不设 PENDING 占位（冲突会记入 notes）
RESERVED_KEYS = {"case_id", "status", "blocked_reason", "sources",
                 "uncertainty", "limitations", "change_log"}

# 必交产物字段（D3 的检查对象）：按名字识别，命中即列入 required_artifacts
ARTIFACT_FIELD_NAMES = ("editable_deck", "export_preview", "content_map")

# slide-workorder 抽取：规范键 -> 候选别名（按序取第一个命中）
WORKORDER_KEYS = {
    "audience": ["audience"],
    "duration_min": ["duration_min", "duration"],
    "slide_count": ["slide_count", "num_slides"],
    "mode": ["mode"],
    "template": ["template", "template_path"],
    "starting_deck": ["starting_deck", "starting_deck_path"],
    "export_formats": ["export_formats", "export_format"],
}
WORKORDER_CONTAINERS = ["work_order", "slide_workorder", "workorder"]


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def dump_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def expand_fields(prefix, value, out):
    """把 output_contract 递归展开为点路径；非空 dict 继续下钻，其余一律视为
    叶子并保留原始声明文本。字段类型不明时不猜测、不报错。"""
    if isinstance(value, dict) and value:
        for key, sub in value.items():
            path = "{}.{}".format(prefix, key) if prefix else str(key)
            expand_fields(path, sub, out)
    else:
        out.append({"path": prefix,
                    "declaration": json.dumps(value, ensure_ascii=False)})


def extract_workorder(case):
    """从 case.json 抽取 slide-workorder 字段。依次检查 work_order /
    slide_workorder / workorder 容器，最后回退到 case 顶层；缺失记 null
    并列入 missing，绝不虚构默认值。"""
    containers = [case.get(name) for name in WORKORDER_CONTAINERS]
    containers = [c for c in containers if isinstance(c, dict)]
    containers.append(case)
    found, missing = {}, []
    for canon, aliases in WORKORDER_KEYS.items():
        value = None
        hit = False
        for container in containers:
            for alias in aliases:
                if alias in container and container[alias] is not None:
                    value = container[alias]
                    hit = True
                    break
            if hit:
                break
        found[canon] = value
        if not hit:
            missing.append(canon)
    return found, missing


def base_result(case_id, status):
    return {"case_id": case_id, "status": status, "sources": [],
            "uncertainty": [], "limitations": [], "change_log": []}


def write_blocked(out_dir, case_id, reason):
    """case.json 不可用时的兜底交付：诚实 blocked，而不是无声崩溃。"""
    try:
        os.makedirs(out_dir, exist_ok=True)
        result = base_result(case_id, "blocked")
        result["blocked_reason"] = reason
        result["uncertainty"] = ["契约接管失败：{}".format(reason)]
        result["limitations"] = ["case.json 不可用，六个阶段均未执行；"
                                 "修复输入后重跑 contract_init.py"]
        path = os.path.join(out_dir, "result.json")
        dump_json(path, result)
        print("[contract_init] BLOCKED: {}".format(reason))
        print("[contract_init] 已写出 blocked 骨架：{}".format(path))
    except OSError as exc:
        print("[contract_init] FATAL: 连 blocked result.json 都无法写出：{}".format(exc),
              file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Phase 0：从 case.json 生成 contract.json / result.json 骨架 / budget_ledger.json")
    parser.add_argument("--case", default="/input/case.json", help="case.json 路径")
    parser.add_argument("--out", default="/app/output", help="产物输出目录")
    parser.add_argument("--materials-dir", default=None,
                        help="材料目录（默认取 case.json 所在目录，递归计算 SHA-256）")
    args = parser.parse_args(argv)

    # ---- 防御式读取：每一步失败都给出可读原因，绝不猜测 ----
    if not os.path.isfile(args.case):
        write_blocked(args.out, None, "case.json 不存在：{}".format(args.case))
        return 2
    try:
        with open(args.case, "r", encoding="utf-8") as fh:
            case = json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        write_blocked(args.out, None, "case.json 读取或解析失败：{}".format(exc))
        return 2
    if not isinstance(case, dict):
        write_blocked(args.out, None, "case.json 顶层必须是 JSON 对象")
        return 2
    case_id = case.get("case_id")
    if not isinstance(case_id, str) or not case_id.strip():
        write_blocked(args.out, None,
                      "case.json 缺少有效的 case_id 字符串（实际为 {!r}）".format(case_id))
        return 2
    contract = case.get("output_contract")
    if not isinstance(contract, dict) or not contract:
        write_blocked(args.out, case_id,
                      "case.json 缺少有效的 output_contract 非空对象（实际为 {}）".format(
                          type(contract).__name__))
        return 2

    # ---- 契约展开（点路径 + 原始声明）----
    fields = []
    for key, value in contract.items():
        expand_fields(str(key), value, fields)
    top_fields = [str(k) for k in contract.keys()]
    collisions = [k for k in top_fields if k in RESERVED_KEYS]
    required_artifacts = [k for k in top_fields if k in ARTIFACT_FIELD_NAMES]

    # ---- work-order 抽取 ----
    workorder, wo_missing = extract_workorder(case)

    # ---- 材料清单与 SHA-256 ----
    materials_dir = args.materials_dir or os.path.dirname(os.path.abspath(args.case))
    materials, materials_note = [], None
    if os.path.isdir(materials_dir):
        for root, _dirs, files in os.walk(materials_dir):
            for name in sorted(files):
                full = os.path.join(root, name)
                if os.path.isfile(full):
                    materials.append({
                        "path": os.path.relpath(full, materials_dir),
                        "sha256": sha256_of(full),
                        "bytes": os.path.getsize(full),
                    })
        materials.sort(key=lambda m: m["path"])
    else:
        materials_note = "材料目录不存在：{}（materials 置空）".format(materials_dir)

    os.makedirs(args.out, exist_ok=True)

    # ---- (a) contract.json ----
    notes = [
        "fields[].path 为 output_contract 的点路径展开；declaration 为原始声明文本",
        "required_artifacts 按字段名识别（{}），是 delivery_gate D3 的检查对象".format(
            "/".join(ARTIFACT_FIELD_NAMES)),
        "work_order 缺失字段为 null 并列入 work_order_missing，禁止虚构默认值",
        "本文件不含随机数与时间戳，重复运行字节一致",
    ]
    if collisions:
        notes.append("以下契约字段名与保留键冲突，骨架中未设 PENDING 占位："
                     + ", ".join(collisions))
    if materials_note:
        notes.append(materials_note)
    contract_doc = {
        "case_id": case_id,
        "generated_by": "contract_init.py (deck-runbook-governor)",
        "output_contract": {"top_level_fields": top_fields, "fields": fields},
        "work_order": workorder,
        "work_order_missing": wo_missing,
        "required_artifacts": required_artifacts,
        "materials_dir": os.path.abspath(materials_dir),
        "materials": materials,
        "reserved_key_collisions": collisions,
        "notes": notes,
    }
    contract_path = os.path.join(args.out, "contract.json")
    dump_json(contract_path, contract_doc)

    # ---- (b) result.json 骨架（诚实 partial，全字段 PENDING 占位）----
    result = base_result(case_id, "partial")
    for key in top_fields:
        if key not in RESERVED_KEYS:
            result[key] = "PENDING"
    result["uncertainty"] = ["初始化占位：尚未执行材料索引与 deck 构建"]
    result["limitations"] = ["初始化占位：全部契约字段待各阶段回填"]
    result_path = os.path.join(args.out, "result.json")
    dump_json(result_path, result)

    # ---- (c) budget_ledger.json ----
    tq = sum(p["quota_requests"] for p in PHASE_QUOTA)
    tr = sum(p["reserve_requests"] for p in PHASE_QUOTA)
    sq = sum(p["quota_seconds"] for p in PHASE_QUOTA)
    sr = sum(p["reserve_seconds"] for p in PHASE_QUOTA)
    ledger = {
        "budget_caps": BUDGET_CAPS,
        "phase0_note": PHASE0_NOTE,
        "phase_quota": PHASE_QUOTA,
        "totals": {"quota_requests": tq, "reserve_requests": tr,
                   "requests": tq + tr,
                   "quota_seconds": sq, "reserve_seconds": sr,
                   "seconds": sq + sr},
        "usage": [],
        "usage_format": {"phase": "阶段名（p1..p5）",
                         "requests": "本阶段累计消耗请求数",
                         "seconds": "本阶段累计消耗秒数",
                         "note": "可选备注（如降级决定）"},
        "note": "每阶段结束向 usage 追加一条；配额将尽时按 references/budget-protocol.md 降级，"
                "最终以诚实 partial 兜底",
    }
    ledger_path = os.path.join(args.out, "budget_ledger.json")
    dump_json(ledger_path, ledger)

    print("[contract_init] OK case_id={}".format(case_id))
    print("[contract_init] 契约顶层字段 {} 个，展开点路径 {} 条：{}".format(
        len(top_fields), len(fields), ", ".join(top_fields)))
    print("[contract_init] 必交产物字段：{}".format(
        ", ".join(required_artifacts) if required_artifacts else "（未识别到，D3 将无对象）"))
    print("[contract_init] work_order 抽取 {} 项，缺失 {} 项：{}".format(
        len(WORKORDER_KEYS) - len(wo_missing), len(wo_missing),
        ", ".join(wo_missing) if wo_missing else "无"))
    print("[contract_init] 材料 {} 个（{}）".format(len(materials), materials_dir))
    print("[contract_init] 预算台账：{} 请求 / {} 秒（quota {}+{} reserve）".format(
        tq + tr, sq + sr, tq, tr))
    if collisions:
        print("[contract_init] WARNING 保留键冲突：{}".format(", ".join(collisions)))
    print("[contract_init] 写出：{} / {} / {}".format(contract_path, result_path, ledger_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
