#!/usr/bin/env python3
"""sniff_parse.py -- 多源文献导出文件的格式嗅探、编码处置与规范化解析。

输入一个目录（如 /input 或案例材料目录），逐个文件：
  1. 判定字节编码（utf-8 / utf-8-sig / gb18030 / latin-1 兜底），记录替换字符数；
  2. 嗅探导出格式（json-array / json-lines / csv / tsv / ris / nbib / plain-text）；
  3. 解析为规范化记录，每条记录携带来源坐标（source_file + source_line）与
     field_status（ok / missing-abstract / missing-title 等）；
  4. 无法解析的条目进入 quarantine 并给出原因，绝不静默丢弃。

产物（写入 --out 目录）：
  records_ingested.json  规范记录数组（含 provenance）
  ingest_ledger.json     每文件摄入台账（字节数、行数、编码、修复、格式、条目计数）

退出码：0=正常完成（允许有 quarantine）；2=输入目录不存在或无候选文件。
本脚本不联网、不合并重复记录（去重是下游环节，此处只登记 exact-dup 提示）。
"""
import argparse
import csv
import io
import json
import os
import re
import sys

MOJIBAKE_RE = re.compile(r"[ÃÂâ]{1}[\x80-\xbf€‚ƒ„…†‡ˆ‰Š‹ŒŽ''""€œ]|Ã©|Ã¶|Ã¼|Ã¤|Ã±")

TEXT_EXTS = {".txt", ".csv", ".tsv", ".json", ".md", ".ris", ".nbib", ".ciw", ".enw", ".xml"}


def read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def decode_bytes(raw):
    """返回 (text, encoding, replaced_chars, notes)。"""
    notes = []
    if raw.startswith(b"\xef\xbb\xbf"):
        text = raw.decode("utf-8-sig", errors="replace")
        notes.append("bom-stripped")
        return text, "utf-8-sig", text.count("�"), notes
    try:
        text = raw.decode("utf-8")
        return text, "utf-8", 0, notes
    except UnicodeDecodeError:
        pass
    for enc in ("gb18030", "latin-1"):
        try:
            text = raw.decode(enc)
            notes.append("utf-8-decode-failed-fell-back")
            return text, enc, 0, notes
        except UnicodeDecodeError:
            continue
    text = raw.decode("utf-8", errors="replace")
    notes.append("lossy-replace")
    return text, "utf-8-replace", text.count("�"), notes


def sniff_format(path, text):
    """返回格式标签。扩展名只是提示，内容签名优先。"""
    head = text.lstrip()[:4000]
    ext = os.path.splitext(path)[1].lower()
    if head.startswith("[") or head.startswith("{"):
        try:
            obj = json.loads(text)
            if isinstance(obj, list):
                return "json-array"
            if isinstance(obj, dict):
                return "json-object"
        except Exception:
            pass
        # 逐行 JSON
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if lines:
            ok = 0
            for ln in lines[:20]:
                try:
                    json.loads(ln)
                    ok += 1
                except Exception:
                    break
            if ok == min(len(lines), 20) and ok > 0:
                return "json-lines"
    if re.search(r"^[A-Z][A-Z0-9]  - ", text, re.M):
        if re.search(r"^PMID- ", text, re.M) or re.search(r"^TI  - ", text, re.M) and "PMID" in head:
            return "nbib"
        return "ris"
    if ext in (".csv", ".tsv") or ("," in text.splitlines()[0] if text.splitlines() else False):
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",\t;")
            return "tsv" if dialect.delimiter == "\t" else "csv"
        except Exception:
            return "tsv" if ext == ".tsv" else ("csv" if ext == ".csv" else "plain-text")
    return "plain-text"


NORM_KEYS = {
    "title": ["title", "ti", "TI", "T1", "article_title", "Article Title"],
    "doi": ["doi", "DOI", "DI", "digital_object_identifier", "DO"],
    "year": ["year", "PY", "Y1", "publication_year", "Year", "DP"],
    "journal": ["journal", "JO", "T2", "source_title", "Source Title", "TA"],
    "abstract": ["abstract", "AB", "Abstract", "abstract_note"],
    "authors": ["authors", "AU", "A1", "Authors", "author"],
    "pmid": ["pmid", "PMID", "pubmed_id"],
}


def pick(d, key):
    for cand in NORM_KEYS[key]:
        if cand in d and d[cand] not in (None, ""):
            v = d[cand]
            if isinstance(v, list):
                v = "; ".join(str(x) for x in v)
            return str(v).strip()
    return ""


def field_status(rec):
    st = []
    if not rec["title"]:
        st.append("missing-title")
    if not rec["abstract"]:
        st.append("missing-abstract")
    if not rec["doi"]:
        st.append("missing-doi")
    return st or ["ok"]


