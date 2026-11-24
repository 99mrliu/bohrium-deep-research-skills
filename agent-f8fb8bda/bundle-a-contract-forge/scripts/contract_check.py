#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_check.py —— 阶段五：交付总门（仅 Python3 标准库，无网络依赖）。

读取 --case 的 case.json 与 --out 下的 result.json，逐项机械检查：

  F1  case_id 与 case.json 完全一致
  F2  output_contract 全部顶层字段存在且非 "PENDING" 占位；
      空值（空串/空数组/空对象）仅在 status=partial 时允许，且 limitations
      中必须存在提及该字段名的条目逐项声明原因；completed 下空字段直接判负
      （status=blocked 时 F2/F3/F6 豁免，改由 F4 要求 blocked_reason）
  F3  六个固定要点区块（problem_decomposition / search_coverage /
      evidence_linkage / conflict_evidence / synthesis / research_gaps）
      全部存在；status=completed 时全部非空
  F4  诚实一致性：completed ⇒ sources 非空；partial ⇒ limitations 非空；
      blocked ⇒ blocked_reason 非空；status 取值必须合法
  F5  sources 为数组，且每条含 id / title / locator 三个非空字符串键
  F6  synthesis 文本中出现的所有证据 id（[E-数字] 或 evidence_ids 列表，
      统一以模式 E-数字 提取）必须存在于 evidence_linkage 收集到的 id 集合

退出码：
  0  全部通过，打印 PASS 汇总
  1  门控违例，逐项打印 F 编号 + 具体问题
  2  用法 / IO 错误（文件缺失、JSON 损坏、case 结构不可用）
