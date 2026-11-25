---
name: query-coverage-engineering
description: 检索式工程与覆盖审计。从研究问题结构化解析概念块（PICO 式：对象/方法/场景），生成 Crossref / Europe PMC / arXiv 三源方言的可审计布尔检索式（块内同义词 OR、块间 AND）；对检索式做静态 lint（未加引号短语、裸 OR、过宽单词、通配符兼容性等逐条给出修改建议）；并利用案例材料中保留的参考图谱/种子文献做已知项召回验证（known-item recall check），输出逐源×逐概念块命中矩阵、未命中诊断（哪个概念块挡掉了种子、缺哪个同义词）与最小化查询修订建议，以及源×查询覆盖矩阵与遗漏说明。全部判断由离线确定性 Python 脚本完成，模型只复核与写作。
---

# query-coverage-engineering — 检索式工程与覆盖审计

## 1. 适用场景与边界

**适用**：「最新文献发现与追踪」类任务中，需要回答"检索式够不够全"的场景：

- 把研究问题/任务描述结构化为概念块（object / method / scenario），产出可审计的布尔检索式；
- 在检索式**发出之前**做静态审计（lint），提前发现语法与方言兼容性问题；
- 用保留的参考图谱/种子清单做**已知项召回验证**：这些已知相关文献会不会被当前检索式
  在各源命中？未命中的，是哪个概念块挡掉的、缺哪个同义词、最小改动怎么修？
- 产出源×查询覆盖矩阵与诚实的遗漏说明。

**明确不做**（避免与相邻 Skill 重叠）：

- 不做去重、合并与归一化；不做增量水位/窗口调度/补抓；不做提醒合并与投递；
- 不做版本链生命周期；不做结果质量打分；不做失败重试。
- 不编造文献、DOI、元数据或检索结果；一切"命中/漏检"判断都基于材料快照的真实内容，
  并带 locator（文件路径 + JSON 指针）。

## 2. 运行契约

- **输入**：`/input/case.json`（必须，含 `case_id`、`output_contract`，可能含
  `concepts` / `research_question` / `window` / `materials_dir`）；`/input/task.md`（可选，
  用于概念块兜底抽取与写作上下文）。
- **材料定位**：优先 `case.json.materials_dir`（相对 case.json 所在目录）；缺失时用
  `find` 兜底：
  `find /input /app -maxdepth 5 \( -name '*snapshot*.json' -o -name 'reference_graph.json' \) 2>/dev/null`。
  快照按文件名识别：`*crossref*.json` / `*europepmc*.json` / `*arxiv*.json`；
  种子清单固定文件名 `reference_graph.json`。
- **工作目录**：`/app/work`（脚本中间产物全部放这里；示例产物在
  `examples/minimal/output/`）。
- **最终产物**：`/app/output/result.json`，必须包含 `case_id` 与
  `case.json.output_contract` 列出的全部字段；任何字段无法产出时补 `null`
  并将 `status` 置为 `"partial"`，在 `partial_reasons` / `contract_notes` 中逐条说明。
- **环境假设**：完全离线；脚本仅用 Python3 标准库；确定性（同输入同输出）。

## 3. 工作流程（编号）

0. **定位与装载**：读 `/input/case.json` 与 `task.md`；按 §2 定位材料目录与快照；
   记录 `window`。材料缺失时继续走降级路径，不中断。
1. **概念块解析**：`scripts/concept_parse.py --case ... --out work/concepts.json`。
   case.json 直接给 `concepts` 时校验后使用；否则从 `research_question`/task 文本按规则
   抽取（degraded=true，**模型必须逐块复核后再继续**）。
2. **检索式构建**：`scripts/query_build.py` 生成三源方言查询
   （块内 OR、块间 AND、短语加引号、窗口按各源语法附加）。
3. **静态审计**：`scripts/query_lint.py` 对概念块与查询串跑 QL001–QL007 规则，
   逐条 finding 给出修改建议（规则表见 `references/lint-rules.md`）。
4. **已知项召回验证**：`scripts/coverage_check.py` 对每颗种子逐源判定
   `hit / miss / absent_from_snapshot / outside_window / no_snapshot`，
   输出命中矩阵与未命中诊断（漏配块 + top-3 候选新同义词 + top-1 最小修订）。
