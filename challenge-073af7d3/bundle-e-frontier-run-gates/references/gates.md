# 阶段门 G0–G8 定义

门（gate）是机器可检查的过程检查点。它们保证"该做的做了、引用链得上、契约对得上"，但**不**判断结论的科学正确性。任何门失败：记录违规、降级 status、按"失败动作"处置后继续或停止，绝不跳过。

| 门 | 名称 | 通过条件 | 失败动作 |
| --- | --- | --- | --- |
| G0 | 契约读取 | case.json 可解析；manifest 的 `case` 段记录了 `case_id` 与全部 `output_contract` 字段名 | 重读 case.json；无 output_contract 时采用四个 canonical 字段并在结果中记录假设（非 blocked） |
| G1 | 语料归一 | `canon.jsonl` 存在且非空；每条记录有非空 id 且 year 为整数 | 修复 ingest 解析；个别记录缺年份则剔除出趋势并在 uncertainty 登记（>20% 时升级为覆盖度不确定性） |
| G2 | 时间切片 | `slices.json` 存在；逐年计数之和 == 有年份记录数（计数闭包），且与 canon 一致 | 闭包破坏说明归一或切片有 bug，修复后重跑该阶段；不得带着破坏的闭包写趋势结论 |
| G3 | 主题队列 | `cohorts.json` 存在且含 `years` 列表 | 重跑 cohorts 阶段；语料过稀导致词队列为空时在 uncertainty 登记 |
| G4 | 代表作草稿 | `representatives.json` 存在且 `phases` 非空、每相有 `candidates` 键 | 重跑该阶段；注意产物是占位，最终遴选是智能体的多准则工作（相内引用分位 + 主题中心性 + 方法首创） |
| G5 | 空白记录 | `gaps.json` 存在；若记录为 none/none_recorded，则 `reason` 必须非空 | "无记录"判失败；要么给出带排除证据的空白主张，要么写明 none-with-reason（检索过但不下空白结论的理由） |
| G6 | 证据回链 | `result_draft.json` 中每个 `{"record_id": ...}` 都能在 `evidence_matrix.jsonl` 中解析 | 悬空引用必须修复：补证据矩阵行或删除/替换该引用；不得交付含悬空引用的结果 |
| G7 | 不确定性 | result 草稿的 uncertainty 字段（契约名含 uncertainty 者）非空 | 补充：证据冲突、检索偏差、覆盖度上限、需人工核验条目；写不出不确定性 = 分析不可信 |
| G8 | 契约 lint | `contract_lint.py` 对 (case.json, result_draft.json, evidence_matrix.jsonl) 判定 clean | 逐条修复 lint 违规（见 contract_rules.md）后重跑 G8 |

## 运行方式

```bash
python3 gate_check.py --work /app/work            # 全门，任一失败 exit 1
python3 gate_check.py --work /app/work --gate G6  # 单门
```

输出 JSON：`{"gate|status|gates|violations: [...]}`，violations 含具体原因，供回填修复。
