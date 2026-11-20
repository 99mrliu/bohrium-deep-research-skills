#!/usr/bin/env python3
"""adjudicate.py — 三级命中判定（L1 标识符精确命中 / L2 题录近似命中 / L3 裁决队列）。

对「参考集条目 × 检索记录中的每个查询 × 来源」逐单元判定，输出：
  work/adjudication.json        全部单元的判定结果（含分数、位次、证据）
  work/adjudication_queue.json  L3 裁决队列（临界对与标识符冲突对）

判定口径（与 references/match_rules.md 一致）：
  L1: 归一化 DOI / PMID / arXiv 任一相等，score=1.0。
  L2: 标题 token F1 >= 0.6 且第一作者姓氏相等且年份差 <= 1，score 记录实际 F1。
  L3: token F1 在 [0.5, 0.6) 的临界对，或标识符冲突对；进入队列，未裁决计 ambiguous。

用法:
  python3 adjudicate.py --work /app/work [--decisions decisions.json] [--case /input/case.json]

退出码: 0 成功; 2 材料不足; 3 校验失败。
仅使用 Python 3 标准库。
"""
import argparse
import json
import os
import re
import sys
import unicodedata

L2_F1_THRESHOLD = 0.6
L3_F1_LOW = 0.5
L3_F1_HIGH = 0.6
YEAR_TOLERANCE = 1

# ---------------------------------------------------------------------------
# 归一化函数（本模块为唯一权威实现，attribute_miss.py / supplement_eval.py 直接导入）
# ---------------------------------------------------------------------------

_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "http://dx.doi.org/",
                 "https://dx.doi.org/", "doi:")


def norm_doi(value):
    """归一化 DOI：小写、去前缀、去空白。无法归一化返回 None。"""
    if not value:
        return None
    s = str(value).strip().lower()
    for p in _DOI_PREFIXES:
        if s.startswith(p):
            s = s[len(p):]
            break
    s = s.strip().rstrip(".")
    return s or None


def norm_pmid(value):
    """归一化 PMID：仅保留数字。"""
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    return digits or None


def norm_arxiv(value):
    """归一化 arXiv 标识：去 arXiv: 前缀、小写、去版本后缀 vN。"""
    if not value:
        return None
    s = str(value).strip().lower()
    if s.startswith("arxiv:"):
        s = s[len("arxiv:"):]
    s = re.sub(r"v\d+$", "", s)
    return s or None


def strip_accents(text):
    """去除重音符号（NFKD 分解后剔除组合字符）。"""
    return "".join(c for c in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(c))


def title_tokens(title):
    """标题归一化分词：小写、去重音、去标点、按空白切分，返回 token 集合。"""
    if not title:
        return set()
    s = strip_accents(str(title).lower())
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return set(t for t in s.split() if t)


def norm_surname(name):
    """归一化姓氏：小写、去重音、仅保留字母。支持 'Zhang, Wei' 与 'Wei Zhang' 两种写法。"""
    if not name:
        return None
    s = strip_accents(str(name).strip())
    if "," in s:
        s = s.split(",", 1)[0]
    else:
        parts = s.split()
        s = parts[-1] if parts else s
    s = re.sub(r"[^a-z]", "", s.lower())
    return s or None


def first_author_surname(record):
    """从记录提取第一作者姓氏；支持 authors 列表（字符串或 {name/family} 字典）或 author 字符串。"""
    authors = record.get("authors")
    first = None
    if isinstance(authors, list) and authors:
        a0 = authors[0]
        if isinstance(a0, dict):
            first = a0.get("family") or a0.get("name")
        else:
            first = a0
    elif isinstance(record.get("author"), str):
        first = record["author"].split(";")[0].strip()
    return norm_surname(first)


def get_year(record):
    """提取整数年份；失败返回 None。"""
    for key in ("year", "published_year", "pubyear"):
        v = record.get(key)
        if v is None:
            continue
        m = re.search(r"(\d{4})", str(v))
        if m:
            return int(m.group(1))
    for key in ("published", "date", "issued"):
        v = record.get(key)
        if v:
            m = re.search(r"(\d{4})", str(v))
            if m:
                return int(m.group(1))
    return None


def token_f1(tokens_a, tokens_b):
    """token 集合 F1 = 2|A∩B| / (|A|+|B|)；两边均空返回 0.0。"""
    if not tokens_a or not tokens_b:
        return 0.0
    inter = len(tokens_a & tokens_b)
    return 2.0 * inter / (len(tokens_a) + len(tokens_b))


def record_ids(record):
    """提取记录的归一化标识符字典。"""
    ids = record.get("ids") if isinstance(record.get("ids"), dict) else {}
    return {
        "doi": norm_doi(record.get("doi") or ids.get("doi")),
        "pmid": norm_pmid(record.get("pmid") or ids.get("pmid")),
        "arxiv": norm_arxiv(record.get("arxiv") or ids.get("arxiv")),
    }


