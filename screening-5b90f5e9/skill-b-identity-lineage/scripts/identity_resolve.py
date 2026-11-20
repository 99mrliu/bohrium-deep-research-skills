#!/usr/bin/env python3
"""identity_resolve.py - 身份解析：规范化 + 阻塞 + 三层匹配。

输入: /app/work/records.jsonl
输出:
  pair_decisions.jsonl  每个候选对 {pair, tier, decision, scores, evidence, buckets}
  clusters.json         Tier1/Tier2 自动合并簇（union-find）
  review_queue.json     Tier3 待仲裁对（含 scores 与双方关键字段对照）

分层判据（见 rules/matching_policy.md）:
  Tier1 归一 DOI / PMID / arXiv id 相同 → auto_merge
  Tier2 归一题名完全相同 且 年份差=0 → auto_merge
  Tier3 题名 token Jaccard≥0.6 且首作者姓相同 且 |年份差|≤1 → pending（绝不自动合并）
  其余 → keep_separate
跨标识符（PMID-only × DOI-only）绝不臆造映射，只能走 Tier2/Tier3。

退出码: 0=成功; 2=记录为空; 3=失败。
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

JACCARD_THRESHOLD = 0.6
TITLE_BUCKET_LEN = 40


def norm_title(t):
    if not t:
        return ""
    s = unicodedata.normalize("NFKC", str(t)).lower()
    s = re.sub(r"[^0-9a-z一-鿿]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_doi(d):
    if not d:
        return ""
    s = str(d).strip().lower()
    for p in ("https://doi.org/", "http://doi.org/",
              "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if s.startswith(p):
            s = s[len(p):]
    return s.strip().rstrip(".")


def norm_simple_id(v):
    if not v:
        return ""
    s = str(v).strip().lower()
    s = re.sub(r"^(pmid:|pmc:|arxiv:)", "", s)
    return s.strip()


def first_author_surname(authors):
    if not authors:
        return ""
    a = str(authors[0]).strip()
    if not a:
        return ""
    if "," in a:
        sur = a.split(",", 1)[0]
    else:
        parts = a.split()
        sur = parts[-1] if parts else ""
    sur = unicodedata.normalize("NFKC", sur).lower()
    return re.sub(r"[^a-z一-鿿]", "", sur)


def year4(y):
    if y is None:
        return None
    m = re.search(r"(19|20)\d{2}", str(y))
    return m.group(0) if m else None


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def enrich(rec):
    r = dict(rec)
    r["_norm_title"] = norm_title(rec.get("title"))
    r["_tokens"] = set(r["_norm_title"].split()) if r["_norm_title"] else set()
    r["_doi"] = norm_doi(rec.get("doi"))
    r["_pmid"] = norm_simple_id(rec.get("pmid"))
    r["_arxiv"] = norm_simple_id(rec.get("arxiv"))
    r["_surname"] = first_author_surname(rec.get("authors"))
    r["_year"] = year4(rec.get("year"))
    return r


def key_fields(r):
    return {"record_id": r["record_id"], "title": r.get("title"),
            "year": r.get("year"), "first_author_surname": r["_surname"],
            "doi": r.get("doi"), "pmid": r.get("pmid"), "arxiv": r.get("arxiv"),
            "venue": r.get("venue"), "source_file": r.get("source_file"),
            "norm_title": r["_norm_title"]}


def evaluate(ra, rb):
    """返回 (tier, decision, scores, evidence)"""
    scores = {
        "title_jaccard": round(jaccard(ra["_tokens"], rb["_tokens"]), 4),
        "norm_title_equal": bool(ra["_norm_title"]) and ra["_norm_title"] == rb["_norm_title"],
        "first_author_match": bool(ra["_surname"]) and ra["_surname"] == rb["_surname"],
        "year_a": ra["_year"], "year_b": rb["_year"],
        "year_diff": (abs(int(ra["_year"]) - int(rb["_year"]))
                      if ra["_year"] and rb["_year"] else None),
    }
    # Tier1: 标识符精确
    for idtype in ("_doi", "_pmid", "_arxiv"):
        va, vb = ra[idtype], rb[idtype]
        if va and vb and va == vb:
            return ("tier1", "auto_merge", scores,
                    {"type": idtype.lstrip("_"), "value": va,
                     "rule": "归一化标识符完全相同"})
    # Tier2: 归一题名 + 年份差 0
    if (scores["norm_title_equal"] and ra["_norm_title"]
            and scores["year_diff"] == 0):
        return ("tier2", "auto_merge", scores,
                {"type": "norm_title+year", "norm_title": ra["_norm_title"],
                 "year": ra["_year"], "rule": "归一化题名完全相同且年份一致"})
    # Tier3: 模糊 → 只进仲裁队列
    if (scores["title_jaccard"] >= JACCARD_THRESHOLD
            and scores["first_author_match"]
            and scores["year_diff"] is not None and scores["year_diff"] <= 1):
        return ("tier3", "pending", scores,
                {"type": "fuzzy",
                 "rule": (f"Jaccard≥{JACCARD_THRESHOLD} 且首作者姓相同且年份差≤1；"
                          "仅入仲裁队列，绝不自动合并"),
                 "conflict_signals": {
                     "year_conflict": scores["year_diff"] not in (0, None),
                     "venue_conflict": bool(ra.get("venue") and rb.get("venue")
                                            and ra["venue"] != rb["venue"]),
                     "doi_both_present_different": bool(ra["_doi"] and rb["_doi"]
                                                        and ra["_doi"] != rb["_doi"])}})
    return ("none", "keep_separate", scores,
            {"type": "no_match", "rule": "未满足任何匹配层判据"})


def main() -> int:
    ap = argparse.ArgumentParser(description="记录身份解析：规范化+阻塞+三层匹配")
    ap.add_argument("--work", default="/app/work", help="工作目录 (默认 /app/work)")
    args = ap.parse_args()
    work = Path(args.work)

    recs_path = work / "records.jsonl"
    if not recs_path.exists():
        print(json.dumps({"ok": False, "exit": 2,
                          "reason": "records.jsonl 不存在，请先运行 import_records.py"},
                         ensure_ascii=False))
        return 2
    records = [enrich(json.loads(line))
               for line in recs_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not records:
        print(json.dumps({"ok": False, "exit": 2, "reason": "0 条记录"}, ensure_ascii=False))
        return 2

    # ---- 阻塞：归一题名前40字符桶 / DOI 桶 / PMID 桶 / arXiv 桶 / 年份桶 ----
    buckets = {}
    for i, r in enumerate(records):
        keys = []
        if r["_norm_title"]:
            keys.append(("t", r["_norm_title"][:TITLE_BUCKET_LEN]))
        if r["_doi"]:
            keys.append(("d", r["_doi"]))
        if r["_pmid"]:
            keys.append(("p", r["_pmid"]))
        if r["_arxiv"]:
            keys.append(("x", r["_arxiv"]))
        if r["_year"]:
            keys.append(("y", r["_year"]))
        r["_bucket_keys"] = keys
        for k in keys:
            buckets.setdefault(k, []).append(i)

    pair_buckets = {}
    for bk, idxs in buckets.items():
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                key = (min(idxs[a], idxs[b]), max(idxs[a], idxs[b]))
                pair_buckets.setdefault(key, []).append(f"{bk[0]}:{bk[1][:24]}")

    uf = UnionFind()
    n_auto = n_pending = n_keep = 0
    pair_lines, pending = [], []
    auto_ev = []  # 平铺存证据，最后按端点归属分配到簇，避免并查集根漂移丢失证据
    for (i, j), bks in sorted(pair_buckets.items()):
        ra, rb = records[i], records[j]
        pair_id = "|".join(sorted([ra["record_id"], rb["record_id"]]))
        tier, decision, scores, evidence = evaluate(ra, rb)
        row = {"pair": pair_id, "tier": tier, "decision": decision,
               "scores": scores, "evidence": evidence, "buckets": bks}
        pair_lines.append(row)
        if decision == "auto_merge":
            uf.union(ra["record_id"], rb["record_id"])
            auto_ev.append({"pair": pair_id, "tier": tier, "evidence": evidence,
                            "endpoints": [ra["record_id"], rb["record_id"]]})
            n_auto += 1
        elif decision == "pending":
            pending.append({"pair": pair_id, "tier": tier, "scores": scores,
                            "evidence": evidence,
                            "a": key_fields(ra), "b": key_fields(rb)})
            n_pending += 1
        else:
            n_keep += 1

    with (work / "pair_decisions.jsonl").open("w", encoding="utf-8") as fh:
        for row in pair_lines:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    groups = {}
    for r in records:
        groups.setdefault(uf.find(r["record_id"]), []).append(r["record_id"])
    clusters = []
    for root in sorted(groups):
        members = sorted(groups[root])
        member_set = set(members)
        ev = [{"pair": e["pair"], "tier": e["tier"], "evidence": e["evidence"]}
              for e in auto_ev
              if e["endpoints"][0] in member_set or e["endpoints"][1] in member_set]
        clusters.append({
            "cluster_id": f"clu-{len(clusters) + 1:03d}",
            "members": members,
            "merge_evidence": ev,
            "origin": "auto",
        })

    (work / "clusters.json").write_text(json.dumps(
        {"clusters": clusters,
         "stats": {"records": len(records), "pairs_evaluated": len(pair_lines),
                   "auto_merge_pairs": n_auto, "pending_pairs": n_pending,
                   "keep_separate_pairs": n_keep,
                   "auto_clusters": len(clusters)}},
        ensure_ascii=False, indent=2), encoding="utf-8")
    (work / "review_queue.json").write_text(json.dumps(
        {"pending_pairs": pending,
         "instructions": "对每个 pending 对给出 merge 或 split 及非空 rationale，"
                         "写入 arbitrations.json（格式见 templates/arbitration.md）；"
                         "标题相似但作者/年份/期刊冲突的必须显式判 split。",
         "jaccard_threshold": JACCARD_THRESHOLD},
        ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"ok": True, "records": len(records),
                      "pairs_evaluated": len(pair_lines), "auto_merge": n_auto,
                      "pending": n_pending, "keep_separate": n_keep,
                      "auto_clusters": len(clusters)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(3)
