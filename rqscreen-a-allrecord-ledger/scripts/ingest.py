#!/usr/bin/env python3
"""ingest.py — 清点输入目录、把所有记录型文件解析为统一 records.jsonl。

用法:
  python3 ingest.py --input-dir /input --work /app/work

行为:
  - 递归扫描输入目录,按扩展名解析: .json/.jsonl/.csv/.tsv/.ris/.bib/.md/.txt
  - 在 JSON 中深度优先寻找"字典列表"作为记录集(取元素数>=2 的列表);
    若顶层含 records/results/items/papers/data 等键则优先
  - 每条记录统一字段: rid(来源文件!行号或record_id), origin_file, origin_row,
    title, authors, year, venue, doi, type, abstract, keywords, source, flags, raw_keys
  - 只读真实文件内容,不依据文件名/目录标签推断语义
  - 输出 work/records.jsonl 与 work/ingest_report.json(文件清点、解析成功/失败原因)
"""
import argparse, csv, io, json, os, re, sys

RECORD_KEYS = ["records", "results", "items", "papers", "entries", "data",
               "documents", "hits", "export", "publications", "refs", "references"]

def norm_space(s):
    return re.sub(r"\s+", " ", str(s)).strip() if s is not None else ""

def first_key(d, keys):
    low = {str(k).lower(): k for k in d.keys()}
    for w in keys:
        if w in low and d[low[w]] not in (None, ""):
            return d[low[w]]
    return None

def normalize_record(rec, origin_file, origin_row):
    """把任意形状的记录字典映射为统一 schema;保留原始键清单与标记位。"""
    g = lambda *ks: first_key(rec, ks)
    title = norm_space(g("title", "article_title", "name", "paper_title", "document_title", "ti"))
    authors = g("authors", "author", "creators", "creator", "au", "author_list")
    if isinstance(authors, list):
        parts = []
        for a in authors:
            if isinstance(a, dict):
                parts.append(norm_space(first_key(a, ["name", "full_name", "family", "last_name", "given"]) or
                                        " ".join(str(v) for v in a.values() if isinstance(v, (str, int)))))
            else:
                parts.append(norm_space(a))
        authors = "; ".join(p for p in parts if p)
    year = first_key(rec, ["year", "publication_year", "pub_year", "date", "py", "published", "issued"])
    if isinstance(year, str):
        m = re.search(r"(19|20)\d{2}", year)
        year = int(m.group(0)) if m else None
    elif isinstance(year, dict):
        y = first_key(year, ["year"])
        year = int(y) if str(y).isdigit() else None
    venue = norm_space(g("venue", "journal", "source", "container_title", "publication", "jo", "journal_title", "publisher"))
    doi = norm_space(g("doi", "DOI", "digital_object_identifier"))
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.I)
    abstract = norm_space(g("abstract", "summary", "description", "abs", "snippet"))
    kws = g("keywords", "keyword", "tags", "terms", "kw", "subjects", "categories")
    if isinstance(kws, list):
        kws = "; ".join(norm_space(k) for k in kws)
    rtype = norm_space(g("type", "record_type", "doc_type", "genre", "document_type"))
    flags = {k: rec[k] for k in rec.keys() if str(k).lower() in
             ("synthetic_duplicate", "duplicate_of", "conflicting_opinion", "conflicts_with",
              "fixture", "fixture_note", "label", "is_duplicate", "is_conflict")}
    rid = first_key(rec, ["record_id", "id", "uid", "key"]) or "%s!%s" % (origin_file, origin_row)
    return {
        "rid": norm_space(rid), "origin_file": origin_file, "origin_row": origin_row,
        "title": title, "authors": norm_space(authors), "year": year, "venue": venue,
        "doi": doi, "type": rtype.lower(), "abstract": abstract,
        "keywords": norm_space(kws), "source": origin_file,
        "flags": flags, "raw_keys": sorted(str(k) for k in rec.keys())[:40],
    }

def find_record_lists(node, path=""):
    """深度优先返回所有"字典列表"候选及其路径。"""
    out = []
    if isinstance(node, list):
        if len(node) >= 1 and all(isinstance(x, dict) for x in node):
            out.append((path, node))
        for i, x in enumerate(node[:5]):
            out += find_record_lists(x, "%s[%d]" % (path, i))
    elif isinstance(node, dict):
        for k, v in node.items():
            out += find_record_lists(v, "%s.%s" % (path, k))
    return out

