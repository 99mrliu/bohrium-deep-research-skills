#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_lineage.py — 全链溯源账本：每条记录从来源库到 canonical 的可回链轨迹。

链模型（详见 references/lineage_schema.md）：
  source_db → query_id → response_file + item_index → record_uid
            → field_extractions(逐字段 raw_pointer + raw_excerpt)
            → dedup_decision(两级精确聚类) → canonical → merge_contribution

两级去重（本 bundle 不做模糊去重，那是方向 A 的领域）：
  Tier1 标识符精确：DOI 小写归一 / PMID / PMCID 相同即并簇；
  Tier2 归一题名精确：题名归一化（小写、去标点、折叠空白）后完全一致即并簇。
  其余相似但不精确的记录对 → unresolved_pairs，交模型仲裁，绝不臆断。

输出（--work 下，全部为确定性内容：无时间戳、无绝对路径、排序固定）：
  lineage.jsonl          每条原始记录一行（含被丢弃者）
  canonical_records.json canonical 合并结果 + unresolved_pairs + stats

raw_pointer 规范：JSON 路径（如 message.items[3].DOI、resultList.result[0].doi），
jsonl 用 line[i].<key>，csv 用 row[i].<col>；纯文本响应可用 char[START:END] 字符偏移。

退出码：0=成功；2=summary 缺失/无响应材料；3=summary 非法。
顶层未捕获异常汇总并以 exit 2 降级，绝不 crash。

用法：
  python3 build_lineage.py [--summary /app/work/case_summary.json]
      [--work /app/work] [--exclusions /app/work/exclusions.json]
