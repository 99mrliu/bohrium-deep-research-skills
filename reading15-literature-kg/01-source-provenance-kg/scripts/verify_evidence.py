#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_evidence.py — 严格证据与归属验证器。

对“候选语义抽取结果”（candidate extraction，通常由模型产出）执行机械化校验。
本脚本不做任何语义判断，只验证可机械判定的硬规则：

A. 证据地址与引文
  A1 每条证据必须含 source_id / paragraph_id / quote 三字段；
  A2 source_id 必须存在于归一化语料；
  A3 paragraph_id 必须存在于该 source 内；
  A4 若 paragraph_id 属于“重复 id”清单（地址歧义），一律报错；
  A5 quote 必须是该段落原文的精确子串（逐字符，含空格与单位符号），
     且长度 <= MAX_QUOTE_CHARS。不允许凭记忆转写、不允许“页码式”地址。
B. 归属（根元数据只属 primary）
  B1 kind=paper 的节点：全部证据必须来自同一 source；其 attributes 中的
     doi/title/authors（若声明）必须逐字符等于该 source 的 article-meta；
  B2 extraction.primary_paper 指向的节点其证据源 role 必须为 primary。
C. 节点/边完备性
  C1 每个节点、每条边必须至少有一条合法证据（无证据的对象一律拒绝）；
  C2 边的 subject/object 必须指向已声明节点；
  C3 边不得引用 merge 的 member 节点（合并必须在图上真正生效）。
D. 合并纪律（跨论文 merge 与显式 nonmerge）
  D1 merge.node 存在；merge.members 存在、互不相同、且至少 2 个；
  D2 merge.node 的证据源集合 == 各 member 证据源集合之并，且跨 >=2 个 source
     （否则合并不具备跨论文依据）；
  D3 merge.node 与全部 members 的 canonical_key 必须完全相同；
  D4 若 members 均带 attributes.value（如 metric/claim），数值必须全部相等，
     否则拒绝合并（条件/样本/数值不同，绝不并入同一结论）；
  D5 nonmerge.members 为存在且互异的两个节点，reason 非空；
  D6 同名（归一化 label 相同）且未被合并吸收的节点对，必须被某条 nonmerge
     显式覆盖——“同名≠同一实体”必须留下显式判决记录。
E. 冲突与未报告
  E1 conflicts[*].resolution 必须为 "preserved"：来源冲突原样保留，
     禁止取平均/择一/静默消解；
  E2 conflicts/unreported 若附证据，同样过 A 组校验。
F. 覆盖度（机械统计）
  F1 统计每个 source 被至少一条证据引用的段落比例，写入 coverage；
     未达 100% 记 warning（不阻断，但必须如实披露）。

CLI:
  python3 verify_evidence.py --corpus normalized_corpus.json \
      --extraction candidate_extraction.json --out verify_report.json
