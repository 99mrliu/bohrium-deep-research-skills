# result.json 交付契约（完整规范）

本文件是 `scripts/contract_check.py` 所执行契约的权威说明。

## 1. 必填顶层字段

| 字段 | 类型 | 要求 |
|---|---|---|
| `case_id` | string | 非空；提供案例文件时必须与 `case.json` 中的 `case_id` 完全一致 |
| 契约声明的每个字段 | 任意 | 见第 4 节“契约镜像规则”，一个都不能少 |
| `status` | string | 枚举：`"success"` \| `"partial"` \| `"failed"` |
| `uncertainties` | array | 可为空列表，但 `status=partial` 时**必须非空** |
| `change_records` | array | 可为空列表；人工 override 由 apply_overrides 追加 |
| `partial_limits` | string/array/object | 仅 `status=partial` 时强制：存在且非空 |

## 2. status 枚举语义

- `success`：契约字段全部完成、无占位符、证据定位齐全。
- `partial`：诚实部分交付。做不完不丢人，**冒充完成才违规**。
  必须同时满足：
  1. `uncertainties` 为非空列表——逐条说明“哪里不确定”；
  2. `partial_limits` 存在且非空——说明“覆盖范围的边界”（评估了哪些、
     没评估哪些、为什么）。
- `failed`：无法产出有意义结果；`uncertainties` 应说明失败原因。

## 3. 诚实 partial 规则

- 缺内容时宁可 `partial` + 说明，也不许写占位符充数；
- 截止时检查器仍失败：保持 `partial`，并把检查器 `--report` 的 JSON
  报告随交付物一起输出，让下游知道差在哪；
- `partial_limits` 的写法建议：列出已覆盖范围、未覆盖范围、
  未覆盖原因（预算/数据可得性/时间）。

## 4. output_contract 镜像规则

检查器在 `case.json` 中**防御式递归**搜索以下键名（按优先级）：
`output_contract` → `contract` → `output_fields` → `required_fields`。

支持两种形态：

```json
{"output_contract": ["summary", "items", "evidence", "conclusion"]}
```

```json
{"output_contract": {"fields": ["summary", "items", "evidence", "conclusion"]}}
```

或对象形态（取键名）：

```json
{"output_contract": {"summary": {"type": "string"}, "items": {"type": "array"}}}
```

规则：

- 契约声明的**每个字段都必须出现在 result.json 顶层**（缺失逐项列出）；
- result.json 顶层出现契约未声明、且不属于保留字段
  （`case_id/status/uncertainties/change_records/partial_limits/evidence/meta`）
  的键，同样列为违规——交付面必须可审计，不许私带字段；
- 未提供 `--case` 时退化为最小契约：仅检查 `status`、`uncertainties`、
  `change_records` 等保留字段。

## 5. 禁用占位符模式

对 result.json 中所有字符串值递归扫描（大小写不敏感）：

- `\bTODO\b`、`\bTBD\b`、`\bFIXME\b`
- `lorem`（lorem ipsum 填充文本）
- `\bx{3,}\b`（`xxx` 及以上连续 x 占位）

**例外**：顶层 `change_records` 子树不参与扫描——它是审计历史，
`old_value` 与 `rationale` 合法地引用被修复前的旧占位符。

## 6. evidence 定位规则

`evidence` 若存在必须是列表；每行必须是对象，且至少携带一个非空的
`source`（来源标识）或 `locator`（页码/章节/表号等定位）字段。
证据引文建议放 `quote` 字段，渲染报告时会以引用块突出显示。

## 7. change_records 模式

由 `apply_overrides.py` 追加，每条：

```json
{
  "target_path": "summary",
  "old_value": "（修改前）",
  "new_value": "（修改后）",
  "reviewer": "复核人",
  "rationale": "修改理由",
  "date": "2026-11-25",
  "applied_at": "2026-11-25T15:31:34",
  "kind": "human_override"
}
```

## 8. 最小合法示例

case.json 声明契约 `["summary", "items"]` 时，最小合法 result.json：

```json
{
  "case_id": "SYNTH-DEMO-001",
  "status": "partial",
  "summary": "仅完成 2 条记录中的 1 条评估。",
  "items": [
    {"id": "P1", "conclusion": "弱支持", "confidence": "low"}
  ],
  "evidence": [
    {"item_id": "P1", "quote": "……", "source": "虚构论文甲", "locator": "第 3 页 表 1"}
  ],
  "uncertainties": ["P2 的实验条件无法核实"],
  "partial_limits": "仅覆盖 2 条记录中的 1 条；预算耗尽。",
  "change_records": []
}
```

## 9. 检查器退出码

| 退出码 | 含义 |
|---|---|
| 0 | 全部通过 |
| 1 | 发现违规（含 result.json 非法 JSON，干净报错、无 traceback） |
| 2 | 用法错误（参数缺失等，argparse 行为） |
