#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lineage.py — 版本世系图谱重建引擎（仅 Python 标准库，无网络）。

三级证据（严格降级，无证据不连边）：
  E1 行政版本备注解析 → basis=admin_note，evidence 带 locator=文件#行号
  E2 内容哈希相同     → 别名组（aliases，同内容不同名，**不是**版本）
  E3 规范化词干+同扩展名+内容不全同 → 候选版本组，组内按 mtime 相邻连
     basis=stem_mtime 的候选 supersedes 边
规则：
  * E1 优先于 E3；E1 指认的文件对即使词干不同也照连。
  * 备注类文件（文件名含 备注/notes/version/版本/行政/admin）不参与 E3 词干分组，
    避免把两个同名 notes.txt 误判为版本。
  * 环检测（DFS）：成环不强行断环，记 conflicts 并置 degraded=true（降级 partial）。
  * 多父（≥2 条入边）记 conflict，交由模型在 work/lineage_overrides.json 裁定：
      {"drop_edges": [[src, dst]], "add_edges": [{"src","dst","reason"}]}
    src/dst 可为 sha256 前缀、相对路径或文件名；重跑 lineage/plan/apply 生效。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata

CHUNK = 65536
SKIP_INPUT_NAMES = {"case.json", "task.md"}
CORRUPT_MARKER = "SIMULATED-CORRUPT"
NOTE_NAME_RE = re.compile(r"(备注|notes?|version|版本|行政|admin)", re.IGNORECASE)

# 文件名允许字符：字母/数字/_-. /CJK/全角括号编号在词干剥离阶段处理
_NAME = r"[A-Za-z0-9_\-\.一-鿿]"
# (句式 id, 正则)。捕获组语义：new=替代者（新），old=被替代者（旧）。边方向 old→new。
ADMIN_PATTERNS = [
    ("zh_tidai", re.compile(r"(?P<new>%s+?)\s*(?:替代|取代)\s*(?P<old>%s+)" % (_NAME, _NAME))),
    ("zh_zuofei", re.compile(r"(?P<old>%s+?)\s*作废\s*[，,；;]?\s*以\s*(?P<new>%s+?)\s*为准" % (_NAME, _NAME))),
    ("zh_beiti", re.compile(r"(?P<old>%s+?)\s*已被\s*(?P<new>%s+?)\s*(?:替换|取代|替代)" % (_NAME, _NAME))),
    ("zh_yiweizhun", re.compile(r"(?:旧版|原文件|原稿)?\s*(?P<old>%s+?)\s*不再使用\s*[，,；;]?\s*以\s*(?P<new>%s+?)\s*为准" % (_NAME, _NAME))),
    ("en_replaces", re.compile(r"(?P<new>%s+?)\s+replaces\s+(?P<old>%s+)" % (_NAME, _NAME), re.IGNORECASE)),
    ("en_supersedes", re.compile(r"(?P<new>%s+?)\s+supersedes\s+(?P<old>%s+)" % (_NAME, _NAME), re.IGNORECASE)),
]

