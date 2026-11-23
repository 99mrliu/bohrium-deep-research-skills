# 错误码目录（qc_gate.py v1.0.0）

每个判定附 `evidence` 字段（命中的词/数值/重复对），第三方可据此复算。

## E_*（硬错误 → verdict=reject，必须修复、降级或删除）

| 代码 | 触发 | 修复 |
|-|-|-|
| E_EMPTY_TEXT / E_SUBJECT_MISSING / E_OBJECT_MISSING | 必填为空 | 补齐或删除 |
| E_PRONOUN_SUBJECT | subject 或句首为 It/They/This/We 等 | 解析为实体（依据先行词） |
| E_RELATION_MISSING / E_RELATION_UNKNOWN | 关系缺失或越出词表 | 映射到受控词表；任务词表优先 |
| E_POLARITY_UNKNOWN / E_MODALITY_UNKNOWN / E_STATUS_UNKNOWN | 枚举越界 | 用受控取值 |
| E_SOURCE_METADATA_MISSING | 断言无来源身份 | 补 title/identifier/source_id |
| E_SCOPE_MISSING | not_reported 缺 searched_scope | 写明检索过的章节/表/图范围 |
| E_EVIDENCE_MISSING | asserted 无引文 | 补逐字引文或降级 |
| E_QUOTE_NOT_VERBATIM | 引文归一化后不在来源文本 | 恢复逐字；改写/翻译/拼接均不允许 |
| E_DUPLICATE | 语义键完全重复 | 合并并保留全部来源 |

## W_*（待审 → verdict=review，逐条判读并写 adjudication）

| 代码 | 触发 | 处置 |
|-|-|-|
| W_NUMBER_NOT_IN_QUOTE | 断言数值不在引文 | 核对抄录；多步计算须注明公式与操作数 |
| W_HEDGE_MISMATCH | 引文有 may/suggest 等、断言无 | 保留模态或改 modality=hedged/proposed |
| W_EVIDENCE_TOO_BROAD | 引文超 55 词 | 收窄到最小充分片段，或说明跨句必要性 |
| W_ATOMIC_BUNDLE | 文本含第二关系谓语线索 | 拆成两条各自可判真断言 |
| W_NEAR_DUPLICATE* | 主体+关系重复、客体相近 | 合并或区分限定（*经主流程成对检测） |
| W_CONFLICT_UNRESOLVED | 同主体同关系客体不同且未标 conflict | 双方标 conflict 互指，或写 adjudication |
| W_SOURCE_TEXT_UNAVAILABLE | 无 source_text 可供逐字核验 | 降级为人工目检并在交付物记录 |
| W_INFERENCE_UNDOCUMENTED | inferred 缺推理说明 | 补推理步骤与假设 |

## verdict 与 status 上限

- `reject`：含任一 E_*；`review`：仅 W_*；`pass`：无发现。
- summary.status_cap：有未处理 reject → `partial`；有未判读 review 或
  not_reported/conflict 特殊条目 → `partial`（或补判读）；否则 `success`。
- 特殊条目（not_reported/conflict）本身阻止「complete success」语义，
  必须在 result.json 的不确定性/边界字段中显式列出。

## 门的边界

不检测：语义蕴含真假、方向错误的所有形态（主客颠倒只在伴随其他线索时间接
暴露）、图表像素内容。这些是 adjudication 与人工复核的职责。
