#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract.py — 契约优先交付门禁（骨架生成 + 机器校验）

两个互斥功能：
  --skeleton : 从 case.json 解析 output_contract，生成 result.json 骨架
               （每个 contract 字段给类型占位值 + 填充计划），写入
               <workdir>/result_skeleton.json
  --verify   : 校验 <out>/result.json：
                 * case_id 非空且与 case.json 一致
                 * output_contract 每个 key 在 result.json 顶层在场且非占位符
                 * status 合法（ok/partial/failed）
               打印逐字段填充状态表（filled/empty/missing）与 ok=true/false，
               退出码 0 = 通过，1 = 未通过，2 = 用法/IO 错误。

仅使用 Python 3 标准库；脚本位置无关（pathlib）；默认离线。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 占位符判定：空串与常见占位词（比较前做小写与去空白）
PLACEHOLDER_STRINGS = {"", "todo", "tbd", "<placeholder>", "placeholder", "n/a", "none", "null", "-"}
VALID_STATUS = {"ok", "partial", "failed"}

# 已知契约字段的填充计划说明（供 --skeleton 写入注释；自定义字段走默认说明）
FILL_PLAN = {
    "case_id": "从 case.json 顶层 case_id 原样复制；pipeline 自动填充",
    "seed_paper": "种子记录视图：DOI/标题鲁棒解析后的规范化记录（含 locator）；pipeline 自动填充",
    "seed": "同 seed_paper 的简写别名；pipeline 自动填充",
    "candidates": "去重后的候选文献清单（含 layer/relation/locator/stub 标记）；pipeline 自动填充",
    "edges": "引用边表（kind=reference/citation，含 direction_restored 标记与 locator）；pipeline 自动填充",
    "sources": "来源注册表：file/format/records/status/error；pipeline 自动填充",
    "evidence_records": "逐候选与逐边的关联依据 + 可回指定位 {file,pointer}；pipeline 自动填充",
    "status": "ok/partial/failed，诚实反映完成度；pipeline 自动填充",
    "uncertainty": "stub、解析失败、合并、缺字段等不确定性说明；pipeline 自动填充",
    "layer_counts": "各扩展层新增候选数统计；pipeline 自动填充",
    "method_summary": "一段中文方法摘要（扩展方向、去重键、规模）；pipeline 自动填充",
}
DEFAULT_PLAN = ("自定义契约字段：pipeline 无内置填充器。优先在 pipeline.py 的 "
                "FILLERS 注册表中补充填充逻辑；确实无法填充时给类型空值，"
                "并在 uncertainty 中写明字段名以便 verify 豁免。")


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def type_placeholder(decl) -> object:
    """按 output_contract 中声明的类型描述生成占位值。"""
    d = str(decl).strip().lower()
    if d in ("array", "list", "array<object>", "list<object>", "array<string>"):
        return []
    if d in ("object", "dict", "map"):
        return {}
    if d in ("number", "integer", "int", "float"):
        return 0
    if d in ("boolean", "bool"):
        return False
    return ""  # string 及未知声明默认空串占位


def classify_value(value) -> str:
    """filled / empty 二分（missing 由调用方在 key 缺席时给出）。"""
    if value is None:
        return "empty"
    if isinstance(value, str):
        return "empty" if value.strip().lower() in PLACEHOLDER_STRINGS else "filled"
    if isinstance(value, (list, dict)):
        return "empty" if len(value) == 0 else "filled"
    return "filled"  # 数字与布尔：在场即视为已填充


def cmd_skeleton(args) -> int:
    case_path = Path(args.case).resolve()
    workdir = Path(args.workdir).resolve()
    case = load_json(case_path)
    contract = case.get("output_contract")
    if not isinstance(contract, dict) or not contract:
        print("[contract] ERROR: case.json 缺少非空 output_contract 对象", file=sys.stderr)
        return 2
    skeleton = {}
    plan = {}
    for field, decl in contract.items():
        if field == "case_id":
            skeleton[field] = case.get("case_id", "")
        else:
            skeleton[field] = type_placeholder(decl)
        plan[field] = FILL_PLAN.get(field, DEFAULT_PLAN)
    doc = {
        "_meta": {
            "purpose": "result.json 骨架：output_contract 逐字段占位 + 填充计划；"
                       "pipeline.py 会按 output_contract 自动镜像填充，无需手工编辑本文件",
            "case_file": str(case_path),
            "contract_fields": len(contract),
        },
        "_fill_plan": plan,
        "skeleton": skeleton,
    }
    workdir.mkdir(parents=True, exist_ok=True)
    out_path = workdir / "result_skeleton.json"
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[contract] skeleton written: {out_path} ({len(contract)} contract fields)")
    for field in contract:
        print(f"  - {field}: {contract[field]!r} -> {plan[field][:40]}...")
    return 0


