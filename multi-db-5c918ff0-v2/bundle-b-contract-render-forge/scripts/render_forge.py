#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_forge.py — contract-render-forge 下游契约与渲染引擎

重心(OUTPUT 侧):
  1. 契约发现:解析 case.json "output_contract" 三种形态(dict / list /
     换行字符串),挖掘 task.md 显式交付字段;写出 work/contract_fields.json。
  2. 证据摄入:嗅探-分类材料(crossref / europepmc / publisher JSON、
     reference_graph、import_state),归一化为通用记录,按
     (DOI 精确, PMID 精确, 标题+年份+第一作者姓) 去重,按
     publisher > crossref > europepmc 逐字段合并并记录字段级溯源。
     若 work/merged_records.json 已存在(上游产出),直接消费并记入
     change_records。
  3. 确定性渲染:candidate_table.md / provenance_chain.md /
     coverage_matrix.md(含 review appendix:未决契约字段 + 冲突清单)。
  4. 契约门控与装配:result.json 覆盖全部契约字段(填不出一律 null +
     unresolved_contract_fields,绝不编造),附 case_id / status /
     sources / uncertainty / change_records / artifacts(path+sha256);
     门控从数据重算所有渲染声明,不采信硬编码。

Python 3 标准库;无网络、无随机数、产物中无墙钟(确定性、幂等)。
退出码:0 正常;2 诚实降级(partial);3 输入非法(input_error)。永不崩溃。
"""

import argparse
import hashlib
import json
import os
import re
import sys

VERSION = "1.0.0"
EXIT_OK = 0
EXIT_DEGRADED = 2
EXIT_INPUT_ERROR = 3

# 合并优先级:publisher > crossref > europepmc;上游 merged_records 兜底
SOURCE_PRIORITY = {"publisher": 30, "crossref": 20, "europepmc": 10,
                   "merged_records": 5, "unknown": 0}
BADGE = {"crossref": "CR", "europepmc": "EP", "publisher": "PU",
         "merged_records": "MR", "unknown": "??"}
KEY_FIELDS = ["doi", "pmid", "title", "year", "first_author", "authors",
              "journal", "volume", "issue", "pages"]
RESERVED_KEYS = {"case_id", "status", "sources", "uncertainty", "change_records",
                 "artifacts", "unresolved_contract_fields", "generated_by"}
STOPWORDS = set((
    "a an the and or of in on for to with by is are was were be been which "
    "what who whom whose this that these those from into over under about "
    "between their its his her our your as at do does did not no yes we you "
    "they he she it via per can may must shall should will would could than "
    "then thus also output field fields result results value values deliverable"
).split())
SCOPE_HINTS = ("纳入", "排除", "范围", "scope", "include", "exclude", "时间窗",
               "criterion", "criteria", "eligib", "filter")


class InputError(Exception):
    """case.json 缺失或非法等致命输入问题 -> status=input_error, exit 3。"""


# ---------------------------------------------------------------- 基础工具

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def write_text(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def log_change(changes, step, action, detail):
    changes.append({"seq": len(changes) + 1, "step": step,
                    "action": action, "detail": detail})


def clean(v):
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    return v


def first_of(v):
    if isinstance(v, (list, tuple)) and v:
        return clean(v[0])
    return clean(v)


def to_int(v):
    v = clean(v)
    if v is None:
        return None
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return None


def norm_doi(v):
    v = clean(v)
    if v is None:
        return None
    s = str(v).strip()
    s = re.sub(r"(?i)^https?://(dx\.)?doi\.org/", "", s)
    s = s.strip().strip(".").strip()
    return s.lower() or None


def norm_title(v):
    v = clean(v)
    if v is None:
        return None
    s = re.sub(r"[^a-z0-9]+", " ", str(v).lower())
    return " ".join(s.split()) or None


def norm_surname(v):
    v = clean(v)
    if v is None:
        return None
    s = re.sub(r"[^a-z\-']+", "", str(v).strip().lower())
    return s or None


def is_present(v):
    return v not in (None, "", [])


# ---------------------------------------------------------------- 记录提取

def make_member(source, artifact, locator, values):
    rec = {k: values.get(k) for k in KEY_FIELDS}
    if not is_present(rec["authors"]):
        rec["authors"] = []
    missing = sorted(k for k in KEY_FIELDS if not is_present(rec[k]))
    return {"source": source, "artifact": artifact, "locator": locator,
            "record": rec, "missing_fields": missing}


def extract_crossref(obj, artifact):
    out = []
    msg = obj.get("message") if isinstance(obj, dict) else None
    items = msg.get("items", []) if isinstance(msg, dict) else []
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        dp = (it.get("issued") or {}).get("date-parts") or [[None]]
        year = to_int(dp[0][0]) if dp and dp[0] else None
        authors = []
        for a in it.get("author") or []:
            if not isinstance(a, dict):
                continue
            fam, giv = clean(a.get("family")), clean(a.get("given"))
            if fam or giv:
                authors.append(", ".join(x for x in (fam, giv) if x))
        vals = {
            "doi": norm_doi(it.get("DOI")),
            "pmid": None,
            "title": first_of(it.get("title")),
            "year": year,
            "first_author": authors[0].split(",")[0].strip() if authors else None,
            "authors": authors,
            "journal": first_of(it.get("container-title")),
            "volume": clean(it.get("volume")),
            "issue": clean(it.get("issue")),
            "pages": clean(it.get("page")),
        }
        out.append(make_member("crossref", artifact,
                               "message.items[%d]" % i, vals))
    return out


def extract_europepmc(obj, artifact):
    out = []
    rl = obj.get("resultList") if isinstance(obj, dict) else None
    results = rl.get("result", []) if isinstance(rl, dict) else []
    for i, r in enumerate(results):
        if not isinstance(r, dict):
            continue
        pmid = clean(r.get("pmid"))
        if not pmid:
            src, rid = clean(r.get("source")), clean(r.get("id"))
            if src and src.upper() in ("MED", "PMC", "PPR") and rid:
                pmid = rid
        astr = clean(r.get("authorString"))
        authors = ([a.strip() for a in astr.split(";") if a.strip()]
                   if astr else [])
        fam = authors[0].split(",")[0].split()[0] if authors else None
        vals = {
            "doi": norm_doi(r.get("doi")),
            "pmid": pmid,
            "title": clean(r.get("title")),
            "year": to_int(r.get("pubYear")),
            "first_author": fam,
            "authors": authors,
            "journal": clean(r.get("journalTitle")),
            "volume": None,
            "issue": None,
            "pages": None,
        }
        out.append(make_member("europepmc", artifact,
                               "resultList.result[%d]" % i, vals))
    return out


def extract_publisher(obj, artifact):
    if isinstance(obj, dict):
        seq = None
        for k in ("records", "items", "papers", "results", "data"):
            if isinstance(obj.get(k), list):
                seq = obj[k]
                break
        if seq is None:
            if obj and all(isinstance(v, dict) for v in obj.values()):
                seq = []
                for k in sorted(obj):
                    v = dict(obj[k])
                    v.setdefault("doi", k)
                    seq.append(v)
            else:
                seq = [obj]
    elif isinstance(obj, list):
        seq = obj
    else:
        seq = []
    out = []
    for i, r in enumerate(seq):
        if not isinstance(r, dict):
            continue

        def pick(rec, *names):
            for n in names:
                if n in rec and is_present(clean(rec[n])):
                    return rec[n]
            return None

        authors = pick(r, "authors", "authorString", "author")
        if isinstance(authors, str):
            authors = [a.strip() for a in re.split(r";| and ", authors)
                       if a.strip()]
        authors = [a for a in (authors or [])
                   if isinstance(a, str) and a.strip()]
        fa = clean(r.get("first_author")) or (
            authors[0].split(",")[0].strip() if authors else None)
        vals = {
            "doi": norm_doi(pick(r, "doi", "DOI")),
            "pmid": clean(pick(r, "pmid", "PMID")),
            "title": first_of(pick(r, "title", "Title")),
            "year": to_int(pick(r, "year", "pubYear", "Year")),
            "first_author": fa,
            "authors": authors,
            "journal": first_of(pick(r, "journal", "journalTitle",
                                     "container-title", "container_title")),
            "volume": clean(pick(r, "volume", "Volume")),
            "issue": clean(pick(r, "issue", "Issue")),
            "pages": clean(pick(r, "pages", "page", "Pages")),
        }
        out.append(make_member("publisher", artifact, "records[%d]" % i, vals))
    return out


# ---------------------------------------------------------------- 嗅探分类

def classify_payload(obj, fname):
    f = fname.lower()
    if isinstance(obj, dict):
        if (obj.get("status") == "ok" and isinstance(obj.get("message"), dict)
                and isinstance(obj["message"].get("items"), list)):
            return "crossref"
        if isinstance(obj.get("hitCount"), int) and \
                isinstance(obj.get("resultList"), dict):
            return "europepmc"
        if any(k in obj for k in ("edges", "nodes", "references",
                                  "retained_reference_graph")):
            return "reference_graph"
        if any(k in obj for k in ("incremental_import", "import_state",
                                  "last_import", "cursors", "imported")):
            return "import_state"
        if any(isinstance(obj.get(k), list) for k in
               ("records", "items", "papers", "results")):
            return "publisher"
        lowered = {k.lower() for k in obj}
        if "doi" in lowered or "title" in lowered:
            return "publisher"
    if isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj):
        probes = [{k.lower() for k in x} for x in obj[:5]]
        if any("doi" in s or "title" in s for s in probes):
            return "publisher"
    if f.endswith(".json"):
        return "unknown_json"
    return "unknown"


def rel_path(path, root):
    try:
        rp = os.path.relpath(path, root)
        if not rp.startswith(".."):
            return rp
    except ValueError:
        pass
    return path


def discover_materials(case_path, case_obj, changes, uncertainty):
    """发现材料:case.json 声明的 materials + case 目录下全部 *.json(去重、排序)。"""
    case_dir = os.path.dirname(os.path.abspath(case_path)) or "."
    candidates = []
    for m in case_obj.get("materials") or []:
        p = m if os.path.isabs(m) else os.path.join(case_dir, m)
        candidates.append(os.path.normpath(p))
    for root, dirs, files in os.walk(case_dir):
        dirs.sort()
        for fn in sorted(files):
            if fn.lower().endswith(".json") and \
                    fn != os.path.basename(case_path):
                candidates.append(os.path.normpath(os.path.join(root, fn)))
    ordered = sorted(set(candidates))
    materials = []
    for p in ordered:
        entry = {"path": rel_path(p, case_dir), "abs_path": p,
                 "sha256": None, "classified_as": None, "error": None}
        try:
            with open(p, "rb") as f:
                raw = f.read()
            entry["sha256"] = hashlib.sha256(raw).hexdigest()
            obj = json.loads(raw.decode("utf-8"))
            entry["classified_as"] = classify_payload(
                obj, os.path.basename(p))
            materials.append((entry, obj))
        except (OSError, UnicodeDecodeError, ValueError) as e:
            entry["error"] = "%s: %s" % (type(e).__name__, e)
            uncertainty.append("material unreadable or invalid JSON: %s (%s)"
                               % (entry["path"], entry["error"]))
            materials.append((entry, None))
    log_change(changes, "intake", "materials_discovered",
               "; ".join("%s=>%s" % (e["path"], e["classified_as"] or "ERROR")
                         for e, _ in materials) or "none")
    return materials


# ---------------------------------------------------------------- 去重合并

def cluster_and_merge(members):
    members = sorted(members, key=lambda m: (m["artifact"], m["locator"]))
    clusters = []
    for m in members:
        r = m["record"]
        doi, pmid = r["doi"], r["pmid"]
        tya = (norm_title(r["title"]), r["year"],
               norm_surname(r["first_author"]))
        target = basis = None
        for cl in clusters:
            if doi and doi in cl["dois"]:
                target, basis = cl, "doi"
                break
            if pmid and pmid in cl["pmids"]:
                target, basis = cl, "pmid"
                break
            if all(x is not None for x in tya) and cl["tya"] == tya:
                target, basis = cl, "title+year+first_author"
                break
        if target is None:
            clusters.append({
                "members": [m],
                "dois": {doi} if doi else set(),
                "pmids": {pmid} if pmid else set(),
                "tya": tya,
                "bases": set(),
            })
        else:
            target["members"].append(m)
            if doi:
                target["dois"].add(doi)
            if pmid:
                target["pmids"].add(pmid)
            target["bases"].add(basis)
    canon = [merge_cluster(i, cl) for i, cl in enumerate(clusters)]
    canon.sort(key=lambda c: c["record_id"])
    return canon


def conflict_key(field, v):
    if field == "title":
        return norm_title(v)
    if field == "authors":
        return tuple(sorted(str(x).lower() for x in v))
    return str(v).strip().lower()


def merge_cluster(idx, cl):
    members = sorted(
        cl["members"],
        key=lambda m: (-SOURCE_PRIORITY.get(m["source"], 0),
                       m["artifact"], m["locator"]))
    merged, prov, conflicts = {}, {}, []
    for field in KEY_FIELDS:
        chosen = None
        for m in members:
            v = m["record"].get(field)
            if is_present(v):
                chosen = (v, m)
                break
        if chosen:
            v, m = chosen
            merged[field] = v
            prov[field] = {"state": "value", "source": m["source"],
                           "artifact": m["artifact"], "locator": m["locator"]}
        else:
            merged[field] = [] if field == "authors" else None
            prov[field] = {"state": "not_provided_by_any_source",
                           "source": None, "artifact": None, "locator": None}
        # 冲突:跨来源同字段出现 >1 种不同取值
        variants = {}
        for m in members:
            v = m["record"].get(field)
            if is_present(v):
                variants.setdefault(conflict_key(field, v), set()).add(
                    m["source"])
        if len(variants) > 1:
            distinct = sorted({str(v) for m in members
                               for v in [m["record"].get(field)]
                               if is_present(v)})
            conflicts.append({
                "field": field,
                "variants": distinct,
                "resolution": "per-field source priority: %s"
                              % (prov[field]["source"] or "none"),
            })
    return {
        "record_id": "rec-%04d" % (idx + 1),
        "merged": merged,
        "field_provenance": prov,
        "sources_seen": sorted({m["source"] for m in members}),
        "dedup": {
            "cluster_size": len(members),
            "match_basis": sorted(cl["bases"]),
            "members": [{"source": m["source"], "artifact": m["artifact"],
                         "locator": m["locator"],
                         "missing_fields": m["missing_fields"]}
                        for m in members],
        },
        "conflicts": conflicts,
    }


# ---------------------------------------------------------------- 排序

def extract_terms(text):
    words = re.findall(r"[a-zA-Z][a-zA-Z\-]{3,}", (text or "").lower())
    return sorted({w.strip("-") for w in words
                   if w.strip("-") and w.strip("-") not in STOPWORDS})


def graph_in_degrees(graph_obj):
    """边语义 citing -> cited;返回被引 DOI 的入度。"""
    deg = {}
    if not isinstance(graph_obj, dict):
        return deg
    edges = graph_obj.get("edges") or []
    for e in edges:
        if isinstance(e, (list, tuple)) and len(e) >= 2:
            cited = norm_doi(e[1])
            if cited:
                deg[cited] = deg.get(cited, 0) + 1
        elif isinstance(e, dict):
            cited = norm_doi(e.get("cited") or e.get("target") or e.get("to"))
            if cited:
                deg[cited] = deg.get(cited, 0) + 1
    return deg


def rank_records(canon, terms, in_degrees):
    scored = []
    for c in canon:
        m = c["merged"]
        title = (m["title"] or "").lower()
        ctx = " ".join([m["journal"] or "",
                        " ".join(m["authors"] or [])]).lower()
        title_hits = sorted(t for t in terms if t in title)
        ctx_hits = sorted(t for t in terms
                          if t not in title_hits and t in ctx)
        boost = in_degrees.get(m["doi"], 0) if m["doi"] else 0
        score = 3 * len(title_hits) + len(ctx_hits) + 2 * boost
        scored.append({
            "record_id": c["record_id"],
            "score": score,
            "matched_terms": title_hits + ctx_hits,
            "title_matches": title_hits,
            "context_matches": ctx_hits,
            "citation_boost": boost,
        })
    order = sorted(scored, key=lambda s: (-s["score"], s["record_id"]))
    for i, s in enumerate(order):
        s["rank"] = i + 1
    return order


# ---------------------------------------------------------------- 覆盖矩阵

def compute_coverage(canon, db_names):
    """成员级计数:单元格 = 该来源库的记录(member)中该字段非空的条数。"""
    dbs = sorted(set(db_names) |
                 {mem["source"] for c in canon
                  for mem in c["dedup"]["members"]})
    matrix = {f: {db: 0 for db in dbs} for f in KEY_FIELDS}
    for c in canon:
        for mem in c["dedup"]["members"]:
            missing = set(mem.get("missing_fields", []))
            for f in KEY_FIELDS:
                if f not in missing and mem["source"] in matrix[f]:
                    matrix[f][mem["source"]] += 1
    merged_counts = {f: sum(1 for c in canon if is_present(c["merged"][f]))
                     for f in KEY_FIELDS}
    single = [{"record_id": c["record_id"], "doi": c["merged"]["doi"],
               "source": c["sources_seen"][0]}
              for c in canon if len(c["sources_seen"]) == 1]
    absent = {}
    for db in dbs:
        miss = sorted(f for f in KEY_FIELDS
                      if matrix[f][db] == 0 and merged_counts[f] > 0)
        if miss:
            absent[db] = miss
    return {
        "databases": dbs,
        "matrix": matrix,
        "merged_counts": merged_counts,
        "single_source_records": single,
        "systematically_absent": absent,
    }


# ---------------------------------------------------------------- 契约发现

def parse_output_contract(raw):
    """三种形态:dict field->spec;list of names;string newline list(保持出现顺序)。"""
    fields = []
    if isinstance(raw, dict):
        for name in raw:
            spec = raw[name]
            fields.append({"name": str(name),
                           "spec": spec if isinstance(spec, str) else
                           json.dumps(spec, ensure_ascii=False,
                                      sort_keys=True),
                           "spec_source": "case.json:output_contract(dict)"})
    elif isinstance(raw, list):
        for name in raw:
            fields.append({"name": str(name), "spec": "",
                           "spec_source": "case.json:output_contract(list)"})
    elif isinstance(raw, str):
        for line in raw.splitlines():
            line = line.strip().strip("-*").strip()
            if line:
                fields.append({"name": line, "spec": "",
                               "spec_source": "case.json:output_contract(str)"})
    return fields


def mine_task_deliverables(task_text):
    """挖掘 task.md 中显式要求的交付物:反引号字段名 + 输出/字段行内标识符。"""
    mined = set()
    for tok in re.findall(r"`([A-Za-z_][A-Za-z0-9_]{1,60})`", task_text or ""):
        mined.add(tok)
    for line in (task_text or "").splitlines():
        low = line.lower()
        if any(h in low for h in ("输出字段", "output field", "deliverable",
                                  "交付字段", "结果字段")):
            for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,60}", line):
                mined.add(tok)
    return sorted(mined)


def extract_scope_notes(task_text):
    notes = []
    for line in (task_text or "").splitlines():
        s = line.strip().lstrip("-*#> ").strip()
        if not s:
            continue
        low = s.lower()
        if any(h in low for h in SCOPE_HINTS):
            notes.append(s)
    seen, out = set(), []
    for n in notes:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out[:8]


# ---------------------------------------------------------------- 渲染

def source_badges(sources):
    return "+".join(BADGE.get(s, s) for s in sources)


def render_candidate_table(ctx):
    lines = []
    lines.append("# Candidate Table(候选排序表)")
    lines.append("")
    lines.append("- case_id: `%s`" % ctx["case_id"])
    lines.append("- canonical records: %d" % len(ctx["canon"]))
    lines.append("<!-- canonical_records:%d -->" % len(ctx["canon"]))
    lines.append("- generated_by: render_forge.py v%s (deterministic, "
                 "no wall-clock)" % VERSION)
    lines.append("- 排序公式: score = 3×标题命中 + 1×上下文命中 + "
                 "2×引用图入度;同分按 record_id 字典序。")
    lines.append("")
    lines.append("## Scope notes(来自 task.md 的纳入/排除口径)")
    lines.append("")
    if ctx["scope_notes"]:
        for n in ctx["scope_notes"]:
            lines.append("- %s" % n)
    else:
        lines.append("- (task.md 未给出显式 scope 口径)")
    lines.append("")
    lines.append("## Ranked candidates")
    lines.append("")
    lines.append("| rank | record_id | DOI | PMID | year | title | "
                 "matched query terms | score | source dbs |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    by_id = {c["record_id"]: c for c in ctx["canon"]}
    for s in ctx["ranking"]:
        c = by_id[s["record_id"]]
        m = c["merged"]
        lines.append("| %d | %s | %s | %s | %s | %s | %s | %d | %s |" % (
            s["rank"], c["record_id"], m["doi"] or "—", m["pmid"] or "—",
            m["year"] if m["year"] is not None else "—",
            (m["title"] or "—").replace("|", "\\|"),
            ", ".join(s["matched_terms"]) or "—",
            s["score"], source_badges(c["sources_seen"])))
    lines.append("")
    lines.append("> source db badges: CR=crossref, EP=europepmc, "
                 "PU=publisher, MR=merged_records(上游)。")
    lines.append("")
    return "\n".join(lines)


def render_provenance_chain(ctx):
    lines = []
    lines.append("# Provenance Chain(逐记录溯源链)")
    lines.append("")
    lines.append("- case_id: `%s`" % ctx["case_id"])
    lines.append("- 链式记号: 来源库 → 材料工件 → 原始响应定位(JSON 路径) → "
                 "字段映射 → 去重判定 → 合并取值(逐字段来源标注)")
    lines.append("- 合并优先级: publisher > crossref > europepmc(逐字段独立裁决)")
    lines.append("")
    for c in ctx["canon"]:
        m, p = c["merged"], c["field_provenance"]
        lines.append("## %s — %s" % (c["record_id"], m["doi"] or m["title"]))
        lines.append("")
        lines.append("- 来源库 → 材料 → 定位:")
        for mem in c["dedup"]["members"]:
            lines.append("  - %s → `%s` @ `%s`"
                         % (mem["source"], mem["artifact"], mem["locator"]))
        lines.append("- 去重判定: cluster_size=%d; match_basis: %s" % (
            c["dedup"]["cluster_size"],
            ", ".join(c["dedup"]["match_basis"]) or "(singleton)"))
        lines.append("- 合并取值(逐字段来源):")
        lines.append("")
        lines.append("| field | merged value | source db | artifact | "
                     "locator | state |")
        lines.append("|---|---|---|---|---|---|")
        for f in KEY_FIELDS:
            pv = p[f]
            val = m[f]
            if isinstance(val, list):
                val_s = "; ".join(val) if val else "—"
            else:
                val_s = str(val) if val is not None else "—"
            lines.append("| %s | %s | %s | %s | %s | %s |" % (
                f, val_s.replace("|", "\\|"), pv["source"] or "—",
                pv["artifact"] or "—", pv["locator"] or "—", pv["state"]))
        lines.append("")
        if c["conflicts"]:
            lines.append("- 跨来源冲突:")
            for cf in c["conflicts"]:
                lines.append("  - `%s`: %d variants; %s"
                             % (cf["field"], len(cf["variants"]),
                                cf["resolution"]))
                for v in cf["variants"]:
                    lines.append("    - variant: %s" % v.replace("|", "\\|"))
        else:
            lines.append("- 跨来源冲突: 无")
        lines.append("- 成员缺失字段(该来源记录中为空):")
        for mem in c["dedup"]["members"]:
            miss = ", ".join(mem["missing_fields"]) or "none"
            lines.append("  - %s @ `%s`: %s"
                         % (mem["source"], mem["locator"], miss))
        lines.append("")
    return "\n".join(lines)


def render_coverage_matrix(ctx):
    cov = ctx["coverage"]
    dbs = cov["databases"]
    lines = []
    lines.append("# Coverage Matrix(数据库 × 关键字段 覆盖矩阵)")
    lines.append("")
    lines.append("- case_id: `%s`" % ctx["case_id"])
    lines.append("- 单元格 = 该来源库的记录中该字段非空的条数;"
                 "`merged` 列 = 合并后规范记录该字段非空的条数。")
    lines.append("")
    lines.append("<!-- matrix:begin -->")
    lines.append("| field | " + " | ".join(dbs + ["merged"]) + " |")
    lines.append("|" + "---|" * (len(dbs) + 2))
    for f in KEY_FIELDS:
        cells = [str(cov["matrix"][f][db]) for db in dbs]
        cells.append(str(cov["merged_counts"][f]))
        lines.append("| %s | %s |" % (f, " | ".join(cells)))
    lines.append("<!-- matrix:end -->")
    lines.append("")
    lines.append("## 单一来源记录(single-source-only,需人工复核)")
    lines.append("")
    if cov["single_source_records"]:
        lines.append("| record_id | doi | sole source |")
        lines.append("|---|---|---|")
        for r in cov["single_source_records"]:
            lines.append("| %s | %s | %s |"
                         % (r["record_id"], r["doi"] or "—", r["source"]))
    else:
        lines.append("- (无:每条规范记录均 ≥2 个来源)")
    lines.append("")
    lines.append("## 系统性缺失字段(某库 0 覆盖、但合并后存在)")
    lines.append("")
    if cov["systematically_absent"]:
        for db in sorted(cov["systematically_absent"]):
            lines.append("- %s: %s"
                         % (db, ", ".join(cov["systematically_absent"][db])))
    else:
        lines.append("- (无)")
    lines.append("")
    lines.append("## Review appendix")
    lines.append("")
    lines.append("### Unresolved contract fields(未决契约字段)")
    lines.append("")
    if ctx["unresolved"]:
        for u in ctx["unresolved"]:
            lines.append("- `%s`: %s" % (u["field"], u["reason"]))
    else:
        lines.append("- (无:全部契约字段均已按语义填充)")
    lines.append("")
    lines.append("### Conflicts(跨来源字段冲突清单)")
    lines.append("")
    any_cf = False
    for c in ctx["canon"]:
        for cf in c["conflicts"]:
            any_cf = True
            lines.append("- %s `%s`: %d variants (%s)"
                         % (c["record_id"], cf["field"],
                            len(cf["variants"]), cf["resolution"]))
    if not any_cf:
        lines.append("- (无)")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- 契约填充

def fill_contract_field(name, ctx):
    """按字段名语义填充;填不出返回 (None, reason) —— 绝不编造。"""
    n = name.lower()
    if n in RESERVED_KEYS:
        return None, ("contract field name collides with reserved "
                      "result.json key '%s'") % name
    if "candidate" in n:
        return ctx["canon"], None
    if "rank" in n:
        return {
            "method": "score = 3*title_term_hits + 1*context_term_hits + "
                      "2*in_graph_citations; deterministic tie-break "
                      "by record_id",
            "terms": ctx["terms"],
            "ranking": [{k: s[k] for k in
                         ("rank", "record_id", "score", "matched_terms",
                          "citation_boost")} for s in ctx["ranking"]],
        }, None
    if "evidence" in n:
        return [{"record_id": c["record_id"],
                 "sources_seen": c["sources_seen"],
                 "dedup": c["dedup"],
                 "field_provenance": c["field_provenance"]}
                for c in ctx["canon"]], None
    if "coverage" in n:
        return ctx["coverage"], None
    if "status" in n or "note" in n:
        return {"status_notes": ctx["status_notes"],
                "uncertainty": ctx["uncertainty"]}, None
    if "graph" in n or "reference" in n:
        return ctx["graph_summary"], None
    if "import" in n:
        return ctx["import_state"], None
    return None, ("no semantic filler available for contract field '%s' "
                  "(null + unresolved, no fabrication)") % name


# ---------------------------------------------------------------- 门控

def parse_embedded_counts(candidate_md, coverage_md):
    """从渲染产物解析被声明的数字,供门控重算比对。"""
    declared = {}
    mc = re.search(r"<!-- canonical_records:(\d+) -->", candidate_md)
    if mc:
        declared["canonical_records"] = int(mc.group(1))
    matrix = {}
    mm = re.search(r"<!-- matrix:begin -->(.*?)<!-- matrix:end -->",
                   coverage_md, re.S)
    if mm:
        for line in mm.group(1).splitlines():
            line = line.strip()
            if not line.startswith("|") or "---" in line or "field" in line:
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 2 and cells[0] and all(
                    re.fullmatch(r"\d+", c) for c in cells[1:]):
                matrix[cells[0]] = [int(c) for c in cells[1:]]
    declared["matrix"] = matrix
    return declared


# ---------------------------------------------------------------- 主流程

def build_result_skeleton():
    return {
        "case_id": None,
        "status": "partial",
        "generated_by": "render_forge.py v%s" % VERSION,
        "sources": [],
        "uncertainty": ["STEP 0 skeleton written before input intake; "
                        "no values inferred yet"],
        "change_records": [{"seq": 1, "step": "step0",
                            "action": "skeleton_written",
                            "detail": "honest early partial result.json"}],
        "artifacts": [],
        "unresolved_contract_fields": [],
    }


def run(args, changes, uncertainty):
    work, out = args.work, args.out
    case_path = args.case

    # ---- 1. case.json(致命问题 -> InputError) ----
    if not os.path.isfile(case_path):
        raise InputError("case.json not found: %s" % case_path)
    try:
        with open(case_path, "rb") as f:
            raw = f.read()
        case_obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise InputError("case.json invalid JSON/UTF-8: %s" % e)
    if not isinstance(case_obj, dict):
        raise InputError("case.json must be a JSON object")
    case_id = case_obj.get("case_id")
    if not case_id:
        raise InputError("case.json missing case_id")
    log_change(changes, "intake", "case_loaded", "case_id=%s" % case_id)

    # ---- 2. task.md ----
    task_text = ""
    if os.path.isfile(args.task):
        with open(args.task, "r", encoding="utf-8", errors="replace") as f:
            task_text = f.read()
        log_change(changes, "intake", "task_loaded",
                   "task.md chars=%d" % len(task_text))
    else:
        uncertainty.append("task.md not found at %s; scope mining skipped"
                           % args.task)
        log_change(changes, "intake", "task_missing", args.task)

    # ---- 3. 契约发现 ----
    contract_fields = parse_output_contract(case_obj.get("output_contract"))
    mined = mine_task_deliverables(task_text)
    contract_names = [f["name"] for f in contract_fields]
    for f in contract_fields:
        if f["name"] in mined:
            f["spec_source"] += "+task.md"
    contract_doc = {
        "case_id": case_id,
        "contract_fields": contract_fields,
        "task_mined_candidates": [t for t in mined if t not in contract_names],
        "note": ("contract fields 仅来自 case.json:output_contract;task.md "
                 "挖掘仅作佐证,绝不新增契约字段"),
    }
    write_json(os.path.join(work, "contract_fields.json"), contract_doc)
    log_change(changes, "contract", "contract_discovered",
               "fields=%s" % (",".join(contract_names) or "(empty)"))
    if not contract_names:
        uncertainty.append("output_contract empty or absent; result.json "
                           "will carry only harness-level keys")

    # ---- 4. 证据摄入(上游 merged_records 优先) ----
    canon, graph_obj, import_obj, sources_meta = [], None, None, []
    merged_path = os.path.join(work, "merged_records.json")
    consumed_upstream = False
    if os.path.isfile(merged_path):
        try:
            with open(merged_path, "r", encoding="utf-8") as f:
                up = json.load(f)
            if isinstance(up, dict) and isinstance(up.get("records"), list):
                canon = up["records"]
                consumed_upstream = True
                log_change(changes, "intake",
                           "consumed_upstream_merged_records",
                           "work/merged_records.json records=%d" % len(canon))
        except (UnicodeDecodeError, ValueError, OSError) as e:
            uncertainty.append("work/merged_records.json unreadable (%s); "
                               "falling back to built-in pipeline" % e)
    materials = discover_materials(case_path, case_obj, changes, uncertainty)
    for entry, obj in materials:
        sources_meta.append({"path": entry["path"],
                             "sha256": entry["sha256"],
                             "classified_as": entry["classified_as"]})
        if obj is None:
            continue
        if entry["classified_as"] == "reference_graph":
            graph_obj = obj
        elif entry["classified_as"] == "import_state":
            import_obj = obj
    if not consumed_upstream:
        members = []
        for entry, obj in materials:
            if obj is None:
                continue
            kind = entry["classified_as"]
            if kind == "crossref":
                members.extend(extract_crossref(obj, entry["path"]))
            elif kind == "europepmc":
                members.extend(extract_europepmc(obj, entry["path"]))
            elif kind == "publisher":
                members.extend(extract_publisher(obj, entry["path"]))
            elif kind in ("reference_graph", "import_state"):
                pass
            else:
                uncertainty.append("unclassified material kept as raw "
                                   "source only: %s" % entry["path"])
        if not members:
            uncertainty.append("no bibliographic records extracted from "
                               "any material; evidence-dependent contract "
                               "fields left null")
        canon = cluster_and_merge(members)
        write_json(merged_path, {"case_id": case_id, "records": canon})
        log_change(changes, "intake", "pipeline_ran",
                   "members=%d canonical=%d" % (len(members), len(canon)))

    # ---- 5. 汇总上下文 ----
    db_names = sorted({m["classified_as"] for m in sources_meta
                       if m["classified_as"] in SOURCE_PRIORITY})
    if not db_names:
        db_names = sorted({s for c in canon
                           for s in c.get("sources_seen", [])})
    in_deg = graph_in_degrees(graph_obj)
    research_q = " ".join(
        [str(case_obj.get("research_question") or ""),
         str(case_obj.get("query") or "")])
    terms = sorted(set(extract_terms(research_q)) |
                   set(extract_terms(task_text)))
    ranking = rank_records(canon, terms, in_deg)
    coverage = compute_coverage(canon, db_names)
    scope_notes = extract_scope_notes(task_text)

    status_notes = []
    if coverage["single_source_records"]:
        status_notes.append(
            "%d record(s) supported by a single source only: %s" % (
                len(coverage["single_source_records"]),
                ", ".join(r["record_id"]
                          for r in coverage["single_source_records"])))
    if coverage["systematically_absent"]:
        for db in sorted(coverage["systematically_absent"]):
            status_notes.append("fields systematically absent in %s: %s"
                                % (db, ", ".join(
                                    coverage["systematically_absent"][db])))
    n_conf = sum(len(c["conflicts"]) for c in canon)
    if n_conf:
        status_notes.append("%d cross-source field conflict(s) resolved by "
                            "per-field priority" % n_conf)
    if consumed_upstream:
        status_notes.append("canonical records consumed from upstream "
                            "work/merged_records.json (pipeline skipped)")

    graph_summary = None
    if isinstance(graph_obj, dict):
        nodes = graph_obj.get("nodes") or []
        edges = graph_obj.get("edges") or []
        graph_summary = {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "edge_semantics": graph_obj.get("edge_semantics",
                                            "assumed citing -> cited"),
            "in_degree_for_canonical_dois": {
                c["merged"]["doi"]: in_deg.get(c["merged"]["doi"], 0)
                for c in canon if c["merged"].get("doi")},
        }

    ctx = {
        "case_id": case_id, "canon": canon, "ranking": ranking,
        "terms": terms, "coverage": coverage, "scope_notes": scope_notes,
        "graph_summary": graph_summary, "import_state": import_obj,
        "status_notes": status_notes, "uncertainty": uncertainty,
        "unresolved": [],
    }

    # ---- 6. 渲染 ----
    candidate_md = render_candidate_table(ctx)
    provenance_md = render_provenance_chain(ctx)
    coverage_md = render_coverage_matrix(ctx)
    write_text(os.path.join(out, "candidate_table.md"), candidate_md)
    write_text(os.path.join(out, "provenance_chain.md"), provenance_md)
    write_text(os.path.join(out, "coverage_matrix.md"), coverage_md)
    log_change(changes, "render", "artifacts_rendered",
               "candidate_table.md, provenance_chain.md, coverage_matrix.md")

    # ---- 7. 契约填充 ----
    result = {
        "case_id": case_id,
        "status": "partial",
        "generated_by": "render_forge.py v%s" % VERSION,
        "sources": sorted(sources_meta, key=lambda s: s["path"]),
        "uncertainty": [],
        "change_records": changes,
        "artifacts": [],
        "unresolved_contract_fields": [],
    }
    for f in contract_fields:
        value, reason = fill_contract_field(f["name"], ctx)
        result[f["name"]] = value
        if value is None:
            result["unresolved_contract_fields"].append(
                {"field": f["name"], "reason": reason})
            uncertainty.append("contract field '%s' unresolved: %s"
                               % (f["name"], reason))
            log_change(changes, "contract", "field_unresolved",
                       "%s: %s" % (f["name"], reason))
    ctx["unresolved"] = result["unresolved_contract_fields"]

    # ---- 8. 门控 ----
    checks = []
    missing_keys = [n for n in contract_names if n not in result]
    checks.append({
        "check": "all contract fields present as keys in result.json",
        "result": "PASS" if not missing_keys else "FAIL",
        "detail": ("missing: %s" % ",".join(missing_keys)) if missing_keys
        else "none"})
    # unresolved 落定后重渲染 coverage(其 review appendix 依赖 unresolved)
    coverage_md = render_coverage_matrix(ctx)
    write_text(os.path.join(out, "coverage_matrix.md"), coverage_md)

    artifact_names = ["candidate_table.md", "provenance_chain.md",
                      "coverage_matrix.md", "render_gate_report.md"]
    write_text(os.path.join(out, "render_gate_report.md"),
               "# Render Gate Report\n\n(draft)\n")

    declared = parse_embedded_counts(candidate_md, coverage_md)
    recomputed = {
        "canonical_records": len(canon),
        "matrix": {f: [coverage["matrix"][f][db] for db in db_names] +
                        [coverage["merged_counts"][f]]
                   for f in KEY_FIELDS},
    }
    ok_count = (declared.get("canonical_records") ==
                recomputed["canonical_records"])
    checks.append({
        "check": "candidate count recomputed from data matches rendered claim",
        "result": "PASS" if ok_count else "FAIL",
        "detail": "rendered=%s recomputed=%d" % (
            declared.get("canonical_records"),
            recomputed["canonical_records"])})
    matrix_ok = all(
        declared["matrix"].get(f) == recomputed["matrix"][f]
        for f in KEY_FIELDS)
    checks.append({
        "check": "coverage matrix counts recomputed from data match "
                 "rendered rows",
        "result": "PASS" if matrix_ok else "FAIL",
        "detail": "rows compared: %d" % len(KEY_FIELDS)})

    null_unlisted = [u["field"] for u in result["unresolved_contract_fields"]]
    consistent = all(
        (result.get(f["name"]) is None) == (f["name"] in null_unlisted)
        for f in contract_fields)
    checks.append({
        "check": "null contract fields consistent with "
                 "unresolved_contract_fields",
        "result": "PASS" if consistent else "FAIL",
        "detail": ("unresolved: %s" % ",".join(null_unlisted))
        if null_unlisted else "none"})

    artifact_bad, artifact_entries = [], []
    for name in sorted(artifact_names):
        p = os.path.join(out, name)
        if not os.path.isfile(p):
            artifact_bad.append("%s missing" % name)
            artifact_entries.append({"path": name, "location": "out",
                                     "sha256": None})
            continue
        digest = sha256_file(p)
        artifact_entries.append({"path": name, "location": "out",
                                 "sha256": digest})
    checks.append({
        "check": "every artifact present with sha256",
        "result": "PASS" if not artifact_bad else "FAIL",
        "detail": "; ".join(artifact_bad) or
                  "%d artifacts hashed" % len(artifact_entries)})
    result["artifacts"] = artifact_entries

    gate_lines = ["# Render Gate Report", "",
                  "- case_id: `%s`" % case_id,
                  "- gate: all rendered claims recomputed from data; hashes "
                  "verified; no fabricated values", "",
                  "| # | check | result | detail |",
                  "|---|---|---|---|"]
    for i, c in enumerate(checks, 1):
        gate_lines.append("| %d | %s | %s | %s |" % (
            i, c["check"], c["result"], c["detail"].replace("|", "\\|")))
    gate_lines.append("")
    all_pass = all(c["result"] == "PASS" for c in checks)
    gate_lines.append("gate_overall: %s" % ("PASS" if all_pass else "FAIL"))
    gate_lines.append("")
    write_text(os.path.join(out, "render_gate_report.md"),
               "\n".join(gate_lines))
    for e in result["artifacts"]:
        if e["path"] == "render_gate_report.md":
            e["sha256"] = sha256_file(
                os.path.join(out, "render_gate_report.md"))
    log_change(changes, "gate", "gate_evaluated",
               "checks=%d overall=%s" % (
                   len(checks), "PASS" if all_pass else "FAIL"))

    # ---- 9. 定态 ----
    if all_pass and not result["unresolved_contract_fields"] and canon:
        result["status"] = "success"
    else:
        result["status"] = "partial"
        if not canon:
            uncertainty.append("no canonical records; evidence-dependent "
                               "contract fields left null")
    result["uncertainty"] = sorted(set(uncertainty))
    write_json(os.path.join(out, "result.json"), result)
    return EXIT_OK if result["status"] == "success" else EXIT_DEGRADED


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="render_forge.py",
        description="contract-render-forge: downstream contract discovery, "
                    "evidence intake, deterministic rendering and gated "
                    "assembly of result.json (stdlib only, offline, "
                    "deterministic).")
    ap.add_argument("--case", default="/input/case.json",
                    help="path to case.json (default: /input/case.json)")
    ap.add_argument("--task", default="/input/task.md",
                    help="path to task.md (default: /input/task.md)")
    ap.add_argument("--work", default="/app/work",
                    help="work directory (default: /app/work)")
    ap.add_argument("--out", default="/app/output",
                    help="output directory (default: /app/output)")
    args = ap.parse_args(argv)

    try:
        os.makedirs(args.work, exist_ok=True)
        os.makedirs(args.out, exist_ok=True)
    except OSError as e:
        sys.stderr.write("cannot create work/out dirs: %s\n" % e)
        return EXIT_INPUT_ERROR

    out_result = os.path.join(args.out, "result.json")
    changes = []
    uncertainty = []

    # STEP 0:诚实早期骨架 —— 在读入任何输入之前写出
    skeleton = build_result_skeleton()
    try:
        write_json(out_result, skeleton)
    except OSError as e:
        sys.stderr.write("cannot write skeleton result.json: %s\n" % e)
        return EXIT_INPUT_ERROR
    changes = skeleton["change_records"]
    defaults = {"case": "/input/case.json", "task": "/input/task.md",
                "work": "/app/work", "out": "/app/output"}
    log_change(changes, "intake", "args",
               "; ".join("%s=%s" % (k, "default" if getattr(args, k) == v
                                    else "custom")
                         for k, v in sorted(defaults.items())))

    try:
        return run(args, changes, uncertainty)
    except InputError as e:
        result = build_result_skeleton()
        result["change_records"] = changes
        result["status"] = "input_error"
        result["uncertainty"] = sorted(set(uncertainty + [str(e)]))
        try:
            write_json(out_result, result)
        except OSError:
            pass
        return EXIT_INPUT_ERROR
    except Exception as e:  # 永不崩溃:诚实降级
        result = build_result_skeleton()
        result["change_records"] = changes
        result["status"] = "partial"
        result["uncertainty"] = sorted(set(
            uncertainty + ["unexpected %s: %s" % (type(e).__name__, e)]))
        try:
            write_json(out_result, result)
        except OSError:
            pass
        return EXIT_DEGRADED


if __name__ == "__main__":
    sys.exit(main())
