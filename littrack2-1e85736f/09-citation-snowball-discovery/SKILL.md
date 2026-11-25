---
name: citation-snowball-discovery
description: 以案例保留参考图谱为起点做一轮 backward（参考文献）/forward（被引）引文滚雪球扩展，与关键词检索 API 快照候选做并集合并，量化图谱渠道的互补增益（graph_only / keyword_only / both 三分与 graph_only 漏检原因诊断），以图谱距离与种子共被引次数作为透明排序先验，诚实隔离窗口外 context 条目与 dangling reference；全程离线，绝不外查网络、绝不编造文献或引文关系。
---

# citation-snowball-discovery — 参考图谱引文滚雪球发现

## 适用场景与边界

适用：评测/工作环境中案例同时提供 (a) 关键词检索的 API 响应快照（Crossref / Europe PMC / 出版商）与 (b) **保留参考图谱（retained reference graph）** 时，需要回答"图谱这条发现渠道相对于关键词渠道多找回了什么、为什么关键词漏掉"的场景。核心产出：

1. 以种子文献为起点的**一轮**滚雪球扩展（backward = 种子的参考文献；forward = 引用了种子的文献，仅当图谱提供相应方向的边时）。
2. 图谱候选与关键词快照候选的**并集合并与渠道三分**：`graph_only` / `keyword_only` / `both`。
3. **互补增益量化**：graph_only 占全部新候选的比例，以及每条 graph_only 候选"为什么关键词漏掉"的证据化诊断（例如标题/摘要不含任何查询词，证据指向材料原文的 locator）。
4. 窗口约束处理：图谱扩展到的时间窗口外条目标记为 `context`（背景文献），**不混入增量新发现清单**。
5. 图谱缺口诚实报告：种子在图谱中无记录（seed missing）、边指向图谱未收录的节点（dangling reference）单独列出。

明确不做（避免与其他方向重复）：

- 不做关键词检索式工程（查询词从案例输入照读，不改写、不扩展）。
- 不做去重键归一化工程：只做**最低限度对齐**——DOI 小写去空白去常见前缀后的精确匹配，失败时退回标题 casefold + 空白压缩后的精确匹配；不做模糊匹配、不做相似度去重。
- 不做窗口调度、提醒/抑制、版本链生命周期、QA 打分。
- 不做多轮滚雪球（一轮为默认；多轮的权衡见 `references/snowball-methodology.md`，如确需多轮必须手工声明并逐轮留 locator）。
- **绝不外查网络**：所有引文边、所有元数据只取自案例材料文件；材料没有的字段一律为 `null` 并在 `gaps` 中说明。

## 运行契约

- 输入：`/input/case.json` 与 `/input/task.md`。case.json 至少提供 `case_id`、`task`（含 `seeds`、`query_terms`）、`window`、`materials_dir`、`output_dir`、`output_contract`。
- 材料定位：优先使用 case.json 的 `materials_dir`；若字段缺失或路径不存在，用 `find /input /app -maxdepth 6 -type f` 兜底搜索图谱文件（文件名含 `graph`、`reference`、`citation` 者优先）与 API 快照（文件名含 `crossref`、`europepmc`、`publisher`、`snapshot`、`response` 者优先），并在 `notes` 中记录兜底过程。
- 图谱布局：兼容 `nodes/edges` 与 `adjacency`（+ 可选 `cited_by`）两类布局，约定边 `source → target` 表示 "source 引用 target"，详见 `references/graph-layout.md`。
- 工作目录：中间产物写 `/app/work`（本地运行时可用案例的 `output_dir` 下子目录）。
- 最终产出：写 `/app/output/result.json`（本地运行写案例 `output_dir/result.json`），必须包含 `case_id` 与 case.json `output_contract` 声明的**全部字段**；任何字段无法填充时补 `null`，`status` 置 `partial` 并在 `gaps` 说明原因。
- 诚实性：禁止编造文献、DOI、元数据、引文关系或检索结果；每个事实性字段值必须带 locator（文件路径 + JSON 指针或边 id）。

## 工作流程（编号）

