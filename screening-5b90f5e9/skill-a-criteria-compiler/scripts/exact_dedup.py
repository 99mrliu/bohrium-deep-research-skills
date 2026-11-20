#!/usr/bin/env python3
"""exact_dedup.py — 保守精确去重（步骤 4，脚本环节）。

仅两种精确合并键（刻意保守，模糊去重不属于本方向）：
  1) 归一 DOI 精确相同（小写、去 https://doi.org/ 等前缀、去空白）；
  2) 归一题名精确相同（NFKC、小写、去标点、压缩空白）。
合并为同一 study_group，保留全部副本记录与来源，写 dedup_ledger.jsonl。
疑似模糊重复（题名 token Jaccard >= 0.7 但标识符不同）只列入
suspected_pairs，不合并、记入 uncertainty。

退出码：0=通过；2=输入不足；3=校验失败。幂等：重跑覆盖同名产物。
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

WS_RE = re.compile(r"\s+")
DOI_PREFIX_RE = re.compile(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", re.I)
JACCARD_THRESHOLD = 0.7
MAX_PAIRWISE = 3000  # 超过则跳过疑似对计算（防爆），并留 note


def norm_doi(doi):
    if not doi:
        return ""
    d = WS_RE.sub("", str(doi).strip().lower())
    d = DOI_PREFIX_RE.sub("", d)
    return d.rstrip(".")


def norm_title(title):
    if not title:
        return ""
    t = unicodedata.normalize("NFKC", str(title)).lower()
    t = "".join(" " if unicodedata.category(ch).startswith("P") else ch for ch in t)
    return WS_RE.sub(" ", t).strip()


def jaccard(a, b):
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def main(argv=None):
    ap = argparse.ArgumentParser(description="保守精确去重，写 dedup_ledger.jsonl")
    ap.add_argument("--work", default="/app/work", help="工作目录（默认 /app/work）")
    args = ap.parse_args(argv)
    work = Path(args.work)
    norm_path = work / "normalized.jsonl"
    if not norm_path.exists():
        print(f"[exact_dedup] 缺少 {norm_path}，请先运行 normalize_records.py。", file=sys.stderr)
        return 2
    try:
        records = [json.loads(l) for l in norm_path.read_text(encoding="utf-8").splitlines()
                   if l.strip()]
    except Exception as e:
        print(f"[exact_dedup] normalized.jsonl 解析失败: {e}", file=sys.stderr)
        return 2
    if not records:
        print("[exact_dedup] 记录为零，输入不足，诚实降级。", file=sys.stderr)
        return 2

    groups = []  # 每项: {group_id, match_key, members:[record...]}
    key_to_group = {}
    for rec in records:
        doi_key = norm_doi(rec.get("doi"))
        title_key = norm_title(rec.get("title"))
        key = f"doi:{doi_key}" if doi_key else (f"title:{title_key}" if title_key else None)
        if key and key in key_to_group:
            groups[key_to_group[key]]["members"].append(rec)
        else:
            gid = f"G{len(groups) + 1:04d}"
            if key:
                key_to_group[key] = len(groups)
            groups.append({"group_id": gid, "match_key": key or "none", "members": [rec]})

    ledger_path = work / "dedup_ledger.jsonl"
    with ledger_path.open("w", encoding="utf-8") as out:
        for g in groups:
            members = g["members"]
            canonical = members[0]
            entry = {
                "group_id": g["group_id"],
                "action": "merge_exact" if len(members) > 1 else "keep",
                "match_key": g["match_key"],
                "evidence": {
                    "matched_on": g["match_key"].split(":", 1)[0] if g["match_key"] != "none" else None,
                    "key_value": g["match_key"].split(":", 1)[1] if g["match_key"] != "none" else None,
                },
                "canonical_record_id": canonical["record_id"],
                "member_record_ids": [m["record_id"] for m in members],
                "member_sources": [
                    {"record_id": m["record_id"], "source_file": m["source_file"],
                     "source_index": m["source_index"]} for m in members],
            }
            out.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # 疑似模糊重复：只列不合并
    suspected = []
    note = ""
    norm_titles = []
    for g in groups:
        c = g["members"][0]
        norm_titles.append((g["group_id"], c["record_id"], norm_title(c.get("title")),
                            norm_doi(c.get("doi"))))
    if len(norm_titles) > MAX_PAIRWISE:
        note = f"组数 {len(norm_titles)} 超过 {MAX_PAIRWISE}，跳过疑似对计算"
    else:
        for i in range(len(norm_titles)):
            for j in range(i + 1, len(norm_titles)):
                ga, ra, ta, da = norm_titles[i]
                gb, rb, tb, db = norm_titles[j]
                if not ta or not tb:
                    continue
                sim = jaccard(ta, tb)
                if sim >= JACCARD_THRESHOLD and da != db:
                    suspected.append({
                        "group_id_a": ga, "record_id_a": ra,
                        "group_id_b": gb, "record_id_b": rb,
                        "title_jaccard": round(sim, 4),
                        "action": "not_merged_conservative",
                    })

    identified = len(records)
    groups_count = len(groups)
    summary = {
        "identified": identified,
        "groups": groups_count,
        "duplicates_removed": identified - groups_count,
        "suspected_pairs": suspected,
        "suspected_pairs_note": note,
        "policy": "仅归一 DOI/归一题名精确匹配合并；疑似模糊重复不合并",
        "ledger": str(ledger_path),
        "generated_by": "exact_dedup.py",
        "stage": "dedup",
    }
    (work / "dedup_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[exact_dedup] identified={identified} groups={groups_count} "
          f"duplicates_removed={identified - groups_count} suspected={len(suspected)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print(f"[exact_dedup] 未预期错误（诚实降级）: {e}", file=sys.stderr)
        sys.exit(2)
