# decomposition.json 结构规范（六要素拆解）

```json
{
  "research_question": "<原问题原文>",
  "time_window": "2022-2025 或 未检出",
  "sqs": [
    {
      "id": "SQ-1",
      "facet": "object",
      "question": "<一句可回答、可独立检索的问句>",
      "acceptance": "<可判定标准,必须含数字或类型词,如:≥3 篇原始研究给出器件效率数据>",
      "queries": {"zh": ["中文检索式"], "en": ["english query"]},
      "depends_on": []
    }
  ]
}
```

## 六要素（facet 取值）

- `object`：研究对象（材料体系/人群/数据集）。
- `mechanism`：机制或干预（现象、处理方法、药物……）。
- `method`：方法学（表征手段、实验设计、算法……）。
- `timeframe`：时间范围（其检索式中允许出现年份窗；全部 SQ 中至多 1 个含年份）。
- `comparator`：比较关系（A 对 B、改进前后……）。
- `evidence`：证据要求（原始研究/综述/定量数据/样本量……）。

## 写作守则

1. question 必须是**问句**且能独立检索；禁止把原问题整句复制进单个 SQ。
2. acceptance 是停止判据的输入：写"≥N 篇/条 + 证据类型"，plan.py 从中提取 K。
3. depends_on 只写真正需要先回答的 SQ；能并行的不要串行（减少轮次）。
4. queries 中英文都给：中文用于中文快照/工具，英文用于英文库；每条检索式含 2–5 个判别词，避免单关键词。
5. 4–8 个 SQ 通常足够；<2 说明没拆，>12 说明拆碎。
