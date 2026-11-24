# case.json 防御式解析契约

运行时输入为 `/input/case.json` 与 `/input/task.md`。字段名**不可假设**，
`inventory.py:parse_case` 按以下顺序容错解析；所有降级路径都会写入
`case_meta.json.parse_notes` 并汇入 result.json 的 uncertainties。

| 语义 | 依次尝试的键 | 兜底 |
|---|---|---|
| case_id | `case_id` / `caseId` / `id` / `name` | case 文件名去扩展名 |
| 库目录 | `library_dir` / `library` / `input_dir` / `data_dir` / `corpus_dir` / `root` / `materials_dir`（相对路径基于 /input 解析） | `/input/library`、`/input/materials`、`/input/files`、`/input/data`；再退为整个 `/input`（排除 case.json/task.md 由调用方判断） |
| output_contract | `output_contract` / `contract` / `output_fields` / `required_fields` / `outputs`；dict 取键列表 | 空列表 → build_result 使用默认字段集并在 uncertainties 注明 |
| 检索问题 | `questions` / `queries` / `search_questions` / `retrieval_questions`；元素为 str 或 dict（`qid/id`、`text/question/q`） | 空列表 → answers 为 null |
| 命名模板 | `naming_template` / `naming` / `filename_template` | `{authors}-{year}-{title}` |
| 目录结构 | `target_structure` / `directory_structure` / `structure` | `type/year two-level` |

解析原则：

1. task.md 的明文要求优先于 case.json 与本 Skill 的默认值。
2. case.json 解析失败不中断：记 parse_notes，继续盘点。
3. 库目录不存在或为空：仍写 `status="blocked"` 的 result.json，不空跑、不伪造清单。
4. contract 中本 Skill 未产出的字段置 null 并在 uncertainties 逐条说明，不省略键。
