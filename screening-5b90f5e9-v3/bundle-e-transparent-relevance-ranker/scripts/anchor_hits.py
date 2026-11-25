#!/usr/bin/env python3
"""anchor_hits.py — 命中锚定门：把每个 facet 词锚定到题录原文。

对 filled_facets.json 中的每个 term，在全部题录的题名/摘要上做
规范化（NFKC + casefold + 空白折叠）子串匹配，记录命中位置与原文片段。

门禁规则（防止"编相关性"）：
  - 任一 term 在整个语料中零命中 → 写入 anchors.json 的 anchor_failures，
    并 exit 3，强制模型重修 facet 词表（换成真实出现在语料中的词）。
  - 命中片段一律由脚本从原文截取，模型无法提供或篡改片段。

输出 <work>/anchors.json:
  {facets: {facet: {terms: {term: {hits_by_record: {record_id: [ {field,
     start, end, snippet}, ... ]}}, corpus_hit_count: n}}}, anchor_failures: []}

退出码：0 全部词可锚定；3 存在零命中词（门禁失败）。
"""
import argparse
import sys
from pathlib import Path

from common_lib import (default_config_path, dump_json, eprint, find_occurrences,
                        load_config, load_json, make_snippet, norm_text)

HIT_FIELDS = ("title", "abstract")


def main(argv=None):
    ap = argparse.ArgumentParser(description="facet 词命中锚定（门禁）")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--facets", required=True, help="模型填好并通过校验的 facets 文件")
    ap.add_argument("--config", default=default_config_path())
    args = ap.parse_args(argv)

    work = Path(args.work)
    cfg = load_config(args.config)
    records = load_json(work / "records.json")
    facets = load_json(args.facets)["facets"]

    cap = int(cfg.get("max_hits_per_field_per_term", 3))
    ctx = int(cfg.get("snippet_context_chars", 30))

    # 预规范化全部记录文本，键为 record_id
    norm_records = {
        r["record_id"]: {f: norm_text(r.get(f)) for f in HIT_FIELDS}
        for r in records
    }

    out_facets, failures = {}, []
    total_hits = 0
    for fname, node in facets.items():
        term_map = {}
        for term in node.get("terms", []):
            tnorm = norm_text(term)
            hits_by_record, corpus_count = {}, 0
            for rid, fields in norm_records.items():
                rec_hits = []
                for field in HIT_FIELDS:
                    hay = fields[field]
                    for (s, e) in find_occurrences(hay, tnorm, cap=cap):
                        rec_hits.append({
                            "field": field,
                            "start": s,
                            "end": e,
                            "snippet": make_snippet(hay, s, e, ctx=ctx),
                        })
                if rec_hits:
                    hits_by_record[rid] = rec_hits
                    corpus_count += len(rec_hits)
            if corpus_count == 0:
                failures.append({"facet": fname, "term": term,
                                 "reason": "规范化子串匹配在整个语料中零命中"})
            total_hits += corpus_count
            term_map[term] = {"hits_by_record": hits_by_record,
                              "corpus_hit_count": corpus_count}
        out_facets[fname] = {"terms": term_map}

    anchors = {
        "anchoring_rule": "NFKC + casefold + 空白折叠后的子串匹配；片段由脚本从规范化原文截取",
        "facets": out_facets,
        "anchor_failures": failures,
    }
    dump_json(work / "anchors.json", anchors)

    if failures:
        for f in failures:
            eprint(f"[anchor_hits] 锚定失败: facet={f['facet']} term={f['term']!r}（{f['reason']}）")
        eprint("[anchor_hits] 门禁未通过：请让模型把上述词替换为语料中真实出现的词后重跑（exit 3）")
        return 3
    print(f"[anchor_hits] 锚定通过: {sum(len(v['terms']) for v in out_facets.values())} 个词，"
          f"共 {total_hits} 处命中")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        eprint(f"[anchor_hits] 未预期异常: {exc!r}")
        sys.exit(3)