# ---------------------------------------------------------------------------
# 判定核心
# ---------------------------------------------------------------------------

def match_pair(ref, rec):
    """判定单条参考记录 ref 与单条检索结果记录 rec 的匹配关系。

    返回 dict: {level, score, status, reason}
      level: 'L1' | 'L2' | 'L3' | None
      status: 'hit' | 'ambiguous' | 'miss'
    """
    ref_ids = record_ids(ref)
    rec_ids = record_ids(rec)

    # 标识符冲突检测：相同类型的键两边都有值但不相等 —— 不算冲突（可能多标识）；
    # 冲突定义：某一非空标识符两边相等，但归一化标题完全不同（F1 < 0.3）→ 标识符冲突对。
    id_equal_keys = [k for k in ("doi", "pmid", "arxiv")
                     if ref_ids.get(k) and rec_ids.get(k) and ref_ids[k] == rec_ids[k]]
    ref_toks = title_tokens(ref.get("title"))
    rec_toks = title_tokens(rec.get("title"))
    f1 = token_f1(ref_toks, rec_toks)

    if id_equal_keys:
        if f1 < 0.3 and ref_toks and rec_toks:
            return {"level": "L3", "score": round(f1, 4), "status": "ambiguous",
                    "reason": "identifier_conflict: %s 相等但标题 F1=%.3f < 0.3" % (id_equal_keys[0], f1)}
        return {"level": "L1", "score": 1.0, "status": "hit",
                "reason": "identifier_equal: %s" % id_equal_keys[0]}

    ref_surname = first_author_surname(ref)
    rec_surname = first_author_surname(rec)
    ref_year = get_year(ref)
    rec_year = get_year(rec)

    surname_ok = bool(ref_surname and rec_surname and ref_surname == rec_surname)
    if ref_year is None or rec_year is None:
        year_ok = None  # 无法核验
    else:
        year_ok = abs(ref_year - rec_year) <= YEAR_TOLERANCE

    if f1 >= L2_F1_THRESHOLD and surname_ok and year_ok is True:
        return {"level": "L2", "score": round(f1, 4), "status": "hit",
                "reason": "bibliographic_match: f1=%.3f, surname=%s, year_diff_ok" % (f1, ref_surname)}

    # L3 临界：F1 在 [0.5, 0.6) 且姓氏相等且年份可核验通过
    if L3_F1_LOW <= f1 < L3_F1_HIGH and surname_ok and year_ok is True:
        return {"level": "L3", "score": round(f1, 4), "status": "ambiguous",
                "reason": "borderline_f1: %.3f in [0.5, 0.6), needs adjudication" % f1}

    # L3：F1 达标但年份或作者缺失无法核验
    if f1 >= L2_F1_THRESHOLD and surname_ok and year_ok is None:
        return {"level": "L3", "score": round(f1, 4), "status": "ambiguous",
                "reason": "year_unverifiable: f1=%.3f but year missing on one side" % f1}

    return {"level": None, "score": round(f1, 4), "status": "miss", "reason": "no_match"}


def make_cell_key(query):
    return "%s|%s|%s" % (query.get("query_id", "?"), query.get("source", "?"),
                         query.get("executed_at", "?"))


def adjudicate(reference_set, queries, results_by_file, decisions=None):
    """对全部 (ref × query) 单元执行判定。

    reference_set: list[dict]，需含 ref_id。
    queries: list[dict]，需含 query_id, source, executed_at, results_file。
    results_by_file: {results_file: [record, ...]}。
    decisions: {queue_key: "accept"|"reject"}，可选，用于回灌 L3 裁决。
    返回 (cells, queue)。
    """
    decisions = decisions or {}
    cells = []
    queue = []
    for ref in reference_set:
        for q in queries:
            key = make_cell_key(q)
            records = results_by_file.get(q.get("results_file"), [])
            best = None  # 该单元内取最优候选
            best_rank = None
            for idx, rec in enumerate(records):
                r = match_pair(ref, rec)
                if r["status"] == "miss":
                    continue
                if best is None or r["score"] > best["score"] or \
                        (r["score"] == best["score"] and r["status"] == "hit"):
                    best = r
                    best_rank = idx + 1
            cell = {
                "ref_id": ref.get("ref_id"),
                "cell_key": key,
                "query_id": q.get("query_id"),
                "source": q.get("source"),
                "executed_at": q.get("executed_at"),
            }
            if best is None:
                cell.update({"status": "miss", "match_level": None,
                             "score": 0.0, "rank_in_results": None, "evidence": None})
            elif best["status"] == "ambiguous":
                qk = "%s::%s" % (ref.get("ref_id"), key)
                verdict = decisions.get(qk)
                if verdict == "accept":
                    cell.update({"status": "hit", "match_level": best["level"] + "(adjudicated)",
                                 "score": best["score"], "rank_in_results": best_rank,
                                 "evidence": best["reason"] + "; adjudication=accept"})
                elif verdict == "reject":
                    cell.update({"status": "miss", "match_level": None,
                                 "score": best["score"], "rank_in_results": None,
                                 "evidence": best["reason"] + "; adjudication=reject"})
                else:
                    cell.update({"status": "ambiguous", "match_level": best["level"],
                                 "score": best["score"], "rank_in_results": best_rank,
                                 "evidence": best["reason"]})
                    queue.append({"queue_key": qk, "ref_id": ref.get("ref_id"),
                                  "query_id": q.get("query_id"), "source": q.get("source"),
                                  "score": best["score"], "rank_in_results": best_rank,
                                  "reason": best["reason"],
                                  "ref_title": ref.get("title"),
                                  "ref_year": get_year(ref)})
            else:
                cell.update({"status": "hit", "match_level": best["level"],
                             "score": best["score"], "rank_in_results": best_rank,
                             "evidence": best["reason"]})
            cells.append(cell)
    return cells, queue


