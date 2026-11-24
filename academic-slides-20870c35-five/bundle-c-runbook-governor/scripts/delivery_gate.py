#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""delivery_gate.py —— Phase 5：交付总门 D1-D6（仅 Python3 标准库）。

对 --out/result.json 做机械可判定的交付核验，违例逐项打印 "D#: 细节"：

  D1  case_id 与 case.json 完全一致
  D2  output_contract 全部顶层字段在 result.json 中存在且非 "PENDING" 占位；
      空值（空串/空数组/空对象/null）仅在 status=partial 时允许，且
      limitations 中必须存在提及该字段名的条目逐项声明原因；
      completed 下空字段直接判负（status=blocked 时 D2/D3 豁免）
  D3  必交产物真实落盘：必交产物字段清单取自 contract.json 的
      required_artifacts（contract_init 按 editable_deck / export_preview /
      content_map 名字识别；contract.json 缺失时回退到对 case.json 的同一
      名字启发式）。从 result.json 对应字段解析相对路径（字符串 / 字符串
      数组 / {"path": ...} / {"paths": [...]}），每个文件必须存在于 --out
      之内且字节数 > 0；绝对路径与越界路径判负
  D4  诚实一致性：completed ⇒ 必交产物字段值非空且 sources 非空；
      partial ⇒ limitations 非空；blocked ⇒ blocked_reason 非空
  D5  status 取值属于受控词表 {completed, partial, blocked}
  D6  change_log 为数组，每条恰为含 file / what / why / rollback 四个
      非空字符串键的对象

退出码：
  0  全部通过，打印 GATE: PASS
  1  存在门控违例，逐项打印 D 编号 + 细节
  2  用法 / IO / 模式错误（case.json 或 result.json 缺失、损坏、结构不可用）