退出码：0 通过（可有 warning）；2 存在 error。
"""

from __future__ import annotations

import argparse
import sys

import kgcommon as k


class Verifier:
    def __init__(self, corpus):
        self.corpus = corpus
        self.sources, self.para_index = k.build_paragraph_index(corpus)
        self.dup = k.duplicate_id_set(corpus)
        self.errors = []
        self.warnings = []
        # 覆盖度：{(source_id, paragraph_id): 引用计数}
        self.cited = {}

    # ---- A 组：证据地址与引文 ----
    def check_evidence_list(self, evidence, where):
        if not isinstance(evidence, list) or not evidence:
            self.errors.append(f"{where}: 缺少证据列表（每个实质性节点/边必须附证据）")
            return []
        ok_items = []
        for i, ev in enumerate(evidence):
            w = f"{where}.evidence[{i}]"
            if not isinstance(ev, dict):
                self.errors.append(f"{w}: 证据项不是对象")
                continue
            sid, pid, quote = ev.get("source_id"), ev.get("paragraph_id"), ev.get("quote")
            missing = [f for f, v in (("source_id", sid), ("paragraph_id", pid), ("quote", quote)) if not v]
            if missing:
                self.errors.append(f"{w}: 缺少字段 {missing}")
                continue
            if sid not in self.sources:
                self.errors.append(f"{w}: source_id '{sid}' 不在语料中（错源/臆造源）")
                continue
            if pid in self.dup.get(sid, set()):
                self.errors.append(f"{w}: paragraph_id '{pid}' 在 {sid} 中为重复地址，歧义不可用")
                continue
            para = self.para_index.get((sid, pid))
            if para is None:
                self.errors.append(f"{w}: 段落 {sid}/{pid} 不存在（地址错误）")
                continue
            if not isinstance(quote, str) or len(quote) > k.MAX_QUOTE_CHARS:
                self.errors.append(f"{w}: quote 缺失或超过 {k.MAX_QUOTE_CHARS} 字符（要求短引文）")
                continue
            if quote not in para["text"]:
                self.errors.append(
                    f"{w}: quote 不是 {sid}/{pid} 原文的精确子串（引文不匹配）：{quote!r}")
                continue
            self.cited[(sid, pid)] = self.cited.get((sid, pid), 0) + 1
            ok_items.append(ev)
        return ok_items

    # ---- B 组：归属 ----
    def check_paper_node(self, node, evidence):
        where = f"node[{node.get('node_id')}](paper)"
        sids = k.evidence_source_ids(evidence)
        if len(sids) != 1:
            self.errors.append(f"{where}: paper 根节点证据必须来自唯一 source，实际 {sids}")
            return
        src = self.sources[sids[0]]
        attrs = node.get("attributes") or {}
        for field in ("doi", "title"):
            if field in attrs and attrs[field] != src.get(field):
                self.errors.append(
                    f"{where}: attributes.{field} 与来源 {sids[0]} 的 article-meta 不一致"
                    f"（根元数据归属错误）：{attrs[field]!r} != {src.get(field)!r}")
        if "authors" in attrs and list(attrs["authors"]) != list(src.get("authors", [])):
            self.errors.append(f"{where}: attributes.authors 与来源 {sids[0]} 不一致")

    # ---- D 组：合并纪律 ----
    def check_merge(self, merge, nodes_by_id):
        mid = merge.get("merge_id", "<no-id>")
        where = f"merge[{mid}]"
        node = nodes_by_id.get(merge.get("node"))
        members = merge.get("members") or []
        if node is None:
            self.errors.append(f"{where}: node '{merge.get('node')}' 不存在")
            return
        if len(members) < 2 or len(set(members)) != len(members):
            self.errors.append(f"{where}: members 必须为 >=2 个互异节点，实际 {members}")
            return
        member_nodes = []
        for m in members:
            mn = nodes_by_id.get(m)
            if mn is None:
                self.errors.append(f"{where}: member '{m}' 不存在")
                continue
            member_nodes.append(mn)
        if len(member_nodes) != len(members):
            return
        if not merge.get("justification"):
            self.errors.append(f"{where}: 缺少 justification（合并理由必须显式记录）")
        self.check_evidence_list(merge.get("evidence"), where)

        node_sids = set(k.evidence_source_ids(node.get("evidence")))
        union = set()
        for mn in member_nodes:
            union |= set(k.evidence_source_ids(mn.get("evidence")))
        if node_sids != union:
            self.errors.append(f"{where}: 合并节点证据源 {sorted(node_sids)} != 成员证据源之并 {sorted(union)}")
        if len(union) < 2:
            self.errors.append(f"{where}: 合并未跨越 >=2 个来源，跨论文依据不足")
        keys = {mn.get("canonical_key") for mn in member_nodes} | {node.get("canonical_key")}
        keys.discard(None)
        if len(keys) > 1:
            self.errors.append(f"{where}: canonical_key 不一致 {sorted(keys)}，禁止合并")
        if not keys:
            self.errors.append(f"{where}: 合并对象缺少 canonical_key，无法机械核对同一性")
        values = [mn.get("attributes", {}).get("value") for mn in member_nodes]
        if all(v is not None for v in values) and len(set(map(str, values))) > 1:
            self.errors.append(
                f"{where}: members 数值不一致 {values}，拒绝合并"
                f"（不同条件/样本/数值绝不并入同一结论）")

    def check_nonmerge(self, nonmerge, nodes_by_id, merge_member_sets):
        nid = nonmerge.get("nonmerge_id", "<no-id>")
        where = f"nonmerge[{nid}]"
        members = nonmerge.get("members") or []
        if len(members) != 2 or len(set(members)) != 2:
            self.errors.append(f"{where}: members 必须为两个互异节点，实际 {members}")
        for m in members:
            if m not in nodes_by_id:
                self.errors.append(f"{where}: member '{m}' 不存在")
        if not nonmerge.get("reason"):
            self.errors.append(f"{where}: 缺少 reason（不合并理由必须显式记录）")
        self.check_evidence_list(nonmerge.get("evidence"), where)
        for mset in merge_member_sets:
            if set(members) <= mset:
                self.errors.append(f"{where}: members 同时被某 merge 吸收，判决自相矛盾")

    # ---- F 组：覆盖度 ----
    def coverage_report(self):
        per_source = []
        total_p, total_c = 0, 0
        for src in self.corpus.get("sources", []):
            sid = src["source_id"]
            paras = src.get("paragraphs", [])
            covered = sum(1 for p in paras if self.cited.get((sid, p["id"])))
            uncovered = [p["id"] for p in paras if not self.cited.get((sid, p["id"]))]
            total_p += len(paras)
            total_c += covered
            if uncovered:
                self.warnings.append(f"{sid}: 段落未被任何证据引用 {uncovered}")
            per_source.append({
                "source_id": sid,
                "paragraphs": len(paras),
                "covered": covered,
                "uncovered_paragraph_ids": sorted(uncovered),
            })
        return {
            "per_source": per_source,
            "total_paragraphs": total_p,
            "covered_paragraphs": total_c,
            "coverage_ratio": (total_c / total_p) if total_p else None,
        }


def verify(extraction, corpus):
    """返回 verify report 对象；report['ok'] 为是否零 error。"""
    v = Verifier(corpus)
    if not isinstance(extraction, dict):
        return {"ok": False, "errors": ["extraction 不是对象"], "warnings": [], "coverage": None}

    nodes = extraction.get("nodes") or []
    edges = extraction.get("edges") or []
    merges = extraction.get("merges") or []
    nonmerges = extraction.get("nonmerges") or []
    conflicts = extraction.get("conflicts") or []
    unreported = extraction.get("unreported") or []

    nodes_by_id = {}
    for node in nodes:
        nid = node.get("node_id")
        where = f"node[{nid}]"
        if not nid:
            v.errors.append("存在缺少 node_id 的节点")
            continue
        if nid in nodes_by_id:
            v.errors.append(f"{where}: node_id 重复")
            continue
        nodes_by_id[nid] = node
        if not node.get("kind"):
            v.errors.append(f"{where}: 缺少 kind")
        ev = v.check_evidence_list(node.get("evidence"), where)
        if node.get("kind") == "paper" and ev:
            v.check_paper_node(node, ev)

    # merge member 节点集合（用于 C3 / D6）
    merge_members = set()
    merge_member_sets = []
    for m in merges:
        ms = set(m.get("members") or [])
        merge_member_sets.append(ms)
        merge_members |= ms

    edge_ids = set()
    for edge in edges:
        eid = edge.get("edge_id")
        where = f"edge[{eid}]"
        if not eid:
            v.errors.append("存在缺少 edge_id 的边")
            continue
        if eid in edge_ids:
            v.errors.append(f"{where}: edge_id 重复")
        edge_ids.add(eid)
        for ep in ("subject", "object"):
            ref = edge.get(ep)
            if ref not in nodes_by_id:
                v.errors.append(f"{where}: {ep} 指向未声明节点 '{ref}'")
            elif ref in merge_members:
                v.errors.append(f"{where}: {ep} 引用了 merge member '{ref}'，"
                                f"必须改引用合并后的节点")
        if not edge.get("type"):
            v.errors.append(f"{where}: 缺少 type")
        v.check_evidence_list(edge.get("evidence"), where)

    for m in merges:
        v.check_merge(m, nodes_by_id)
    for nm in nonmerges:
        v.check_nonmerge(nm, nodes_by_id, merge_member_sets)

    # D6：同名节点对必须有显式 nonmerge
    by_label = {}
    for nid, node in nodes_by_id.items():
        if nid in merge_members:
            continue
        merged_nodes = {m.get("node") for m in merges}
        if nid in merged_nodes:
            continue
        by_label.setdefault(k.norm_label(node.get("label")), []).append(nid)
    covered_pairs = set()
    for nm in nonmerges:
        members = nm.get("members") or []
        if len(members) == 2:
            covered_pairs.add(frozenset(members))
    for label, ids in sorted(by_label.items()):
        if label and len(ids) > 1:
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    if frozenset((ids[i], ids[j])) not in covered_pairs:
                        v.errors.append(
                            f"同名节点对 ({ids[i]}, {ids[j]})（label 归一化='{label}'）"
                            f"既未合并也无显式 nonmerge 记录")

    # E 组
    for c in conflicts:
        cid = c.get("conflict_id", "<no-id>")
        if c.get("resolution") != "preserved":
            v.errors.append(f"conflict[{cid}]: resolution 必须为 'preserved'"
                            f"（来源冲突原样保留，禁止消解），实际 {c.get('resolution')!r}")
        if not c.get("topic"):
            v.errors.append(f"conflict[{cid}]: 缺少 topic")
        for claim in c.get("claims") or []:
            ref = claim.get("node") if isinstance(claim, dict) else None
            if ref not in nodes_by_id:
                v.errors.append(f"conflict[{cid}]: claims 引用未声明节点 '{ref}'")
        if c.get("evidence"):
            v.check_evidence_list(c["evidence"], f"conflict[{cid}]")
    for u in unreported:
        if not u.get("topic") or not u.get("reason"):
            v.errors.append(f"unreported 条目缺少 topic/reason：{u}")
        if u.get("evidence"):
            v.check_evidence_list(u["evidence"], f"unreported[{u.get('topic')}]")

    # B2
    pp = extraction.get("primary_paper")
    if pp is not None:
        node = nodes_by_id.get(pp)
        if node is None:
            v.errors.append(f"primary_paper 指向未声明节点 '{pp}'")
        else:
            sids = k.evidence_source_ids(node.get("evidence"))
            roles = {v.sources[s].get("role") for s in sids if s in v.sources}
            if roles != {"primary"}:
                v.errors.append(f"primary_paper 节点证据源 role 必须为 primary，实际 {sorted(roles)}")
    else:
        v.warnings.append("extraction 未声明 primary_paper 字段")

    coverage = v.coverage_report()
    return {
        "ok": not v.errors,
        "error_count": len(v.errors),
        "warning_count": len(v.warnings),
        "errors": v.errors,
        "warnings": v.warnings,
        "coverage": coverage,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="严格证据与归属验证器")
    ap.add_argument("--corpus", required=True, help="normalized_corpus.json")
    ap.add_argument("--extraction", required=True, help="candidate extraction JSON")
    ap.add_argument("--out", required=True, help="verify_report.json 输出路径")
    args = ap.parse_args(argv)

    corpus = k.read_json(args.corpus)
    extraction = k.read_json(args.extraction)
    report = verify(extraction, corpus)
    k.write_json(args.out, report)
    print(f"[verify_evidence] ok={report['ok']} errors={report['error_count']} "
          f"warnings={report['warning_count']}")
    for e in report["errors"]:
        print(f"  error: {e}")
    for w in report["warnings"]:
        print(f"  warning: {w}")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