"""

import argparse
import json
import os
import re
import sys

SIX_BLOCKS = ["problem_decomposition", "search_coverage", "evidence_linkage",
              "conflict_evidence", "synthesis", "research_gaps"]

VALID_STATUS = {"completed", "partial", "blocked"}

EVIDENCE_ID_RE = re.compile(r"E-\d+")


def is_empty(value):
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def collect_linkage_ids(node, out):
    """递归收集 evidence_linkage 结构中所有 "id" 键的字符串值。"""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "id" and isinstance(value, str) and value.strip():
                out.add(value.strip())
            collect_linkage_ids(value, out)
    elif isinstance(node, list):
        for item in node:
            collect_linkage_ids(item, out)


def load_json(path, label):
    """返回 (obj, error)；error 非 None 表示用法/IO 错误。"""
    if not os.path.isfile(path):
        return None, "{} 不存在：{}".format(label, path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh), None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, "{} 读取或解析失败：{}".format(label, exc)


def main(argv=None):
    parser = argparse.ArgumentParser(description="阶段五：result.json 交付总门（F1-F6）")
    parser.add_argument("--case", default="/input/case.json", help="case.json 路径")
    parser.add_argument("--out", default="/app/output", help="result.json 所在目录")
    args = parser.parse_args(argv)

    case, err = load_json(args.case, "case.json")
    if err:
        print("[contract_check] USAGE/IO ERROR: {}".format(err))
        return 2
    if not isinstance(case, dict):
        print("[contract_check] USAGE/IO ERROR: case.json 顶层必须是 JSON 对象")
        return 2
    case_id = case.get("case_id")
    if not isinstance(case_id, str) or not case_id.strip():
        print("[contract_check] USAGE/IO ERROR: case.json 缺少有效的 case_id 字符串")
        return 2
    contract = case.get("output_contract")
    if not isinstance(contract, dict) or not contract:
        print("[contract_check] USAGE/IO ERROR: case.json 缺少有效的 output_contract 非空对象")
        return 2

    result_path = os.path.join(args.out, "result.json")
    result, err = load_json(result_path, "result.json")
    if err:
        print("[contract_check] USAGE/IO ERROR: {}".format(err))
        return 2
    if not isinstance(result, dict):
        print("[contract_check] USAGE/IO ERROR: result.json 顶层必须是 JSON 对象")
        return 2

    status = result.get("status")
    blocked = (status == "blocked")
    failures = []

    # ---- F1：case_id 一致 ----
    if result.get("case_id") != case_id:
        failures.append("F1 case_id 不一致：result.json 为 {!r}，case.json 为 {!r}".format(
            result.get("case_id"), case_id))

    # ---- F2：契约字段存在且非占位 ----
    if not blocked:
        limitations = result.get("limitations")
        lim_text = json.dumps(limitations, ensure_ascii=False) \
            if isinstance(limitations, (list, str)) else ""
        for field in [str(k) for k in contract.keys()]:
            if field not in result:
                failures.append("F2 契约字段缺失：{}".format(field))
                continue
            value = result[field]
            if isinstance(value, str) and value == "PENDING":
                failures.append("F2 契约字段仍是 PENDING 占位：{}".format(field))
            elif is_empty(value):
                if status == "partial":
                    if field not in lim_text:
                        failures.append(
                            "F2 partial 状态下空字段未在 limitations 中逐项声明原因：{}".format(field))
                elif status == "completed":
                    failures.append("F2 completed 状态下契约字段为空：{}".format(field))
                else:
                    failures.append("F2 契约字段为空且 status 无法豁免：{}".format(field))

    # ---- F3：六要点区块齐备（completed 时非空）----
    if not blocked:
        for name in SIX_BLOCKS:
            if name not in result:
                failures.append("F3 六要点区块缺失：{}".format(name))
            elif status == "completed" and is_empty(result[name]):
                failures.append("F3 completed 状态下区块为空：{}".format(name))

    # ---- F4：诚实一致性 ----
    if status not in VALID_STATUS:
        failures.append("F4 status 非法：{!r}（须为 completed / partial / blocked）".format(status))
    elif status == "completed":
        if is_empty(result.get("sources")):
            failures.append("F4 completed 状态下 sources 为空（completed ⇒ sources 非空）")
    elif status == "partial":
        if is_empty(result.get("limitations")):
            failures.append("F4 partial 状态下 limitations 为空（partial ⇒ limitations 非空）")
    elif status == "blocked":
        if is_empty(result.get("blocked_reason")):
            failures.append("F4 blocked 状态下缺少 blocked_reason（blocked ⇒ 必须有 blocked_reason）")

    # ---- F5：sources 条目三键 ----
    sources = result.get("sources")
    if not isinstance(sources, list):
        failures.append("F5 sources 不是数组（实际为 {}）".format(type(sources).__name__))
    else:
        for idx, item in enumerate(sources):
            if not isinstance(item, dict):
                failures.append("F5 sources[{}] 不是对象".format(idx))
                continue
            missing = [k for k in ("id", "title", "locator")
                       if k not in item or not isinstance(item[k], str) or not item[k].strip()]
            if missing:
                failures.append("F5 sources[{}] 缺少非空键：{}".format(idx, ", ".join(missing)))

    # ---- F6：synthesis 引用的证据 id 必须存在于 evidence_linkage ----
    if not blocked and "synthesis" in result:
        synthesis_text = json.dumps(result["synthesis"], ensure_ascii=False)
        cited = sorted(set(EVIDENCE_ID_RE.findall(synthesis_text)))
        linkage_ids = set()
        collect_linkage_ids(result.get("evidence_linkage"), linkage_ids)
        for eid in cited:
            if eid not in linkage_ids:
                failures.append(
                    "F6 synthesis 引用的证据 id 不存在于 evidence_linkage：{}".format(eid))

    # ---- 汇总 ----
    if failures:
        print("GATE: FAIL（{} 项违例）".format(len(failures)))
        for item in failures:
            print("  " + item)
        return 1
    checked = ["F1", "F5"] + ([] if blocked else ["F2", "F3", "F6"]) + ["F4"]
    print("GATE: PASS")
    print("  status={} case_id={}".format(status, case_id))
    print("  已检查：" + " / ".join(sorted(set(checked))))
    if blocked:
        print("  blocked 状态：F2/F3/F6 豁免，F4 已确认 blocked_reason 存在")
    return 0


if __name__ == "__main__":
    sys.exit(main())
