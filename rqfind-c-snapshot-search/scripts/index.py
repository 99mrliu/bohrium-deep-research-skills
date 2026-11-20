#!/usr/bin/env python3
"""index.py — 对输入快照建立可解释倒排索引(纯本地,零网络)。

用法:
  python3 index.py --input-dir /input --work /app/work

分词: 拉丁词干化(去复数/后缀: s,es,ing,ed,ly,ation->ate 不做,仅保守截尾) +
      CJK 二元组; title 权重 3.0, keywords 2.0, abstract 1.0。
输出: work/index.json (postings: term -> {rid: [field,score] 列表}),
      work/docstats.json (df, 文档长度, 记录数), work/index_report.json
记录解析逻辑与单独文件 ingest 一致(支持 JSON/JSONL/CSV/TSV/RIS/BIB/MD),
但本方向完全独立,不依赖其他 bundle 的脚本。
"""
import argparse, csv, json, os, re, sys, unicodedata

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
    g = lambda *ks: first_key(rec, ks)
    title = norm_space(g("title", "article_title", "name", "ti"))
    authors = g("authors", "author", "creators", "au")
    if isinstance(authors, list):
        authors = "; ".join(norm_space(first_key(a, ["name", "full_name"]) or str(a)) if isinstance(a, dict) else norm_space(a) for a in authors)
    year = first_key(rec, ["year", "publication_year", "pub_year", "date", "py"])
    if isinstance(year, str):
        m = re.search(r"(19|20)\d{2}", year)
        year = int(m.group(0)) if m else None
    kws = g("keywords", "keyword", "tags", "terms", "kw", "subjects")
    if isinstance(kws, list):
        kws = "; ".join(norm_space(k) for k in kws)
    rid = first_key(rec, ["record_id", "id", "uid", "key"]) or "%s!%s" % (origin_file, origin_row)
    flags = {k: rec[k] for k in rec.keys() if str(k).lower() in
             ("synthetic_duplicate", "duplicate_of", "conflicting_opinion", "conflicts_with", "fixture", "label")}
    return {"rid": norm_space(rid), "title": title, "authors": norm_space(authors),
            "year": year, "venue": norm_space(g("venue", "journal", "source", "jo", "publication")),
            "doi": norm_space(g("doi", "DOI")), "abstract": norm_space(g("abstract", "summary", "abs", "snippet")),
            "keywords": norm_space(kws), "type": norm_space(g("type", "record_type", "doc_type")).lower(),
            "origin_file": origin_file, "origin_row": origin_row, "flags": flags}

def find_record_lists(node, path=""):
    out = []
    if isinstance(node, list):
        if node and all(isinstance(x, dict) for x in node):
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
        for line in txt.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    recs.append(json.loads(line))
                except Exception:
                    pass
        return recs or None
    if isinstance(data, list) and all(isinstance(x, dict) for x in data):
        return data
    if isinstance(data, dict):
        for k in RECORD_KEYS:
            if isinstance(data.get(k), list) and data[k] and isinstance(data[k][0], dict):
                return data[k]
        cands = [c for c in find_record_lists(data) if len(c[1]) >= 2]
        if cands:
            cands.sort(key=lambda c: -len(c[1]))
            return cands[0][1]
    return None

def parse_csv(path, delim):
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        return [dict(r) for r in csv.DictReader(f, delimiter=delim)] or None

def parse_lines(path):
    recs = []
    for line in open(path, encoding="utf-8", errors="replace"):
        m = re.match(r"^\s*(?:[-*]\s+|\d+[.)]\s+)(.+?)\s*$", line)
        if m and len(m.group(1)) >= 20:
            recs.append({"title": re.sub(r"[*_`]", "", m.group(1)).strip()})
    return recs or None

PARSERS = {".json": parse_json, ".jsonl": parse_json,
           ".csv": lambda p: parse_csv(p, ","), ".tsv": lambda p: parse_csv(p, "\t"),
           ".md": parse_lines, ".txt": parse_lines}

STOP = set("""the a an of for in on with and or to from by is are was were be been we our this that their
its as at into via over under between among using use used study studies based have has had report show
shows shown results demonstrate demonstrates review perspective editorial news comment""".split())

def stem(w):
    for suf in ("ingly", "edly", "ing", "edly", "ed", "ies", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)]
            break
    return w

def tokenize(text):
    text = unicodedata.normalize("NFKC", text or "").lower()
    toks = []
    for chunk in re.split(r"[^a-z0-9一-鿿]+", text):
        if not chunk:
            continue
        if re.search(r"[一-鿿]", chunk):
            latin = re.findall(r"[a-z0-9]+", chunk)
            toks += [stem(w) for w in latin if w not in STOP and len(w) >= 2]
            cjk = re.sub(r"[a-z0-9]+", "", chunk)
            toks += [cjk[i:i + 2] for i in range(len(cjk) - 1)]
        else:
            if chunk not in STOP and len(chunk) >= 2:
                toks.append(stem(chunk))
    return toks

FIELD_W = {"title": 3.0, "keywords": 2.0, "abstract": 1.0, "authors": 0.5, "venue": 0.5}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--work", required=True)
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    docs, failures, files = {}, [], []
    n = 0
    for root, _, names in os.walk(args.input_dir):
        for name in sorted(names):
            ext = os.path.splitext(name)[1].lower()
            path = os.path.join(root, name)
            rel = os.path.relpath(path, args.input_dir)
            files.append(rel)
            if ext not in PARSERS:
                continue
            try:
                recs = PARSERS[ext](path)
            except Exception as e:
                failures.append({"path": rel, "reason": str(e)})
                continue
            if not recs:
                continue
            for i, r in enumerate(recs):
                if not isinstance(r, dict):
                    continue
                rec = normalize_record(r, rel, i + 1)
                if not rec["title"] and not rec["doi"]:
                    continue
                if rec["rid"] in docs:
                    rec["rid"] = rec["rid"] + "#dup%d" % i
                docs[rec["rid"]] = rec
                n += 1
    index, df = {}, {}
    for rid, rec in docs.items():
        for field in ("title", "keywords", "abstract", "authors", "venue"):
            toks = tokenize(rec.get(field, ""))
            freq = {}
            for t in toks:
                freq[t] = freq.get(t, 0) + 1
            for t, c in freq.items():
                index.setdefault(t, {}).setdefault(rid, []).append([field, round(c * FIELD_W[field], 3)])
    for t in index:
        df[t] = len(index[t])
    json.dump(index, open(os.path.join(args.work, "index.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump({"n_docs": n, "vocab": len(index), "df": df,
               "docs": {rid: {k: rec[k] for k in ("title", "year", "venue", "doi", "type", "flags", "origin_file", "origin_row")}
                        for rid, rec in docs.items()}},
              open(os.path.join(args.work, "docstats.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump({"input_dir": args.input_dir, "files_scanned": files, "records_indexed": n,
               "failures": failures}, open(os.path.join(args.work, "index_report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps({"ok": True, "docs": n, "vocab": len(index), "failures": len(failures)},
                     ensure_ascii=False))

if __name__ == "__main__":
    main()