# ---------------------------------------------------------------------------
# 案例加载（与 parse_case.py 输出格式一致）
# ---------------------------------------------------------------------------

def load_normalized_case(work_dir):
    path = os.path.join(work_dir, "case_normalized.json")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_results_files(work_dir, file_list):
    """加载本地响应文件；损坏文件记 None，由调用方降级处理。"""
    out = {}
    for rel in file_list:
        path = rel if os.path.isabs(rel) else os.path.join(work_dir, rel)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data = data.get("results") or data.get("records") or []
            out[rel] = data if isinstance(data, list) else []
        except (OSError, ValueError):
            out[rel] = None
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="三级命中判定：L1 标识符精确命中 / L2 题录近似命中 / L3 裁决队列。")
    ap.add_argument("--work", default="/app/work", help="工作目录（默认 /app/work）")
    ap.add_argument("--decisions", default=None,
                    help="L3 裁决回灌文件：{queue_key: 'accept'|'reject'}")
    ap.add_argument("--strict", action="store_true",
                    help="存在损坏响应文件时以退出码 2 降级而非跳过")
    args = ap.parse_args(argv)

    case = load_normalized_case(args.work)
    if case is None:
        print("ERROR: 未找到 %s/case_normalized.json，请先运行 parse_case.py" % args.work,
              file=sys.stderr)
        return 2

    reference_set = [r for r in case.get("reference_set", []) if r.get("usable", True)]
    queries = case.get("search_log", [])
    if not reference_set or not queries:
        print("ERROR: 可用参考集或检索记录为空，无法判定", file=sys.stderr)
        return 2

    files = sorted({q.get("results_file") for q in queries if q.get("results_file")})
    results_by_file = load_results_files(args.work, files)
    broken = [f for f, v in results_by_file.items() if v is None]
    if broken and args.strict:
        print("ERROR: 响应文件缺失或损坏: %s" % ", ".join(broken), file=sys.stderr)
        return 2
    if broken:
        print("WARN: 响应文件缺失或损坏，按空结果处理: %s" % ", ".join(broken),
              file=sys.stderr)
        for f in broken:
            results_by_file[f] = []

    decisions = {}
    if args.decisions:
        try:
            with open(args.decisions, "r", encoding="utf-8") as f:
                decisions = json.load(f)
        except (OSError, ValueError) as e:
            print("ERROR: 裁决文件不可解析: %s" % e, file=sys.stderr)
            return 3

    cells, queue = adjudicate(reference_set, queries, results_by_file, decisions)

    adj_path = os.path.join(args.work, "adjudication.json")
    with open(adj_path, "w", encoding="utf-8") as f:
        json.dump({"cells": cells, "broken_files": broken}, f,
                  ensure_ascii=False, indent=2)
    queue_path = os.path.join(args.work, "adjudication_queue.json")
    with open(queue_path, "w", encoding="utf-8") as f:
        json.dump({"queue": queue, "pending": len(queue)}, f, ensure_ascii=False, indent=2)

    hits = sum(1 for c in cells if c["status"] == "hit")
    amb = sum(1 for c in cells if c["status"] == "ambiguous")
    print("adjudicate: %d 单元, hit=%d, ambiguous=%d, miss=%d, 裁决队列 %d 条"
          % (len(cells), hits, amb, len(cells) - hits - amb, len(queue)))
    print("输出: %s ; %s" % (adj_path, queue_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
