#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ingest_corpus.py — 语料摄入与规范化引擎（仅标准库，确定性输出，无网络）。

用法:
    python3 ingest_corpus.py --work DIR --inputs FILE_OR_DIR... [--date-policy POLICY]

读取 json/jsonl/csv/bib/ris/txt/md 文件（或包含这些文件的目录），在 --work 下写出:
    canon.jsonl        规范化后的保留记录（每行一条 JSON）
    duplicates.json    被移除的重复记录对及触发规则
    ingest_report.json 计数闭环、分格式统计、输入文件 sha256 清单、错误日志

设计原则:
  * 确定性：无时间戳；JSON 键排序；处理顺序 = 输入路径字典序 + 文件内顺序。
  * 健壮性：单个文件损坏/解析失败不会终止运行，记入 ingest_report.errors。
  * 日期溯源：year 一律记录其来源字段（date_provenance），策略见 references/date_policy.md。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import unicodedata
from pathlib import Path

SUPPORTED_EXTS = (".bib", ".csv", ".json", ".jsonl", ".md", ".ris", ".txt")
YEAR_RE = re.compile(r"(?:19|20)\d{2}")
TOKEN_RE = re.compile(r"[a-z0-9]+|[一-鿿]")
CJK_RE = re.compile(r"[一-鿿]")

STOPWORDS = set(
    "a an the of in on for and or with via to from by at as is are was were "
    "be been into over under between among using based toward towards its it "
    "this that these those".split()
)

FIELD_ALIASES = {
    "title": ["title", "ti"],
    "authors": ["authors", "author", "creator"],
    "year": ["year", "publication_year", "pub_year", "py", "date"],
    "year_print": ["year_print", "print_year"],
    "year_online": ["year_online", "online_year"],
    "year_preprint": ["year_preprint", "preprint_year"],
    "doi": ["doi"],
    "venue": ["venue", "journal", "journal_title", "container_title",
              "container-title", "publication", "source_title"],
    "abstract": ["abstract", "summary"],
    "keywords": ["keywords", "keyword", "tags"],
}

POLICY_ORDER = {
    "print": ("year_print", "year_online", "year_preprint", "year"),
    "online": ("year_online", "year_print", "year_preprint", "year"),
    "preprint": ("year_preprint", "year_online", "year_print", "year"),
}

CANON_KEYS = ("id", "title", "authors", "year", "year_print", "year_online",
              "year_preprint", "doi", "venue", "abstract", "keywords",
              "source_file", "source_sha256", "source_format", "date_provenance")


# ---------------------------------------------------------------------------
# 各格式解析器：均返回 (raw_records, error_or_None)，不因内容问题抛异常
# ---------------------------------------------------------------------------

def parse_json(text):
    """解析 .json：列表 / 含列表字段的对象 / 单条记录对象。"""
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        return [], f"json decode error: {e}"
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)], None
    if isinstance(obj, dict):
        for key in ("records", "items", "papers", "results", "data",
                    "documents", "entries", "works", "publications"):
            if isinstance(obj.get(key), list):
                return [x for x in obj[key] if isinstance(x, dict)], None
        if "title" in obj or "doi" in obj:
            return [obj], None
        return [], "unrecognized json structure (no record list found)"
    return [], "top-level json is neither list nor object"


def parse_jsonl(text):
    recs, bad = [], 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                recs.append(obj)
            else:
                bad += 1
        except json.JSONDecodeError:
            bad += 1
    err = f"{bad} non-record line(s) skipped" if bad else None
    return recs, err


def parse_csv_text(text):
    try:
        reader = csv.DictReader(io.StringIO(text))
        return [dict(r) for r in reader], None
    except csv.Error as e:
        return [], f"csv error: {e}"


def _split_top_level(body):
    """按顶层逗号切分 BibTeX entry body（感知花括号与引号深度）。"""
    parts, depth, cur, in_quote = [], 0, [], False
    for ch in body:
        if ch == '"' and depth == 0:
            in_quote = not in_quote
        if not in_quote:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append("".join(cur))
                cur = []
                continue
        cur.append(ch)
    if cur:
        parts.append("".join(cur))
    return parts


def parse_bib(text):
    """极简 BibTeX 解析器：提取 @type{key, field = {value}, ...} 的字段。"""
    recs = []
    for m in re.finditer(r"@\w+\s*\{", text):
        depth, i = 1, m.end()
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        body = text[m.end():i - 1]
        parts = _split_top_level(body)
        fields = {}
        for p in parts[1:]:
            if "=" in p:
                k, v = p.split("=", 1)
                v = v.strip()
                while v.startswith("{") and v.endswith("}") and len(v) >= 2:
                    v = v[1:-1].strip()
                fields[k.strip().lower()] = v.strip().strip('"').strip()
        if fields:
            if "author" in fields:
                fields["authors"] = [a.strip() for a in fields["author"].split(" and ") if a.strip()]
            if "journal" in fields and "venue" not in fields:
                fields["venue"] = fields["journal"]
            if "booktitle" in fields and "venue" not in fields:
                fields["venue"] = fields["booktitle"]
            recs.append(fields)
    if not recs:
        return [], "no bibtex entries found"
    return recs, None


