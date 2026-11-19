# 五级判据全表（grading rubric）

判定全部可由脚本机械复核；模型负责选段、措辞与补写 `missing`。

| 级 | 进入条件（满足其一即为该级） | 退出条件（升级为更高级别） | 答案形态 |
|-|-|-|-|
| SUPPORTED | 至少一条逐字引文机器核验通过（空白去除后子串比对），且该问题无未决 clear_conflict | — | 论断 + `[Dxx|sha8|L起-L止]` 引文 |
| PARTIAL | 有存活引文但 best_coverage < 0.5，或引文只覆盖部分子论断，或证据仅来自历史版本 | 补全引文且 coverage ≥0.5 → SUPPORTED | 作答 + 限定语 |
| CONFLICTED | 问题命中 clear_conflict 键（不同来源同一事实取值不同），且有至少一方坐标 | 权威版本被任务/行政备注指定后 → 按权威版本给 SUPPORTED，其余保留在 caveat | 并列双方引文，说明分歧点，不裁决 |
| UNSUPPORTED | coverage_matrix 中该问题零可用命中 | 后续抽到有效引文 → 重新判级 | "库中无依据" + 具体 missing |
| INACCESSIBLE | 问题点名了不可读/无权限文件，且无可读替代证据 | 获得权限/OCR 后重新判级 | 写明文件名、所需权限或工具，不引用其内容 |

## missing 的写法规范（硬性）

必须具体到以下三类之一（可组合）：

1. **缺哪类文件**："库内无原始实验记录（仅有综述性 PDF），无法回答样本量相关问题"。
2. **缺哪个版本**："库内仅有 2022 初稿，2023 修订版（含修正后的转化率）缺失"。
3. **缺哪个字段**："编目元数据中无 DOI 字段，且正文未给出，无法确认出处"。

不可接受："不确定""未知""没找到""待查"。

## 覆盖矩阵指标定义

- `coverage` = 问题去停用词 token（CJK 二字组+单字+拉丁词）中被某文档命中的比例。
- `best_coverage` = 该问题所有文档中的最大 coverage。
- 建议阈值：SUPPORTED 需 best_coverage ≥ 0.5 且有逐字引文；0 < best_coverage < 0.5 或无引文 → PARTIAL；0 命中 → UNSUPPORTED。

## questions.json 附录

由模型从 case.json 提取，写入 `/app/work/questions.json`：

```json
{"questions": [{"id": "Q1", "text": "催化剂 X 在 400 °C 下的转化率是多少？"}]}
```

id 沿用 case.json 的问题编号；text 必须保留原文，不得改写问题语义。
