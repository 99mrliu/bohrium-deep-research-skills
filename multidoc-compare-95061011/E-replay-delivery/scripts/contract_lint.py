#!/usr/bin/env python3
"""contract_lint.py — result.json 契约强校验（失败非零退出）。

校验项（细则见 references/contract-spec.md）：
  1. result.json 存在且为合法 JSON；
  2. case_id 与 case.json 一致（原样复制）；
  3. case.json 的 output_contract 全部字段在场（字段名原样照搬）；无 output_contract 时检查基础字段；
  4. status ∈ {success, partial, failed}；
  5. status=partial ⇒ uncertainty 为非空字符串列表（必须写明缺失边界）；
  6. sources 引用的 document_id/paragraph_id 必须存在于 work/cells.jsonl 记录中；
  7. 数值交叉校验：result.json 内 comparison_matrix 条目的 value/numeric_value
     必须与 cells.jsonl 中同 (document_id, paragraph_id, field) 的记录一致（防手改数字）。

仅标准库，无网络。
"""
import argparse
import json
import sys
from pathlib import Path

STATUS_VALUES = {"success", "partial", "failed"}


def load_jsonl(path):
    recs = []
    if not path.exists():
        return recs
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            recs.append(json.loads(line))
    return recs


def contract_fields_of(case):
    contract = case.get("output_contract")
    if isinstance(contract, dict):
        return list(contract.keys())
    if isinstance(contract, list) and all(isinstance(x, str) for x in contract):
        return list(contract)
    return None


def main():
    ap = argparse.ArgumentParser(description="result.json 契约强校验")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--workdir", default="/app/work")
    ap.add_argument("--outdir", default="/app/output")
    args = ap.parse_args()

    errors = []
    case = json.loads(Path(args.case).read_text(encoding="utf-8"))
    rj_path = Path(args.outdir) / "result.json"
    if not rj_path.exists():
        print(f"[contract_lint] 失败：{rj_path} 不存在")
        sys.exit(1)
    try:
        result = json.loads(rj_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[contract_lint] 失败：result.json 不是合法 JSON: {e}")
        sys.exit(1)

    # 2. case_id 一致
    case_id = case.get("case_id")
    if result.get("case_id") != case_id:
        errors.append(
            f"case_id 不一致: result.json={result.get('case_id')!r} ≠ case.json={case_id!r}"
        )

    # 3. 契约字段在场（字段名原样照搬）
    fields = contract_fields_of(case)
    if fields:
        for f in fields:
            if f not in result:
                errors.append(f"output_contract 字段缺失: {f}")
    else:
        for f in ("case_id", "status", "result", "sources", "uncertainty"):
            if f not in result:
                errors.append(f"基础字段缺失（无 output_contract 退化契约）: {f}")

    # 4. status 合法
    st = result.get("status")
    if st not in STATUS_VALUES:
        errors.append(f"status 非法: {st!r}（须为 success/partial/failed）")

    # 5. partial ⇒ uncertainty 非空
    unc = result.get("uncertainty")
    if "uncertainty" not in result:
        errors.append("缺 uncertainty 字段")
    elif st == "partial":
        if (
            not isinstance(unc, list)
            or not unc
            or not all(isinstance(x, str) and x.strip() for x in unc)
        ):
            errors.append(
                "status=partial 但 uncertainty 为空或非字符串列表（必须写明缺失边界）"
            )

    if "sources" not in result:
        errors.append("缺 sources 字段")

    # 6. sources 引用存在性
    cells = load_jsonl(Path(args.workdir) / "cells.jsonl")
    pair_index = {(c.get("paper_document_id"), c.get("paragraph_id")) for c in cells}
    doc_index = {c.get("paper_document_id") for c in cells}
    for s in result.get("sources", []) or []:
        doc = s.get("document_id")
        if doc not in doc_index:
            errors.append(f"sources 引用了记录中不存在的文档: {doc}")
            continue
        for pid in s.get("paragraph_ids", []):
            if (doc, pid) not in pair_index:
                errors.append(f"sources 引用了记录中不存在的段落: {doc}/{pid}")

    # 7. 数值交叉校验（防手改数字）
    cell_index = {
        (c.get("paper_document_id"), c.get("paragraph_id"), c.get("field")): c
        for c in cells
    }
    cm = result.get("comparison_matrix")
    if isinstance(cm, list):
        for e in cm:
            if not isinstance(e, dict):
                errors.append(f"comparison_matrix 条目非对象: {e!r}")
                continue
            key = (e.get("document_id"), e.get("paragraph_id"), e.get("field"))
            rec = cell_index.get(key)
            if rec is None:
                errors.append(f"comparison_matrix 条目在记录中不存在: {key}")
                continue
            if e.get("numeric_value") != rec.get("numeric_value"):
                errors.append(
                    f"数值与记录不符 {key}: result.json={e.get('numeric_value')!r} "
                    f"≠ cells.jsonl={rec.get('numeric_value')!r}（疑似手改数字）"
                )
            if e.get("value") != rec.get("value"):
                errors.append(
                    f"文本与记录不符 {key}: result.json={e.get('value')!r} "
                    f"≠ cells.jsonl={rec.get('value')!r}"
                )

    if errors:
        print("[contract_lint] 契约校验失败：")
        for e in errors:
            print("  - " + e)
        sys.exit(1)
    print(
        f"[contract_lint] 通过：{rj_path}"
        f"（契约字段 {len(fields) if fields else '基础'} 项在场，"
        f"status={st}，sources {len(result.get('sources', []) or [])} 项，数值交叉校验一致）"
    )


if __name__ == "__main__":
    main()
