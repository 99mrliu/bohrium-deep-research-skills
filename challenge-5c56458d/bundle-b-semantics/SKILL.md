---
name: field-caliber-resolver
description: Resolve field semantics and statistical caliber for a scientific SQLite snapshot before querying. Use when a case requires explaining what columns mean, their units and coding, distinguishing confusable fields (coded vs measured, sample status vs experiment status, 0 vs NULL), and pinning down an explicit analysis caliber (grain, aggregations, filters) with an ambiguity queue instead of guesses. 字段解释与口径：自动构建数据字典、编码陷阱识别、口径声明。
---

# Field Caliber Resolver：字段语义与统计口径解析

本 Skill 的重心是**字段含义与统计口径**——"结果对了却说不清字段含义和口径"是题目点名的失败模式。它从真实快照 profiling 出发构建数据字典草稿，识别编码型字段等陷阱，并把任务问题解析成一份可否决的口径声明；解释不了的字段进歧义队列，绝不猜测。

## 运行约定（先读）

先读 `/input/case.json` 与 `/input/task.md`。`/app/output/result.json` 必须含原始 `case_id` 与 `output_contract` 的全部字段，按原样填写；**先写 `status: "partial"` 的兜底版本再逐步改进**（预算约 900 s / 64 次请求）。工作目录 `/app/work`。只读真实文件；任务方提供的数据字典优先级最高，本 Skill 的 semantics_pack 只是参考。技能目录解析：`/skills/weekly-skill` → `$WEEKLY_SKILL` → 本文件所在目录。

## 工作流

1. **契约兜底**：按 output_contract 写 partial result.json。
2. **字段画像**：`python <skill>/scripts/profile_fields.py --db <库> --out /app/work/field_profile.json`。每列得到角色判定（identifier / coded_categorical / **numeric_coded_category（陷阱）** / numeric_measure / boolean_flag / free_text / constant）与证据（distinct 比、typeof、levels）。`numeric_code_traps` 列表是后续所有聚合的红线。
3. **构建数据字典**：`python <skill>/scripts/build_dictionary.py --profile ... --pack <skill>/references/semantics_pack.json --out /app/work/data_dictionary.json --md /app/work/data_dictionary.md`。命名字段得到语义/单位/口径（confidence=pack_match）；多义名与未收录字段进 `ambiguity_queue`。**未解决字段不许编语义**——在报告中注明"含义未经任务方确认"。
4. **解析任务口径**：`python <skill>/scripts/resolve_caliber.py --task-file /input/task.md --dictionary /app/work/data_dictionary.json --out /app/work/caliber.json --md /app/work/caliber.md`。得到：字段映射（每个映射带命中 token，可人工否决）、聚合动词、候选分组字段、粒度声明、编码字段聚合陷阱告警、未映射任务词清单。
5. **按口径执行分析**：写 SQL 时强制应用 caliber.md——编码字段只计数、单位随数字带出、粒度与声明一致、0 与 NULL 按 `references/confusable_fields.md` 第 3 条分别处理。
6. **交付**：result.json（complete，含口径摘要与不确定性）+ data_dictionary.md + caliber.md + 分析产物 + analysis_notes.md（歧义队列处置记录、未覆盖部分）。

## 异常处理

| 情况 | 处置 |
|-|-|
| 字段名与任务用词对不上 | 映射按 token 命中，低证据映射在 caliber.md 标注可否决；仍无法对应的任务词进未映射清单，不猜。 |
| 任务要求对编码字段求均值 | 给计数/比例，异常清单写明拒绝理由（confusable_fields.md 第 1 条）。 |
| 存在近义状态字段 | 按任务方字典取舍；无字典时两口径各算一遍或列入歧义队列，并说明。 |
| 数据字典与快照取值冲突（如类别集合不同） | 以快照为准，冲突写入异常清单。 |
| 多套类别拼写 | 出显式映射表合并，映射表作为交付物。 |

## 附带脚本与资源

- `scripts/profile_fields.py` — 列角色画像与编码陷阱识别（纯标准库，只读）。
- `scripts/build_dictionary.py` — 画像 × semantics_pack → 数据字典草稿（JSON+Markdown），含歧义队列。
- `scripts/resolve_caliber.py` — 任务文本 × 字典 → 口径声明（JSON+Markdown），透明启发式、证据可否决。
- `references/semantics_pack.json` — UCI Iris/Wine/Concrete 字段语义（含义、单位、编码、口径），来源为 UCI 数据集说明页 + 原始文件复算。
- `references/confusable_fields.md` — 七类易混字段与取舍规则。

## 最小调用示例（合成示例，非正式案例结果）

合成输入：脚本自建 `lab.db`（表 `assay`，含 `class` 编码列 1/2/3、含 NULL 与 0 的 `additive` 列、以及 `sample_status`/`experiment_status` 近义列），任务文本"按 class 统计 alcohol 平均值与样本数"。执行：

```
python <skill>/scripts/profile_fields.py --db lab.db --out work/field_profile.json
python <skill>/scripts/build_dictionary.py --profile work/field_profile.json \
  --pack <skill>/references/semantics_pack.json --out work/data_dictionary.json --md work/data_dictionary.md
python <skill>/scripts/resolve_caliber.py --task-file task.md \
  --dictionary work/data_dictionary.json --out work/caliber.json --md work/caliber.md
```

示意输出（示例，非正式结果）：`class` 被标为 numeric_coded_category 陷阱；caliber.md 声明粒度"每个 class 一行"、聚合 AVG(alcohol)+COUNT，并告警不得对 class 本身求均值；`sample_status`/`experiment_status` 进歧义队列。完整可跑脚本见 `examples/run_example.sh`。

## 边界与限制

口径解析是透明启发式（token 匹配），不是自然语言理解——它的价值在于把映射证据摆出来供否决，而非保证正确；semantics_pack 只覆盖收录数据集，其他数据集的字典语义依赖任务方字典或显式声明；面向单文件 SQLite、≤百万行表。
