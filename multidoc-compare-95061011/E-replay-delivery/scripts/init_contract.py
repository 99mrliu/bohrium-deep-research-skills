#!/usr/bin/env python3
"""init_contract.py — 契约优先：开工第一步。

读 case.json（容忍无 output_contract），生成：
  work/result.schema.json   钉死 result.json 的字段清单（字段名原样照搬）
  out/result.json           骨架（status=partial 起步，此时即为降级梯 L2 可交付状态）

此后所有渲染朝 result.schema.json 收口，交付前由 contract_lint.py 强校验。
仅标准库，无网络。
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import manifest as mf  # noqa: E402

STATUS_ENUM = ["success", "partial", "failed"]
BASE_FIELDS = ["case_id", "status", "sources", "uncertainty"]


def dump_json(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def contract_fields_of(case):
    """从 case.json 提取 output_contract 字段名（原样照搬）。支持 dict 或 list；无则 None。"""
    contract = case.get("output_contract")
    if isinstance(contract, dict):
        return list(contract.keys())
    if isinstance(contract, list) and all(isinstance(x, str) for x in contract):
        return list(contract)
    return None


def main():
    ap = argparse.ArgumentParser(description="契约优先：生成 result.schema.json 与 result.json 骨架")
    ap.add_argument("--case", default="/input/case.json", help="case.json 路径")
    ap.add_argument("--workdir", default="/app/work", help="中间产物目录")
    ap.add_argument("--outdir", default="/app/output", help="最终交付目录")
    args = ap.parse_args()

    case_path = Path(args.case)
    if not case_path.exists():
        raise SystemExit(f"[init_contract] 缺少输入: {case_path}")
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case_id = case.get("case_id")
    if not case_id:
        raise SystemExit("[init_contract] case.json 缺 case_id，无法建立契约")

    fields = contract_fields_of(case)
    has_contract = bool(fields)

    # 必填字段清单：case_id + 契约字段（原样照搬）+ status/sources/uncertainty，去重保序
    required = []
    for f in ["case_id"] + (fields or []) + ["status", "sources", "uncertainty"]:
        if f not in required:
            required.append(f)

    schema = {
        "schema_version": "1.0",
        "case_id": case_id,
        "has_output_contract": has_contract,
        "contract_fields": fields or [],
        "required_fields": required,
        "status_enum": STATUS_ENUM,
        "partial_rule": "status=partial 时 uncertainty 必须为非空字符串列表，并写明缺失边界（哪些文档/字段/维度未覆盖）",
        "sources_rule": "sources 引用的 document_id/paragraph_id 必须存在于 work/cells.jsonl 记录中",
        "fallback_note": None
        if has_contract
        else "case.json 无 output_contract，退化为基础契约 {case_id, status, result, sources, uncertainty}",
    }
    if not has_contract and "result" not in schema["required_fields"]:
        schema["required_fields"].insert(1, "result")

    workdir = Path(args.workdir)
    outdir = Path(args.outdir)
    workdir.mkdir(parents=True, exist_ok=True)
    outdir.mkdir(parents=True, exist_ok=True)
    (workdir / "result.schema.json").write_text(dump_json(schema), encoding="utf-8")

    skeleton = {"case_id": case_id}
    if fields:
        for f in fields:
            if f not in skeleton:
                skeleton[f] = None
    else:
        skeleton["result"] = None
    skeleton["status"] = "partial"
    skeleton["sources"] = []
    skeleton["uncertainty"] = [
        "init_contract：契约骨架已生成（降级梯 L2 可交付状态）；"
        "全部字段待 render_all.py 从 work/cells.jsonl + work/decisions.jsonl 渲染填充。"
    ]
    (outdir / "result.json").write_text(dump_json(skeleton), encoding="utf-8")

    mf.begin_stage(workdir, "init_contract", [case_path])
    mf.end_stage(
        workdir,
        "init_contract",
        [workdir / "result.schema.json", outdir / "result.json"],
    )
    print(
        f"[init_contract] case_id={case_id} 契约字段 {len(fields) if fields else 0} 项"
        f"（{'output_contract 原样照搬' if has_contract else '无 output_contract，基础契约退化'}）"
    )
    print(f"[init_contract] 已落盘: {workdir/'result.schema.json'}, {outdir/'result.json'}（骨架，status=partial）")


if __name__ == "__main__":
    main()
