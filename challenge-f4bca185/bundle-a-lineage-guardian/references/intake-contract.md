# Intake Contract and Discovery Reference

本文件定义 Lineage Guardian 对 case、task、材料、输出 contract 的解释方式。目标是“先证明输入是什么，再清洗输入”，而不是猜测固定案例内容。

## 1. 运行入口与路径

默认入口等价于：

```bash
python3 scripts/lineage_guardian.py --case /input/case.json --task /input/task.md --work /app/work --out /app/output
```

- `--case`：case JSON。可为 object 或其他 JSON 值；object 中优先读取 `case_id`（缺省时尝试 `id`）和 `output_contract`。
- `--task`：任务说明 Markdown。只用于发现材料路径和审计，不用于补造数据。
- `--work`：scratch。当前实现不依赖 scratch 中状态完成最终输出，因此重跑不受旧状态污染。
- `--out`：最终可编辑交付物目录。脚本先写 honest partial，再增量覆盖最终 `result.json`。

所有路径都可覆盖。脚本只写 `--out` 和创建 `--work`；材料路径只读。

## 2. 字节级输入完整性

每个可读控制文件/材料记录：

| 字段 | 含义 |
|---|---|
| `path` | 可移植显示路径；输入目录内文件优先相对 case 目录，外部文件才保留绝对路径 |
| `sha256` | 原始字节 SHA256，不解码后重算 |
| `bytes` | 原始字节数 |
| `encoding` | 本工具固定解释为 UTF-8 |
| `utf8_bom` | 是否以 UTF-8 BOM 开头 |
| `decode_status` | `valid_utf8` 或 `recovered_with_replacement` |
| `decode_error_events` | 是否发生 strict UTF-8 解码失败 |
| `replacement_character_count` | 解码文本中的 U+FFFD 数，包含输入原本已有的 U+FFFD |

BOM 不改变文件哈希；CSV header 匹配时忽略起始 BOM，但 raw snapshot 保留原始 header。非法字节用 U+FFFD 恢复，运行状态至少为 `partial`，因为损坏字符不能自动还原。

## 3. 材料发现顺序

发现是确定性的，重复路径只注册一次：

1. 解析 `--case`。
2. 递归检查 case JSON 中除 `output_contract`、`input_contract`、`schema`、`json_schema` 以外的字符串；跟踪 `.csv`、`.tsv`、`.json` 后缀。
3. 读取 `--task`，用文件名模式发现 `.csv`、`.tsv`、`.json` 引用。
4. 对 case 所在目录递归排序扫描相同后缀，排除 case/task 本体以及 `--out`、`--work` 内文件。
5. 相对路径依次按 case 目录、task 目录、当前工作目录解析。找不到即 `MATERIAL_NOT_FOUND`，不猜测替代文件。

目录扫描是补足机制，不是答案来源。审计的 `discovered_via` 会区分 case JSON、task Markdown 和 directory scan。

## 4. JSON 嵌套表识别

支持三类常见结构：

```json
{"columns": ["Material", "Value"], "rows": [{"Material": "X", "Value": "1.2 ks"}]}
```

```json
{"headers": ["Material", "Value"], "records": [["X", "1.2 ks"]]}
```

```json
{"records": [{"Material": "X", "Value": "1.2 ks"}]}
```

`rows`、`records`、`data`、`entries`、`measurements`、`observations`、`extracted_data`、`extracted_records`、`literature_records`、`items` 下的 dict 列表会按记录表处理；根 JSON 若是 dict 列表也按记录表处理。wrapper 列表（每项自身有 `columns`/`rows`）会递归，不会把 wrapper 当数据行。仅含文件路径的文件描述列表不当作科学记录。

列集合按记录中首次出现的 key 顺序取并集。JSON 原生类型进入 raw snapshot；清洗时 dict/list 单元格转 canonical JSON 字符串，绝不静默展开成科学值。

## 5. CSV/TSV 行身份

- 第一行是 header。
- header 原顺序保留；重复 header 使用 `原名#2`、`原名#3` 作为 occurrence key，不覆盖前一列。
- 数据行 `source_row_index` 从 1 开始。
- 记录 `physical_line_start`/`physical_line_end`，覆盖多行 quoted cell。
- 短行缺列：缺失单元格为 null/空并产生 ragged-row 复核，不补值。
- 长行额外单元格：进入 `__extra_cell_N`，保留并复核。
- 完全空或全是 missing token 的行不进入 cleaned rows，但保留在 `raw_snapshot.json` 并记录显式 `excluded_empty` 变更。

## 6. `output_contract` 三种形态

### dict

顶层每个 key 都是结果必须保留的字段：

```json
{"case_id": "string", "cleaned_rows": "array", "custom_extension": "any"}
```

dict 的 value 视为描述，不决定输出值。

### list

支持字符串列表和常见 descriptor object：

```json
["case_id", "cleaned_rows", {"name": "review_queue"}]
```

descriptor 中优先读取 `name`、`field`、`key`、`path`；单键 object 使用该键。

### string

先尝试把字符串解析为 JSON list/dict；失败后按换行、逗号或分号切分。空白项忽略。

## 7. contract 字段填充与未知键

内置语义字段包括：`case_id`、`status`、`sources`、`uncertainty`、`change_records`、`artifacts`、`cleaned_rows`、`cleaned_csv`、`raw_snapshot`、`anomalies`、`review_queue`、`audit_report`、`errors`、`partial`、`unresolved_contract_fields`、`input_fingerprint`。

若干同义名称（如 `records`、`results`、`source_files`、`output_files`、`report`）会映射到上述语义。其他未知顶层键一律为 `null`，并加入 `unresolved_contract_fields`。即使 contract 声明了类型，工具也不会为了满足类型而编造科学数据、来源、文件名或默认值。

## 8. 失败路径

- case 不存在或 JSON 无法解析：状态 `input_error`；仍尝试从可恢复文本/task/输入目录发现材料，但不会把恢复结果伪装成完整运行。
- task 缺失：记录控制文件错误，材料发现继续。
- 某个材料缺失或 JSON/CSV 解析失败：状态至少 `partial`，其他可信材料继续处理。
- 非法 UTF-8 恢复：状态 `partial`，相关 U+FFFD 单元格进入复核。
- 未预期异常：立即写 `result.json`（`stage=failed`）、已有 sources/changes/errors 和所有已知 contract 键，然后以非零退出码结束。
