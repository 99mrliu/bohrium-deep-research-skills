#!/usr/bin/env python3
"""normalize_records.py — 把各来源记录统一为 normalized.jsonl（步骤 3，脚本环节）。

每条记录：
{record_id（来源文件名+序号派生）, title, abstract, authors, year, doi, language,
 source_file, source_index, field_status（每字段 present/missing/unknown/not_provided）,
 encoding_notes, html_stripped}

容忍：HTML 标签、键名大小写与别名变体、authors list/dict/str 变体、json 数组或
{"records": [...]} 包裹、编码问题（非法字符替换并留痕）。

退出码：0=通过；2=输入不足；3=校验失败。幂等：重跑覆盖同名产物。
"""
import argparse
import csv
import html as html_mod
import json
import re
import sys
from pathlib import Path

FIELDS = ["title", "abstract", "authors", "year", "doi", "language"]
ALIASES = {
    "title": ["title", "ti", "t1", "headline", "题名", "标题"],
    "abstract": ["abstract", "ab", "n2", "summary", "description", "摘要"],
    "authors": ["authors", "author", "au", "creators", "作者"],
    "year": ["year", "py", "y1", "date", "publication_year", "published", "年份"],
    "doi": ["doi", "do", "ur_doi"],
    "language": ["language", "lang", "la", "语言"],
}
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
YEAR_RE = re.compile(r"(19|20)\d{2}")


def clean_text(s):
    """去 HTML 标签、反转义实体、压缩空白。"""
    if s is None:
        return None, False
    if not isinstance(s, str):
        s = str(s)
    had_html = bool(TAG_RE.search(s))
    s = TAG_RE.sub(" ", s)
    s = html_mod.unescape(s)
    s = WS_RE.sub(" ", s).strip()
    return s, had_html


def canon_key(k):
    return str(k).strip().lower()


def map_record(raw):
    """把任意键名变体的 dict 映射到规范字段；返回 (mapped, present_keys)。"""
    mapped = {f: None for f in FIELDS}
    present = set()
    if not isinstance(raw, dict):
        return mapped, present
    lut = {}
    for f, names in ALIASES.items():
        for n in names:
            lut[n] = f
    for k, v in raw.items():
        f = lut.get(canon_key(k))
        if f is None or v is None:
            continue
        present.add(f)
        if mapped[f] is None or mapped[f] in ("", []):
            mapped[f] = v
    return mapped, present


def norm_authors(v):
    if v is None:
        return []
    if isinstance(v, str):
        parts = re.split(r";|\band\b", v)
        return [p.strip() for p in parts if p.strip()]
    if isinstance(v, list):
        out = []
        for a in v:
            if isinstance(a, dict):
                name = a.get("name") or " ".join(
                    str(a.get(x, "")) for x in ("given", "family", "last", "first")).strip()
                out.append(name if name else json.dumps(a, ensure_ascii=False))
            else:
                out.append(str(a))
        return [x for x in out if x]
    return [str(v)]


def norm_year(v):
    if v is None:
        return None
    m = YEAR_RE.search(str(v))
    return int(m.group(0)) if m else None


def parse_ris(text):
    """极简 RIS 解析：按 TY  - / ER  - 分块。"""
    records, cur = [], {}
    for line in text.splitlines():
        m = re.match(r"^([A-Z0-9]{2})  - (.*)$", line.rstrip("\n"))
        if not m:
            continue
        tag, val = m.group(1), m.group(2)
        if tag == "TY":
            cur = {}
        elif tag == "ER":
            if cur:
                records.append(cur)
            cur = {}
        elif tag in ("TI", "T1"):
            cur["title"] = val
        elif tag in ("AB", "N2"):
            cur["abstract"] = (cur.get("abstract", "") + " " + val).strip()
        elif tag in ("AU", "A1"):
            cur.setdefault("authors", []).append(val)
        elif tag in ("PY", "Y1"):
            cur["year"] = val
        elif tag == "DO":
            cur["doi"] = val
        elif tag == "LA":
            cur["language"] = val
    if cur:
        records.append(cur)
    return records


def read_text(path):
    """读文件，utf-8 优先，失败替换并留痕。"""
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8"), ""
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace"), "encoding_repair:非法字节已用�替换"


