#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""merge_records.py — 确定性簇合并：每字段优先级策略 + 字段溯源 + 冲突日志。

输入：
  --normalized   normalized.jsonl（normalize_records.py）
  --clusters     clusters.json（dedup.py）
  --arbitrations 可选。模型仲裁决议 JSON：
      [{"pair": ["uidA", "uidB"], "decision": "merge"|"split",
        "decided_by": "model", "rationale": "..."}]
      无此文件时，arbitrate 涉及的簇保持未决并在结果中如实标注
      arbitration_status=pending_arbitration。

合并策略（全文见 references/merge_policy.md）：
  标识符 doi/pmid/pmcid：任一来源提供即收录，来源全部记入 provenance；
    同簇出现多个不同 DOI 属标识符冲突，记 conflict_log 并取优先级最高者。
  书目字段（title/year/container/volume/issue/pages/type/pub_date_iso）：
    publisher > crossref > europepmc > recordlist > jsonl > csv > unknown
    （version of record 优先）。
  abstract：europepmc > publisher > crossref > 其余；来源未提供时在
    provenance 记 not_provided_by（如 not_provided_by_crossref）。
  authors：crossref > europepmc > publisher > 其余；统一 [{family, given}]。
  字段缺失聚合语义：present（任一来源提供）> unknown（有键但空/不可解析）
    > missing（所有来源 not_provided）。
  同字段多来源给出不同非空值 → conflict_log.jsonl：
    {cluster_id, canonical_id, field, values_by_source, chosen, rule, reason}。
  确定性排序：canonical 记录按 (归一 DOI 或 归一题名) 字典序升序，
    canonical_id 在排序后分配，同输入必得同输出（可重放）。

输出：
  --out        merged_records.json {records:[canonical...], summary:{...}}
  --conflicts  conflict_log.jsonl

