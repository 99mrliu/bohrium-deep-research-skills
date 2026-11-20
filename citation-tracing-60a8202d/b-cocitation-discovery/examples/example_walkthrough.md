# 最小调用示例（示意，非正式案例结果）

合成玩具语料，仅说明接口。文献标识均为虚构。

## 输入

`/tmp/demo/case.json`：

```json
{"case_id": "demo-para-001",
 "seed_paper": {"doi": "10.0000/demo.seed"},
 "output_contract": {"candidates": null, "status": null}}
```

`/tmp/demo/corpus.jsonl`：

```json
{"DOI": "10.0000/demo.seed", "title": ["Seed Method X"], "issued": {"date-parts": [[2021]]}, "reference": [{"DOI": "10.0000/demo.baseA"}, {"DOI": "10.0000/demo.baseB"}]}
{"DOI": "10.0000/demo.citer1", "title": ["Citer One"], "reference": [{"DOI": "10.0000/demo.seed"}, {"DOI": "10.0000/demo.parallel1"}]}
{"DOI": "10.0000/demo.citer2", "title": ["Citer Two"], "reference": [{"DOI": "10.0000/demo.seed"}, {"DOI": "10.0000/demo.parallel1"}]}
{"DOI": "10.0000/demo.parallel1", "title": ["Parallel Method Y"], "reference": [{"DOI": "10.0000/demo.baseA"}, {"DOI": "10.0000/demo.baseC"}]}
{"DOI": "10.0000/demo.unrelated", "title": ["Unrelated Topic Z"], "reference": [{"DOI": "10.0000/demo.baseD"}]}
```

## 调用

```bash
python3 scripts/codiscover.py --case /tmp/demo/case.json \
    --out /tmp/demo/out --workdir /tmp/demo/work --roots /tmp/demo
python3 scripts/verify_discovery.py /tmp/demo/out /tmp/demo/work
```

## 示意输出（节选，标明为示例）

```json
{
  "case_id": "demo-para-001",
  "status": "ok",
  "candidates": [
    {"rank": 1, "doi": "10.0000/demo.parallel1", "title": "Parallel Method Y",
     "score": 0.9082,
     "score_parts": {"co_citation": 0.8165, "coupling": 0.25, "author": 0, "venue_task": 0},
     "association_evidence": {
       "co_citation": [
         {"citing_work": "doi:10.0000/demo.citer1",
          "citer_cites_seed_at": {"file": "/tmp/demo/corpus.jsonl", "pointer": "$/1/refs/0"},
          "citer_cites_candidate_at": {"file": "/tmp/demo/corpus.jsonl", "pointer": "$/1/refs/1"}},
         {"citing_work": "doi:10.0000/demo.citer2", "...": "..."}
       ],
       "bibliographic_coupling": [
         {"shared_reference": "doi:10.0000/demo.baseA",
          "seed_cites_at": {"file": "/tmp/demo/corpus.jsonl", "pointer": "$/0/refs/0"},
          "candidate_cites_at": {"file": "/tmp/demo/corpus.jsonl", "pointer": "$/3/refs/0"}}
       ]},
     "excluded_direct_relation": true}
  ],
  "direct_neighbors": {"n_seed_references": 2, "n_seed_citers": 2}
}
```

注意：`demo.parallel1` 不直接引用种子、种子也不引用它——它由两条共被引（citer1、citer2 同时引用种子与它）和一条耦合（共享 baseA）入选；`demo.unrelated` 无任何结构信号，被正确排除；`baseA/baseB/citer1/citer2` 是直接邻居，按设计不出现在候选中。
