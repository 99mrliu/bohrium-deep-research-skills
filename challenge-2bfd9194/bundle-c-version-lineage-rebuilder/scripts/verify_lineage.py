#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_lineage.py — 独立校验器（仅标准库，无网络）。

**只读** /input 与 /app/output（本脚本不写任何被校验目录，仅在 --out 下
写 audit_report.json）。独立重算：哈希 / 词干 / 分组 / 边，并回查：
  1. version_graph.json 节点与重扫输入一致；
  2. 每条 admin_note 边的 locator 回查备注原文真实命中且两端解析正确；
  3. 每条 stem_mtime 边同词干同扩展名、为组内 mtime 相邻对、方向一致；
  4. 链拓扑健全：重算无未声明的环；
  5. LINEAGE_REPORT.md 与图一致（链/边依据/locator/latest 标注）；
  6. LIBRARY_MANIFEST.jsonl 与 library/ 目录树一致（哈希复算）；
  7. duplicates.json 与重算哈希组一致；
  8. 跳过项在 skipped_and_conflicts.json 中如实披露；
  9. operations_journal.jsonl 行可解析且与 manifest 闭合；
 10. result.json 存在且含 case_id/status。
输出 /app/output/audit_report.json：{"overall": PASS|FAIL, "checks": [...]}
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lineage  # noqa: E402  校验器复用同一规则书（references/ 中已文档化）

