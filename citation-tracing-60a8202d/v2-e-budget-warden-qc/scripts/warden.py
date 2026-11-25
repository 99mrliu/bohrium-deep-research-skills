#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
warden.py — 分阶段编排器（budget-warden-qc 核心脚本）

阶段划分：
  stage0: 解析 case.json，立即写出 honest partial result.json（任何时刻中断都有可评交付）
  stage1: 递归 ingest 语料（Crossref / EuropePMC / OpenAlex / 通用 JSON / JSONL / CSV / TSV /
          edgelist / bib），全部记录带 source locator，checkpoint 到 workdir/checkpoints/stage1.json
  stage2: 种子解析 + 第 1 层扩展，落盘增强 result.json（status 仍为 partial，注明仅 1 层），checkpoint
  stage3: 加深至 --max-depth（默认 2）+ DOI/标题去重合并 + 反向索引恢复前向边，
          写最终 result.json（status=ok 或诚实 partial），checkpoint

特性：
  * --resume         从最近 checkpoint 断点续跑
  * --time-budget S  临近预算耗尽时跳过加深阶段，直接落盘当前最好版本
  * 确定性输出：所有遍历按排序键迭代、结果按稳定键排序、json 以 sort_keys 序列化；
    时间戳只写入 run_log.json，绝不进入 result.json —— 重复运行 result.json 字节一致。

仅使用 Python 3 标准库；默认完全离线；脚本位置无关（pathlib）。
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>}\)]+", re.IGNORECASE)
CORPUS_SUFFIXES = {".json", ".jsonl", ".csv", ".tsv", ".edgelist", ".bib"}
# 扫描候选根时跳过本管线自身产物，避免把 result/checkpoint 当语料
SKIP_NAMES = {
    "result.json", "run_log.json", "qc_report.json", "qc_report.md",
    "reproduce_report.json", "case.json", "task.md",
}
STAGE_NAMES = ["stage0_contract", "stage1_ingest", "stage2_shallow", "stage3_deepen"]
BIB_ENTRY_RE = re.compile(r"@\w+\s*\{\s*([^,]+),(.*?)\n\}", re.DOTALL)
BIB_FIELD_RE = re.compile(r"(\w+)\s*=\s*[\{\"](.*?)[\}\"]\s*,?\s*\n", re.DOTALL)


# ---------------------------------------------------------------- 基础工具

def utcnow():
    return datetime.now(timezone.utc).isoformat()


