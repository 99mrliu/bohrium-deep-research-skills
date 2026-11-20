#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dedup.py — 分层身份匹配，产出可解释判定日志、簇划分与仲裁队列。

输入：normalize_records.py 的 normalized.jsonl；跨标识符互链线索来自
--summary（case_summary.json 的 reference_graph_files）或显式 --idmap 文件。
只使用引用图/映射表中显式给出的 id 对应关系，绝不臆造 pmid↔doi 映射。

分层规则（详见 references/matching_rules.md）：
  Tier 1 标识符精确：DOI 归一相等→T1_DOI_EXACT；PMID→T1_PMID_EXACT；
    PMCID→T1_PMCID_EXACT；引用图别名对齐的跨标识符对→T1_ID_CROSSREF。
    全部自动归并。
  Tier 2 归一题名+年份+首作者姓三者全等→T2_TITLE_YEAR_FIRSTAUTHOR，
    自动归并；题名与首作者全等但年份不同→NON_DUP_YEAR_MISMATCH（判非重复）。
  Tier 3 模糊：归一词集合 Jaccard≥阈值 且 作者姓集合重合≥阈值 且
    年份差≤窗口→T3_FUZZY_ARBITRATE，仅进仲裁队列，绝不自动合并；
    触发相似但作者不重合→NON_DUP_AUTHOR_MISMATCH；年份超窗→
    NON_DUP_YEAR_MISMATCH。

输出：
  --decisions  dedup_decisions.jsonl：每条 {pair, tier, match, reason_code,
               evidence}；match ∈ true|false|arbitrate，确定性排序。
  --clusters   clusters.json：并查集簇 [{cluster_id, member_uids, tier,
               status}]，仲裁对涉及的簇标 pending_arbitration。
  --queue      arbitration_queue.json：待人工/模型仲裁对。

退出码：0=成功；2=normalized 缺失或无有效记录；3=输入 JSON 非法。
--thresholds '{"jaccard":0.6,"author_overlap":0.5,"year_window":1}' 可调，
默认值即规范值。

用法：
  python3 dedup.py --normalized /app/work/normalized.jsonl \
      --summary /app/work/case_summary.json \
      --decisions /app/work/dedup_decisions.jsonl \
      --clusters /app/work/clusters.json --queue /app/work/arbitration_queue.json
"""
import argparse
import json
import os
import re
import sys

DEFAULT_THRESHOLDS = {"jaccard": 0.6, "author_overlap": 0.5, "year_window": 1}
ALIAS_KEYS = ("aliases", "same_work", "equivalences", "id_map", "mappings",
              "sameas", "same_as")
ID_KINDS = ("doi", "pmid", "pmcid")


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
            self.parent[max(ra, rb)] = min(ra, rb)
            return True
        return False


def load_jsonl(path):
    """宽容读 JSONL：坏行跳过并计数留痕。"""
    records, bad = [], 0
    with open(path, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                print("WARN: normalized.jsonl 第 %d 行 JSON 非法，已跳过留痕"
                      % ln, file=sys.stderr)
                continue
            if isinstance(obj, dict) and obj.get("record_uid"):
                records.append(obj)
            else:
                bad += 1
                print("WARN: normalized.jsonl 第 %d 行缺 record_uid，已跳过"
                      % ln, file=sys.stderr)
    return records, bad


def collect_alias_pairs(obj, out):
    """从引用图 JSON 递归收集显式 id 对应关系（不臆造）。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            if kl in ALIAS_KEYS:
                items = v if isinstance(v, list) else [v]
                for it in items:
                    ids = {}
                    if isinstance(it, dict):
                        for kind in ID_KINDS:
                            val = it.get(kind) or it.get(kind.upper())
                            if val:
                                ids[kind] = str(val).strip().lower()
                        if it.get("type") in ("same_as", "same-work",
                                              "same_work", "equivalent"):
                            a, b = it.get("a") or it.get("from"), \
                                it.get("b") or it.get("to")
                            if a and b:
                                out.append((("id", str(a).strip().lower()),
                                            ("id", str(b).strip().lower())))
                    kinds = sorted(ids)
                    for i in range(len(kinds)):
                        for j in range(i + 1, len(kinds)):
                            out.append(((kinds[i], ids[kinds[i]]),
                                        (kinds[j], ids[kinds[j]])))
            else:
                collect_alias_pairs(v, out)
    elif isinstance(obj, list):
        for it in obj:
            collect_alias_pairs(it, out)


