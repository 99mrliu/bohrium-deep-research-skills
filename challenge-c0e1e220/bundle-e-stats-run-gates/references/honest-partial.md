# 诚实 partial 规范（honest-partial）

原则：宁可交付一份**结构完整、明确标注缺口**的 partial，也不交付静默缺字段的
"成功"。评分事实：旧作把推断字段标 not_in_scope 只交清洗 → 5 分。因此：
**任何情况下 9 个契约字段都必须存在**；做不了的内容降级填充并在 exceptions 说明。

## status 语义（枚举仅三个值）
| status | 含义 | 必要条件 |
|---|---|---|
| complete | 全部契约字段按规则填满，无 exception | exceptions == [] |
| partial | 契约字段全部存在，但至少一项降级（结局被跳过、DB 不一致、效应量不可算等） | exceptions 非空且每条含 code+message（G5 + lint 强制） |
| failed | 流水线未能建立有效分析（如无分组列、无数据行） | 骨架仍含全部字段 + 失败原因 exception |

注意：`"success"` 不是合法值。写 status 前过一遍枚举，contract_lint 的
INVALID_STATUS 就是为你拦这个的。

## 骨架先行机制（崩溃不丢工作）
1. run 启动后第一件事：生成 `stage_05_result_draft.json`（含 case_id、
   skeleton_fields=required_fields、status=partial、exceptions=[SKELETON_NOT_FILLED]），
   并**同时**写到 `/app/output/result.json`。
2. 之后才做 ingest → clean → descriptive → inference；seq.log 记录写出顺序，
   G2 校验骨架 seq < 推断 seq。
3. 全部完成才用完整结果覆盖 `/app/output/result.json`。
4. 任何步骤崩溃：交付位上是一份可解析、字段齐全、明确标注 partial 的诚实结果，
   而不是空气或半成品散装文件。

## 降级决策表
| 情形 | 字段级降级 | exception code |
|---|---|---|
| 某组有效 n<2 | 该组 descriptive=null；推断剔除该组 | GROUP_SMALL_N |
| 可用组<2 | 该结局 hypothesis_test/effect_size 缺省，保留 descriptive | OUTCOME_SKIPPED |
| 结局非数值 | 跳过该结局 | OUTCOME_NOT_NUMERIC |
| 组内方差为 0 | 检验给保护值（p=1 或 0），效应量 null | （组装时记） |
| SQLite 不可读/无表 | db_consistency.checked=false + limitation | DB_UNREADABLE |
| CSV/SQLite 不一致 | 以 CSV 为准（DEC-004 待确认） | DB_MISMATCH |
| bootstrap 有效样本不足 | ci95=[null,null] + uncertainty 注明 | （组装时记） |
| 单位不明 | unit="unspecified" + limitation + DEC-005 | — |
| 找不到分组列 | failed：骨架 + FATAL 退出 | NO_GROUPING |

## 红线
- 不得预制答案：所有数字必须来自本次运行的阶段产物（G3 会核对）。
- 不得把 partial 伪装成 complete：status 由 exceptions 自动推导，不提供人工覆盖开关。
- 不得静默吞错：所有降级路径都留下 exception 或 limitation 文字。
- 崩溃后恢复：修复原因后直接重跑 run/decide/finalize，骨架会被正常覆盖。
