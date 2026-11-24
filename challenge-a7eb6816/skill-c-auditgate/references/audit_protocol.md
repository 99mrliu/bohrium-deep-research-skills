# 审计门协议（audit protocol）

本协议定义 AuditGate 的判定标准、阈值、降级规则，以及与写作流程的接口。
审计门独立于写作过程：写作者交付「源文 + 改写稿 + 改动清单」三件套后，
审计方才启动；审计不修改稿件，只出具判定与待确认问题。

## 1. 句级对齐（align_map.py）

- **分句**：中英文句读兼容；Markdown 标题行不参与对齐；小数点受保护
  （96.5 不会被切成两句）。
- **相似度**：字符 3-gram Jaccard，比较前做 NFKC 归一化、小写化、
  去空白与标点（保留字母、数字、CJK 字符）。
- **阈值（默认，可调，调整须写入报告）**：

| 判定 | 条件 | 含义 |
|---|---|---|
| supported | score ≥ 0.35 | 稿句有明确源句支撑 |
| weak | 0.15 ≤ score < 0.35 | 弱支撑，需人工抽看（意译常见落此档） |
| unsupported | score < 0.15 | 找不到源支撑，须列入待确认或修正 |

- **反向覆盖**：关键源句 = 含数字 / 图表引用（图 N、表 N、Figure、Table）/
  强度词（显著、首次、最优、突破、大幅、优于、novel、first 等）的源句。
  关键源句与任一稿句的得分 ≥ weak 阈值即视为被覆盖，否则记入
  `uncovered_key_source`。

## 2. 改动清单校验（editlog_check.py）

- 每条目：`action` ∈ {retain, rephrase, move, condense, omit, translate}；
  `reason` 去空白后 ≥ 4 字；`locator` 可解析（S/D/P + 序号，或 GLOBAL）。
- **覆盖性**：`uncovered_key_source` 中每条源句必须存在至少一条
  **合法**（自身无错误）的 `omit`/`condense` 条目，且 locator 引用该源句。
- 待确认问题（`needs_confirmation: true` 或 reason 以「待确认」开头）
  不算错误，单独汇总交原作者。
- 退出码：0=PASS，4=FAIL。

## 3. 审计门（audit_gate.py）

四项检查，全部 PASS 才过门：

1. `unsupported_draft_sentences`：无 unsupported 稿句，或全部列入待确认；
2. `key_source_coverage`：关键源句全覆盖，或有合法 omit/condense 记录；
3. `editlog_legal`：edit_log 全部条目合法；
4. `numeric_anchors`：稿件中的数字均能在源文中找到**字面**出现。

总判定与退出码：

| 总判定 | 条件 | 退出码 | 处置 |
|---|---|---|---|
| PASS | 四项全 PASS 且非降级 | 0 | 可交付 |
| FAIL | 任一检查 FAIL | 5 | 不过门，不得交付 |
| MANUAL_REVIEW | 无 FAIL 但处于降级态 | 6 | 附人工复核清单交付 |

## 4. 降级规则

触发条件（满足其一）：

- 源文 < 3 句或改写稿 < 2 句（对齐统计不可靠）；
- 稿句平均最佳对齐分 < supported 阈值（疑似整体意译或阈值不适配）。

降级时**不判 FAIL**，改判 MANUAL_REVIEW 并附降级原因；但已查实的硬错误
（删减无记录、edit_log 非法、数字无源）仍判 FAIL。调阈值重跑是合法操作，
但新阈值必须写进 alignment.json 的 `meta.thresholds`（脚本自动记录），
禁止为凑结果而改输出文件。

## 5. 与写作流程的接口

```
写作者                          审计门（本技能）
  │  源文 + 改写稿 + edit_log.jsonl
  ├────────────────────────────►│  1. align_map（双向映射）
  │                             │  2. editlog_check（清单合法性）
  │                             │  3. audit_gate（过门判定）
  │◄────────────────────────────┤  PASS / FAIL / MANUAL_REVIEW
  │  FAIL 时附：失败检查项、待确认问题清单
  │  MANUAL_REVIEW 时附：降级原因 + 弱支撑句清单
```

- 审计门只消费三件套，不回写稿件；
- 写作者根据 FAIL 检查项返修后可重新送审（幂等，同一输入必得同一输出）；
- 待确认问题随 PASS 一并交付原作者，由原作者做最终确认。
