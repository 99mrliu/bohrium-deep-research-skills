# PRISMA 式流转计数与边界带规则

## 1. 流转层级

```
identified            快照归一化后的全部题录
  ├─ prefiltered_out  预筛排除（by_category: language / non_research_type /
  │                    out_of_window / blocked_term）
  └─ screened         进入 rubric 打分
        ├─ included              高于边界带上界
        ├─ needs_human_review    落在边界带内
        └─ excluded_at_screening 低于边界带下界或 duplicate_of_kept
                                   （by_category: wrong_population / wrong_method /
                                    wrong_outcome / duplicate_of_kept /
                                    off_topic_low_score）
```

## 2. 守恒不变量（必须恒为真）

1. `identified == prefiltered_out + screened`
2. `screened == included + needs_human_review + excluded_at_screening`

`scripts/prisma_flow.py` 计算并自检；任一不成立即 `ok=false` 并中止组装，
禁止输出"看起来正常"的 result.json。

## 3. 边界带（borderline band）

- 参数：`include_threshold`（T）、`borderline_delta`（δ），均来自 case 的 rubric 配置。
- 判定：`|score − T| ≤ δ` → `needs_human_review`。
- 语义：边界带条目**既不是 included 也不是 excluded**；在 result.json 中单独成组，
  每条附 `band = {threshold, delta, note}`，等待人工复核。
- 动机：词表打分对"对象匹配但干预弱命中"或"干预匹配但结局未报告"的条目不可
  靠，强行二分会制造静默的误纳/误排；边界带把不确定性显性化。

## 4. 遗漏说明（omission_notes）规则

result.json 必须如实交代以下遗漏面：

| 字段 | 内容 |
|---|---|
| `prefilter_excluded_not_audited` | 预筛排除但未逐条人工抽审的类别清单（如 language、out_of_window） |
| `title_only_records` | 摘要缺失、只能按标题判断的条目；其 included 结论置信度低 |
| `other` | 其他已知遗漏（如某快照文件无法识别被跳过） |

另有 `limitations`：汇总所有降级与 partial 原因。原则：**宁可 partial，不可隐瞒**。

## 5. 计数与证据的勾稽

- `prisma_flow.*_by_category` 的每个数字都能回算到 `screening_decisions.jsonl` /
  `prefilter_results.jsonl` 的具体行；
- `included` 与 `needs_human_review` 的每条记录必须在 `evidence_selected.json`
  中有对应装订（缺失 → status=partial）；
- 证据 quote 必须逐字等于快照字段文本的 `[char_start:char_end]` 切片，
  由 `evidence_bind.verify_binding` 复核。