def parse_ris(text):
    recs, cur = [], None
    multi = {"AU": "authors", "A1": "authors", "KW": "keywords"}
    single = {"TI": "title", "T1": "title", "CT": "title",
              "PY": "year", "Y1": "year", "DA": "year",
              "DO": "doi", "JO": "venue", "JF": "venue", "T2": "venue",
              "JA": "venue", "AB": "abstract", "N2": "abstract"}
    for line in text.splitlines():
        m = re.match(r"^([A-Z0-9]{2})  - (.*)$", line)
        if not m:
            continue
        tag, val = m.group(1), m.group(2).strip()
        if tag == "TY":
            cur = {"authors": [], "keywords": []}
        elif tag == "ER":
            if cur is not None:
                recs.append(cur)
            cur = None
        elif cur is not None:
            if tag in multi:
                cur[multi[tag]].append(val)
            elif tag in single and single[tag] not in cur:
                cur[single[tag]] = val
    if cur is not None:
        recs.append(cur)
    if not recs:
        return [], "no RIS records found"
    return recs, None


def parse_freetext(text):
    """txt/md 兜底：首行作标题，正则抓第一个年份，其余作摘要。标注 freetext_regex 溯源。"""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return [], "empty file"
    rec = {"title": lines[0].lstrip("# ").strip()[:300],
           "abstract": " ".join(lines[1:])[:2000]}
    m = YEAR_RE.search(text)
    if m:
        rec["year"] = int(m.group(0))
        rec["_year_hint"] = "freetext_regex"
    return [rec], None


def parse_file(fmt, text):
    if fmt == "json":
        return parse_json(text)
    if fmt == "jsonl":
        return parse_jsonl(text)
    if fmt == "csv":
        return parse_csv_text(text)
    if fmt == "bib":
        return parse_bib(text)
    if fmt == "ris":
        return parse_ris(text)
    # txt / md：依次尝试 json → jsonl → 自由文本兜底
    recs, _ = parse_json(text)
    if recs:
        return recs, None
    recs, _ = parse_jsonl(text)
    if recs:
        return recs, None
    return parse_freetext(text)


# ---------------------------------------------------------------------------
# 规范化
# ---------------------------------------------------------------------------

def _first_key(raw, aliases):
    lower = {str(k).lower().replace(" ", "_"): v for k, v in raw.items()}
    for a in aliases:
        if a in lower and lower[a] not in (None, "", []):
            return lower[a]
    return None