"""

import argparse
import json
import os
import sys

VALID_STATUS = ("completed", "partial", "blocked")
ARTIFACT_FIELD_NAMES = ("editable_deck", "export_preview", "content_map")
CHANGE_LOG_KEYS = ("file", "what", "why", "rollback")
PENDING = "PENDING"


def is_empty(value):
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def load_json(path, label):
    """返回 (obj, error)；error 非 None 即用法/IO 错误（exit 2）。"""
    if not os.path.isfile(path):
        return None, "{} 不存在：{}".format(label, path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh), None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, "{} 读取或解析失败：{}".format(label, exc)


def resolve_paths(value):
    """把契约字段值解析为相对路径列表；无法解析返回 None（区别于空列表）。"""
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str) and v.strip()]
    if isinstance(value, dict):
        if isinstance(value.get("path"), str) and value["path"].strip():
            return [value["path"]]
        if isinstance(value.get("paths"), list):
            return [p for p in value["paths"] if isinstance(p, str) and p.strip()]
        return None
    return None


def check_artifact_file(out_dir, field, rel):
    """返回 None（通过）或违例细节字符串。"""
    if os.path.isabs(rel):
        return "字段 {} 的路径不允许为绝对路径：{}".format(field, rel)
    full = os.path.realpath(os.path.join(out_dir, rel))
    out_real = os.path.realpath(out_dir)
    if full != out_real and not full.startswith(out_real + os.sep):
        return "字段 {} 的路径越出输出目录：{}".format(field, rel)
    if not os.path.isfile(full):
        return "字段 {} 指向的产物文件不存在：{}".format(field, rel)
    if os.path.getsize(full) == 0:
        return "字段 {} 指向的产物文件为空（0 字节）：{}".format(field, rel)
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description="交付总门 D1-D6：result.json 机械核验")
    parser.add_argument("--case", default="/input/case.json", help="case.json 路径")
    parser.add_argument("--out", default="/app/output", help="result.json 所在目录")
    parser.add_argument("--contract", default=None,
                        help="contract.json 路径（默认 <out>/contract.json，缺失时回退启发式）")
    args = parser.parse_args(argv)

    case, err = load_json(args.case, "case.json")
    if err:
        print("[delivery_gate] USAGE/IO ERROR: {}".format(err))
        return 2
    if not isinstance(case, dict):
        print("[delivery_gate] USAGE/IO ERROR: case.json 顶层必须是 JSON 对象")
        return 2
    case_id = case.get("case_id")
    if not isinstance(case_id, str) or not case_id.strip():
        print("[delivery_gate] USAGE/IO ERROR: case.json 缺少有效的 case_id 字符串")
        return 2
    contract = case.get("output_contract")
    if not isinstance(contract, dict) or not contract:
        print("[delivery_gate] USAGE/IO ERROR: case.json 缺少有效的 output_contract 非空对象")
        return 2

    result_path = os.path.join(args.out, "result.json")
    result, err = load_json(result_path, "result.json")
    if err:
        print("[delivery_gate] USAGE/IO ERROR: {}".format(err))
        return 2
    if not isinstance(result, dict):
        print("[delivery_gate] USAGE/IO ERROR: result.json 顶层必须是 JSON 对象")
        return 2

    # 必交产物字段：优先 contract.json 的 required_artifacts，缺失时回退名字启发式
    contract_path = args.contract or os.path.join(args.out, "contract.json")
    artifact_fields = None
    if os.path.isfile(contract_path):
        cdoc, cerr = load_json(contract_path, "contract.json")
        if cerr or not isinstance(cdoc, dict):
            print("[delivery_gate] USAGE/IO ERROR: contract.json 不可用：{}".format(
                cerr or "顶层非对象"))
            return 2
        ra = cdoc.get("required_artifacts")
        if isinstance(ra, list):
            artifact_fields = [str(x) for x in ra]
    if artifact_fields is None:
        artifact_fields = [k for k in (str(x) for x in contract.keys())
                           if k in ARTIFACT_FIELD_NAMES]

    status = result.get("status")
    blocked = (status == "blocked")
    violations = []

    # ---- D1：case_id 一致 ----
    if result.get("case_id") != case_id:
        violations.append(
            "D1: case_id 不一致：result.json 为 {!r}，case.json 为 {!r}".format(
                result.get("case_id"), case_id))

    # ---- D5：status 受控词表（提前判定，后续规则依赖 status）----
    if status not in VALID_STATUS:
        violations.append(
            "D5: status 非法：{!r}（受控词表 completed / partial / blocked）".format(status))

    # ---- D2：契约字段齐备且非占位 ----
    if not blocked:
        limitations = result.get("limitations")
        lim_text = json.dumps(limitations, ensure_ascii=False) \
            if isinstance(limitations, (list, str)) else ""
        for field in [str(k) for k in contract.keys()]:
            if field not in result:
                violations.append("D2: 契约字段缺失：{}".format(field))
                continue
            value = result[field]
            if isinstance(value, str) and value == PENDING:
                violations.append("D2: 契约字段仍为 PENDING 占位：{}".format(field))
            elif is_empty(value):
                if status == "partial":
                    if field not in lim_text:
                        violations.append(
                            "D2: partial 下空字段未在 limitations 中逐项声明原因：{}".format(field))
                elif status == "completed":
                    violations.append("D2: completed 下契约字段为空：{}".format(field))
                else:
                    violations.append("D2: 契约字段为空且 status 无法豁免：{}".format(field))

    # ---- D3：必交产物真实落盘且非空 ----
    if not blocked:
        for field in artifact_fields:
            value = result.get(field, PENDING)
            if isinstance(value, str) and value == PENDING:
                continue  # 由 D2 负责，不重复计数
            if field not in result:
                continue  # 同上
            paths = resolve_paths(value)
            if paths is None:
                violations.append(
                    "D3: 字段 {} 的值无法解析为产物路径（实际为 {}）".format(
                        field, type(value).__name__))
                continue
            if not paths:
                continue  # 空值由 D2 负责
            for rel in paths:
                problem = check_artifact_file(args.out, field, rel)
                if problem:
                    violations.append("D3: {}".format(problem))

    # ---- D4：诚实一致性 ----
    if status == "completed":
        for field in artifact_fields:
            if field in result and is_empty(result[field]):
                violations.append(
                    "D4: completed 状态下必交产物字段为空：{}（completed ⇒ 产物非空）".format(field))
        if is_empty(result.get("sources")):
            violations.append("D4: completed 状态下 sources 为空（completed ⇒ sources 非空）")
    elif status == "partial":
        if is_empty(result.get("limitations")):
            violations.append("D4: partial 状态下 limitations 为空（partial ⇒ limitations 非空）")
    elif status == "blocked":
        if is_empty(result.get("blocked_reason")):
            violations.append("D4: blocked 状态下缺少 blocked_reason（blocked ⇒ 必须有 blocked_reason）")

    # ---- D6：change_log 条目模式 ----
    change_log = result.get("change_log")
    if change_log is None:
        violations.append("D6: 缺少 change_log 字段（须为数组，可为空数组）")
    elif not isinstance(change_log, list):
        violations.append("D6: change_log 不是数组（实际为 {}）".format(type(change_log).__name__))
    else:
        for idx, entry in enumerate(change_log):
            if not isinstance(entry, dict):
                violations.append("D6: change_log[{}] 不是对象".format(idx))
                continue
            bad = [k for k in CHANGE_LOG_KEYS
                   if k not in entry or not isinstance(entry[k], str) or not entry[k].strip()]
            if bad:
                violations.append(
                    "D6: change_log[{}] 缺少非空字符串键：{}（模式 file/what/why/rollback）".format(
                        idx, ", ".join(bad)))

    # ---- 汇总 ----
    if violations:
        print("GATE: FAIL（{} 项违例）".format(len(violations)))
        for item in violations:
            print(item)
        return 1
    print("GATE: PASS")
    print("  status={} case_id={}".format(status, case_id))
    checked = ["D1", "D4", "D5", "D6"] + ([] if blocked else ["D2", "D3"])
    print("  已检查：" + " / ".join(checked))
    print("  必交产物字段：{}".format(
        ", ".join(artifact_fields) if artifact_fields else "（无）"))
    if blocked:
        print("  blocked 状态：D2/D3 豁免，D4 已确认 blocked_reason 存在")
    return 0


if __name__ == "__main__":
    sys.exit(main())
