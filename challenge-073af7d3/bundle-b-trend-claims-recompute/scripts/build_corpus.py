#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_corpus.py -- 最小语料归一器（仅标准库、确定性、无网络）。

从 json / jsonl / csv / bib / ris / txt / md 抽取统一记录，写入 <work>/canon.jsonl：
    {"id","title","year","venue","abstract","source_file"}
并写出 <work>/corpus_meta.json（记录数、年份缺失比例、年份范围、告警）。

本脚本刻意保持简单：它是本 bundle 上游的“够用即可”归一器，深度在下游
（slice_stats / changepoint / claim_audit）。若已有其它语料审计技能产出的
canon.jsonl，可直接复用而无需运行本脚本。
"""
import argparse
import csv
import glob
import json
import os
import re
import sys

SUPPORTED_EXT = {".json", ".jsonl", ".csv", ".bib", ".ris", ".txt", ".md"}
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")

# 列名（小写）到规范字段的映射，用于 csv/json 记录的键归一
KEY_MAP = {
    "id": "id", "doi": "id", "key": "id", "uid": "id",
    "title": "title", "ti": "title",
    "year": "year", "pub_year": "year", "py": "year", "date": "year",
    "published": "year", "publication_year": "year",
    "venue": "venue", "journal": "venue", "journaltitle": "venue",
    "conference": "venue", "source": "venue", "booktitle": "venue", "jo": "venue",
    "abstract": "abstract", "summary": "abstract", "description": "abstract",
    "ab": "abstract",
}


def extract_year(value):
    """从任意值中提取 1900-2099 的 4 位年份；失败返回 None。"""
    if value is None:
        return None
    if isinstance(value, int) and 1900 <= value <= 2099:
        return value
    m = YEAR_RE.search(str(value))
    if m:
        y = int(m.group(1))
        if 1900 <= y <= 2099:
            return y
    return None


def normalize_record(raw, source_file, idx):
    """把任意 dict 记录归一到规范 schema；缺键容错。"""
    if not isinstance(raw, dict):
        raw = {"title": str(raw)}
    low = {}
    for k, v in raw.items():
        if isinstance(k, str):
            low.setdefault(k.strip().lower(), v)
    rec = {"id": "", "title": "", "year": None, "venue": "", "abstract": ""}
    for k, v in low.items():
        canon = KEY_MAP.get(k)
        if canon is None or v is None:
            continue
        if canon == "year":
            rec["year"] = extract_year(v)
        else:
            sval = str(v).strip()
            if sval and not rec[canon]:
                rec[canon] = sval
    if rec["year"] is None:
        rec["year"] = extract_year(low.get("year")) or extract_year(low.get("date"))
    if not rec["id"]:
        rec["id"] = "%s-%04d" % (os.path.splitext(os.path.basename(source_file))[0], idx)
    rec["source_file"] = os.path.basename(source_file)
    return rec


def parse_json(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("records", "items", "data", "papers", "results"):
            if isinstance(data.get(key), list):
                return data[key]
        return [data]
    return []


def parse_jsonl(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                # 坏行不致命：降级为纯文本标题记录
                out.append({"title": line[:200]})
    return out


def parse_csv(path):
    with open(path, encoding="utf-8", newline="") as f:
        return [dict(row) for row in csv.DictReader(f)]


BIB_START_RE = re.compile(r"@\w+\s*\{")
BIB_FIELD_RE = re.compile(r"(\w+)\s*=\s*[\{\"](.+?)[\}\"]\s*,", re.DOTALL)


def _bib_entries(text):
    """按花括号配平切分 BibTeX 条目（兼容单行/多行），yield (key, body)。"""
    for m in BIB_START_RE.finditer(text):
        depth, i = 1, m.end()
        start = i
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        entry = text[start:i - 1]
        if "," in entry:
            key, body = entry.split(",", 1)
            yield key.strip(), body


def parse_bib(path):
    """极简 BibTeX 解析：花括号配平 + 单值字段抽取，不追求完整 BibTeX 语法。"""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    out = []
    for key, body in _bib_entries(text):
        rec = {"id": key}
        # 字段以逗号分隔；末字段无逗号时补一个以便统一正则
        for fm in BIB_FIELD_RE.finditer(body + ","):
            rec[fm.group(1).lower()] = re.sub(r"\s+", " ", fm.group(2)).strip()
        out.append(rec)
    return out


def parse_ris(path):
    out, rec = [], None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if len(line) >= 6 and line[2:6] == "  - ":
                tag, val = line[:2].strip(), line[6:].strip()
                if tag == "TY":
                    rec = {}
                elif tag == "ER":
                    if rec is not None:
                        out.append(rec)
                    rec = None
                elif rec is not None:
                    if tag in ("TI", "T1"):
                        rec.setdefault("title", val)
                    elif tag in ("PY", "Y1", "DA"):
                        rec.setdefault("year", val)
                    elif tag in ("JO", "JF", "T2", "JA"):
                        rec.setdefault("venue", val)
                    elif tag in ("AB", "N2"):
                        rec["abstract"] = (rec.get("abstract", "") + " " + val).strip()
                    elif tag == "ID":
                        rec.setdefault("id", val)
    if rec is not None:
        out.append(rec)
    return out


def parse_text(path):
    """txt/md：一个文件视为一条记录；标题取首个 markdown 标题或首个非空行。"""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    title = ""
    for line in text.splitlines():
        s = line.strip().lstrip("#").strip()
        if s:
            title = s[:200]
            break
    stem = os.path.splitext(os.path.basename(path))[0]
    year = extract_year(text[:2000]) or extract_year(stem)
    rec = {"id": stem, "title": title or stem, "year": year, "venue": "",
           "abstract": re.sub(r"\s+", " ", text).strip()[:500]}
    return [rec]


PARSERS = {".json": parse_json, ".jsonl": parse_jsonl, ".csv": parse_csv,
           ".bib": parse_bib, ".ris": parse_ris, ".txt": parse_text, ".md": parse_text}


def collect_files(inputs):
    files = []
    for item in inputs:
        if os.path.isdir(item):
            for ext in sorted(SUPPORTED_EXT):
                files.extend(glob.glob(os.path.join(item, "**", "*" + ext), recursive=True))
        elif os.path.isfile(item):
            files.append(item)
        else:
            print("WARNING: input not found, skipped: %s" % item, file=sys.stderr)
    # 去重并排序，保证确定性
    return sorted(dict.fromkeys(files))


def main():
    ap = argparse.ArgumentParser(description="归一化文献语料到 canon.jsonl（仅标准库）")
    ap.add_argument("--work", required=True, help="工作目录（输出 canon.jsonl / corpus_meta.json）")
    ap.add_argument("--inputs", nargs="+", required=True, help="输入文件或目录（可多个）")
    args = ap.parse_args()

    os.makedirs(args.work, exist_ok=True)
    files = collect_files(args.inputs)
    records, per_source, skipped_ext = [], {}, []
    for path in files:
        ext = os.path.splitext(path)[1].lower()
        parser = PARSERS.get(ext)
        if parser is None:
            skipped_ext.append(os.path.basename(path))
            continue
        try:
            raw_list = parser(path)
        except Exception as exc:  # 单个文件失败不致命
            print("WARNING: parse failed %s: %s" % (path, exc), file=sys.stderr)
            raw_list = []
        for idx, raw in enumerate(raw_list):
            records.append(normalize_record(raw, path, idx))
        per_source[os.path.basename(path)] = len(raw_list)

    # 确定性排序：按 (source_file, year缺失置后, year, id)
    records.sort(key=lambda r: (r["source_file"], r["year"] is None, r["year"] or 9999, r["id"]))

    canon_path = os.path.join(args.work, "canon.jsonl")
    with open(canon_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")

    n = len(records)
    n_missing = sum(1 for r in records if r["year"] is None)
    years = [r["year"] for r in records if r["year"] is not None]
    frac = (n_missing / n) if n else 0.0
    warnings = []
    if n == 0:
        warnings.append("empty_corpus: 未从输入解析出任何记录")
    if frac > 0.2:
        warnings.append("year_missing_gt_20pct: 年份缺失比例 %.1f%% > 20%%，趋势结论须附带覆盖度不确定性，禁止补零" % (frac * 100))
    if skipped_ext:
        warnings.append("unsupported_files_skipped: %s" % ",".join(sorted(skipped_ext)))
    meta = {
        "n_records": n,
        "n_missing_year": n_missing,
        "missing_year_frac": round(frac, 6),
        "year_min": min(years) if years else None,
        "year_max": max(years) if years else None,
        "per_source": per_source,
        "warnings": warnings,
    }
    with open(os.path.join(args.work, "corpus_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print("build_corpus: %d records (%d missing year) -> %s" % (n, n_missing, canon_path))
    for w in warnings:
        print("WARNING: %s" % w, file=sys.stderr)


if __name__ == "__main__":
    main()
