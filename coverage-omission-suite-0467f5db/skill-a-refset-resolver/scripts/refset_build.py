#!/usr/bin/env python3
"""refset_build.py — 步骤②至⑥：参考题录解析、核验、去重、处置、冻结。

输入：materials_index.json（由 parse_case.py 产出）及其实际材料文件。
输出：raw_records.json、verification.json、dedup_log.json、exclusion_log.json、
     frozen reference_set.json（v1.0.0，含逐条出处）。

核验顺序：本地 Crossref/EuropePMC 响应文件优先；本地不足时经 urllib 联网
兜底（带缓存与超时）；离线时诚实降级，绝不伪造。

退出码：0 正常；2 材料不足；3 校验失败。仅使用 Python 标准库。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SCRIPT_NAME = "refset_build.py"
SCHEMA_VERSION = "1.0.0"
LIVE_TIMEOUT = 10  # 秒

# ---------------------------------------------------------------- 工具

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def norm_doi(value):
    """规范化 DOI；无法解析返回 None。规则见 references/identifier_normalization_rules.md"""
    if not value:
        return None
    v = str(value).strip()
    v = re.sub(r"(?i)^https?://(dx\.)?doi\.org/", "", v)
    v = re.sub(r"(?i)^doi:\s*", "", v)
    v = v.strip().strip(".").rstrip("/").lower()
    if re.fullmatch(r"10\.\d{4,9}/\S+", v):
        return v
    return None


def norm_pmid(value):
    if not value:
        return None
    v = str(value).strip()
    m = re.fullmatch(r"(\d{1,9})", v)
    return m.group(1) if m else None


def norm_pmcid(value):
    if not value:
        return None
    v = str(value).strip().upper()
    m = re.fullmatch(r"PMC\d+", v)
    return v if m else None


def norm_arxiv(value):
    if not value:
        return None
    v = str(value).strip()
    v = re.sub(r"(?i)^arxiv:\s*", "", v).strip()
    v = re.sub(r"\s+as\s+$", "", v)
    v = re.sub(r"v\d+$", "", v)  # 去版本号
    if re.fullmatch(r"\d{4}\.\d{4,5}(:\d+)?", v) or re.fullmatch(r"[a-z-]+/\d{7}", v):
        return v
    return None


def norm_title_key(title):
    """标题弱匹配键：小写、去标点、去停用词、排序词组。"""
    if not title:
        return ()
    t = title.lower()
    t = re.sub(r"[^a-z0-9一-鿿\s]", " ", t)
    stop = {"the", "a", "an", "of", "and", "in", "on", "for", "to", "with", "by",
            "is", "are", "was", "were", "using", "based", "study", "studies",
            "review", "an", "from", "at", "as", "be", "its"}
    toks = tuple(sorted(w for w in t.split() if w not in stop and len(w) > 1))
    return toks


def jaccard(a, b):
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb)


# ---------------------------------------------------------------- 题录解析

def parse_csv(path, loc_prefix):
    records = []
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as fh:
            lines = [ln for ln in fh if not ln.lstrip().startswith("#")]
            if not lines:
                return records
            reader = csv.DictReader(lines)
            if not reader.fieldnames:
                return records
            names = {n.lower().strip(): n for n in reader.fieldnames}
            def pick(*keys):
                for k in keys:
                    if k in names:
                        return names[k]
                return None
            cols = {
                "title": pick("title", "article_title", "题名"),
                "authors": pick("authors", "author", "authors_full", "作者"),
                "year": pick("year", "pub_year", "出版年"),
                "journal": pick("journal", "journal_title", "container", "刊名"),
                "doi": pick("doi", "DO".lower()),
                "pmid": pick("pmid", "pubmed_id"),
                "pmcid": pick("pmcid", "pmc_id"),
                "arxiv": pick("arxiv", "arxiv_id"),
            }
            if not cols["title"]:
                return records  # 无标题列则不是题录 CSV
            for i, row in enumerate(reader, start=2):
                rec = {k: (row[c].strip() if c and row.get(c) else "")
                       for k, c in cols.items()}
                if rec["title"]:
                    records.append((rec, f"{loc_prefix}#L{i}"))
    except (OSError, csv.Error, UnicodeDecodeError):
        pass
    return records


def parse_json_biblio(path, loc_prefix):
    records = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return records
    candidates = data if isinstance(data, list) else \
        data.get("references") or data.get("items") or [] \
        if isinstance(data, dict) else []
    for i, item in enumerate(candidates):
        if not isinstance(item, dict):
            continue
        title = item.get("title") or item.get("article-title") or ""
        if isinstance(title, list):
            title = title[0] if title else ""
        authors = item.get("authors") or item.get("author") or ""
        if isinstance(authors, list):
            authors = "; ".join(a if isinstance(a, str) else
                                (a.get("family", "") + ", " + a.get("given", ""))
                                for a in authors)
        journal = item.get("journal") or item.get("container-title") or ""
        if isinstance(journal, list):
            journal = journal[0] if journal else ""
        year = str(item.get("year") or item.get("issued") or item.get("pub_year") or "")
        if isinstance(item.get("issued"), dict):
            parts = item["issued"].get("date-parts", [[""]])
            year = str(parts[0][0]) if parts and parts[0] else year
        rec = {"title": str(title).strip(), "authors": str(authors).strip(),
               "year": year.strip()[:4], "journal": str(journal).strip(),
               "doi": str(item.get("doi") or item.get("DOI") or "").strip(),
               "pmid": str(item.get("pmid") or item.get("PMID") or "").strip(),
               "pmcid": str(item.get("pmcid") or item.get("PMCID") or "").strip(),
               "arxiv": str(item.get("arxiv") or item.get("eprint") or "").strip()}
        if rec["title"]:
            records.append((rec, f"{loc_prefix}#[{i}]"))
    return records


def parse_bibtex(path, loc_prefix):
    records = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return records
    entry_re = re.compile(r"@(\w+)\s*\{\s*([^,]+),(.*?)\n\s*\}", re.S)
    for m in entry_re.finditer(text):
        body = m.group(3)
        fields = {}
        for fm in re.finditer(r'(\w+)\s*=\s*[{"](.+?)[}"]\s*,?\s*(?=\n|\w+\s*=|\})',
                              body, re.S):
            fields[fm.group(1).lower()] = re.sub(r"\s+", " ", fm.group(2)).strip()
        title = fields.get("title", "")
        if not title:
            continue
        line = text[:m.start()].count("\n") + 1
        authors = fields.get("author", "")
        year = (fields.get("year") or "")[:4]
        eprint = fields.get("eprint", "")
        rec = {"title": title, "authors": authors, "year": year,
               "journal": fields.get("journal", ""),
               "doi": fields.get("doi", ""),
               "pmid": fields.get("pmid", ""),
               "pmcid": fields.get("pmcid", ""),
               "arxiv": eprint if fields.get("archiveprefix", "").lower() == "arxiv" or "arxiv" in eprint else
                        fields.get("arxiv", "")}
        records.append((rec, f"{loc_prefix}#L{line}"))
    return records


def parse_ris(path, loc_prefix):
    records = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return records
    cur, start_line = {}, None
    tagmap = {"TI": "title", "T1": "title", "AU": "authors", "PY": "year",
              "Y1": "year", "JO": "journal", "JF": "journal",
              "DO": "doi", "PM": "pmid", "PMC": "pmcid", "AR": "arxiv"}
    def flush():
        if cur.get("title") and start_line:
            rec = {"title": cur.get("title", ""), "authors": "; ".join(cur.get("authors", [])),
                   "year": (cur.get("year", "") or "")[:4],
                   "journal": cur.get("journal", ""),
                   "doi": cur.get("doi", ""), "pmid": cur.get("pmid", ""),
                   "pmcid": cur.get("pmcid", ""), "arxiv": cur.get("arxiv", "")}
            records.append((rec, f"{loc_prefix}#L{start_line}"))
    for i, line in enumerate(lines, start=1):
        m = re.match(r"^(\w{2})\s+-\s?(.*)$", line.rstrip("\n"))
        if not m:
            continue
        tag, val = m.group(1), m.group(2).strip()
        if tag == "TY":
            cur, start_line = {}, i
            continue
        if tag == "ER":
            flush()
            cur, start_line = {}, None
            continue
        if start_line is None:
            continue
        if tag in tagmap:
            key = tagmap[tag]
            if key == "authors":
                cur.setdefault("authors", []).append(val)
            elif key == "year" and not cur.get("year"):
                cur[key] = val
            elif key not in cur:
                cur[key] = val
    return records


def pdf_to_text(pdf_path, workdir):
    """pdftotext 可用则提取文本到 workdir/_pdftext/，返回文本路径或 None。"""
    outdir = os.path.join(workdir, "_pdftext")
    os.makedirs(outdir, exist_ok=True)
    base = hashlib.sha1(pdf_path.encode()).hexdigest()[:12]
    out_txt = os.path.join(outdir, base + ".txt")
    if os.path.isfile(out_txt):
        return out_txt
    try:
        subprocess.run(["pdftotext", pdf_path, out_txt],
                       check=True, timeout=60,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return out_txt
    except (OSError, subprocess.SubprocessError):
        return None


REF_LINE_RE = re.compile(r"^\s*(?:\[\d+\]|\(\d{4}\)\s*\d+\.|\d+\.)\s+(.{20,})$")


def parse_pdf_refs(path, workdir, loc_prefix):
    """启发式解析 PDF 提取文本中的编号参考文献行；置信度低，需人工复核。"""
    records = []
    txt = pdf_to_text(path, workdir)
    if not txt:
        return records
    try:
        with open(txt, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return records
    in_refs = False
    for i, line in enumerate(lines, start=1):
        low = line.strip().lower()
        if not in_refs:
            if re.match(r"^(references|bibliography|参考文献)\s*$", low):
                in_refs = True
            continue
        m = REF_LINE_RE.match(line)
        if m:
            snippet = m.group(1).strip()
            if len(snippet) < 25 or "et al" not in snippet.lower() and "doi" not in snippet.lower() \
               and not re.search(r"\d{4}", snippet):
                continue
            doi = None
            dm = re.search(r"(?i)(10\.\d{4,9}/[^\s\"'<>]+)", snippet)
            if dm:
                doi = dm.group(1).rstrip(".,;)]")
            pmid = None
            pm = re.search(r"(?i)pmid[:\s]*(\d{6,9})", snippet)
            if pm:
                pmid = pm.group(1)
            year = ""
            ym = re.search(r"\b(19|20)\d{2}\b", snippet)
            if ym:
                year = ym.group(0)
            title = snippet
            tm = re.search(r"[\"“](.+?)[\"”]", snippet)
            if tm:
                title = tm.group(1)
            records.append(({"title": title, "authors": "", "year": year,
                             "journal": "", "doi": doi or "", "pmid": pmid or "",
                             "pmcid": "", "arxiv": ""},
                            f"{loc_prefix}#pdfL{i}"))
    return records


PARSERS = {
    "bibtex": parse_bibtex,
    "ris": parse_ris,
    "csv": parse_csv,
    "bibliography": parse_json_biblio,
    "pdf": parse_pdf_refs,
}

# ---------------------------------------------------------------- 响应索引

def load_response_index(workdir, materials):
    """从本地 API 响应文件建立标识符→记录索引与标题键→记录索引。"""
    idx = {"doi": {}, "pmid": {}, "pmcid": {}, "title": {}}
    for m in materials:
        if m["type"] not in ("crossref_response", "europepmc_response",
                             "publisher_response", "json_other"):
            continue
        fpath = m.get("abs_path")
        if not fpath or not os.path.isfile(fpath):
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        items = []
        if isinstance(data, dict):
            msg = data.get("message", {})
            if isinstance(msg, dict) and isinstance(msg.get("items"), list):
                items = msg["items"]
            elif isinstance(data.get("resultList"), dict):
                items = data["resultList"].get("result", [])
            elif isinstance(data.get("results"), list):
                items = data["results"]
        elif isinstance(data, list):
            items = data
        for j, it in enumerate(items):
            if not isinstance(it, dict):
                continue
            title = it.get("title") or it.get("titleString") or it.get("articleTitle") or ""
            if isinstance(title, list):
                title = title[0] if title else ""
            title = str(title).strip()
            doi = norm_doi(it.get("DOI") or it.get("doi"))
            pmid = norm_pmid(it.get("PMID") or it.get("pmid"))
            pmcid = norm_pmcid(it.get("PMCID") or it.get("pmcid"))
            journal = it.get("container-title") or \
                ((it.get("journalInfo", {}) or {}).get("journal", {}) or {}).get("title", "") or \
                it.get("journalTitle") or ""
            if isinstance(journal, list):
                journal = journal[0] if journal else ""
            entry = {"file": m["path"], "json_ptr": f"[{j}]",
                     "title": title, "doi": doi, "pmid": pmid, "pmcid": pmcid,
                     "journal": str(journal),
                     "year": str(_extract_year(it)),
                     "raw": it}
            if doi:
                idx["doi"].setdefault(doi, entry)
            if pmid:
                idx["pmid"].setdefault(pmid, entry)
            if pmcid:
                idx["pmcid"].setdefault(pmcid, entry)
            if title:
                idx["title"].setdefault(norm_title_key(title), entry)
    return idx


def _extract_year(item):
    if isinstance(item.get("issued"), dict):
        parts = item["issued"].get("date-parts", [[None]])
        if parts and parts[0] and parts[0][0]:
            return parts[0][0]
    for k in ("pubYear", "year", "published", "firstPublicationDate"):
        v = item.get(k)
        if isinstance(v, str) and re.search(r"(19|20)\d{2}", v):
            return re.search(r"(19|20)\d{2}", v).group(0)
        if isinstance(v, (int, float)):
            return int(v)
    for k in ("journalInfo",):
        ji = item.get(k)
        if isinstance(ji, dict):
            y = ji.get("yearOfPublication")
            if y:
                return y
    return None


def is_retracted(entry):
    raw = entry.get("raw", {})
    # Crossref update 关系
    rel = raw.get("relation", {})
    if isinstance(rel, dict):
        for vals in rel.values():
            if isinstance(vals, list):
                for v in vals:
                    if isinstance(v, dict) and "retraction" in str(
                            v.get("id-type", "") + v.get("type", "")).lower():
                        return True
    # EuropePMC 撤稿线索
    jt = str(entry.get("journal", "")).lower()
    if "retraction" in jt:
        return True
    text = json.dumps(raw, ensure_ascii=False).lower()
    if '"retracted"' in text and "true" in text:
        return True
    if re.search(r"retraction of[: ]", text[:4000]):
        return True
    return False


# ---------------------------------------------------------------- 联网兜底

def live_lookup(kind, ident, cache_dir):
    """经缓存的 urllib 核验；失败返回 None（诚实降级）。"""
    os.makedirs(cache_dir, exist_ok=True)
    if kind == "doi":
        url = "https://api.crossref.org/works/" + urllib.parse.quote(ident, safe="")
    elif kind == "pmid":
        url = ("https://www.ebi.ac.uk/europepmc/webservices/rest/search?format=json"
               "&query=" + urllib.parse.quote(f"EXT_ID:{ident} AND SRC:MED"))
    else:
        return None
    key = hashlib.sha1(url.encode()).hexdigest() + ".json"
    cpath = os.path.join(cache_dir, key)
    if os.path.isfile(cpath):
        try:
            with open(cpath, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "refset-resolver/1.0"})
        with urllib.request.urlopen(req, timeout=LIVE_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        with open(cpath, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        return payload
    except Exception:
        return None


# ---------------------------------------------------------------- 主流程

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="构建并冻结版本化参考集（含核验、去重、处置台账）。")
    ap.add_argument("--workdir", default="/app/work")
    ap.add_argument("--outdir", default="/app/output")
    ap.add_argument("--rebuild", action="store_true",
                    help="忽略已冻结参考集，强制重建")
    ap.add_argument("--no-live", action="store_true",
                    help="禁用联网兜底，仅使用本地响应文件")
    ap.add_argument("--pdf-refs", action="store_true",
                    help="启用 PDF 参考文献启发式解析（默认关闭，置信度低）")
    args = ap.parse_args(argv)

    workdir, outdir = args.workdir, args.outdir
    os.makedirs(workdir, exist_ok=True)
    os.makedirs(outdir, exist_ok=True)

    idx_path = os.path.join(workdir, "materials_index.json")
    if not os.path.isfile(idx_path):
        print(f"[{SCRIPT_NAME}] 缺少 materials_index.json，请先运行 parse_case.py",
              file=sys.stderr)
        return 2
    with open(idx_path, "r", encoding="utf-8") as fh:
        materials_index = json.load(fh)
    case_id = materials_index.get("case_id", "unknown_case")
    # 还原绝对路径（materials_index 存的是相对路径）
    matdir = materials_index.get("materials_dir", "")
    for m in materials_index.get("materials", []):
        m["abs_path"] = os.path.join(matdir, m["path"])

    frozen_path = os.path.join(outdir, "reference_set.json")
    if os.path.isfile(frozen_path) and not args.rebuild:
        print(f"[{SCRIPT_NAME}] 已存在冻结参考集，未指定 --rebuild，跳过重建。"
              f"如需重建请显式加 --rebuild。")
        return 0

    limitations = []
    status = "complete"

    # ---- ② 解析候选题录 ----
    raw_records = []
    for m in materials_index.get("materials", []):
        ftype, fpath = m["type"], m["abs_path"]
        if not os.path.isfile(fpath):
            limitations.append(f"材料缺失：{m['path']}")
            continue
        if ftype == "pdf" and not args.pdf_refs:
            continue
        parser = PARSERS.get(ftype)
        if not parser:
            continue
        if ftype == "pdf":
            parsed = parser(fpath, workdir, m["path"])
        else:
            parsed = parser(fpath, m["path"])
        for rec, loc in parsed:
            raw_records.append({"raw": rec, "source": loc,
                                "inclusion_reason": f"parsed_from:{ftype}"})
    if not raw_records:
        print(f"[{SCRIPT_NAME}] 未解析到任何候选题录，无法构建分母。", file=sys.stderr)
        limitations.append("未解析到候选题录。")
        status = "failed"
    with open(os.path.join(workdir, "raw_records.json"), "w", encoding="utf-8") as fh:
        json.dump(raw_records, fh, ensure_ascii=False, indent=2)

    # ---- 建立本地响应索引 ----
    resp_idx = load_response_index(workdir, materials_index.get("materials", []))
    has_local = bool(resp_idx["doi"] or resp_idx["pmid"])
    if not has_local:
        limitations.append("本地无可用 API 响应文件，核验范围受限。")
        status = "partial"
        if args.no_live:
            limitations.append("--no-live 已指定，全部记录仅能标 unverified。")

    # ---- ③ 核验 ----
    verifications = []
    for rr in raw_records:
        rec = rr["raw"]
        ids = {"doi": norm_doi(rec.get("doi")),
               "pmid": norm_pmid(rec.get("pmid")),
               "pmcid": norm_pmcid(rec.get("pmcid")),
               "arxiv": norm_arxiv(rec.get("arxiv"))}
        found = []
        vsource = None
        for kind in ("doi", "pmid", "pmcid"):
            ident = ids[kind]
            if ident and ident in resp_idx[kind]:
                found.append((kind, ident, resp_idx[kind][ident], "local"))
                vsource = "local_response"
        if not found and not args.no_live:
            # 联网兜底：仅当本地无命中
            for kind in ("doi", "pmid"):
                ident = ids[kind]
                if not ident:
                    continue
                payload = live_lookup(kind, ident, os.path.join(workdir, "api_cache"))
                if payload:
                    entry = payload_to_entry(payload, kind, ident)
                    if entry:
                        found.append((kind, ident, entry, "live"))
                        vsource = "live_api_cached"
        vrec = {"source": rr["source"], "ids": ids,
                "verification_source": vsource,
                "matches": [
                    {"via": k, "id": i, "entry": _slim(e), "channel": ch}
                    for (k, i, e, ch) in found]}
        if not found:
            vrec["verification_status"] = "unverified"
        else:
            titles = {e["title"] for (_, _, e, _) in found if e.get("title")}
            if len(titles) > 1 and all(
                    jaccard(norm_title_key(t), norm_title_key(t2)) < 0.6
                    for t in titles for t2 in titles if t != t2):
                vrec["verification_status"] = "identifier_conflict"
            else:
                vrec["verification_status"] = "verified"
        verifications.append(vrec)
    with open(os.path.join(workdir, "verification.json"), "w", encoding="utf-8") as fh:
        json.dump(verifications, fh, ensure_ascii=False, indent=2)

    # ---- 合并 raw + verification ----
    entries = []
    for rr, vv in zip(raw_records, verifications):
        rec = rr["raw"]
        e = {
            "title": rec.get("title", "").strip(),
            "authors": rec.get("authors", "").strip(),
            "year": (rec.get("year") or "").strip()[:4],
            "journal": rec.get("journal", "").strip(),
            "doi": vv["ids"]["doi"], "pmid": vv["ids"]["pmid"],
            "pmcid": vv["ids"]["pmcid"], "arxiv": vv["ids"]["arxiv"],
            "verification_status": vv["verification_status"],
            "verification_source": vv["verification_source"],
            "verification_evidence": vv["matches"],
            "inclusion_reason": rr["inclusion_reason"],
            "source": [rr["source"]],
        }
        # 本地核验命中时用权威字段补齐空缺
        if vv["matches"]:
            auth = vv["matches"][0]["entry"]
            for f in ("year", "journal"):
                if not e[f] and auth.get(f):
                    e[f] = str(auth[f])
        entries.append(e)

    # ---- ④ 去重（阻塞 + 标题相似度） ----
    dedup_log = []
    by_id = {}
    for e in entries:
        for k in ("doi", "pmid", "pmcid", "arxiv"):
            if e.get(k):
                by_id.setdefault((k, e[k]), []).append(e)
    clusters = []
    seen_ids = set()
    for key, members in by_id.items():
        if key in seen_ids:
            continue
        cluster, stack = [], [key]
        while stack:
            k = stack.pop()
            if k in seen_ids:
                continue
            seen_ids.add(k)
            for m in by_id.get(k, []):
                if m not in cluster:
                    cluster.append(m)
                    for k2 in ("doi", "pmid", "pmcid", "arxiv"):
                        if m.get(k2):
                            stack.append((k2, m[k2]))
        clusters.append(cluster)
    # 无标识符条目与跨簇标题相似合并
    merged_into = {}
    representatives = []
    title_keys = {}
    for ci, cluster in enumerate(clusters):
        rep = max(cluster, key=lambda e: sum(1 for f in
                  ("doi", "pmid", "year", "journal") if e.get(f)))
        # 补齐：合并被并记录的出处
        for m in cluster:
            if m is not rep:
                for s in m["source"]:
                    if s not in rep["source"]:
                        rep["source"].append(s)
                merged_into[id(m)] = rep
        rep["merged_from"] = [m["source"][0] for m in cluster if m is not rep]
        representatives.append(rep)
        tk = norm_title_key(rep["title"])
        if tk:
            title_keys.setdefault(tk, []).append(rep)
    # 标题相似度弱键去重（针对无标识符条目）
    orphans = [e for e in entries if not any(e.get(k) for k in
               ("doi", "pmid", "pmcid", "arxiv")) and e not in representatives]
    for e in orphans:
        tk = norm_title_key(e["title"])
        best, best_sim = None, 0.0
        for rep in representatives:
            sim = jaccard(tk, norm_title_key(rep["title"]))
            if sim > best_sim:
                best, best_sim = rep, sim
        if best and best_sim >= 0.85:
            for s in e["source"]:
                if s not in best["source"]:
                    best["source"].append(s)
            dedup_log.append({
                "action": "merge_title_similarity",
                "dropped_source": e["source"][0],
                "kept_source": best["source"][0],
                "similarity": round(best_sim, 3),
                "note": "无标识符条目按标题相似度合并。"})
            merged_into[id(e)] = best
        else:
            representatives.append(e)
    for cluster in clusters:
        if len(cluster) > 1:
            rep = [r for r in representatives if r in cluster][0]
            for m in cluster:
                if m is not rep:
                    dedup_log.append({
                        "action": "merge_identifier",
                        "dropped_source": m["source"][0],
                        "kept_source": rep["source"][0],
                        "shared_key": next(k for k in ("doi", "pmid", "pmcid", "arxiv")
                                           if m.get(k) and rep.get(k)),
                        "note": "标识符相同合并。"})
    with open(os.path.join(outdir, "dedup_log.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated_at": now_iso(), "entries": dedup_log},
                  fh, ensure_ascii=False, indent=2)

    # ---- ⑤ 不可用记录处置 ----
    exclusion_log = []
    for e in representatives:
        disp, flags = "include", []
        retracted = any(m["entry"].get("retracted")
                        for m in e["verification_evidence"]
                        if isinstance(m.get("entry"), dict))
        if retracted:
            disp = "exclude_retracted"
        elif e["verification_status"] == "identifier_conflict":
            disp = "needs_manual_review"
            flags.append("identifier_conflict")
        elif e["verification_status"] == "unverified" and \
                any(e.get(k) for k in ("doi", "pmid")):
            disp = "needs_manual_review"
            flags.append("identifier_unresolvable_local" if not args.no_live
                         else "identifier_unresolvable_offline")
        elif e["verification_status"] == "unverified":
            disp = "needs_manual_review"
            flags.append("no_identifier")
        # 全文可得性（仅当有证据记录）
        if disp == "include" and any(
                m["entry"].get("no_fulltext_url")
                for m in e["verification_evidence"]
                if isinstance(m.get("entry"), dict)):
            disp = "flag_keep_no_fulltext"
            flags.append("no_fulltext_url")
        e["disposition"] = disp
        e["flags"] = sorted(set(flags))
        e["usable"] = disp in ("include", "flag_keep_no_fulltext",
                               "needs_manual_review")
        e["usable_for_fulltext"] = "no_fulltext_url" not in e["flags"]
        if disp != "include":
            exclusion_log.append({
                "source": e["source"][0], "title": e["title"][:120],
                "disposition": disp, "flags": e["flags"],
                "reason": _disp_reason(disp, e["flags"])})
    with open(os.path.join(outdir, "exclusion_log.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated_at": now_iso(), "entries": exclusion_log},
                  fh, ensure_ascii=False, indent=2)

    # ---- ⑥ 冻结参考集 ----
    representatives.sort(key=lambda e: (e.get("year") or "9999", e["title"]))
    for i, e in enumerate(representatives, start=1):
        e["ref_id"] = f"REF-{i:04d}"
    refset = {
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "frozen_at": now_iso(),
        "frozen_by": SCRIPT_NAME,
        "denominator_policy": ("分母仅来自案例本地参考材料（题录文件与参考图谱），"
                               "与任何检索结果无关；条目经核验、去重、处置后冻结。"),
        "records": representatives,
        "stats": {
            "total": len(representatives),
            "usable": sum(1 for e in representatives if e["usable"]),
            "verified": sum(1 for e in representatives
                            if e["verification_status"] == "verified"),
            "needs_manual_review": sum(1 for e in representatives
                                       if e["disposition"] == "needs_manual_review"),
            "excluded": sum(1 for e in representatives
                            if e["disposition"].startswith("exclude")),
            "merged_away": len(dedup_log),
        },
        "status": status,
        "limitations": limitations,
    }
    with open(frozen_path, "w", encoding="utf-8") as fh:
        json.dump(refset, fh, ensure_ascii=False, indent=2)

    print(f"[{SCRIPT_NAME}] 参考集冻结：total={refset['stats']['total']} "
          f"usable={refset['stats']['usable']} "
          f"review={refset['stats']['needs_manual_review']} "
          f"excluded={refset['stats']['excluded']} "
          f"merged={refset['stats']['merged_away']} status={status}")
    for lim in limitations:
        print(f"  limitation: {lim}", file=sys.stderr)
    return 0 if status != "failed" else 2


def payload_to_entry(payload, kind, ident):
    """将联网兜底响应转成与本地索引一致的 entry。"""
    try:
        if kind == "doi":
            msg = payload.get("message", {})
            title = msg.get("title", [""])[0]
            return {"file": "live:crossref", "json_ptr": ident, "title": title,
                    "doi": ident, "pmid": None, "pmcid": None,
                    "journal": (msg.get("container-title", [""]) or [""])[0],
                    "year": str(_extract_year(msg)), "raw": msg}
        if kind == "pmid":
            res = payload.get("resultList", {}).get("result", [])
            if not res:
                return None
            r = res[0]
            return {"file": "live:europepmc", "json_ptr": ident,
                    "title": r.get("titleString", ""), "doi": norm_doi(r.get("doi")),
                    "pmid": ident, "pmcid": norm_pmcid(r.get("pmcid")),
                    "journal": (r.get("journalInfo", {}) or {}).get("journal", {}).get("title", ""),
                    "year": str(r.get("pubYear", "")), "raw": r}
    except (AttributeError, IndexError, KeyError, TypeError):
        return None
    return None


def _no_fulltext(entry):
    """依据本地响应结构化字段判定全文不可得。"""
    raw = entry.get("raw", {}) if isinstance(entry, dict) else {}
    ft = raw.get("fullTextUrlList") if isinstance(raw, dict) else None
    if isinstance(ft, dict) and isinstance(ft.get("fullTextUrl"), list) \
            and not ft["fullTextUrl"]:
        return True
    return False


def _slim(entry):
    d = {k: entry.get(k) for k in
         ("file", "json_ptr", "title", "doi", "pmid", "pmcid", "journal", "year")}
    d["retracted"] = is_retracted(entry)
    d["no_fulltext_url"] = _no_fulltext(entry)
    return d


def _disp_reason(disp, flags):
    table = {
        "exclude_retracted": "本地响应含撤稿标记，移出可用分母。",
        "needs_manual_review": "存在未决异常：" + "、".join(flags),
        "flag_keep_no_fulltext": "本地响应无可及全文链接，保留为题录级分母成员，标记全文不可得。",
    }
    return table.get(disp, "正常纳入。")


if __name__ == "__main__":
    sys.exit(main())
