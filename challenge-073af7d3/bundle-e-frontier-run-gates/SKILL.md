---
name: frontier-run-gates
description: 用于预算受限（如 64 次请求 / 900 秒）的文献趋势与前沿分析执行过程质量控制。它在 /input → /app/work → /app/output 全流程上提供哈希建档、阶段门 G0–G8、输出契约 lint 与确定性复跑校验，强制 result.json 始终满足 case.json 的 output_contract，并以 partial-first 纪律保证中途耗尽预算也能交出诚实可用的部分结果。它只做过程与契约层面的机器校验，不判断结论的科学正确性，也不调用任何外部数据库。
---

# frontier-run-gates：过程质量控制、契约强制与可复跑

## 1. 定位

文献趋势分析在预算受限的运行里，主要死因不是统计错了，而是**过程失败**：跑了半小时没留档、`result.json` 写了一半缺契约字段、结论里引用的 record_id 在证据矩阵里查无此条、两次运行结果对不上无法复现。本技能的重心是把"运行本身"变成可审计对象：

- **建档（manifest）**：所有输入文件 sha256 + 大小，每个阶段的状态与产物哈希，全部落盘。
- **阶段门（gate）**：G0–G8 九个机器检查点，每一步过了才走下一步，失败即记录并降级。
- **契约强制（contract lint）**：交付前把 result.json 与 case.json 的 output_contract 逐字段对表。
- **确定性复跑（replay diff）**：脚本化阶段重跑一遍，逐字节比对，证明可复现。

核心纪律是 **partial-first（部分结果优先）**：第 0 步就写出带全部契约字段占位、`status="partial"` 的 result.json 骨架，之后每完成一个阶段就回填一次。运行契约要求任何时候中断，/app/output 里都是一份诚实标注了完成度的结果——预算耗尽的运行仍然产出自洽的 partial，而不是一地半成品。

**门是检查点，不是判断力的替代品**：门只保证"该做的做了、引用链得上、契约对得上"，结论本身的质量仍由你（智能体）负责。

## 2. 固定路径

- 技能脚本：`/skills/weekly-skill/scripts/`（`run_manifest.py`、`mini_pipeline.py`、`gate_check.py`、`contract_lint.py`、`replay_diff.py`）
- 参考资料：`/skills/weekly-skill/references/`（`gates.md`、`contract_rules.md`）
- 输入：`/input/case.json`、`/input/task.md`、语料材料文件（json/jsonl/csv/bib/ris/txt/md/PDF，**一律读真实文件，绝不凭文件名猜内容**；PDF 用平台 pdf-text/pdf-render/ocr 工具）
- 工作目录：`/app/work`（manifest、中间产物都放这里）
- 交付：`/app/output/result.json` + 报告 md + 证据矩阵

## 3. 执行协议

### 第 0 步 · G0 读契约 + 建档（≤3 次模型请求）

1. 读 `/input/case.json`：记下 `case_id` 与 `output_contract.fields` 的**全部字段名**；读 `/input/task.md` 确认任务口径。
2. 建档：`python3 /skills/weekly-skill/scripts/run_manifest.py --work /app/work init --input-dir /input`；额外产生的输入（如 PDF 抽取的文本）用 `add-input FILE` 逐个登记。
3. **立刻**在 `/app/output/result.json` 写骨架：`case_id` + 每个契约字段的结构化占位（`{"note": "PLACEHOLDER - ..."}`）+ `status="partial"` + provenance（输入 sha256 列表）。可运行 `mini_pipeline.py --work /app/work --corpus <语料> --case /input/case.json` 一次生成全部中间产物与草稿骨架。
4. 之后**每完成一个阶段就回填一次 result.json**（把占位换成真实内容），这是硬规则。

### 第 1 步 · G1 语料归一

用 mini_pipeline 的 normalize 或你自己的 ingest，产出 `canon.jsonl`（id/title/year/abstract）。G1 要求每条记录有 id 且 year 为整数。缺年份记录占比 >20% 时，必须在 uncertainty 里登记覆盖度不确定性，并在时间趋势中说明剔除口径。

### 第 2 步 · G2 时间趋势

基于 `slices.json`（逐年计数，含闭包校验：逐年之和 == 有年份记录数）撰写趋势。必须注意三点并写进结果：① 年度计数噪声量级 ~√n（泊松尺度），小样本波动勿过度解读；② 末年计数存在右删失（索引不全），不得把末年下降直接当结论；③ 声明日期口径（print / online / preprint 谁先谁后）。

### 第 3 步 · G3 主题演化

基于 `cohorts.json`（逐年高频词队列，已去停用词、min_df=2）做相分段，识别每相主导主题与相间转移。每条主题演化结论要写明"何时变化 + 变化证据"；**为什么会变化**（范式转移、方法成熟、应用拉动等）属于推断，必须标注为 inference，不得与词频事实混写。

### 第 4 步 · G4 代表作遴选

`representatives.json` 里的候选**只是占位**（每相按引用量排序），不允许直接交付。你必须按多准则重选：相内引用分位（而非全局 top-N，避免老论文天然占优）+ 主题中心性（与该相主导主题的关联）+ 方法首创性（首次提出某方法者优先）。把每篇入选作品的评分表写进证据矩阵对应行，保证可追溯。每个相等三段由年代跨度均分得到。

### 第 5 步 · G5 研究空白

每条空白主张都必须附**排除证据**：检索范围说明（查了哪些库/哪些词）+ 近似命中分析（最接近的工作是什么、为什么不算覆盖）。如果提不出站得住的空白，就记录 none-with-reason（说明检索过、为何不下空白结论）——这是诚实，**编造的空白不是成果**。G5 对"有理由的无"与"有证据的有"同等放行，只对"什么都没记录"判失败。

