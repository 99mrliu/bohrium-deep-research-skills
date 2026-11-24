---
name: queryforge
description: 过滤条件方向。把自然语言提问编译成结构化查询 JSON（概念词 + 硬过滤：年份、项目/批次编号、文件类型、版本标记、日期区间、路径约束），概念词经可编辑中英同义/缩写词表扩展；执行时硬过滤永远先施加且绝不放宽，每个过滤条件留下淘汰计数轨迹，无满足条件的文件时如实报 no_match 并说明是哪个条件排除了全部候选，而不是悄悄放松条件凑答案。当任务强调"按条件筛出、条件无法满足时如实报告"时使用；输入为 /input/case.json + task.md + 文档库。
---

# queryforge：提问编译与硬过滤执行

## 重心

检索失分的一条规律是"条件被悄悄放宽"：用户要"2023 年终稿"，
Agent 命中了 2022 年初稿也照答。本技能把提问先**编译**成机器可检查的
查询 JSON，硬过滤逐条施加并留下**淘汰轨迹**（哪个条件排除了几个候选），
答不出来就明说卡在哪条条件上。

## 运行契约（必须遵守）

1. 先读 `/input/case.json` 与 `/input/task.md`：记录 `case_id`，照抄
   `output_contract` 全部字段；库路径与提问以实际键名为准，找不到就
   `ls -R /input` 盘点。**不凭文件名猜内容。**
2. **立刻**写 `/app/output/result.json` 骨架（case_id + 全字段占位 +
   `"status":"partial"`），随后逐步填充。
3. 中间产物 `/app/work`，交付 `/app/output`；`$S` 为技能安装目录
   （通常 `/skills/weekly-skill`）。Python ≥3.9 标准库，不装第三方包；
   PDF 文本抽取依赖本机 `pdftotext`，缺失时该文件内容字段为空并记
   `content_unavailable`（元数据过滤不受影响）。

## 执行步骤

```bash
S=/skills/weekly-skill
mkdir -p /app/work /app/output
# 1. 提问 → 查询 JSON（概念词 + 硬过滤 + 词表扩展记录）
python3 "$S/scripts/forge_parse.py" /input/case.json "$S/references/lexicon.json" /app/work/queries.json
# 2. 执行：硬过滤（含淘汰轨迹）→ 概念打分 → 命中或诚实 no_match
python3 "$S/scripts/forge_run.py" /input/case.json /app/work/queries.json /app/work/query_results.json
# 3. 组装 result.json（output_contract 全字段）
python3 "$S/scripts/forge_result.py" /input/case.json /app/work /app/output/result.json
```

## 查询 JSON 结构（详见 references/query-schema.md）

```json
{"question": "2023年终稿版本的缓冲液配方",
 "concepts": ["缓冲液", "配方", "buffer"],
 "expansion_log": {"缓冲液": ["buffer", "缓冲溶液"]},
 "hard_filters": {"year": 2023, "version": "final"},
 "filter_trace": {"year": {"kept": 5, "dropped": 3},
                  "version": {"kept": 2, "dropped": 3}}}
```

硬过滤语义：能从文件名/内容/元数据中确认**不满足**条件的候选被排除；
条件字段完全不可判定的候选记 `undecidable` 并在答案中声明，
**不算满足也不算排除**，由 Agent 决定是否人工查看，但不得当作命中证据。

## 异常处理

| 情况 | 处置 |
|-|-|
| 全部候选被某条件排除 | `no_match`，给出淘汰轨迹与最后存活数 |
| 条件解析不出（如无年份） | 该条件不施加，queries.json 记录 `unparsed_constraints` |
| 文件内容不可抽取 | 仅元数据参与过滤，答案注明 `metadata_only` |
| 词表文件缺失 | 仅用原词，记 `lexicon_missing` |

## 最小示例

`examples/` 为**合成示例**（含 v1/终稿两版本、不同批次 CSV），运行
`python3 run_example.py`，预期见 `examples/README.md`。

## 限制

- 定位粒度为文件级 + 命中行号，章节级定位非本技能重心。
- 词表为人工可编辑资源，覆盖有限；扩展失败的词原样使用。
- 不做开放网络检索。