def mojibake_scan(rec):
    hits = []
    for k in ("title", "abstract", "authors", "journal"):
        v = rec.get(k) or ""
        if MOJIBAKE_RE.search(v):
            hits.append(k)
    return hits


def norm_doi(doi):
    doi = (doi or "").strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    return doi


def parse_json_array(text, src, quarantine):
    records = []
    data = json.loads(text)
    if isinstance(data, dict):
        for key in ("records", "references", "results", "items", "data"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            data = [data]
    for i, item in enumerate(data):
        line = i + 1
        if not isinstance(item, dict):
            quarantine.append({"source_file": src, "item_index": i,
                               "reason": "json-entry-not-object",
                               "excerpt": repr(item)[:200]})
            continue
        rec = {k: pick(item, k) for k in NORM_KEYS}
        rec["source_line"] = line
        records.append(rec)
    return records


def parse_json_lines(text, src, quarantine):
    records = []
    for i, ln in enumerate(text.splitlines()):
        if not ln.strip():
            continue
        try:
            item = json.loads(ln)
        except Exception as exc:
            quarantine.append({"source_file": src, "item_index": i,
                               "reason": "json-line-parse-error: %s" % type(exc).__name__,
                               "excerpt": ln[:200]})
            continue
        if not isinstance(item, dict):
            quarantine.append({"source_file": src, "item_index": i,
                               "reason": "json-entry-not-object", "excerpt": repr(item)[:200]})
            continue
        rec = {k: pick(item, k) for k in NORM_KEYS}
        rec["source_line"] = i + 1
        records.append(rec)
    return records


def parse_delimited(text, src, quarantine, delim=None):
    records = []
    if delim is None:
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",\t;")
        except Exception:
            dialect = csv.excel
    else:
        dialect = csv.excel_tab if delim == "\t" else csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        quarantine.append({"source_file": src, "item_index": 0,
                           "reason": "no-header-row", "excerpt": text[:200]})
        return records
    for i, row in enumerate(reader):
        if row is None:
            continue
        row = {k: v for k, v in row.items() if k is not None}
        if any(v is None for v in row.values()) or None in row.values():
            quarantine.append({"source_file": src, "item_index": i + 2,
                               "reason": "ragged-row-field-count-mismatch",
                               "excerpt": json.dumps(row, ensure_ascii=False)[:200]})
            continue
        rec = {k: pick(row, k) for k in NORM_KEYS}
        rec["source_line"] = i + 2  # header 为第 1 行
        if not any(rec.values()):
            quarantine.append({"source_file": src, "item_index": i + 2,
                               "reason": "empty-row", "excerpt": ""})
            continue
        records.append(rec)
    return records


RIS_TAG_RE = re.compile(r"^([A-Z][A-Z0-9])  - (.*)$")


def parse_ris(text, src, quarantine):
    records = []
    blocks, cur, cur_start = [], [], 1
    for ln_no, ln in enumerate(text.splitlines(), start=1):
        m = RIS_TAG_RE.match(ln)
        if m:
            if not cur:
                cur_start = ln_no
            cur.append((m.group(1), m.group(2).strip()))
        elif cur:
            blocks.append((cur_start, cur))
            cur = []
    if cur:
        blocks.append((cur_start, cur))
    # RIS 以 TY 开始、ER 结束；按 TY 切块更稳，但上面按空行/连续标签已可工作。
    # 重新按 TY..ER 分组：
    grouped, cur, cur_start = [], [], None
    for start, block in blocks:
        for tag, val in block:
            if tag == "TY" and cur:
                grouped.append((cur_start, cur))
                cur, cur_start = [], start
            if cur_start is None:
                cur_start = start
            cur.append((tag, val))
            if tag == "ER":
                grouped.append((cur_start, cur))
                cur, cur_start = [], None
    if cur:
        grouped.append((cur_start or 1, cur))
    for start, block in (grouped or blocks):
        item = {}
        for tag, val in block:
            item.setdefault(tag, []).append(val)
        flat = {k: "; ".join(v) for k, v in item.items()}
        rec = {k: pick(flat, k) for k in NORM_KEYS}
        rec["source_line"] = start
        if not rec["title"]:
            quarantine.append({"source_file": src, "item_index": start,
                               "reason": "ris-block-without-title",
                               "excerpt": json.dumps(flat, ensure_ascii=False)[:200]})
            continue
        records.append(rec)
    return records


def parse_plain_text(text, src, quarantine):
    """兜底：非空行视作无法结构化的题录材料，整体隔离并说明。"""
    quarantine.append({
        "source_file": src, "item_index": 1,
        "reason": "unrecognized-format-plain-text",
        "excerpt": text[:200]})
    return []


