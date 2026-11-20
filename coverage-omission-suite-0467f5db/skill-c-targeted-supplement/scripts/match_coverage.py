#!/usr/bin/env python3
"""match_coverage.py — 初始覆盖测量：标识符归一化匹配 + 标题相似度匹配 + Wilson 区间。

分母一律来自冻结参考集 refset.json；绝不从检索结果推导分母。
匹配规则（固定顺序，确定性）：
  1) DOI 归一化精确匹配（小写、去 https://doi.org/ 与 doi: 前缀）
  2) PMID 归一化精确匹配（数字串）
  3) 规范化标题相似度：difflib.SequenceMatcher 比率 ≥ 阈值（默认 0.90）
  4) 得分落在边界带 [threshold, threshold+0.05) 的命中标记为 borderline，
     供审计协议 100% 复核。

仅使用 Python 标准库。支持 --help。
退出码：0 正常；2 材料不足；3 校验失败。
"""
import argparse
import difflib
import hashlib
import json
import math
import os
import re
import sys

EXIT_OK = 0
EXIT_INSUFFICIENT = 2
EXIT_VALIDATION = 3

DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def norm_doi(value):
    if not isinstance(value, str) or not value.strip():
        return None
    v = DOI_PREFIX_RE.sub("", value.strip()).strip().lower()
    return v or None


def norm_pmid(value):
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    return digits or None


def norm_title(value):
    if not isinstance(value, str) or not value.strip():
        return None
    v = NON_ALNUM_RE.sub(" ", value.lower())
    v = re.sub(r"\s+", " ", v).strip()
    return v or None


def _first_key(rec, candidates):
    lower = {k.lower(): v for k, v in rec.items()}
    for key in candidates:
        if key in lower and lower[key] not in (None, "", []):
            return lower[key]
    return None


def doi_of(rec):
    v = _first_key(rec, ("doi",))
    if isinstance(v, list):
        v = v[0] if v else None
    return norm_doi(v)


def pmid_of(rec):
    v = _first_key(rec, ("pmid", "pmid_link", "pubmed_id"))
    return norm_pmid(v)


def title_of(rec):
    v = _first_key(rec, ("title", "article_title"))
    if isinstance(v, list):
        v = v[0] if v else None
    return v if isinstance(v, str) and v.strip() else None


def year_of(rec):
    v = _first_key(rec, ("year", "pub_year", "publication_year", "published_year", "date"))
    if isinstance(v, dict):  # crossref 风格 {"date-parts": [[2021]]}
        parts = v.get("date-parts")
        if parts and parts[0]:
            return str(parts[0][0])
    if v is None:
        return None
    m = re.search(r"(19|20)\d{2}", str(v))
    return m.group(0) if m else None


def first_author_surname(rec):
    authors = _first_key(rec, ("authors", "author", "creator"))
    if isinstance(authors, str):
        # 形如 "Surname, X Y; Surname2, Z" 或 "X Y Surname"
        first = re.split(r";| and ", authors)[0].strip()
        if "," in first:
            return first.split(",")[0].strip().lower() or None
        parts = first.split()
        return parts[-1].lower() if parts else None
    if isinstance(authors, list) and authors:
        a0 = authors[0]
        if isinstance(a0, dict):
            fam = _first_key(a0, ("family", "surname", "lastname", "last_name"))
            if fam:
                return str(fam).strip().lower() or None
        elif isinstance(a0, str):
            if "," in a0:
                return a0.split(",")[0].strip().lower() or None
            parts = a0.split()
            return parts[-1].lower() if parts else None
    return None


def iter_records(obj):
    """深度优先遍历任意嵌套 JSON，产出含 title 字段的记录字典（确定性顺序）。"""
    if isinstance(obj, dict):
        keys = [k for k in obj if k.lower() == "title"]
        if keys:
            yield obj
        for key in sorted(obj.keys()):
            for rec in iter_records(obj[key]):
                yield rec
    elif isinstance(obj, list):
        for item in obj:
            for rec in iter_records(item):
                yield rec


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_records_from_paths(paths):
    """从 JSON / JSONL 文件载入候选记录；返回 [(path, record_dict)]。"""
    out = []
    for path in paths:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        try:
            obj = json.loads(text)
            for rec in iter_records(obj):
                out.append((path, rec))
            continue
        except json.JSONDecodeError:
            pass
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict):
                for r in iter_records(rec):
                    out.append((path, r))
    return out


