# output_contract 契约 playbook

本文是 deliverline-contract-render 技能的契约处理细则：契约抽取、字段回填、
诚实 partial 规则。配套脚本：`scripts/contract_scaffold.py`。

## 1. 为什么契约优先

成果转化写作任务的最终评分物是 `/app/output/result.json` 加一组产物文件。
最常见的丢分不是「写得差」，而是「交得不对」：缺字段、类型错、路径 404、
status 自相矛盾。因此**第一步永远是抽取契约**，让契约驱动后续所有交付动作，
而不是写完再补 result.json。

## 2. 契约定位（contract_scaffold.py）

按优先级在 case.json 中递归查找这些键：
`output_contract`、`outputContract`、`output-contract`、`contract`、
`output_schema`、`result_contract`。先查当前层，再递归深入 dict 值与 list
元素；找到的第一个即采用，位置记入 `contract_map.json` 的
`contract_location`。

## 3. 支持的契约形态

| 形态 | 例子 | 解析方式 |
|---|---|---|
| `json_schema` | `{"type":"object","required":[...],"properties":{...}}` | 读 `required` 列表与 `properties`；嵌套 object 递归为点分路径（如 `meta.reviewer`）；`enum`/`description` 一并抽取 |
| `flat_dict` | `{"title":"string","word_count":{"type":"integer","required":true}}` | 值为字符串直接当类型；值为 dict 读 `type`/`required` |
| `descriptor_list` | `[{"name":"title","type":"string","required":true}, ...]` 或字符串列表 | dict 项读 `name/field/path`；字符串项按行解析 |
| `string_schema` | `"title: string (必填)\nword_count: integer"` | 逐行正则：字段名 + 类型关键词 + `required/必填/必须/mandatory` 判定必填 |

类型别名归一化：`str→string`、`int→integer`、`float/double→number`、
`bool→boolean`、`list→array`、`dict→object`；无法识别记为 `any`
（验收门对 `any` 不做类型检查）。

解析结果统一为 `contract_map.json`：

```json
{
  "case_id": "...",
  "contract_found": true,
  "contract_location": "output_contract",
  "contract_shape": "json_schema",
  "field_count": 10,
  "fields": [{"path": "title", "type": "string", "required": true}]
}
```

## 4. 保底脚手架规则

无论契约是否找到，`--outdir` 下都会写出结构合法的 `result.json`：

- `case_id`：从 case.json **原样复制**（不做任何改写、trim、大小写处理）；
- 全部契约字段（含可选字段）以类型允许的空值占位：`""` / `0` / `0.0` /
  `false` / `[]` / `{}`；
- `status`：`"partial"`（若契约枚举不含 `partial` 则退用枚举首值并在
  notes 中说明）；
- `notes`：如实写明「本文件为保底脚手架，字段为占位值，尚未回填」。

这样即使后续写作/渲染流程崩溃，输出目录里也始终有一份结构合法的
result.json 兜底，不会「零交付」。

## 5. 字段回填规则

1. **逐个字段对照 contract_map.json 回填**，不要凭记忆写字段名；
2. 回填值必须与声明类型严格一致：
   - boolean 只能写 `true/false`，写 `1/0`、`"true"` 都是 FAIL；
   - integer 不能带小数点（`1200.0` 不是 integer）；
   - 数组元素类型也要对（deliverables 里放 dict 会触发路径检查异常）；
3. 路径类字段（deliverables/files/paths/artifacts/outputs）写**相对输出
   目录的相对路径**，并在过门前确认文件真实存在；
4. 回填完成后才允许把 `status` 从 `partial` 改为 `complete`，且改为
   `complete` 前必须清空 `limitations`；
5. `notes` 中保留一句「占位说明已失效」之类的交接话不如直接改写为真实
   交付说明——notes 是给人看的，写清楚本结果怎么来的、还有什么注意点。

## 6. 诚实 partial 规则

- 任何一部分没有真实内容可填，就保持 `status=partial`，并把缺口写进
  `limitations` 数组，一条一项，例如：
  - `" limitations"`：`"中试成本数据缺失，财务测算章节为定性描述"`
  - `"专利法律状态未获 FTO 意见，侵权风险未评估"`
- **禁止**：为了好看把 `status` 写 `complete` 却留占位值；把 limitations
  里的问题删掉而不是解决掉；把不存在的文件路径写进 deliverables。
- `partial` 不是失败，虚假 `complete` 才是。验收门只对
  `complete + 非空 limitations` 判 FAIL，对 `partial + 空 limitations`
  给警告（诚实 partial 应说明缺口）。

## 7. 常见契约异常与处置

| 异常 | 处置 |
|---|---|
| 契约键不存在 | scaffold 退出码 3，写最小脚手架；按平台默认契约（case_id/status/notes）手工补齐，notes 中说明契约缺失 |
| 契约嵌套在 list 元素里 | 递归定位能找到，`contract_location` 会记录如 `sections[2].output_contract` |
| 契约是自由文本 | string_schema 逐行解析；解析不到字段时视同缺失并如实记录，**不猜** |
| 契约字段与任务描述冲突 | 以契约为准，冲突记入 notes/limitations |
| 契约要求字段在输入中无数据支撑 | 诚实 partial：占位值 + limitations 说明缺什么输入 |
