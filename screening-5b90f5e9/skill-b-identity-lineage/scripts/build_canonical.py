#!/usr/bin/env python3
"""build_canonical.py - 簇 → canonical 记录：确定性字段级合并 + 版本谱系链。

规则（详见 rules/version_chain.md）:
  - 角色识别: 有 arXiv 无 DOI 或 venue 含 arxiv → preprint；有 DOI → published；否则 unknown。
  - canonical 选取: published 优先于 unknown 优先于 preprint；同级比有无 DOI、摘要长度、record_id。
  - 字段合并: 题名/作者/年份/DOI/venue 取 canonical 副本；摘要取最长者；
    arXiv/PMID 优先 canonical 副本、缺失则取任一副本。
  - 每字段记 provenance（来源文件 + 记录序号）。
  - 字段值冲突（年份/DOI/venue/原始题名不一致）全量写 conflict_log.jsonl。
  - version_chain 完整保留全部副本，不丢弃任何记录。

退出码: 0=成功; 2=输入缺失; 3=失败。
"""
import argparse
import json
import sys
from pathlib import Path

MERGE_FIELDS = ["title", "abstract", "authors", "year", "doi", "pmid", "arxiv", "venue"]
CONFLICT_FIELDS = ["title", "year", "doi", "venue"]


def classify_role(rec):
    venue = (rec.get("venue") or "").lower()
    if (rec.get("arxiv") and not rec.get("doi")) or "arxiv" in venue:
        return "preprint"
    if rec.get("doi"):
        return "published"
    return "unknown"


def canon_rank(rec):
    role_rank = {"published": 0, "unknown": 1, "preprint": 2}
    return (role_rank[classify_role(rec)],
            0 if rec.get("doi") else 1,
            -len(rec.get("abstract") or ""),
            rec["record_id"])


def pick_field(field, members, canon):
    """返回 (value, provenance_record)。确定性策略。"""
    if field == "abstract":
        best = max(members, key=lambda r: (len(r.get("abstract") or ""),
                                           tuple(reversed(r["record_id"]))))
        # 摘要最长者优先；完全等长时取 record_id 较小者（确定性）
        best = min([m for m in members
                    if len(m.get("abstract") or "") == len(best.get("abstract") or "")],
                   key=lambda r: r["record_id"])
        return best.get("abstract"), best
    # 其余字段：canonical 副本优先，缺失则按 rank 顺序取第一个有值者
    if canon.get(field):
        return canon[field], canon
    for r in sorted(members, key=canon_rank):
        if r.get(field):
            return r[field], r
    return ([] if field == "authors" else None), canon


def main() -> int:
    ap = argparse.ArgumentParser(description="簇 → canonical 记录（字段级合并+谱系）")
    ap.add_argument("--work", default="/app/work", help="工作目录 (默认 /app/work)")
    args = ap.parse_args()
    work = Path(args.work)

    clusters_path = work / "clusters.final.json"
    recs_path = work / "records.jsonl"
    if not clusters_path.exists():
        clusters_path = work / "clusters.json"
    if not clusters_path.exists() or not recs_path.exists():
        print(json.dumps({"ok": False, "exit": 2,
                          "reason": "缺少 clusters(.final).json 或 records.jsonl"},
                         ensure_ascii=False))
        return 2

    records = {}
    for line in recs_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            records[r["record_id"]] = r
    clusters = json.loads(clusters_path.read_text(encoding="utf-8"))["clusters"]

    canonical_records, conflict_log = [], []
    for idx, c in enumerate(clusters, 1):
        members = [records[m] for m in c["members"] if m in records]
        if not members:
            continue
        canon = sorted(members, key=canon_rank)[0]
        roles = {m["record_id"]: classify_role(m) for m in members}

        merged, provenance = {}, {}
        for field in MERGE_FIELDS:
            val, src = pick_field(field, members, canon)
            merged[field] = val
            provenance[field] = {"record_id": src["record_id"],
                                 "source_file": src.get("source_file"),
                                 "source_index": src.get("source_index")}
        # 字段冲突全量记录
        for field in CONFLICT_FIELDS:
            vals = {}
            for m in members:
                v = m.get(field)
                if v:
                    vals.setdefault(str(v), []).append(m["record_id"])
            if len(vals) > 1:
                conflict_log.append({
                    "cluster_id": c["cluster_id"], "field": field,
                    "values": [{"value": v, "record_ids": ids} for v, ids in vals.items()],
                    "resolution": {"chosen": merged.get(field),
                                   "rule": "canonical 副本字段优先（published>unknown>preprint）"
                                   if field != "abstract" else "最长摘要优先"}})

        version_chain = {
            "roles": roles,
            "canonical_record_id": canon["record_id"],
            "copies": sorted(m["record_id"] for m in members
                             if m["record_id"] != canon["record_id"]),
            "has_preprint": any(r == "preprint" for r in roles.values()),
            "has_published": any(r == "published" for r in roles.values()),
        }
        canonical_records.append({
            "canonical_id": f"can-{idx:03d}",
            "cluster_id": c["cluster_id"],
            "members": sorted(m["record_id"] for m in members),
            "canonical_record_id": canon["record_id"],
            "version_chain": version_chain,
            "fields": merged,
            "provenance": provenance,
            "merge_evidence": c.get("merge_evidence", []),
            "screen_text": {"title": merged.get("title"),
                            "abstract": merged.get("abstract")},
        })

    (work / "canonical_records.json").write_text(json.dumps(
        {"canonical_records": canonical_records,
         "stats": {"canonical": len(canonical_records),
                   "multi_copy_clusters": sum(1 for c in canonical_records
                                              if len(c["members"]) > 1),
                   "conflicts": len(conflict_log)}},
        ensure_ascii=False, indent=2), encoding="utf-8")
    (work / "conflict_log.jsonl").write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in conflict_log),
        encoding="utf-8")
    print(json.dumps({"ok": True, "canonical": len(canonical_records),
                      "conflicts": len(conflict_log)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(3)
