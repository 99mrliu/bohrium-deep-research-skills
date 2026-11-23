# 断言记录字段字典

任务 schema 优先；以下为缺省字段语义，供适配与 lint 使用。`atomize_lint.py` 读取
JSONL（每行一条断言）。嵌套与命名按任务 output_contract 适配，语义不得丢。

| 字段 | 类型 | 必填 | 语义 |
|-|-|-|-|
| id | string | 是 | 案例内稳定局部 ID（如 A-001） |
| text | string | 是 | 自足陈述句，离开原段可读 |
| subject | string | 是 | 实体，不得为代词 |
| relation | string | 是 | 受控词表成员 |
| object | string/object | 是 | 客体；集合性客体整体保留 |
| qualifiers | array | 可空 | 条件/范围/版本/时间等限定，逐条字符串或 {type,text} |
| polarity | string | 是 | positive / negative |
| modality | string | 是 | asserted / hedged / speculative / proposed |
| evidence.quote | string | 是 | 原文最小充分逐字引文（原语言） |
| evidence.location | object | 是 | 物理页 + 章节/段落/表行列定位；无机械行号时不编造 |
| evidence.kind | string | 建议 | direct / indirect（间接推论须写推理链） |
| source | object | 是 | title、creators、year、identifier/version、file 标识 |
| confidence.level | string | 是 | high / medium / low |
| confidence.rationale | string | 是 | 证据强度理由（证据类型、直接性、限定完整性），非虚构概率 |
| status_note | string | 可空 | 该断言的冲突/存疑/待审说明 |

## 置信度标定依据（可复核）

- high：直接证据、数值与限定逐字可对、单一来源且原文表述明确。
- medium：证据为间接推论、跨句拼合、或最高级/集合性结论无法逐字对数。
- low：来源间冲突未裁定、证据跨图表难以对齐、或文本层质量差（如 OCR）。

## lint 代码表（atomize_lint.py）

| 代码 | 级别 | 触发 |
|-|-|-|
| E_EMPTY_TEXT / E_SUBJECT_MISSING / E_OBJECT_MISSING | 硬错误 | 必填为空 |
| E_PRONOUN_SUBJECT | 硬错误 | 主语或句首为代词 |
| E_RELATION_MISSING / E_RELATION_UNKNOWN | 硬错误 | 关系缺失或越出词表 |
| E_MODALITY_UNKNOWN / E_POLARITY_UNKNOWN | 硬错误 | 枚举越界 |
| E_EVIDENCE_MISSING | 硬错误 | 无引文 |
| E_DUPLICATE | 硬错误 | 规范化键完全重复 |
| W_ATOMIC_BUNDLE | 待审 | 文本含第二关系谓语线索 |
| W_NUMBER_NOT_IN_QUOTE | 待审 | 断言数值不在引文 |
| W_HEDGE_MISMATCH | 待审 | 引文有模态词、断言无 |
| W_SCOPE_DROPPED | 待审 | 引文含范围限定未保留 |
| W_NEAR_DUPLICATE | 待审 | 主体+关系重复、客体相近 |
| W_CONFIDENCE_UNKNOWN | 待审 | 置信度取值越界 |

硬错误必须修复或删除断言；待审项逐条判读并在交付物留痕。
