# 子问题分解模板（decomposition.json 的书写规范）

measure.py 的测量质量上限由子问题清单决定。**优先由 Agent 手写** `/app/work/decomposition.json`；
只有缺失或损坏时，脚本才从 research_question 自动派生 2–5 个子问题（元素抽取口径粗，
产物中会以 `decomposition_source=auto_derived` 如实标注，结论按降级置信对待）。

## 文件格式

```json
{
  "research_question": "原样抄录 case.json 的 research_question",
  "subquestions": [
    {
      "sq_id": "SQ-1",
      "question": "一句可回答的子问题",
      "must_terms": ["perovskite", "grain boundary"],
      "any_terms": ["passivation", "钝化"],
      "year_window": [2021, 2024],
      "rationale": "为什么这样拆/这些词为什么是该子问题的判据"
    }
  ]
}
```

## 字段语义

| 字段 | 必填 | 语义 |
|-|-|-|
| `sq_id` | 是 | 稳定标识，矩阵、决定、result.json 都用它回溯 |
| `question` | 是 | 人话子问题，供复核者判断术语是否切题 |
| `must_terms` | 是 | **全部**命中才算命中（AND）。大小写不敏感，子串匹配于 标题+摘要+期刊 |
| `any_terms` | 否 | 至少命中其一（OR）；留空则不约束 |
| `year_window` | 否 | `[起, 止]` 闭区间；年份缺失的记录按在窗处理但计入 metadata_missing |
| `rationale` | 建议 | 一句理由，复核者据此审计分解是否合理 |

## 书写纪律

1. **2–5 个子问题**：少于 2 个说明没分解，多于 5 个说明在凑数；每个子问题应对应
   RQ 的一个独立证据需求（机制/效果/条件/风险……）。
2. 术语必须**来自 RQ 或其众所周知的同义/译名**，禁止臆造领域黑话；中英文并列写进
   must/any（脚本是纯子串匹配，不会自动翻译）。
3. must_terms 宁少勿多：每加一个词都是一道 AND 闸门，过严会人为制造 starved。
4. year_window 只从 RQ 明示的时间范围取；RQ 没写就省略该字段（不加窗），
   不要编造窗口。
5. 子问题之间允许证据重叠（一条记录可支撑多个 SQ），这不是重复计数——矩阵按
   SQ 行独立统计。

## 自动派生的降级语义

缺 decomposition.json 时，脚本按 CJK 语义段（连词切分）+ 拉丁相邻实词二元组抽取
至多 5 个元素，每个元素成为一个 must_term 单子问题，并应用内置小词表做跨语扩展。
派生结果写入 `/app/work/decomposition.used.json` 供对照；凡自动派生，measure.py
的 problems 与 finalize.py 的 uncertainty 都会写明"口径粗于人工分解"。
