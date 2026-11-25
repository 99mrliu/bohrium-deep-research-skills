# 不确定性规则（Bundle E）

## 类型

| type | 触发 | 状态影响 |
|-|-|-|
| unreadable | 源文本符号不可读（�、扫描缺字） | 阻塞 success |
| ambiguous_term | 术语/缩写义项不定 | 阻塞 success |
| unresolved_reference | 指代无法解析 | 阻塞 success |
| unverified_evidence | 证据核验失败 | 阻塞 success |
| coverage_gap | 源文本有覆盖缺口 | 阻塞 success |
| overlapping_evidence | 证据重叠 | 不阻塞（提示） |
| untranslated_segment | 段未译 | 阻塞 success |

## 状态推导

- `success`：全部段已译 ∧ 证据全部 verified ∧ 无 gap ∧ 登记册无阻塞项。
- `partial`：其余有实质产出情形；登记册列出全部原因。
- `failed`：无一段译文。
- **禁止**：把不确定内容写成事实、删除不确定性记录以求"清零"、
  用摘要替代未译段（未译必须显式标注）。

## 人工确认清单

verification_report.md 末尾列出全部登记项；人工逐条处置（确认/修订/维持存疑），
处置记录建议写回 translations.json 对应段的 note 并留 history。
