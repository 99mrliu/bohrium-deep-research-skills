# 契约处理规范（contract_handling.md）

本文件规定 output_contract 的解析规则、字段填充与 null/uncertainty 规范、
provenance 格式。实现见 `scripts/contract_scan.py` 与 `scripts/fill_result.py`。

## 1. output_contract 形态解析规则

字段集**运行时动态读取**，任何代码不得假设固定字段名。兼容三种形态：

### 1.1 list-of-str

```json
"output_contract": ["answer_summary", "item_bank"]
```

每个字符串即字段名；`type_guess="any"`，`required=true`。

### 1.2 list-of-obj

```json
"output_contract": [{"name": "answer_summary", "type": "string", "required": true}]
```

对象键名兼容 `name` / `field` / `key`；`type` 归一化到
`{string, number, integer, boolean, array, object, any}`，非法值降为 `any`；
`required` 缺省视为 `true`。

### 1.3 dict

```json
"output_contract": {"answer_summary": "string",
                    "item_bank": {"type": "array", "required": true}}
```

值为字符串时视为类型名；值为对象时按 1.2 规则取 `type` / `required`。

### 1.4 降级（degraded）

缺 `output_contract`、解析结果为空、case.json 缺失或畸形时，
`contract.json` 置 `degraded: true`，`fields` 为空，仅保证 `case_id`，
并在 `notes` 中记明原因。降级不是失败，后续流程照常推进。

## 2. 字段填充与 null/uncertainty 规范

1. **工作文件约定**：`/app/work` 下依次扫描 `answers.json`、`items.json`、
   `evidence_map.json`。JSON 对象的顶层键名与契约字段名匹配即作为来源
   （优先级 answers > items > evidence_map）；`evidence_map.json` 无显式
   `evidence_map` 键时整个对象充作该字段；`answers.json` / `items.json`
   为数组时分别充作 `answers` / `item_bank`。
2. **类型校验**：按 `type_guess` 校验；不匹配时该字段置 `null` 并记
   `uncertainty`（注明期望类型与实际类型），不做隐式强转。
3. **超长截断**：字符串值超过 8000 字符时截断至 8000 并追加
   `…[TRUNCATED original_len=N]` 标记，同时记一条 uncertainty 告警。
4. **null 规范**：工作文件未提供的字段一律填 `null`，并在 `uncertainty`
   中记 `{field, reason}`。**绝不编造内容**——宁可 null 不可虚构。
5. **status 诚实**：必填字段全部非 null → `成功`；有 null 必填字段 →
   `部分完成`（status_reason 必须列明缺失字段与局限）；契约降级 →
   `无法判断`；任务不可执行 → `拒答`（附理由）。status 取值仅限
   {成功, 部分完成, 无法判断, 拒答}。
6. **骨架先行**：`fill_result.py --init` 在任何起草之前即写入合法的
   部分 result.json（字段全 null、status=无法判断），保证预算耗尽时
   仍有可交付的合法结果；后续 fill 以增量方式完善（change_records
   追加序号记录，保留 init 记录）。

## 3. field_provenance 格式

每个已填充字段必须可追溯：

```json
"field_provenance": {
  "answer_summary": {
    "work_file": "/app/work/items.json",
    "work_key": "answer_summary",
    "evidence_anchors": ["source_excerpt.txt:L3-L14"]
  }
}
```

- `work_file`：来源工作文件的绝对路径；
- `work_key`：该值在工作文件中的顶层键（根数组记 `<root>`）；
- `evidence_anchors`：证据锚点列表，格式 `文件名:L行号` 或
  `文件名:L起-止`。`item_bank` 字段聚合全部题卡锚点（去重、按字典序）；
  其余字段取 evidence_map 中与字段同名的键。锚点必须指向源材料中
  可人工核对的行号。

## 4. 两类工单的字段期待

- T1（阅读问答/解析/翻译/抽取）：契约字段多为答案、摘要、证据等；
  填充规则不变。
- T2（benchmark-DRAFT 出题）：题卡数组的每题应含任务、材料范围、
  参考答案、评分规则、证据锚点、难度、授权七要素；本技能只负责
  契约化与门禁，不替 agent 撰写题目内容。
