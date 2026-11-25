# 运行时交付契约解读（runtime_contract）

> 本文是 challenge-5b90f5e9「系统性文献检索与纳排筛选」运行时交付契约的守门员视角解读，
> 仅解释契约条款如何映射为可执行检查，不包含任何案例答案。

## 1. 运行时拓扑

| 路径 | 角色 | 守门员关注点 |
|---|---|---|
| `/input/case.json`、`/input/task.md` | 只读输入：固定研究问题、九篇真实署名文献题录、真实检索式、合同定义 | 合同字段清单与 `case_id` 的唯一权威来源；**禁止修改** |
| `/app/work` | 中间产物：contract_spec.json、fill_ledger.json、筛选决策、去重报告等 | 填充台账的住所；result.json 引用的产物路径必须真实存在于此（或 /input） |
| `/app/output` | 交付目录：`result.json`（必须）+ 校验报告等 | 评测器只认这里的交付物 |

预算：**64 请求 / 900 秒**。超时杀进程 → 零交付是最常见失败。推论：交付物必须"从第一分钟起就存在"，
即零分钟骨架 + 增量填充，而非最后一分钟一次性写出。

## 2. result.json 必备要素

1. `case_id`：与 `/input/case.json` 一致（V1）。
2. `output_contract` 声明的全部字段：一个不少、不得删字段（V2）。
3. 每个字段要么有真实值，要么为 `null` 且原因可溯（台账 `null_with_reason.reason` + `uncertainty` 说明）（V4/V5）。
4. `status ∈ {completed, partial, failed}`，且与内容诚实一致（V3/V4，细则见 status_honesty_rules.md）。
5. `sources`：支撑交付物的来源清单（题录/输入文件/中间产物）。
6. `uncertainty`：不确定性列表；有限快照、无实时库带来的限制必须写在这里。
7. `change_records`：变更流水——骨架初始化、每次字段填充、终态定级都可审计。
8. `partial` 必须附非空限制说明（`uncertainty` 或 `limits`）；`failed` 必须附 `reason`。

## 3. 合同的可能形态与探测策略

`output_contract` 在 case.json/task.md 中可能以以下形态出现，contract_probe 全部归一化为字段名列表并留痕：

- **A. 包装对象**：`{"output_contract": {"fields": [...]}}` / `{"required": [...]}` / JSON Schema 风格 `{"properties": {...}}`；
- **B. 键即字段**：`{"output_contract": {"decisions": "array of ...", "limits": "string|null"}}`；
- **C. 字符串列表**：`["decisions", "dedup_report", ...]`；
- **D. 对象列表**：`[{"field": "decisions", "type": "array"}, {"name": "limits"}]`；
- **E. 自由文本**：逗号/换行分隔的字段名串，或 task.md 中"输出合同 / result.json"小节下的
  `- field: 描述` 列表、`| field | 描述 |` 表格。

探测优先级：case.json（递归找 `output_contract`/`contract` 键）> task.md 小节解析 >
运行时最低保障字段回退（`case_id/status/sources/uncertainty/change_records`，
warning `contract_missing_fallback_runtime_minimum`，需人工确认）。
`case_id` 支持 `case_id`/`caseId`/`case-id`/顶层 `id`，以及 task.md 中 `case_id: xxx` 文本。
**case_id 探测不到 = 合同不可用 = exit 3**，因为身份无法守门。

## 4. 特殊案例输入的守门含义

- search09 含组织方标注为输入夹具的**合成重复导出**与**冲突双人意见**：它们属于"输入数据"，
  去重裁决与冲突调解是模型的实质工作；守门员只保证对应合同字段（如 `dedup_report`、
  `conflict_resolutions`）被真实填充或被诚实标注为 null_with_reason，**不裁决内容对错**。
- 有限快照、无实时库：检索无法外推的限制属于 `uncertainty`，不是 `failed` 的理由；
  但若它导致某合同字段完全无法填充，该字段必须 `null_with_reason`，且通常触发降级为 `partial`。

## 5. 退出码约定（本技能统一）

| 退出码 | 含义 | 典型触发 |
|---|---|---|
| 0 | 成功/校验通过 | probe/scaffold/mark 成功；validate 全绿 |
| 2 | 用法/IO/内部错误 | 参数非法、文件不可读、未捕获异常（顶层 try/except） |
| 3 | 合同不可用或门禁违规 | case_id 缺失、静默空字段、status 不诚实、引用路径不存在 |
