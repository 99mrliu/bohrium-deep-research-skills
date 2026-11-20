#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""load_records.py — 导入题录记录（JSON/JSONL/CSV/RIS）并旁路保存冲突标注 fixture。

用法:
    python3 load_records.py [--input-dir /input] [--work /app/work]

输出:
    <work>/records.jsonl
      每行 {record_id, title, abstract, authors[], year, doi, source_file, field_status[]}
    <work>/external_annotations.json   (仅 dual_fixture 模式)
      {_fixture: true, notice, source_files[], raw: {文件名: 原始内容}}
      —— fixture 内容原样保留，明确标注为输入 fixture 而非事实/金标准。

说明:
    - 跳过 case.json / task.md 以及 case_summary.json 中列出的 fixture 文件；
    - record_id 优先取记录自带 id/record_id/pmid，否则按文件排序顺序生成 R0001...；
    - field_status 记录缺失字段（如 abstract_missing），供 D3 分类与人工确认门使用。

退出码: 0=成功, 2=用法或IO错误, 3=校验失败
"""
import argparse
import csv
import io
import json
import sys
import traceback
from pathlib import Path

SKIP_NAMES = {"case.json", "task.md"}
RECORD_LIST_KEYS = ("records", "studies", "articles", "references", "citations", "items")


def eprint(*a):
    print(*a, file=sys.stderr)


def first_key(d, keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    low = {str(k).lower(): v for k, v in d.items()}
    for k in keys:
        if k.lower() in low and low[k.lower()] not in (None, ""):
            return low[k.lower()]
    return None


def norm_record(raw, fallback_id, source_file):
    title = first_key(raw, ("title", "TI", "t")) or ""
    abstract = first_key(raw, ("abstract", "AB", "abstract_note")) or ""
    authors = first_key(raw, ("authors", "AU", "author")) or []
    if isinstance(authors, str):
        authors = [a.strip() for a in authors.replace("；", ";").split(";") if a.strip()]
    year = first_key(raw, ("year", "PY", "publication_year", "date")) or ""
    doi = first_key(raw, ("doi", "DO", "DOI")) or ""
    rid = first_key(raw, ("record_id", "id", "pmid", "uid")) or fallback_id
    field_status = []
    if not str(title).strip():
        field_status.append("title_missing")
    if not str(abstract).strip():
        field_status.append("abstract_missing")
    return {
        "record_id": str(rid),
        "title": str(title).strip(),
        "abstract": str(abstract).strip(),
        "authors": authors if isinstance(authors, list) else [str(authors)],
        "year": str(year).strip(),
        "doi": str(doi).strip(),
        "source_file": source_file,
        "field_status": field_status,
    }


def parse_json_records(text):
    data = json.loads(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in RECORD_LIST_KEYS:
            if isinstance(data.get(k), list):
                return data[k]
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
        return [data]
    return []


def parse_jsonl(text):
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def parse_csv_records(text):
    reader = csv.DictReader(io.StringIO(text))
    return [dict(r) for r in reader]


def parse_ris(text):
    records, cur = [], {}

    def flush():
        nonlocal cur
        if cur:
            rec = {
                "title": cur.get("TI", cur.get("T1", "")),
                "abstract": cur.get("AB", cur.get("N2", "")),
                "authors": cur.get("AU", []),
                "year": cur.get("PY", cur.get("Y1", ""))[:4] if cur.get("PY") or cur.get("Y1") else "",
                "doi": cur.get("DO", ""),
            }
            records.append(rec)
        cur = {}

    last_tag = None
    for line in text.splitlines():
        if len(line) >= 6 and line[2:6] == "  - ":
            tag, val = line[:2].strip(), line[6:].strip()
            if tag == "TY":
                flush()
            elif tag == "ER":
                flush()
                last_tag = None
                continue
            if tag == "AU":
                cur.setdefault("AU", []).append(val)
            else:
                cur[tag] = val
            last_tag = tag
        elif last_tag and last_tag != "AU" and line.strip():
            cur[last_tag] = cur.get(last_tag, "") + " " + line.strip()
    flush()
    return records


def main():
    ap = argparse.ArgumentParser(description="导入题录记录并旁路保存冲突标注 fixture")
    ap.add_argument("--input-dir", default="/input")
    ap.add_argument("--work", default="/app/work")
    args = ap.parse_args()

    in_dir = Path(args.input_dir)
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)

    summary_path = work / "case_summary.json"
    if not summary_path.exists():
        eprint(f"[load_records] 缺少 {summary_path}，请先运行 parse_case.py")
        return 2
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    fixture_names = {f["name"] for f in summary.get("fixtures", [])}

    records, seq = [], 0
    for p in sorted(in_dir.iterdir()):
        if not p.is_file() or p.name in SKIP_NAMES or p.name in fixture_names:
            continue
        ext = p.suffix.lower()
        if ext not in (".json", ".jsonl", ".csv", ".ris"):
            eprint(f"[load_records] 跳过不支持的文件类型: {p.name}")
            continue
        text = p.read_text(encoding="utf-8")
        try:
            if ext == ".json":
                raws = parse_json_records(text)
            elif ext == ".jsonl":
                raws = parse_jsonl(text)
            elif ext == ".csv":
                raws = parse_csv_records(text)
            else:
                raws = parse_ris(text)
        except Exception as ex:
            eprint(f"[load_records] 解析失败 {p.name}: {ex}（跳过该文件）")
            continue
        for raw in raws:
            if not isinstance(raw, dict):
                continue
            seq += 1
            records.append(norm_record(raw, f"R{seq:04d}", p.name))

    if not records:
        eprint("[load_records] 未导入任何记录")
        return 2

    out = work / "records.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[load_records] 导入记录 {len(records)} 条 -> {out}")

    if fixture_names:
        raw = {}
        for name in sorted(fixture_names):
            p = in_dir / name
            text = p.read_text(encoding="utf-8")
            try:
                raw[name] = json.loads(text)
            except Exception:
                raw[name] = {"_unparsed_text": text}
        ext_out = {
            "_fixture": True,
            "notice": ("本文件为案例自带的冲突标注 fixture（输入材料），"
                       "原样保留，不是事实、不是金标准、不得作为人工复核结论。"),
            "source_files": sorted(fixture_names),
            "raw": raw,
        }
        ext_path = work / "external_annotations.json"
        ext_path.write_text(json.dumps(ext_out, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"[load_records] fixture 原样保存 -> {ext_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        eprint("[load_records] 未捕获异常:")
        traceback.print_exc()
        sys.exit(2)
