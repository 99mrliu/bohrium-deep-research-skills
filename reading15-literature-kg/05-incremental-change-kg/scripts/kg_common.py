#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kg_common.py — 共享库：材料加载、文本规范化、稳定语义 ID、图模型读写。

仅使用 Python3 标准库。所有 JSON 输出 sort_keys=True、无时间戳、无随机数，
保证同一输入重复运行字节级一致（幂等，见 references/reproducibility.md）。
"""
import hashlib
import json
import os
import re

SCHEMA_GRAPH = "kg-graph/1"
SCHEMA_CANDIDATES = "kg-candidates/1"
SCHEMA_CHANGESET = "kg-changeset/1"
SCHEMA_CHANGES = "kg-changes/1"
SCHEMA_QUERIES = "kg-queries/1"
SCHEMA_RESULT = "kg-result/1"

# 实质节点允许的类型词表（references/change-semantics.md 有完整定义）
NODE_TYPES = [
    "material", "method", "task", "metric", "researcher",
    "conclusion", "sample", "dataset", "condition", "device",
]

# 通用术语词表：标签落在此集合中的候选，禁止仅凭同名强制 MERGE，
# 除非操作显式给出 allow_generic=true 且附跨来源证据（见 verify_changeset）。
GENERIC_TERMS = {
    "sample", "commercial sample", "control", "control group", "reference",
    "reference sample", "composite", "the composite", "material",
    "the material", "standard method", "commercial carbon black",
    "carbon black", "the electrode", "electrode", "commercial",
    "baseline", "blank", "substrate", "catalyst", "solution", "powder",
}

MAX_QUOTE_LEN = 280  # 原文短引最大长度（字符）

WS = re.compile(r"\s+")
NONALNUM = re.compile(r"[^0-9a-z一-鿿]+")
REL_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def norm_ws(s):
    """空白规范化：用于引文子串匹配（JATS 线性化文本的换行/多空格差异）。"""
    return WS.sub(" ", (s or "")).strip()


def norm_label(s):
    """语义键规范化：小写、去标点、压缩空白。ID 与别名解析都以此为准。"""
    return WS.sub(" ", NONALNUM.sub(" ", (s or "").lower())).strip()


def h8(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:8]


_TYPE_ABBR = {
    "material": "mat", "method": "mtd", "task": "tsk", "metric": "mtr",
    "researcher": "res", "conclusion": "con", "sample": "sam",
    "dataset": "dat", "condition": "cnd", "device": "dev",
}


def type_abbr(t):
    t = (t or "").lower()
    if t in _TYPE_ABBR:
        return _TYPE_ABBR[t]
    a = re.sub(r"[^a-z]", "", t)[:3]
    return a or "gen"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(obj, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def dump_jsonl(records, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True))
            f.write("\n")


# ---------------------------------------------------------------- 输入加载

def read_case(input_dir):
    p = os.path.join(input_dir, "case.json")
    return load_json(p) if os.path.exists(p) else {}


def load_sources(input_dir, case):
    """从 corpus-manifest.json 加载来源列表；缺失时按文件名兜底。

    根 case.json 的 doi/title/authors 只属于第一篇（primary），
    仅补到 sources[0]，绝不套用到第二篇及以后。
    """
    sources = []
    mpath = os.path.join(input_dir, "corpus-manifest.json")
    raw = []
    if os.path.exists(mpath):
        doc = load_json(mpath)
        raw = doc.get("sources") or doc.get("materials") or []
    for i, s in enumerate(raw):
        sid = s.get("source_id") or s.get("id") or (
            "primary" if i == 0 else "secondary" if i == 1 else "source%d" % (i + 1))
        sources.append({
            "source_id": sid,
            "doi": s.get("doi"),
            "title": s.get("title"),
            "authors": s.get("authors"),
            "license": s.get("license"),
            "sha256": s.get("sha256") or s.get("hash"),
            "file": s.get("file") or ("%s-material.json" % sid),
        })
    if not sources:  # 兜底：按约定文件名探测
        for i, sid in enumerate(["primary", "secondary"]):
            f = os.path.join(input_dir, "%s-material.json" % sid)
            if os.path.exists(f):
                doc = load_json(f)
                sources.append({
                    "source_id": sid,
                    "doi": doc.get("doi"), "title": doc.get("title"),
                    "authors": doc.get("authors"), "license": doc.get("license"),
                    "sha256": doc.get("sha256"), "file": "%s-material.json" % sid,
                })
    if sources and case:
        s0 = sources[0]
        for k in ("doi", "title", "authors"):
            if not s0.get(k) and case.get(k):
                s0[k] = case.get(k)
                s0["root_metadata_applied"] = True
    return sources


def _paras_from_doc(doc):
    """宽容解析段落：支持 paragraphs/content 列表或 {id: text} 映射。"""
    paras = []
    if isinstance(doc, dict):
        items = doc.get("paragraphs") or doc.get("content") or []
        if isinstance(items, dict):
            items = [{"paragraph_id": k, "text": v} for k, v in items.items()]
        for it in items:
            if not isinstance(it, dict):
                continue
            pid = it.get("paragraph_id") or it.get("id") or it.get("pid")
            text = it.get("text") or it.get("content") or ""
            if pid and text:
                paras.append({"paragraph_id": str(pid), "text": str(text),
                              "section": str(it.get("section") or "")})
    return paras


def load_paragraphs(input_dir, sources):
    """返回 {(source_id, paragraph_id): {"text":..,"section":..}}。

    主来源是各 source 的 material 文件；material.json 作为汇总索引兜底。
    段落定位一律使用组织方 JATS paragraph_id，不涉及 PDF 页码。
    """
    paras = {}
    for s in sources:
        fpath = os.path.join(input_dir, s["file"])
        if not os.path.exists(fpath):
            continue
        doc = load_json(fpath)
        plist = _paras_from_doc(doc)
        sids = {s["source_id"]}
        if isinstance(doc, dict) and doc.get("source_id"):
            sids.add(str(doc["source_id"]))
        for sid in sids:
            for p in plist:
                paras[(sid, p["paragraph_id"])] = {"text": p["text"],
                                                   "section": p["section"]}
    mpath = os.path.join(input_dir, "material.json")
    if os.path.exists(mpath):
        doc = load_json(mpath)
        papers = doc.get("papers") if isinstance(doc, dict) else None
        if papers:
            for pap in papers:
                sid = pap.get("source_id") or pap.get("id")
                if not sid:
                    continue
                for p in _paras_from_doc(pap):
                    paras.setdefault((sid, p["paragraph_id"]),
                                     {"text": p["text"], "section": p["section"]})
        elif isinstance(doc, dict):
            for it in doc.get("paragraphs") or []:
                sid = it.get("source_id")
                pid = it.get("paragraph_id") or it.get("id")
                text = it.get("text") or ""
                if sid and pid and text:
                    paras.setdefault((sid, str(pid)),
                                     {"text": str(text),
                                      "section": str(it.get("section") or "")})
    return paras


def source_rank(sources, sid):
    for i, s in enumerate(sources):
        if s["source_id"] == sid:
            return i
    return len(sources)


# ---------------------------------------------------------------- 稳定 ID

def base_node_id(ntype, label):
    """节点基准 ID：类型缩写 + 语义键哈希。与来源顺序无关，重跑稳定。"""
    return "n_%s_%s" % (type_abbr(ntype), h8(ntype + "|" + norm_label(label)))


def base_edge_id(rel, frm, to, attrs):
    """边基准 ID：端点 ID + 关系 + 数值/条件哈希。不同数值天然不同 ID，
    从机制上防止把不同论文的数值合并成一条边。"""
    attrs = attrs or {}
    val = norm_ws(str(attrs.get("value", "")))
    cond = norm_ws(str(attrs.get("condition", "")))
    return "e_%s_%s" % (type_abbr(rel), h8("|".join([frm, to, rel, val, cond])))


def node_anchor(ntype, label, evidence):
    ev = (evidence or [{}])[0]
    return "%s|%s|%s" % (ev.get("source_id", ""), ev.get("paragraph_id", ""),
                         norm_label(label))


def edge_anchor(rel, frm, to, attrs, evidence):
    ev = (evidence or [{}])[0]
    attrs = attrs or {}
    return "|".join([frm, to, rel, norm_ws(str(attrs.get("value", ""))),
                     norm_ws(str(attrs.get("condition", ""))),
                     ev.get("source_id", ""), ev.get("paragraph_id", "")])


def unique_id(base, anchor, registry):
    """registry: {id: anchor}。同一 anchor 复用原 ID（幂等）；
    不同 anchor 撞键时按确定性顺序追加 _2、_3…，既有记录永不改号。"""
    if base in registry:
        if registry[base] == anchor:
            return base
        i = 2
        while True:
            cand = "%s_%d" % (base, i)
            if cand not in registry or registry[cand] == anchor:
                return cand
            i += 1
    return base


# ---------------------------------------------------------------- 图操作辅助

def build_resolver(graph):
    """norm_label -> [node_id]，覆盖 label 与 aliases，仅含 active 节点。"""
    res = {}
    for n in graph.get("nodes", []):
        if n.get("status") == "merged":
            continue
        keys = [n.get("label", "")]
        for a in n.get("aliases", []):
            keys.append(a.get("label", "") if isinstance(a, dict) else str(a))
        for k in keys:
            res.setdefault(norm_label(k), []).append(n["id"])
    return res


def resolve_ref(ref, graph, op_results=None):
    """端点/目标解析：支持 "label" 字符串、{"label":..}、{"id":..}、{"ref":"op:N"}。

    返回 (id, error)。歧义（同名 KEEP_DISTINCT 多节点）必须显式用 id 或 ref。
    """
    if isinstance(ref, str):
        ref = {"label": ref}
    if not isinstance(ref, dict):
        return None, "非法引用: %r" % (ref,)
    if "ref" in ref:
        key = ref["ref"]
        if op_results and key in op_results:
            return op_results[key], None
        return None, "未知操作引用 %s（该操作尚未执行或不产生节点）" % key
    if "id" in ref:
        for n in graph.get("nodes", []):
            if n["id"] == ref["id"]:
                return ref["id"], None
        for e in graph.get("edges", []):
            if e["id"] == ref["id"]:
                return ref["id"], None
        return None, "图中不存在 id=%s" % ref["id"]
    label = ref.get("label", "")
    ids = build_resolver(graph).get(norm_label(label), [])
    if len(ids) == 1:
        return ids[0], None
    if not ids:
        return None, "图中找不到标签 '%s'（含别名）" % label
    return None, ("标签 '%s' 匹配到 %d 个节点 %s（KEEP_DISTINCT 同名实体），"
                  "请改用 id 显式指定" % (label, len(ids), ids))


def find_node(graph, nid):
    for n in graph.get("nodes", []):
        if n["id"] == nid:
            return n
    return None


def find_edge(graph, eid):
    for e in graph.get("edges", []):
        if e["id"] == eid:
            return e
    return None


def dedupe_evidence(evs):
    seen, out = set(), []
    for ev in evs:
        k = (ev.get("source_id"), ev.get("paragraph_id"), norm_ws(ev.get("quote", "")))
        if k not in seen:
            seen.add(k)
            out.append(ev)
    return out


def node_summary(n):
    return {"id": n["id"], "type": n["type"], "label": n["label"],
            "aliases": [a.get("label") if isinstance(a, dict) else a
                        for a in n.get("aliases", [])],
            "status": n.get("status", "active"),
            "evidence": n.get("evidence", [])}


def edge_summary(e):
    return {"id": e["id"], "relation": e["relation"], "from": e["from"],
            "to": e["to"], "attributes": e.get("attributes", {}),
            "status": e.get("status", "active"),
            "conflict_group": e.get("conflict_group"),
            "evidence": e.get("evidence", [])}