# 词干规范化：剥离版本/备份/日期/序号尾巴（循环剥离直到稳定）
_STEM_TAIL_RES = [
    re.compile(r"[ _\-]?\(\d+\)$"),                                   # 尾序号 (1) (2)
    re.compile(r"[ _\-]?\d{4}-\d{2}-\d{2}$"),                         # 尾日期 YYYY-MM-DD
    re.compile(r"[ _\-]?\d{8}$"),                                     # 尾日期 YYYYMMDD
    re.compile(r"[ _\-]?[vV]\s?\d+(?:\.\d+)?$"),                      # _vN / _V N / v2
    re.compile(r"[ _\-]?(?:最终版|定稿|副本|备份)$"),
]
_TILDE_RE = re.compile(r"~+$")


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def normalize_stem(basename: str):
    """返回 (stem, ext_lower)。剥离 _vN、_V N、最终版、定稿、副本、备份、
    .bak、~、尾日期 YYYYMMDD/YYYY-MM-DD、尾序号 (1)/(2) 等。"""
    name = nfc(basename).strip()
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    if ext.lower() == "bak":  # file.txt.bak → stem=file, ext=txt
        s2, d2, e2 = stem.rpartition(".")
        if d2:
            stem, ext = s2, e2
        else:
            ext = ""
    stem = _TILDE_RE.sub("", stem)
    changed = True
    while changed and stem:
        changed = False
        for rx in _STEM_TAIL_RES:
            new = rx.sub("", stem)
            if new and new != stem:
                stem, changed = new, True
    return stem, ext.lower()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_tree(input_dir: str):
    """递归扫描材料。返回 (records, skipped)。绝不静默跳过、绝不崩溃。"""
    records, skipped = [], []
    for root, dirs, files in os.walk(input_dir):
        dirs.sort()
        for fn in sorted(files):
            name = nfc(fn)
            if name in SKIP_INPUT_NAMES:
                continue
            full = os.path.join(root, fn)
            rel = nfc(os.path.relpath(full, input_dir))
            try:
                st = os.stat(full)
                with open(full, "rb") as f:
                    head = f.read(512)
                if CORRUPT_MARKER.encode() in head:
                    skipped.append({"path": rel, "reason": "simulated_corrupt_marker",
                                    "detail": "文件头含 SIMULATED-CORRUPT 标记，按模拟损坏处理"})
                    continue
                sha = sha256_file(full)
            except (PermissionError, OSError, UnicodeError) as e:
                skipped.append({"path": rel, "reason": type(e).__name__,
                                "detail": str(e)[:200]})
                continue
            stem, ext = normalize_stem(fn)
            records.append({
                "path": rel, "name": name, "sha256": sha,
                "size": st.st_size, "mtime": st.st_mtime,
                "stem": stem, "ext": ext,
                "is_note": bool(NOTE_NAME_RE.search(name)),
            })
    records.sort(key=lambda r: r["path"])
    return records, skipped


