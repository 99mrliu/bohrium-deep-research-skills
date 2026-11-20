#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""map_fields.py — 跨库字段标准化：按 references/field_map_*.md 的映射表把
crossref / europepmc / publisher / recordlist / jsonl / csv 原始记录归一为
“字段卡片”，输出 /app/work/field_cards.jsonl（每行一条记录一张卡片）。

卡片结构：
  {record_uid, source, source_file, item_index, cluster_key, retracted,
   fields: {field: {status: present|missing|unknown|not_provided,
                    value, source_path, raw_excerpt}},
   warnings: []}

缺失三级语义判定（完整伪代码见 references/gap_taxonomy.md §0）：
  present      来源提供该字段且本条记录值非空、可解析；
  unknown      来源提供该字段，本条记录字段存在但为空 / 无法解析（告警留痕）；
  missing      同一响应载荷中其他记录出现该字段，本条记录键缺失；
  not_provided 来源 schema 不提供（静态清单）或本响应载荷整体无此字段（动态判定）。

清洗规则（与 references/field_map_*.md 一一对应）：
  DOI 去 https://doi.org/ 前缀并小写；abstract 剥离 HTML 标签并反转义实体；
  作者统一为 [{family, given}]（"Family, Given" 与 "Family II" 两种串格式）；
  Crossref 的 issued / published-print / published-online 语义不等价：
  year 取 issued，pub_date 按 print→online→issued 优先级，二者不一致时告警留痕。

本脚本只按 标识符（DOI/PMID）+ 归一题名+年份 做最小必要聚类键（cluster_key），
不做模糊匹配（模糊去重属 identitymerge-dedup-engine 方向）。