### 第 6 步 · G6 证据回链

result.json 中每条结论（趋势、主题、代表作、空白）都要带 `{"record_id": "..."}` 形式的证据引用，且每个 record_id 必须能在 `evidence_matrix.jsonl` 中解析。G6 与 contract_lint 都会遍历全 JSON 检查，出现悬空引用即失败。

### 第 7 步 · G7 不确定性

uncertainty 字段**必须非空**：证据冲突（双方如何表述）、检索偏差（数据库/语种/年份覆盖）、覆盖度上限、需要人工核验的条目。写不出不确定性恰恰说明分析不可信。

### 第 8 步 · G8 定稿

1. `python3 /skills/weekly-skill/scripts/gate_check.py --work /app/work` 全门通过。
2. `python3 /skills/weekly-skill/scripts/replay_diff.py --work /app/work` 必须为 identical（exit 0）；若报 differ，先查非确定性来源再交付。
3. `python3 /skills/weekly-skill/scripts/contract_lint.py --case /input/case.json --result /app/output/result.json --evidence-matrix /app/work/evidence_matrix.jsonl` 必须 clean。
4. 交付 `/app/output/`：最终 `result.json`（status 视完成度为 ok/partial）、分析报告 md、`evidence_matrix.jsonl`。

## 4. 输出契约

`result.json` 必须包含：`case_id`（与 case.json 一致）、`status`（枚举：`ok` / `partial` / `blocked_no_corpus` / `blocked_no_contract` / `failed`）、case.json `output_contract.fields` 里列出的**每一个字段**、证据引用、非空的 uncertainty。规则细节（linter 逐条判定，见 `references/contract_rules.md`）：

- 契约字段缺失 → 违规（`missing_field`）。
- status 不在枚举内 → 违规（`invalid_status`）。
- 字段为 null/空串/空数组/空对象 → 违规（`empty_field`）；结构化占位（仅含非空 `note` 的对象）只在 status 为 partial/blocked_*/failed 时合法，status=ok 下出现占位即违规。
- 任何 `{"record_id": ...}` 在证据矩阵中解析不到 → 违规（`dangling_evidence`）。
- case_id 不匹配 → 违规。

诚实的 partial 必须点名自己的边界：哪些字段是占位、卡在哪个门、还差什么。这份诚实本身就是交付质量的一部分。

## 5. 预算规划

64 次模型请求 / 900 秒的分配建议：

| 阶段 | 请求预算 | 说明 |
| --- | --- | --- |
| G0 读契约+建档 | ≤3 | 含 task.md 口径确认 |
| G1–G3 脚本化阶段 | 0 | mini_pipeline 确定性脚本，不占模型请求；你只需读产物 |
| G4–G7 判断密集阶段 | 大头（≥40） | 代表作多准则遴选、空白排除证据、回链与不确定性 |
| G8 定稿 | ≤5 | lint/门/复跑均为脚本，请求只花在修补违规上 |
| 机动 | 余量 | 异常处理（见下节） |

**硬规则**：每阶段完成后立即回填 result.json。这样即使第 900 秒被掐断，/app/output 里也是一份 status=partial、边界清晰的自洽结果，而不是零。

## 6. 异常处理

| 异常 | 处置 |
| --- | --- |
| 检索为空 / 无语料 | status=`blocked_no_corpus`，在 result.json 说明检索式与范围，manifest 记录，不要编造数据 |
| case.json 无 output_contract | 不判 blocked：默认采用四个 canonical 交付字段（trend_summary / theme_evolution / representative_works / research_gaps），并在 result.json 记录该假设 |
| 语料爆炸（量太大跑不动） | 按记录 seed 与分层（年份/来源）抽样，抽样参数写进 manifest notes 与 uncertainty，趋势结论注明样本口径 |
| 年份缺失 >20% | 见 G1：登记覆盖度不确定性，趋势只基于有年份子集并声明 |
| 证据冲突 | 双方并陈（both-sides rule）：两条对立证据都进证据矩阵与 uncertainty，不单边取舍 |
| 权限 / 工具失败（如 PDF 无法解析） | manifest 记录失败命令，status 降 partial，用可用材料继续，限制写进 uncertainty |
| 主题歧义 | 在 uncertainty 登记候选主题口径，按 case.json task 字段取主口径 |
| 复跑不一致（replay_diff 报 differ） | 调查脚本化阶段的非确定性来源（排序/时间/外部状态），修复后再交付；不得在 differ 状态下交付 |

## 7. 不适用

- 本技能**不判断结论的科学正确性**：趋势统计是否恰当、主题语义是否合理、代表作选得对不对，属于统计/语义类技能的职责；这里的门只管"做了没有、链得上没有、契约对不对"。
- 不调用任何外部数据库或网络；脚本全部 Python 标准库、离线、确定性。
- 不替代你对材料的阅读：语料内容一律以真实文件为准。

## 8. 合成示例

`examples/` 下为**合成（synthetic/合成）**示例：`synthetic_case/` 含 15 条编造的文献记录（2012–2024）、case.json 与一份埋了三个违规的 result_bad.json；`run_example.sh` 演示完整好流程（建档→管线→G0–G8 全过→复跑字节一致→lint 干净）与坏样本（lint 恰好报出缺字段、非法 status、悬空引用三条违规）；`example_output/` 保存真实跑出来的产物。运行：`bash examples/run_example.sh`。
