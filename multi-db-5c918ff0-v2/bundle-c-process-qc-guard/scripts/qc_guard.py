#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qc_guard.py — 多数据库联合检索的"过程质量控制"流水线(process-qc-guard)。

设计哲学:多库合并结果的可信度,取决于运行本身是否被检查点化、可恢复、
预算安全、可重放一致,并在交付前通过显式自查门(self-check gate)。

阶段: intake -> normalize -> identity -> coverage -> report
每个阶段: 重算输入哈希 -> (可选)按 --resume 跳过 -> 执行 -> 校验阶段不变量
         -> 写产物与检查点 -> 向 run_ledger.jsonl 追加一条带逻辑序号的事件行。

硬约束: Python 3 标准库;无网络;无随机性;产物中无墙钟时间、无绝对路径。
退出码: 0 = success;2 = 诚实降级(partial);3 = 输入非法(input_error)。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import unicodedata

TOOL_NAME = "qc_guard.py"
VERSION = "1.0.0"
STAGES = ["intake", "normalize", "identity", "coverage", "report"]
CANONICAL_FIELDS = ["doi", "pmid", "title", "year", "first_author_surname",
                    "authors", "journal", "volume", "issue", "pages"]
# 已知源模式缺失的字段概念(区别于"键缺失" missing 与"值为空" unknown)
NOT_PROVIDED_BY_SOURCE = {"crossref": {"pmid"}, "publisher": {"pmid"}}
DEFAULT_SOURCE_PRIORITY = ["publisher", "crossref", "europepmc"]
FUZZY_JACCARD_THRESHOLD = 0.6
DECISIONS_FILENAME = "arbitration_decisions.json"  # 模型判断产物,置于 work 目录


class QCFailure(Exception):
    """阶段不变量失败等可预期失败。"""


# ---------------------------------------------------------------------------
# 确定性 IO 与哈希
# ---------------------------------------------------------------------------

def _canon(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path):
    with open(path, "rb") as f:
        return sha256_bytes(f.read())


def sha256_json(obj):
    return sha256_bytes(_canon(obj).encode("utf-8"))


def write_json(path, obj):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True))
        f.write("\n")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 账本(逻辑序号,无墙钟)
# ---------------------------------------------------------------------------

class Ledger(object):
    def __init__(self, path):
        self.path = path
        self.seq = 0
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        self.seq += 1

    def emit(self, event, stage=None, detail=None):
        rec = {"seq": self.seq, "event": event, "stage": stage, "detail": detail}
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(_canon(rec) + "\n")
        self.seq += 1

    def events(self):
        out = []
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        out.append(json.loads(line))
        return out


# ---------------------------------------------------------------------------
# 文本规范化
# ---------------------------------------------------------------------------

def norm_doi(d):
    if d is None:
        return None
    s = str(d).strip().lower()
    for p in ("https://doi.org/", "http://doi.org/", "http://dx.doi.org/",
              "https://dx.doi.org/", "doi.org/", "doi:"):
        if s.startswith(p):
            s = s[len(p):]
    s = s.strip().strip("/")
    return s or None