退出码：0=成功；2=输入缺失/无记录；3=输入 JSON 非法。
"""
import argparse
import json
import os
import sys

SOURCE_PRIORITY = ["publisher", "crossref", "europepmc", "recordlist",
                   "jsonl", "csv", "unknown"]
ABSTRACT_PRIORITY = ["europepmc", "publisher", "crossref", "recordlist",
                     "jsonl", "csv", "unknown"]
AUTHORS_PRIORITY = ["crossref", "europepmc", "publisher", "recordlist",
                    "jsonl", "csv", "unknown"]

BIB_FIELDS = ["title", "year", "container", "volume", "issue", "pages",
              "type", "pub_date_iso"]
REC_FIELD = {"title": ("title_raw", "title"), "year": ("year", "year"),
             "container": ("container_raw", "container"),
             "volume": ("volume", "volume"), "issue": ("issue", "issue"),
             "pages": ("pages", "pages"), "type": ("type", "type"),
             "pub_date_iso": ("pub_date_iso", "pub_date_iso"),
             "abstract": ("abstract", "abstract")}


def prio(priority, source):
    try:
        return priority.index(source)
    except ValueError:
        return len(priority)


def load_json(path, what):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print("ERROR: %s JSON 非法（校验失败）: %s" % (what, e), file=sys.stderr)
        raise ValueError(what)


def load_jsonl(path):
    records, bad = [], 0
    with open(path, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            if isinstance(obj, dict) and obj.get("record_uid"):
                records.append(obj)
    if bad:
        print("WARN: normalized.jsonl 有 %d 行非法已跳过（留痕）" % bad,
              file=sys.stderr)
    return records


def member_value(rec, field):
    """取成员记录的字段 (value, status)。authors 特殊处理。"""
    if field == "authors":
        st = (rec.get("field_status") or {}).get("authors", "not_provided")
        val = rec.get("authors_norm") or []
        return (val if val else None), st
    key, _ = REC_FIELD[field]
    val = rec.get(key)
    if field == "title":
        val = rec.get("title_raw")
    st = (rec.get("field_status") or {}).get(field, "not_provided")
    if val in (None, "", []):
        if st == "present":
            st = "unknown"
        return None, st
    return val, "present"


def aggregate_status(statuses):
    """聚合 missing/unknown/not_provided 语义。"""
    if any(s == "present" for s in statuses):
        return "present"
    if any(s == "unknown" for s in statuses):
        return "unknown"
    return "missing"


class UnionFind:
    def __init__(self, items):
        self.parent = {x: x for x in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def run(args):
    for p, what in ((args.normalized, "normalized.jsonl"),
                    (args.clusters, "clusters.json")):
        if not os.path.isfile(p):
            print("ERROR: %s 不存在（材料不足）: %s" % (what, p), file=sys.stderr)
            return 2
    try:
        records = load_jsonl(args.normalized)
        clusters_obj = load_json(args.clusters, "clusters.json")
    except ValueError:
        return 3
    except OSError as e:
        print("ERROR: 输入读取失败（校验失败）: %s" % e, file=sys.stderr)
        return 3
    if not records:
        print("ERROR: 无有效记录（材料不足，诚实降级）。", file=sys.stderr)
        return 2
    by_uid = {r["record_uid"]: r for r in records}

    # ---- 仲裁决议 ----
    arbitration_applied, arbitration_ignored = [], []
    pending_pairs = set()
    if args.arbitrations:
        if not os.path.isfile(args.arbitrations):
            print("ERROR: --arbitrations 文件不存在: %s" % args.arbitrations,
                  file=sys.stderr)
            return 2
        try:
            arb = load_json(args.arbitrations, "arbitrations.json")
        except ValueError:
            return 3
        entries = arb if isinstance(arb, list) else arb.get("decisions") or []
        for e in entries:
            if not isinstance(e, dict):
                continue
            pair = e.get("pair")
            if isinstance(pair, list) and len(pair) == 2:
                key = tuple(sorted(str(u) for u in pair))
                if e.get("decision") == "merge":
                    arbitration_applied.append(
                        {"pair": list(key), "decided_by": e.get("decided_by"),
                         "rationale": e.get("rationale")})
                elif e.get("decision") == "split":
                    arbitration_ignored.append(
                        {"pair": list(key), "decision": "split",
                         "rationale": e.get("rationale")})
                else:
                    pending_pairs.add(key)
    else:
        # 无仲裁文件：从 dedup 队列恢复 pending 标注
        if os.path.isfile(args.queue):
            try:
                q = load_json(args.queue, "arbitration_queue.json")
                for e in q.get("pending") or []:
                    if isinstance(e.get("pair"), list):
                        pending_pairs.add(tuple(sorted(e["pair"])))
            except ValueError:
                print("WARN: arbitration_queue.json 非法，pending 标注缺失",
                      file=sys.stderr)

    # ---- 应用仲裁 merge 决议到簇 ----
    uid_cluster = {}
    for c in clusters_obj.get("clusters") or []:
        for u in c.get("member_uids") or []:
            uid_cluster[u] = c["cluster_id"]
    uf = UnionFind(list(by_uid.keys()))
    for c in clusters_obj.get("clusters") or []:
        mem = [u for u in c.get("member_uids") or [] if u in by_uid]
        for u in mem[1:]:
            uf.union(mem[0], u)
    for a in arbitration_applied:
        x, y = a["pair"]
        if x in by_uid and y in by_uid:
            uf.union(x, y)
        else:
            arbitration_ignored.append({"pair": a["pair"],
                                        "decision": "merge",
                                        "rationale": "uid 不存在，决议无效"})
    groups = {}
    for u in by_uid:
        groups.setdefault(uf.find(u), []).append(u)
    cluster_list = sorted(groups.values(), key=lambda g: sorted(g)[0])

    # ---- 逐簇合并 ----
    canon_pre = []  # [(canon_dict, cluster_conflicts)]
    for members in cluster_list:
        conflicts = []
        muids = sorted(members)
        recs = sorted((by_uid[u] for u in muids),
                      key=lambda r: (prio(SOURCE_PRIORITY, r["source"]),
                                     r["record_uid"]))
        orig_cids = sorted({uid_cluster.get(u, "?") for u in muids})
        arb_status = "auto"
        member_set = set(muids)
        if any(set(a["pair"]) <= member_set for a in arbitration_applied):
            arb_status = "resolved_by_arbitration"
        elif any(set(q) & member_set for q in pending_pairs):
            # 有 pending 对触及本簇且未被仲裁消解
            arb_status = "pending_arbitration"

        canon = {"cluster_ids": orig_cids, "member_uids": muids,
                 "arbitration_status": arb_status,
                 "sources": sorted({r["source"] for r in recs}),
                 "identifiers": {}, "field_status": {},
                 "field_provenance": {}}

        # 标识符：任一来源提供即收录，全部来源留痕
        for fid in ("doi", "pmid", "pmcid"):
            offers = []
            for r in recs:
                ent = (r.get("identifiers") or {}).get(fid) or {}
                offers.append((r, ent.get("value"), ent.get("status",
                                                            "not_provided")))
            present = [(r, v) for r, v, st in offers if v]
            statuses = [st for _, _, st in offers]
            chosen = None
            if present:
                distinct = sorted({v for _, v in present})
                present.sort(key=lambda rv: (prio(SOURCE_PRIORITY,
                                                  rv[0]["source"]),
                                             rv[0]["record_uid"]))
                chosen = present[0]
                if len(distinct) > 1:
                    conflicts.append({
                        "field": fid,
                        "values_by_source": {r["source"]: sorted(
                            {v for rr, v in present
                             if rr["source"] == r["source"]})
                            for r, _ in present},
                        "chosen": {"value": chosen[1],
                                   "source": chosen[0]["source"]},
                        "rule": "identifier_priority",
                        "reason": "簇内出现多个不同 %s，按来源优先级取值，"
                                  "全部值已在 provenance 留痕；"
                                  "需人工复核是否误并" % fid})
            canon["identifiers"][fid] = {
                "value": chosen[1] if chosen else None,
                "status": aggregate_status(statuses)}
            canon["field_provenance"][fid] = {
                "value": chosen[1] if chosen else None,
                "source": chosen[0]["source"] if chosen else None,
                "raw_excerpt": chosen[0]["raw_excerpt"] if chosen else None,
                "all_sources": sorted({r["source"] for r, _ in present}),
                "not_provided_by": sorted({r["source"] for r, v, st in offers
                                           if st == "not_provided"}),
                "unknown_by": sorted({r["source"] for r, v, st in offers
                                      if st == "unknown"})}

        # 普通字段
        field_specs = [(f, SOURCE_PRIORITY) for f in BIB_FIELDS]
        field_specs.append(("abstract", ABSTRACT_PRIORITY))
        field_specs.append(("authors", AUTHORS_PRIORITY))
        for field, priority in field_specs:
            offers = [(r, *member_value(r, field)) for r in recs]
            present = [(r, v) for r, v, st in offers
                       if v not in (None, "", [])]
            statuses = [st for _, _, st in offers]
            canon["field_status"][field] = aggregate_status(statuses)
            chosen = None
            if present:
                def normv(v):
                    if isinstance(v, list):
                        return json.dumps(v, ensure_ascii=False, sort_keys=True)
                    return str(v)
                present.sort(key=lambda rv: (prio(priority, rv[0]["source"]),
                                             rv[0]["record_uid"]))
                chosen = present[0]
                distinct = {normv(v) for _, v in present}
                if len(distinct) > 1:
                    conflicts.append({
                        "field": field,
                        "values_by_source": {r["source"]: v
                                             for r, v in present},
                        "chosen": {"value": chosen[1],
                                   "source": chosen[0]["source"]},
                        "rule": "field_priority",
                        "reason": "多来源值不一致，按 %s 优先级取 %s"
                                  % (">".join(priority[:3]) + "...",
                                     chosen[0]["source"])})
            key = {"title": "title", "container": "container"}.get(field, field)
            canon[key] = chosen[1] if chosen else (
                [] if field == "authors" else None)
            canon["field_provenance"][field] = {
                "value": chosen[1] if chosen else None,
                "source": chosen[0]["source"] if chosen else None,
                "raw_excerpt": chosen[0]["raw_excerpt"] if chosen else None,
                "all_sources": sorted({r["source"] for r, v, st in offers
                                       if st == "present"}),
                "not_provided_by": sorted({r["source"] for r, v, st in offers
                                           if st == "not_provided"}),
                "unknown_by": sorted({r["source"] for r, v, st in offers
                                      if st == "unknown"})}
        # 确定性排序键：归一 DOI 或归一题名
        doi = canon["identifiers"]["doi"]["value"]
        tnorm = ""
        for r in recs:
            if r.get("title_norm"):
                tnorm = r["title_norm"]
                break
        canon["_sort_key"] = doi or tnorm
        canon_pre.append((canon, conflicts))

    # 确定性排序 + canonical_id 分配（排序后分配 id，同输入必得同输出）
    canon_pre.sort(key=lambda c: (c[0]["_sort_key"], c[0]["member_uids"][0]))
    out_records, canon_conflict = [], []
    for i, (canon, cl_conflicts) in enumerate(canon_pre, 1):
        cid = "W%03d" % i
        canon.pop("_sort_key", None)
        canon = dict([("canonical_id", cid)] +
                     [(k, v) for k, v in canon.items() if k != "canonical_id"])
        out_records.append(canon)
        for c in cl_conflicts:
            canon_conflict.append(dict([("canonical_id", cid),
                                        ("cluster_ids",
                                         canon["cluster_ids"])] + list(c.items())))

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    summary = {
        "input_records": len(records),
        "canonical_records": len(out_records),
        "clusters_auto": sum(1 for c in out_records
                             if c["arbitration_status"] == "auto"),
        "clusters_resolved_by_arbitration": sum(
            1 for c in out_records
            if c["arbitration_status"] == "resolved_by_arbitration"),
        "clusters_pending_arbitration": sum(
            1 for c in out_records
            if c["arbitration_status"] == "pending_arbitration"),
        "conflicts": len(canon_conflict),
        "arbitrations_applied": len(arbitration_applied),
        "arbitrations_rejected_or_split": len(arbitration_ignored),
        "sort_rule": "按 (归一 DOI 或 归一题名) 字典序升序；canonical_id 排序后分配",
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"records": out_records,
                   "arbitration_notes": {
                       "applied": arbitration_applied,
                       "rejected_or_split": arbitration_ignored,
                       "pending_pairs": sorted(list(pending_pairs))},
                   "summary": summary}, f, ensure_ascii=False, indent=2)
    cpath = args.conflicts
    os.makedirs(os.path.dirname(os.path.abspath(cpath)), exist_ok=True)
    with open(cpath, "w", encoding="utf-8") as f:
        for c in canon_conflict:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print("OK: 合并完成 -> %s (输入=%d, canonical=%d, 冲突=%d, 仲裁应用=%d, "
          "待仲裁簇=%d)" % (args.out, len(records), len(out_records),
                            len(canon_conflict), len(arbitration_applied),
                            summary["clusters_pending_arbitration"]))
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="簇合并 + 字段溯源 + 冲突日志 + 确定性排序（exit 0/2/3）。")
    ap.add_argument("--normalized", default="/app/work/normalized.jsonl")
    ap.add_argument("--clusters", default="/app/work/clusters.json")
    ap.add_argument("--arbitrations", default=None,
                    help="模型仲裁决议 JSON（可选）；缺省时 arbitrate 簇保持未决")
    ap.add_argument("--queue", default="/app/work/arbitration_queue.json",
                    help="dedup 仲裁队列（无 --arbitrations 时用于 pending 标注）")
    ap.add_argument("--out", default="/app/work/merged_records.json")
    ap.add_argument("--conflicts", default="/app/work/conflict_log.jsonl")
    args = ap.parse_args()
    try:
        return run(args)
    except Exception as e:
        print("ERROR: merge_records 未预期异常（降级 exit 2）: %r" % e,
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