def load_id_pairs(paths):
    pairs, loaded = [], []
    for p in paths:
        if not p or not os.path.isfile(p):
            print("WARN: id 映射/引用图文件不存在，跳过: %s" % p, file=sys.stderr)
            continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                obj = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print("WARN: 引用图文件 JSON 非法，跳过: %s (%s)" % (p, e),
                  file=sys.stderr)
            continue
        collect_alias_pairs(obj, pairs)
        loaded.append(os.path.basename(p))
    # 去重保持确定性
    uniq = sorted(set(pairs))
    return uniq, loaded


def jaccard(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / float(len(a | b))


def author_families(rec):
    fams = set()
    for a in rec.get("authors_norm") or []:
        f = re.sub(r"[^a-z]+", "", str(a.get("family") or "").lower())
        if f:
            fams.add(f)
    return fams


def first_author_family(rec):
    au = rec.get("authors_norm") or []
    if not au:
        return ""
    return re.sub(r"[^a-z]+", "", str(au[0].get("family") or "").lower())


def title_tokens(rec):
    return set((rec.get("title_norm") or "").split())


def run(args):
    try:
        thresholds = dict(DEFAULT_THRESHOLDS)
        if args.thresholds:
            thresholds.update(json.loads(args.thresholds))
    except json.JSONDecodeError as e:
        print("ERROR: --thresholds JSON 非法（校验失败）: %s" % e, file=sys.stderr)
        return 3

    if not os.path.isfile(args.normalized):
        print("ERROR: normalized.jsonl 不存在（材料不足）: %s"
              % args.normalized, file=sys.stderr)
        return 2
    try:
        records, bad_lines = load_jsonl(args.normalized)
    except OSError as e:
        print("ERROR: normalized.jsonl 读取失败（校验失败）: %s" % e,
              file=sys.stderr)
        return 3
    if not records:
        print("ERROR: normalized.jsonl 无有效记录（材料不足，诚实降级）。",
              file=sys.stderr)
        return 2

    # 收集引用图/映射文件
    idmap_paths = list(args.idmap or [])
    if args.summary and os.path.isfile(args.summary):
        try:
            with open(args.summary, "r", encoding="utf-8") as f:
                sm = json.load(f)
            idmap_paths.extend(sm.get("reference_graph_files") or [])
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print("WARN: case_summary 非法，忽略其引用图定位: %s" % e,
                  file=sys.stderr)
    alias_pairs, alias_files = load_id_pairs(idmap_paths)

    n = len(records)
    uf = UnionFind(n)
    uid_of = [r["record_uid"] for r in records]
    idx_of = {u: i for i, u in enumerate(uid_of)}
    decisions = []

    def decide(a, b, tier, match, reason, evidence):
        pa, pb = sorted((uid_of[a], uid_of[b]))
        decisions.append({"pair": [pa, pb], "tier": tier, "match": match,
                          "reason_code": reason, "evidence": evidence})

    # 标识符索引：id 值 -> [record 索引]
    id_index = {k: {} for k in ID_KINDS}
    for i, r in enumerate(records):
        ids = r.get("identifiers") or {}
        for kind in ID_KINDS:
            v = (ids.get(kind) or {}).get("value")
            if v:
                id_index[kind].setdefault(v, []).append(i)

    # ---- Tier 1a：同标识符精确 ----
    for kind, reason in (("doi", "T1_DOI_EXACT"), ("pmid", "T1_PMID_EXACT"),
                         ("pmcid", "T1_PMCID_EXACT")):
        for value in sorted(id_index[kind]):
            members = sorted(id_index[kind][value])
            for x, y in zip(members, members[1:]):
                if uf.union(x, y):
                    decide(x, y, 1, True, reason,
                           {kind: value, "sources": [records[x]["source"],
                                                     records[y]["source"]]})
    # ---- Tier 1b：跨标识符互链（引用图显式别名） ----
    for (ka, va), (kb, vb) in alias_pairs:
        group_a, group_b = set(), set()
        for kind, val in ((ka, va), (kb, vb)):
            ids = id_index.get(kind, {})
            hit = ids.get(val)
            if hit is None and kind == "doi":
                hit = ids.get(val.lower())
            if hit:
                (group_a if (kind, val) == (ka, va) else group_b).update(hit)
        for x in sorted(group_a):
            for y in sorted(group_b):
                if x != y and uf.union(x, y):
                    decide(x, y, 1, True, "T1_ID_CROSSREF",
                           {"alias": {ka: va, kb: vb},
                            "alias_source_files": alias_files,
                            "note": "引用图显式别名对齐，非臆造映射"})

    # ---- Tier 2：归一题名 + 年份 + 首作者姓 ----
    by_title = {}
    for i, r in enumerate(records):
        t = r.get("title_norm") or ""
        if t:
            by_title.setdefault(t, []).append(i)
    for t in sorted(by_title):
        members = sorted(by_title[t])
        for ai in range(len(members)):
            for bi in range(ai + 1, len(members)):
                x, y = members[ai], members[bi]
                if uf.find(x) == uf.find(y):
                    continue
                fa, fb = first_author_family(records[x]), first_author_family(records[y])
                ya, yb = records[x].get("year"), records[y].get("year")
                ev = {"title_norm": t, "year_a": ya, "year_b": yb,
                      "first_author_a": fa, "first_author_b": fb}
                if fa and fb and fa == fb:
                    if ya and yb and ya != yb:
                        decide(x, y, 2, False, "NON_DUP_YEAR_MISMATCH", ev)
                    elif ya and yb and ya == yb:
                        uf.union(x, y)
                        decide(x, y, 2, True, "T2_TITLE_YEAR_FIRSTAUTHOR", ev)
                    else:
                        decide(x, y, 2, False, "NON_DUP_YEAR_UNKNOWN",
                               dict(ev, note="年份缺失，Tier2 不予自动归并"))
                # 首作者不同：交给 Tier 3 判断（题名相同也算强相似候选）

    # ---- Tier 3：模糊匹配 → 仲裁队列（绝不自动合并） ----
    tj, ta = float(thresholds["jaccard"]), float(thresholds["author_overlap"])
    yw = int(thresholds["year_window"])
    decided_pairs = {tuple(sorted(d["pair"])) for d in decisions}
    queue = []
    for x in range(n):
        for y in range(x + 1, n):
            if uf.find(x) == uf.find(y):
                continue
            if tuple(sorted((uid_of[x], uid_of[y]))) in decided_pairs:
                continue
            ta_set, tb_set = title_tokens(records[x]), title_tokens(records[y])
            jac = jaccard(ta_set, tb_set)
            if jac < tj:
                continue  # 低相似对不记入日志（降噪）
            fa_set, fb_set = author_families(records[x]), author_families(records[y])
            aov = jaccard(fa_set, fb_set)
            ya, yb = records[x].get("year"), records[y].get("year")
            ydiff = abs(ya - yb) if (ya and yb) else None
            ev = {"jaccard": round(jac, 4), "author_overlap": round(aov, 4),
                  "year_a": ya, "year_b": yb, "year_diff": ydiff,
                  "title_norm_a": records[x].get("title_norm"),
                  "title_norm_b": records[y].get("title_norm"),
                  "thresholds": thresholds}
            if ydiff is None or ydiff > yw:
                decide(x, y, 3, False, "NON_DUP_YEAR_MISMATCH", ev)
            elif aov < ta:
                decide(x, y, 3, False, "NON_DUP_AUTHOR_MISMATCH", ev)
            else:
                decide(x, y, 3, "arbitrate", "T3_FUZZY_ARBITRATE", ev)
                queue.append({"pair": sorted((uid_of[x], uid_of[y])),
                              "reason_code": "T3_FUZZY_ARBITRATE",
                              "evidence": ev, "status": "pending",
                              "question": "两条记录是否指向同一作品？"
                                          "（merge/split，写入 arbitrations.json）"})
    # ---- 簇划分 ----
    pending_pairs = {tuple(q["pair"]) for q in queue}
    clusters_map = {}
    for i in range(n):
        clusters_map.setdefault(uf.find(i), []).append(i)
    clusters = []
    for root in sorted(clusters_map, key=lambda r: uid_of[min(clusters_map[r])]):
        members = sorted(clusters_map[root], key=lambda i: uid_of[i])
        muids = [uid_of[i] for i in members]
        tiers = sorted({d["tier"] for d in decisions
                        if d["match"] is True
                        and set(d["pair"]) <= set(muids)} or {0})
        status = "auto"
        for q in queue:
            if set(q["pair"]) & set(muids):
                status = "pending_arbitration"
                break
        clusters.append({"cluster_id": None, "member_uids": muids,
                         "match_tiers": [t for t in tiers if t],
                         "status": status})
    for k, c in enumerate(clusters, 1):
        c["cluster_id"] = "C%03d" % k

    # 确定性排序后落盘
    decisions.sort(key=lambda d: (d["tier"], d["pair"], d["reason_code"]))
    for path, obj, is_jsonl in (
            (args.decisions, decisions, True),
            (args.clusters, {"clusters": clusters,
                             "thresholds": thresholds,
                             "alias_source_files": alias_files,
                             "skipped_bad_lines": bad_lines}, False),
            (args.queue, {"pending": queue,
                          "policy": "T3 模糊对绝不自动合并；模型按 SKILL.md "
                                    "步骤仲裁后写入 arbitrations.json"}, False)):
        d = os.path.dirname(os.path.abspath(path))
        os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            if is_jsonl:
                for row in obj:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            else:
                json.dump(obj, f, ensure_ascii=False, indent=2)
    n_true = sum(1 for d in decisions if d["match"] is True)
    n_false = sum(1 for d in decisions if d["match"] is False)
    print("OK: 去重判定完成 (记录=%d, 簇=%d, 判定=%d[并=%d/否=%d/裁=%d], "
          "待仲裁=%d, 坏行跳过=%d)"
          % (n, len(clusters), len(decisions), n_true, n_false,
             len(queue), len(queue), bad_lines))
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="分层身份匹配 + 判定日志 + 仲裁队列（exit 0/2/3）。")
    ap.add_argument("--normalized", default="/app/work/normalized.jsonl",
                    help="normalized.jsonl 路径")
    ap.add_argument("--summary", default=None,
                    help="case_summary.json（用于定位 reference_graph 文件）")
    ap.add_argument("--idmap", nargs="*", default=None,
                    help="显式 id 映射/引用图文件（可多个，与 --summary 叠加）")
    ap.add_argument("--decisions", default="/app/work/dedup_decisions.jsonl")
    ap.add_argument("--clusters", default="/app/work/clusters.json")
    ap.add_argument("--queue", default="/app/work/arbitration_queue.json")
    ap.add_argument("--thresholds", default=None,
                    help='JSON 覆盖默认阈值，如 '
                         '\'{"jaccard":0.6,"author_overlap":0.5,"year_window":1}\'')
    args = ap.parse_args()
    try:
        return run(args)
    except Exception as e:
        print("ERROR: dedup 未预期异常（降级 exit 2）: %r" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
