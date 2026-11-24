---
name: theme-evolution-cartography
description: 用于文献综述/研究前沿分析任务中的主题演化语义分析与代表作遴选：当任务需要回答"主题如何随时间演化、何时演化、哪些工作能代表每个阶段"时使用。它用语料可复算的词项队列矩阵、相邻年余弦距离阶段划分、术语漂移报告和带阶段配额的多准则代表作打分，产出全部可审计的证据表；同义词表由代理阅读语料后判断并留档。它不做嵌入语义聚类、不做因果断言、不做引文网络分析，绝不接受"换了说法=新兴主题"或"引用Top-N=代表作"这类结论。
---

# theme-evolution-cartography — 主题演化语义层与代表作遴选

## 1. 定位

本 Skill 的重心是**主题演化的语义层**：演化结论必须来自可复算的**词项队列矩阵**（哪些词项何时出现、合并、分裂、衰退），术语漂移（术语换了说法）必须被识别为"同一队列的词面变化"，而不是被计成新主题；代表作必须用**可审计的多准则打分 + 每阶段配额**遴选。它直接处死两条反模式：

- **换词=新兴主题（术语漂移）**：`drift_report.json` 对每个 canonical 词项给出各变体的逐年文献计数。若变体 A 早、变体 B 晚、合并队列连续，则这是改名而非新主题，报告中必须如此表述。
- **引用 top-N=代表作**：纯引用排序系统性偏向 mid-life 阶段（积累时间够长、又足够新被持续引用），漏掉早期开创与最新阶段。`representative_select.py --baseline top-citations` 内置该反模式基线并做覆盖率闸门，覆盖不全即 exit 1——你必须用多准则模式并附上完整打分表。

本 Skill 仍要求走完**完整四交付物流程**：时间趋势、主题演化（含何时+为何）、覆盖全部阶段的代表作（遴选口径可说明）、有排除证据支撑的研究空白。脚本直接支撑第 1/3/4/5 步，第 2 步（时间趋势）与第 6 步（研究空白）给出具体程序。

## 2. 固定路径

- Skill 安装位置：`/skills/weekly-skill/`（脚本在 `/skills/weekly-skill/scripts/`，本文件在 `/skills/weekly-skill/SKILL.md`）
- 输入：`/input/case.json`、`/input/task.md`、`/input/` 下文献材料（json/jsonl/csv/bib/ris/txt/md，可能有 PDF）
- 工作目录：`/app/work/`（所有中间产物）
- 交付：`/app/output/`，其中 `result.json` 为必需
- PDF：平台提供 pdf-text/pdf-render/ocr 工具；**必须读真实文件内容，绝不凭文件名/标签猜测**；PDF 抽取出的条目存成 txt/md/jsonl 后即可进入 build_corpus

## 3. 执行协议

### 第 0 步 读契约 + 建档（最先做，不可跳过）

1. 读 `/input/case.json`：记下 `case_id` 与 `output_contract` 列出的**每一个字段名**。
2. 读 `/input/task.md`：圈定主题范围、时间口径、交付物要求。
3. 盘点 `/input/` 材料文件（格式、数量、是否 PDF）。
4. **立即**写 `/app/output/result.json` 骨架：`case_id` + output_contract 每个字段的占位值 + `status` + `provenance`（输入文件清单）。此后每完成一步就回填对应字段——这样即使中途预算耗尽，留下的也是诚实的 partial，而不是零交付。
5. 若材料无法构成语料（目录为空/全部不可解析/与本主题无关）：`status=blocked_no_corpus`，写明尝试过的解析路径与证据，**绝不编造语料或结论**。

### 第 1 步 语料归一（build_corpus）

```
python3 /skills/weekly-skill/scripts/build_corpus.py --work /app/work --inputs /input <任何PDF抽取产物>
```

产出 `/app/work/canon.jsonl`（id/title/year/abstract/keywords/citations/source_file）。缺键容忍、年份缺失记 null、被引缺失记 0。抽查 3–5 条确认 year/abstract 没有解析错位；记录每条来源文件以便回链。

### 第 2 步 时间趋势（年度分布）

从 canon.jsonl 直接统计每年文献数（可顺手用 `year_vectors.json` 的年份键核对）。要求：

