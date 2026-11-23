# -*- coding: utf-8 -*-
"""跨文档实体身份裁决门（确定性合并门，仅标准库）。

输入：一组“提及记录”（mention），各自属于某一篇论文（source_id）。
输出：逐对裁决（MERGE / KEEP_DISTINCT / UNDECIDED）与并查集聚类。

裁决规则（保守，透明）：
R0  仅同篇（source_id 相同）的提及不构成本门的跨篇候选，直接跳过——
    同篇多种格式或同篇多处出现都不算跨篇证据。
R1  阻断项（任一成立即 KEEP_DISTINCT，并记录 blocking_evidence）：
    - 定义性属性同名不同值（样品、模型实例、数据集版本、条件等不同）；
    - 测量属性同名同单位但数值不同（numeric_conflict）；
    - 测量属性同名但单位不可比（unit_conflict）。
    注意：不同 DOI / 不同来源 *不是* 阻断项。
R2  合并依据（无阻断项时）：至少一个定义性属性规范化一致
    （如化学式、原理、架构等），允许 MERGE，merge_basis 记录该依据。
R2b 通用术语（generic_terms）即使 R2 命中，若缺少强身份键
    （cas_number/identifier/sample_id/instrument）一致，至多 UNDECIDED：
    相同通用方法/材料术语不代表同一物理样品、模型实例或数据集。
R3  既无阻断也无合并依据（仅规范化别名相同）：UNDECIDED，
    证据不足，绝不强迫合并。
稳定节点 ID 只在裁决完成之后由 build_graph.py 分配。
"""
from normalize import (
    candidate_keys, defining_attrs, measured_attrs,
    normalize_unit, normalize_value, numbers_equal,
)


def compare_pair(a, b):
    """比较两条提及的属性签名，返回 (blockers, matches)。"""
    blockers, matches = [], []
    da, db = defining_attrs(a), defining_attrs(b)
    for key in sorted(set(da) & set(db)):
        va, vb = normalize_value(da[key]), normalize_value(db[key])
        rec = {"attribute": key, "value_a": da[key], "value_b": db[key]}
        if va == vb:
            rec["kind"] = "defining_match"
            matches.append(rec)
        else:
            rec["kind"] = "defining_conflict"
            blockers.append(rec)
    for na in measured_attrs(a):
        for nb in measured_attrs(b):
            if normalize_value(na.get("name")) != normalize_value(nb.get("name")):
                continue
            rec = {"attribute": na.get("name"),
                   "value_a": na.get("value"), "unit_a": na.get("unit"),
                   "value_b": nb.get("value"), "unit_b": nb.get("unit")}
            ua, ub = normalize_unit(na.get("unit")), normalize_unit(nb.get("unit"))
            if ua != ub:
                rec["kind"] = "unit_conflict"
                blockers.append(rec)
            else:
                eq = numbers_equal(na.get("value"), nb.get("value"))
                if eq is False:
                    rec["kind"] = "numeric_conflict"
                    blockers.append(rec)
    return blockers, matches


class _UnionFind(object):
    def __init__(self, ids):
        self.parent = {i: i for i in ids}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # 确定性：字典序小者为根
            hi, lo = max(ra, rb), min(ra, rb)
            self.parent[hi] = lo


def adjudicate(mentions, generic_terms=None):
    """对全部提及执行跨篇身份裁决，返回 (decisions, clusters)。

    decisions: 逐对裁决记录（含 blocking_evidence / merge_basis / rationale）。
    clusters:  MERGE 并查集聚类，每个簇 {cluster_key, members, decision_refs}；
               未合并的提及各自成为单成员簇。
    """
    generic = set(generic_terms or [])
    uf = _UnionFind([m["mention_id"] for m in mentions])
    by_id = {m["mention_id"]: m for m in mentions}
    key_index = {}
    for m in mentions:
        for key in candidate_keys(m):
            key_index.setdefault(key, []).append(m)

    # 先归并候选对：同一对跨篇提及无论共享多少个候选键，只裁决一次。
    pair_keys = {}
    for key in sorted(key_index):
        group = key_index[key]
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if a.get("source_id") == b.get("source_id"):
                    continue  # R0：同篇不算跨篇候选
                pair = tuple(sorted((a["mention_id"], b["mention_id"])))
                pair_keys.setdefault(pair, set()).add(key)

    decisions = []
    for pair_no, pair in enumerate(sorted(pair_keys), start=1):
        a, b = by_id[pair[0]], by_id[pair[1]]
        shared = sorted(pair_keys[pair])
        blockers, matches = compare_pair(a, b)
        strong = any(m["attribute"] in
                     ("cas_number", "identifier", "sample_id", "instrument")
                     for m in matches)
        if blockers:
            dec, rationale = "KEEP_DISTINCT", (
                "存在阻断性冲突证据（不同样品/模型/数据集/条件或数值/单位冲突），"
                "不得合并")
        elif matches and not (set(shared) & generic and not strong):
            dec, rationale = "MERGE", "定义性属性一致，无阻断项，允许合并"
        elif matches:
            dec, rationale = "UNDECIDED", (
                "通用术语且缺少强身份键一致，不能确认同一物理实例")
        else:
            dec, rationale = "UNDECIDED", (
                "仅规范化别名相同，无定义性属性证据，证据不足")
        if dec == "MERGE":
            uf.union(a["mention_id"], b["mention_id"])
        decisions.append({
            "decision_id": "D-%04d" % pair_no,
            "candidate_keys": shared,
            "pair": [a["mention_id"], b["mention_id"]],
            "sources": [a.get("source_id"), b.get("source_id")],
            "decision": dec,
            "merge_basis": matches,
            "blocking_evidence": blockers,
            "rationale": rationale,
        })

    groups = {}
    for mid in by_id:
        groups.setdefault(uf.find(mid), []).append(mid)
    clusters = []
    for root in sorted(groups):
        members = sorted(groups[root])
        refs = [d["decision_id"] for d in decisions
                if d["decision"] == "MERGE"
                and d["pair"][0] in members and d["pair"][1] in members]
        clusters.append({
            "cluster_key": root,
            "members": members,
            "merged": len(members) > 1,
            "decision_refs": refs,
        })
    return decisions, clusters
