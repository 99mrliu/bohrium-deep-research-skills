#!/usr/bin/env python3
"""parse_case.py — 读取 /input/case.json 与题录材料，生成统一中间产物。

输出（写入 --work，默认 /app/work）：
  - case_summary.json : {case_id, research_question, output_contract(字段名列表),
                         material_files, record_count, warnings}
  - records.json      : 规范化题录列表 [{record_id, title, abstract, year,
                         authors, journal, publication_type, source_db}, ...]

支持材料格式：.jsonl / .json(数组) / .csv / .ris（最小字段集）。
退出码：0 正常；2 有警告（如缺合同/缺年份）；3 致命（case.json 缺失或材料为零）。
"""
import argparse
import csv
import sys
from pathlib import Path

from common_lib import dump_json, eprint, load_json, norm_text

CONTRACT_KEYS = ("output_contract", "contract", "output_fields", "deliverable_fields")


def contract_fields(raw):
    """output_contract 可能是字段名列表或 {字段: 说明} 字典，统一为字段名列表。"""
    if isinstance(raw, dict):
        return list(raw.keys())
    if isinstance(raw, list):
        out = []
        for item in raw:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                out.extend(item.keys())
        return out
    return []


def norm_record(rec, idx, source_file, warnings):
    """把一条任意来源的题录映射到统一字段；字段缺失记 warning 并置 None/空。"""
    rid = rec.get("record_id") or rec.get("id") or rec.get("pmid") or rec.get("doi")
    if not rid:
        rid = f"R{idx:03d}"
    title = rec.get("title") or rec.get("ti") or ""
    abstract = rec.get("abstract") or rec.get("ab") or ""
    if not norm_text(title) and not norm_text(abstract):
        warnings.append(f"{source_file}: 记录 {rid} 题名与摘要均为空，评分将接近 0")
    year = rec.get("year") or rec.get("py") or rec.get("date")
    if year is not None:
        digits = "".join(ch for ch in str(year) if ch.isdigit())
        year = int(digits[:4]) if len(digits) >= 4 else None
    if year is None:
        warnings.append(f"{source_file}: 记录 {rid} 缺年份，时效分按 unknown_year_factor 折算")
    authors = rec.get("authors") or rec.get("au") or []
    if isinstance(authors, str):
        authors = [a.strip() for a in authors.split(";") if a.strip()]
    ptype = rec.get("publication_type") or rec.get("pt") or rec.get("type") or "unknown"
    return {
        "record_id": str(rid),
        "title": title,
        "abstract": abstract,
        "year": year,
        "authors": authors,
        "journal": rec.get("journal") or rec.get("jo") or rec.get("source") or "",
        "publication_type": str(ptype),
        "source_db": rec.get("source_db") or rec.get("db") or source_file,
    }


def parse_ris(text):
    """最小 RIS 解析：TY/TI/T1/AB/N2/PY/Y1/JO/JF/AU/ID。"""
    records, cur = [], {}
    for line in text.splitlines():
        if len(line) >= 6 and line[2:6] == "  - ":
            tag, val = line[:2].strip(), line[6:].strip()
            if tag == "TY":
                cur = {"publication_type": val}
            elif tag in ("TI", "T1"):
                cur["title"] = val
            elif tag in ("AB", "N2"):
                cur["abstract"] = val
            elif tag in ("PY", "Y1"):
                cur["year"] = val
            elif tag in ("JO", "JF"):
                cur["journal"] = val
            elif tag == "AU":
                cur.setdefault("authors", []).append(val)
            elif tag == "ID":
                cur["record_id"] = val
            elif tag == "ER":
                records.append(cur)
                cur = {}
    if cur:
        records.append(cur)
    return records


def load_material(path, warnings):
    """按扩展名解析一个材料文件，返回原始记录列表。"""
    p = Path(path)
    ext = p.suffix.lower()
    text = p.read_text(encoding="utf-8")
    if ext == ".jsonl":
        return [json_loads_line(l, p, warnings) for l in text.splitlines() if l.strip()]
    if ext == ".json":
        data = load_json(p)
        if isinstance(data, dict) and isinstance(data.get("records"), list):
            return data["records"]
        if isinstance(data, list):
            return data
        warnings.append(f"{p.name}: JSON 材料既不是数组也无 records 键，已跳过")
        return []
    if ext == ".csv":
        rows = list(csv.DictReader(text.splitlines()))
        return rows
    if ext == ".ris":
        return parse_ris(text)
    warnings.append(f"{p.name}: 不支持的扩展名 {ext}，已跳过")
    return []


def json_loads_line(line, path, warnings):
    import json as _json
    try:
        return _json.loads(line)
    except Exception:
        warnings.append(f"{path.name}: 有一行 JSONL 解析失败，已跳过")
        return {}


def main(argv=None):
    ap = argparse.ArgumentParser(description="解析 case.json 与题录材料")
    ap.add_argument("--input-dir", default="/input")
    ap.add_argument("--work", default="/app/work")
    args = ap.parse_args(argv)

    input_dir, work = Path(args.input_dir), Path(args.work)
    warnings = []
    case_path = input_dir / "case.json"
    if not case_path.exists():
        eprint(f"[parse_case] 致命: 未找到 {case_path}")
        return 3

    case = load_json(case_path)
    contract = None
    for key in CONTRACT_KEYS:
        if key in case:
            contract = case[key]
            break
    fields = contract_fields(contract)
    if not fields:
        warnings.append("case.json 中未找到 output_contract，result.json 将仅含通用字段")

    materials = case.get("materials") or []
    records, material_files = [], []
    idx = 0
    for rel in materials:
        fpath = input_dir / rel
        if not fpath.exists():
            warnings.append(f"材料文件缺失: {rel}")
            continue
        material_files.append(rel)
        for raw in load_material(fpath, warnings):
            if not raw:
                continue
            idx += 1
            records.append(norm_record(raw, idx, Path(rel).name, warnings))

    if not records:
        eprint("[parse_case] 致命: 题录材料为零，无法排序")
        return 3

    summary = {
        "case_id": case.get("case_id"),
        "research_question": case.get("research_question"),
        "output_contract": fields,
        "material_files": material_files,
        "record_count": len(records),
        "warnings": warnings,
    }
    dump_json(work / "case_summary.json", summary)
    dump_json(work / "records.json", records)
    print(f"[parse_case] case_id={summary['case_id']} 记录数={len(records)} "
          f"合同字段数={len(fields)} 警告数={len(warnings)}")
    return 2 if warnings else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # 顶层兜底：任何未预期异常都不静默
        eprint(f"[parse_case] 未预期异常: {exc!r}")
        sys.exit(3)