def load_records(path, sniffed):
    """按嗅探类型把文件解析为 raw dict 列表 + 警告列表。"""
    text, enc_note = read_text(path)
    warnings = [enc_note] if enc_note else []
    raw_records = []
    try:
        if sniffed == "jsonl":
            for i, line in enumerate(text.splitlines()):
                if not line.strip():
                    continue
                try:
                    raw_records.append(json.loads(line))
                except json.JSONDecodeError as e:
                    warnings.append(f"line {i + 1} json 解析失败已跳过: {e}")
        elif sniffed == "json":
            data = json.loads(text)
            if isinstance(data, list):
                raw_records = data
            elif isinstance(data, dict):
                for key in ("records", "items", "results", "data"):
                    if isinstance(data.get(key), list):
                        raw_records = data[key]
                        break
                else:
                    raw_records = [data]
        elif sniffed == "csv":
            raw_records = list(csv.DictReader(text.splitlines()))
        elif sniffed == "ris":
            raw_records = parse_ris(text)
        else:  # txt：整篇作为一条记录，首行为题名
            non_empty = [l.strip() for l in text.splitlines() if l.strip()]
            first = non_empty[0] if non_empty else ""
            raw_records = [{"title": first, "abstract": " ".join(non_empty[1:])}]
    except Exception as e:
        warnings.append(f"文件解析异常（已尽量恢复）: {e}")
    return raw_records, warnings


def main(argv=None):
    ap = argparse.ArgumentParser(description="统一各来源记录为 normalized.jsonl")
    ap.add_argument("--work", default="/app/work", help="工作目录（默认 /app/work）")
    ap.add_argument("--files", nargs="*", default=None,
                    help="显式指定记录文件（默认取 case_summary.records_files）")
    args = ap.parse_args(argv)
    work = Path(args.work)
    summary_path = work / "case_summary.json"
    if not summary_path.exists():
        print(f"[normalize_records] 缺少 {summary_path}，请先运行 parse_case.py。", file=sys.stderr)
        return 2
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[normalize_records] case_summary 解析失败: {e}", file=sys.stderr)
        return 2

    if args.files:
        files = [{"path": f, "name": Path(f).name, "sniffed_type": "jsonl"
                  if f.endswith("jsonl") else "txt"} for f in args.files]
    else:
        files = summary.get("records_files") or []
    if not files:
        print("[normalize_records] 无材料文件，输入不足，诚实降级。", file=sys.stderr)
        return 2

    out_path = work / "normalized.jsonl"
    per_file = []
    parse_warnings = []
    n_total = 0
    with out_path.open("w", encoding="utf-8") as out:
        for finfo in files:
            p = Path(finfo["path"])
            if not p.exists():
                parse_warnings.append(f"{finfo['name']}: 文件不存在，已跳过")
                continue
            raw_records, warns = load_records(p, finfo.get("sniffed_type", "txt"))
            parse_warnings.extend(f"{finfo['name']}: {w}" for w in warns)
            mapped_list, seen = [], set()
            for raw in raw_records:
                mapped, present = map_record(raw)
                mapped_list.append((mapped, present))
                seen |= present
            count = 0
            for idx, (mapped, present) in enumerate(mapped_list, start=1):
                title, html_t = clean_text(mapped["title"])
                abstract, html_a = clean_text(mapped["abstract"])
                authors = norm_authors(mapped["authors"])
                year = norm_year(mapped["year"])
                doi, _ = clean_text(mapped["doi"])
                language, _ = clean_text(mapped["language"])
                values = {"title": title, "abstract": abstract, "authors": authors,
                          "year": year, "doi": doi, "language": language}
                field_status = {}
                for f in FIELDS:
                    v = values[f]
                    empty = v is None or v == "" or v == []
                    if f not in seen:
                        field_status[f] = "not_provided"
                    elif f not in present:
                        field_status[f] = "missing"
                    elif empty:
                        field_status[f] = "unknown"
                    else:
                        field_status[f] = "present"
                rec = {
                    "record_id": f"{p.stem}-{idx:04d}",
                    "title": title,
                    "abstract": abstract,
                    "authors": authors,
                    "year": year,
                    "doi": doi,
                    "language": language,
                    "source_file": finfo["name"],
                    "source_index": idx,
                    "field_status": field_status,
                    "encoding_notes": "; ".join(warns) if warns else "",
                    "html_stripped": bool(html_t or html_a),
                }
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                count += 1
            n_total += count
            per_file.append({"file": finfo["name"], "type": finfo.get("sniffed_type"),
                             "records": count})

    nsummary = {
        "identified": n_total,
        "per_file": per_file,
        "parse_warnings": parse_warnings,
        "output": str(out_path),
        "generated_by": "normalize_records.py",
        "stage": "normalize",
    }
    (work / "normalize_summary.json").write_text(
        json.dumps(nsummary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[normalize_records] identified={n_total} files={len(per_file)} -> {out_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print(f"[normalize_records] 未预期错误（诚实降级）: {e}", file=sys.stderr)
        sys.exit(2)