def parse_json(path):
    txt = open(path, encoding="utf-8", errors="replace").read()
    try:
        data = json.loads(txt)
    except Exception:
        recs = []
        for ln, line in enumerate(txt.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    recs.append((ln + 1, json.loads(line)))
                except Exception:
                    pass
        return [r for _, r in recs] if recs else None
    if isinstance(data, list) and all(isinstance(x, dict) for x in data):
        return data
    if isinstance(data, dict):
        for k in RECORD_KEYS:
            if k in data and isinstance(data[k], list) and data[k] and isinstance(data[k][0], dict):
                return data[k]
        cands = find_record_lists(data)
        cands = [c for c in cands if len(c[1]) >= 2]
        if cands:
            cands.sort(key=lambda c: -len(c[1]))
            return cands[0][1]
    return None

def parse_csv(path, delim):
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        rdr = csv.DictReader(f, delimiter=delim)
        return [dict(r) for r in rdr] or None

RIS_MAP = {"TI": "title", "T1": "title", "AU": "authors", "PY": "year", "Y1": "year",
           "JO": "venue", "JF": "venue", "T2": "venue", "DO": "doi", "AB": "abstract",
           "KW": "keywords", "TY": "type", "N2": "abstract"}

def parse_ris(path):
    recs, cur = [], None
    for line in open(path, encoding="utf-8", errors="replace"):
        m = re.match(r"^([A-Z][A-Z0-9])  ?- (.*)$", line.rstrip("\n"))
        if not m:
            continue
        tag, val = m.group(1), m.group(2).strip()
        if tag == "TY":
            cur = {}
        if cur is None:
            continue
        key = RIS_MAP.get(tag)
        if key:
            if key in cur:
                cur[key] = (cur[key] + "; " + val) if key in ("authors", "keywords") else cur[key]
            else:
                cur[key] = val
        if tag == "ER":
            recs.append(cur); cur = None
    return recs or None

def parse_bib(path):
    txt = open(path, encoding="utf-8", errors="replace").read()
    recs = []
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,]+),(.*?)\n\s*\}", txt, re.S):
        body = m.group(3)
        d = {"type": m.group(1).lower(), "id": m.group(2).strip()}
        for fm in re.finditer(r"(\w+)\s*=\s*[\{\"](.+?)[\}\"]\s*,?\s*\n", body, re.S):
            d[fm.group(1).lower()] = re.sub(r"\s+", " ", fm.group(2)).strip()
        recs.append(d)
    return recs or None

MD_ROW = re.compile(r"^\s*(?:[-*]\s+|\d+[.)]\s+)(.+?)\s*$")

def parse_md(path):
    """从 markdown 列表行中提取含标题样式的记录(标题加粗或以句点结尾的长文本)。"""
    recs = []
    for line in open(path, encoding="utf-8", errors="replace"):
        m = MD_ROW.match(line)
        if m:
            t = re.sub(r"[*_`]", "", m.group(1)).strip()
            if len(t) >= 20 and not t.startswith(("http", "|")):
                recs.append({"title": t})
    return recs or None

PARSERS = {".json": parse_json, ".jsonl": parse_json, ".csv": lambda p: parse_csv(p, ","),
           ".tsv": lambda p: parse_csv(p, "\t"), ".ris": parse_ris, ".bib": parse_bib,
           ".md": parse_md, ".txt": parse_md}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--work", required=True)
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    report = {"input_dir": args.input_dir, "files": [], "records_total": 0, "records_parsed": 0, "failures": []}
    out_path = os.path.join(args.work, "records.jsonl")
    n = 0
    with open(out_path, "w", encoding="utf-8") as out:
        for root, _, names in os.walk(args.input_dir):
            for name in sorted(names):
                ext = os.path.splitext(name)[1].lower()
                path = os.path.join(root, name)
                rel = os.path.relpath(path, args.input_dir)
                report["files"].append({"path": rel, "bytes": os.path.getsize(path)})
                if ext not in PARSERS:
                    continue
                try:
                    recs = PARSERS[ext](path)
                except Exception as e:
                    report["failures"].append({"path": rel, "reason": "parse_error: %s" % e})
                    continue
                if not recs:
                    report["failures"].append({"path": rel, "reason": "no record list found"})
                    continue
                parsed = 0
                for i, r in enumerate(recs):
                    if not isinstance(r, dict):
                        continue
                    rec = normalize_record(r, rel, i + 1)
                    if not rec["title"] and not rec["doi"]:
                        continue
                    n += 1; parsed += 1
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                report["records_parsed"] += parsed
                report["files"][-1]["records"] = parsed
    report["records_total"] = n
    with open(os.path.join(args.work, "ingest_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({"ok": True, "records": n, "report": "ingest_report.json",
                      "failures": len(report["failures"])}, ensure_ascii=False))

if __name__ == "__main__":
    main()
