# 术语一致性执行规则（Bundle A）

## 出现区带（zones）

源文可用 `<!-- zone:name -->` 显式标记区带；无标记时整篇按 `body` 处理。
审计对每个锁定术语统计各区带渲染次数，标题/摘要/正文/图注/结论必须同译名。
真实 PDF 抽取无标记时，Agent 应按标题样式（Abstract/Introduction/Conclusion、
Figure/Table 开头行）在 translations.json 的每个 segment 上标注 zone。

## 违规分级

| 类别 | 判定 | 处置 |
|-|-|-|
| forbidden_variant | 禁用变体出现于译文 | 单变体情形 `--apply-lock` 自动回填；其余进 human_confirm |
| multiple_variants | 锁定译名与禁用变体并存 | 先 apply-lock 回填，再重跑审计确认 |
| missing_rendering | 源出现、译文零渲染 | 硬性违规；补译后重审 |
| count_mismatch | 渲染次数 < 源出现次数 | 仅提示核对（human_confirm），不自动改 |
| untranslated_term | 译文仍含英文原词 | 硬性违规；keep_original 决议豁免 |

## 执行纪律

- 审计在锁上进行：LOCK_BROKEN 时拒绝出报告（exit 2）。
- 回填只替换 `forbid` 列出的变体，绝不做同义词"润色"。
- 审计通过 ≠ 语义正确；审计只保证术语口径一致。
