#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""parse_case.py — 读取 case.json 与 task.md，盘点输入材料并嗅探冲突标注 fixture。

用法:
    python3 parse_case.py [--input-dir /input] [--work /app/work]

输出:
    <work>/case_summary.json
      {case_id, research_question, output_contract:[字段名...],
       materials:[{file,size_bytes,kind}], fixtures:[{file,trigger}],
       mode: dual_fixture | dual_model}

嗅探规则: 材料文件名或 JSON 内容键名(深度<=4)含 annotation/annotator/conflict/
reviewer/rater/adjudicat/标注/分歧/冲突/仲裁 等标记 → 判为冲突标注 fixture。
fixture 一律视为「输入 fixture」而非事实或金标准，原样保留。

退出码: 0=成功, 2=用法或IO错误, 3=校验失败(本脚本一般不产生)
"""
import argparse
import json
import sys
import traceback
from pathlib import Path

FIXTURE_MARKERS = (
    "annotation", "annotator", "conflict", "reviewer", "rater",
    "adjudicat", "标注", "分歧", "冲突", "仲裁",
)
SKIP_NAMES = {"case.json", "task.md"}
CONTRACT_KEYS = ("output_contract", "contract", "output_fields", "deliverable_fields")
CASE_ID_KEYS = ("case_id", "id", "case")
RQ_KEYS = ("research_question", "question", "rq", "pico")


def eprint(*a):
    print(*a, file=sys.stderr)


def name_matches(name: str) -> bool:
    low = name.lower()
    return any(m in low for m in FIXTURE_MARKERS)


def json_keys_match(obj, depth=0) -> bool:
    if depth > 4:
        return False
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and any(m in k.lower() for m in FIXTURE_MARKERS):
                return True
            if json_keys_match(v, depth + 1):
                return True
    elif isinstance(obj, list):
        for it in obj[:50]:
            if json_keys_match(it, depth + 1):
                return True
    return False


def find_first(obj, keys, depth=0):
    """深度优先在嵌套 dict 中找第一个匹配的键值。"""
    if depth > 6 or not isinstance(obj, dict):
        return None
    for k in keys:
        if k in obj and obj[k] not in (None, "", []):
            return obj[k]
    for v in obj.values():
        r = find_first(v, keys, depth + 1)
        if r is not None:
            return r
    return None


def normalize_contract(raw):
    """合同可能是字段名列表、{字段:说明} 字典或嵌套结构，统一成字段名列表。"""
    fields = []
    if isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(v, (dict, list)):
                fields.extend(normalize_contract(v))
            else:
                fields.append(str(k))
    elif isinstance(raw, list):
        for it in raw:
            if isinstance(it, str):
                fields.append(it)
            elif isinstance(it, dict):
                fields.extend(normalize_contract(it))
    elif isinstance(raw, str):
        fields.append(raw)
    # 保序去重
    seen, out = set(), []
    for f in fields:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def sniff_fixture(path: Path):
    """返回触发原因字符串；非 fixture 返回 None。"""
    if name_matches(path.name):
        return "filename_marker"
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if json_keys_match(data):
                return "json_key_marker"
        except Exception:
            return None
    return None


def main():
    ap = argparse.ArgumentParser(description="解析 case.json/task.md 并嗅探冲突标注 fixture")
    ap.add_argument("--input-dir", default="/input", help="输入目录 (默认 /input)")
    ap.add_argument("--work", default="/app/work", help="工作目录 (默认 /app/work)")
    args = ap.parse_args()

    in_dir = Path(args.input_dir)
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)

    case_path = in_dir / "case.json"
    if not case_path.exists():
        eprint(f"[parse_case] 缺少 {case_path}")
        return 2
    case = json.loads(case_path.read_text(encoding="utf-8"))

    task_text = ""
    task_path = in_dir / "task.md"
    if task_path.exists():
        task_text = task_path.read_text(encoding="utf-8")

    case_id = find_first(case, CASE_ID_KEYS) or in_dir.name or "unknown_case"
    rq = find_first(case, RQ_KEYS) or ""
    contract_raw = find_first(case, CONTRACT_KEYS)
    contract = normalize_contract(contract_raw) if contract_raw else []
    if not contract:
        eprint("[parse_case] 警告: 未在 case.json 中找到 output_contract，"
               "将从 task.md 与运行时判断回填合同字段。")

    materials, fixtures = [], []
    for p in sorted(in_dir.iterdir()):
        if not p.is_file() or p.name in SKIP_NAMES:
            continue
        entry = {"file": str(p), "name": p.name,
                 "size_bytes": p.stat().st_size,
                 "kind": p.suffix.lower().lstrip(".") or "unknown"}
        materials.append(entry)
        trig = sniff_fixture(p)
        if trig:
            fixtures.append({"file": str(p), "name": p.name, "trigger": trig})

    mode = "dual_fixture" if fixtures else "dual_model"
    summary = {
        "case_id": str(case_id),
        "research_question": rq if isinstance(rq, str) else json.dumps(rq, ensure_ascii=False),
        "output_contract": contract,
        "task_md_excerpt": task_text[:2000],
        "materials": materials,
        "fixtures": fixtures,
        "mode": mode,
        "notice": "fixture 为输入材料而非事实/金标准；禁止声称实时数据库检索或全局召回。",
    }
    out = work / "case_summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[parse_case] case_id={summary['case_id']} mode={mode} "
          f"materials={len(materials)} fixtures={len(fixtures)} contract_fields={len(contract)}")
    print(f"[parse_case] -> {out}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        eprint("[parse_case] 未捕获异常:")
        traceback.print_exc()
        sys.exit(2)
