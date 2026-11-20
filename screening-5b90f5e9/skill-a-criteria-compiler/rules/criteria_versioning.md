# 标准版本管理与漂移回溯协议

criteria_table.json 是筛选的唯一事实来源。筛选途中发现标准歧义需要细化时，必须走本协议，**杜绝标准漂移**。

## 版本号规则（语义化 vMAJOR.MINOR.PATCH）

- **PATCH（v1.0.0 → v1.0.1）**：纯文字润色，不改变任何判定结果（错别字、表述清晰化）。无需重判。
- **MINOR（v1.0.0 → v1.1.0）**：细化 predicate / boundary_notes，可能改变部分记录的判定（如明确"混合人群判 uncertain"）。**必须回溯重判受影响记录**。
- **MAJOR（v1.0.0 → v2.0.0）**：新增/删除标准、改变纳入排除范围、改 reason_code 语义。**必须回溯重判全部受影响记录，新增标准需对全部在筛记录补判定**。

## 每次修改必须做的事

1. 升版本号；
2. 在 `changelog` 追加一条：`{version, date, change, rationale, triggered_by（哪条记录/哪个歧义触发）}`；
3. 运行回溯计划：
   ```bash
   python3 $SKILL/scripts/rejudge_plan.py \
     --old /app/work/criteria_table_v1.0.0.json \
     --new /app/work/criteria_table.json \
     --judgments /app/work/judgments.jsonl --work /app/work
   ```
4. 按 `rejudge_plan.json` 的 `affected_record_ids` 强制重判（模型环节），更新 judgments.jsonl；
5. 重跑 `screen_engine.py` 与 `prisma_check.py`；
6. 把旧版 criteria_table 留存为 `criteria_table_v<X>.json`（不删除，保证可回溯）。

## 漂移红线

- **禁止口头改标准不回改表**：任何在判定中实际使用但未写入 criteria_table 的规则，视为漂移，全部相关判定作废重判。
- **禁止静默改码**：reason_code 变更必须升版本并注册（rules/reason_codes.md）。
- **禁止追溯性宽严不一**：同一版本标准下，所有记录必须使用同一判定口径；发现口径不一即触发 MINOR/MAJOR 升版与全量重判。
- result.json 的 `change_records` 必须逐条列出全部版本变更与重判动作。
