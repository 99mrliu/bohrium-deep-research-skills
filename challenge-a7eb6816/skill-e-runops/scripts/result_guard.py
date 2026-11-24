#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""result_guard.py — 保底 result.json 管理工具（仅 Python 3 标准库）。

用途：在任何时刻保证 /app/output/result.json 存在且状态诚实。

子命令：
  init      按 case.json 的 output_contract 生成 partial 脚手架
  update    回填指定字段（--value 字符串 / --value-json JSON 值）
  finalize  校验并定稿：complete / partial / failed 三态判定

退出码：
  0  命令成功（含 finalize 判定为 partial/failed 并如实写入）
  9  操作失败（文件缺失、JSON 非法、参数错误等）

诚实状态判定规则（写死，不得绕过）：
  complete  仅当：output_contract 全部必填字段非空
            且 limitations 为空列表
            且所有"产物路径"字段指向的文件真实存在
  partial   有任何缺口（必填为空 / limitations 非空 / 产物缺失）但已有可交付内容
  failed    需显式传入 --fail-stage 与 --fail-reason，记录失败阶段与原因
"""
import argparse
import json
import os
import sys

ARTIFACT_EXTS = (".md", ".json", ".csv", ".txt", ".pdf", ".html",
                 ".cif", ".dat", ".png", ".jpg", ".jpeg", ".ipynb")
INIT_GAP = "初始化保底：管线尚未完成，全部字段待回填"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(obj, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def contract_fields(contract):
    """output_contract 兼容两种形态：{字段: 说明} 或 [字段, ...]。"""
    if isinstance(contract, dict):
        return list(contract.keys())
    if isinstance(contract, list):
        return [str(x) for x in contract]
    return []


def is_empty(v):
    if v is None:
        return True
    if isinstance(v, str):
        return v.strip() == ""
    if isinstance(v, (list, dict)):
        return len(v) == 0
    return False  # 数字 0 / False 视为已填写的合法值


def looks_like_path(v):
    return isinstance(v, str) and (
        v.lower().endswith(ARTIFACT_EXTS) or "/" in v or os.sep in v)


def cmd_init(a):
    case = load_json(a.case)
    cid = case.get("case_id", "unknown-case")
    fields = contract_fields(case.get("output_contract", {}))
    result = {"case_id": cid, "status": "partial"}
    for f in fields:
        if f in result:
            continue
        result[f] = [] if f == "limitations" else ""
    result.setdefault("limitations", [])
    gaps = list(result.get("limitations") or [])
    gaps.append(INIT_GAP)
    for g in (a.gap or []):
        if g not in gaps:
            gaps.append(g)
    result["limitations"] = gaps
    out = os.path.join(a.out, "result.json")
    dump_json(result, out)
    print(f"[result_guard init] 保底 partial 已写入: {out} (字段: {', '.join(fields) or '无契约'})")
    return 0


def cmd_update(a):
    result = load_json(a.result)
    if a.value_json is not None:
        try:
            value = json.loads(a.value_json)
        except json.JSONDecodeError as e:
            print(f"[result_guard update] --value-json 解析失败: {e}", file=sys.stderr)
            return 9
    else:
        value = a.value
    known = set(result.keys())
    if a.field not in known:
        print(f"[result_guard update] 警告: 字段 '{a.field}' 不在现有 result 中，仍将写入",
              file=sys.stderr)
    result[a.field] = value
    # 回填实质字段后，移除初始化占位缺口
    if a.field != "limitations" and isinstance(result.get("limitations"), list):
        result["limitations"] = [g for g in result["limitations"] if g != INIT_GAP]
    dump_json(result, a.result)
    print(f"[result_guard update] {a.field} 已回填 -> {a.result}")
    return 0


def cmd_finalize(a):
    result = load_json(a.result)
    if a.fail_stage:
        result["status"] = "failed"
        result["failure"] = {"stage": a.fail_stage,
                             "reason": a.fail_reason or "未提供原因"}
        dump_json(result, a.result)
        print(f"[result_guard finalize] FAILED 已记录: stage={a.fail_stage}")
        return 0
    contract = {}
    if a.case:
        contract = load_json(a.case).get("output_contract", {})
    fields = contract_fields(contract) or [k for k in result.keys() if k != "status"]
    gaps = []
    for f in fields:
        if f == "status":
            continue
        if f == "limitations":
            if result.get("limitations"):
                gaps.append("limitations 未清空: " + "; ".join(
                    str(x) for x in result["limitations"]))
            continue
        v = result.get(f)
        if is_empty(v):
            gaps.append(f"必填字段 '{f}' 为空")
            continue
        if looks_like_path(v):
            ok = os.path.exists(v)
            if not ok and a.outdir:
                ok = os.path.exists(os.path.join(a.outdir, v))
            if not ok:
                gaps.append(f"产物路径不存在: {v}")
    if gaps:
        result["status"] = "partial"
        lim = result.get("limitations")
        if not isinstance(lim, list):
            lim = [] if is_empty(lim) else [str(lim)]
        for g in gaps:
            if g.startswith("limitations 未清空"):
                continue  # 元缺口不回写，避免自我重复
            if g not in lim:
                lim.append(g)
        result["limitations"] = lim
        dump_json(result, a.result)
        print(f"[result_guard finalize] 保持 PARTIAL，剩余缺口 {len(gaps)} 项:")
        for g in gaps:
            print(f"  - {g}")
        return 0
    result["status"] = "complete"
    dump_json(result, a.result)
    print("[result_guard finalize] COMPLETE：全部必填非空、limitations 为空、产物存在")
    return 0


def main():
    p = argparse.ArgumentParser(description="保底 result.json 管理（诚实 partial）")
    sub = p.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("init", help="按 output_contract 生成 partial 脚手架")
    pi.add_argument("--case", required=True)
    pi.add_argument("--out", required=True, help="输出目录（result.json 写入其中）")
    pi.add_argument("--gap", action="append", default=[],
                    help="已知缺口，可重复传入")
    pi.set_defaults(fn=cmd_init)
    pu = sub.add_parser("update", help="回填指定字段")
    pu.add_argument("--result", required=True)
    pu.add_argument("--field", required=True)
    pu.add_argument("--value", default=None)
    pu.add_argument("--value-json", default=None)
    pu.set_defaults(fn=cmd_update)
    pf = sub.add_parser("finalize", help="三态校验并定稿")
    pf.add_argument("--result", required=True)
    pf.add_argument("--outdir", default=None, help="产物路径解析的备选基准目录")
    pf.add_argument("--case", default=None, help="提供则以 output_contract 校验")
    pf.add_argument("--fail-stage", default=None)
    pf.add_argument("--fail-reason", default=None)
    pf.set_defaults(fn=cmd_finalize)
    a = p.parse_args()
    try:
        return a.fn(a)
    except FileNotFoundError as e:
        print(f"[result_guard] 文件缺失: {e}", file=sys.stderr)
        return 9
    except json.JSONDecodeError as e:
        print(f"[result_guard] JSON 非法: {e}", file=sys.stderr)
        return 9
    except OSError as e:
        print(f"[result_guard] IO 错误: {e}", file=sys.stderr)
        return 9


if __name__ == "__main__":
    sys.exit(main())
