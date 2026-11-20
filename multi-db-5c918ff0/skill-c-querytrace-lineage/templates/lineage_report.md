# 多源查询编排与全链来源回溯报告

- case_id：{{CASE_ID}}
- skill：{{SKILL_NAME}}
- 链完整性核验结论：{{STATUS}}

## 1. 查询台账（query_ledger.jsonl）

{{QUERY_LEDGER_TABLE}}

## 2. 编排审计（query_audit.json）

### 2.1 机械复制检查（逐库查询串两两 diff）

{{AUDIT_MECHANICAL}}

### 2.2 分页完整性检查（Σ items_returned vs total_hits）

{{AUDIT_PAGINATION}}

### 2.3 限流 / 配额痕迹分类

{{AUDIT_RATELIMIT}}

## 3. canonical 记录溯源表（canonical_records.json）

{{CANONICAL_TABLE}}

## 4. unresolved 模糊对（交模型仲裁，不臆断）

{{UNRESOLVED_PAIRS}}

## 5. 断链清单（chain_gaps.jsonl，逐条报告，不静默修补）

{{CHAIN_GAPS}}

## 6. 增量导入 diff 摘要（import_diff.json）

{{IMPORT_DIFF}}

## 7. 重放一致性声明

{{REPLAY_STATEMENT}}
