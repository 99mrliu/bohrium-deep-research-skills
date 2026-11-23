---
name: crossdoc-identity-kg
description: >-
  跨文档实体身份裁决与图谱构建 Skill（挑战 阅读15 文献知识图谱构建）。在两篇独立论文材料上，
  以确定性规范化生成跨篇候选键，用独立属性签名执行 MERGE / KEEP_DISTINCT / UNDECIDED
  三态合并门裁决：不同 DOI 来源不是阻断项，不同样品/模型实例/数据集/实验条件以及
  数值/单位冲突是阻断项；仅规范化别名相同不得合并，证据不足一律 UNDECIDED。
  每个实质节点/边携带独立论文 source_id、组织方 JATS paragraph_id 与逐字短引
  （无 PDF 页码声称），核验失败即剔除并记录。稳定节点 ID 在裁决完成后才分配，
  最终交付完整图谱（graph.json/jsonl/dot/svg/文本预览）、identity-decisions.json、
  conflicts.json 与至少 3 条实际执行的查询及其证据。当 /input 提供 case.json、
  task.md、corpus-manifest.json、material.json、primary-material.json、
  secondary-material.json（可能含 XML），且 /app/output/result.json 需要动态镜像
  output_contract 全部键并诚实标注状态/不确定性/变更记录时使用。
---

# 跨文档实体身份裁决与图谱构建（crossdoc-identity-kg）

**核心主张**：跨篇实体对齐的正确性不靠“名字像不像”，而靠透明的合并门。
本 Skill 把语义候选交给 Agent（抽取提及与别名），把**裁决**交给确定性脚本：
任何一对跨篇候选必须给出合并依据（merge_basis）或阻断证据（blocking_evidence），
两者都没有就是 UNDECIDED——绝不强迫合并，也绝不把不同论文的条件、样本和数值
合成一个结论。

## 何时使用

- `/input` 提供两篇独立论文文本（`corpus-manifest.json`、`material.json`、
  `primary-material.json`、`secondary-material.json`，可能另有
  `secondary-publisher.xml` 供核对），根 `case.json` 的 DOI/title/authors
  **只属于第一篇**；
- 需要在同一图谱中保留两篇材料的节点、关系与来源，记录跨篇候选同一概念的
  合并依据与不得合并的冲突，并实际执行至少 3 个查询；
- 运行约束：Python3 标准库、UTF-8、无第三方依赖。

## 工作流（路径相对本 SKILL.md）

**第 0 步｜识别输入（Agent）。** 读取 `/input/case.json`（`case_id`、
`output_contract`、根元数据）、`task.md`、`corpus-manifest.json`。根
DOI/title/authors 仅归属第一篇，不得套用到第二篇。

**第 1 步｜段落库与语义抽取（Agent + 脚本）。**
运行 `python3 scripts/run_case.py` 第一轮：它把各材料的 JATS 段落索引写到
`/app/work/paragraph-store-index.json`，并因缺少提及而产出诚实的部分结果。
Agent 据此逐篇抽取提及，按 `references/schema.md` 写入
`/app/work/mentions.json`（每条含 `mention_id`、`source_id`、`paragraph_id`、
`surface`、`entity_type`、`aliases`、`quote`（逐字短引）、`properties`
（定义性属性：化学式/架构/原理/数据集版本/样品/条件等）、`numbers`
（测量值）），并可写 `/app/work/relations.json`（带逐字证据的关系）与
`/app/work/queries.json`（查询规格，缺省时脚本自动生成 3 条）。
段落 ID 是组织方 JATS ID，**不是 PDF 页码**；本包无 PDF 页码，任何证据
不得携带 page 字段。

**第 2 步｜确定性裁决 + 核验 + 构图 + 查询（脚本，0 次模型请求）。**
再次运行 `python3 scripts/run_case.py`：
`identity_gate.py` 执行三态合并门（规则见 `references/identity-policy.md`），
`quote_verify.py` 逐字核验全部节点/边证据，`build_graph.py` 在裁决完成后
分配稳定节点 ID 并输出图谱，`query_graph.py` 实际执行查询。

**第 3 步｜核对与交付（Agent）。** 检查 `/app/output/`：
`result.json`（动态镜像 output_contract 全部键 + case_id + 诚实 status /
uncertainties / change_records）、`graph.json`、`graph.jsonl`、
`identity-decisions.json`、`conflicts.json`、`queries.json`、
`verification-report.json`、`graph.dot`、`graph.svg`、`preview.txt`。
UNDECIDED 与 KEEP_DISTINCT 必须在交付说明中保留，不得写成事实。

## 输入 / 输出

- 输入：`/input/*`（见上）+ Agent 在 `/app/work` 写的 mentions/relations/queries。
- 中间产物：`/app/work/`（段落索引、根元数据记录）。
- 最终产物：`/app/output/`（见第 3 步）。`result.json` 的键集合动态来自
  原始 `output_contract`，无自然映射的键保留 null 并在 uncertainties 说明。

## 异常处理（诚实优先）

- 缺 mentions.json → 立即产出 `status=partial` 的 result.json，说明人工接管位置；
- 段落抽取为空 → `status=partial`，图谱为空，不臆造内容；
- 引文非逐字 / 段落或来源不存在 / 携带 page 字段 → 元素剔除并记入
  verification-report.json，运行继续；
- 单个查询失败不影响其余查询，失败状态如实记录；
- 跨篇同名测量值不同 → 记入 conflicts.json，各来源数值分别保留。

## 最小示例（合成数据，非正式案例结果）

`examples/minimal/` 内含两篇**人工编写**的合成短文（12 条提及、12 条关系），
演示：LLZO 与 LATP 凭化学式一致 MERGE；sintering 因烧结条件不同
KEEP_DISTINCT；两个随机森林模型因 R2 数值冲突 KEEP_DISTINCT；SynthIon-1/2
因数据集版本不同 KEEP_DISTINCT；XRD 仅为通用术语 UNDECIDED。
运行 `python3 scripts/run_example.py` 重新生成 `examples/minimal/output/`
（终图 12 节点 12 边，4 条查询全部执行成功）。
运行 `python3 scripts/selftest.py` 执行全部正向与负向守门测试
（含精确别名不合并、数值冲突阻断、证据不足、伪造引文剔除）。

## 参考资料

- `references/identity-policy.md`：合并门策略与阻断规则全文；
- `references/schema.md`：mentions / relations / decisions / graph / result 结构；
- `references/limitations.md`：适用边界、失败模式与维护信息。
