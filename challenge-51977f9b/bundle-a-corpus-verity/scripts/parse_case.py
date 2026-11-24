#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_case.py — 防御式案例解析（slr-corpus-verity）

读取 /input/case.json 与 /input/task.md，产出 case_summary.json：
  case_id、output_contract（原样复制；缺省置 CONTRACT.md 通用默认字段列表）、
  research_question（来自 task.md 文本提取时标 needs_confirmation=true）、
  materials（文件名+推断用途）、records_path 候选。

文件缺失、JSON 损坏、字段缺省分别处理；材料不足时诚实降级（exit 2），
但仍尽可能写出降级版 case_summary.json，供 scaffold_result.py 保底。

退出码：0=通过；2=输入/材料不足（诚实降级）；3=输出不可写等校验失败
"""
import argparse
import json
import os
import re
import sys

# CONTRACT.md 规定的通用默认输出合同字段
DEFAULT_OUTPUT_CONTRACT = [
    "case_id", "skill_name", "status", "product", "evidence_matrix",
    "sources", "uncertainty", "change_records", "counts", "checks",
]

RECORD_NAME_HINTS = ("record", "reference", "biblio", "citation", "corpus",
                     "题录", "文献", "检索")


def infer_purpose(fname):
    """按扩展名与文件名关键词推断材料用途。"""
    base = os.path.basename(fname)
    low = base.lower()
    ext = os.path.splitext(low)[1]
    is_recordish = any(h in low for h in RECORD_NAME_HINTS)
    if ext in (".json", ".jsonl"):
        return "候选题录清单（records 候选）" if is_recordish else "结构化数据（用途待确认）"
    if ext == ".pdf":
        return "全文文献 PDF（现场解析）"
    if ext in (".md", ".txt"):
        return "任务说明或文本材料"
    if ext in (".csv", ".tsv"):
        return "表格数据（可能为题录或提取表）"
    if ext in (".ris", ".bib", ".enw"):
        return "文献管理软件导出题录"
    return "未知类型材料（用途待确认）"


def is_records_candidate(fname):
    low = os.path.basename(fname).lower()
    ext = os.path.splitext(low)[1]
    if ext in (".ris", ".bib", ".jsonl"):
        return True
    if ext in (".json", ".csv", ".tsv"):
        return any(h in low for h in RECORD_NAME_HINTS)
    return False


def extract_research_question_from_task(task_text):
    """从 task.md 文本中提取研究问题（启发式，需人工确认）。"""
    if not task_text:
        return None
    # 优先：含"研究问题/research question"的行，取其冒号后内容或下一行
    lines = [ln.strip() for ln in task_text.splitlines()]
    for i, ln in enumerate(lines):
        m = re.match(r"^#*\s*(研究问题|research question|rq)\s*[:：]?\s*(.*)$",
                     ln, re.IGNORECASE)
        if m:
            if m.group(2).strip():
                return m.group(2).strip()
            for nxt in lines[i + 1:]:
                if nxt and not nxt.startswith("#"):
                    return nxt.lstrip("# ").strip()
    # 次选：第一个含问号的句子
    for ln in lines:
        if "？" in ln or "?" in ln:
            return ln.lstrip("# ").strip()
    # 兜底：第一段非标题文本
    for ln in lines:
        if ln and not ln.startswith("#"):
            return ln.strip()
    return None


def main():
    ap = argparse.ArgumentParser(
        description="防御式解析 case.json 与 task.md，产出 case_summary.json。"
                    "退出码：0=通过；2=材料不足（诚实降级）；3=校验失败。")
    ap.add_argument("--case", required=True, help="case.json 路径")
    ap.add_argument("--task", required=True, help="task.md 路径")
    ap.add_argument("--out", required=True, help="case_summary.json 输出路径")
    args = ap.parse_args()

    warnings = []
    case_data, case_ok = {}, False
    task_text, task_ok = None, False

    # ---- case.json：缺失 / 损坏 / 正常 分别处理
    if not os.path.isfile(args.case):
        warnings.append("R1: case.json 缺失：{}".format(args.case))
        print("[R1] case.json 缺失：{}".format(args.case), file=sys.stderr)
    else:
        try:
            with open(args.case, "r", encoding="utf-8") as fh:
                case_data = json.load(fh)
            if not isinstance(case_data, dict):
                warnings.append("R2: case.json 顶层不是对象，按空案例降级")
                print("[R2] case.json 顶层不是对象，按空案例降级", file=sys.stderr)
                case_data = {}
            else:
                case_ok = True
        except json.JSONDecodeError as e:
            warnings.append("R2: case.json 损坏（JSON 解析失败：第 {} 行 {}）"
                            .format(e.lineno, e.msg))
            print("[R2] case.json 损坏：{}".format(e), file=sys.stderr)
        except OSError as e:
            warnings.append("R1: case.json 不可读：{}".format(e))
            print("[R1] case.json 不可读：{}".format(e), file=sys.stderr)

    # ---- task.md：缺失不致命，但研究问题可信度下降
    if not os.path.isfile(args.task):
        warnings.append("R5: task.md 缺失：{}；研究问题无法从文本提取".format(args.task))
        print("[R5] task.md 缺失：{}".format(args.task), file=sys.stderr)
    else:
        try:
            with open(args.task, "r", encoding="utf-8") as fh:
                task_text = fh.read()
            task_ok = True
        except OSError as e:
            warnings.append("R5: task.md 不可读：{}".format(e))

    # ---- case_id
    case_id = case_data.get("case_id") or case_data.get("id") or "unknown-case"
    if case_id == "unknown-case":
        warnings.append("R6: case_id 缺省，置 unknown-case")

    # ---- output_contract：原样复制；缺省置默认字段列表
    oc = case_data.get("output_contract")
    if isinstance(oc, list) and oc and all(isinstance(x, str) for x in oc):
        output_contract = list(oc)
        output_contract_source = "case.json"
    elif isinstance(oc, dict) and oc:
        output_contract = list(oc.keys())
        output_contract_source = "case.json(键名)"
    else:
        output_contract = list(DEFAULT_OUTPUT_CONTRACT)
        output_contract_source = "default(CONTRACT.md 通用默认字段)"
        warnings.append("R6: output_contract 缺省，采用 CONTRACT.md 通用默认字段列表")

    # ---- research_question
    rq, rq_needs_confirm, rq_source = None, True, None
    for key in ("research_question", "question", "rq"):
        if case_data.get(key) and str(case_data[key]).strip():
            rq, rq_needs_confirm, rq_source = str(case_data[key]).strip(), False, "case.json"
            break
    if rq is None and task_ok:
        rq = extract_research_question_from_task(task_text)
        if rq:
            rq_needs_confirm, rq_source = True, "task.md(文本提取)"
            warnings.append("R6: 研究问题来自 task.md 文本提取，needs_confirmation=true")
    if rq is None:
        warnings.append("R6: 研究问题缺失（case.json 与 task.md 均未提供）")

    # ---- materials：case.json 声明 + 输入目录扫描，去重
    declared = case_data.get("materials") or []
    names = []
    if isinstance(declared, list):
        for m in declared:
            if isinstance(m, str):
                names.append(m)
            elif isinstance(m, dict):
                names.append(str(m.get("path") or m.get("file") or m.get("name") or ""))
    case_dir = os.path.dirname(os.path.abspath(args.case)) or "."
    try:
        for f in sorted(os.listdir(case_dir)):
            full = os.path.join(case_dir, f)
            if os.path.isfile(full) and f not in (os.path.basename(args.case),
                                                  os.path.basename(args.task)):
                names.append(f)
    except OSError:
        pass
    seen, materials = set(), []
    for n in names:
        if not n or n in seen:
            continue
        seen.add(n)
        materials.append({"file": n, "inferred_purpose": infer_purpose(n),
                          "exists_in_case_dir": os.path.isfile(os.path.join(case_dir, n))})
    if not materials:
        warnings.append("R6: 未发现任何材料文件")

    # ---- records_path 候选
    records_candidates = [m["file"] for m in materials if is_records_candidate(m["file"])]
    if not records_candidates:
        records_candidates = [m["file"] for m in materials
                              if os.path.splitext(m["file"].lower())[1]
                              in (".json", ".jsonl", ".csv", ".tsv")]
    if not records_candidates:
        warnings.append("R6: 未找到 records_path 候选（题录清单缺失风险）")

    summary = {
        "tool": "parse_case.py",
        "skill": "slr-corpus-verity",
        "case_id": case_id,
        "output_contract": output_contract,
        "output_contract_source": output_contract_source,
        "research_question": {
            "text": rq,
            "needs_confirmation": rq_needs_confirm,
            "source": rq_source,
        },
        "materials": materials,
        "records_path_candidates": records_candidates,
        "parse_status": {
            "case_json": "ok" if case_ok else "missing_or_broken",
            "task_md": "ok" if task_ok else "missing_or_unreadable",
        },
        "warnings": warnings,
    }

    try:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=2)
    except OSError as e:
        print("[R3] case_summary.json 不可写：{}（exit 3）".format(e), file=sys.stderr)
        return 3

    print("案例解析完成：case_id={} 材料 {} 项 records 候选 {} 项 警告 {} 条"
          .format(case_id, len(materials), len(records_candidates), len(warnings)))
    for w in warnings:
        print("  警告：{}".format(w))
    if not case_ok:
        print("诚实降级：case.json 不可用，已写出降级版 case_summary.json（exit 2）",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
