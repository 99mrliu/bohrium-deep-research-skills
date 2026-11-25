#!/usr/bin/env python3
"""coverage_check.py — 已知文献覆盖验证（known-item recall check）。

利用案例材料中保留的参考图谱 / 种子文献清单（reference_graph.json），逐颗种子：
  1. 在各源快照中定位其记录（按 doi/pmid/arxiv_id，兜底精确标题匹配）；
  2. 若快照中不存在            -> status = absent_from_snapshot（诚实标注，非检索式问题）；
  3. 若存在但日期在窗口外      -> status = outside_window；
  4. 否则模拟当前检索式：逐概念块检查"块内任一同义词命中 标题+摘要"，
     块间 AND。全部块命中 -> hit；否则 -> miss，并给出诊断：
       - missed_blocks：哪些概念块把该种子挡掉了；
       - 每个漏配块给出最小化修订建议（从该种子记录文本中确定性抽取的候选新同义词）。

匹配规则（确定性）：大小写不敏感 + 词边界 + 词尾单复数容忍
（network 命中 networks；property 命中 properties）。详见
references/known-item-recall-methodology.md。

仅用 Python3 标准库，完全离线，确定性输出。

用法:
  python3 coverage_check.py --case case.json --concepts concepts.json \
      --materials materials/ --out coverage.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "and", "or", "to", "for", "with",
    "via", "using", "use", "based", "by", "at", "as", "from", "into", "that",
    "which", "we", "our", "their", "its", "is", "are", "was", "were", "be",
    "this", "these", "those", "it", "over", "under", "during", "toward",
    "towards", "between", "within", "across", "present", "show", "demonstrate",
}

SOURCE_ID_KEYS = {
    "crossref": ["doi"],
    "europepmc": ["pmid", "doi"],
    "arxiv": ["arxiv_id"],
}

SOURCE_FILE_HINTS = {"crossref": "crossref", "europepmc": "europepmc", "arxiv": "arxiv"}


# ---------------------------------------------------------------- 匹配原语

def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _plural_tail(term: str) -> str:
    """词尾单复数容忍：property -> propert(?:y|ies)，network -> networks?，
    box/class -> (?:box|class)(?:es)?。"""
    if re.search(r"[^aeiou]y$", term):
        return term[:-1] + r"(?:y|ies)"
    if re.search(r"(s|x|ch|sh)$", term):
        return term + r"(?:es)?"
    if re.search(r"[a-z]$", term):
        return term + "s?"
    return term


def term_pattern(term: str) -> re.Pattern:
    t = norm_text(term).strip('"')
    parts = [re.escape(p) for p in t.split(" ")]
    if parts:
        parts[-1] = _plural_tail(parts[-1])
    body = " ".join(parts)
    return re.compile(r"(?<![a-z0-9])" + body + r"(?![a-z0-9])")


def term_hit(term: str, text: str) -> bool:
    if not norm_text(term):
        return False
    return bool(term_pattern(term).search(norm_text(text)))


# ---------------------------------------------------------------- 快照加载

def _norm_item(source: str, raw: dict, idx: int, path: str) -> dict:
    if source == "crossref":
        return {"source": source, "doi": raw.get("doi"), "pmid": None, "arxiv_id": None,
                "title": raw.get("title") or "", "abstract": raw.get("abstract") or "",
                "date": raw.get("published"), "locator": {"path": path, "pointer": f"/items/{idx}"}}
    if source == "europepmc":
        return {"source": source, "doi": raw.get("doi"), "pmid": raw.get("pmid"),
                "arxiv_id": None, "title": raw.get("title") or "",
                "abstract": raw.get("abstractText") or "",
                "date": raw.get("firstPublicationDate"),
                "locator": {"path": path, "pointer": f"/items/{idx}"}}
    return {"source": source, "doi": None, "pmid": None, "arxiv_id": raw.get("arxiv_id"),
            "title": raw.get("title") or "", "abstract": raw.get("summary") or "",
            "date": raw.get("published"), "locator": {"path": path, "pointer": f"/items/{idx}"}}


def load_materials(materials_dir: str | Path) -> tuple[dict[str, list[dict]], dict, list[str]]:
    """返回 (items_by_source, reference_graph, warnings)。文件名按 SOURCE_FILE_HINTS 识别。"""
    mdir = Path(materials_dir)
    warnings: list[str] = []
    items_by_source: dict[str, list[dict]] = {s: [] for s in SOURCE_FILE_HINTS}
    if not mdir.is_dir():
        return items_by_source, {}, [f"materials 目录不存在: {mdir}"]
    for f in sorted(mdir.glob("*.json")):
        low = f.name.lower()
        for source, hint in SOURCE_FILE_HINTS.items():
            if hint in low:
                doc = json.loads(f.read_text(encoding="utf-8"))
                raw_items = doc.get("items") if isinstance(doc, dict) else None
                if not isinstance(raw_items, list):
                    warnings.append(f"{f.name} 缺少 items list，已跳过")
                    break
                items_by_source[source] = [
                    _norm_item(source, r, i, str(f)) for i, r in enumerate(raw_items)]
                break
    rg_path = mdir / "reference_graph.json"
    reference_graph = {}
    if rg_path.is_file():
        reference_graph = json.loads(rg_path.read_text(encoding="utf-8"))
        reference_graph["__locator_dir"] = str(rg_path)
    else:
        warnings.append(f"未找到 reference_graph.json（{rg_path}）；无种子图谱时无法做已知项召回验证")
    for source, items in items_by_source.items():
        if not items:
            warnings.append(f"源 {source} 无快照数据（空或缺失），该源覆盖验证将标记为 no_snapshot")
    return items_by_source, reference_graph, warnings


# ---------------------------------------------------------------- 种子定位

def find_record(seed: dict, items: list[dict]) -> dict | None:
    ids = {k: norm_text(str(v)) for k, v in (seed.get("identifiers") or {}).items() if v}
    for key in ("doi", "pmid", "arxiv_id"):
        if key in ids:
            for it in items:
                if it.get(key) and norm_text(str(it[key])) == ids[key]:
                    return it
    title = norm_text(seed.get("title") or "")
    if title:
        for it in items:
            if norm_text(it["title"]) == title:
                return it
    return None


# ---------------------------------------------------------------- 修订建议

def suggest_terms(block: dict, all_concepts: list[dict], record_text: str, top_k: int = 3) -> list[dict]:
    """从种子记录文本中确定性抽取候选新同义词。

    候选 = 记录文本中不含停用词的 n-gram（n=1..3），按以下键排序：
      (-与漏配块现有 term 的 token 重叠数, n 升序(最小修订), 字典序)。
    排除：已是任意块 term 的候选（大小写不敏感）。
    """
    text = norm_text(record_text)
    tokens = re.findall(r"[a-z][a-z0-9\-]*", text)
    block_tokens = set()
    for t in block.get("terms", []):
        block_tokens.update(re.findall(r"[a-z][a-z0-9\-]*", norm_text(t)))
    existing_terms = {norm_text(t).strip('"') for blk in all_concepts for t in blk.get("terms", [])}

    candidates: dict[str, int] = {}
    for n in (1, 2, 3):
        for i in range(0, len(tokens) - n + 1):
            gram_tokens = tokens[i:i + n]
            if any(g in STOPWORDS for g in gram_tokens):
                continue
            gram = " ".join(gram_tokens)
            if gram in existing_terms:
                continue
            overlap = len(set(gram_tokens) & block_tokens)
            if overlap == 0:
                continue
            candidates[gram] = max(overlap, candidates.get(gram, 0))

    ranked = sorted(candidates.items(), key=lambda kv: (-kv[1], len(kv[0].split()), kv[0]))
    return [{"term": gram, "overlap_with_block_tokens": ov} for gram, ov in ranked[:top_k]]


# ---------------------------------------------------------------- 主流程

def simulate_seed(seed: dict, concepts: list[dict], items: list[dict],
                  source: str, window: dict | None) -> dict:
    if not items:
        return {"status": "no_snapshot", "record_title": None, "locator": None}
    rec = find_record(seed, items)
    if rec is None:
        return {"status": "absent_from_snapshot", "record_title": None, "locator": None}
    cell: dict = {"status": None, "record_title": rec["title"], "locator": rec["locator"]}
    date = rec.get("date")
    if window and date:
        start, end = window.get("start"), window.get("end")
        if (start and date < start) or (end and date > end):
            cell["status"] = "outside_window"
            cell["record_date"] = date
            return cell
    text = rec["title"] + " . " + rec["abstract"]
    per_block: dict[str, dict] = {}
    missed: list[str] = []
    for blk in concepts:
        matched = [t for t in blk.get("terms", []) if term_hit(t, text)]
        hit = bool(matched)
        per_block[blk["id"]] = {"hit": hit, "matched_terms": matched}
        if not hit:
            missed.append(blk["id"])
    cell["blocks"] = per_block
    if missed:
        cell["status"] = "miss"
        suggestions = {
            bid: suggest_terms(next(b for b in concepts if b["id"] == bid), concepts, text)
            for bid in missed
        }
        cell["missed_blocks"] = missed
        cell["diagnosis"] = {
            "reason": "；".join(
                f"概念块 '{bid}' 无任何同义词命中该记录标题/摘要" for bid in missed),
            "suggestions": suggestions,
            "minimal_revision": [
                {"concept": bid, "add_term": s[0]["term"]}
                for bid, s in suggestions.items() if s
            ],
        }
    else:
        cell["status"] = "hit"
    return cell


def run(case: dict, concepts: list[dict], materials_dir: str | Path) -> dict:
    items_by_source, reference_graph, warnings = load_materials(materials_dir)
    window = case.get("window")
    seeds = reference_graph.get("seeds") or []
    rg_dir = reference_graph.get("__locator_dir", str(Path(str(materials_dir)) / "reference_graph.json"))

    seed_results: list[dict] = []
    for si, seed in enumerate(seeds):
        sources_cell = {}
        for source in sorted(items_by_source):
            sources_cell[source] = simulate_seed(
                seed, concepts, items_by_source[source], source, window)
        seed_results.append({
            "seed_id": seed.get("seed_id"),
            "seed_title": seed.get("title"),
            "seed_locator": {"path": rg_dir, "pointer": f"/seeds/{si}"},
            "sources": sources_cell,
        })

    matrix: dict[str, dict[str, str]] = {}
    for source in sorted(items_by_source):
        matrix[source] = {sr["seed_id"]: sr["sources"][source]["status"] for sr in seed_results}

    summary: dict[str, dict] = {}
    for source in sorted(items_by_source):
        statuses = list(matrix[source].values())
        testable = [s for s in statuses if s in ("hit", "miss")]
        summary[source] = {
            "seeds_total": len(statuses),
            "hit": statuses.count("hit"),
            "miss": statuses.count("miss"),
            "absent_from_snapshot": statuses.count("absent_from_snapshot"),
            "outside_window": statuses.count("outside_window"),
            "no_snapshot": statuses.count("no_snapshot"),
            "known_item_recall": statuses.count("hit") / len(testable) if testable else None,
        }

    missed_seeds = []
    for sr in seed_results:
        miss_in = {s: c for s, c in sr["sources"].items() if c["status"] == "miss"}
        if miss_in:
            missed_seeds.append({
                "seed_id": sr["seed_id"],
                "seed_title": sr["seed_title"],
                "seed_locator": sr["seed_locator"],
                "miss_in_sources": sorted(miss_in),
                "diagnosis": {s: c["diagnosis"] for s, c in miss_in.items()},
                "record_locators": {s: c["locator"] for s, c in miss_in.items()},
            })

    return {
        "window": window,
        "concepts_used": concepts,
        "seeds_total": len(seeds),
        "matrix": matrix,
        "summary": summary,
        "seeds": seed_results,
        "missed_seeds": missed_seeds,
        "warnings": warnings,
        "note": "已知项召回仅针对种子清单，是检索式召回能力的可验证下界，"
                "不代表对真实全量相关文献的召回率",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="已知文献覆盖验证（known-item recall check）")
    ap.add_argument("--case", required=True)
    ap.add_argument("--concepts", required=True, help="concept_parse 输出或裸 concepts list")
    ap.add_argument("--materials", required=True, help="材料目录（快照 + reference_graph.json）")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    case = json.loads(Path(args.case).read_text(encoding="utf-8"))
    cdoc = json.loads(Path(args.concepts).read_text(encoding="utf-8"))
    concepts = cdoc["concepts"] if isinstance(cdoc, dict) and "concepts" in cdoc else cdoc
    doc = run(case, concepts, args.materials)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[coverage_check] seeds={doc['seeds_total']} "
          f"missed={len(doc['missed_seeds'])} summary={json.dumps(doc['summary'])} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
