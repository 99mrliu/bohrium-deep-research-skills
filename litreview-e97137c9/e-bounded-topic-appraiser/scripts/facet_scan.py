#!/usr/bin/env python3
"""facet_scan.py — facet 打标与覆盖缺口检测（bundle E 签名脚本 1）。

输入：work/docs.jsonl、work/pages/<doc_id>.jsonl、vocab/facets.json、
      （可选）模型产物 work/themes.json。
逻辑：
  1. 对每篇可用文献（fulltext/abstract_only）用 facet 词表 aliases 打标
     （英文别名按词边界匹配，中文别名按子串匹配）→ 每篇的 facet 集合。
  2. 全语料覆盖统计：每个 facet 值被哪些文献覆盖。
  3. 检测：underpowered（恰好 1 篇覆盖）、absent（0 篇覆盖）的 facet 值。
  4. theme：优先读 work/themes.json（模型产出，格式
     [{"theme":"T1","label":"…","docs":["D1",…]}]）；缺失时按 facet 共现
     粗聚类（共享任一 facet 值的文献并入同簇，并标注 themes_source）。
  5. 每个 theme 的覆盖缺口：语料中已出现但本 theme 文献未覆盖的 facet 值。
产物：work/facet_matrix.json
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VOCAB_PATH = os.path.join(HERE, "..", "vocab", "facets.json")

ASCII_ALIAS_RE = re.compile(r"^[A-Za-z0-9 .\-+/]+$")


def load_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def load_vocab(path=VOCAB_PATH):
    with open(path, encoding="utf-8") as f:
        vocab = json.load(f)
    flat = []  # [(facet_id, category, value, aliases)]
    for cat, entries in vocab.get("categories", {}).items():
        for e in entries:
            flat.append((f"{cat}:{e['value']}", cat, e["value"], e.get("aliases", [e["value"]])))
    return flat


def alias_hit(text_lower, alias):
    a = alias.lower()
    if ASCII_ALIAS_RE.match(alias):
        return re.search(r"\b" + re.escape(a) + r"\b", text_lower) is not None
    return a in text_lower


def doc_text(work, doc_id):
    rows = load_jsonl(os.path.join(work, "pages", f"{doc_id}.jsonl"))
    return "\n\n".join(r.get("text", "") for r in rows)


def load_themes(work, usable_docs, doc_facets):
    """返回 (themes, source)。模型 themes.json 优先；缺失则 facet 共现粗聚类。"""
    path = os.path.join(work, "themes.json")
    if os.path.exists(path):
        try:
            raw = json.load(open(path, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            raw = []
        themes = []
        for i, t in enumerate(raw if isinstance(raw, list) else [], 1):
            docs = [d for d in t.get("docs", []) if d in usable_docs]
            if docs:
                themes.append({"theme": str(t.get("theme", f"T{i}")),
                               "label": str(t.get("label", "")),
                               "docs": sorted(set(docs))})
        if themes:
            return themes, "model_themes_json"
    # 粗聚类：共享任一 facet 值即连通（并查集）
    parent = {d: d for d in usable_docs}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    by_facet = {}
    for d in usable_docs:
        for fid in doc_facets.get(d, set()):
            by_facet.setdefault(fid, []).append(d)
    for members in by_facet.values():
        for other in members[1:]:
            union(members[0], other)
    clusters = {}
    for d in usable_docs:
        clusters.setdefault(find(d), []).append(d)
    themes = [{"theme": f"T{i}", "label": "facet 共现粗聚类簇（无模型 themes.json）",
               "docs": sorted(members)}
              for i, members in enumerate(clusters.values(), 1)]
    return themes, "coarse_facet_coclustering"


def run(work, vocab_path=VOCAB_PATH):
    docs = load_jsonl(os.path.join(work, "docs.jsonl"))
    usable = [d["doc_id"] for d in docs if d.get("tier") in ("fulltext", "abstract_only")]
    flat = load_vocab(vocab_path)

    doc_facets, doc_facets_by_cat = {}, {}
    for d in usable:
        text = doc_text(work, d).lower()
        hits, by_cat = set(), {}
        for fid, cat, value, aliases in flat:
            if any(alias_hit(text, a) for a in aliases):
                hits.add(fid)
                by_cat.setdefault(cat, []).append(value)
        doc_facets[d] = hits
        doc_facets_by_cat[d] = {c: sorted(v) for c, v in by_cat.items()}

    coverage = {}
    for fid, cat, value, _ in flat:
        members = sorted(d for d in usable if fid in doc_facets[d])
        coverage[fid] = members
    underpowered = [{"facet": fid, "docs": m} for fid, m in coverage.items() if len(m) == 1]
    absent = [fid for fid, m in coverage.items() if len(m) == 0]

    themes, themes_source = load_themes(work, set(usable), doc_facets)
    corpus_facets = {fid for fid, m in coverage.items() if m}
    theme_gaps = {}
    for t in themes:
        covered = set()
        for d in t["docs"]:
            covered |= doc_facets.get(d, set())
        theme_gaps[t["theme"]] = {
            "label": t["label"],
            "docs": t["docs"],
            "doc_count": len(t["docs"]),
            "covered_facets": sorted(covered),
            "coverage_gaps": sorted(corpus_facets - covered),
        }

    matrix = {
        "vocab": os.path.relpath(vocab_path, work) if vocab_path != VOCAB_PATH else "vocab/facets.json",
        "usable_docs": usable,
        "doc_facets": {d: sorted(doc_facets[d]) for d in usable},
        "doc_facets_by_category": doc_facets_by_cat,
        "coverage": coverage,
        "underpowered_facets": underpowered,
        "absent_facets": absent,
        "themes": themes,
        "themes_source": themes_source,
        "theme_gaps": theme_gaps,
    }
    with open(os.path.join(work, "facet_matrix.json"), "w", encoding="utf-8") as f:
        json.dump(matrix, f, ensure_ascii=False, indent=2)
    return matrix


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--vocab", default=VOCAB_PATH)
    args = ap.parse_args(argv)
    m = run(args.work, args.vocab)
    print(json.dumps({"usable_docs": len(m["usable_docs"]),
                      "underpowered_facets": len(m["underpowered_facets"]),
                      "absent_facets": len(m["absent_facets"]),
                      "themes": len(m["themes"]),
                      "themes_source": m["themes_source"]}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
