# output_contract 镜像规则与字段语义

本文档定义 `contract-first-deliverable-forge` 对 `case.json` 中 `output_contract`
的镜像填充规则，以及各已知字段的语义与校验判据。

## 一、镜像规则（硬性）

1. **逐字段在场**：`output_contract` 的每个 key 必须出现在 `result.json` 顶层，
   不允许丢字段；契约之外可以附加字段（如 `seed`、`sources`、`merge_log`）。
2. **类型一致**：填充值的 JSON 类型须与契约声明兼容
   （`string`→字符串、`array`→数组、`object`→对象、`number`→数值、`boolean`→布尔）。
3. **非占位符**：空串、`"TODO"`、`"TBD"`、`"<placeholder>"`、`"N/A"`、`null`
   均视为占位符/空值；空数组、空对象同样视为空值。
4. **诚实空值豁免**：确实无法填充的字段允许给类型空值，但**必须**在
   `result.json.uncertainty` 的某一条目中点名该字段名；`contract.py --verify`
   将其标为 `empty(excused)` 而不判负。未点名的空值判 `empty`，`ok=false`。
5. **case_id 一致**：`result.json.case_id` 非空且与 `case.json.case_id` 完全一致。
6. **status 合法**：仅允许 `ok` / `partial` / `failed`；有 stub、解析失败、
   缺元数据时不允许报 `ok`；种子未解析报 `failed`。
7. **填充优先级**：pipeline 内置 FILLERS 注册表 > 类型空值＋uncertainty 豁免。
   新增自定义字段的推荐做法是在 `scripts/pipeline.py` 的 `FILLERS` 中注册填充器。

## 二、骨架生成（--skeleton）

`contract.py --skeleton` 按契约声明的类型生成占位值（string→`""`、array→`[]`、
object→`{}`、number→`0`、boolean→`false`），连同逐字段**填充计划**写入
`<workdir>/result_skeleton.json`：

```json
{
  "_meta": {"purpose": "...", "contract_fields": 9},
  "_fill_plan": {"candidates": "去重后的候选文献清单…", "...": "..."},
  "skeleton": {"case_id": "...", "candidates": [], "...": "..."}
}
```

骨架供人工核对契约范围；`pipeline.py` 运行时自行镜像填充，不依赖骨架文件。

## 三、已知字段语义

| 字段 | 类型 | 语义 |
|------|------|------|
| `case_id` | string | 与 case.json 一致，原样复制 |
| `seed_paper` / `seed` | object | 种子记录视图：`{id, doi, title, year, found, source{file,pointer}}`；未解析时 `found=false` |
| `candidates` | array | 去重后候选文献：`{id, doi, title, year, layer, stub, relation, source}`；stub 候选另带 `unresolved_ref` 原始指针，无补造元数据 |
| `edges` | array | 引用边：`{source, target, kind, direction_restored, locator}`；`kind=reference` 为 citing→cited，`kind=citation` 为 cited→citing（由全语料反向索引恢复时 `direction_restored=true`） |
| `sources` | array | 来源注册表：`{file, format, records, edges, status, error}`，解析失败不中断、登记原因 |
| `evidence_records` | array | 逐候选＋逐边证据：`{type, claim, basis, locator}`，locator 为 `{file, pointer}`（JSON 路径或行号），保证可回指复核 |
| `status` | string | `ok`/`partial`/`failed`，诚实反映完成度 |
| `uncertainty` | array | stub、解析失败、身份合并、空值豁免等说明的字符串列表 |
| `layer_counts` | object | 各扩展层新增候选数，如 `{"layer_1": 4, "layer_2": 0}` |
| `method_summary` | string | 一段中文方法摘要（扩展方向、去重键、规模、locator 承诺） |

## 四、verify 判定

逐字段状态：`filled`（在场且非占位）/ `empty`（空值或占位符）/
`empty(excused)`（空值但已被 uncertainty 点名）/ `missing`（key 缺席）。
`ok=true` 当且仅当：case_id 一致 ∧ status 合法 ∧ 无 missing ∧ 无未豁免 empty；
退出码 0 通过、1 未通过、2 用法/IO 错误。
