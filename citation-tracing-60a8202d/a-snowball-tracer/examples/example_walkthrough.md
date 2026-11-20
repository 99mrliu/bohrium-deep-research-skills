# 最小调用示例（示意，非正式案例结果）

以下使用**合成玩具语料**演示接口与输出形态。所有文献均为虚构标识，仅说明字段含义。

## 输入

`/tmp/demo/case.json`：

```json
{
  "case_id": "demo-case-001",
  "seed_paper": {"doi": "10.0000/demo.seed.1", "title": "A Demo Method for Toy Graphs"},
  "output_contract": {"candidates": null, "evidence": null, "status": null}
}
```

`/tmp/demo/corpus.jsonl`（每行一条 Crossref 风格记录）：

```json
{"DOI": "10.0000/demo.seed.1", "title": ["A Demo Method for Toy Graphs"], "issued": {"date-parts": [[2020]]}, "is-referenced-by-count": 12, "reference": [{"DOI": "10.0000/demo.prior.1", "article-title": "Earlier Toy Baseline"}, {"DOI": "10.0000/demo.prior.2"}]}
{"DOI": "10.0000/demo.follow.1", "title": ["Improving the Demo Method"], "issued": {"date-parts": [[2022]]}, "reference": [{"DOI": "10.0000/demo.seed.1"}]}
{"DOI": "10.0000/demo.prior.1", "title": ["Earlier Toy Baseline"], "issued": {"date-parts": [[2015]]}, "is-referenced-by-count": 300}
```

## 调用

```bash
python3 scripts/snowball_trace.py --case /tmp/demo/case.json \
    --out /tmp/demo/out --workdir /tmp/demo/work --roots /tmp/demo
python3 scripts/verify_trace.py /tmp/demo/out /tmp/demo/work
```

## 示意输出（节选，标明为示例）

```json
{
  "case_id": "demo-case-001",
  "status": "ok",
  "seed": {"doi": "10.0000/demo.seed.1", "title": "A Demo Method for Toy Graphs", "year": 2020},
  "nodes": [
    {"key": "doi:10.0000/demo.seed.1", "layer": 0, "direction": "seed"},
    {"key": "doi:10.0000/demo.prior.1", "layer": 1, "direction": "backward",
     "via": "doi:10.0000/demo.seed.1", "cited_by_hint": 300},
    {"key": "doi:10.0000/demo.prior.2", "layer": 1, "direction": "backward", "stub": true},
    {"key": "doi:10.0000/demo.follow.1", "layer": 1, "direction": "forward",
     "via": "doi:10.0000/demo.seed.1"}
  ],
  "edges": [
    {"from": "doi:10.0000/demo.seed.1", "to": "doi:10.0000/demo.prior.1",
     "direction": "backward", "layer": 1,
     "source": {"file": "/tmp/demo/corpus.jsonl", "pointer": "$/0/references/0"}},
    {"from": "doi:10.0000/demo.seed.1", "to": "doi:10.0000/demo.follow.1",
     "direction": "forward", "layer": 1,
     "source": {"file": "/tmp/demo/corpus.jsonl", "pointer": "$/1/references/0"}}
  ]
}
```

注意第二条边：数据源只给了 `demo.follow.1` 的参考文献列表，脚本通过**反向索引**恢复出"follow.1 引用 seed"这条前向边，方向语义正确且可回指。`demo.prior.2` 在语料中无完整记录，保留为 `stub=true`，不补造元数据。

## 复核方式

用定位信息直接回指原始记录，例如：

```bash
sed -n '1p' /tmp/demo/corpus.jsonl | python3 -c "import json,sys; print(json.load(sys.stdin)['reference'][0])"
```