"""
import argparse
import json
import os
import re
import sys
from itertools import combinations

FIELDS = ["doi", "pmid", "pmcid", "title", "authors", "journal", "year",
          "volume", "issue", "pages", "abstract", "publisher", "type"]

DISCARD_REASONS = {"duplicate_of", "relevance_excluded", "unparsed",
                   "withdrawn"}

EXCERPT_MAX = 200
FUZZY_JACCARD_THRESHOLD = 0.8


# ---------------------------------------------------------------- 归一化

def norm_doi(v):
    if not isinstance(v, str):
        return None
    s = v.strip().lower()
    s = re.sub(r"^https?://(dx\.)?doi\.org/", "", s)
    s = s.rstrip(".")
    return s or None


def norm_id(v):
    if v is None:
        return None
    s = re.sub(r"\D", "", str(v))
    return s or None


def norm_title(v):
    if not isinstance(v, str):
        return None
    s = v.strip().lower()
    s = re.sub(r"[^a-z0-9一-鿿]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def tokens(s):
    return set(s.split()) if s else set()


# ---------------------------------------------------------------- 定位与提取

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def locate_items(obj, sniff):
    """返回 (items_list, base_path) 或 (None, None)。obj 为已解析 JSON。"""
    if sniff == "crossref":
        msg = obj.get("message") if isinstance(obj, dict) else None
        if isinstance(msg, dict):
            if isinstance(msg.get("items"), list):
                return msg["items"], "message.items"
            if "DOI" in msg or "title" in msg:
                return [msg], "message"
    elif sniff == "europepmc":
        rl = obj.get("resultList") if isinstance(obj, dict) else None
        if isinstance(rl, dict) and isinstance(rl.get("result"), list):
            return rl["result"], "resultList.result"
    elif sniff == "publisher":
        if isinstance(obj, dict):
            for k in ("items", "records", "results"):
                if isinstance(obj.get(k), list):
                    return obj[k], k
        elif isinstance(obj, list):
            return obj, ""
    elif sniff == "recordlist":
        if isinstance(obj, list):
            return obj, ""
        if isinstance(obj, dict):
            for k in ("records", "items", "results"):
                if isinstance(obj.get(k), list):
                    return obj[k], k
    return None, None


def split_pointer(ptr):
    """把 'a.b[0].c' 拆成 [('a',None),('b',0),('c',None)]。"""
    out = []
    for seg in str(ptr).split("."):
        m = re.match(r"^([^\[\]]+)((?:\[\d+\])*)$", seg)
        if not m:
            out.append((seg, None))
            continue
        name, idxs = m.group(1), m.group(2)
        out.append((name, None))
        for i in re.findall(r"\[(\d+)\]", idxs):
            out.append((None, int(i)))
    return out


def resolve_pointer(obj, ptr):
    """按 JSON 路径解析；jsonl/csv 的 line[i]/row[i] 根由调用方预处理。"""
    cur = obj
    for name, idx in split_pointer(ptr):
        if name is not None:
            if not isinstance(cur, dict) or name not in cur:
                raise KeyError(name)
            cur = cur[name]
        else:
            if not isinstance(cur, list) or idx >= len(cur):
                raise IndexError(idx)
            cur = cur[idx]
    return cur


def first_scalar(node):
    if isinstance(node, list):
        return node[0] if node else None
    return node


# ---- 各库提取规则（路径相对 item，base 为响应内 items 数组路径）----

def _x_crossref(item, base):
    out = {}

    def put(field, value, rel, extractor):
        if value is None:
            return
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return
        out[field] = {"extractor": extractor,
                      "raw_pointer": base + "." + rel,
                      "raw_excerpt": str(value)[:EXCERPT_MAX],
                      "value": value}

    def put_raw(field, value, rel, extractor, raw_excerpt):
        """raw_pointer 指向原始节点、raw_excerpt 为该节点原文（派生字段用）。"""
        if value is None:
            return
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return
        out[field] = {"extractor": extractor,
                      "raw_pointer": base + "." + rel,
                      "raw_excerpt": str(raw_excerpt)[:EXCERPT_MAX],
                      "value": value}

    put("doi", item.get("DOI"), "DOI", "crossref.DOI")
    put("title", first_scalar(item.get("title")), "title[0]", "crossref.title")
    authors = item.get("author")
    if isinstance(authors, list) and authors:
        names = [("%s %s" % (a.get("family", ""),
                            a.get("given", ""))).strip()
                 for a in authors if isinstance(a, dict)]
        names = [n for n in names if n]
        if names:
            put_raw("authors", "; ".join(names), "author", "crossref.author",
                    authors)
    put("journal", first_scalar(item.get("container-title")),
        "container-title[0]", "crossref.container-title")
    dp = item.get("issued") or {}
    dp = dp.get("date-parts") if isinstance(dp, dict) else None
    if isinstance(dp, list) and dp and isinstance(dp[0], list) and dp[0]:
        put("year", str(dp[0][0]), "issued.date-parts[0][0]", "crossref.issued")
    put("volume", item.get("volume"), "volume", "crossref.volume")
    put("issue", item.get("issue"), "issue", "crossref.issue")
    put("pages", item.get("page"), "page", "crossref.page")
    put("type", item.get("type"), "type", "crossref.type")
    ab = item.get("abstract")
    if isinstance(ab, str) and ab.strip():
        put("abstract", re.sub(r"<[^>]+>", " ", ab).strip(),
            "abstract", "crossref.abstract")
    put("publisher", item.get("publisher"), "publisher", "crossref.publisher")
    return out


def _x_europepmc(item, base):
    out = {}

    def put(field, value, rel, extractor):
        if value is None:
            return
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return
        out[field] = {"extractor": extractor,
                      "raw_pointer": base + "." + rel,
                      "raw_excerpt": str(value)[:EXCERPT_MAX],
                      "value": value}

    ji = item.get("journalInfo") or {}
    j = ji.get("journal") or {}
    put("doi", item.get("doi"), "doi", "europepmc.doi")
    put("pmid", item.get("pmid") or item.get("id"), "pmid", "europepmc.pmid")
    put("pmcid", item.get("pmcid"), "pmcid", "europepmc.pmcid")
    put("title", item.get("title"), "title", "europepmc.title")
    put("authors", item.get("authorString"), "authorString",
        "europepmc.authorString")
    put("journal", j.get("title"), "journalInfo.journal.title",
        "europepmc.journalInfo")
    put("year", str(ji.get("yearOfPublication") or ji.get("pubYear") or ""),
        "journalInfo.yearOfPublication", "europepmc.journalInfo")
    put("volume", ji.get("volume"), "journalInfo.volume", "europepmc.journalInfo")
    put("issue", ji.get("issue"), "journalInfo.issue", "europepmc.journalInfo")
    put("pages", ji.get("pages"), "journalInfo.pages", "europepmc.journalInfo")
    ab = item.get("abstractText")
    if isinstance(ab, str) and ab.strip():
        put("abstract", ab.strip(), "abstractText", "europepmc.abstractText")
    ptl = item.get("pubTypeList") or {}
    if isinstance(ptl.get("pubType"), list) and ptl["pubType"]:
        put("type", ptl["pubType"][0], "pubTypeList.pubType[0]",
            "europepmc.pubType")
    return out


GENERIC_KEYS = {
    "doi": ["doi", "DOI", "DOI_"],
    "pmid": ["pmid", "PMID"],
    "pmcid": ["pmcid", "PMCID"],
    "title": ["title", "Title"],
    "authors": ["authors", "author", "authorString", "creator"],
    "journal": ["journal", "container", "container-title", "journalTitle",
                "journal_title"],
    "year": ["year", "pubYear", "date", "published", "issued"],
    "volume": ["volume", "Volume"],
    "issue": ["issue", "Issue"],
    "pages": ["pages", "page", "Pages"],
    "abstract": ["abstract", "abstractText"],
    "publisher": ["publisher"],
    "type": ["type", "pubType", "publicationType"],
}


def _x_generic(item, base, extractor_prefix):
    out = {}
    for field, cands in GENERIC_KEYS.items():
        for k in cands:
            if k in item and item[k] not in (None, ""):
                v = item[k]
                if isinstance(v, list):
                    v = "; ".join(str(x) for x in v if x)
                if isinstance(v, str):
                    v = v.strip()
                    if not v:
                        continue
                    if field == "year":
                        m = re.search(r"(1[5-9]\d{2}|20\d{2})", v)
                        if m:
                            v = m.group(1)
                out[field] = {"extractor": "%s.%s" % (extractor_prefix, k),
                              "raw_pointer": (base + "." + k) if base else k,
                              "raw_excerpt": str(v)[:EXCERPT_MAX],
                              "value": v}
                break
    return out


def extract_item_fields(item, base, sniff):
    if sniff == "crossref":
        return _x_crossref(item, base)
    if sniff == "europepmc":
        return _x_europepmc(item, base)
    prefix = sniff if sniff in ("publisher", "recordlist", "jsonl", "csv") \
        else "generic"
    return _x_generic(item, base, prefix)


def detect_withdrawn(item):
    """识别撤回/撤销痕迹：结构化字段优先，其次全文关键词。"""
    if not isinstance(item, dict):
        return None
    for k in ("withdrawn", "retracted", "is-retracted"):
        if item.get(k) is True:
            return k
    rel = item.get("relation") or {}
    if isinstance(rel, dict):
        for k, v in rel.items():
            if "update-to" in str(k).lower() or "retract" in str(k).lower():
                if v:
                    return "relation.%s" % k
    ptl = item.get("pubTypeList") or {}
    if isinstance(ptl.get("pubType"), list):
        for t in ptl["pubType"]:
            if "retraction" in str(t).lower():
                return "pubTypeList:%s" % t
    text = json.dumps(item, ensure_ascii=False).lower()
    if '"update-to"' in text or '"is-update-to"' in text:
        return "raw_text:update-to"
    return None


# ---------------------------------------------------------------- 主流程

class DSU(object):
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def load_exclusions(path):
    if not path or not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    if isinstance(data, dict):
        for uid, reason in data.items():
            out[str(uid)] = str(reason)
    elif isinstance(data, list):
        for it in data:
            if isinstance(it, dict) and it.get("record_uid"):
                out[str(it["record_uid"])] = str(it.get("reason_code")
                                                 or "relevance_excluded")
    return out


def main_inner(args):
    if not os.path.isfile(args.summary):
        print("ERROR: case_summary 不存在（材料不足）: %s；请先运行 parse_case.py。"
              % args.summary, file=sys.stderr)
        return 2
    try:
        with open(args.summary, "r", encoding="utf-8") as f:
            summary = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print("ERROR: case_summary 非法（校验失败）: %s" % e, file=sys.stderr)
        return 3

    responses = [m for m in (summary.get("materials") or [])
                 if m.get("sniff") in
                 ("crossref", "europepmc", "publisher", "recordlist",
                  "jsonl", "csv")]
    if not responses:
        print("ERROR: 无可建账的响应材料，诚实降级。", file=sys.stderr)
        return 2

    exclusions = load_exclusions(args.exclusions)

    # query_id 映射（若有 query_ledger.jsonl）
    qmap = {}
    ledger_path = os.path.join(args.work, "query_ledger.jsonl")
    if os.path.isfile(ledger_path):
        with open(ledger_path, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    e = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if e.get("response_file") and e.get("query_id"):
                    qmap[e["response_file"]] = e["query_id"]

    records = []   # 每个 dict 是一条原始 item 的完整 lineage 记录
    skipped = []   # 文件级失败留痕
    for m in sorted(responses, key=lambda x: x.get("file") or ""):
        base_name, sniff, path = m.get("file"), m.get("sniff"), m.get("path")
        try:
            if sniff == "jsonl":
                rows = [json.loads(ln) for ln in
                        open(path, encoding="utf-8").read().splitlines()
                        if ln.strip()]
                items, root = [r if isinstance(r, dict) else None for r in rows], \
                    ("line", rows)
            elif sniff == "csv":
                import csv as _csv
                with open(path, encoding="utf-8") as f:
                    rows = list(_csv.DictReader(f))
                items, root = rows, ("row", rows)
            else:
                obj = load_json(path)
                items, base = locate_items(obj, sniff)
                root = ("json", obj, base)
                if items is None:
                    skipped.append({"file": base_name, "reason":
                                    "locate_items_failed: schema 不匹配 sniff=%s"
                                    % sniff})
                    continue
        except Exception as e:
            skipped.append({"file": base_name, "reason":
                            "parse_error: %r" % e})
            continue

        for idx, item in enumerate(items):
            uid = "%s:%s:item[%d]" % (sniff, base_name, idx)
            rec = {
                "record_uid": uid,
                "source_db": sniff,
                "query_id": qmap.get(base_name),
                "response_file": base_name,
                "item_index": idx,
                "field_extractions": {},
                "dedup_decision": None,
                "merge_contribution": None,
                "discard": None,
                "notes": [],
            }
            if not isinstance(item, dict):
                rec["discard"] = {"reason_code": "unparsed",
                                  "detail": "item 非 dict（%s），无法提取字段"
                                            % type(item).__name__}
                records.append(rec)
                continue
            # 构造 base 前缀
            if root[0] == "json":
                base_path = (root[2] + "[%d]") % idx if root[2] else ""
            elif root[0] == "line":
                base_path = "line[%d]" % idx
            else:
                base_path = "row[%d]" % idx
            try:
                rec["field_extractions"] = extract_item_fields(
                    item, base_path, sniff)
            except Exception as e:
                rec["discard"] = {"reason_code": "unparsed",
                                  "detail": "extract_error: %r" % e}
                records.append(rec)
                continue
            reason = exclusions.get(uid)
            if reason:
                if reason not in DISCARD_REASONS:
                    reason = "relevance_excluded"
                    rec["notes"].append("exclusion 原因码非法，回退 relevance_excluded")
                rec["discard"] = {"reason_code": reason,
                                  "detail": "模型仲裁排除（见 exclusions 文件）"}
                records.append(rec)
                continue
            w = detect_withdrawn(item)
            if w:
                rec["discard"] = {"reason_code": "withdrawn",
                                  "detail": "撤回痕迹信号: %s" % w}
                records.append(rec)
                continue
            records.append(rec)

    # ---------------- 两级精确聚类 ----------------
    active = [i for i, r in enumerate(records) if r["discard"] is None]
    dsu = DSU(len(records))

    def field_val(i, f):
        ex = records[i]["field_extractions"].get(f)
        return ex.get("value") if ex else None

    ident_keys = {}
    for i in active:
        for f, norm in (("doi", norm_doi), ("pmid", norm_id),
                        ("pmcid", norm_id)):
            v = field_val(i, f)
            if v is None:
                continue
            nv = norm(v)
            if not nv:
                continue
            key = "%s:%s" % (f, nv)
            if key in ident_keys:
                dsu.union(i, ident_keys[key])
            else:
                ident_keys[key] = i

    title_keys = {}
    for i in active:
        t = norm_title(field_val(i, "title"))
        if t and len(t) >= 8:
            if t in title_keys:
                dsu.union(i, title_keys[t])
            else:
                title_keys[t] = i

    clusters = {}
    for i in active:
        clusters.setdefault(dsu.find(i), []).append(i)

    def cluster_basis(members):
        """判定簇依据：任一标识符被 ≥2 成员共享 → Tier1；
        否则归一题名被 ≥2 成员共享 → Tier2；否则 unique。"""
        if len(members) == 1:
            return "unique"
        keys = {}
        for i in members:
            ks = set()
            d = norm_doi(field_val(i, "doi"))
            if d:
                ks.add("doi:" + d)
            for f in ("pmid", "pmcid"):
                v = norm_id(field_val(i, f))
                if v:
                    ks.add("%s:%s" % (f, v))
            for k in ks:
                keys.setdefault(k, []).append(i)
        if any(len(v) > 1 for v in keys.values()):
            return "tier1_identifier_exact"
        titles = {}
        for i in members:
            t = norm_title(field_val(i, "title"))
            if t:
                titles.setdefault(t, []).append(i)
        if any(len(v) > 1 for v in titles.values()):
            return "tier2_title_exact"
        return "unique"

    # canonical 编号：按簇内首成员出现顺序（records 顺序即确定性顺序）
    canon_order = sorted(clusters.values(), key=lambda ms: min(ms))
    canonicals, uid2canon = [], {}
    for n, members in enumerate(canon_order, 1):
        cid = "C%03d" % n
        members = sorted(members)
        basis = cluster_basis(members)
        cfields, contrib = {}, {}
        for f in FIELDS:
            for i in members:
                ex = records[i]["field_extractions"].get(f)
                if ex and ex.get("value") not in (None, ""):
                    cfields[f] = {"value": ex["value"],
                                  "from_record": records[i]["record_uid"],
                                  "raw_pointer": ex["raw_pointer"],
                                  "raw_excerpt": ex["raw_excerpt"]}
                    contrib.setdefault(records[i]["record_uid"], []).append(f)
                    break
        canonicals.append({
            "canonical_id": cid,
            "cluster_basis": basis,
            "members": [records[i]["record_uid"] for i in members],
            "fields": cfields,
        })
        for i in members:
            uid2canon[i] = cid
            first = i == members[0]
            records[i]["dedup_decision"] = {
                "canonical": cid,
                "status": "adopted" if first else "duplicate_of",
                "reason_code": basis if not first or basis != "unique"
                else "unique",
            }
            records[i]["merge_contribution"] = {
                "canonical": cid,
                "fields": sorted(contrib.get(records[i]["record_uid"], [])),
            }

    # ---------------- 模糊对 → unresolved（不臆断）----------------
    unresolved = []
    norm_t = {}
    for i in active:
        t = norm_title(field_val(i, "title"))
        if t:
            norm_t[i] = tokens(t)
    act = sorted(norm_t)
    for x, y in combinations(act, 2):
        if dsu.find(x) == dsu.find(y):
            continue
        a, b = norm_t[x], norm_t[y]
        j = len(a & b) / float(len(a | b)) if (a | b) else 0.0
        if j >= FUZZY_JACCARD_THRESHOLD:
            unresolved.append({
                "record_a": records[x]["record_uid"],
                "record_b": records[y]["record_uid"],
                "title_similarity_jaccard": round(j, 4),
                "note": "题名相似但未达两级精确聚类条件；模糊对一律 unresolved，"
                        "交模型仲裁，本 bundle 不臆断",
            })

    os.makedirs(args.work, exist_ok=True)
    lin_out = os.path.join(args.work, "lineage.jsonl")
    can_out = os.path.join(args.work, "canonical_records.json")
    with open(lin_out, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    with open(can_out, "w", encoding="utf-8") as f:
        json.dump({
            "canonicals": canonicals,
            "unresolved_pairs": unresolved,
            "skipped_files": skipped,
            "stats": {
                "raw_records": len(records),
                "canonicals": len(canonicals),
                "discarded": sum(1 for r in records if r["discard"]),
                "unresolved_pairs": len(unresolved),
            },
        }, f, ensure_ascii=False, indent=2, sort_keys=True)

    print("OK: lineage -> %s (records=%d)" % (lin_out, len(records)))
    print("OK: canonicals -> %s (canonicals=%d, unresolved=%d, skipped=%d)"
          % (can_out, len(canonicals), len(unresolved), len(skipped)))
    for s in skipped:
        print("WARN: skipped_file: %s (%s)" % (s["file"], s["reason"]),
              file=sys.stderr)
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="构建全链溯源账本 + 两级精确聚类（exit 0/2/3）。")
    ap.add_argument("--summary", default="/app/work/case_summary.json")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--exclusions", default=None,
                    help="模型仲裁排除文件：{record_uid: reason_code} 或列表")
    args = ap.parse_args()
    try:
        return main_inner(args)
    except Exception as e:
        print("ERROR: 未捕获异常，诚实降级 exit 2: %r" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
