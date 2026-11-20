#!/usr/bin/env python3
"""parse_case.py - 读取 /input/case.json 与 /input/task.md，盘点材料文件，生成 case_summary.json。

用法:
    python3 parse_case.py [--input-dir /input] [--work /app/work]

退出码: 0=成功; 2=输入不足(诚实降级, 产出部分摘要); 3=校验/运行失败。
"""
import argparse
import json
import re
import sys
from pathlib import Path

RECORD_EXTS = {".json", ".jsonl", ".csv", ".ris", ".bib", ".txt"}
SPECIAL_NAMES = {"case.json", "task.md"}


def sniff_format(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in (".json", ".jsonl", ".csv", ".ris", ".bib"):
        return ext.lstrip(".")
    if ext == ".txt":
        try:
            head = path.read_text(encoding="utf-8", errors="replace")[:4000]
        except Exception:
            return "txt"
        if re.search(r"(?m)^TY  - ", head):
            return "ris"
        if re.search(r"@\w+\s*\{", head):
            return "bib"
        return "txt"
    return ext.lstrip(".") or "unknown"


def load_case(input_dir: Path, warnings):
    case_path = input_dir / "case.json"
    if not case_path.exists():
        warnings.append("case.json 不存在，使用降级摘要")
        return None
    try:
        return json.loads(case_path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        warnings.append(f"case.json 解析失败: {type(e).__name__}: {e}")
        return None


def extract_contract(case, task_text, warnings):
    """output_contract 可能是字段名列表或 {字段: 说明} 字典。"""
    raw = None
    if isinstance(case, dict):
        for key in ("output_contract", "contract", "required_output_fields"):
            if key in case:
                raw = case[key]
                break
    fields = []
    if isinstance(raw, list):
        fields = [str(x) for x in raw]
    elif isinstance(raw, dict):
        fields = [str(k) for k in raw.keys()]
    if not fields and task_text:
        # 兜底：从 task.md 中扫描形如 `- \`field_name\`` 的合同字段列表
        m = re.search(r"output[_ ]contract(.{0,3000})", task_text, re.IGNORECASE | re.DOTALL)
        if m:
            fields = re.findall(r"`([a-zA-Z_][a-zA-Z0-9_]*)`", m.group(1))
    if not fields:
        warnings.append("未找到 output_contract，将使用默认字段骨架")
    return fields


def main() -> int:
    ap = argparse.ArgumentParser(description="解析案例输入并盘点材料文件")
    ap.add_argument("--input-dir", default="/input", help="输入目录 (默认 /input)")
    ap.add_argument("--work", default="/app/work", help="工作目录 (默认 /app/work)")
    args = ap.parse_args()

    input_dir = Path(args.input_dir)
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    warnings = []
    degraded = False

    if not input_dir.exists():
        summary = {"case_id": "UNKNOWN", "research_question": None,
                   "output_contract": [], "material_files": [],
                   "warnings": [f"输入目录不存在: {input_dir}"]}
        (work / "case_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": False, "exit": 2, "reason": "input dir missing"}, ensure_ascii=False))
        return 2

    case = load_case(input_dir, warnings)
    if case is None:
        degraded = True
        case = {}

    task_text = ""
    task_path = input_dir / "task.md"
    if task_path.exists():
        try:
            task_text = task_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            warnings.append(f"task.md 读取失败: {type(e).__name__}: {e}")
    else:
        warnings.append("task.md 不存在")

    case_id = None
    for key in ("case_id", "id", "case"):
        if isinstance(case.get(key), str) and case.get(key).strip():
            case_id = case[key].strip()
            break
    if not case_id:
        case_id = "UNKNOWN"
        degraded = True
        warnings.append("case_id 缺失，记为 UNKNOWN")

    research_question = None
    for key in ("research_question", "question", "rq"):
        if isinstance(case.get(key), str) and case.get(key).strip():
            research_question = case[key].strip()
            break
    if not research_question:
        warnings.append("research_question 未在 case.json 中找到")
        degraded = True

    contract = extract_contract(case, task_text, warnings)

    material_files = []
    for p in sorted(input_dir.rglob("*")):
        if not p.is_file() or p.name in SPECIAL_NAMES:
            continue
        if p.suffix.lower() not in RECORD_EXTS:
            warnings.append(f"未识别扩展名，仍列入待导入: {p.name}")
        material_files.append({
            "path": str(p),
            "name": p.name,
            "sniffed_format": sniff_format(p),
            "size_bytes": p.stat().st_size,
        })
    if not material_files:
        degraded = True
        warnings.append("未发现任何材料文件")

    summary = {
        "case_id": case_id,
        "research_question": research_question,
        "output_contract": contract,
        "material_files": material_files,
        "task_md_excerpt": task_text[:2000] if task_text else None,
        "warnings": warnings,
    }
    out = work / "case_summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": not degraded, "case_id": case_id,
                      "materials": len(material_files), "warnings": len(warnings),
                      "summary": str(out)}, ensure_ascii=False))
    return 2 if degraded else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(3)