def cmd_verify(args) -> int:
    case_path = Path(args.case).resolve()
    result_path = Path(args.out).resolve() / "result.json"
    case = load_json(case_path)
    contract = case.get("output_contract")
    if not isinstance(contract, dict) or not contract:
        print("[contract] ERROR: case.json 缺少非空 output_contract 对象", file=sys.stderr)
        return 2
    if not result_path.exists():
        print(f"[contract] ERROR: 未找到 {result_path}", file=sys.stderr)
        return 2
    result = load_json(result_path)

    problems = []
    # 1) case_id 非空且一致
    case_id = case.get("case_id", "")
    rid = result.get("case_id", "")
    if not rid:
        problems.append("result.json 缺少 case_id 或为空")
    elif case_id and rid != case_id:
        problems.append(f"case_id 不一致: result={rid!r} vs case={case_id!r}")

    # 2) status 合法
    status = result.get("status", "")
    status_ok = status in VALID_STATUS

    # 3) 逐字段在场且非占位；空值若被 uncertainty 点名说明则视为 empty(excused)
    uncertainty = result.get("uncertainty") or []
    unc_text = " ".join(str(u) for u in uncertainty)
    rows = []
    n_missing = n_empty = n_excused = 0
    for field, decl in contract.items():
        if field not in result:
            rows.append((field, str(decl), "missing", "key 缺席"))
            n_missing += 1
            continue
        state = classify_value(result[field])
        if state == "empty":
            if field in unc_text:
                rows.append((field, str(decl), "empty(excused)", "空值已在 uncertainty 中说明"))
                n_excused += 1
            else:
                rows.append((field, str(decl), "empty", "空值/占位符且未在 uncertainty 说明"))
                n_empty += 1
        else:
            rows.append((field, str(decl), "filled", ""))

    ok = (not problems) and status_ok and n_missing == 0 and n_empty == 0

    # 输出逐字段表
    print("=" * 72)
    print(f"contract verify: {result_path}")
    print(f"case_id: {rid!r} (expected {case_id!r})  status: {status!r}")
    print("-" * 72)
    print(f"{'field':<22} {'declared':<14} {'state':<16} note")
    print("-" * 72)
    for field, decl, state, note in rows:
        print(f"{field:<22} {decl:<14} {state:<16} {note}")
    print("-" * 72)
    for p in problems:
        print(f"PROBLEM: {p}")
    if not status_ok:
        print(f"PROBLEM: status {status!r} 不合法（应为 ok/partial/failed）")
    print(f"summary: fields={len(rows)} filled={sum(1 for r in rows if r[2]=='filled')} "
          f"empty={n_empty} empty(excused)={n_excused} missing={n_missing}")
    print(f"ok={'true' if ok else 'false'}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="契约优先交付门禁：--skeleton 生成骨架 / --verify 校验结果")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--skeleton", action="store_true", help="从 case.json 生成 result.json 骨架到 <workdir>/result_skeleton.json")
    g.add_argument("--verify", action="store_true", help="校验 <out>/result.json 是否逐字段镜像填充 output_contract")
    ap.add_argument("--case", default="/input/case.json", help="case.json 路径（默认 /input/case.json）")
    ap.add_argument("--out", default="/app/output", help="输出目录（默认 /app/output）")
    ap.add_argument("--workdir", default="/app/work", help="工作目录（默认 /app/work）")
    args = ap.parse_args()
    try:
        if args.skeleton:
            return cmd_skeleton(args)
        return cmd_verify(args)
    except FileNotFoundError as exc:
        print(f"[contract] ERROR: 文件不存在: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"[contract] ERROR: JSON 解析失败: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