- 写明**日期口径**：用出版年还是入库年，来源字段是什么；
- **Poisson 噪声提醒**：年计数是随机计数，小样本年份间 ±√n 的波动不构成"趋势"，只报告超过噪声水平的结构（持续斜率、台阶）；
- **末年截尾**：最后一年（尤其当年）通常不完整，必须标注 censoring，不得把末年下降读成"热度消退"；
- 结论形态："2016–2020 年年均 X 篇、为 2010–2015 的 Y 倍"这类可核对表述，绑定 canon id 计数。

### 第 3 步 词项队列（term_cohorts）

```
python3 /skills/weekly-skill/scripts/term_cohorts.py --work /app/work --synonyms /app/work/synonyms.json
```

- **synonyms.json 是代理的判断产物**：先不带同义词表跑一遍，读 `top_terms.csv` 与高 df 词项的原文上下文，识别"同一概念的不同说法"（缩写/全拼、英美拼写、新旧术语），写成 `{变体: 规范形}` 存 `/app/work/synonyms.json`，并在报告里把它列为**版本化证据工件**（谁、依据什么上下文合并了哪些词面）。合并要保守：只在上下文确证同义时合并。
- 产出 `term_year_matrix.json`（词项→逐年文献计数）、`year_vectors.json`、`record_terms.json`、`top_terms.csv`。词项抽取口径见 `references/term_normalization.md`。
- 词项热度本身**不是**趋势结论；它只是后续阶段划分与漂移检测的输入。

### 第 4 步 阶段划分（phase_segment）

```
python3 /skills/weekly-skill/scripts/phase_segment.py --work /app/work --synonyms /app/work/synonyms.json
```

- 规则（已写入 `phases.json` 的 meta 供复核）：相邻年词项向量余弦距离 → 1-2-1 核平滑 → 局部极大且 > median+1×MAD 处为候选边界。
- 产出 `phases.json`（每阶段 dominant/emerging/declining 词项）与 `drift_report.json`（术语漂移检测）。
- **每条演化论断必须含三件套**：(a) 何时（边界年，注明平滑与阈值带来的 ±1 年不确定性）；(b) 前后 dominant-term 证据（引用 phases.json 的词项与份额）；(c) 一条从记录本身得出的**合理机制**（如某方法在某基准上取代了前者），并显式标注为**推断**，绑定具体 canon id。
- 漂移结论范式："X 在 2023 年后改称 Y：变体计数 {X:2021–22, Y:2023–24}，合并队列 2021–24 连续——系术语漂移，非新兴主题。"

### 第 5 步 代表作遴选（representative_select）

```
python3 /skills/weekly-skill/scripts/representative_select.py --work /app/work --per-phase 2
```

- 打分（口径见 `references/selection_rubric.md`）：0.5×阶段内引用百分位 + 0.3×词项中心度 + 0.2×方法首发奖励，每阶段取 top-K。
- `representatives.json` 含**每个候选**的完整分项打分表——把它直接放进证据矩阵，遴选口径因此可说明、可复算。
- 闸门：任一阶段 0 代表作 → 警告（语料空洞，需在报告中指明）；交付前可跑一次 `--baseline top-citations` 自证：若基线覆盖率 < 1.0（exit 1）而你的多准则结果覆盖全阶段，就在报告中引用这个对比作为反模式证据。
- 代表作仍须人工读摘要确认"该文确实在做该阶段的核心工作"；打分表决定候选与口径，最终表述由你负责。

### 第 6 步 研究空白（排除证据，不是"没检索到"）

每条空白论断必须附**排除证据**三件套：

1. **检索范围**：语料来自哪些文件/库、时间跨度、共 N 条（引用 canon 计数）；
2. **近似命中分析**：列出最接近空白主题的记录（canon id），说明它们做到哪一步、缺哪一块——空白存在于"近似命中与目标之间的差集"；
3. **定位**：该空白落在哪个阶段/哪条主题线上（引用 phases.json 的阶段与词项）。

程序建议：用 `term_year_matrix.json` 检查空白主题相关词项的 df 与逐年计数，确认不是同义词漏并（先查 synonyms.json 是否该扩）；若词项 df=0，做近似词面扫描（子串/相关 bigram）找出"差一步"的记录作为近似命中。表述范式："在 30 条语料（2010–2024）中，'多模态情感分类'词面 0 命中；最近似的是 P26/P27（纯文本 foundation model  prompting），缺模态融合环节；该空白位于 P3 阶段的 transformer 主线。"

