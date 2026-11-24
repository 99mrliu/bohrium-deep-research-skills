#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
assemble_result.py —— result.json 装配器（仅 Python3 标准库）。

两种用途：
    skeleton  从 case.json 生成骨架 result.json：output_contract 全部字段原样保留，
              case_id 填真实值，其余一律 "PENDING" —— 诚实 partial 的基线。
    final     从 workplan / worklog / deliverable 及可选的
              preserved_facts.json、evidence_map.json 装配终版 result.json，
              并附上诚实的 status / sources / uncertainty / change records。

既可被 gate.py 以 import 方式调用，也可独立命令行使用：
    python3 assemble_result.py skeleton --case /input/case.json --out /app/output/result.json
    python3 assemble_result.py final --case /input/case.json \
        --workplan /app/work/workplan.json --worklog /app/work/worklog.jsonl \
        --workdir /app/work --out /app/output/result.json
"""

import argparse
import json
import os
import re
from datetime import datetime, timezone

PENDING = "PENDING"
UNCERTAIN_MARK = "【待确认】"
PLACEHOLDER_RE = re.compile(r"TODO|FIXME|XXX|TBD|<PLACEHOLDER>|占位符")

# 契约中常见键的默认空结构（终版装配时若工作目录没有对应文件则用这些诚实空值）
TYPED_DEFAULTS = {
    "deliverable": PENDING,
    "preserved_facts": list,
    "evidence_map": dict,
    "change_log": list,
    "sources": list,
    "uncertainty": list,
    "status": "partial",
}


def contract_keys(case):
    """output_contract 兼容 dict（键→说明）与 list（键名）两种写法；都没有则用典型五键。"""
    oc = case.get("output_contract")
    if isinstance(oc, dict):
        return list(oc.keys())
    if isinstance(oc, list):
        return [str(k) for k in oc]
    return ["case_id", "deliverable", "preserved_facts", "evidence_map", "change_log"]


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _load(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _dump(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ---- 骨架 ----------------------------------------------------------------------
def build_skeleton(case):
    """全字段原样保留：case_id 真实值，其余一律 PENDING。"""
    res = {}
    for k in contract_keys(case):
        res[k] = str(case.get("case_id", "UNKNOWN")) if k == "case_id" else PENDING
    return res


def write_skeleton(case, out_path):
    res = build_skeleton(case)
    _dump(out_path, res)
    return res


# ---- 终版 ----------------------------------------------------------------------
def _typed_value(key, work_dir, deliverable_text, change_log, status, sources, uncertainty):
    """按常见键给出类型正确的终版值；未知键返回 None 由调用方兜底。"""
    if key == "deliverable":
        return deliverable_text.strip() if deliverable_text.strip() else PENDING
    if key == "preserved_facts":
        v = _load(os.path.join(work_dir, "preserved_facts.json"))
        return v if isinstance(v, list) else []
    if key == "evidence_map":
        v = _load(os.path.join(work_dir, "evidence_map.json"))
        return v if isinstance(v, (dict, list)) else {}
    if key == "change_log":
        return change_log
    if key == "status":
        return status
    if key == "sources":
        return sources
    if key == "uncertainty":
        return uncertainty
    return None


def list_sources(input_dir):
    """sources：输入目录内除 case.json / task.md 外的材料文件相对路径清单。"""
    srcs = []
    for root, _dirs, names in os.walk(input_dir):
        for n in sorted(names):
            rel = os.path.relpath(os.path.join(root, n), input_dir)
            if rel not in ("case.json", "task.md"):
                srcs.append(rel)
    return sorted(srcs)


def build_change_log(worklog_path):
    """把 worklog.jsonl 汇成 change_log 列表（每条含 ts/stage/verdict/notes）。"""
    log = []
    for line in _read(worklog_path).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            log.append(json.loads(line))
        except json.JSONDecodeError:
            log.append({"ts": "", "stage": "unknown", "verdict": "WARN-BUT-PROCEED",
                        "notes": f"worklog 行无法解析：{line[:80]}"})
    return log


def extract_uncertainty(deliverable_text):
    """抽出含【待确认】的行，作为 uncertainty 的诚实来源。"""
    items = []
    for ln in deliverable_text.splitlines():
        if UNCERTAIN_MARK in ln:
            items.append(ln.strip()[:200])
    return items


def build_final(case, workplan, worklog_path, work_dir, input_dir=None):
    """装配终版 result.json（dict）。"""
    deliverable_text = _read(os.path.join(work_dir, "deliverable.md"))
    change_log = build_change_log(worklog_path)
    uncertainty = extract_uncertainty(deliverable_text)
    sources = list_sources(input_dir) if input_dir and os.path.isdir(input_dir) else []

    # 诚实 status：deliverable 缺失/占位/含 PENDING 或仍有【待确认】 → partial
    degraded = (
        not deliverable_text.strip()
        or PLACEHOLDER_RE.search(deliverable_text) is not None
        or PENDING in deliverable_text
        or len(uncertainty) > 0
    )
    status = "partial" if degraded else "complete"

    res = {}
    for k in contract_keys(case):
        if k == "case_id":
            res[k] = str(case.get("case_id", "UNKNOWN"))
            continue
        v = _typed_value(k, work_dir, deliverable_text, change_log, status, sources, uncertainty)
        if v is None:  # 契约中的未知键：诚实兜底
            v = PENDING
        res[k] = v

    # 契约未列但运行时契约要求诚实附带的字段（额外键不违反"原样包含全部字段"）
    res.setdefault("status", status)
    res.setdefault("sources", sources)
    res.setdefault("uncertainty", uncertainty)
    if not isinstance(res.get("change_log"), list) or not res["change_log"]:
        res["change_log"] = change_log or [
            {"ts": _now_iso(), "stage": "finalize", "verdict": "WARN-BUT-PROCEED",
             "notes": "worklog 为空；PENDING 字段为诚实占位，流程记录缺失。"}
        ]
    # 若仍有 PENDING 字段，在 change_log 追加说明，满足出口清单 E3 的"诚实降级"语义
    raw = json.dumps(res, ensure_ascii=False)
    if PENDING in raw:
        res["change_log"].append(
            {"ts": _now_iso(), "stage": "finalize", "verdict": "WARN-BUT-PROCEED",
             "notes": "result.json 仍含 PENDING 字段：对应内容在预算内未完成，如实保留。"})
    return res


def write_final(case, workplan, worklog_path, work_dir, out_path, input_dir=None):
    if input_dir is None:
        input_dir = (workplan or {}).get("paths", {}).get("input")
    res = build_final(case, workplan or {}, worklog_path, work_dir, input_dir)
    _dump(out_path, res)
    return res


# ---- 命令行 --------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="result.json 装配器：skeleton / final")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("skeleton", "final"):
        p = sub.add_parser(name)
        p.add_argument("--case", required=True, help="case.json 路径")
        p.add_argument("--out", required=True, help="输出 result.json 路径")
        if name == "final":
            p.add_argument("--workplan", default=None)
            p.add_argument("--worklog", default=None)
            p.add_argument("--workdir", required=True)
            p.add_argument("--input-dir", default=None)
    args = ap.parse_args()
    case = _load(args.case)
    if case is None:
        print(f"[assemble][FATAL] 无法读取 {args.case}")
        return 1
    if args.cmd == "skeleton":
        write_skeleton(case, args.out)
    else:
        write_final(case, _load(args.workplan) if args.workplan else {},
                    args.worklog or os.path.join(args.workdir, "worklog.jsonl"),
                    args.workdir, args.out, args.input_dir)
    print(f"[assemble] {args.cmd} → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
