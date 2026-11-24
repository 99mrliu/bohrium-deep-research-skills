# case.json 防御式解析契约

运行时输入为 `/input/case.json` 与 `/input/task.md`。字段名**不可假设**，
`inventory.py:parse_case` 按以下顺序容错解析；所有降级路径写入
`case_meta.json.parse_notes` 并汇入 result.json 的 uncertainties。

| 语义 | 依次尝试的键 | 兜底 |
|---|---|---|
| case_id | `case_id` / `caseId` / `id` / `name` | case 文件名去扩展名 |
| 库目录 | `library_dir` / `library` / `input_dir` / `data_dir` / `corpus_dir` / `root` / `materials_dir`（相对路径基于 /input） | `/input/library`、`/input/materials`、`/input/files`、`/input/data`；再退为整个 `/input` |
| output_contract | `output_contract` / `contract` / `output_fields` / `required_fields` / `outputs`；dict 取键列表 | 空列表 → 默认字段集并在 uncertainties 注明 |
| 检索问题 | `questions` / `queries` / `search_questions` / `retrieval_questions`；元素 str 或 dict | 空列表 → answers 为 null |
| 命名模板 | `naming_template` / `naming` / `filename_template` | `{authors}-{year}-{title}` |
| 目录结构 | `target_structure` / `directory_structure` / `structure` | `type/year two-level` |

解析原则：task.md 明文要求优先；解析失败不中断只留痕；库不可读时写
`status="blocked"` 的 result.json；contract 中未产出字段置 null 并说明，不省略键。
