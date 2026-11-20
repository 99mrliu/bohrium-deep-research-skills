#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""exact_dedup.py — 保守精确去重：仅归一 DOI 精确 / 归一题名精确合并，并写台账。

用法:
    python3 exact_dedup.py [--work /app/work]

输入:  <work>/records.jsonl
输出:
    <work>/records_dedup.jsonl   去重后的待筛记录（保持原顺序）
    <work>/dedup_ledger.jsonl    每条合并 {kept, removed, match_key, basis}
    <work>/dedup_summary.json    {identified, duplicates_removed, screened, suspected_pairs[]}

规则:
    - 归一: NFKC + 小写 + 压缩空白；DOI 额外剥离 doi.org 前缀与尾部标点；
    - 完整身份解析/模糊去重不属本方向：疑似模糊重复（题名 token Jaccard>=0.8）
      只列入 suspected_pairs 供人工复核，绝不合并。

退出码: 0=成功, 2=用法或IO错误, 3=校验失败
"""
import argparse
import json
import re
import sys
import traceback
import unicodedata
from pathlib import Path


def eprint(*a):
    print(*a, file=sys.stderr)


def norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"\s+", " ", s).strip()


def norm_doi(s: str) -> str:
    s = norm_text(s)
    for pre in ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:"):
        if s.startswith(pre):
            s = s[len(pre):]
    return s.strip().rstrip(".").strip()


def title_tokens(s: str):
    return set(re.findall(r"[a-z0-9一-鿿]+", norm_text(s)))


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main():
    ap = argparse.ArgumentParser(description="保守精确去重（DOI/题名），疑似模糊重复仅列台账")
    ap.add_argument("--work", default="/app/work")
    args = ap.parse_args()
    work = Path(args.work)

    in_path = work / "records.jsonl"
    if not in_path.exists():
        eprint(f"[exact_dedup] 缺少 {in_path}，请先运行 load_records.py")
        return 2
    records = load_jsonl(in_path)

    kept, ledger = [], []
    seen_doi, seen_title = {}, {}
    for rec in records:
        nd, nt = norm_doi(rec.get("doi", "")), norm_text(rec.get("title", ""))
        dup_of, key, basis = None, None, None
        if nd and nd in seen_doi:
            dup_of, key, basis = seen_doi[nd], f"doi:{nd}", "doi_exact"
        elif nt and nt in seen_title:
            dup_of, key, basis = seen_title[nt], f"title:{nt[:80]}", "title_exact"
        if dup_of:
            ledger.append({"kept": dup_of, "removed": rec["record_id"],
                           "match_key": key, "basis": basis})
            continue
        kept.append(rec)
        if nd:
            seen_doi.setdefault(nd, rec["record_id"])
        if nt:
            seen_title.setdefault(nt, rec["record_id"])

    removed_ids = {l["removed"] for l in ledger}
    # 疑似模糊重复：仅在保留集中两两比较，不合并
    suspected = []
    toks = [title_tokens(r.get("title", "")) for r in kept]
    for i in range(len(kept)):
        for j in range(i + 1, len(kept)):
            sim = jaccard(toks[i], toks[j])
            if sim >= 0.8:
                suspected.append({
                    "pair": [kept[i]["record_id"], kept[j]["record_id"]],
                    "title_jaccard": round(sim, 3),
                    "note": "疑似模糊重复，未合并，需人工复核确认",
                })

    with (work / "records_dedup.jsonl").open("w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (work / "dedup_ledger.jsonl").open("w", encoding="utf-8") as f:
        for l in ledger:
            f.write(json.dumps(l, ensure_ascii=False) + "\n")
    summary = {
        "identified": len(records),
        "duplicates_removed": len(ledger),
        "removed_ids": sorted(removed_ids),
        "screened": len(kept),
        "suspected_pairs": suspected,
        "policy": "仅 DOI/题名归一精确合并；模糊疑似仅列出不合并（身份解析不属本方向）",
    }
    (work / "dedup_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[exact_dedup] identified={len(records)} removed={len(ledger)} "
          f"screened={len(kept)} suspected={len(suspected)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        eprint("[exact_dedup] 未捕获异常:")
        traceback.print_exc()
        sys.exit(2)
