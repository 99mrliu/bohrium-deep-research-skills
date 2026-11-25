#!/usr/bin/env python3
"""query_build.py — 概念块 -> 各源方言的可审计布尔检索式。

支持三个源的序列化方言（细节见 references/source-dialects.md）：
  - crossref   : Crossref REST API 无真正布尔语义；序列化为 query.bibliographic
                 的空格分隔词串 + from-pub-date/until-pub-date filter，并附 note 说明
                 短语约束丢失（交由 query_lint QL001 逐条提示）。
  - europepmc  : Europe PMC 完整布尔语法；每个概念块 = TITLE_ABS:"同义詞" OR ...，
                 块间 AND，末尾 AND FIRST_PDATE:[start TO end]。
  - arxiv      : arXiv API 字段前缀 all:"..."，块内 OR、块间 AND，
                 末尾 AND submittedDate:[yyyymmdd0000 TO yyyymmdd2359]。

约定：块内同义词一律 OR、块间一律 AND；多词 term 在支持短语的方言中加双引号。
仅用 Python3 标准库，完全离线，确定性输出。

用法:
  python3 query_build.py --concepts concepts.json --window-start 2024-01-01 \
      --window-end 2026-06-30 --out queries.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SOURCES = ("crossref", "europepmc", "arxiv")


def quote(term: str) -> str:
    """多词 term 加双引号；已含引号的 term 原样返回（避免双重引用）。"""
    t = term.strip()
    if t.startswith('"') and t.endswith('"'):
        return t
    return f'"{t}"' if " " in t else t


def load_concepts(path: str | Path) -> list[dict]:
    """接受 concept_parse 的输出文档（{"concepts": [...]}）或裸 list。"""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(doc, dict) and "concepts" in doc:
        return doc["concepts"]
    if isinstance(doc, list):
        return doc
    raise ValueError(f"无法从 {path} 读取概念块")


def _window_dates(window: dict | None) -> tuple[str | None, str | None]:
    if not window:
        return None, None
    return window.get("start"), window.get("end")


def build_crossref(concepts: list[dict], window: dict | None) -> dict:
    terms = [t for blk in concepts for t in blk.get("terms", [])]
    start, end = _window_dates(window)
    filters = []
    if start:
        filters.append(f"from-pub-date:{start}")
    if end:
        filters.append(f"until-pub-date:{end}")
    return {
        "source": "crossref",
        "dialect": "query.bibliographic + filter",
        "query": " ".join(terms),
        "filter": ",".join(filters) if filters else None,
        "notes": [
            "Crossref REST API 无 AND/OR/短语布尔语义；空格分隔词串按相关度匹配，"
            "概念块的 AND/OR 结构无法在服务端表达，需客户端后置过滤",
            "多词 term 的词序与短语约束在此方言中丢失（见 query_lint QL001）",
        ],
    }


def build_europepmc(concepts: list[dict], window: dict | None) -> dict:
    blocks = []
    for blk in concepts:
        ors = " OR ".join(f"TITLE_ABS:{quote(t)}" for t in blk.get("terms", []))
        blocks.append(f"({ors})")
    query = " AND ".join(blocks) if blocks else ""
    start, end = _window_dates(window)
    if start or end:
        query += f" AND FIRST_PDATE:[{start or '*'} TO {end or '*'}]"
    return {
        "source": "europepmc",
        "dialect": "Europe PMC query syntax (TITLE_ABS, AND/OR, FIRST_PDATE)",
        "query": query,
        "filter": None,
        "notes": ["块内 OR、块间 AND；短语用双引号锁定词序"],
    }


def build_arxiv(concepts: list[dict], window: dict | None) -> dict:
    blocks = []
    for blk in concepts:
        ors = " OR ".join(f"all:{quote(t)}" for t in blk.get("terms", []))
        blocks.append(f"({ors})")
    query = " AND ".join(blocks) if blocks else ""
    start, end = _window_dates(window)
    if start or end:
        def _ts(d: str | None, tail: str) -> str:
            return re.sub(r"-", "", d) + tail if d else "*"
        query += f" AND submittedDate:[{_ts(start, '0000')} TO {_ts(end, '2359')}]"
    return {
        "source": "arxiv",
        "dialect": "arXiv API search_query (all:/ti:/abs:, AND/OR/ANDNOT, submittedDate)",
        "query": query,
        "filter": None,
        "notes": [
            "arXiv 不支持通配符 *（见 query_lint QL004）",
            "all: 覆盖标题/摘要/作者等字段；如需限定摘要用 abs:",
        ],
    }


BUILDERS = {"crossref": build_crossref, "europepmc": build_europepmc, "arxiv": build_arxiv}


def build_all(concepts: list[dict], window: dict | None) -> dict:
    return {src: BUILDERS[src](concepts, window) for src in SOURCES}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="概念块 -> 各源方言布尔检索式")
    ap.add_argument("--concepts", required=True, help="concept_parse 输出或裸 concepts list")
    ap.add_argument("--window-start", default=None)
    ap.add_argument("--window-end", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    concepts = load_concepts(args.concepts)
    window = {"start": args.window_start, "end": args.window_end} if (args.window_start or args.window_end) else None
    queries = build_all(concepts, window)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"concepts": concepts, "window": window, "queries": queries},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[query_build] blocks={len(concepts)} sources={list(queries)} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
