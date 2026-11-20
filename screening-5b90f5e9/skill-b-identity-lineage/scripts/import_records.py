#!/usr/bin/env python3
"""import_records.py - 多格式导入嗅探：JSON 数组 / JSONL / CSV / RIS / BibTeX。

统一写出 /app/work/records.jsonl，每行:
{record_id, title, abstract, authors[], year, doi, pmid, arxiv, venue,
 source_file, source_index, field_status, parse_warnings}

field_status 三级语义:
  ok            字段有值
  missing       来源给了该字段但内容为空
  not_provided  来源本来没给该字段
  unknown       字段有内容但解析不出（如年份无 4 位数字）

解析失败降级留痕不静默: 文件级失败记入 warnings 并继续；全部失败 exit 2。

退出码: 0=全部成功; 2=部分降级; 3=没有导入任何记录/运行失败。
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

CANON_FIELDS = ["title", "abstract", "authors", "year", "doi", "pmid", "arxiv", "venue"]

KEY_MAP = {
    "title": ["title", "ti", "paper_title", "t1"],
    "abstract": ["abstract", "ab", "summary", "description", "n2"],
    "authors": ["authors", "author", "au", "creators"],
    "year": ["year", "py", "publication_year", "date", "y1"],
    "doi": ["doi", "do"],
    "pmid": ["pmid", "pubmed_id"],
    "arxiv": ["arxiv", "arxiv_id", "eprint"],
    "venue": ["venue", "journal", "jo", "jf", "source", "publication", "booktitle", "t2"],
}


def year4(v):
    if v is None:
        return None
    m = re.search(r"(19|20)\d{2}", str(v))
    return m.group(0) if m else None


def split_authors(v):
    if v is None:
        return []
    if isinstance(v, list):
        return [str(a).strip() for a in v if str(a).strip()]
    s = str(v).strip()
    if not s:
        return []
    if ";" in s:
        return [a.strip() for a in s.split(";") if a.strip()]
    if " and " in s:
        return [a.strip() for a in s.split(" and ") if a.strip()]
    if "|" in s:
        return [a.strip() for a in s.split("|") if a.strip()]
    return [s]


def lower_keys(d):
    return {str(k).strip().lower(): v for k, v in d.items()}


def normalize_record(raw: dict, source_file: str, idx: int):
    """把任意来源的字段映射为统一记录，并标注 field_status。"""
    lk = lower_keys(raw) if isinstance(raw, dict) else {}
    rec, status, warns = {}, {}, []
    provided = set()  # 来源实际给出的 canonical 字段

    def find_value(field):
        for alias in KEY_MAP[field]:
            if alias in lk:
                provided.add(field)
                return lk[alias]
        return None

    rec["title"] = (find_value("title") or "")
    rec["title"] = str(rec["title"]).strip() or None
    rec["abstract"] = (find_value("abstract") or "")
    rec["abstract"] = str(rec["abstract"]).strip() or None
    rec["authors"] = split_authors(find_value("authors"))
    raw_year = find_value("year")
    rec["year"] = year4(raw_year)
    if raw_year not in (None, "") and rec["year"] is None:
        warns.append(f"year 解析失败: {raw_year!r}")
    for f in ("doi", "pmid", "arxiv", "venue"):
        v = find_value(f)
        v = str(v).strip() if v is not None else None
        rec[f] = v or None

    for f in CANON_FIELDS:
        val = rec.get(f)
        has_val = bool(val) if f != "authors" else bool(val)
        if has_val:
            status[f] = "ok"
        elif f in provided:
            status[f] = "missing"
        elif f == "year" and raw_year not in (None, "") and val is None:
            status[f] = "unknown"
        else:
            status[f] = "not_provided"

    rec.update({
        "record_id": f"{Path(source_file).stem}-{idx:03d}",
        "source_file": source_file,
        "source_index": idx,
        "field_status": status,
        "parse_warnings": warns,
    })
    return rec


# ---------- 各格式解析器 ----------

def parse_json_file(text):
    data = json.loads(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("records", "results", "items", "entries", "data"):
            if isinstance(data.get(key), list):
                return data[key]
        return [data]
    raise ValueError("JSON 顶层既不是数组也不是对象")


def parse_jsonl_file(text):
    rows = []
    for ln, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            rows.append({"_parse_error": f"line {ln}: {e}"})
    return rows


def parse_csv_file(text):
    reader = csv.DictReader(text.splitlines())
    return [dict(r) for r in reader]


def parse_ris_file(text):
    records, cur = [], None
    for line in text.splitlines():
        m = re.match(r"^([A-Z0-9]{2})  - (.*)$", line.rstrip("\n"))
        if not m:
            if cur is not None and line.strip() and cur.get("_last"):
                cur[cur["_last"]] = str(cur.get(cur["_last"], "")) + " " + line.strip()
            continue
        tag, val = m.group(1), m.group(2).strip()
        if tag == "TY":
            cur = {"_last": None}
        elif tag == "ER":
            if cur is not None:
                cur.pop("_last", None)
                records.append(cur)
            cur = None
        elif cur is not None:
            if tag == "AU":
                cur.setdefault("AU", []).append(val)
                cur["_last"] = None
            else:
                cur[tag] = val
                cur["_last"] = tag
    if cur is not None:
        cur.pop("_last", None)
        records.append(cur)
    mapped = []
    for r in records:
        out = {}
        for k, v in r.items():
            kl = k.lower()
            if kl == "au":
                out["au"] = v
            elif kl == "pmid":
                out["pmid"] = v
            elif kl == "ar":
                out["arxiv"] = v
            else:
                out[kl] = v
        mapped.append(out)
    return mapped


def _bib_entries(text):
    """按花括号配平切分 BibTeX 条目。"""
    entries = []
    for m in re.finditer(r"@(\w+)\s*\{", text):
        entry_type = m.group(1).lower()
        depth, i = 1, m.end()
        start = i
        while i < len(text) and depth > 0:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        if depth == 0:
            entries.append((entry_type, text[start:i - 1]))
    return entries


def _bib_fields(body):
    """解析条目体: key, field = {value} / "value" / bare。"""
    fields = {}
    # key 到第一个逗号
    m = re.match(r"\s*([^,]+),", body, re.DOTALL)
    if not m:
        return fields
    fields["_key"] = m.group(1).strip()
    rest = body[m.end():]
    pos = 0
    while pos < len(rest):
        fm = re.search(r"(\w+)\s*=\s*", rest[pos:])
        if not fm:
            break
        name = fm.group(1).lower()
        vstart = pos + fm.end()
        if vstart < len(rest) and rest[vstart] == "{":
            depth, i = 1, vstart + 1
            while i < len(rest) and depth > 0:
                if rest[i] == "{":
                    depth += 1
                elif rest[i] == "}":
                    depth -= 1
                i += 1
            fields[name] = rest[vstart + 1:i - 1].strip()
            pos = i
        elif vstart < len(rest) and rest[vstart] == '"':
            i = vstart + 1
            while i < len(rest) and rest[i] != '"':
                i += 1
            fields[name] = rest[vstart + 1:i].strip()
            pos = i + 1
        else:
            vm = re.match(r"[^,]+", rest[vstart:])
            if vm:
                fields[name] = vm.group(0).strip()
                pos = vstart + vm.end()
            else:
                break
    return fields


def parse_bib_file(text):
    records = []
    for entry_type, body in _bib_entries(text):
        f = _bib_fields(body)
        rec = {}
        if f.get("title"):
            rec["title"] = f["title"]
        if f.get("abstract"):
            rec["abstract"] = f["abstract"]
        if f.get("author"):
            rec["authors"] = [a.strip() for a in f["author"].split(" and ") if a.strip()]
        for k in ("year", "doi", "pmid"):
            if f.get(k):
                rec[k] = f[k]
        if f.get("eprint"):
            rec["arxiv"] = f["eprint"]
        venue = f.get("journal") or f.get("booktitle")
        if venue:
            rec["venue"] = venue
        if entry_type in ("misc", "unpublished") and not venue and f.get("eprint"):
            rec["venue"] = "arXiv"
        rec["_bibtype"] = entry_type
        records.append(rec)
    return records


PARSERS = {
    "json": parse_json_file,
    "jsonl": parse_jsonl_file,
    "csv": parse_csv_file,
    "ris": parse_ris_file,
    "bib": parse_bib_file,
}


def main() -> int:
    ap = argparse.ArgumentParser(description="多格式题录导入嗅探 → records.jsonl")
    ap.add_argument("--input-dir", default="/input", help="输入目录 (默认 /input)")
    ap.add_argument("--work", default="/app/work", help="工作目录 (默认 /app/work)")
    ap.add_argument("--files", nargs="*", default=None,
                    help="显式指定文件列表（缺省读 case_summary.json 的 material_files）")
    args = ap.parse_args()

    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    warnings = []

    files = args.files
    if files is None:
        summary_path = work / "case_summary.json"
        if summary_path.exists():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            files = [m["path"] for m in summary.get("material_files", [])]
        else:
            input_dir = Path(args.input_dir)
            files = [str(p) for p in sorted(input_dir.rglob("*"))
                     if p.is_file() and p.name not in ("case.json", "task.md")]
    if not files:
        (work / "records.jsonl").write_text("", encoding="utf-8")
        print(json.dumps({"ok": False, "exit": 2, "reason": "no material files"}, ensure_ascii=False))
        return 2

    all_records = []
    degraded = False
    for fpath in files:
        p = Path(fpath)
        if not p.exists():
            warnings.append(f"文件不存在: {fpath}")
            degraded = True
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        ext = p.suffix.lower().lstrip(".")
        fmt = ext
        if ext == "txt":
            if re.search(r"(?m)^TY  - ", text[:4000]):
                fmt = "ris"
            elif re.search(r"@\w+\s*\{", text[:4000]):
                fmt = "bib"
        parser = PARSERS.get(fmt)
        if parser is None:
            warnings.append(f"格式不支持，跳过: {fpath} (.{ext})")
            degraded = True
            continue
        try:
            raw_records = parser(text)
        except Exception as e:  # noqa: BLE001
            warnings.append(f"解析失败，跳过文件 {fpath}: {type(e).__name__}: {e}")
            degraded = True
            continue
        if not raw_records:
            warnings.append(f"文件无记录: {fpath}")
            degraded = True
            continue
        for i, raw in enumerate(raw_records, 1):
            if isinstance(raw, dict) and raw.get("_parse_error"):
                warnings.append(f"{fpath}#{i}: {raw['_parse_error']}")
                degraded = True
                continue
            rec = normalize_record(raw if isinstance(raw, dict) else {"title": str(raw)},
                                   str(p), i)
            all_records.append(rec)

    out = work / "records.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for rec in all_records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    (work / "import_warnings.json").write_text(
        json.dumps({"warnings": warnings}, ensure_ascii=False, indent=2), encoding="utf-8")

    if not all_records:
        print(json.dumps({"ok": False, "exit": 3, "reason": "no records imported",
                          "warnings": warnings}, ensure_ascii=False))
        return 3
    print(json.dumps({"ok": not degraded, "records": len(all_records),
                      "files": len(files), "warnings": len(warnings),
                      "out": str(out)}, ensure_ascii=False))
    return 2 if degraded else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(3)
