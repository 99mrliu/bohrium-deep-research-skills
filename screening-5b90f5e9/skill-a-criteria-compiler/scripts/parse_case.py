#!/usr/bin/env python3
"""parse_case.py — 盘点 /input 案例材料，生成 case_summary.json（步骤 0，脚本环节）。

读取 case.json 与 task.md，按扩展名+内容嗅探盘点材料文件
（json/jsonl/csv/ris/txt），抽取 case_id、research_question、criteria 文本片段、
output_contract 字段列表、records 文件清单，写 <work>/case_summary.json。

退出码：0=通过；2=输入不足（case.json 缺失/损坏），诚实降级；3=校验失败。
幂等：同参数重跑覆盖同名产物。
"""
import argparse
import json
import re
import sys
from pathlib import Path

CRITERIA_KW = re.compile(r"纳入|排除|inclusion|exclusion|eligib|criteria|标准", re.I)


def sniff_type(path: Path) -> str:
    """按扩展名优先、内容兜底嗅探材料类型。"""
    ext = path.suffix.lower()
    if ext in (".jsonl", ".ndjson"):
        return "jsonl"
    if ext == ".json":
        return "json"
    if ext == ".csv":
        return "csv"
    if ext == ".ris":
        return "ris"
    if ext in (".txt", ".md"):
        return "txt"
    try:
        head = path.read_bytes()[:8192].decode("utf-8", errors="replace").lstrip()
    except Exception:
        return "unknown"
    if head.startswith("{") or head.startswith("["):
        return "json"
    if "TY  -" in head:
        return "ris"
    lines = [l for l in head.splitlines() if l.strip()]
    if lines and all(l.strip().startswith("{") for l in lines[:3]):
        return "jsonl"
    if lines and "," in lines[0]:
        return "csv"
    return "txt"


def contract_fields(oc):
    """把 output_contract 统一为字段名列表（支持 dict / list[str] / list[dict]）。"""
    if isinstance(oc, dict):
        return list(oc.keys())
    if isinstance(oc, list):
        out = []
        for it in oc:
            if isinstance(it, str):
                out.append(it)
            elif isinstance(it, dict):
                name = it.get("field") or it.get("name") or it.get("key")
                out.append(name if isinstance(name, str) else json.dumps(it, ensure_ascii=False))
        return [x for x in out if x]
    return []


def extract_criteria_fragments(task_text: str, max_fragments: int = 12):
    """从 task.md 中粗提取含纳排关键词的文本块（供模型编译标准时参考）。"""
    fragments = []
    lines = task_text.splitlines()
    i = 0
    while i < len(lines) and len(fragments) < max_fragments:
        line = lines[i]
        if CRITERIA_KW.search(line):
            block = [line.strip()]
            j = i + 1
            while j < len(lines) and len(block) < 10 and lines[j].strip():
                block.append(lines[j].strip())
                j += 1
            fragments.append("\n".join(block))
            i = j
        else:
            i += 1
    return fragments


def main(argv=None):
    ap = argparse.ArgumentParser(description="盘点 /input 案例材料，写 case_summary.json")
    ap.add_argument("--input-dir", default="/input", help="输入目录（默认 /input）")
    ap.add_argument("--work", default="/app/work", help="工作目录（默认 /app/work）")
    args = ap.parse_args(argv)

    input_dir = Path(args.input_dir)
    work = Path(args.work)
    try:
        work.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"[parse_case] 无法创建工作目录 {work}: {e}", file=sys.stderr)
        return 2

    case_path = input_dir / "case.json"
    task_path = input_dir / "task.md"
    if not case_path.exists():
        print(f"[parse_case] 缺少 {case_path}，输入不足，诚实降级。", file=sys.stderr)
        return 2
    try:
        case = json.loads(case_path.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        print(f"[parse_case] case.json 解析失败: {e}", file=sys.stderr)
        return 2

    task_text = ""
    if task_path.exists():
        task_text = task_path.read_text(encoding="utf-8", errors="replace")

    case_id = case.get("case_id") or case.get("id") or "unknown_case"
    rq = case.get("research_question") or case.get("question") or ""
    rq_source = "case.json"
    if not rq and task_text:
        for ln in task_text.splitlines():
            if ln.strip():
                rq = ln.strip().lstrip("#").strip()
                rq_source = "task.md(first_line)"
                break

    criteria_text = case.get("criteria_text") or case.get("criteria") or ""
    if not isinstance(criteria_text, str):
        criteria_text = json.dumps(criteria_text, ensure_ascii=False)
    criteria_fragments = []
    if criteria_text.strip():
        criteria_fragments.append(criteria_text.strip())
    criteria_fragments.extend(extract_criteria_fragments(task_text))
    criteria_source = "case.json+task.md" if criteria_text.strip() else (
        "task.md" if criteria_fragments else "none")

    oc_fields = contract_fields(case.get("output_contract"))

    records_files = []
    if input_dir.exists():
        for p in sorted(input_dir.iterdir()):
            if not p.is_file():
                continue
            if p.name in ("case.json", "task.md"):
                continue
            records_files.append({
                "path": str(p),
                "name": p.name,
                "sniffed_type": sniff_type(p),
                "size_bytes": p.stat().st_size,
            })

    summary = {
        "case_id": case_id,
        "research_question": {"value": rq, "source": rq_source if rq else "none"},
        "criteria_fragments": criteria_fragments,
        "criteria_source": criteria_source,
        "output_contract_fields": oc_fields,
        "records_files": records_files,
        "materials_count": len(records_files),
        "notes": [] if records_files else ["materials_zero: 未发现任何材料文件，后续 result status 应为 failed"],
        "generated_by": "parse_case.py",
        "stage": "intake",
    }
    out = work / "case_summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[parse_case] case_id={case_id} materials={len(records_files)} "
          f"contract_fields={len(oc_fields)} -> {out}")
    if not records_files:
        print("[parse_case] 警告：材料文件为零（materials_zero）。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # 兜底：绝不 traceback-crash
        print(f"[parse_case] 未预期错误（诚实降级）: {e}", file=sys.stderr)
        sys.exit(2)
