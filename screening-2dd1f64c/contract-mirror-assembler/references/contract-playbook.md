# 契约镜像装配手册（contract-mirror-assembler）

## 契约形态识别

`inspect` 按以下优先级在 case.json 顶层寻找契约：`output_contract`、`outputContract`、`output_contract_fields`、`contract`、`expected_output(s)`。支持四种形态：

1. 字典 `{字段名: 类型或说明}`——最常见；hint 原样保留进 plan.json。
2. 列表 `["field_a", {"name": "field_b", ...}]`——取 name。
3. JSON-Schema 风格 `{"properties": {...}}`——展开 properties。
4. 单字符串——视为一个字段名。

找不到契约时不得编造字段：结果只含标准载荷键，并在 `status.limits` 记录"案例未声明 output_contract"。

## 字段装配策略（assemble）

按顺序决策，可审计：

1. 结果载荷已覆盖（case_id、screened_records、ranking、evidence_records、status 等）→ 直接使用。
2. 字段名与 case.json 顶层真实输入字段同名（如 research_question）→ 回显真实输入。
3. 字段名含 omission/coverage/note → 由脚本生成诚实的覆盖与遗漏说明（有限快照声明、缺失元数据清单、排除记录指针）。
4. 其他 → 显式 `null` + `status.incomplete` 条目（部分名 + 原因）。禁止猜测填充。

## 排序与平局协议

- 排序键：`(label 层级 keep=0<pending=1<exclude=2, -score, record_id)`，全确定性。
- 同 (label, score) 的记录共享同一 rank，并各自带 `tie_group`（同组 record_id 排序列表）；后续 rank 按占用数顺延（竞赛排名法），保证换批候选后语义一致。
- score 由判定方给出（0–100），脚本只做钳制与排序，不改写语义。

## 诚实 partial 规则

- 判定缺失的记录一律 `pending`，rationale 明示"not yet judged"，计入 `status.incomplete`。
- 任何契约字段不可产出 → `status.state=partial` 并给出原因；全部字段齐备且判定完整 → `complete`。
- 合成夹具（fixture_note）只允许作为 provenance 写入 rationale，不得作为判定依据的来源。

## 交付前校验清单（validate）

case_id 回显一致；契约字段零缺失；screened_records 覆盖全部输入记录且无重复、无外来 id；label 枚举合法；score∈[0,100]；status.state 存在。任一不满足即 FAIL 并打印全部问题，修复后重跑。