def match_record(ref, rec, threshold=0.90, band=0.05):
    """单条参考与单条候选的匹配判定。返回 (status, method, score)。
    status ∈ {matched, borderline, none}。"""
    rd, cd = norm_doi(ref.get("doi")), doi_of(rec)
    if rd and cd:
        if rd == cd:
            return "matched", "doi", 1.0
        return "none", "doi_conflict", 0.0
    rp, cp = norm_pmid(ref.get("pmid")), pmid_of(rec)
    if rp and cp:
        if rp == cp:
            return "matched", "pmid", 1.0
        return "none", "pmid_conflict", 0.0
    rt, ct = norm_title(ref.get("title")), norm_title(title_of(rec))
    if rt and ct:
        score = difflib.SequenceMatcher(None, rt, ct).ratio()
        if score >= threshold + band:
            return "matched", "title_sim", round(score, 4)
        if score >= threshold:
            return "borderline", "title_sim", round(score, 4)
    return "none", None, 0.0


def wilson_ci(k, n, z=1.959964):
    """Wilson 得分区间（95%）；n=0 时返回 (None, None) 并显式记录。"""
    if n <= 0:
        return None, None
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return round(max(0.0, center - half), 6), round(min(1.0, center + half), 6)


def compute_coverage(refset, candidate_pairs, threshold=0.90, band=0.05):
    """candidate_pairs: [(path, record)]。对每条 ref 取首个（确定性）匹配候选。"""
    matches = []
    covered, missed = [], []
    for ref in refset:
        best = ("none", None, 0.0, None, None)
        for idx, (path, rec) in enumerate(candidate_pairs):
            status, method, score = match_record(ref, rec, threshold, band)
            if status in ("matched", "borderline"):
                best = (status, method, score, idx, path)
                break
        entry = {
            "ref_id": ref.get("ref_id"),
            "status": best[0],
            "method": best[1],
            "score": best[2],
            "candidate_index": best[3],
            "candidate_source": best[4],
        }
        if best[3] is not None:
            rec = candidate_pairs[best[3]][1]
            entry["candidate_evidence"] = {
                "doi": doi_of(rec),
                "pmid": pmid_of(rec),
                "title": title_of(rec),
            }
        matches.append(entry)
        if best[0] in ("matched", "borderline"):
            covered.append(ref.get("ref_id"))
        else:
            missed.append(ref.get("ref_id"))
    n = len(refset)
    k = len(covered)
    low, high = wilson_ci(k, n)
    return {
        "denominator": n,
        "covered": k,
        "coverage": round(k / n, 6) if n else None,
        "wilson_ci": {"low": low, "high": high, "z": 1.959964},
        "covered_ids": covered,
        "missed_ids": missed,
        "matches": matches,
    }


def result_hash(obj):
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="以冻结参考集为分母计算覆盖率（标识符匹配 + 标题相似度 + Wilson 区间）。"
    )
    ap.add_argument("--refset", required=True, help="freeze_refset.py 产出的 refset.json")
    ap.add_argument("--retrieved", nargs="+", required=True,
                    help="候选记录来源：JSON/JSONL 文件路径（可多份）")
    ap.add_argument("--out", required=True, help="覆盖测量输出 JSON 路径")
    ap.add_argument("--threshold", type=float, default=0.90, help="标题相似度阈值（默认 0.90）")
    ap.add_argument("--band", type=float, default=0.05, help="边界带宽度（默认 0.05）")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.refset):
        print("[match_coverage] 冻结参考集缺失：%s" % args.refset, file=sys.stderr)
        return EXIT_INSUFFICIENT
    refset_obj = load_json(args.refset)
    refs = refset_obj.get("references", [])
    if not refs:
        print("[match_coverage] 冻结参考集为空，无法计算覆盖率", file=sys.stderr)
        return EXIT_INSUFFICIENT

    missing = [p for p in args.retrieved if not os.path.isfile(p)]
    candidates = load_records_from_paths(args.retrieved)
    coverage = compute_coverage(refs, candidates, args.threshold, args.band)
    coverage.update({
        "refset_hash": refset_obj.get("refset_hash"),
        "threshold": args.threshold,
        "band": args.band,
        "candidate_files": [os.path.abspath(p) for p in args.retrieved if os.path.isfile(p)],
        "candidate_records": len(candidates),
        "missing_candidate_files": missing,
        "status": "partial" if missing else "ok",
        "coverage_hash": result_hash({
            "refset_hash": refset_obj.get("refset_hash"),
            "covered_ids": coverage["covered_ids"],
            "missed_ids": coverage["missed_ids"],
        }),
    })
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(coverage, fh, ensure_ascii=False, indent=2)
    print("[match_coverage] 分母=%d 覆盖=%d 覆盖率=%s 漏检=%d -> %s"
          % (coverage["denominator"], coverage["covered"], coverage["coverage"],
             len(coverage["missed_ids"]), args.out))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