def norm_text(s):
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", str(s)).casefold()
    s = re.sub(r"[^\w]+", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def title_tokens(title):
    t = norm_text(title)
    return t.split() if t else []


def norm_year(y):
    if y is None:
        return None
    m = re.search(r"(\d{4})", str(y))
    return m.group(1) if m else None


def norm_surname(s):
    return norm_text(s).replace(" ", "") if s else None


def jaccard(toks_a, toks_b):
    a, b = set(toks_a), set(toks_b)
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


# ---------------------------------------------------------------------------
# 字段状态: ok / missing(键缺失) / unknown(值为空) / not_provided(源模式无此概念)
# ---------------------------------------------------------------------------

def fld_ok(v):
    return {"value": v, "status": "ok"}


def fld_none(status):
    return {"value": None, "status": status}


def field_from(item, key, source_db, canon_name, transform=None):
    if canon_name in NOT_PROVIDED_BY_SOURCE.get(source_db, set()):
        return fld_none("not_provided")
    if key not in item:
        return fld_none("missing")
    v = item.get(key)
    if transform is not None and v is not None:
        try:
            v = transform(v)
        except Exception:
            v = None
    if v is None or v == "" or v == []:
        return fld_none("unknown")
    return fld_ok(v)


# ---------------------------------------------------------------------------
# 各源解析为通用记录
# ---------------------------------------------------------------------------

def _first_surname_from_crossref(item):
    au = item.get("author")
    if isinstance(au, list) and au and isinstance(au[0], dict):
        fam = au[0].get("family")
        if fam:
            return str(fam)
    return None


def _authors_from_crossref(item):
    au = item.get("author")
    out = []
    if isinstance(au, list):
        for a in au:
            if isinstance(a, dict):
                fam = a.get("family") or ""
                giv = a.get("given") or ""
                name = (str(fam) + (" " + str(giv) if giv else "")).strip()
                if name:
                    out.append(name)
    return out or None


def _crossref_year(item):
    issued = item.get("issued")
    if isinstance(issued, dict):
        dp = issued.get("date-parts")
        if isinstance(dp, list) and dp and isinstance(dp[0], list) and dp[0]:
            return norm_year(dp[0][0])
    return None


def parse_crossref(data):
    items = ((data or {}).get("message") or {}).get("items") or []
    records = []
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            it = {}
        title = it.get("title")
        title_v = None
        if isinstance(title, list) and title:
            title_v = str(title[0]) if title[0] else None
        elif isinstance(title, str):
            title_v = title
        ct = it.get("container-title")
        journal_v = None
        if isinstance(ct, list) and ct:
            journal_v = str(ct[0]) if ct[0] else None
        elif isinstance(ct, str):
            journal_v = ct
        f = {
            "doi": field_from(it, "DOI", "crossref", "doi"),
            "pmid": fld_none("not_provided"),
            "title": fld_ok(title_v) if title_v else (
                fld_none("missing") if "title" not in it else fld_none("unknown")),
            "year": fld_ok(_crossref_year(it)) if _crossref_year(it) else (
                fld_none("missing") if "issued" not in it else fld_none("unknown")),
            "first_author_surname": fld_ok(_first_surname_from_crossref(it)) if _first_surname_from_crossref(it) else (
                fld_none("missing") if "author" not in it else fld_none("unknown")),
            "authors": fld_ok(_authors_from_crossref(it)) if _authors_from_crossref(it) else (
                fld_none("missing") if "author" not in it else fld_none("unknown")),
            "journal": fld_ok(journal_v) if journal_v else (
                fld_none("missing") if "container-title" not in it else fld_none("unknown")),
            "volume": field_from(it, "volume", "crossref", "volume", str),
            "issue": field_from(it, "issue", "crossref", "issue", str),
            "pages": field_from(it, "page", "crossref", "pages", str),
        }
        records.append({"record_id": "crossref#%02d" % i, "source_db": "crossref",
                        "source_index": i, "fields": f})
    return records


def _surname_from_epmc_author_string(s):
    if not s:
        return None
    first = str(s).split(",")[0].strip()
    return first.split(" ")[0] if first else None


def _authors_from_epmc(s):
    if not s:
        return None
    out = [a.strip() for a in str(s).split(",") if a.strip()]
    return out or None


def parse_europepmc(data):
    results = ((data or {}).get("resultList") or {}).get("result") or []
    records = []
    for i, it in enumerate(results):
        if not isinstance(it, dict):
            it = {}
        f = {
            "doi": field_from(it, "doi", "europepmc", "doi", str),
            "pmid": field_from(it, "pmid", "europepmc", "pmid", str),
            "title": field_from(it, "title", "europepmc", "title", str),
            "year": field_from(it, "pubYear", "europepmc", "year", norm_year),
            "first_author_surname": fld_ok(_surname_from_epmc_author_string(it.get("authorString"))) if _surname_from_epmc_author_string(it.get("authorString")) else (
                fld_none("missing") if "authorString" not in it else fld_none("unknown")),
            "authors": fld_ok(_authors_from_epmc(it.get("authorString"))) if _authors_from_epmc(it.get("authorString")) else (
                fld_none("missing") if "authorString" not in it else fld_none("unknown")),
            "journal": field_from(it, "journalTitle", "europepmc", "journal", str),
            "volume": field_from(it, "journalVolume", "europepmc", "volume", str),
            "issue": field_from(it, "issue", "europepmc", "issue", str),
            "pages": field_from(it, "pageInfo", "europepmc", "pages", str),
        }
        records.append({"record_id": "europepmc#%02d" % i, "source_db": "europepmc",
                        "source_index": i, "fields": f})
    return records


def _surname_from_publisher_authors(authors):
    if isinstance(authors, list) and authors:
        toks = str(authors[0]).strip().split()
        if toks:
            return toks[-1]  # 出版方格式默认为 "Given Family"
    return None


def parse_publisher(data):
    if isinstance(data, dict):
        items = data.get("records") or []
    elif isinstance(data, list):
        items = data
    else:
        items = []
    records = []
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            it = {}
        surname = _surname_from_publisher_authors(it.get("authors"))
        authors = it.get("authors")
        if isinstance(authors, list):
            authors = [str(a) for a in authors if a] or None
        else:
            authors = None
        f = {
            "doi": field_from(it, "doi", "publisher", "doi", str),
            "pmid": fld_none("not_provided"),
            "title": field_from(it, "title", "publisher", "title", str),
            "year": field_from(it, "year", "publisher", "year", norm_year),
            "first_author_surname": fld_ok(surname) if surname else (
                fld_none("missing") if "authors" not in it else fld_none("unknown")),
            "authors": fld_ok(authors) if authors else (
                fld_none("missing") if "authors" not in it else fld_none("unknown")),
            "journal": field_from(it, "journal", "publisher", "journal", str),
            "volume": field_from(it, "volume", "publisher", "volume", str),
            "issue": field_from(it, "issue", "publisher", "issue", str),
            "pages": field_from(it, "pages", "publisher", "pages", str),
        }
        records.append({"record_id": "publisher#%02d" % i, "source_db": "publisher",
                        "source_index": i, "fields": f})
    return records


PARSERS = {"crossref": parse_crossref, "europepmc": parse_europepmc,
           "publisher": parse_publisher}


# ---------------------------------------------------------------------------
# 材料嗅探分类
# ---------------------------------------------------------------------------

def sniff_class(obj):
    if isinstance(obj, dict):
        if "resultList" in obj and "hitCount" in obj:
            return "europepmc"
        msg = obj.get("message")
        if isinstance(msg, dict) and "items" in msg:
            return "crossref"
        if "nodes" in obj and "edges" in obj:
            return "reference_graph"
        if isinstance(obj.get("records"), list):
            return "publisher"
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        return "publisher"
    return "unknown"


# ---------------------------------------------------------------------------
# 上下文与阶段输入哈希
# ---------------------------------------------------------------------------

def wpath(ctx, name):
    return os.path.join(ctx["work"], name)


def material_relpaths(ctx):
    mats = ctx["case"].get("materials") or []
    out = []
    for m in mats:
        if isinstance(m, dict):
            p = m.get("path") or m.get("file") or ""
        else:
            p = str(m)
        if p:
            out.append(p)
    return out


def material_abspath(ctx, rel):
    return os.path.join(ctx["case_dir"], rel)


def decisions_path(ctx):
    return wpath(ctx, DECISIONS_FILENAME)


def stage_input_hash(ctx, stage):
    if stage == "intake":
        files = [{"path": "__case__", "sha256": sha256_file(ctx["case_path"])}]
        if os.path.exists(ctx["task_path"]):
            files.append({"path": "__task__", "sha256": sha256_file(ctx["task_path"])})
        else:
            files.append({"path": "__task__", "sha256": "absent"})
        for rel in material_relpaths(ctx):
            ap = material_abspath(ctx, rel)
            files.append({"path": rel,
                          "sha256": sha256_file(ap) if os.path.exists(ap) else "missing"})
        return sha256_json({"stage": stage, "files": files})
    if stage == "normalize":
        return sha256_json({"stage": stage,
                            "materials_index": sha256_file(wpath(ctx, "materials_index.json"))})
    if stage == "identity":
        dp = decisions_path(ctx)
        return sha256_json({"stage": stage,
                            "normalized_records": sha256_file(wpath(ctx, "normalized_records.json")),
                            "arbitration_decisions": sha256_file(dp) if os.path.exists(dp) else "absent"})
    if stage == "coverage":
        return sha256_json({"stage": stage,
                            "merged_records": sha256_file(wpath(ctx, "merged_records.json"))})
    if stage == "report":
        rv = wpath(ctx, "replay_verdict.json")
        return sha256_json({
            "stage": stage,
            "case": sha256_file(ctx["case_path"]),
            "coverage_matrix": sha256_file(wpath(ctx, "coverage_matrix.json")),
            "merged_records": sha256_file(wpath(ctx, "merged_records.json")),
            "decision_log": sha256_file(wpath(ctx, "decision_log.json")),
            "arbitration_queue": sha256_file(wpath(ctx, "arbitration_queue.json")),
            "replay_verdict": sha256_file(rv) if os.path.exists(rv) else "absent"})
    raise QCFailure("unknown stage: %s" % stage)


def checkpoint_path(ctx, stage):
    return wpath(ctx, os.path.join("checkpoints", "%s.json" % stage))


def run_stage(ctx, stage, resume=False, force=False):
    ih = stage_input_hash(ctx, stage)
    cp_path = checkpoint_path(ctx, stage)
    cp = load_json(cp_path) if os.path.exists(cp_path) else None
    if (not force) and resume and cp and cp.get("status") == "ok" \
            and cp.get("input_sha256") == ih:
        ctx["ledger"].emit("stage_skipped", stage,
                           {"reason": "input_unchanged", "input_sha256": ih})
        return "skipped"
    if cp and cp.get("input_sha256") != ih:
        ctx["ledger"].emit("stale_detected", stage,
                           {"reason": "input_hash_changed",
                            "old_input_sha256": cp.get("input_sha256"),
                            "new_input_sha256": ih})
    result = STAGE_FUNCS[stage](ctx)
    invs = result.get("invariants", [])
    failed = [i for i in invs if i.get("status") != "ok"]
    cp_rec = {"stage": stage, "input_sha256": ih,
              "output_sha256": result.get("output_sha256"),
              "invariants_checked": invs,
              "status": "ok" if not failed else "invariant_failed"}
    write_json(cp_path, cp_rec)
    if failed:
        ctx["ledger"].emit("invariant_failed", stage,
                           {"failed": [i["name"] for i in failed]})
        raise QCFailure("stage %s invariant failure: %s"
                        % (stage, "; ".join(i["name"] for i in failed)))
    ctx["ledger"].emit("stage_completed", stage,
                       {"input_sha256": ih,
                        "output_sha256": result.get("output_sha256"),
                        "invariants_ok": len(invs)})
    return "completed"


def run_pipeline(ctx, resume=False):
    for stage in STAGES:
        run_stage(ctx, stage, resume=resume)


# ---------------------------------------------------------------------------
# 阶段 1: intake —— 嗅探分类,任何材料不得被静默丢弃
# ---------------------------------------------------------------------------

def stage_intake(ctx):
    entries = []
    for rel in material_relpaths(ctx):
        ap = material_abspath(ctx, rel)
        entry = {"path": rel, "dropped": False}
        if not os.path.exists(ap):
            entry.update({"class": "missing_file", "sha256": None, "bytes": 0,
                          "note": "case.json 中声明但文件不存在"})
        else:
            entry["sha256"] = sha256_file(ap)
            entry["bytes"] = os.path.getsize(ap)
            try:
                obj = load_json(ap)
                entry["class"] = sniff_class(obj)
            except Exception as e:
                entry["class"] = "unparseable"
                entry["note"] = "JSON 解析失败: %s" % type(e).__name__
        entries.append(entry)
    index = {"case_id": ctx["case"].get("case_id"),
             "task_sha256": sha256_file(ctx["task_path"]) if os.path.exists(ctx["task_path"]) else None,
             "materials": entries}
    write_json(wpath(ctx, "materials_index.json"), index)
    discovered = len(material_relpaths(ctx))
    classified = len(entries)
    dropped = sum(1 for e in entries if e.get("dropped"))
    invs = [{"name": "every_discovered_material_classified",
             "status": "ok" if (classified == discovered and dropped == 0) else "failed",
             "detail": {"discovered": discovered, "classified": classified,
                        "dropped": dropped}}]
    return {"invariants": invs,
            "output_sha256": sha256_file(wpath(ctx, "materials_index.json"))}


# ---------------------------------------------------------------------------
# 阶段 2: normalize —— 规范化为通用记录,计数守恒
# ---------------------------------------------------------------------------

def stage_normalize(ctx):
    index = load_json(wpath(ctx, "materials_index.json"))
    records = []
    per_source = {}
    notes = []
    for entry in index["materials"]:
        cls = entry["class"]
        if cls in PARSERS:
            obj = load_json(material_abspath(ctx, entry["path"]))
            recs = PARSERS[cls](obj)
            per_source[cls] = per_source.get(cls, 0) + len(recs)
            records.extend(recs)
        elif cls == "reference_graph":
            notes.append({"path": entry["path"], "class": cls,
                          "note": "非书志材料:不进入记录规范化,供引用图统计使用"})
            per_source.setdefault(cls, 0)
        else:
            notes.append({"path": entry["path"], "class": cls,
                          "note": "无法规范化(类别 %s),计数为 0,但未丢弃" % cls})
            per_source.setdefault(cls, 0)
    total = len(records)
    out = {"records": records, "per_source_counts": per_source,
           "total": total, "notes": notes,
           "field_status_semantics": {
               "ok": "值存在", "missing": "源记录中键缺失",
               "unknown": "键存在但值为空", "not_provided": "源模式无此字段概念"}}
    write_json(wpath(ctx, "normalized_records.json"), out)
    s = sum(v for k, v in per_source.items())
    invs = [{"name": "record_counts_conserved",
             "status": "ok" if (s == total) else "failed",
             "detail": {"sum_per_source": s, "total": total}}]
    return {"invariants": invs,
            "output_sha256": sha256_file(wpath(ctx, "normalized_records.json"))}


# ---------------------------------------------------------------------------
# 阶段 3: identity —— 去重判定、仲裁队列、按字段优先级合并(含字段级溯源)
# ---------------------------------------------------------------------------

def _key_doi(r):
    f = r["fields"]["doi"]
    return norm_doi(f["value"]) if f["status"] == "ok" else None


def _key_pmid(r):
    f = r["fields"]["pmid"]
    return str(f["value"]).strip() if f["status"] == "ok" and f["value"] else None


def _key_tya(r):
    t, y, s = r["fields"]["title"], r["fields"]["year"], r["fields"]["first_author_surname"]
    if t["status"] == "ok" and y["status"] == "ok" and s["status"] == "ok":
        nt = norm_text(t["value"])
        ny = norm_year(y["value"])
        ns = norm_surname(s["value"])
        if nt and ny and ns:
            return "%s|%s|%s" % (nt, ny, ns)
    return None


class UnionFind(object):
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if rb < ra:
            ra, rb = rb, ra
        self.parent[rb] = ra
        return True


def stage_identity(ctx):
    norm = load_json(wpath(ctx, "normalized_records.json"))
    records = norm["records"]
    by_id = {r["record_id"]: r for r in records}
    uf = UnionFind()
    log = []

    def pair_key(a, b):
        return tuple(sorted([a, b]))

    # --- 精确规则 ---
    exact_rules = [("doi_exact", _key_doi), ("pmid_exact", _key_pmid),
                   ("title_year_first_author", _key_tya)]
    for rule, keyfn in exact_rules:
        groups = {}
        for r in records:
            k = keyfn(r)
            if k:
                groups.setdefault(k, []).append(r["record_id"])
        for k in sorted(groups):
            ids = sorted(groups[k])
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    a, b = pair_key(ids[i], ids[j])
                    already = uf.find(a) == uf.find(b)
                    uf.union(a, b)
                    log.append({"record_a": a, "record_b": b,
                                "decision": "auto_merge",
                                "reason_code": rule,
                                "detail": {"key": k, "already_linked": already}})
    # --- 模糊候选(同年 + 标题 Jaccard>=阈值):只入队,绝不自动合并 ---
    queue = []
    ids = sorted(by_id)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            if uf.find(a) == uf.find(b):
                continue
            ra, rb = by_id[a], by_id[b]
            ya, yb = ra["fields"]["year"], rb["fields"]["year"]
            if not (ya["status"] == "ok" and yb["status"] == "ok"
                    and norm_year(ya["value"]) == norm_year(yb["value"])):
                continue  # 年份守卫:限制候选爆炸,亦符合书目学常识
            jac = jaccard(title_tokens(ra["fields"]["title"]["value"]),
                          title_tokens(rb["fields"]["title"]["value"]))
            if jac >= FUZZY_JACCARD_THRESHOLD:
                pid = "pair:%s--%s" % (a, b)
                queue.append({"pair_id": pid, "record_ids": [a, b],
                              "jaccard": "%.4f" % jac,
                              "reason_code": "fuzzy_title_jaccard",
                              "titles": [ra["fields"]["title"]["value"],
                                         rb["fields"]["title"]["value"]],
                              "status": "pending"})
                log.append({"record_a": a, "record_b": b,
                            "decision": "queued_for_arbitration",
                            "reason_code": "fuzzy_title_jaccard",
                            "detail": {"pair_id": pid, "jaccard": "%.4f" % jac,
                                       "threshold": FUZZY_JACCARD_THRESHOLD}})
    # --- 应用模型仲裁决定(若存在) ---
    decisions = []
    dp = decisions_path(ctx)
    if os.path.exists(dp):
        try:
            decisions = (load_json(dp) or {}).get("decisions") or []
        except Exception:
            decisions = []
    decided = {str(d.get("pair_id")): d for d in decisions if isinstance(d, dict)}
    pending = []
    for qp in queue:
        d = decided.get(qp["pair_id"])
        if d and d.get("verdict") in ("merge", "distinct"):
            a, b = qp["record_ids"]
            if d["verdict"] == "merge":
                uf.union(a, b)
                qp["status"] = "resolved_merge"
            else:
                qp["status"] = "resolved_distinct"
            log.append({"record_a": a, "record_b": b,
                        "decision": "arbitrated_" + d["verdict"],
                        "reason_code": "arbitration_decision",
                        "detail": {"pair_id": qp["pair_id"],
                                   "rationale": d.get("rationale")}})
        else:
            pending.append(qp["pair_id"])
    # --- 分组合并 ---
    groups = {}
    for rid in ids:
        groups.setdefault(uf.find(rid), []).append(rid)
    ordered = sorted(groups.values(), key=lambda g: sorted(g)[0])
    priority = list(ctx["case"].get("source_dbs") or []) or list(DEFAULT_SOURCE_PRIORITY)
    for db in sorted({r["source_db"] for r in records}):
        if db not in priority:
            priority.append(db)

    def rank(r):
        try:
            return priority.index(r["source_db"])
        except ValueError:
            return len(priority)

    merged = []
    for gi, g in enumerate(ordered):
        members = sorted((by_id[rid] for rid in g),
                         key=lambda r: (rank(r), r["record_id"]))
        fields = {}
        for f in CANONICAL_FIELDS:
            chosen = None
            for r in members:
                if r["fields"][f]["status"] == "ok":
                    chosen = r
                    break
            if chosen is not None:
                fields[f] = {"value": chosen["fields"][f]["value"], "status": "ok",
                             "provenance": {"from_record": chosen["record_id"],
                                            "from_db": chosen["source_db"],
                                            "rule": "source_priority",
                                            "priority_rank": rank(chosen)}}
            else:
                sts = [r["fields"][f]["status"] for r in members]
                st = "unknown" if "unknown" in sts else (
                    "missing" if "missing" in sts else "not_provided")
                fields[f] = {"value": None, "status": st, "provenance": None}
        merged.append({"merged_id": "M%03d" % (gi + 1),
                       "member_record_ids": sorted(g),
                       "sources": sorted({by_id[rid]["source_db"] for rid in g}),
                       "fields": fields})
    # --- 落盘 ---
    log_sorted = sorted(log, key=lambda e: (e["record_a"], e["record_b"],
                                            e["reason_code"], e["decision"]))
    write_json(wpath(ctx, "decision_log.json"),
               {"entries": log_sorted, "entry_count": len(log_sorted)})
    write_json(wpath(ctx, "arbitration_queue.json"),
               {"threshold": FUZZY_JACCARD_THRESHOLD, "pairs": queue,
                "pending_pair_ids": sorted(pending),
                "note": "模糊重复对绝不自动合并;须由模型在单次批量请求中仲裁," 
                        "决定写入 work/%s 后 --resume 重跑" % DECISIONS_FILENAME})
    write_json(wpath(ctx, "merged_records.json"),
               {"merged_records": merged, "merged_count": len(merged),
                "source_record_count": len(records),
                "field_priority_order": priority})
    # --- 不变量 ---
    n_members = sum(len(m["member_record_ids"]) for m in merged)
    queue_ids = {q["pair_id"] for q in queue}
    logged_ids = {e.get("detail", {}).get("pair_id") for e in log_sorted
                  if isinstance(e.get("detail"), dict)}
    invs = [
        {"name": "every_pair_decision_logged_with_reason_code",
         "status": "ok" if all(e.get("reason_code") for e in log_sorted) else "failed",
         "detail": {"entries": len(log_sorted)}},
        {"name": "merge_partition_conserves_records",
         "status": "ok" if n_members == len(records) else "failed",
         "detail": {"merged_members": n_members, "source_records": len(records),
                    "merged_count": len(merged)}},
        {"name": "queued_pairs_all_logged",
         "status": "ok" if queue_ids <= logged_ids else "failed",
         "detail": {"queued": sorted(queue_ids)}},
    ]
    out_hash = sha256_json({"log": log_sorted, "queue": queue, "merged": merged})
    return {"invariants": invs, "output_sha256": out_hash}


# ---------------------------------------------------------------------------
# 阶段 4: coverage —— 数据库×字段覆盖矩阵
# ---------------------------------------------------------------------------

def _compute_coverage(merged_records):
    dbs = sorted({s for m in merged_records for s in m["sources"]})
    matrix = {db: {f: 0 for f in CANONICAL_FIELDS} for db in dbs}
    matrix["MERGED_UNION"] = {f: 0 for f in CANONICAL_FIELDS}
    for m in merged_records:
        for db in m["sources"]:
            for f in CANONICAL_FIELDS:
                if m["fields"][f]["status"] == "ok":
                    matrix[db][f] += 1
        for f in CANONICAL_FIELDS:
            if m["fields"][f]["status"] == "ok":
                matrix["MERGED_UNION"][f] += 1
    return dbs + ["MERGED_UNION"], matrix


def stage_coverage(ctx):
    merged_obj = load_json(wpath(ctx, "merged_records.json"))
    merged = merged_obj["merged_records"]
    rows, matrix = _compute_coverage(merged)
    out = {"fields": list(CANONICAL_FIELDS), "rows": rows, "matrix": matrix,
           "merged_total": len(merged),
           "semantics": "matrix[db][field] = 含该库贡献且合并后该字段可用的合并记录数;" 
                        "MERGED_UNION 行为合并并集覆盖"}
    write_json(wpath(ctx, "coverage_matrix.json"), out)
    # 独立第二遍重算(不同代码路径)校验
    rows2, matrix2 = _compute_coverage(list(reversed(merged)))
    union_ok = all(matrix["MERGED_UNION"][f] ==
                   sum(1 for m in merged if m["fields"][f]["status"] == "ok")
                   for f in CANONICAL_FIELDS)
    invs = [{"name": "coverage_matrix_recomputes_from_merged_records",
             "status": "ok" if (matrix == matrix2 and rows == rows2 and union_ok) else "failed",
             "detail": {"rows": rows, "merged_total": len(merged)}}]
    return {"invariants": invs,
            "output_sha256": sha256_file(wpath(ctx, "coverage_matrix.json"))}


# ---------------------------------------------------------------------------
# 阶段 5: report —— 输出契约填充、result.json、自查门、qc_report.md
# ---------------------------------------------------------------------------

def parse_contract(case):
    oc = case.get("output_contract")
    specs = []
    if isinstance(oc, dict) and isinstance(oc.get("fields"), list):
        for f in oc["fields"]:
            if isinstance(f, dict) and f.get("name"):
                specs.append({"name": str(f["name"]),
                              "type": str(f.get("type") or f.get("shape") or "string"),
                              "description": str(f.get("description") or "")})
    elif isinstance(oc, dict):
        for k in sorted(oc):
            specs.append({"name": str(k), "type": "string",
                          "description": str(oc[k])})
    elif isinstance(oc, list):
        for f in oc:
            if isinstance(f, str):
                specs.append({"name": f, "type": "string", "description": ""})
            elif isinstance(f, dict) and f.get("name"):
                specs.append({"name": str(f["name"]),
                              "type": str(f.get("type") or "string"),
                              "description": str(f.get("description") or "")})
    for s in specs:
        t = s["type"].lower()
        if t in ("object", "dict", "map"):
            s["type"] = "object"
        elif t in ("array", "list"):
            s["type"] = "array"
        else:
            s["type"] = "string"
    return specs


def _lean_merged(m):
    f = m["fields"]
    return {"merged_id": m["merged_id"],
            "doi": f["doi"]["value"], "pmid": f["pmid"]["value"],
            "title": f["title"]["value"], "year": f["year"]["value"],
            "first_author_surname": f["first_author_surname"]["value"],
            "journal": f["journal"]["value"],
            "sources": m["sources"], "member_record_ids": m["member_record_ids"]}


def _graph_stats(ctx):
    index_path = wpath(ctx, "materials_index.json")
    if not os.path.exists(index_path):
        return None
    for e in load_json(index_path)["materials"]:
        if e["class"] == "reference_graph":
            obj = load_json(material_abspath(ctx, e["path"]))
            return {"node_count": len(obj.get("nodes") or []),
                    "edge_count": len(obj.get("edges") or []),
                    "source_material": e["path"]}
    return None


def _summary_string(ctx, merged_obj, norm_obj, queue_obj, log_obj):
    rq = str(ctx["case"].get("research_question") or "").strip()
    dbs = ",".join(ctx["case"].get("source_dbs") or [])
    n_auto = sum(1 for e in log_obj["entries"] if e["decision"] == "auto_merge")
    n_q = len(queue_obj["pairs"])
    n_pend = len(queue_obj["pending_pair_ids"])
    return ("针对研究问题「%s」:本案例跨 %d 个数据库(%s)获取 %d 条原始记录,"
            "经规范化与去重合并为 %d 条文献记录;精确规则自动合并 %d 对,"
            "模糊候选 %d 对(待仲裁 %d 对)。数据库×字段覆盖见 field_coverage_matrix。"
            % (rq, len(ctx["case"].get("source_dbs") or []), dbs,
               norm_obj["total"], merged_obj["merged_count"], n_auto, n_q, n_pend))


def fill_contract_field(ctx, spec, data):
    name, typ = spec["name"], spec["type"]
    ln = name.lower()
    if typ == "array" and ("record" in ln or "merged" in ln or "result" in ln):
        return [_lean_merged(m) for m in data["merged"]["merged_records"]], True
    if typ == "object" and ("coverage" in ln or "matrix" in ln):
        return data["coverage"], True
    if typ == "array" and ("decision" in ln or "duplicate" in ln or "dedup" in ln):
        return data["log"]["entries"], True
    if typ == "string" and ("summary" in ln or "answer" in ln or "abstract" in ln):
        return data["summary"], True
    if typ == "object" and "graph" in ln:
        gs = _graph_stats(ctx)
        return (gs, True) if gs is not None else (None, False)
    return None, False


def stage_report(ctx):
    case = ctx["case"]
    merged_obj = load_json(wpath(ctx, "merged_records.json"))
    norm_obj = load_json(wpath(ctx, "normalized_records.json"))
    queue_obj = load_json(wpath(ctx, "arbitration_queue.json"))
    log_obj = load_json(wpath(ctx, "decision_log.json"))
    coverage_obj = load_json(wpath(ctx, "coverage_matrix.json"))
    data = {"merged": merged_obj, "coverage": coverage_obj, "log": log_obj,
            "summary": _summary_string(ctx, merged_obj, norm_obj, queue_obj, log_obj)}
    # --- 契约填充:可填则填,不可填 -> null + unresolved_contract_fields ---
    fields_out, unresolved = {}, []
    for spec in parse_contract(case):
        value, filled = fill_contract_field(ctx, spec, data)
        if filled:
            fields_out[spec["name"]] = value
        else:
            fields_out[spec["name"]] = None
            unresolved.append({"field": spec["name"], "type": spec["type"],
                               "reason": "无确定性映射可填充该字段;绝不捏造(null)"})
    # --- sources ---
    sources = [{"path": os.path.basename(ctx["case_path"]),
                "sha256": sha256_file(ctx["case_path"])}]
    if os.path.exists(ctx["task_path"]):
        sources.append({"path": os.path.basename(ctx["task_path"]),
                        "sha256": sha256_file(ctx["task_path"])})
    index = load_json(wpath(ctx, "materials_index.json"))
    for e in index["materials"]:
        sources.append({"path": e["path"], "sha256": e.get("sha256"),
                        "class": e.get("class")})
    # --- 复制产物到输出目录(相对路径,便于重放一致性) ---
    out_artifacts = []
    for name in ("merged_records.json", "coverage_matrix.json",
                 "decision_log.json", "arbitration_queue.json"):
        shutil.copyfile(wpath(ctx, name), os.path.join(ctx["out"], name))
        out_artifacts.append({"path": name,
                              "sha256": sha256_file(os.path.join(ctx["out"], name))})
    # --- 状态判定 ---
    pending = queue_obj["pending_pair_ids"]
    uncertainty = []
    if pending:
        uncertainty.append("仲裁队列存在 %d 对未决模糊重复: %s;须模型单次批量仲裁后 --resume"
                           % (len(pending), ";".join(pending)))
    if unresolved:
        uncertainty.append("输出契约字段无法确定性填充: %s"
                           % ";".join(u["field"] for u in unresolved))
    status = "partial" if uncertainty else "success"
    change_records = [{"seq": e["seq"], "event": e["event"], "stage": e["stage"]}
                      for e in ctx["ledger"].events()]
    result = {"case_id": case.get("case_id"),
              "status": status,
              "sources": sources,
              "uncertainty": uncertainty or None,
              "change_records": change_records,
              "artifacts": out_artifacts,
              "unresolved_contract_fields": unresolved,
              "tool": {"name": TOOL_NAME, "version": VERSION}}
    result.update(fields_out)
    # --- 自查门 ---
    checks = run_gate_checks(ctx, result, pending, unresolved)
    failed = [c for c in checks if c["status"] == "FAIL"]
    if failed and result["status"] == "success":
        result["status"] = "partial"
        u = list(result.get("uncertainty") or [])
        u.append("自查门未通过: %s" % ";".join(c["id"] for c in failed))
        result["uncertainty"] = u
    elif failed:
        u = list(result.get("uncertainty") or [])
        u.append("自查门未通过: %s" % ";".join(c["id"] for c in failed))
        result["uncertainty"] = u
    write_qc_report(ctx, result, checks)
    # qc_report.md 写入后再补其哈希(报告自身不参与 artifact_hashes 自查,避免自引用)
    qcp = os.path.join(ctx["out"], "qc_report.md")
    result["artifacts"] = out_artifacts + [{"path": "qc_report.md",
                                            "sha256": sha256_file(qcp)}]
    write_json(os.path.join(ctx["out"], "result.json"), result)
    ctx["ledger"].emit("gate_completed", "report",
                       {"checks_pass": sum(1 for c in checks if c["status"] == "PASS"),
                        "checks_fail": len(failed),
                        "final_status": result["status"]})
    invs = [{"name": "all_contract_fields_present",
             "status": "ok" if all(s["name"] in result for s in parse_contract(case)) else "failed",
             "detail": {"contract_fields": [s["name"] for s in parse_contract(case)],
                        "unresolved": [u["field"] for u in unresolved]}}]
    out_hash = sha256_json({"result_status": result["status"],
                            "artifacts": result["artifacts"]})
    return {"invariants": invs, "output_sha256": out_hash}


# ---------------------------------------------------------------------------
# 交付前自查门(对应 references/qc-checklist.md)
# ---------------------------------------------------------------------------

def run_gate_checks(ctx, result, pending, unresolved):
    checks = []
    specs = parse_contract(ctx["case"])
    # 1. 契约完备性
    missing = [s["name"] for s in specs if s["name"] not in result]
    null_unlisted = [s["name"] for s in specs
                     if result.get(s["name"]) is None
                     and s["name"] not in [u["field"] for u in unresolved]]
    ok = not missing and not null_unlisted
    checks.append({"id": "contract_completeness",
                   "status": "PASS" if ok else "FAIL",
                   "evidence": "result.json",
                   "note": "缺失=%s;未声明的 null=%s" % (missing or "无", null_unlisted or "无")})
    # 2. 产物哈希一致(不含 qc_report.md 自身)
    bad = []
    for a in result["artifacts"]:
        p = os.path.join(ctx["out"], a["path"])
        if not os.path.exists(p) or sha256_file(p) != a["sha256"]:
            bad.append(a["path"])
    checks.append({"id": "artifact_hashes",
                   "status": "PASS" if not bad else "FAIL",
                   "evidence": "result.json#artifacts",
                   "note": ("全部 %d 个产物哈希一致(qc_report.md 为报告本身,"
                            "其哈希于门后写入,不参与本检查)"
                            % len(result["artifacts"])) if not bad
                           else "哈希不符: %s" % ";".join(bad)})
    # 3. 计数守恒
    norm_obj = load_json(wpath(ctx, "normalized_records.json"))
    merged_obj = load_json(wpath(ctx, "merged_records.json"))
    s = sum(norm_obj["per_source_counts"].values())
    n_members = sum(len(m["member_record_ids"]) for m in merged_obj["merged_records"])
    ok = (s == norm_obj["total"] == len(norm_obj["records"])
          and n_members == norm_obj["total"])
    checks.append({"id": "count_conservation",
                   "status": "PASS" if ok else "FAIL",
                   "evidence": "work/normalized_records.json;work/merged_records.json",
                   "note": "per_source 合计=%d,规范化总数=%d,合并成员合计=%d"
                           % (s, norm_obj["total"], n_members)})
    # 4. 决策日志完备
    log_obj = load_json(wpath(ctx, "decision_log.json"))
    queue_obj = load_json(wpath(ctx, "arbitration_queue.json"))
    logged = {e.get("detail", {}).get("pair_id") for e in log_obj["entries"]
              if isinstance(e.get("detail"), dict)}
    qids = {q["pair_id"] for q in queue_obj["pairs"]}
    ok = all(e.get("reason_code") and e.get("decision") for e in log_obj["entries"]) \
        and qids <= logged
    checks.append({"id": "decision_log_completeness",
                   "status": "PASS" if ok else "FAIL",
                   "evidence": "work/decision_log.json",
                   "note": "日志条目=%d;队列对=%d;均含 reason_code=%s"
                           % (len(log_obj["entries"]), len(qids),
                              "是" if ok else "否")})
    # 5. 仲裁队列:为空,或显式待决且状态为 partial
    if not pending:
        checks.append({"id": "arbitration_queue_resolved_or_explicit",
                       "status": "PASS", "evidence": "work/arbitration_queue.json",
                       "note": "仲裁队列为空(全部已决或无候选)"})
    else:
        ok = result["status"] == "partial" and result.get("uncertainty")
        checks.append({"id": "arbitration_queue_resolved_or_explicit",
                       "status": "PASS" if ok else "FAIL",
                       "evidence": "work/arbitration_queue.json;result.json#uncertainty",
                       "note": "待决 %d 对且状态为 partial 并在 uncertainty 中显式声明=%s"
                               % (len(pending), "是" if ok else "否")})
    # 6. 重放一致性
    rvp = wpath(ctx, "replay_verdict.json")
    if os.path.exists(rvp):
        rv = load_json(rvp)
        ok = rv.get("verdict") == "STABLE" and \
            rv.get("case_sha256") == sha256_file(ctx["case_path"])
        note = "verdict=%s,differing=%s" % (rv.get("verdict"),
                                            rv.get("differing_files") or "无")
    else:
        ok, note = False, "尚未执行 --replay(work/replay_verdict.json 不存在)"
    checks.append({"id": "replay_stable",
                   "status": "PASS" if ok else "FAIL",
                   "evidence": "work/replay_verdict.json", "note": note})
    # 7. 诚实 partial:状态与不确定性声明一致
    if result["status"] == "success":
        ok = not pending and not unresolved
        note = "success 且无待决/未解字段" if ok else "success 但仍存在待决或未解字段"
    elif result["status"] == "partial":
        ok = bool(result.get("uncertainty"))
        note = "partial 且 uncertainty 非空=%s" % ("是" if ok else "否")
    else:
        ok, note = result["status"] == "input_error", "状态=%s" % result["status"]
    checks.append({"id": "honest_partial",
                   "status": "PASS" if ok else "FAIL",
                   "evidence": "result.json", "note": note})
    return checks


def write_qc_report(ctx, result, checks):
    L = []
    L.append("# 过程质量控制报告(process-qc-guard)")
    L.append("")
    L.append("- case_id: `%s`" % result.get("case_id"))
    L.append("- 工具: `%s` v%s" % (TOOL_NAME, VERSION))
    L.append("- 最终状态: **%s**" % result.get("status"))
    L.append("")
    L.append("## 交付前自查门(pre-delivery self-check gate)")
    L.append("")
    L.append("| 检查项 | 结果 | 证据 | 说明 |")
    L.append("|---|---|---|---|")
    for c in checks:
        L.append("| `%s` | **%s** | `%s` | %s |"
                 % (c["id"], c["status"], c["evidence"],
                    str(c.get("note") or "").replace("|", "\\|")))
    L.append("")
    L.append("## 重放一致性(replay consistency)")
    L.append("")
    rvp = wpath(ctx, "replay_verdict.json")
    if os.path.exists(rvp):
        rv = load_json(rvp)
        L.append("- 判定: **%s**" % rv.get("verdict"))
        L.append("- 比对产物文件数: %s" % rv.get("compared_file_count"))
        diff = rv.get("differing_files") or []
        L.append("- 差异文件: %s" % ("无" if not diff else "; ".join(diff)))
    else:
        L.append("- 判定: **NOT_RUN**(尚未执行 `--replay`)")
    L.append("")
    L.append("## 阶段账本摘要(逻辑序号,无墙钟)")
    L.append("")
    L.append("| seq | 事件 | 阶段 |")
    L.append("|---|---|---|")
    for e in ctx["ledger"].events():
        L.append("| %d | `%s` | `%s` |" % (e["seq"], e["event"],
                                            e["stage"] or "-"))
    L.append("")
    L.append("## 预算包线(budget envelope)")
    L.append("")
    L.append("- 模型请求上限 64 / 时限 900s;本流水线全部阶段为脚本化执行(0 模型请求)。")
    L.append("- 唯一模型判断点: identity 阶段模糊重复对仲裁,单次批量请求(队列空则 0 次)。")
    L.append("- 详见 `references/budget-and-checkpoints.md`。")
    L.append("")
    L.append("## 备注")
    L.append("")
    L.append("- `qc_report.md` 自身的 sha256 写入 `result.json.artifacts`,"
             "但不参与 `artifact_hashes` 自查(避免自引用)。")
    L.append("- 全部产物不含墙钟时间与绝对路径;账本仅使用逻辑序号。")
    L.append("- 状态语义: `success`=全部通过;`partial`=诚实降级(原因见 "
             "`result.json.uncertainty`);`input_error`=输入非法。")
    L.append("")
    with open(os.path.join(ctx["out"], "qc_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))


STAGE_FUNCS = {"intake": stage_intake, "normalize": stage_normalize,
               "identity": stage_identity, "coverage": stage_coverage,
               "report": stage_report}


# ---------------------------------------------------------------------------
# 运行计划(预算感知)
# ---------------------------------------------------------------------------

def build_run_plan(ctx):
    return {
        "plan_version": VERSION,
        "case_id": ctx["case"].get("case_id"),
        "stages": [
            {"name": "intake", "executor": "script", "model_requests": 0,
             "invariant": "every_discovered_material_classified"},
            {"name": "normalize", "executor": "script", "model_requests": 0,
             "invariant": "record_counts_conserved"},
            {"name": "identity", "executor": "script+model", "model_requests": "0 或 1",
             "invariant": "every_pair_decision_logged_with_reason_code",
             "model_judgment_point": "模糊重复对仲裁:单次批量请求,"
                                     "决定写入 work/%s" % DECISIONS_FILENAME},
            {"name": "coverage", "executor": "script", "model_requests": 0,
             "invariant": "coverage_matrix_recomputes_from_merged_records"},
            {"name": "report", "executor": "script", "model_requests": 0,
             "invariant": "all_contract_fields_present"},
        ],
        "budget_envelope": {
            "max_model_requests": 64, "max_seconds": 900,
            "planned_model_requests_min": 0, "planned_model_requests_max": 1,
            "model_request_purpose": "identity 阶段模糊重复对的单次批量仲裁",
            "scripted_batching": "5 个脚本化阶段合并为 1 条 bash 命令执行",
            "reserve_model_requests": 63,
            "reserve_note": "剩余预算保留给 Harness 编排、契约核验与异常重试",
            "budget_math_reference": "references/budget-and-checkpoints.md"},
        "model_judgment_points": [
            {"stage": "identity", "kind": "fuzzy_duplicate_arbitration",
             "mode": "single batched request over work/arbitration_queue.json"}],
        "replayability": "python3 scripts/qc_guard.py ... --replay 双跑字节级比对",
    }


def execute(ctx, resume=False):
    write_json(wpath(ctx, "run_plan.json"), build_run_plan(ctx))
    ctx["ledger"].emit("run_plan_written", None,
                       {"stages": STAGES, "resume": bool(resume)})
    run_pipeline(ctx, resume=resume)


# ---------------------------------------------------------------------------
# --replay:双跑字节级比对
# ---------------------------------------------------------------------------

def _collect_artifacts(rw, ro):
    m = {}
    for root, _dirs, files in os.walk(ro):
        for fn in sorted(files):
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, ro)
            m["out/" + rel.replace(os.sep, "/")] = sha256_file(p)
    work_files = ["run_plan.json", "run_ledger.jsonl", "materials_index.json",
                  "normalized_records.json", "decision_log.json",
                  "arbitration_queue.json", "merged_records.json",
                  "coverage_matrix.json", DECISIONS_FILENAME]
    for fn in work_files:
        p = os.path.join(rw, fn)
        if os.path.exists(p):
            m["work/" + fn] = sha256_file(p)
    cp_dir = os.path.join(rw, "checkpoints")
    if os.path.isdir(cp_dir):
        for fn in sorted(os.listdir(cp_dir)):
            m["work/checkpoints/" + fn] = sha256_file(os.path.join(cp_dir, fn))
    return m


def cmd_replay(ctx):
    base = wpath(ctx, "replay")
    if os.path.isdir(base):
        shutil.rmtree(base)
    maps = {}
    for tag in ("a", "b"):
        rw = os.path.join(base, tag, "work")
        ro = os.path.join(base, tag, "out")
        os.makedirs(rw, exist_ok=True)
        os.makedirs(ro, exist_ok=True)
        dp = decisions_path(ctx)
        if os.path.exists(dp):
            shutil.copyfile(dp, os.path.join(rw, DECISIONS_FILENAME))
        subctx = dict(ctx)
        subctx["work"] = rw
        subctx["out"] = ro
        subctx["ledger"] = Ledger(os.path.join(rw, "run_ledger.jsonl"))
        execute(subctx, resume=False)
        maps[tag] = _collect_artifacts(rw, ro)
    keys = sorted(set(maps["a"]) | set(maps["b"]))
    differing = [k for k in keys if maps["a"].get(k) != maps["b"].get(k)]
    verdict = "STABLE" if not differing else "DRIFT"
    write_json(wpath(ctx, "replay_verdict.json"),
               {"verdict": verdict, "differing_files": differing,
                "compared_file_count": len(keys),
                "case_sha256": sha256_file(ctx["case_path"]),
                "note": "两个全新 work/out 目录下完整流水线(含已播种的仲裁决定)"
                        "所有实质产物逐字节比对"})
    ctx["ledger"].emit("replay_completed", None,
                       {"verdict": verdict, "differing_files": differing,
                        "compared_file_count": len(keys)})
    # 重放裁决是 report 阶段的输入之一:强制重跑 report 以刷新 result.json 与 qc_report.md
    run_stage(ctx, "report", force=True)
    return verdict


# ---------------------------------------------------------------------------
# 入口:早期诚实 partial、错误映射、退出码
# ---------------------------------------------------------------------------

def write_skeleton_result(out_dir, case_id=None):
    os.makedirs(out_dir, exist_ok=True)
    write_json(os.path.join(out_dir, "result.json"), {
        "case_id": case_id,
        "status": "partial",
        "sources": [],
        "uncertainty": ["运行刚开始:输入尚未读取(早期诚实 partial 骨架);"
                        "若进程中断,此文件即为诚实的中间态"],
        "change_records": [],
        "artifacts": [],
        "unresolved_contract_fields": [],
        "tool": {"name": TOOL_NAME, "version": VERSION}})


def write_error_result(out_dir, case_id, status, message):
    write_json(os.path.join(out_dir, "result.json"), {
        "case_id": case_id,
        "status": status,
        "sources": [],
        "uncertainty": [message],
        "change_records": [],
        "artifacts": [],
        "unresolved_contract_fields": [],
        "tool": {"name": TOOL_NAME, "version": VERSION}})


def _sanitize(msg, ctx):
    for key in ("work", "out", "case_path", "task_path", "case_dir"):
        v = ctx.get(key) if ctx else None
        if v:
            msg = msg.replace(str(v), "<%s>" % key)
    return msg


def build_arg_parser():
    p = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="多数据库联合检索的过程质量控制流水线:检查点化、可恢复、"
                    "预算安全、重放一致、交付前自查门。")
    p.add_argument("--case", default="/input/case.json", help="案例 JSON 路径")
    p.add_argument("--task", default="/input/task.md", help="任务说明路径")
    p.add_argument("--work", default="/app/work", help="工作目录(检查点/账本/中间产物)")
    p.add_argument("--out", default="/app/output", help="输出目录(result.json/qc_report.md)")
    p.add_argument("--resume", action="store_true",
                   help="跳过输入哈希未变的已完成阶段;检测到输入陈旧则自该阶段起重跑")
    p.add_argument("--replay", action="store_true",
                   help="在两个全新 work/out 目录各完整运行一次并逐字节比对,"
                        "给出 STABLE/DRIFT 裁决并刷新报告")
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    ctx = {"case_path": args.case, "task_path": args.task,
           "work": args.work, "out": args.out,
           "case_dir": os.path.dirname(os.path.abspath(args.case)) or "."}
    # 早期诚实 partial:读取任何输入之前先落骨架;
    # 若已有 result.json(断点续跑/重放场景)则保留,不得覆盖既有诚实状态
    skeleton_path = os.path.join(args.out, "result.json")
    try:
        if not os.path.exists(skeleton_path):
            write_skeleton_result(args.out)
    except Exception as e:
        sys.stderr.write("无法写出骨架 result.json: %s\n" % e)
        return 2
    try:
        os.makedirs(args.work, exist_ok=True)
        ctx["ledger"] = Ledger(wpath(ctx, "run_ledger.jsonl"))
        try:
            case = load_json(args.case)
        except Exception as e:
            write_error_result(args.out, None, "input_error",
                               "case.json 无法解析: %s: %s" % (type(e).__name__, e))
            ctx["ledger"].emit("input_error", None, {"reason": "case_unparseable"})
            return 3
        if not isinstance(case, dict) or not case.get("case_id"):
            write_error_result(args.out, None, "input_error",
                               "case.json 非法: 缺少 case_id 或顶层不是对象")
            ctx["ledger"].emit("input_error", None, {"reason": "case_invalid"})
            return 3
        ctx["case"] = case
        if not os.path.exists(skeleton_path):
            write_skeleton_result(args.out, case_id=case.get("case_id"))
        if args.replay:
            verdict = cmd_replay(ctx)
            return 0 if verdict == "STABLE" else 2
        execute(ctx, resume=args.resume)
        final = load_json(os.path.join(args.out, "result.json"))
        st = final.get("status")
        return 0 if st == "success" else (3 if st == "input_error" else 2)
    except QCFailure as e:
        msg = _sanitize("阶段失败: %s" % e, ctx)
        _honest_partial_on_error(args.out, ctx, msg)
        return 2
    except Exception as e:  # 顶层兜底:诚实 partial + 退出码 2
        msg = _sanitize("未捕获异常: %s: %s" % (type(e).__name__, e), ctx)
        _honest_partial_on_error(args.out, ctx, msg)
        return 2


def _honest_partial_on_error(out_dir, ctx, msg):
    try:
        rp = os.path.join(out_dir, "result.json")
        result = load_json(rp) if os.path.exists(rp) else {}
        if not isinstance(result, dict):
            result = {}
        result.setdefault("case_id", (ctx.get("case") or {}).get("case_id") if ctx else None)
        result["status"] = "partial"
        u = result.get("uncertainty") or []
        if isinstance(u, str):
            u = [u]
        u.append(msg)
        result["uncertainty"] = u
        result.setdefault("sources", [])
        result.setdefault("change_records",
                          [{"seq": e["seq"], "event": e["event"], "stage": e["stage"]}
                           for e in ctx["ledger"].events()] if ctx and ctx.get("ledger") else [])
        result.setdefault("artifacts", [])
        result.setdefault("unresolved_contract_fields", [])
        result.setdefault("tool", {"name": TOOL_NAME, "version": VERSION})
        write_json(rp, result)
        if ctx and ctx.get("ledger"):
            ctx["ledger"].emit("honest_partial_on_error", None, {"message": msg})
    except Exception as e2:
        sys.stderr.write("无法写出诚实 partial: %s\n" % e2)


if __name__ == "__main__":
    sys.exit(main())
