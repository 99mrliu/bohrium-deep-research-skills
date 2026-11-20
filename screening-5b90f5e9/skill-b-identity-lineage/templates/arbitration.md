# 仲裁文件模板：/app/work/arbitrations.json

对 `review_queue.json` 中**每一个** pending 对给出裁决。漏裁、未知 pair、
rationale 为空都会使 `apply_arbitration.py` exit 3。

## 格式

```json
{
  "arbitrations": [
    {
      "pair": "<record_id_a>|<record_id_b>",
      "decision": "merge",
      "rationale": "非空。指出同一研究的实质依据（标识符/题名/版本关系/数据一致性）。"
    },
    {
      "pair": "<record_id_c>|<record_id_d>",
      "decision": "split",
      "rationale": "非空。指出不同研究的实质依据（人群/数据/DOI/期刊冲突等）。"
    }
  ]
}
```

## 规则

- `pair` 必须与 `review_queue.json` 中的 pair 字符串完全一致
  （两个 record_id 以 `|` 连接、字典序排列）。
- `decision` 只能是 `merge` 或 `split`。
- `rationale` 必填非空：合并要有依据，拆分也要有依据（防误并留痕）。
- 拿不准倾向 split，并在 rationale 写明不确定点（误并代价高于漏并）。

## 示例（合成，对应 examples/ 虚构数据）

```json
{
  "arbitrations": [
    {"pair": "source_a-003|source_b-003", "decision": "merge",
     "rationale": "题名完全一致、首作者相同；a 为 arXiv 预印本（2021），b 为期刊正式版（DOI 10.1000/gnn789, 2022），同一研究的两个版本。"},
    {"pair": "source_a-004|source_b-004", "decision": "split",
     "rationale": "题名相似但人群（综合 ICU vs 心脏 ICU）、数据规模、DOI、期刊均不同，判为两项不同研究。"}
  ]
}
```