### 第 7 步 证据回链与定稿

- 每条结论（趋势/演化/代表作/空白）必须携带 canon id 列表；不允许无 id 断言。
- 回填 `/app/output/result.json` 全部 output_contract 字段；写 `/app/output/theme_report.md`（四交付物各一节 + 证据矩阵 + 不确定性节）。
- 定稿前自查：趋势有日期口径与截尾声明吗？演化有边界年+前后词项+机制推断标注吗？代表作覆盖全部阶段且打分表随附吗？空白有排除证据三件套吗？

## 4. 输出契约

`result.json` 必须含 `case_id` + `output_contract` 列出的**全部字段**，外加：

- `status`: `ok` / `partial` / `blocked_no_corpus` / `blocked_no_year_span` / `blocked_*`
- `evidence`: 关键工件路径与 canon id 锚点
- `uncertainty`: 边界年容差、同义词表主观性、末年截尾、语料覆盖偏倚

`partial` 必须说明哪部分完成、哪部分受限、受限原因；完成部分照常给出证据。

## 5. 预算规划（64 请求 / 900 s）

- 第 0 步契约+建档：≤3 请求，立即落盘 result.json 骨架。
- 脚本调用都是**一次 bash 即完成**且可串行连跑；把 4 个脚本合在 1–2 次 bash 调用里，总脚本开销 ≤4 请求。
- 阅读/判断集中在：top_terms.csv 与同义词表起草（≤6 请求）、代表作摘要确认（≤6 请求）、空白近似命中分析（≤6 请求）。
- 预留 ≥8 请求用于写 theme_report.md、回填 result.json 与自查。超时风险大时优先保：result.json 字段齐全 + 四交付物各有一句有证据的诚实结论。

## 6. 异常处理

| 异常 | 处理 |
|---|---|
| 无语料/解析全失败 | status=blocked_no_corpus；写明尝试过的格式与文件清单；不编造 |
| 年份缺失严重或仅单一年份 | 阶段划分不可能：仍给年度事实与词项队列，演化节改为 exploratory note（说明无法分段），status=partial |
| 重度多语混合语料 | 英文走 unigram+bigram，中文走关键词整词+字符 bigram（见 normalization 参考）；两语词项分开报告，不硬合并；结论注明语种口径 |
| 同义词歧义（同名异义，如 "transformer" 在电力文献中） | 不合并；抽查该词面 3–5 条原文上下文，按多数语义决定；把决定与上下文 id 记入 synonyms.json 的 `_comment` 与报告 |
| 阶段边界不稳定 | 换平滑强度（如去掉平滑或改阈值倍数）重跑 phase_segment；若边界移动 >1 年，报告两个候选边界并给出敏感性说明，不得只报单一"精确"边界 |
| 某阶段 0 代表作 | representative_select 已警告；在报告中显式指认语料空洞（该阶段记录数），空白节将其列为证据，不强行凑数 |
| baseline 覆盖率 < 1.0 | 这是预期证据：引用对比说明纯引用 top-N 漏掉哪些阶段，作为采用多准则口径的理由 |

## 7. 不适用

- 需要嵌入向量/神经模型的语义聚类（运行期无外部模型可用；本 Skill 用语面队列近似语义，结论精度受此限制）；
- 因果断言（"X 导致了 Y 的兴起"只能作为标注过的推断）；
- 引文网络/共被引/耦合分析（citations 字段只用作阶段内相对百分位）；
- 语料与主题无关或检索本身不可信时，先解决检索问题，本 Skill 不背书垃圾语料上的"精确"演化图。

## 8. 合成示例

`examples/` 内含 **30 条合成记录（2010–2024，明确标注 synthetic/合成）**：埋入三阶段词面结构（SVM/kernel → deep/convolutional → transformer/PLM）、一对术语漂移（"pretrained language model"→"foundation model"）、以及一个引用陷阱（全局引用 top-5 全在第二阶段）。`bash examples/run_example.sh` 一次跑通 GOOD（exit 0，复现 ±1 年内的三阶段边界、漂移报告、每阶段 2 代表作含打分表）与 BAD（`--baseline top-citations` exit 1，覆盖率 1/3 违规点名未覆盖阶段）。产物在 `examples/example_output/`。
