#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kg_loader.py — 健壮的知识图谱加载器（仅标准库）。

职责：
  * 读取候选图谱 JSON（agent 撰写的 graph.candidate.json 或已导出的 graph.json）
  * 做结构性检查（缺键、重复 id、悬空端点等），错误明确报告，不静默吞掉
  * 构建内存索引：按 id 的节点表、别名索引、出/入邻接表
  * 计算确定性 graph_hash（sha256，排序后的规范化 JSON，不含时间戳）

被 kg_validate.py / kg_engine.py / kg_export.py / run_queries.py 复用。
"""

import hashlib
import json
import os

SCHEMA_VERSION = "1.0"

NODE_REQUIRED = ("id", "type", "name", "evidence")
EDGE_REQUIRED = ("id", "src", "dst", "relation", "evidence")
EVIDENCE_REQUIRED = ("source_id", "paragraph_id", "quote")


class GraphLoadError(Exception):
    """图谱加载/结构错误。message 为人类可读中文说明。"""


def _canon(obj):
    """规范化序列化：排序键、去空白差异，保证哈希确定性。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Graph:
    """内存图谱。只读视图 + 索引。"""

    def __init__(self, raw, origin=""):
        self.origin = origin
        self.raw = raw
        self.graph_id = raw.get("graph_id", "unknown-graph")
        self.case_id = raw.get("case_id", "")
        self.sources = {s["source_id"]: s for s in raw.get("sources", []) if "source_id" in s}
        self.nodes = {}
        self.edges = {}
        self.merge_decisions = list(raw.get("merge_decisions", []))
        self.alias_index = {}   # lower(name/alias) -> node_id
        self.out_adj = {}       # node_id -> [edge_id]
        self.in_adj = {}        # node_id -> [edge_id]
        errors = []
        for n in raw.get("nodes", []):
            nid = n.get("id", "<无id节点>")
            missing = [k for k in NODE_REQUIRED if k not in n]
            if missing:
                errors.append("节点 %s 缺少字段: %s" % (nid, ",".join(missing)))
                continue
            if nid in self.nodes:
                errors.append("节点 id 重复: %s" % nid)
                continue
            self.nodes[nid] = n
            keys = [n.get("name", "")] + list(n.get("aliases", []))
            for k in keys:
                if isinstance(k, str) and k.strip():
                    self.alias_index.setdefault(k.strip().lower(), nid)
            self.out_adj[nid] = []
            self.in_adj[nid] = []
        for e in raw.get("edges", []):
            eid = e.get("id", "<无id边>")
            missing = [k for k in EDGE_REQUIRED if k not in e]
            if missing:
                errors.append("边 %s 缺少字段: %s" % (eid, ",".join(missing)))
                continue
            if eid in self.edges:
                errors.append("边 id 重复: %s" % eid)
                continue
            if e["src"] not in self.nodes:
                errors.append("边 %s 的 src 指向不存在节点: %s" % (eid, e["src"]))
                continue
            if e["dst"] not in self.nodes:
                errors.append("边 %s 的 dst 指向不存在节点: %s" % (eid, e["dst"]))
                continue
            self.edges[eid] = e
            self.out_adj[e["src"]].append(eid)
            self.in_adj[e["dst"]].append(eid)
        # 证据结构检查（内容的原文比对由 kg_validate 负责）
        for kind, items in (("节点", self.nodes.values()), ("边", self.edges.values())):
            for it in items:
                ev = it.get("evidence")
                if not isinstance(ev, list) or not ev:
                    errors.append("%s %s 缺少非空 evidence 列表" % (kind, it.get("id")))
                    continue
                for j, e in enumerate(ev):
                    miss = [k for k in EVIDENCE_REQUIRED if k not in e]
                    if miss:
                        errors.append("%s %s 的第 %d 条证据缺字段: %s"
                                      % (kind, it.get("id"), j + 1, ",".join(miss)))
                    elif not str(e.get("quote", "")).strip():
                        errors.append("%s %s 的第 %d 条证据 quote 为空" % (kind, it.get("id"), j + 1))
                    elif len(str(e.get("quote", ""))) > 200:
                        errors.append("%s %s 的第 %d 条证据 quote 超过 200 字符（应为原文短引）"
                                      % (kind, it.get("id"), j + 1))
        # 合并决策结构检查
        for d in self.merge_decisions:
            if d.get("decision") not in ("merge", "no_merge"):
                errors.append("merge_decision %s 的 decision 必须为 merge/no_merge" % d.get("id", "?"))
            if d.get("decision") == "merge" and d.get("canonical_node") not in self.nodes:
                errors.append("merge_decision %s 的 canonical_node 不存在: %s"
                              % (d.get("id", "?"), d.get("canonical_node")))
            if not str(d.get("rationale", "")).strip():
                errors.append("merge_decision %s 缺少 rationale（合并/不合并依据）" % d.get("id", "?"))
        if errors:
            raise GraphLoadError("图谱结构检查未通过（%d 处问题）：\n - %s"
                                 % (len(errors), "\n - ".join(errors)))

    # ---- 查询辅助 ----
    def find_node(self, name):
        """按 name 或别名（大小写不敏感、去首尾空白）查找节点 id；找不到返回 None。"""
        if not isinstance(name, str):
            return None
        return self.alias_index.get(name.strip().lower())

    def neighbors(self, node_id, relations=None, direction="any", types=None):
        """返回 (edge_id, 对端node_id) 列表，按 edge_id 排序保证确定性。

        relations: None 或关系名列表（大小写不敏感精确匹配，列表内为 OR）。
        direction: "out" | "in" | "any"。
        types: None 或对端节点类型白名单。
        """
        rels = None
        if relations:
            rels = {r.strip().lower() for r in relations}
        tset = set(types) if types else None
        pairs = []
        if direction in ("out", "any"):
            for eid in self.out_adj.get(node_id, []):
                e = self.edges[eid]
                if rels and e["relation"].strip().lower() not in rels:
                    continue
                other = e["dst"]
                if tset and self.nodes[other]["type"] not in tset:
                    continue
                pairs.append((eid, other))
        if direction in ("in", "any"):
            for eid in self.in_adj.get(node_id, []):
                e = self.edges[eid]
                if rels and e["relation"].strip().lower() not in rels:
                    continue
                other = e["src"]
                if tset and self.nodes[other]["type"] not in tset:
                    continue
                pairs.append((eid, other))
        pairs.sort(key=lambda p: (p[0], p[1]))
        return pairs

    def evidence_sources(self, node_id):
        """节点自身证据 + 关联边证据中出现的所有不同 source_id（排序）。"""
        srcs = set()
        for e in self.nodes[node_id].get("evidence", []):
            srcs.add(e.get("source_id"))
        for eid in self.out_adj.get(node_id, []) + self.in_adj.get(node_id, []):
            for e in self.edges[eid].get("evidence", []):
                srcs.add(e.get("source_id"))
        srcs.discard(None)
        return sorted(srcs)

    def graph_hash(self):
        """确定性哈希：只取决于 sources/nodes/edges/merge_decisions 内容。"""
        payload = {
            "sources": sorted(self.sources.values(), key=lambda s: s["source_id"]),
            "nodes": sorted(self.nodes.values(), key=lambda n: n["id"]),
            "edges": sorted(self.edges.values(), key=lambda e: e["id"]),
            "merge_decisions": sorted(self.merge_decisions, key=lambda d: d.get("id", "")),
        }
        return sha256_text(_canon(payload))

    def counts(self):
        return {"nodes": len(self.nodes), "edges": len(self.edges),
                "sources": len(self.sources), "merge_decisions": len(self.merge_decisions)}


def load_graph(path):
    """从 JSON 文件加载图谱；任何结构问题都抛 GraphLoadError（信息明确）。"""
    if not os.path.isfile(path):
        raise GraphLoadError("图谱文件不存在: %s" % path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as exc:
        raise GraphLoadError("图谱文件不是合法 JSON: %s（%s）" % (path, exc))
    except UnicodeDecodeError as exc:
        raise GraphLoadError("图谱文件不是 UTF-8 文本: %s（%s）" % (path, exc))
    if not isinstance(raw, dict):
        raise GraphLoadError("图谱顶层必须是 JSON 对象: %s" % path)
    for key in ("nodes", "edges"):
        if key not in raw or not isinstance(raw[key], list):
            raise GraphLoadError("图谱缺少列表字段 %s: %s" % (key, path))
    return Graph(raw, origin=path)