5. **最小化修订**：取每颗 `miss` 种子每个漏配块的 top-1 建议，向概念块 OR 组
   **追加**同义词（只增不删），重建检索式并重跑覆盖验证；断言原有 `hit` 不回归。
6. **汇总**：`scripts/assemble_result.py` 按 `output_contract` 强制校验并写
   `result.json`，生成遗漏说明与 locators。
7. **自查**：按 §6 清单逐项核对；端到端演示见
   `python3 scripts/run_minimal_example.py`（含埋点断言与 bundle 约束自查）。

模型的角色：复核第 1 步的概念块、第 3 步 lint 建议与第 4 步诊断是否合理，
撰写遗漏说明的可读文本；**不代替脚本做命中判断**。

## 4. 异常处理与诚实降级

| 异常 | 处理 |
|---|---|
| case.json 无 `concepts` 但有 `research_question`/task | 规则抽取概念块，`degraded=true`、`needs_model_review=true`，模型复核后继续 |
| 无任何研究问题字段 | 输出空概念块 + warning；下游 result.json 相关字段补 null，`status=partial` |
| 无 `reference_graph.json` / 种子清单为空 | 覆盖验证整体缺失，`coverage` 补 null，`status=partial`，omissions 说明"无种子图谱，已知项召回验证无法执行" |
| 某源快照缺失/为空 | 该源所有种子标记 `no_snapshot`，写入 omissions |
| 种子在某源快照中找不到 | 标记 `absent_from_snapshot`（**不是**检索式漏检），写入 omissions |
| 种子日期在窗口外 | 标记 `outside_window`，写入 omissions |
| lint 存在 error 级 finding | `status=partial` 并在 `partial_reasons` 说明 |
| 修订后仍有种子 `miss` | `status=partial`，`missed_seeds` 保留诊断 |

## 5. 输出契约（result.json 字段）

以 `case.json.output_contract` 为准；本 Skill 的完整形态为：

- `case_id`：与 case.json 一致（不一致直接报错）；
- `status`：`"complete" | "partial"`；
- `synthetic` / `synthetic_note`：透传合成标注，绝不冒称真实数据；
- `concepts`：初始与最终概念块、解析来源与降级标记、locator；
- `queries`：初始与最终三源检索式、窗口、locator；
- `lint_report`：findings（逐条含修改建议）、按严重级汇总、规则表；
- `coverage`：最终覆盖全量结果（逐源×逐种子状态、逐概念块命中明细、命中矩阵、
  逐源汇总、known_item_recall）与初始汇总，locator；
- `missed_seeds`：初始检索式下未命中的种子及诊断（漏配块、候选同义词、最小修订、
  记录 locator）；
- `query_revisions`：已应用的修订（块、新增同义词、理由、证据 locator）；
- `omissions`：遗漏说明（源未收录、窗口排除、材料缺失、方法学局限）；
- `locators`：事实性字段的 文件路径 + JSON 指针。

## 6. 自查清单

- [ ] `result.json` 含 `case_id` 且与 case.json 一致；`output_contract` 字段全部存在，
      缺失字段为 null 且 `status="partial"` 并给出理由。
- [ ] 每颗种子的每个源状态都属于五态之一；`absent_from_snapshot` 未被误报为 `miss`。
- [ ] 每个 `miss` 诊断都指出漏配块与至少一个候选新同义词；修订后重跑且原有 `hit` 无回归。
- [ ] lint findings 均带 rule_id 与 suggestion；error 级 finding 已修复或已解释。
- [ ] 所有事实性字段值带 locator（路径 + JSON 指针），抽查指针可解。
- [ ] 合成数据保留 `synthetic` / `synthetic_note` 标注，未冒称真实。
- [ ] 未编造任何文献、DOI、PMID、arXiv ID 或元数据。
- [ ] bundle 约束：文件 ≤50、单文件 ≤500KB、总计 ≤2MB、无符号链接、全 UTF-8、
      每个文件带扩展名（`run_minimal_example.py` 第 7 步自动断言）。

## 7. 参考文档

- `references/lint-rules.md` — QL001–QL007 规则表与设计说明
- `references/source-dialects.md` — 三源查询方言差异、字段表与快照结构
- `references/known-item-recall-methodology.md` — 已知项召回验证方法学、状态语义与局限
- `examples/minimal/` — 合成端到端示例（含埋点：初始漏检种子经诊断修订后命中）