def _to_year(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v if 1900 <= v <= 2099 else None
    if isinstance(v, float) and v.is_integer():
        return _to_year(int(v))
    m = YEAR_RE.search(str(v))
    return int(m.group(0)) if m else None


def _to_list(v, seps=(";", "|")):
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    s = str(v).strip()
    if not s:
        return []
    for sep in seps:
        if sep in s:
            return [p.strip() for p in s.split(sep) if p.strip()]
    return [s]


def norm_doi(v):
    if not v:
        return None
    s = str(v).strip().lower()
    for prefix in ("https://doi.org/", "http://dx.doi.org/", "https://dx.doi.org/", "doi:"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    return s.strip().rstrip("/") or None


def coerce(raw):
    """把任意来源的 raw dict 归一为 canon 记录（id/年份决策稍后填充）。"""
    rec = {
        "title": str(_first_key(raw, FIELD_ALIASES["title"]) or "").strip(),
        "authors": _to_list(_first_key(raw, FIELD_ALIASES["authors"]), (";", "|", " and ")),
        "year": _to_year(_first_key(raw, FIELD_ALIASES["year"])),
        "year_print": _to_year(_first_key(raw, FIELD_ALIASES["year_print"])),
        "year_online": _to_year(_first_key(raw, FIELD_ALIASES["year_online"])),
        "year_preprint": _to_year(_first_key(raw, FIELD_ALIASES["year_preprint"])),
        "doi": norm_doi(_first_key(raw, FIELD_ALIASES["doi"])),
        "venue": str(_first_key(raw, FIELD_ALIASES["venue"]) or "").strip(),
        "abstract": str(_first_key(raw, FIELD_ALIASES["abstract"]) or "").strip(),
        "keywords": _to_list(_first_key(raw, FIELD_ALIASES["keywords"]), (";", "|", ",")),
    }
    if raw.get("synthetic") is not None:
        rec["synthetic"] = bool(raw.get("synthetic"))
    if raw.get("_year_hint"):
        rec["_year_hint"] = raw["_year_hint"]
    return rec


def choose_year(rec, policy):
    """按日期策略选定 year，返回 (year, date_provenance)。"""
    cands = {f: rec.get(f) for f in ("year_print", "year_online", "year_preprint", "year")}
    cands = {f: y for f, y in cands.items() if isinstance(y, int)}
    if not cands:
        return None, "missing"
    if policy == "earliest":
        field = min(sorted(cands), key=lambda k: cands[k])
        prov = field + ("(earliest)" if len(cands) > 1 else "")
    else:
        field = next(k for k in POLICY_ORDER[policy] if k in cands)
        prov = field
    hint = rec.get("_year_hint")
    if hint and field == "year":
        prov = f"{prov}:{hint}"
    return cands[field], prov


def title_tokens(t):
    t = unicodedata.normalize("NFKD", t or "").lower()
    out = set()
    for tok in TOKEN_RE.findall(t):
        if tok in STOPWORDS:
            continue
        if len(tok) >= 2 or CJK_RE.match(tok):
            out.add(tok)
    return out


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="语料摄入与规范化引擎（stdlib only）")
    ap.add_argument("--work", required=True, help="工作目录，工件写在此处")
    ap.add_argument("--inputs", nargs="+", required=True, help="输入文件或目录")
    ap.add_argument("--date-policy", choices=["print", "online", "preprint", "earliest"],
                    default="print", help="冲突日期字段的取舍策略（默认 print）")
    args = ap.parse_args()

    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)

    files, skipped = [], []
    for item in args.inputs:
        p = Path(item)
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS:
                    files.append(f)
                elif f.is_file():
                    skipped.append(str(f))
        elif p.is_file():
            if p.suffix.lower() in SUPPORTED_EXTS:
                files.append(p)
            else:
                skipped.append(str(p))
        else:
            skipped.append(f"{item} (not found)")
    files = sorted({str(f) for f in files})

    input_files, errors, per_format, raws = [], [], {}, []
    for fpath in files:
        f = Path(fpath)
        fmt = f.suffix.lower().lstrip(".")
        try:
            data = f.read_bytes()
            sha = hashlib.sha256(data).hexdigest()
            text = data.decode("utf-8", errors="replace")
            recs, err = parse_file(fmt, text)
            if err:
                errors.append({"path": str(f), "error": err})
            input_files.append({"path": str(f), "sha256": sha, "format": fmt,
                                "status": "ok" if err is None else "partial",
                                "records": len(recs)})
            pf = per_format.setdefault(fmt, {"files": 0, "records": 0})
            pf["files"] += 1
            pf["records"] += len(recs)
            for r in recs:
                raws.append((r, str(f), sha, fmt))
        except Exception as e:  # 单文件损坏不得终止运行
            errors.append({"path": str(f), "error": f"{type(e).__name__}: {e}"})
            input_files.append({"path": str(f), "sha256": None, "format": fmt,
                                "status": "failed", "records": 0})

    records = []
    for i, (raw, src, sha, fmt) in enumerate(raws, 1):
        rec = coerce(raw)
        rec["id"] = f"R{i:03d}"
        rec["source_file"] = src
        rec["source_sha256"] = sha
        rec["source_format"] = fmt
        year, prov = choose_year(rec, args.date_policy)
        rec["year"] = year
        rec["date_provenance"] = prov
        rec["_tokens"] = title_tokens(rec["title"])
        records.append(rec)

    # 去重：DOI 精确匹配优先，其次归一化标题 token Jaccard >= 0.9；保留先见者
    kept, pairs = [], []
    for rec in records:
        hit = None
        for k in kept:
            if rec["doi"] and k["doi"] and rec["doi"] == k["doi"]:
                hit = (k, "doi_exact", 1.0)
                break
            score = jaccard(rec["_tokens"], k["_tokens"])
            if score >= 0.9:
                hit = (k, "title_jaccard>=0.9", round(score, 4))
                break
        if hit:
            pairs.append({"kept_id": hit[0]["id"], "removed_id": rec["id"],
                          "removed_title": rec["title"], "rule": hit[1],
                          "score": hit[2]})
        else:
            kept.append(rec)

    canon_path = work / "canon.jsonl"
    with canon_path.open("w", encoding="utf-8") as fh:
        for rec in kept:
            out = {k: rec.get(k) for k in CANON_KEYS}
            if "synthetic" in rec:
                out["synthetic"] = rec["synthetic"]
            fh.write(json.dumps(out, ensure_ascii=False, sort_keys=True) + "\n")

    dup_doc = {"duplicates_removed": len(pairs), "pairs": pairs}
    (work / "duplicates.json").write_text(
        json.dumps(dup_doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")

    report = {
        "records_total": len(records),
        "records_kept": len(kept),
        "duplicates_removed": len(pairs),
        "records_with_year": sum(1 for r in kept if isinstance(r.get("year"), int)),
        "records_without_year": sum(1 for r in kept if not isinstance(r.get("year"), int)),
        "per_format": per_format,
        "input_files": input_files,
        "skipped_inputs": sorted(skipped),
        "errors": errors,
        "date_policy": args.date_policy,
    }
    (work / "ingest_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")

    print(json.dumps({"canon": str(canon_path),
                      "records_total": report["records_total"],
                      "records_kept": report["records_kept"],
                      "duplicates_removed": report["duplicates_removed"],
                      "records_without_year": report["records_without_year"]},
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
