---
name: catalog-delivery-forge
description: 科研资料库整理的"交付物工程"技能。当任务要求把混杂文献目录归档、命名、去重并交付可复核清单时使用；重心在下游交付渲染：整理结论必须落成四类可独立复核的交付物——人读 catalog.md（分组目录，含哈希短码与证据锚点）、机读 catalog.csv、整理前后目录树对照 tree_diff.md、哈希复核报告 verify_report.md，全部交叉链接。整理逻辑确定性优先（脚本先出带置信度的提案，模型只写覆盖项），输入只读、不删除、重跑幂等。不负责单篇精读、全文翻译与文献检索发现。
---

# catalog-delivery-forge：整理结论必须落成可复核的交付物

## 1. 核心思想

"把分类做成聊天回复"是资料整理最常见的失败：结论停在对话里，资料库没有任何
可交接的产物。本 Skill 的重心是**下游交付渲染工程**——整理结果存在的唯一合法
形态是落在 `/app/output` 里、人和机器都能独立复核的交付物集合：

1. **先提案后覆盖**：脚本在 init 阶段就对每个文件给出确定性提案（文献类型判定、
   目录归属、规范命名、置信度），模型**只写 `overrides.json` 覆盖提案错误之处**，
   不为已经正确的文件消耗预算。提案-覆盖全程留痕，谁改了什么一目了然。
2. **四件套交付物**（render 阶段由脚本渲染，格式契约见
   `references/catalog_format.md`）：
   - `catalog.md`：人读总目录，按 类型/年份 分组；每条含规范名、原始路径、
     SHA-256 短码、DOI、版本关系标注、元数据证据锚点；
   - `catalog.csv`：机读平表，每文件一行 14 列，可直接进 Excel/Zotero 比对；
   - `tree_diff.md`：整理前后目录树并排对照，移动、改名、归档、跳过逐条可见；
   - `verify_report.md`：哈希复核报告，逐条列出 源哈希=目标哈希 的核验结论。
3. **交叉链接**：catalog.md 条目 ↔ operations.jsonl 操作号 ↔ result.json
   library_index 三方用同一 fid 串联，评审从任何一件都能追到另外两件。

## 2. 适用边界

- 适用：给真实文件批次与组织规则，要求真实产出整理后目录与**可交接**清单的任务。
- 不适用：精读、翻译、润色、检索发现；无文本层扫描件的 OCR（登记跳过）；
  损坏/无权限文件的内容判读（如实进 skipped，catalog 中标注状态）。

## 3. 运行时契约（Harbor）

- 安装路径 `/skills/weekly-skill`；脚本 `python3 /skills/weekly-skill/scripts/xxx.py`。
- 输入 `/input/case.json`、`/input/task.md` 与材料目录；字段名不可假设，防御式
  解析见 `references/case_contract.md`。
- 工作目录 `/app/work`；交付 `/app/output/`：`result.json`（含原 `case_id` 与
  `output_contract` 全部字段、诚实 status）、`library/`、`catalog.md`、`catalog.csv`、
  `tree_diff.md`、`verify_report.md`、`operations.jsonl`。
- status：`complete` / `partial`（有跳过，必须列限度）/ `blocked`，不得粉饰。
- 依赖：Python 3 标准库；`pdftotext` 缺失时降级登记，不中断。
- 预算：脚本零模型请求；模型 0–2 次响应（覆盖项 + 检索回答）。第一步永远是
  init，10 秒内落地保底 partial result.json。

## 4. 工作流程

设 `S=/skills/weekly-skill/scripts`。

### 第 1 步：只读盘点 + 确定性提案（脚本，0 次模型请求）

```bash
python3 $S/run_case.py init --input /input --work /app/work --out /app/output
```

除盘点产物（files.jsonl / aliases.json / sidecars.json / meta_candidates.json）外，
额外写 `/app/work/proposal.json`：每文件
`{fid, doc_type, category, subcategory, new_name, confidence, signals, disposition}`。
`signals` 列出判定依据（如 "含 arXiv 标识"、"标题含 Supplementary"、"SHA-256 与
F001 相同"），`confidence ∈ {high, medium, low}`：low 的条目是模型最该看的地方。
保底 partial result.json 同步落地。

### 第 2 步：模型覆盖（0–1 次模型请求）

模型读 `proposal.json`、`decision_digest.md`、旁挂说明，**只写**
`/app/work/overrides.json`：

```json
{"overrides": [{"fid": "F004", "category": "preprints", "new_name": "……", "reason": "……"}],
 "answers": [{"qid": "Q1", "answer": "……", "evidence": "……"}]}
```

没有错误的提案就一行不写；`answers` 仅当 case 含检索问题时需要。拿不准的字段
保持提案中的 `unknown`，不得编补。

### 第 3 步：落地 + 渲染四件套（脚本，0 次模型请求）

```bash
python3 $S/run_case.py finalize --work /app/work --out /app/output
```

合并提案与覆盖 → 复制归档（冲突加序号、不覆盖、幂等跳过）→ 哈希核验 →
渲染 `catalog.md` / `catalog.csv` / `tree_diff.md` / `verify_report.md` →
终版 `result.json`（mirror output_contract 全字段，`library_index` 与 catalog
严格同源）。

## 5. 异常处理

| 情况 | 处置 |
|---|---|
| 损坏/加密 PDF、无文本层、无权限 | 进 skipped，catalog.md 中列入"未归档"节并标注状态与恢复建议 |
| 提案置信度 low | catalog 条目加 `(置信度:低)` 标记，tree_diff 中同样标注 |
| 字节级重复 | 保留一份，其余进 `_archive_dups/`，catalog 两组互链 |
| 目标重名不同内容 | 自动 `-2` 后缀，记 conflict，不覆盖 |
| 库不可读 | `status="blocked"`，不空跑 |

## 6. 最小调用示例（合成示例）

```bash
cd examples && python3 make_fixture.py && bash run_example.sh
```

合成夹具 13 文件（重复下载、版本三件套、损坏/无权限/无文本层、管理员说明），
预写 overrides 代替模型步骤；输出摘录见 `sample_output.md`。**合成示例，
非正式案例结果。**

## 7. 自查清单

- [ ] 四件套都存在且与 operations.jsonl、result.json 同源一致（fid 可互查）。
- [ ] catalog.md 覆盖全部输入文件（含未归档节），无静默遗漏。
- [ ] verify_report.md 每条核验结论为 "一致"；不一致时必须出现在 uncertainties。
- [ ] 重跑 finalize 后四件套内容不变（时间戳除外）。