退出码：0=完成；2=case_summary 缺失或无可用记录（诚实降级）；3=输入文件非法。
顶层 try/except 汇总 exit 2，绝不崩溃、绝不静默吞掉解析失败。
"""
import argparse
import csv
import html
import json
import os
import re
import sys

FIELDS = [
    "identifiers.doi", "identifiers.pmid", "identifiers.pmcid",
    "title", "authors", "container", "year", "volume", "issue", "pages",
    "type", "abstract", "pub_date", "cited_by", "references", "license",
    "status",
]

# 静态 not_provided 清单（schema 层确定不提供；其余 not_provided 由载荷动态判定）
STATIC_NOT_PROVIDED = {
    "crossref": {"identifiers.pmid", "identifiers.pmcid"},
    "europepmc": set(),
    "publisher": set(),
    "recordlist": set(),
    "jsonl": set(),
    "csv": set(),
}

SOURCE_PRIORITY = ["crossref", "europepmc", "publisher", "recordlist",
                   "jsonl", "csv", "unknown"]

DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.I)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
NONALNUM_RE = re.compile(r"[^0-9a-z]+")
RETRACT_RE = re.compile(r"retract|withdraw", re.I)
INITIAL_RE = re.compile(r"^[A-Z]{1,4}$")
YEAR_RE = re.compile(r"(19|20)\d{2}")

RAW_EXCERPT_LEN = 160


# ---------------------------------------------------------------- 基础清洗

def clean_doi(v):
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    return DOI_PREFIX.sub("", s).lower() or None


def strip_html(s):
    if s is None:
        return None
    t = TAG_RE.sub(" ", str(s))
    t = html.unescape(t)
    return WS_RE.sub(" ", t).strip() or None


def norm_ws(s):
    if s is None:
        return None
    return WS_RE.sub(" ", str(s)).strip() or None


def norm_title(s):
    if s is None:
        return None
    return NONALNUM_RE.sub(" ", str(s).lower()).strip() or None


def parse_year(v):
    if v is None:
        return None
    if isinstance(v, int):
        return v if 1500 <= v <= 2100 else None
    m = YEAR_RE.search(str(v))
    return int(m.group(0)) if m else None


def parse_int(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return None


def raw_excerpt(v):
    if v is None:
        return None
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return s[:RAW_EXCERPT_LEN]


def ent(found, value=None, path=None, raw=None, warn=None):
    return {"found": found, "value": value, "source_path": path,
            "raw_excerpt": raw_excerpt(raw), "warning": warn}


def is_empty(v):
    return v is None or v == "" or v == [] or v == {}


# ---------------------------------------------------------------- 作者解析

def parse_author_name(s):
    """解析单个作者串。支持 'Family, Given' 与 'Family II'（EuropePMC 风格）。
    返回 ({family, given} 或 None, warning 或 None)。"""
    t = norm_ws(s)
    if not t:
        return None, "空作者名"
    if "," in t:
        fam, _, giv = t.partition(",")
        return {"family": fam.strip(), "given": giv.strip()}, None
    toks = t.split()
    if len(toks) == 1:
        return {"family": toks[0], "given": ""}, "作者名仅单 token，family/given 不可分"
    i = len(toks)
    while i > 1 and INITIAL_RE.match(toks[i - 1].replace(".", "")):
        i -= 1
    family = " ".join(toks[:i])
    given = " ".join(toks[i:])
    if not given:
        return {"family": t, "given": ""}, "作者名无首字母尾缀，整体记为 family"
    return {"family": family, "given": given}, None


def normalize_authors(raw):
    """统一作者为 [{family, given}]。返回 (value 或 None, warnings[list])。"""
    warns = []
    out = []
    if isinstance(raw, str):
        parts = [p for p in re.split(r"\s*;\s*|\s+and\s+", raw) if p.strip()]
        for p in parts:
            a, w = parse_author_name(p)
            if a:
                out.append(a)
            if w:
                warns.append("%s: %r" % (w, p))
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                fam = (item.get("family") or item.get("last")
                       or item.get("surname") or item.get("lastName") or "")
                giv = (item.get("given") or item.get("first")
                       or item.get("initials") or item.get("firstName") or "")
                if not fam and item.get("fullName"):
                    a, w = parse_author_name(item["fullName"])
                    if a:
                        out.append(a)
                    if w:
                        warns.append("%s: %r" % (w, item.get("fullName")))
                    continue
                if not fam and not giv:
                    warns.append("作者条目缺 family/given: %r" % raw_excerpt(item))
                    continue
                out.append({"family": str(fam), "given": str(giv)})
            elif isinstance(item, str):
                a, w = parse_author_name(item)
                if a:
                    out.append(a)
                if w:
                    warns.append("%s: %r" % (w, item))
            else:
                warns.append("作者条目类型无法解析: %s" % type(item).__name__)
    elif raw is None:
        return None, warns
    else:
        return None, ["authors 字段类型无法解析: %s" % type(raw).__name__]
    return (out or None), warns


# ---------------------------------------------------------------- Crossref

def crossref_records(obj):
    if isinstance(obj, dict):
        msg = obj.get("message")
        if isinstance(msg, dict):
            if isinstance(msg.get("items"), list):
                return msg["items"]
            if "DOI" in msg or "title" in msg:
                return [msg]
        if "DOI" in obj and "title" in obj:
            return [obj]
    return []


def cr_dateparts(item, keys):
    for k in keys:
        d = item.get(k)
        if isinstance(d, dict):
            dp = d.get("date-parts")
            if isinstance(dp, list) and dp and isinstance(dp[0], list) and dp[0]:
                return k, dp[0]
    return None, None


def fmt_dateparts(parts):
    out = [str(parts[0])]
    if len(parts) > 1:
        out.append("%02d" % int(parts[1]))
    if len(parts) > 2:
        out.append("%02d" % int(parts[2]))
    return "-".join(out)


def extract_crossref(item, path, idx):
    f = {}
    warns = []
    f["identifiers.doi"] = ent("DOI" in item, clean_doi(item.get("DOI")),
                               "DOI", item.get("DOI"))
    f["identifiers.pmid"] = ent(False)   # 静态 not_provided
    f["identifiers.pmcid"] = ent(False)  # 静态 not_provided
    tl = item.get("title")
    tv = None
    if isinstance(tl, list) and tl:
        tv = norm_ws(tl[0])
    elif isinstance(tl, str):
        tv = norm_ws(tl)
    f["title"] = ent("title" in item, tv, "title[0]", tl)
    if "author" in item:
        av, aw = normalize_authors(item.get("author"))
        warns.extend(aw)
        f["authors"] = ent(True, av, "author[*]", item.get("author"))
    else:
        f["authors"] = ent(False)
    ct = item.get("container-title")
    cv = norm_ws(ct[0]) if isinstance(ct, list) and ct else norm_ws(ct)
    f["container"] = ent("container-title" in item, cv, "container-title[0]", ct)
    # year 取 issued（收录日期语义）；pub_date 取 print→online→issued
    yk, yp = cr_dateparts(item, ("issued", "published-print",
                                 "published-online", "published", "created"))
    f["year"] = ent(yk is not None, (yp[0] if yp else None),
                    "%s.date-parts[0][0]" % yk if yk else None,
                    item.get(yk) if yk else None)
    pk, pp = cr_dateparts(item, ("published-print", "published-online",
                                 "issued", "published", "created"))
    f["pub_date"] = ent(pk is not None, (fmt_dateparts(pp) if pp else None),
                        "%s.date-parts[0]" % pk if pk else None,
                        item.get(pk) if pk else None)
    _k1, p1 = cr_dateparts(item, ("published-print",))
    _k2, p2 = cr_dateparts(item, ("published-online",))
    if p1 and p2 and p1 != p2:
        warns.append("published-print(%s) 与 published-online(%s) 不一致：二者语义"
                     "不等价（见 references/field_map_crossref.md），pub_date 已按 "
                     "print 优先取值" % (fmt_dateparts(p1), fmt_dateparts(p2)))
    f["volume"] = ent("volume" in item, norm_ws(item.get("volume")),
                      "volume", item.get("volume"))
    f["issue"] = ent("issue" in item, norm_ws(item.get("issue")),
                     "issue", item.get("issue"))
    f["pages"] = ent("page" in item, norm_ws(item.get("page")),
                     "page", item.get("page"))
    f["type"] = ent("type" in item, norm_ws(item.get("type")),
                    "type", item.get("type"))
    f["abstract"] = ent("abstract" in item, strip_html(item.get("abstract")),
                        "abstract", item.get("abstract"))
    f["cited_by"] = ent("is-referenced-by-count" in item,
                        parse_int(item.get("is-referenced-by-count")),
                        "is-referenced-by-count",
                        item.get("is-referenced-by-count"))
    refs = item.get("reference")
    if isinstance(refs, list):
        f["references"] = ent(True, len(refs), "reference[]", {"count": len(refs)})
    elif "reference-count" in item:
        f["references"] = ent(True, parse_int(item.get("reference-count")),
                              "reference-count", item.get("reference-count"))
    else:
        f["references"] = ent(False)
    lic = item.get("license")
    lv = None
    if isinstance(lic, list) and lic:
        lv = [norm_ws(x.get("URL")) for x in lic if isinstance(x, dict) and x.get("URL")] or None
    f["license"] = ent("license" in item, lv, "license[*].URL", lic)
    # status：撤回/更正标记（relation/update-to/assertion 中出现 retract/withdraw）
    markers = []
    rel = item.get("relation")
    if isinstance(rel, dict):
        markers += [k for k in rel if RETRACT_RE.search(str(k))]
    for ut in item.get("update-to") or []:
        if isinstance(ut, dict) and RETRACT_RE.search(str(ut.get("type", ""))):
            markers.append("update-to:%s" % ut.get("type"))
    for a in item.get("assertion") or []:
        if isinstance(a, dict) and RETRACT_RE.search(str(a.get("label", ""))):
            markers.append("assertion:%s" % a.get("label"))
    status_schema = any(k in item for k in ("relation", "update-to", "assertion"))
    if markers:
        f["status"] = ent(True, ";".join(markers), "relation/update-to/assertion", markers)
    elif status_schema:
        f["status"] = ent(True, "active_no_marker", "relation/update-to/assertion",
                          {"note": "有状态承载字段但无撤回标记"})
    else:
        f["status"] = ent(False)
    return f, bool(markers), warns


# ---------------------------------------------------------------- EuropePMC

def europepmc_records(obj):
    if isinstance(obj, dict):
        rl = obj.get("resultList")
        if isinstance(rl, dict) and isinstance(rl.get("result"), list):
            return rl["result"]
        if isinstance(obj.get("result"), list):
            return obj["result"]
        if "title" in obj and ("pmid" in obj or "id" in obj or "journalInfo" in obj):
            return [obj]
    return []


def extract_europepmc(rec, path, idx):
    f = {}
    warns = []
    drift = []
    ji = rec.get("journalInfo") if isinstance(rec.get("journalInfo"), dict) else None
    jr = (ji.get("journal") if ji and isinstance(ji.get("journal"), dict) else None)
    if ji is not None and jr is None:
        drift.append({
            "file": path, "record_index": idx, "field": "container",
            "detail": "journalInfo.journal 嵌套缺失（schema 漂移），container 降级为"
                      " missing/not_provided 动态判定",
        })
    f["identifiers.doi"] = ent("doi" in rec, clean_doi(rec.get("doi")),
                               "doi", rec.get("doi"))
    pmid = rec.get("pmid")
    if pmid is None and str(rec.get("source", "")).lower() == "med":
        pmid = rec.get("id")
    f["identifiers.pmid"] = ent("pmid" in rec or pmid is not None,
                                norm_ws(pmid), "pmid", rec.get("pmid"))
    f["identifiers.pmcid"] = ent("pmcid" in rec, norm_ws(rec.get("pmcid")),
                                 "pmcid", rec.get("pmcid"))
    f["title"] = ent("title" in rec, norm_ws(rec.get("title")),
                     "title", rec.get("title"))
    if "authorString" in rec:
        av, aw = normalize_authors(rec.get("authorString"))
        warns.extend(aw)
        f["authors"] = ent(True, av, "authorString", rec.get("authorString"))
    elif isinstance(rec.get("authorList"), dict):
        lst = rec["authorList"].get("author")
        av, aw = normalize_authors(lst)
        warns.extend(aw)
        f["authors"] = ent(True, av, "authorList.author[*].fullName", lst)
    else:
        f["authors"] = ent(False)
    cv = norm_ws(jr.get("title")) if jr else norm_ws(rec.get("journalTitle"))
    f["container"] = ent(cv is not None or (jr is not None and "title" in jr)
                         or "journalTitle" in rec, cv,
                         "journalInfo.journal.title", jr.get("title") if jr else None)
    yr = None
    ypath = None
    if ji and "yearOfPublication" in ji:
        yr, ypath = ji.get("yearOfPublication"), "journalInfo.yearOfPublication"
    elif "pubYear" in rec:
        yr, ypath = rec.get("pubYear"), "pubYear"
    if ji and "yearOfPublication" in ji and "pubYear" in rec and \
            str(ji.get("yearOfPublication")) != str(rec.get("pubYear")):
        warns.append("journalInfo.yearOfPublication 与 pubYear 不一致，year 取 "
                     "journalInfo.yearOfPublication（见 references/field_map_europepmc.md）")
    f["year"] = ent(ypath is not None, parse_year(yr), ypath, yr)
    vol = (ji or {}).get("volume")
    if vol is None and jr:
        vol = jr.get("volume")
    f["volume"] = ent(vol is not None, norm_ws(vol), "journalInfo.volume", vol)
    iss = (ji or {}).get("issue")
    if iss is None and jr:
        iss = jr.get("issue")
    f["issue"] = ent(iss is not None, norm_ws(iss), "journalInfo.issue", iss)
    pages = (ji or {}).get("pages") or rec.get("pageInfo")
    f["pages"] = ent(pages is not None, norm_ws(pages), "journalInfo.pages", pages)
    pt = rec.get("pubTypeList")
    ptypes = pt.get("pubType") if isinstance(pt, dict) else None
    tv = norm_ws("; ".join(str(x) for x in ptypes)) if isinstance(ptypes, list) and ptypes else None
    f["type"] = ent(isinstance(ptypes, list), tv, "pubTypeList.pubType", ptypes)
    f["abstract"] = ent("abstractText" in rec, strip_html(rec.get("abstractText")),
                        "abstractText", rec.get("abstractText"))
    pd = rec.get("firstPublicationDate")
    ppath = "firstPublicationDate"
    if pd is None and ji:
        for k in ("printPublicationDate", "electronicPublicationDate"):
            if ji.get(k):
                pd, ppath = ji.get(k), "journalInfo.%s" % k
                break
    f["pub_date"] = ent(pd is not None, norm_ws(pd), ppath, pd)
    f["cited_by"] = ent("citedByCount" in rec, parse_int(rec.get("citedByCount")),
                        "citedByCount", rec.get("citedByCount"))
    rl2 = rec.get("referenceList")
    if isinstance(rl2, dict) and isinstance(rl2.get("reference"), list):
        f["references"] = ent(True, len(rl2["reference"]), "referenceList.reference[]",
                              {"count": len(rl2["reference"])})
    else:
        f["references"] = ent(False)
    f["license"] = ent("license" in rec, norm_ws(rec.get("license")),
                       "license", rec.get("license"))
    # status：pubTypeList 中出现 retract/withdraw/correction 即标记
    markers = []
    if isinstance(ptypes, list):
        markers = [str(p) for p in ptypes if RETRACT_RE.search(str(p))]
    if markers:
        f["status"] = ent(True, ";".join(markers), "pubTypeList.pubType", ptypes)
    elif isinstance(ptypes, list):
        f["status"] = ent(True, "active_no_marker", "pubTypeList.pubType", ptypes)
    else:
        f["status"] = ent(False)
    return f, bool(markers), warns, drift


# ---------------------------------------------------------------- 通用（publisher/recordlist/jsonl/csv）

KEY_CANDIDATES = {
    "identifiers.doi": ["doi", "article_doi", "doi.org"],
    "identifiers.pmid": ["pmid", "pubmed_id", "pubmed"],
    "identifiers.pmcid": ["pmcid", "pmc_id"],
    "title": ["title", "article_title", "articletitle", "name"],
    "authors": ["authors", "author", "creators", "byline", "authorstring"],
    "container": ["journal", "journal_title", "journaltitle", "container",
                  "container_title", "container-title", "publication", "source"],
    "year": ["year", "publication_year", "pub_year", "published_year"],
    "volume": ["volume", "vol"],
    "issue": ["issue", "number"],
    "pages": ["pages", "page", "pagination"],
    "type": ["type", "article_type", "content_type", "genre", "pubtype"],
    "abstract": ["abstract", "summary", "description"],
    "pub_date": ["publication_date", "pub_date", "pubdate", "date",
                 "published", "online_date"],
    "cited_by": ["cited_by", "citedby", "citation_count", "times_cited",
                 "citedbycount"],
    "references": ["references", "reference_count", "refs", "reference"],
    "license": ["license", "licence", "copyright"],
    "status": ["status", "retracted", "withdrawal", "article_status"],
}

META_RE_1 = re.compile(
    r"<meta[^>]+name=[\"'](citation_[^\"']+)[\"'][^>]*content=[\"']([^\"']*)[\"']",
    re.I)
META_RE_2 = re.compile(
    r"<meta[^>]+content=[\"']([^\"']*)[\"'][^>]*name=[\"'](citation_[^\"']+)[\"']",
    re.I)


def html_meta_records(text):
    """出版商 HTML 落盘：提取 citation_* 元标签合成一条记录。"""
    metas = {}
    for name, content in META_RE_1.findall(text):
        metas.setdefault(name.lower(), []).append(html.unescape(content))
    for content, name in META_RE_2.findall(text):
        metas.setdefault(name.lower(), []).append(html.unescape(content))
    if not metas:
        return []
    rec = {}
    one = lambda k: metas.get(k, [None])[0]
    rec["doi"] = one("citation_doi")
    rec["title"] = one("citation_title")
    rec["authors"] = metas.get("citation_author") or []
    rec["journal"] = one("citation_journal_title")
    rec["volume"] = one("citation_volume")
    rec["issue"] = one("citation_issue")
    fp, lp = one("citation_firstpage"), one("citation_lastpage")
    rec["pages"] = ("%s-%s" % (fp, lp)) if fp and lp else (fp or lp)
    rec["publication_date"] = one("citation_publication_date") or one("citation_online_date")
    rec["abstract"] = one("citation_abstract")
    rec["type"] = one("citation_article_type") or "journal-article"
    return [{k: v for k, v in rec.items() if v is not None}]


def generic_records(obj):
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        for k in ("records", "items", "results", "works", "articles"):
            if isinstance(obj.get(k), list):
                return [x for x in obj[k] if isinstance(x, dict)]
        if any(k in obj for k in ("title", "article_title", "doi", "DOI")):
            return [obj]
    return []


def extract_generic(rec, path, idx):
    """启发式键名映射（publisher/recordlist/jsonl/csv 共用）。"""
    f = {}
    warns = []
    lower = {}
    for k in rec.keys():
        if isinstance(k, str):
            lower.setdefault(k.lower(), k)
    markers = []
    for field, cands in KEY_CANDIDATES.items():
        hit = None
        for c in cands:
            if c in lower:
                hit = lower[c]
                break
        if hit is None:
            f[field] = ent(False)
            continue
        raw = rec.get(hit)
        if field == "identifiers.doi":
            f[field] = ent(True, clean_doi(raw), hit, raw)
        elif field in ("identifiers.pmid", "identifiers.pmcid", "container",
                       "volume", "issue", "pages", "type", "pub_date", "license"):
            f[field] = ent(True, norm_ws(raw), hit, raw)
        elif field == "title":
            f[field] = ent(True, norm_ws(raw), hit, raw)
        elif field == "abstract":
            f[field] = ent(True, strip_html(raw), hit, raw)
        elif field == "authors":
            av, aw = normalize_authors(raw)
            warns.extend(aw)
            f[field] = ent(True, av, hit, raw)
        elif field == "year":
            f[field] = ent(True, parse_year(raw), hit, raw)
        elif field == "cited_by":
            f[field] = ent(True, parse_int(raw), hit, raw)
        elif field == "references":
            if isinstance(raw, list):
                f[field] = ent(True, len(raw), hit, {"count": len(raw)})
            else:
                f[field] = ent(True, parse_int(raw), hit, raw)
        elif field == "status":
            sv = norm_ws(raw)
            if isinstance(raw, bool):
                sv = "retracted" if raw else "active_no_marker"
            if sv and RETRACT_RE.search(sv):
                markers.append(sv)
            f[field] = ent(True, sv, hit, raw)
    # 标题前缀撤回标记（如 "Retracted: ..."/"WITHDRAWN: ..."）
    tv = f.get("title", {}).get("value")
    if tv and RETRACT_RE.search(str(tv)[:20]):
        markers.append("title_prefix")
    if markers and f["status"]["found"] and not RETRACT_RE.search(
            str(f["status"]["value"] or "")):
        f["status"]["value"] = ";".join(markers)
    elif markers and not f["status"]["found"]:
        f["status"] = ent(True, ";".join(markers), "title_prefix", tv)
    return f, bool(markers), warns, []


# ---------------------------------------------------------------- 记录装载

def load_records(mat):
    """按 sniff 类型装载原始记录列表。返回 (records, note)。"""
    sniff = mat.get("sniff")
    path = mat.get("path")
    with open(path, "r", encoding="utf-8", errors="replace") as fp:
        text = fp.read()
    if sniff in ("crossref", "europepmc"):
        obj = json.loads(text)
        return (crossref_records(obj) if sniff == "crossref"
                else europepmc_records(obj)), None
    if sniff == "publisher":
        s = text.lstrip()
        if s.startswith("{") or s.startswith("["):
            return generic_records(json.loads(text)), None
        recs = html_meta_records(text)
        return recs, ("HTML citation_* 元标签提取 %d 条" % len(recs))
    if sniff == "recordlist":
        return generic_records(json.loads(text)), None
    if sniff == "jsonl":
        recs = []
        for ln in text.splitlines():
            if ln.strip():
                recs.append(json.loads(ln))
        return [r for r in recs if isinstance(r, dict)], None
    if sniff == "csv":
        return list(csv.DictReader(text.splitlines())), None
    return [], "sniff=%s 不支持记录装载" % sniff


def extract_record(source, rec, path, idx):
    if source == "crossref":
        f, ret, warns = extract_crossref(rec, path, idx)
        return f, ret, warns, []
    if source == "europepmc":
        return extract_europepmc(rec, path, idx)
    f, ret, warns, drift = extract_generic(rec, path, idx)
    return f, ret, warns, drift


def cluster_key(fields):
    doi = fields["identifiers.doi"].get("value")
    if doi:
        return "doi:" + doi
    t = norm_title(fields["title"].get("value"))
    y = fields["year"].get("value")
    if t:
        return "ty:%s::%s" % (t, y if y else "?")
    pmid = fields["identifiers.pmid"].get("value")
    if pmid:
        return "pmid:" + str(pmid)
    return None


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(
        description="按映射表归一各来源记录为字段卡片 JSONL（exit 0/2/3）。")
    ap.add_argument("--summary", default="/app/work/case_summary.json",
                    help="case_summary.json 路径")
    ap.add_argument("--out", default="/app/work/field_cards.jsonl",
                    help="字段卡片 JSONL 输出路径")
    ap.add_argument("--report", default="/app/work/map_report.json",
                    help="映射报告（对账/漂移/丢弃留痕）输出路径")
    args = ap.parse_args()

    if not os.path.isfile(args.summary):
        print("ERROR: case_summary.json 不存在（材料不足，exit 2）: %s"
              % args.summary, file=sys.stderr)
        return 2
    try:
        with open(args.summary, "r", encoding="utf-8") as fp:
            summary = json.load(fp)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print("ERROR: case_summary.json 非法（校验失败，exit 3）: %s" % e,
              file=sys.stderr)
        return 3

    cards = []
    report = {"files": [], "totals": {}, "dropped_records": [],
              "drift_log": [], "skipped_files": [], "warnings": []}
    processable = ("crossref", "europepmc", "publisher",
                   "recordlist", "jsonl", "csv")

    for mat in summary.get("materials", []):
        sniff = mat.get("sniff")
        path = mat.get("path")
        if sniff not in processable:
            report["skipped_files"].append({
                "path": path, "sniff": sniff,
                "reason": "非题录记录来源（reference_graph/import_state/unknown），"
                          "不产出字段卡片"})
            continue
        finfo = {"path": path, "source": sniff, "records_found": 0,
                 "records_mapped": 0, "records_dropped": [], "notes": []}
        try:
            records, note = load_records(mat)
        except Exception as e:
            report["skipped_files"].append({
                "path": path, "sniff": sniff,
                "reason": "装载失败（已留痕，不中断流程）: %r" % e})
            report["files"].append(finfo)
            continue
        if note:
            finfo["notes"].append(note)
        finfo["records_found"] = len(records)
        extractions = []
        observed = set()
        for i, rec in enumerate(records):
            if not isinstance(rec, dict):
                finfo["records_dropped"].append(
                    {"index": i, "reason": "记录非 JSON 对象: %s" % type(rec).__name__})
                continue
            try:
                fields, retracted, warns, drift = extract_record(sniff, rec, path, i)
            except Exception as e:
                finfo["records_dropped"].append(
                    {"index": i, "reason": "字段提取异常（已留痕）: %r" % e})
                continue
            report["drift_log"].extend(drift)
            ck = cluster_key(fields)
            if ck is None:
                finfo["records_dropped"].append(
                    {"index": i, "reason": "无 DOI 且无可归一化的题名+年份，"
                                           "无法建立最小聚类键"})
                continue
            for fld, e in fields.items():
                if e["found"]:
                    observed.add(fld)
            extractions.append((i, fields, retracted, warns, ck))
        static_np = STATIC_NOT_PROVIDED.get(sniff, set())
        for i, fields, retracted, warns, ck in extractions:
            fmap = {}
            for fld in FIELDS:
                e = fields.get(fld) or ent(False)
                if fld in static_np:
                    st = "not_provided"
                elif e["found"]:
                    st = "unknown" if is_empty(e["value"]) else "present"
                else:
                    st = "missing" if fld in observed else "not_provided"
                fmap[fld] = {
                    "status": st,
                    "value": e["value"] if st == "present" else None,
                    "source_path": e["source_path"],
                    "raw_excerpt": e["raw_excerpt"],
                }
                if e.get("warning"):
                    warns.append("[%s] %s" % (fld, e["warning"]))
            cards.append({
                "record_uid": "%s::%s::%d" % (sniff, os.path.basename(path), i),
                "source": sniff, "source_file": path, "item_index": i,
                "cluster_key": ck, "retracted": retracted,
                "fields": fmap, "warnings": warns,
            })
        finfo["records_mapped"] = len(extractions)
        report["files"].append(finfo)
        report["dropped_records"].extend(
            {"file": path, **d} for d in finfo["records_dropped"])
        tot = report["totals"].setdefault(
            sniff, {"returned": 0, "parsed": 0, "dropped": 0})
        tot["returned"] += finfo["records_found"]
        tot["parsed"] += finfo["records_mapped"]
        tot["dropped"] += len(finfo["records_dropped"])

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fp:
        for c in cards:
            fp.write(json.dumps(c, ensure_ascii=False) + "\n")
    rep_dir = os.path.dirname(os.path.abspath(args.report))
    os.makedirs(rep_dir, exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as fp:
        json.dump(report, fp, ensure_ascii=False, indent=2)

    print("OK: 字段标准化完成 -> %s (%d 张卡片); 报告 -> %s (丢弃=%d, 漂移=%d, "
          "跳过文件=%d)" % (args.out, len(cards), args.report,
                            len(report["dropped_records"]),
                            len(report["drift_log"]),
                            len(report["skipped_files"])))
    if not cards:
        print("ERROR: 无任何可映射记录（材料不足，诚实降级，exit 2）", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("ERROR: map_fields 未捕获异常（诚实降级，exit 2）: %r" % e,
              file=sys.stderr)
        sys.exit(2)
