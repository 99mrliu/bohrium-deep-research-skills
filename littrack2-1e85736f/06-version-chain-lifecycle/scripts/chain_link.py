"""chain_link.py — 版本链构建。

把同一研究成果的预印本 / 正式版 / 修订版 / 撤稿或勘误声明链接成一条
版本链（union-find）。链接规则按证据强度排序：

  R1  DOI 关系字段：Crossref `relation` 中 relation-type 属于版本链语义的
      （is-preprint-of / has-preprint / is-retraction-of / has-retraction /
       is-correction-of / has-correction / is-version-of / has-version /
       is-supplement-to 不在内——补充材料不是同一成果的版本）。
  R2  Crossref `update-to`（retraction / correction 等更新标记，按 DOI 链接）。
  R3  arXiv base id 相同、版本号不同（v1→v2→…）。
  R4  后备：标题归一化完全一致 且 第一作者归一化一致（标注 confidence=low）。

每条链接决策都写入 link_decisions，携带双方记录的 locator 与触发字段的
JSON 指针，保证可回放。
"""

# R1 接受的 relation-type（全部小写、连字符风格）
LINKING_RELATION_TYPES = {
    "is-preprint-of", "has-preprint",
    "is-retraction-of", "has-retraction",
    "is-correction-of", "has-correction",
    "is-version-of", "has-version",
    "is-expression-of-concern-of", "has-expression-of-concern",
}


class UnionFind:
    def __init__(self, n):
        self.parent = list(range(n))

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra
            return True
        return False


def _loc(rec):
    return {"file": rec["locator"]["file"], "pointer": rec["locator"]["pointer"]}


def build_chains(records):
    """输入 common.extract_records 的记录列表。

    返回 (chains, link_decisions)。
    chains: list of {"chain_id", "members": [uid...], "member_records": [...]}
    link_decisions: list of 决策证据字典。
    """
    n = len(records)
    uf = UnionFind(n)
    decisions = []

    by_doi = {}
    by_arxiv = {}
    for i, rec in enumerate(records):
        if rec.get("doi"):
            by_doi.setdefault(rec["doi"], []).append(i)
        if rec.get("arxiv_id"):
            by_arxiv.setdefault(rec["arxiv_id"], []).append(i)

    def link(a, b, rule, confidence, extra_locators):
        if a == b:
            return
        merged = uf.union(a, b)
        decisions.append({
            "rule": rule,
            "confidence": confidence,
            "a": records[a]["uid"],
            "b": records[b]["uid"],
            "merged": merged,
            "locators": [_loc(records[a]), _loc(records[b])] + extra_locators,
        })

    # R1: DOI 关系字段
    for i, rec in enumerate(records):
        for rel in rec.get("relations", []):
            if rel["type"] not in LINKING_RELATION_TYPES:
                continue
            target = rel["id"].lower()
            for j in by_doi.get(target, []):
                link(i, j, "R1-doi-relation(%s)" % rel["type"], "high", [{
                    "file": rec["locator"]["file"],
                    "pointer": rec["locator"]["pointer"] + rel["pointer"],
                }])

    # R2: update-to（撤稿/勘误更新标记）
    for i, rec in enumerate(records):
        for upd in rec.get("update_to", []):
            target = upd["doi"].lower()
            for j in by_doi.get(target, []):
                link(i, j, "R2-update-to(%s)" % upd["type"], "high", [{
                    "file": rec["locator"]["file"],
                    "pointer": rec["locator"]["pointer"] + upd["pointer"],
                }])

    # R3: arXiv base id 相同 → 同一链的不同版本
    for arxiv_id, idxs in by_arxiv.items():
        for k in range(1, len(idxs)):
            link(idxs[0], idxs[k], "R3-arxiv-version(%s)" % arxiv_id, "high", [])

    # R4: 标题归一化 + 第一作者 后备近似匹配
    by_title = {}
    for i, rec in enumerate(records):
        if rec.get("title_norm") and rec.get("first_author"):
            by_title.setdefault(
                (rec["title_norm"], rec["first_author"]), []).append(i)
    for (_t, _a), idxs in by_title.items():
        for k in range(1, len(idxs)):
            link(idxs[0], idxs[k], "R4-title+first-author", "low", [])

    # 汇总链
    groups = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)
    chains = []
    for seq, (_root, idxs) in enumerate(
            sorted(groups.items(), key=lambda kv: min(kv[1])), start=1):
        members = [records[i] for i in idxs]
        chains.append({
            "chain_id": "chain-%03d" % seq,
            "members": [r["uid"] for r in members],
            "member_records": members,
        })
    return chains, decisions