REQUIRED_ROLES = {"latest", "superseded", "alias", "orphan"}


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def sha_of(path):
    try:
        return lineage.sha256_file(path)
    except OSError:
        return None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    inp, out = args.input, args.out
    checks = []

    def check(cid, ok, detail=""):
        checks.append({"id": cid, "status": "PASS" if ok else "FAIL",
                       "detail": "" if ok else detail})
        return ok

    records, skipped = lineage.scan_tree(inp)
    rec_by_sha = {r["sha256"]: r for r in records}

    graph = load_json(os.path.join(out, "version_graph.json"))
    if not check("graph_exists", graph is not None,
                 "version_graph.json 缺失或不可解析"):
        graph = {"nodes": [], "edges": [], "aliases": [], "chains": [],
                 "chain_meta": [], "orphans": [], "conflicts": []}

    # 1. 节点一致性（重扫输入 vs graph.nodes）
    g_nodes = {(n["sha256"], n["path"]) for n in graph["nodes"]}
    r_nodes = {(r["sha256"], r["path"]) for r in records}
    check("nodes_match_input", g_nodes == r_nodes,
          "graph 节点 %d，重扫 %d；差集: %s" % (
              len(g_nodes), len(r_nodes),
              list(g_nodes ^ r_nodes)[:5]))

    # 2. admin_note 边 locator 回查原文真实命中
    e1_edges = [e for e in graph["edges"] if e.get("basis") == "admin_note"]
    e1_bad = []
    for e in e1_edges:
        loc = e.get("locator", "")
        path, _, ln = loc.rpartition("#L")
        ok = False
        try:
            with open(os.path.join(inp, path), encoding="utf-8",
                      errors="replace") as f:
                lines = f.read().splitlines()
            line = lines[int(ln) - 1]
            for _pid, rx in lineage.ADMIN_PATTERNS:
                m = rx.search(line)
                if m:
                    new_r = lineage.resolve_name(m.group("new").strip(" .。，,"), records)
                    old_r = lineage.resolve_name(m.group("old").strip(" .。，,"), records)
                    ok = (new_r and old_r
                          and new_r["sha256"] == e["dst_sha"]
                          and old_r["sha256"] == e["src_sha"])
                    break
        except (OSError, ValueError, IndexError):
            ok = False
        if not ok:
            e1_bad.append(loc)
    check("admin_note_locator_verified", not e1_bad,
          "回查失败 locator: %s" % e1_bad[:5])

    # 3. stem_mtime 边：同词干同扩展名、组内 mtime 相邻、方向一致
    alias_paths = {a["alias_path"] for a in graph["aliases"]}
    groups = {}
    for r in records:
        if r["is_note"] or r["path"] in alias_paths:
            continue
        groups.setdefault((r["stem"], r["ext"]), []).append(r)
    adjacent = set()
    for members in groups.values():
        if len(members) < 2 or len({m["sha256"] for m in members}) == 1:
            continue
        members.sort(key=lambda r: (r["mtime"], r["name"]))
        for a, b in zip(members, members[1:]):
            if a["sha256"] != b["sha256"]:
                adjacent.add((a["sha256"], b["sha256"]))
    e3_edges = [e for e in graph["edges"] if e.get("basis") == "stem_mtime"]
    e3_bad = [(e["src_sha"][:8], e["dst_sha"][:8])
              for e in e3_edges if (e["src_sha"], e["dst_sha"]) not in adjacent]
    check("stem_mtime_edges_valid", not e3_bad,
          "非词干组内 mtime 相邻对的 stem_mtime 边: %s" % e3_bad[:5])

    # 4. 拓扑健全：重算的环必须已在 conflicts 中声明
    recomputed_cycles = lineage.find_cycles(
        [n["sha256"] for n in graph["nodes"]], graph["edges"])
    declared = bool([c for c in graph["conflicts"] if c.get("type") == "cycle"])
    check("no_undeclared_cycles", not recomputed_cycles or declared,
          "重算发现 %d 个环，conflicts 声明=%s" % (len(recomputed_cycles), declared))

    # 5. LINEAGE_REPORT.md 与图一致
    try:
        with open(os.path.join(out, "LINEAGE_REPORT.md"), encoding="utf-8") as f:
            report = f.read()
    except OSError:
        report = ""
    rep_bad = []
    for e in graph["edges"]:
        if e.get("basis") == "admin_note" and e.get("locator", "") not in report:
            rep_bad.append("locator " + e.get("locator", ""))
        if e.get("basis") == "stem_mtime" and e.get("evidence", "") not in report:
            rep_bad.append("evidence " + e.get("evidence", "")[:40])
    for meta in graph["chain_meta"]:
        if "`%s`" % meta["stem"] not in report:
            rep_bad.append("stem " + meta["stem"])
    n_latest = report.count("（latest）")
    if n_latest != len(graph["chains"]):
        rep_bad.append("latest 标注 %d != 链数 %d" % (n_latest, len(graph["chains"])))
    check("report_consistent_with_graph", bool(report) and not rep_bad,
          "; ".join(rep_bad[:5]))

    # 6. manifest 与 library/ 目录树一致（哈希复算）
    manifest = []
    try:
        with open(os.path.join(out, "LIBRARY_MANIFEST.jsonl"), encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    manifest.append(json.loads(ln))
    except (OSError, ValueError):
        manifest = None
    lib_root = os.path.join(out, "library")
    tree = {}
    for root, dirs, files in os.walk(lib_root):
        dirs.sort()
        for fn in sorted(files):
            full = os.path.join(root, fn)
            rel = lineage.nfc(os.path.relpath(full, lib_root))
            tree[rel] = sha_of(full)
    m_bad = []
    if manifest is None:
        m_bad.append("manifest 缺失或不可解析")
    else:
        m_tree = {}
        for m in manifest:
            if m.get("role") not in REQUIRED_ROLES:
                m_bad.append("非法 role: %s" % m.get("role"))
            if m.get("role") == "alias":
                if m.get("library_path") is not None or not m.get("alias_of"):
                    m_bad.append("alias 行缺 alias_of 或误入库: %s" % m.get("source_path"))
                continue
            lib = m.get("library_path")
            if not lib or lib not in tree:
                m_bad.append("manifest 指向的文件不存在: %s" % lib)
            elif tree[lib] != m.get("sha256"):
                m_bad.append("哈希不符: %s" % lib)
            else:
                m_tree[lib] = tree[lib]
        missing = sorted(set(tree) - set(m_tree))
        if missing:
            m_bad.append("library/ 中未登记: %s" % missing[:5])
    check("manifest_matches_tree", not m_bad, "; ".join(m_bad[:5]))

    # 7. duplicates.json 与重算哈希组一致
    by_hash = {}
    for r in records:
        by_hash.setdefault(r["sha256"], []).append(r["path"])
    expect_dup = {sha: sorted(ps) for sha, ps in by_hash.items() if len(ps) > 1}
    dup = load_json(os.path.join(out, "duplicates.json")) or {}
    got_dup = {}
    for g in dup.get("groups", []):
        got_dup[g.get("sha256")] = sorted([g.get("canonical", "")] + g.get("aliases", []))
    check("duplicates_match",
          expect_dup == got_dup,
          "期望 %s，实际 %s" % ({k[:8]: v for k, v in expect_dup.items()},
                                {str(k)[:8]: v for k, v in got_dup.items()}))

    # 8. 跳过项如实披露
    sc = load_json(os.path.join(out, "skipped_and_conflicts.json")) or {}
    disclosed = {s.get("path") for s in sc.get("skipped", [])}
    expect_skip = {s["path"] for s in skipped}
    check("skipped_disclosed", expect_skip <= disclosed,
          "未披露: %s" % sorted(expect_skip - disclosed)[:5])

    # 9. journal 闭合：行可解析、copy 条目覆盖 manifest 已入库项
    j_bad = []
    journal = []
    try:
        with open(os.path.join(out, "operations_journal.jsonl"), encoding="utf-8") as f:
            for i, ln in enumerate(f, 1):
                ln = ln.strip()
                if ln:
                    try:
                        journal.append(json.loads(ln))
                    except ValueError:
                        j_bad.append("第 %d 行不可解析" % i)
    except OSError:
        j_bad.append("operations_journal.jsonl 缺失")
    if manifest is not None:
        j_srcs = {j.get("src") for j in journal if j.get("op") == "copy"}
        for m in manifest:
            if m.get("role") != "alias" and m.get("source_path") not in j_srcs:
                j_bad.append("已入库但无 copy 日志: %s" % m.get("source_path"))
    check("journal_closed", not j_bad, "; ".join(j_bad[:5]))

    # 10. result.json 基本结构
    result = load_json(os.path.join(out, "result.json"))
    check("result_structure",
          bool(result) and "case_id" in result and "status" in result,
          "result.json 缺 case_id/status")

    overall = "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL"
    audit = {"overall": overall, "verifier": "verify_lineage.py",
             "checks": checks,
             "counts": {"pass": sum(1 for c in checks if c["status"] == "PASS"),
                        "fail": sum(1 for c in checks if c["status"] == "FAIL")}}
    with open(os.path.join(out, "audit_report.json"), "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps({"overall": overall,
                      "fail": [c["id"] for c in checks if c["status"] == "FAIL"]},
                     ensure_ascii=False))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