def parse_admin_notes(records, input_root: str, extra_note_paths=None):
    """E1：扫描备注类文本，逐行跑中英文句式正则。返回命中列表（含 locator）。"""
    hits = []
    note_recs = [r for r in records if r["is_note"]]
    if extra_note_paths:
        have = {r["path"] for r in note_recs}
        for r in records:
            if r["path"] in extra_note_paths and r["path"] not in have:
                note_recs.append(r)
    for r in note_recs:
        full = os.path.join(input_root, r["path"])
        try:
            with open(full, encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            for pid, rx in ADMIN_PATTERNS:
                m = rx.search(line)
                if m:
                    hits.append({
                        "new_name": m.group("new").strip(" .。，,"),
                        "old_name": m.group("old").strip(" .。，,"),
                        "pattern": pid,
                        "locator": "%s#L%d" % (r["path"], i),
                        "line": line.strip(),
                    })
                    break
    return hits


def resolve_name(token: str, records):
    """把备注里的名字解析到扫描记录：先按文件名精确匹配，再按词干唯一匹配。
    无法唯一解析返回 None。"""
    token = nfc(token)
    by_name = [r for r in records if r["name"] == token]
    if len(by_name) == 1:
        return by_name[0]
    if len(by_name) > 1:
        return None  # 同名多文件，无法唯一指认
    base = token.rpartition(".")[0] if "." in token else token
    by_stem = [r for r in records if r["stem"] == base or r["stem"] == token]
    if len(by_stem) == 1:
        return by_stem[0]
    return None


def find_cycles(node_shas, edges):
    """DFS 找环。返回环列表（每个环是 sha 序列）。"""
    adj = {}
    for e in edges:
        adj.setdefault(e["src_sha"], []).append(e["dst_sha"])
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {s: WHITE for s in node_shas}
    cycles, stack = [], []

    def dfs(u):
        color[u] = GRAY
        stack.append(u)
        for v in adj.get(u, []):
            cv = color.get(v, WHITE)
            if cv == GRAY:
                cycles.append(stack[stack.index(v):] + [v])
            elif cv == WHITE:
                dfs(v)
        stack.pop()
        color[u] = BLACK

    for s in node_shas:
        if color[s] == WHITE:
            dfs(s)
    return cycles


def _resolve_ref(ref, records):
    """overrides 里的 src/dst 引用：sha256 前缀 / 相对路径 / 文件名。"""
    ref = nfc(str(ref))
    for r in records:
        if r["sha256"].startswith(ref) or r["path"] == ref or r["name"] == ref:
            return r["sha256"]
    return None


def build_graph(records, input_root: str, overrides=None, extra_note_paths=None):
    """构建版本世系图。返回 graph dict（可直接 json 序列化）。"""
    conflicts = []
    nodes = [{"sha256": r["sha256"], "path": r["path"], "stem": r["stem"],
              "mtime": r["mtime"], "size": r["size"]} for r in records]

    # ---- E2：内容哈希相同 → 别名组（不是版本）----
    by_hash = {}
    for r in records:
        by_hash.setdefault(r["sha256"], []).append(r)
    aliases, alias_paths = [], set()
    for sha, members in sorted(by_hash.items()):
        if len(members) > 1:
            members = sorted(members, key=lambda r: (len(r["name"]), r["name"]))
            canon = members[0]
            for m in members[1:]:
                aliases.append({"canonical_sha": canon["sha256"],
                                "canonical_path": canon["path"],
                                "alias_sha": m["sha256"], "alias_path": m["path"]})
                alias_paths.add(m["path"])

    # ---- E1：行政备注 ----
    e1_edges = []
    for h in parse_admin_notes(records, input_root, extra_note_paths):
        new_r = resolve_name(h["new_name"], records)
        old_r = resolve_name(h["old_name"], records)
        if new_r is None or old_r is None:
            conflicts.append({"type": "unresolved_admin_reference",
                              "locator": h["locator"], "line": h["line"],
                              "new_name": h["new_name"], "old_name": h["old_name"],
                              "detail": "行政备注指认的文件无法唯一解析，未连边"})
            continue
        if new_r["sha256"] == old_r["sha256"]:
            conflicts.append({"type": "admin_self_edge", "locator": h["locator"],
                              "detail": "备注两端解析为同一内容，未连边"})
            continue
        e1_edges.append({"src_sha": old_r["sha256"], "dst_sha": new_r["sha256"],
                         "basis": "admin_note",
                         "evidence": "行政备注原文: %s" % h["line"],
                         "locator": h["locator"]})

    # ---- E3：词干分组候选版本边 ----
    groups = {}
    for r in records:
        if r["is_note"] or r["path"] in alias_paths:
            continue  # 备注类文件与别名副本不参与版本分组
        groups.setdefault((r["stem"], r["ext"]), []).append(r)
    e3_edges = []
    for (stem, ext), members in sorted(groups.items()):
        if len(members) < 2 or len({m["sha256"] for m in members}) == 1:
            continue  # 单成员或全同（别名组）不连边
        members.sort(key=lambda r: (r["mtime"], r["name"]))
        for a, b in zip(members, members[1:]):
            if a["sha256"] == b["sha256"]:
                continue
            ev = "size_delta=%+dB; mtime_delta=%.0fs; stem=%s" % (
                b["size"] - a["size"], b["mtime"] - a["mtime"], stem)
            e3_edges.append({"src_sha": a["sha256"], "dst_sha": b["sha256"],
                             "basis": "stem_mtime", "evidence": ev})

    # ---- 合并：E1 优先 ----
    edges = list(e1_edges)
    e1_pairs = {(e["src_sha"], e["dst_sha"]) for e in e1_edges}
    for e in e3_edges:
        pair = (e["src_sha"], e["dst_sha"])
        if pair in e1_pairs:
            continue
        if (e["dst_sha"], e["src_sha"]) in e1_pairs:
            conflicts.append({"type": "e1_overrides_e3", "kept_basis": "admin_note",
                              "dropped_candidate": e,
                              "detail": "E3 候选边方向与行政备注相反，按 E1 优先丢弃"})
            continue
        edges.append(e)

    # ---- 模型裁定覆盖 ----
    if overrides:
        for pair in overrides.get("drop_edges", []):
            if isinstance(pair, (list, tuple)) and len(pair) == 2:
                s = _resolve_ref(pair[0], records)
                d = _resolve_ref(pair[1], records)
                before = len(edges)
                edges = [e for e in edges if not (e["src_sha"] == s and e["dst_sha"] == d)]
                if len(edges) == before:
                    conflicts.append({"type": "override_noop",
                                      "detail": "drop_edges %s 未命中任何边" % (pair,)})
        for e in overrides.get("add_edges", []):
            s = _resolve_ref(e.get("src", ""), records)
            d = _resolve_ref(e.get("dst", ""), records)
            if s and d and s != d:
                edges.append({"src_sha": s, "dst_sha": d, "basis": "model",
                              "evidence": "模型裁定: %s" % e.get("reason", ""),
                              "locator": "work/lineage_overrides.json"})
            else:
                conflicts.append({"type": "override_noop",
                                  "detail": "add_edges 无法解析: %s" % (e,)})

    # 去重（同 src/dst 保留先者，E1 在前）
    seen, dedup = set(), []
    for e in edges:
        k = (e["src_sha"], e["dst_sha"])
        if k not in seen:
            seen.add(k)
            dedup.append(e)
    edges = dedup

    node_shas = [n["sha256"] for n in nodes]
    degraded = False

    # ---- 环检测：不断环，记冲突并降级 ----
    cycles = find_cycles(node_shas, edges)
    if cycles:
        degraded = True
        by_sha = {n["sha256"]: n["path"] for n in nodes}
        conflicts.append({"type": "cycle", "cycles_sha": cycles,
                          "cycles_path": [[by_sha.get(s, s) for s in c] for c in cycles],
                          "detail": "版本关系成环，未强行断环，需模型裁定"})

    # ---- 多父检测 ----
    indeg = {}
    for e in edges:
        indeg[e["dst_sha"]] = indeg.get(e["dst_sha"], 0) + 1
    by_sha = {n["sha256"]: n["path"] for n in nodes}
    for sha, d in sorted(indeg.items()):
        if d > 1:
            degraded = True
            parents = [by_sha.get(e["src_sha"], e["src_sha"]) for e in edges if e["dst_sha"] == sha]
            conflicts.append({"type": "multi_parent", "node": by_sha.get(sha, sha),
                              "parents": parents,
                              "detail": "多个节点同时 supersedes 同一节点，需模型在 lineage_overrides.json 裁定"})

    # ---- 链（弱连通分量 + 拓扑序）----
    parent = {s: s for s in node_shas}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in edges:
        parent[find(e["src_sha"])] = find(e["dst_sha"])
    comps = {}
    for s in node_shas:
        comps.setdefault(find(s), []).append(s)
    node_by_sha = {n["sha256"]: n for n in nodes}
    in_edge = {e["dst_sha"] for e in edges}
    out_edge = {e["src_sha"] for e in edges}
    chains, chain_meta = [], []
    for root, members in sorted(comps.items(), key=lambda kv: min(kv[1])):
        if not any(s in in_edge or s in out_edge for s in members):
            continue  # 孤立节点不进链
        mset = set(members)
        # Kahn 拓扑排序（成环时退化为 mtime 序）
        ind = {s: 0 for s in members}
        adj2 = {}
        for e in edges:
            if e["src_sha"] in mset:
                adj2.setdefault(e["src_sha"], []).append(e["dst_sha"])
                ind[e["dst_sha"]] += 1
        queue = sorted([s for s in members if ind[s] == 0],
                       key=lambda s: (node_by_sha[s]["mtime"], node_by_sha[s]["path"]))
        order = []
        while queue:
            u = queue.pop(0)
            order.append(u)
            for v in sorted(adj2.get(u, [])):
                ind[v] -= 1
                if ind[v] == 0:
                    queue.append(v)
            queue.sort(key=lambda s: (node_by_sha[s]["mtime"], node_by_sha[s]["path"]))
        if len(order) < len(members):  # 有环
            rest = [s for s in members if s not in order]
            rest.sort(key=lambda s: (node_by_sha[s]["mtime"], node_by_sha[s]["path"]))
            order.extend(rest)
        sinks = [s for s in members if s not in out_edge]
        if len(sinks) == 1 and not cycles:
            latest = sinks[0]
        elif sinks:
            sinks.sort(key=lambda s: (node_by_sha[s]["mtime"], node_by_sha[s]["path"]))
            latest = sinks[-1]
            conflicts.append({"type": "multi_sink",
                              "nodes": [by_sha.get(s, s) for s in sinks],
                              "detail": "链内多个无出边节点，latest 按 mtime 取最末，需模型确认"})
            degraded = True
        else:  # 全节点成环，无 sink：latest 取 mtime 最末并记冲突（环已另行记录）
            latest = max(members, key=lambda s: (node_by_sha[s]["mtime"],
                                                 node_by_sha[s]["path"]))
            conflicts.append({"type": "no_sink",
                              "nodes": [by_sha.get(s, s) for s in members],
                              "detail": "链内无无出边节点（成环），latest 按 mtime 取最末，需模型裁定"})
            degraded = True
        chains.append(order)
        chain_meta.append({"stem": node_by_sha[latest]["stem"], "latest_sha": latest})

    chained = {s for ch in chains for s in ch}
    seen_orphan, orphans = set(), []
    for n in nodes:  # 同 sha 的别名副本会产生重复节点条目，按 path 去重
        if n["sha256"] in chained or n["path"] in alias_paths or n["path"] in seen_orphan:
            continue
        seen_orphan.add(n["path"])
        orphans.append(n["sha256"])
    orphans.sort(key=lambda s: node_by_sha[s]["path"])

    return {
        "schema": "version_graph/v1",
        "evidence_levels": {"E1": "admin_note", "E2": "content_hash_alias", "E3": "stem_mtime"},
        "nodes": nodes,
        "edges": edges,
        "aliases": aliases,
        "chains": chains,
        "chain_meta": chain_meta,
        "orphans": orphans,
        "conflicts": conflicts,
        "degraded": degraded,
    }


def render_report(graph) -> str:
    """生成人读版 LINEAGE_REPORT.md。"""
    by_sha = {n["sha256"]: n for n in graph["nodes"]}
    lines = ["# 版本世系报告（LINEAGE_REPORT）", "",
             "> 自动生成。证据等级：E1 行政备注（admin_note）> E2 内容哈希（别名，非版本）> E3 词干+mtime（stem_mtime 候选）。**无证据不连边。**",
             "> 边方向：旧版本 → 新版本（supersedes）。", ""]

    latest_of = {m["latest_sha"] for m in graph["chain_meta"]}
    for idx, (chain, meta) in enumerate(zip(graph["chains"], graph["chain_meta"]), 1):
        lines.append("## 链 %d：词干 `%s`（%d 个版本）" % (idx, meta["stem"], len(chain)))
        lines.append("")
        lines.append("版本序列（旧 → 新）：")
        for pos, sha in enumerate(chain, 1):
            n = by_sha[sha]
            mark = " **（latest）**" if sha in latest_of and pos == len(chain) else ""
            lines.append("%d. `%s`（size=%dB, mtime=%d）%s" % (
                pos, n["path"], n["size"], int(n["mtime"]), mark))
        lines.append("")
        lines.append("边依据：")
        chain_set = set(chain)
        pos = {s: i for i, s in enumerate(chain)}
        chain_edges = [e for e in graph["edges"]
                       if e["src_sha"] in chain_set and e["dst_sha"] in chain_set]
        chain_edges.sort(key=lambda e: (pos.get(e["src_sha"], 99), pos.get(e["dst_sha"], 99)))
        for e in chain_edges:
            a, b = e["src_sha"], e["dst_sha"]
            loc = "；locator: `%s`" % e["locator"] if e.get("locator") else ""
            lines.append("- `%s` → `%s`：basis=%s；evidence: %s%s" % (
                by_sha[a]["path"], by_sha[b]["path"], e["basis"], e["evidence"], loc))
        lines.append("")

    if graph["aliases"]:
        lines.append("## 别名组（同内容不同名，**不是**版本关系）")
        lines.append("")
        for a in graph["aliases"]:
            lines.append("- 正本 `%s` ← 别名 `%s`（sha256 相同，不重复入库）" % (
                a["canonical_path"], a["alias_path"]))
        lines.append("")

    if graph["orphans"]:
        lines.append("## 孤儿节点（无版本关系证据，正常入库）")
        lines.append("")
        for s in graph["orphans"]:
            lines.append("- `%s`" % by_sha[s]["path"])
        lines.append("")

    if graph["conflicts"]:
        lines.append("## 冲突与待裁定项")
        lines.append("")
        for c in graph["conflicts"]:
            lines.append("- [%s] %s" % (c.get("type", "?"), c.get("detail", "")))
        lines.append("")

    lines.append("---")
    lines.append("链数=%d，边数=%d，别名=%d，孤儿=%d，冲突=%d，degraded=%s" % (
        len(graph["chains"]), len(graph["edges"]), len(graph["aliases"]),
        len(graph["orphans"]), len(graph["conflicts"]), str(graph["degraded"]).lower()))
    lines.append("")
    return "\n".join(lines)