1. **读案例**：解析 case.json，取 `case_id`、`task.seeds`、`task.query_terms`、`window`、`materials_dir`、`output_dir`、`output_contract`；缺失任一关键字段即记录 gap（不中断）。
2. **定位材料**：按运行契约定位图谱文件与关键词 API 快照；定位不到图谱 → 直接走异常处理 A。
3. **加载图谱**：`scripts/graph_load.py` 解析图谱，输出节点表（带 `/nodes/...` locator）与边表（带 `/edges/...` locator 或边 id）。
4. **一轮滚雪球**：`scripts/snowball.py` 对每个种子做 backward（边的 target 是候选）与 forward（边的 source 是候选）扩展，聚合每个候选的方向、来源种子、边 locator、距离（恒为 1）、种子共被引次数；按 `window` 判定 `new` / `context`；收集 dangling reference 与缺失种子。
5. **读关键词候选**：从 API 快照提取候选（DOI、标题、摘要、年份，带 `/message/items/i` 这类 locator）。
6. **渠道合并**：`scripts/channel_merge.py` 以最低限度 DOI/标题精确匹配对齐两渠道，产出 `both` / `graph_only` / `keyword_only` 三分；`context` 与 `dangling` 不参与合并，单独成列。
7. **互补增益与诊断**：`scripts/complementarity.py` 计算互补增益（定义见 `references/complementarity-metrics.md`），对每条 graph_only 候选检查其标题/摘要是否含各查询词，给出漏检原因与指向材料原文的 evidence locator。
8. **排序**：对全部新候选按 (图谱距离升序, 种子共被引次数降序, 渠道 both 优先) 排序，排序依据逐条写 `reason`，保证透明可复核。
9. **组装结果**：`scripts/assemble_result.py` 按 `output_contract` 组装 result.json，缺失字段补 `null` 并置 `partial`；写 `output_dir/result.json`。
10. **自查**：按下方清单逐项核对，发现问题回退到对应步骤修正或诚实标注 partial。

## 异常处理（诚实降级，绝不中断后编造）

- **A. 无图谱文件**：result.json 照常输出，`expansion`、`merged.graph_only`、`complementarity` 等图谱相关字段补 `null` 或空表，`status=partial`，`gaps` 记录"未找到参考图谱文件（已搜索路径列表）"。关键词渠道结果仍可给出，但禁止伪造 graph_only。
- **B. 图谱为空（0 节点或 0 边）**：`expansion.records=[]`，互补增益补 `null`（分母为 0 时不输出数字），`status=partial`，gap 说明。
- **C. 种子缺失**：种子在图谱中既无节点也无边 → 列入 `expansion.seeds_missing`；全部种子缺失时等同 B。禁止用标题猜配其他节点顶替种子。
- **D. 快照缺失或不可解析**：关键词渠道字段补 `null`，合并退化为仅图谱结果，`status=partial`。
- **E. 日期缺失**：候选无任何可解析年份 → `in_window=null`，按 `new` 处理但打 `date_unknown` 标记并记 gap，禁止猜测年份。

## 输出契约（result.json 顶层字段）

以 case.json `output_contract` 为准；本 Skill 的标准字段集：

- `case_id`、`status`（complete / partial）、`generated_by`
- `task_echo`（seeds、query_terms 照读回显）、`window`
- `channels`：两渠道的来源文件、候选计数、locator 基址
- `expansion`：seeds_used / seeds_missing、逐候选扩展记录（方向、边 locator、距离、共被引次数、in_window、role）、dangling_references
- `merged`：`both` / `graph_only` / `keyword_only` / `context` 四列，每条带双渠道 locator
- `complementarity`：counts、graph_unique_gain（及定义字符串）、diagnosis（graph_only 漏检原因 + evidence locator）
- `ranking`：criteria 与 ranked 列表（逐条 reason）
- `gaps`、`notes`

## 自查清单

- [ ] result.json 存在且含 `case_id` 与 `output_contract` 全部字段（缺失已补 null 且 partial）。
- [ ] 所有引文边均可在图谱文件中找到（抽查边 locator 回指成功）。
- [ ] graph_only / keyword_only / both 三分计数之和 = 去重后新候选总数；context 与 dangling 未混入。
- [ ] 每条 graph_only 诊断的 evidence locator 指向材料原文，且原文确实不含所述查询词。
- [ ] 窗口外条目全部在 `context`；窗口内条目无被误标 context。
- [ ] 无任何字段值来自材料之外的来源；合成示例数据已显式标注 synthetic。
- [ ] 脚本仅用 Python3 标准库、全程离线。

## 脚本清单

| 脚本 | 职责 |
| --- | --- |
| `scripts/graph_load.py` | 加载参考图谱（nodes/edges、adjacency 两类布局），输出节点/边表（带 locator） |
| `scripts/snowball.py` | 一轮 backward/forward 扩展，聚合方向/共被引/窗口角色，收集 dangling 与缺失种子 |
| `scripts/channel_merge.py` | 关键词快照候选读取 + 与图谱候选最低限度对齐、渠道三分 |
| `scripts/complementarity.py` | 互补增益度量与 graph_only 漏检原因诊断（带 evidence locator） |
| `scripts/assemble_result.py` | 按 output_contract 组装 result.json，缺失补 null + partial |
| `scripts/run_minimal_example.py` | 端到端跑 examples/minimal 并自检（含 bundle 体积/文件数约束自查） |

## 参考文档

- `references/snowball-methodology.md` — 滚雪球方法学与一轮/多轮权衡
- `references/graph-layout.md` — 图谱文件布局约定与 locator 规则
- `references/complementarity-metrics.md` — 互补性度量定义
