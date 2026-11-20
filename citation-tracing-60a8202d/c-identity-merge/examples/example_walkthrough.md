# 最小调用示例（示意，非正式案例结果）

合成数据，仅说明接口。标识均为虚构。

## 输入

`/tmp/demo/case.json`：

```json
{"case_id": "demo-merge-001",
 "output_contract": {"clean_works": null, "status": null}}
```

`/tmp/demo/records.jsonl`（同一工作的三种形态＋一对同名不同文）：

```json
{"DOI": "10.0000/demo.journal.1", "title": ["Deep Toy Networks: A Study"], "type": "journal-article", "issued": {"date-parts": [[2021]]}, "author": [{"family": "Smith", "given": "A."}], "volume": "12", "page": "1-15"}
{"arxiv": "2101.00001", "title": "Deep Toy Networks: A Study", "type": "posted-content", "year": 2020, "authors": [{"name": "A. Smith"}]}
{"DOI": "10.0000/demo.conf.1", "title": ["Deep toy networks - a study"], "type": "proceedings-article", "issued": {"date-parts": [[2021]]}, "author": [{"family": "Smith", "given": "A."}]}
{"DOI": "10.0000/demo.same.1", "title": ["Graph Kernels Revisited"], "year": 2019, "author": [{"family": "Lee"}]}
{"DOI": "10.0000/demo.same.2", "title": ["Graph Kernels Revisited"], "year": 2019, "author": [{"family": "Garcia"}]}
```

## 调用

```bash
python3 scripts/identity_merge.py --case /tmp/demo/case.json \
    --out /tmp/demo/out --workdir /tmp/demo/work --roots /tmp/demo
python3 scripts/verify_merge.py /tmp/demo/out /tmp/demo/work
```

## 示意输出（节选，标明为示例）

```json
{
  "case_id": "demo-merge-001",
  "status": "ok",
  "clean_works": [
    {"cluster_id": "r000000",
     "canonical": {"doi": "10.0000/demo.journal.1", "version": "journal",
                   "title": "Deep Toy Networks: A Study", "year": 2021},
     "versions_present": ["conference", "journal", "preprint"],
     "all_doi": ["10.0000/demo.conf.1", "10.0000/demo.journal.1"],
     "all_arxiv": ["2101.00001"],
     "field_conflicts": [{"field": "year", "values": [2020, 2021]},
                          {"field": "title", "n_distinct": 3}]},
    {"cluster_id": "r000003", "canonical": {"doi": "10.0000/demo.same.1"}},
    {"cluster_id": "r000004", "canonical": {"doi": "10.0000/demo.same.2"}}
  ],
  "review_queue": [
    {"pair": ["r000003", "r000004"],
     "evidence": {"key": "same_title_disjoint_authors",
                  "reason": "标题指纹一致但作者集合不相交：疑似同名不同文"}}
  ],
  "stats": {"records_ingested": 5, "clusters": 3, "duplicates_removed": 2,
            "review_pairs": 1}
}
```

要点：三种形态合并为一簇且期刊版为 canonical，全部标识入并集、年份/标题差异留痕；两条 "Graph Kernels Revisited" 因作者不相交**未被合并**，进入待人工裁定队列。