def sha1_text(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def sha1_file(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def canon(obj):
    """确定性 JSON 序列化（排序键、UTF-8、不转义非 ASCII）。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canon(obj), encoding="utf-8")


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_doi(doi):
    if not doi:
        return ""
    d = str(doi).strip().lower()
    for pre in ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:"):
        if d.startswith(pre):
            d = d[len(pre):]
    return d.strip().rstrip(".,;")


def normalize_title(title):
    if not title:
        return ""
    t = re.sub(r"[^0-9a-z一-鿿]+", " ", str(title).lower())
    return re.sub(r"\s+", " ", t).strip()


def rec_sort_key(rec):
    return (rec.get("doi") or "", normalize_title(rec.get("title") or ""), rec["record_id"])


class RunLog:
    """运行日志：唯一允许出现时间戳的地方。"""

    def __init__(self, workdir):
        self.path = Path(workdir) / "run_log.json"
        self.events = []
        if self.path.exists():
            try:
                self.events = read_json(self.path).get("events", [])
            except Exception:
                self.events = []

    def log(self, stage, msg):
        self.events.append({"time": utcnow(), "stage": stage, "msg": msg})
        write_json(self.path, {"events": self.events})


# ---------------------------------------------------------------- case.json 解析

SEED_KEYS = ("seed", "seeds", "seed_papers", "seed_paper", "seed_dois", "seed_doi",
             "seed_work", "seed_works", "seed_records")


def _seed_entries(obj):
    """把 seed 字段归一成 [{'doi':..,'title':..}] 列表。"""
    out = []

    def one(x):
        if isinstance(x, str):
            m = DOI_RE.search(x)
            if m:
                out.append({"doi": normalize_doi(m.group(0)), "title": None})
            else:
                out.append({"doi": None, "title": x})
        elif isinstance(x, dict):
            doi = x.get("doi") or x.get("DOI")
            out.append({"doi": normalize_doi(doi) if doi else None,
                        "title": x.get("title") or x.get("display_name")})
        elif isinstance(x, list):
            for y in x:
                one(y)

    one(obj)
    return out


def parse_case(case_path):
    case = read_json(case_path)
    case_id = case.get("case_id") or case.get("id") or "unknown-case"
    contract = case.get("output_contract") or case.get("outputContract") or {}
    if isinstance(contract, list):
        contract = {str(k): None for k in contract}
    if not isinstance(contract, dict):
        contract = {"result": None}
    seeds = []
    for k in SEED_KEYS:
        if k in case:
            seeds.extend(_seed_entries(case[k]))
    # 去重保持确定性顺序
    seen, uniq = set(), []
    for s in seeds:
        key = (s.get("doi") or "", s.get("title") or "")
        if key not in seen and key != ("", ""):
            seen.add(key)
            uniq.append(s)
    return {"case_id": case_id, "contract": contract, "seeds": uniq, "raw": case}


CONTRACT_FILL = {
    "caseid": "case_id", "status": "status", "seed": "seed", "seeds": "seed",
    "candidates": "candidates", "candidatelist": "candidates", "results": "candidates",
    "edges": "edges", "edge": "edges", "sources": "sources", "source": "sources",
    "evidence": "evidence_records", "evidencerecords": "evidence_records",
    "uncertainty": "uncertainty", "uncertainties": "uncertainty",
}


def mirror_contract(contract, doc, uncertainty):
    """逐字段镜像 output_contract：认识的字段填产物，不认识的置空并记 uncertainty。"""
    mirror = {}
    for key in contract:
        nk = re.sub(r"[^0-9a-z]", "", str(key).lower())
        target = CONTRACT_FILL.get(nk)
        if target and target in doc:
            mirror[key] = doc[target]
        else:
            mirror[key] = None
            note = "output_contract 字段 '%s' 无对应产物，按契约置空。" % key
            if note not in uncertainty:
                uncertainty.append(note)
    return mirror


# ---------------------------------------------------------------- 语料发现与解析

def iter_input_files(roots, workdir, outdir):
    skip_dirs = {str(Path(workdir).resolve()), str(Path(outdir).resolve())}
    files = []
    for root in roots:
        root = Path(root)
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in CORPUS_SUFFIXES:
                continue
            if p.name in SKIP_NAMES or "checkpoints" in p.parts:
                continue
            rp = str(p.resolve())
            if any(rp.startswith(d + os.sep) for d in skip_dirs):
                continue
            files.append(p)
    return sorted({str(p.resolve()): p for p in files}.values(), key=lambda x: str(x))


def _crossref_record(it, path, pointer):
    title = it.get("title")
    title = title[0] if isinstance(title, list) and title else title
    authors = []
    for a in it.get("author") or []:
        if isinstance(a, dict):
            name = ", ".join(x for x in (a.get("family"), a.get("given")) if x)
            if name:
                authors.append(name)
    year = None
    dp = ((it.get("issued") or {}).get("date-parts") or [[None]])[0]
    if dp and dp[0]:
        year = dp[0]
    venue = it.get("container-title")
    venue = venue[0] if isinstance(venue, list) and venue else venue
    refs = []
    for j, r in enumerate(it.get("reference") or []):
        if not isinstance(r, dict):
            r = {"unstructured": str(r)}
        refs.append({
            "doi": normalize_doi(r.get("DOI")) or None,
            "title": r.get("article-title"),
            "raw": r.get("unstructured") or r.get("key") or r.get("DOI") or "",
            "source": {"file": str(path), "pointer": "%s/reference/%d" % (pointer, j)},
        })
    return {
        "doi": normalize_doi(it.get("DOI")) or None, "title": title,
        "authors": authors, "year": year, "venue": venue,
        "openalex_id": None, "refs": refs,
        "source": {"file": str(path), "pointer": pointer},
    }


def _europepmc_record(it, path, pointer):
    authors = [a.strip() for a in (it.get("authorString") or "").split(";") if a.strip()]
    venue = ((it.get("journalInfo") or {}).get("journal") or {}).get("title")
    year = it.get("pubYear")
    try:
        year = int(year) if year else None
    except (TypeError, ValueError):
        year = None
    refs = []
    rlist = (it.get("referenceList") or {}).get("reference") or []
    for j, r in enumerate(rlist):
        if not isinstance(r, dict):
            r = {"citation": str(r)}
        refs.append({
            "doi": normalize_doi(r.get("doi")) or None,
            "title": r.get("title"),
            "raw": r.get("citation") or r.get("id") or "",
            "source": {"file": str(path), "pointer": "%s/referenceList/reference/%d" % (pointer, j)},
        })
    return {
        "doi": normalize_doi(it.get("doi")) or None, "title": it.get("title"),
        "authors": authors, "year": year, "venue": venue,
        "openalex_id": None, "refs": refs,
        "source": {"file": str(path), "pointer": pointer},
    }


def _openalex_record(it, path, pointer):
    authors = []
    for a in it.get("authorships") or []:
        name = ((a or {}).get("author") or {}).get("display_name")
        if name:
            authors.append(name)
    venue = (((it.get("primary_location") or {}).get("source") or {}) or {}).get("display_name")
    refs = []
    for j, wid in enumerate(it.get("referenced_works") or []):
        refs.append({"doi": None, "title": None, "raw": str(wid),
                     "source": {"file": str(path),
                                "pointer": "%s/referenced_works/%d" % (pointer, j)}})
    cites = []
    for j, wid in enumerate(it.get("cited_by_works") or it.get("citations") or []):
        cites.append({"raw": str(wid),
                      "source": {"file": str(path),
                                 "pointer": "%s/citations/%d" % (pointer, j)}})
    return {
        "doi": normalize_doi(it.get("doi")) or None,
        "title": it.get("display_name") or it.get("title"),
        "authors": authors, "year": it.get("publication_year"), "venue": venue,
        "openalex_id": it.get("id"), "refs": refs, "citations_raw": cites,
        "source": {"file": str(path), "pointer": pointer},
    }


def _generic_node(it, path, pointer):
    refs, cites = [], []
    for j, r in enumerate(it.get("references") or []):
        if isinstance(r, dict):
            refs.append({"doi": normalize_doi(r.get("doi") or r.get("DOI")) or None,
                         "title": r.get("title"), "raw": r.get("id") or r.get("raw") or "",
                         "source": {"file": str(path), "pointer": "%s/references/%d" % (pointer, j)}})
        else:
            m = DOI_RE.search(str(r))
            refs.append({"doi": normalize_doi(m.group(0)) if m else None,
                         "title": None, "raw": str(r),
                         "source": {"file": str(path), "pointer": "%s/references/%d" % (pointer, j)}})
    for j, r in enumerate(it.get("citations") or []):
        if isinstance(r, dict):
            cites.append({"doi": normalize_doi(r.get("doi") or r.get("DOI")) or None,
                          "title": r.get("title"), "raw": r.get("id") or "",
                          "source": {"file": str(path), "pointer": "%s/citations/%d" % (pointer, j)}})
        else:
            m = DOI_RE.search(str(r))
            cites.append({"doi": normalize_doi(m.group(0)) if m else None,
                          "title": None, "raw": str(r),
                          "source": {"file": str(path), "pointer": "%s/citations/%d" % (pointer, j)}})
    return {
        "doi": normalize_doi(it.get("doi") or it.get("DOI")) or None,
        "title": it.get("title") or it.get("display_name"),
        "authors": it.get("authors") if isinstance(it.get("authors"), list) else [],
        "year": it.get("year") or it.get("publication_year"),
        "venue": it.get("venue") or it.get("journal"),
        "openalex_id": it.get("openalex_id"), "refs": refs, "citations_raw": cites,
        "source": {"file": str(path), "pointer": pointer},
    }


def parse_json_obj(obj, path):
    """返回 (records, edges, format_name)。edges 为裸边（source_raw/target_raw）。"""
    records, edges, fmt = [], [], "unknown-json"
    if isinstance(obj, dict) and "message" in obj:
        msg = obj["message"]
        if isinstance(msg, dict) and isinstance(msg.get("items"), list):
            fmt = "crossref-batch"
            for i, it in enumerate(msg["items"]):
                records.append(_crossref_record(it, path, "/message/items/%d" % i))
        elif isinstance(msg, dict):
            fmt = "crossref-single"
            records.append(_crossref_record(msg, path, "/message"))
    elif isinstance(obj, dict) and isinstance((obj.get("resultList") or {}).get("result"), list):
        fmt = "europepmc"
        for i, it in enumerate(obj["resultList"]["result"]):
            records.append(_europepmc_record(it, path, "/resultList/result/%d" % i))
    elif isinstance(obj, dict) and isinstance(obj.get("results"), list):
        fmt = "openalex-or-generic-results"
        for i, it in enumerate(obj["results"]):
            records.append(_openalex_record(it, path, "/results/%d" % i))
    elif isinstance(obj, dict) and ("referenced_works" in obj or "display_name" in obj):
        fmt = "openalex-single"
        records.append(_openalex_record(obj, path, "/"))
    elif isinstance(obj, dict) and isinstance(obj.get("edges") or obj.get("links"), list):
        fmt = "generic-edge-json"
        for i, e in enumerate(obj.get("edges") or obj.get("links")):
            edges.append({"source_raw": e.get("source"), "target_raw": e.get("target"),
                          "edge_type": e.get("type") or "reference",
                          "source": {"file": str(path), "pointer": "/edges/%d" % i}})
        for i, n in enumerate(obj.get("nodes") or []):
            records.append(_generic_node(n, path, "/nodes/%d" % i))
    elif isinstance(obj, list):
        fmt = "generic-node-list"
        for i, it in enumerate(obj):
            if isinstance(it, dict):
                records.append(_generic_node(it, path, "/%d" % i))
    elif isinstance(obj, dict) and ("doi" in obj or "DOI" in obj or "title" in obj):
        fmt = "generic-single-node"
        records.append(_generic_node(obj, path, "/"))
    return records, edges, fmt


def parse_jsonl(path):
    records, edges = [], []
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    for i, ln in enumerate(lines):
        try:
            obj = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and ("source" in obj and "target" in obj):
            edges.append({"source_raw": obj.get("source"), "target_raw": obj.get("target"),
                          "edge_type": obj.get("type") or "reference",
                          "source": {"file": str(path), "pointer": "line %d" % (i + 1)}})
        elif isinstance(obj, dict):
            if "referenced_works" in obj or "display_name" in obj:
                records.append(_openalex_record(obj, path, "line %d" % (i + 1)))
            else:
                records.append(_generic_node(obj, path, "line %d" % (i + 1)))
    return records, edges, "jsonl(%d lines)" % len(lines)


def parse_table(path):
    suffix = path.suffix.lower()
    with open(path, "r", encoding="utf-8", newline="") as f:
        text = f.read()
    if suffix == ".edgelist":
        rows = [ln.split() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
        header = None
    else:
        delim = "\t" if suffix == ".tsv" else ","
        rows = [r for r in csv.reader(text.splitlines(), delimiter=delim) if any(c.strip() for c in r)]
        header = [c.strip().lower() for c in rows[0]] if rows else None
        if header and not any(DOI_RE.search(c) for c in rows[0]):
            rows = rows[1:]
        else:
            header = None
    edges = []
    src_i = tgt_i = typ_i = None
    if header:
        for i, name in enumerate(header):
            if name in ("source", "source_doi", "citing", "from", "src"):
                src_i = i
            elif name in ("target", "target_doi", "cited", "to", "dst"):
                tgt_i = i
            elif name in ("type", "edge_type", "relation"):
                typ_i = i
    src_i = src_i if src_i is not None else 0
    tgt_i = tgt_i if tgt_i is not None else 1
    for i, row in enumerate(rows):
        if len(row) <= max(src_i, tgt_i):
            continue
        edges.append({
            "source_raw": row[src_i].strip(), "target_raw": row[tgt_i].strip(),
            "edge_type": (row[typ_i].strip() if typ_i is not None and len(row) > typ_i
                          else "reference") or "reference",
            "source": {"file": str(path), "pointer": "line %d" % (i + (2 if header else 1))},
        })
    return [], edges, ("table:%s" % suffix.lstrip("."))


def parse_bib(path):
    text = path.read_text(encoding="utf-8")
    records = []
    for i, m in enumerate(BIB_ENTRY_RE.finditer(text)):
        fields = {k.lower(): v.strip() for k, v in BIB_FIELD_RE.findall(m.group(2))}
        authors = [a.strip() for a in re.split(r"\s+and\s+", fields.get("author", "")) if a.strip()]
        year = fields.get("year")
        try:
            year = int(year) if year else None
        except ValueError:
            year = None
        records.append({
            "doi": normalize_doi(fields.get("doi")) or None, "title": fields.get("title"),
            "authors": authors, "year": year,
            "venue": fields.get("journal") or fields.get("booktitle"),
            "openalex_id": None, "refs": [],
            "source": {"file": str(path), "pointer": "entry %d (@%s)" % (i, m.group(1))},
        })
    return records, [], "bibtex"


def parse_file(path):
    suffix = path.suffix.lower()
    if suffix == ".json":
        return parse_json_obj(read_json(path), path)
    if suffix == ".jsonl":
        return parse_jsonl(path)
    if suffix in (".csv", ".tsv", ".edgelist"):
        return parse_table(path)
    if suffix == ".bib":
        return parse_bib(path)
    return [], [], "unsupported"


# ---------------------------------------------------------------- 语料库（身份合并）

class Corpus:
    """DOI 规范化精确键 + 标题规范化键的身份合并；两键都缺失的记录保持独立。"""

    def __init__(self):
        self.records = {}
        self.doi_index = {}
        self.title_index = {}
        self.oa_index = {}

    def _rid(self, doi_key, title_key):
        if doi_key:
            return "doi:" + doi_key
        if title_key:
            return "t:" + sha1_text(title_key)[:12]
        return "anon:" + sha1_text(json.dumps("x"))[:12]

    def add(self, raw):
        doi_key = normalize_doi(raw.get("doi"))
        title_key = normalize_title(raw.get("title"))
        rid = None
        if doi_key and doi_key in self.doi_index:
            rid = self.doi_index[doi_key]
        elif title_key and title_key in self.title_index:
            rid = self.title_index[title_key]
        if rid is None:
            rid = self._rid(doi_key, title_key)
            n = 0
            base = rid
            while rid in self.records:
                n += 1
                rid = "%s#%d" % (base, n)
            self.records[rid] = {
                "record_id": rid, "kind": "resolved",
                "doi": raw.get("doi"), "title": raw.get("title"),
                "authors": raw.get("authors") or [], "year": raw.get("year"),
                "venue": raw.get("venue"), "openalex_id": raw.get("openalex_id"),
                "refs": [], "citations_raw": [], "source": raw.get("source"),
                "extra_sources": [],
            }
        rec = self.records[rid]
        # 字段补缺合并（不覆盖已有值，冲突保留在 extra_sources 可回指）
        for fld in ("doi", "title", "year", "venue", "openalex_id"):
            if not rec.get(fld) and raw.get(fld):
                rec[fld] = raw[fld]
        if raw.get("authors") and not rec.get("authors"):
            rec["authors"] = raw["authors"]
        if raw.get("source") and raw["source"] != rec.get("source"):
            if raw["source"] not in rec["extra_sources"]:
                rec["extra_sources"].append(raw["source"])
        for ref in raw.get("refs") or []:
            rec["refs"].append(ref)
        for c in raw.get("citations_raw") or []:
            rec["citations_raw"].append(c)
        if doi_key:
            self.doi_index[doi_key] = rid
        if title_key:
            self.title_index[title_key] = rid
        if rec.get("openalex_id"):
            self.oa_index[rec["openalex_id"]] = rid
        return rid

    def resolve(self, doi=None, title=None, raw=None):
        if doi:
            rid = self.doi_index.get(normalize_doi(doi))
            if rid:
                return rid
        if title:
            rid = self.title_index.get(normalize_title(title))
            if rid:
                return rid
        if raw and str(raw) in self.oa_index:
            return self.oa_index[str(raw)]
        if raw:
            m = DOI_RE.search(str(raw))
            if m:
                return self.doi_index.get(normalize_doi(m.group(0)))
        return None

    def get_or_stub(self, doi=None, title=None, raw=None, source=None):
        rid = self.resolve(doi=doi, title=title, raw=raw)
        if rid:
            return rid, False
        doi_key = normalize_doi(doi)
        title_key = normalize_title(title)
        if doi_key:
            rid = "doi:" + doi_key
        elif title_key:
            rid = "t:" + sha1_text(title_key)[:12]
        else:
            rid = "stub:" + sha1_text(str(raw))[:12]
        if rid not in self.records:
            # 诚实 stub：只保留原始指针与定位，绝不补造作者/年份/标题
            self.records[rid] = {
                "record_id": rid, "kind": "stub",
                "doi": doi_key or None, "title": None, "authors": [], "year": None,
                "venue": None, "openalex_id": None, "refs": [], "citations_raw": [],
                "raw_pointer": raw or doi or title or "",
                "source": source, "extra_sources": [],
            }
        return rid, True


def corpus_from_checkpoint(data):
    c = Corpus()
    c.records = data["records"]
    for rid, rec in c.records.items():
        dk = normalize_doi(rec.get("doi"))
        tk = normalize_title(rec.get("title"))
        if dk:
            c.doi_index[dk] = rid
        if tk:
            c.title_index[tk] = rid
        if rec.get("openalex_id"):
            c.oa_index[rec["openalex_id"]] = rid
    return c


# ---------------------------------------------------------------- 图构建与扩展

def build_graph(corpus, raw_edges):
    """reference 边 = citing→cited；数据源只给参考文献列表时用反向索引恢复 citation 边。"""
    edges = {}

    def add_edge(src, dst, etype, restored, source, extra=None):
        if src == dst:
            return
        key = (src, dst, etype)
        if key in edges:
            return
        e = {"source_id": src, "target_id": dst, "type": etype,
             "direction_restored": restored, "source": source}
        if extra:
            e.update(extra)
        edges[key] = e

    for rid in sorted(corpus.records, key=lambda r: rec_sort_key(corpus.records[r])):
        rec = corpus.records[rid]
        for ref in rec.get("refs") or []:
            tgt, _ = corpus.get_or_stub(doi=ref.get("doi"), title=ref.get("title"),
                                        raw=ref.get("raw"), source=ref.get("source"))
            add_edge(rid, tgt, "reference", False, ref.get("source"))
        for cit in rec.get("citations_raw") or []:
            src, _ = corpus.get_or_stub(doi=cit.get("doi"), title=cit.get("title"),
                                        raw=cit.get("raw"), source=cit.get("source"))
            add_edge(src, rid, "citation", False, cit.get("source"))
    for re_ in raw_edges:
        sraw, traw = re_.get("source_raw"), re_.get("target_raw")
        sd = normalize_doi(sraw) if sraw and DOI_RE.search(str(sraw)) else None
        td = normalize_doi(traw) if traw and DOI_RE.search(str(traw)) else None
        src, _ = corpus.get_or_stub(doi=sd, title=None if sd else sraw,
                                    raw=sraw, source=re_.get("source"))
        tgt, _ = corpus.get_or_stub(doi=td, title=None if td else traw,
                                    raw=traw, source=re_.get("source"))
        add_edge(src, tgt, re_.get("edge_type") or "reference", False, re_.get("source"))
    # 反向索引：由 reference 边恢复前向 citation 边
    for (src, dst, etype), e in sorted(list(edges.items())):
        if etype == "reference":
            add_edge(dst, src, "citation", True, e.get("source"),
                     {"restored_from": "%s->%s" % (src, dst)})
    return edges


def bfs_expand(corpus, edges, seed_rids, max_depth):
    adj = {}
    for (src, dst, etype) in edges:
        adj.setdefault(src, []).append((dst, (src, dst, etype)))
        adj.setdefault(dst, []).append((src, (src, dst, etype)))
    for k in adj:
        # 优先选择从当前节点出发的边（自然方向），再按邻居稳定键与边类型排序，
        # 保证 via_edge 记录的是语义上最自然的来路边。
        adj[k].sort(key=lambda x: (0 if x[1][0] == k else 1,
                                   rec_sort_key(corpus.records[x[0]]), x[1][2]))
    hop = {}
    via = {}
    frontier = sorted(seed_rids, key=lambda r: rec_sort_key(corpus.records[r]))
    for rid in frontier:
        hop[rid] = 0
    depth = 0
    while frontier and depth < max_depth:
        nxt = []
        for rid in frontier:
            for nb, ekey in adj.get(rid, []):
                if nb not in hop:
                    hop[nb] = depth + 1
                    via[nb] = ekey
                    nxt.append(nb)
        frontier = nxt
        depth += 1
    return hop, via


def make_candidates(corpus, hop, via, edges):
    cands = []
    for rid in sorted(hop, key=lambda r: (hop[r], rec_sort_key(corpus.records[r]))):
        rec = corpus.records[rid]
        c = {"record_id": rid, "kind": rec["kind"], "doi": rec.get("doi"),
             "title": rec.get("title"), "authors": rec.get("authors") or [],
             "year": rec.get("year"), "venue": rec.get("venue"),
             "hop": hop[rid], "source": rec.get("source")}
        if rec["kind"] == "stub":
            c["raw_pointer"] = rec.get("raw_pointer")
        if rid in via:
            src, dst, etype = via[rid]
            c["via_edge"] = {"source_id": src, "target_id": dst, "type": etype,
                             "direction_restored": edges[(src, dst, etype)]["direction_restored"]}
        cands.append(c)
    return cands


def make_evidence(cands, edges):
    ev = []
    for c in cands:
        if c["hop"] == 0:
            ev.append({"record_id": c["record_id"], "kind": "seed-resolution",
                       "note": "种子记录，按 DOI/标题键在语料中解析。",
                       "source": c.get("source")})
        else:
            ve = c.get("via_edge") or {}
            ekey = (ve.get("source_id"), ve.get("target_id"), ve.get("type"))
            e = edges.get(ekey, {})
            ev.append({"record_id": c["record_id"], "kind": "expansion",
                       "hop": c["hop"], "via_edge": ve,
                       "note": "沿 %s 边第 %d 层扩展到达。" % (ve.get("type"), c["hop"]),
                       "source": e.get("source")})
    return sorted(ev, key=lambda x: (x["record_id"], x["kind"]))


def candidate_edges(edges, hop):
    out = [e for (s, t, ty), e in edges.items() if s in hop and t in hop]
    return sorted(out, key=lambda e: (e["source_id"], e["target_id"], e["type"]))


# ---------------------------------------------------------------- 结果落盘

def write_result(outdir, state, status, max_depth_reached, completed_stage,
                 budget_limited, extra_uncertainty):
    uncertainty = list(state.get("uncertainty") or [])
    for u in extra_uncertainty or []:
        if u not in uncertainty:
            uncertainty.append(u)
    doc = {
        "case_id": state["case_id"],
        "status": status,
        "seed": state.get("seed_view") or {"declared": state["seeds"],
                                           "resolved": [], "unresolved": []},
        "candidates": state.get("candidates") or [],
        "edges": state.get("result_edges") or [],
        "sources": state.get("sources") or [],
        "evidence_records": state.get("evidence") or [],
        "uncertainty": uncertainty,
        "stage_summary": {
            "pipeline": STAGE_NAMES,
            "completed_stage": completed_stage,
            "max_depth_reached": max_depth_reached,
            "budget_limited": bool(budget_limited),
        },
    }
    doc["contract"] = mirror_contract(state["contract"], doc, uncertainty)
    doc["uncertainty"] = uncertainty
    write_json(Path(outdir) / "result.json", doc)
    return doc


def write_checkpoint(workdir, idx, payload):
    cp = {"stage": idx, "stage_name": STAGE_NAMES[idx], "finished_at": utcnow(),
          "artifact_sha1": sha1_text(canon(payload)), "data": payload}
    write_json(Path(workdir) / "checkpoints" / ("stage%d.json" % idx), cp)


def detect_resume(workdir):
    cpdir = Path(workdir) / "checkpoints"
    best = -1
    if cpdir.is_dir():
        for p in cpdir.glob("stage*.json"):
            try:
                cp = read_json(p)
                best = max(best, int(cp.get("stage", -1)))
            except Exception:
                continue
    return best


def load_checkpoint(workdir, idx):
    return read_json(Path(workdir) / "checkpoints" / ("stage%d.json" % idx))["data"]


# ---------------------------------------------------------------- 主流程

def main(argv=None):
    ap = argparse.ArgumentParser(description="分阶段引文追踪编排器（budget-warden-qc）")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--workdir", default="/app/work")
    ap.add_argument("--roots", nargs="*", default=None,
                    help="语料候选根；缺省按 /input > /app/work > cwd 顺序扫描")
    ap.add_argument("--max-depth", type=int, default=2)
    ap.add_argument("--resume", action="store_true", help="从最近 checkpoint 续跑")
    ap.add_argument("--time-budget", type=int, default=850, help="秒；临近耗尽时降级落盘")
    ap.add_argument("--margin", type=int, default=30, help="预算安全余量（秒）")
    args = ap.parse_args(argv)

    t0 = time.monotonic()
    outdir, workdir = Path(args.out), Path(args.workdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (workdir / "checkpoints").mkdir(parents=True, exist_ok=True)
    log = RunLog(workdir)

    def budget_ok(stage_name):
        remain = args.time_budget - (time.monotonic() - t0)
        ok = remain > args.margin
        log.log(stage_name, "budget check: remaining=%.1fs margin=%ds -> %s"
                % (remain, args.margin, "go" if ok else "SKIP"))
        return ok

    resumed_from = detect_resume(workdir) if args.resume else -1
    if args.resume:
        log.log("resume", "resume requested; latest checkpoint stage=%d" % resumed_from)

    state = {"uncertainty": []}

    # ---------- stage0: 契约优先的 honest partial ----------
    if resumed_from < 0:
        if not Path(args.case).exists():
            state.update({"case_id": "unknown-case", "contract": {}, "seeds": []})
            state["uncertainty"].append("case.json 不存在于 %s；仅输出空骨架。" % args.case)
            write_result(outdir, state, "failed", 0, 0, False,
                         ["无法读取案例输入，管线中止于 stage0。"])
            log.log("stage0", "case.json missing -> failed skeleton written")
            return 2
        caseinfo = parse_case(args.case)
        state.update(caseinfo)
        write_result(outdir, state, "partial", 0, 0, False,
                     ["扩展未完成：stage0 仅完成 case.json 解析，候选集为空属预期中间状态。"])
        write_checkpoint(workdir, 0, {"case_id": state["case_id"],
                                      "seeds": state["seeds"],
                                      "contract_keys": sorted(state["contract"])})
        log.log("stage0", "honest partial result.json written (case_id=%s, seeds=%d)"
                % (state["case_id"], len(state["seeds"])))
    else:
        cp0 = load_checkpoint(workdir, 0) if (Path(workdir) / "checkpoints" / "stage0.json").exists() else None
        if cp0:
            caseinfo = parse_case(args.case) if Path(args.case).exists() else \
                {"case_id": cp0["case_id"], "contract": {}, "seeds": cp0.get("seeds", []), "raw": {}}
        else:
            caseinfo = parse_case(args.case)
        state.update(caseinfo)
        log.log("stage0", "skipped (resume)")

    # ---------- stage1: ingest ----------
    corpus, raw_edges = None, []
    if resumed_from >= 1:
        payload = load_checkpoint(workdir, 1)
        corpus = corpus_from_checkpoint(payload["corpus_records"])
        raw_edges = payload["raw_edges"]
        state["sources"] = payload["sources"]
        log.log("stage1", "skipped (resume); loaded %d records, %d raw edges"
                % (len(corpus.records), len(raw_edges)))
    elif not budget_ok("stage1"):
        write_result(outdir, state, "partial", 0, 0, True,
                     ["预算临近耗尽，stage1 ingest 未执行；保留 stage0 骨架。"])
        log.log("stage1", "skipped due to budget")
        return 0
    else:
        if args.roots:
            roots = [Path(r) for r in args.roots]
        else:
            roots = [Path(p) for p in ("/input", "/app/work", os.getcwd()) if Path(p).is_dir()]
        corpus = Corpus()
        sources = []
        for path in iter_input_files(roots, workdir, outdir):
            entry = {"file": str(path), "sha1": None, "format": None,
                     "records": 0, "edges": 0, "parse_ok": False, "error": None}
            try:
                entry["sha1"] = sha1_file(path)
                recs, eds, fmt = parse_file(path)
                entry["format"] = fmt
                for r in recs:
                    corpus.add(r)
                raw_edges.extend(eds)
                entry["records"], entry["edges"], entry["parse_ok"] = len(recs), len(eds), True
            except Exception as exc:  # 解析失败记入来源注册表而不是中断
                entry["error"] = "%s: %s" % (type(exc).__name__, exc)
                state["uncertainty"].append("语料文件解析失败：%s（%s）" % (path, entry["error"]))
            sources.append(entry)
        sources.sort(key=lambda s: s["file"])
        state["sources"] = sources
        payload = {"corpus_records": {"records": corpus.records},
                   "raw_edges": raw_edges, "sources": sources}
        write_checkpoint(workdir, 1, payload)
        log.log("stage1", "ingested %d files, %d records, %d raw edges"
                % (len(sources), len(corpus.records), len(raw_edges)))

    # ---------- 种子解析 ----------
    resolved, unresolved = [], []
    for s in state["seeds"]:
        rid = corpus.resolve(doi=s.get("doi"), title=s.get("title"))
        if rid:
            resolved.append({"seed": s, "record_id": rid})
        else:
            unresolved.append(s)
    state["seed_view"] = {"declared": state["seeds"], "resolved": resolved,
                          "unresolved": unresolved}
    for s in unresolved:
        state["uncertainty"].append(
            "种子未能在语料中解析：%s（保留声明信息，不补造元数据）。"
            % (s.get("doi") or s.get("title")))
    log.log("seed", "resolved=%d unresolved=%d" % (len(resolved), len(unresolved)))

    # ---------- stage2: 第 1 层扩展 ----------
    graph_edges = None
    if resumed_from >= 2:
        payload = load_checkpoint(workdir, 2)
        graph_edges = {(e["source_id"], e["target_id"], e["type"]): e
                       for e in payload["graph_edges"]}
        # stub 节点可能是在 stage2 建图时新建的，需回填 corpus
        corpus = corpus_from_checkpoint(payload["corpus_records"])
        state["candidates"] = payload["candidates"]
        state["result_edges"] = payload["result_edges"]
        state["evidence"] = payload["evidence"]
        log.log("stage2", "skipped (resume); loaded graph with %d edges" % len(graph_edges))
    elif not resolved:
        state["uncertainty"].append("无可解析种子，扩展阶段跳过。")
        write_result(outdir, state, "partial", 0, 1, False, [])
        log.log("stage2", "no resolved seeds -> partial written")
        return 0
    elif not budget_ok("stage2"):
        write_result(outdir, state, "partial", 0, 1, True,
                     ["预算临近耗尽，stage2 浅层扩展未执行；结果停留在 ingest 后状态。"])
        log.log("stage2", "skipped due to budget")
        return 0
    else:
        graph_edges = build_graph(corpus, raw_edges)
        seed_rids = [r["record_id"] for r in resolved]
        hop, via = bfs_expand(corpus, graph_edges, seed_rids, 1)
        cands = make_candidates(corpus, hop, via, graph_edges)
        state["candidates"] = cands
        state["result_edges"] = candidate_edges(graph_edges, hop)
        state["evidence"] = make_evidence(cands, graph_edges)
        write_result(outdir, state, "partial", 1, 2, False,
                     ["当前仅完成第 1 层扩展（stage2），加深与全局合并未完成。"])
        payload = {"corpus_records": {"records": corpus.records},
                   "graph_edges": [graph_edges[k] for k in sorted(graph_edges)],
                   "candidates": state["candidates"],
                   "result_edges": state["result_edges"],
                   "evidence": state["evidence"]}
        write_checkpoint(workdir, 2, payload)
        log.log("stage2", "depth-1 expansion: %d candidates, %d edges"
                % (len(cands), len(state["result_edges"])))

    # ---------- stage3: 加深 + 去重合并 + 最终落盘 ----------
    if resumed_from >= 3:
        log.log("stage3", "already completed; nothing to do")
        print("resume: stage3 checkpoint exists, pipeline already finished.")
        return 0
    if not budget_ok("stage3"):
        write_result(outdir, state, "partial", 1, 2, True,
                     ["预算临近耗尽，stage3 加深扩展被跳过；当前为第 1 层扩展的诚实 partial。"])
        log.log("stage3", "skipped due to budget; best-effort partial kept")
        return 0
    seed_rids = [r["record_id"] for r in state["seed_view"]["resolved"]]
    hop, via = bfs_expand(corpus, graph_edges, seed_rids, args.max_depth)
    cands = make_candidates(corpus, hop, via, graph_edges)
    state["candidates"] = cands
    state["result_edges"] = candidate_edges(graph_edges, hop)
    state["evidence"] = make_evidence(cands, graph_edges)
    stubs = sum(1 for c in cands if c["kind"] == "stub")
    final_unc = []
    if state["seed_view"]["unresolved"]:
        final_unc.append("存在未解析种子 %d 个，覆盖不完整。" % len(state["seed_view"]["unresolved"]))
    if stubs:
        final_unc.append(
            "%d 条记录为 stub（语料内无法解析的引用目标），仅保留原始指针与定位，未补造元数据。" % stubs)
    status = "ok" if not state["seed_view"]["unresolved"] else "partial"
    write_result(outdir, state, status, args.max_depth, 3, False, final_unc)
    write_checkpoint(workdir, 3, {
        "candidates": len(cands), "edges": len(state["result_edges"]),
        "stubs": stubs, "status": status, "max_depth": args.max_depth,
        "result_sha1": sha1_file(Path(outdir) / "result.json"),
    })
    log.log("stage3", "final result: status=%s candidates=%d edges=%d stubs=%d"
            % (status, len(cands), len(state["result_edges"]), stubs))
    print("warden done: status=%s candidates=%d edges=%d stubs=%d"
          % (status, len(cands), len(state["result_edges"]), stubs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
