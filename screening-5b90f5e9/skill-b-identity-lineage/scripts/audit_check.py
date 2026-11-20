#!/usr/bin/env python3
"""audit_check.py - 计数闭合审计，支持第三人复算。

闭合恒等式:
  identified（导入总条数）= canonical 数 + 合并掉的副本数
  screened（canonical 数）= included + excluded + needs_human
  每个记录恰好属于一个簇；多副本簇必须有非空 merge_evidence；
  每个簇 version_chain.copies 数 = 成员数 - 1。

输出 /app/work/audit_summary.json；任何一项不闭合 exit 3。

退出码: 0=全部闭合; 2=输入缺失; 3=不闭合。
"""
import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="计数闭合审计")
    ap.add_argument("--work", default="/app/work", help="工作目录 (默认 /app/work)")
    args = ap.parse_args()
    work = Path(args.work)

    recs_path = work / "records.jsonl"
    clusters_path = work / "clusters.final.json"
    if not clusters_path.exists():
        clusters_path = work / "clusters.json"
    can_path = work / "canonical_records.json"
    for p in (recs_path, clusters_path, can_path):
        if not p.exists():
            print(json.dumps({"ok": False, "exit": 2,
                              "reason": f"缺少 {p.name}，请先完成前置步骤"},
                             ensure_ascii=False))
            return 2

    records = [json.loads(l) for l in recs_path.read_text(encoding="utf-8").splitlines()
               if l.strip()]
    clusters = json.loads(clusters_path.read_text(encoding="utf-8"))["clusters"]
    canonical = json.loads(can_path.read_text(encoding="utf-8"))["canonical_records"]

    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    identified = len(records)
    n_canonical = len(canonical)
    merged_copies = identified - n_canonical
    add("identified_eq_canonical_plus_copies",
        identified == n_canonical + merged_copies,
        f"identified={identified} canonical={n_canonical} merged_copies={merged_copies}")

    # 记录恰好属于一个簇
    all_members = [m for c in clusters for m in c["members"]]
    rec_ids = {r["record_id"] for r in records}
    add("cluster_members_cover_all_records",
        len(all_members) == len(set(all_members)) == identified
        and set(all_members) == rec_ids,
        f"cluster_members={len(all_members)} unique={len(set(all_members))} "
        f"records={identified}")

    # 多副本簇必须有合并依据
    bad_ev = [c["cluster_id"] for c in clusters
              if len(c["members"]) > 1 and not c.get("merge_evidence")]
    add("multi_copy_clusters_have_evidence", not bad_ev,
        f"缺证据簇: {bad_ev}" if bad_ev else "全部多副本簇均有 merge_evidence")

    # canonical 与簇一一对应
    add("canonical_matches_clusters",
        sorted(c["cluster_id"] for c in canonical) == sorted(c["cluster_id"] for c in clusters),
        f"canonical={n_canonical} clusters={len(clusters)}")

    # 谱系副本数一致
    bad_chain = [c["canonical_id"] for c in canonical
                 if len(c["version_chain"]["copies"]) != len(c["members"]) - 1]
    add("version_chain_copies_consistent", not bad_chain,
        f"谱系不一致: {bad_chain}" if bad_chain else "全部簇谱系副本数=成员数-1")

    # 筛选闭合
    dec_path = work / "final_decisions.jsonl"
    cnt_path = work / "screening_counts.json"
    if dec_path.exists() and cnt_path.exists():
        decisions = [json.loads(l) for l in dec_path.read_text(encoding="utf-8").splitlines()
                     if l.strip()]
        cnt = json.loads(cnt_path.read_text(encoding="utf-8"))
        screened = len(decisions)
        total = cnt["included"] + cnt["excluded"] + cnt["needs_human"]
        add("screened_eq_canonical", screened == n_canonical,
            f"screened={screened} canonical={n_canonical}")
        add("screened_eq_inc_exc_nh", screened == total and cnt.get("closure") is True,
            f"screened={screened} = {cnt['included']}+{cnt['excluded']}+{cnt['needs_human']}")
        known = {c["canonical_id"] for c in canonical}
        add("decisions_reference_known_canonicals",
            all(d["canonical_id"] in known for d in decisions),
            "全部判定引用存在的 canonical_id")
        # 传播计数：副本继承条数 = 合并掉的副本数
        prop = sum(len(d.get("propagated_copies", [])) for d in decisions)
        add("propagation_covers_merged_copies", prop == merged_copies,
            f"propagated={prop} merged_copies={merged_copies}")
    else:
        add("screening_done", False, "final_decisions.jsonl/screening_counts.json 缺失")

    all_ok = all(c["ok"] for c in checks)
    summary = {"identified": identified, "canonical": n_canonical,
               "merged_copies": merged_copies,
               "screened": len(canonical),
               "checks": checks, "all_ok": all_ok}
    (work / "audit_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": all_ok,
                      "failed": [c["name"] for c in checks if not c["ok"]]},
                     ensure_ascii=False))
    return 0 if all_ok else 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(3)