def main():
    ap = argparse.ArgumentParser(description="多源导出嗅探解析（摄入取证）")
    ap.add_argument("--input-dir", default="/input")
    ap.add_argument("--out", default="/app/work/ingest")
    ap.add_argument("--glob", default="",
                    help="逗号分隔的额外文件名过滤子串，如 exports,ris；默认全目录文本文件")
    args = ap.parse_args()

    if not os.path.isdir(args.input_dir):
        print("INPUT-DIR-MISSING: %s" % args.input_dir, file=sys.stderr)
        sys.exit(2)

    os.makedirs(args.out, exist_ok=True)
    filters = [s for s in args.glob.split(",") if s]

    candidates = []
    for root, _dirs, files in os.walk(args.input_dir):
        for fn in sorted(files):
            ext = os.path.splitext(fn)[1].lower()
            if ext not in TEXT_EXTS:
                continue
            if fn.startswith("case") or fn in ("task.md", "result.json"):
                continue
            if filters and not any(f in fn for f in filters):
                continue
            candidates.append(os.path.join(root, fn))
    candidates.sort()

    if not candidates:
        print("NO-CANDIDATE-FILES under %s" % args.input_dir, file=sys.stderr)
        sys.exit(2)

    all_records, quarantine, ledger = [], [], []
    seq = 0
    for path in candidates:
        raw = read_bytes(path)
        text, encoding, replaced, notes = decode_bytes(raw)
        fmt = sniff_format(path, text)
        rel = os.path.relpath(path, args.input_dir)
        before_q = len(quarantine)
        try:
            if fmt == "json-array" or fmt == "json-object":
                recs = parse_json_array(text, rel, quarantine)
            elif fmt == "json-lines":
                recs = parse_json_lines(text, rel, quarantine)
            elif fmt in ("csv", "tsv"):
                recs = parse_delimited(text, rel, quarantine,
                                       delim="\t" if fmt == "tsv" else None)
            elif fmt in ("ris", "nbib"):
                recs = parse_ris(text, rel, quarantine)
            else:
                recs = parse_plain_text(text, rel, quarantine)
        except Exception as exc:
            recs = []
            quarantine.append({"source_file": rel, "item_index": 0,
                               "reason": "parser-exception: %s" % type(exc).__name__,
                               "excerpt": text[:200]})
        for rec in recs:
            seq += 1
            rec["record_id"] = "ingest-%04d" % seq
            rec["source_file"] = rel
            rec["source_format"] = fmt
            rec["encoding"] = encoding
            rec["doi_norm"] = norm_doi(rec["doi"])
            rec["field_status"] = field_status(rec)
            mb = mojibake_scan(rec)
            if mb:
                rec.setdefault("repair_notes", []).append(
                    "suspected-mojibake-in:%s" % ",".join(mb))
            all_records.append(rec)
        n_q = len(quarantine) - before_q
        ledger.append({
            "source_file": rel,
            "bytes": len(raw),
            "lines": text.count("\n") + (1 if text and not text.endswith("\n") else 0),
            "encoding": encoding,
            "replaced_chars": replaced,
            "decode_notes": notes,
            "format": fmt,
            "records_parsed": len(recs),
            "items_quarantined": n_q,
            "items_found": len(recs) + n_q,
        })

    # exact-dup 提示（只登记、不合并）：归一 DOI 或归一标题完全相同
    seen, dup_hints = {}, []
    for rec in all_records:
        keys = []
        if rec["doi_norm"]:
            keys.append("doi:" + rec["doi_norm"])
        t = re.sub(r"\W+", " ", (rec["title"] or "").lower()).strip()
        if t:
            keys.append("title:" + t)
        for k in keys:
            if k in seen:
                dup_hints.append({"key": k, "kept": seen[k],
                                  "also": rec["record_id"],
                                  "note": "exact-duplicate-hint; merge decision belongs to dedup stage"})
            else:
                seen[k] = rec["record_id"]

    payload = {
        "records": all_records,
        "quarantine": quarantine,
        "duplicate_hints": dup_hints,
        "totals": {
            "files": len(ledger),
            "records_parsed": len(all_records),
            "items_quarantined": len(quarantine),
            "duplicate_hints": len(dup_hints),
        },
        "provenance_policy": "每条记录含 source_file+source_line；quarantine 条目含原因与摘录；不静默丢弃任何输入条目。",
    }
    with open(os.path.join(args.out, "records_ingested.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "ingest_ledger.json"), "w", encoding="utf-8") as fh:
        json.dump({"files": ledger,
                   "totals": payload["totals"]}, fh, ensure_ascii=False, indent=2)
    print("PARSED %d records, QUARANTINED %d items from %d files -> %s"
          % (len(all_records), len(quarantine), len(ledger), args.out))
    sys.exit(0)


if __name__ == "__main__":
    main()
