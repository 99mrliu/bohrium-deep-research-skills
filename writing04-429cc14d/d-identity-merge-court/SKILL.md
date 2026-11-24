---
name: identity-merge-court
description: >-
  文献去重与身份归并（方向 D）。适用：多来源文献库（BibTeX/RIS/CNKI/EndNote/Crossref/arXiv 导出）的
  去重候选挖掘、同一文献身份裁决（中英文题名对、预印本与正式版、跨数据库导出字段差异）、
  可解释合并（逐案理由+冲突字段表+谱系保留）、引用出现点重定向复核、同姓同年不同文献保护。
  不适用：无任何标识符与坐标佐证的纯印象式合并；凭记忆补造 DOI/元数据；会议扩展版与期刊版
  等"不同工作"的归并；撤回/更正规约与原文的归并。
---

# identity-merge-court — 可解释身份裁决的文献去重与归并

## 核心主张

去重不是字符串相似度问题，而是**身份判定问题**。本 skill 把流程切成两段：**候选挖掘**只负责
"可能是同一文献"并给出证据分级（strong / moderate / weak），它从不合并任何东西；**裁决**必须是
保守的、逐案给理由的"判案"——每条候选组只有三态：`merge` / `keep_separate` / `human_queue`，
每条决定都附证据、逐字段冲突表与回退方案。所有被并条目的引用出现点必须全部重定向到 canonical
并有脚本复核；同姓氏同年但题名/容器显著不同的文献**显式保护**不予合并；预印本并入正式版必须
保留谱系（preprint id、版本关系、重定向），**绝不凭印象补造正式版 DOI**。

## 运行时契约（必须先读）

1. **逐文件读真实内容**：开工前逐一读取 `/input` 下的 `case.json`、`task.md` 与全部真实材料
   （稿件、文献库导出、可能的快照）。不得凭文件名或经验猜测内容。
2. **先读 resources.yaml**：若 skill 目录或输入中存在 `resources.yaml`，先读它再行动。
3. **工作目录**：中间产物写 `/app/work`；最终产物写 `/app/output`。
4. **result.json 契约**：`/app/output/result.json` 必须**逐字**包含 `case.json` 中的 `case_id`
   与 `output_contract` 的**全部原始字段**（原样照抄，不改名、不省略、不改写值），再追加本任务
   要求的结果字段。
5. **两阶段写 result.json**：第一阶段（开工时）立即写出骨架，`status` 置 `"in_progress"`，
   已知的契约字段照抄填入；之后每完成一个阶段**回填**对应字段；全部完成才置最终状态。
   骨架与回填都不可省。
6. **预算**：运行预算上限 64 / 900 / 16384（以 harness 解释为准）。候选挖掘与裁决施加交给
   确定性脚本完成，模型只做规则内裁决与文书工作，避免在长清单上逐条手工比对消耗预算。
7. **status 诚实**：完成了多少就写多少。存在未决 human_queue 项时，`status` 不得宣称完全成功，
   必须在不确定性字段中登记未决清单。
8. **禁止伪造**：不凭记忆合并任何条目；不杜撰 DOI/PMID/arXiv 号/页码；不把"相似"写成"同一"；
   不臆译中英题名当作匹配依据。凡写入产物的身份断言，必须能在材料或标识符中找到证据。

## 产物地图（/app/work 与 /app/output）

| 产物 | 位置 | 产生阶段 | 说明 |
|---|---|---|---|
| records.jsonl | /app/work | 1 | 规范化建档，一行一条，保留 raw 与 parse_warnings |
| candidates.json | /app/work/candidates | 2 | 候选组 + 信号 + 逐字段冲突表 + 证据分级 |
| decisions.json | /app/work | 3 | 模型逐案书写的三态裁决（本 skill 的核心文书） |
| merged_records.jsonl | /app/work/merge | 3 | 归并后文献表（canonical 吸收成员、例外与谱系在记录内） |
| redirect_map.json | /app/work/merge | 3 | 被并 record_id / cite_key → canonical 的重定向表 |
| merge_report.json / .md | /app/work/merge | 3 | 逐案 rationale：成员、证据、理由、冲突表、谱系 |
| residual_report.json / .md | /app/work/redirect | 4 | 引用重定向残留复核 |
| 归并后文献表 | /app/output | 4 | 按 output_contract 要求的格式导出 |
| 改后稿 | /app/output | 4 | 引用出现点已重定向的稿件 |
| result.json | /app/output | 0→4 | 契约字段照抄 + 分阶段回填的结果字段 |

## 工作流程（五阶段）

### 阶段 0 — 盘点与契约骨架

- 清点 `/input`：稿件、各来源文献导出、既有文献表、快照；登记文件清单与格式。
- 从 `case.json` 照抄 `case_id` 与 `output_contract` 全部原始字段，写 `/app/output/result.json`
  骨架（`status: "in_progress"`）。
- 明确任务边界：本任务是去重归并为主，还是还包含引用插入/编号更新/格式转换/来源核验；
  边界之外的子任务按各自要求另立产物，不混入归并报告。
- 与其他子任务的接口约定：
  - **引用插入 / 编号更新**：以归并后的 canonical 标签为唯一引用目标，插入与重排
    一律在重定向完成之后进行；
  - **格式转换**：输入是 merged_records.jsonl，身份结论（merged_from / lineage /
    merge_exceptions）在转换中原样携带，不得"顺手改掉"；
  - **来源核验**：human_queue 组的核查结论若能从材料内获得（快照、note、任务给出
    的辅助文件），回到阶段 3 重新裁决；材料内无法获得则保持未决，不得臆断。

### 阶段 1 — 记录规范化建档（records.jsonl）

把每一条文献记录规范化为 `/app/work/records.jsonl` 的一行 JSON（格式详见
`references/record_formats.md`），硬性要求：

- **保留 raw 原文**：原导出片段原样存入 `raw` 字段，归并后仍可回溯；
- **保留原标签/键**：`cite_key`（BibTeX key、EndNote 编号、CNKI 序号等）原样保留；
- **全部作者含机构**：`authors` 数组按原顺序，含 `family` / `given` / `affiliation`；
- 题名（含 `title_original` 中文原题名）、年份/日期、文献类型、刊名/容器、卷期页/文章号、
  DOI / PMID / arXiv / URL、版本信息（preprint v1/v2 等）逐字段建档；
- **解析警告逐条登记**：缺字段、年份无法解析、字段冲突等写入 `parse_warnings`，
  不得静默丢弃。

各来源转档要点：

- **BibTeX**：可用 `--bib` 直接解析；`journal` / `booktitle` 归入 `container`，
  `eprint` + `archiveprefix=arXiv` 归入 `arxiv`，`author` 按 ` and ` 拆分。
- **RIS**：`TY`→`type`、`TI`→`title`、`AU`→`authors`（逐行一个）、`JO`/`JF`→`container`、
  `PY`→`year`、`DO`→`doi`、`UR`→`url`、`N1`→`note`；整段原文入 `raw`。
- **CNKI 导出**：中文题名入 `title`，英文题名（如有）入 `note` 或单独字段；作者拆
  `family`/`given`；页码、卷期原样保留；缺 DOI 属常态，按阶段 2 的坐标信号 corroborate。
- **EndNote**：注意 DOI 常被放进 `url` 或 `accession` 字段——脚本会从 `url` 提取 DOI，
  但**绝不从 note 等自由文本提取身份 DOI**（note 里的 DOI 可能是关系声明）。
- **arXiv 导出**：`type=preprint`，保留版本号（v1/v2）于 `version`；若条目自带
  "Published in ..." 类 note，**原样保留**——它是 S4 信号升级 strong 的关键材料内证据。

可选加速：`scripts/dedup_candidates.py --bib library.bib` 可直接行级解析简易 BibTeX
（`@type{key, field={...}}`），自动保留 raw；RIS/CNKI/EndNote 等格式请先人工或脚本转档为
records.jsonl。

### 阶段 2 — 候选挖掘（dedup_candidates.py）

```bash
python3 /skills/weekly-skill/scripts/dedup_candidates.py \
  --records /app/work/records.jsonl --out /app/work/candidates
# 本地复现用相对路径：python3 scripts/dedup_candidates.py --records examples/input/records.jsonl --out examples/output
```

五类候选信号（实现细节见脚本 docstring 与 `references/adjudication_rules.md`）：

| 信号 | 触发条件 | 证据分级 |
|---|---|---|
| S1 same_doi | 规范化 DOI 相同（大小写折叠、去 doi.org/doi: 前缀；可从 url 字段提取） | strong |
| S2 same_title | 规范化题名相同（NFKC + casefold + 去标点空白 + 去停用冠词 the/a/an）；坐标（第一作者姓/年/容器）一致数 ≥2 才升 moderate | moderate / weak |
| S3 translation_pair | 中英题名对：**仅**通过材料内 `translation_of` 字段线索或共享标识符触发，绝不允许模型臆译判定 | strong（共享标识）/ moderate |
| S4 preprint_published | 规范化题名相同 + 一方为预印本（含 arXiv id）+ 容器/年异；材料内 note 声明关系则升 strong | strong / moderate |
| S5 author_year_title_jaccard | 同第一作者姓 + 同年 + 题名 token Jaccard ≥ 0.8；容器一致才升 moderate | moderate / weak |

输出 `candidates.json`：候选组（并查集连通分量，确定性排序）、每组的信号列表（>2 条组按
成员对给出两两证据）、**逐字段冲突表**（field → {record_id: raw_value} + `normalized_equal`
标记）、组级证据分级。**本阶段不合并任何记录。**

证据分级语义（裁决时据此选择门检强度）：

- **strong**：共享规范化标识符（DOI / PMID / arXiv），或材料内明确声明的版本/翻译关系
  （note 写明 "Published in ... DOI ..."、`translation_of` 字段）。strong 证据 + 坐标一致
  → M1/M4 可 merge；strong 证据 + 坐标冲突 → M2 必须 human_queue。
- **moderate**：规范化题名相同且有坐标佐证，或同姓同年高 Jaccard 且容器一致，或仅材料内
  `translation_of` 线索。可 merge，但 reason 必须逐条列出佐证坐标。
- **weak**：仅题名相似（裸题名相同而无坐标佐证、或 Jaccard 触达但容器不同）。**默认不可
  合并**：keep_separate 或 human_queue，判 merge 会被 M3/M5 拒绝。

书写 decisions.json 的要求：

- 每个候选组**恰好一条**裁决；缺组、重复组、未知组都会被拒绝。
- `reason` 是硬性要求（非空且有实质内容）：写清触发哪条 M 规则、依据哪些信号、
  冲突字段如何解释、canonical 选择依据。
- `keep_separate` 与 `human_queue` 永不拒绝（保守方向不造成不可逆后果）；只有 `merge`
  需要通过 M1–M5 全部门检。
- 拿不准就 `human_queue`：它不是失败，而是把不可自动判定的身份问题显式升级，
  并在阶段 4 写入不确定性清单。

### 阶段 3 — 裁决（merge_adjudicate.py）

模型逐组阅读 `candidates.json` 的证据与冲突表，按 M1–M5 规则（精确定义见
`references/adjudication_rules.md`）写出 `/app/work/decisions.json`（每组一条：
`group_id`、`verdict ∈ {merge, keep_separate, human_queue}`、`canonical`（merge 时必填且必须
是组成员）、非空 `reason`），然后交给脚本**校验并施加**：

```bash
python3 /skills/weekly-skill/scripts/merge_adjudicate.py \
  --candidates /app/work/candidates/candidates.json \
  --records /app/work/records.jsonl \
  --decisions /app/work/decisions.json --out /app/work/merge
```

校验规则（违反即整体拒绝，**退出码 1 且不写任何产物**，原子）：

- **M1** 同规范化 DOI 且书目坐标一致 → 允许 merge；
- **M2** 同规范化 DOI 但书目坐标（年/卷/期/页/文章号）规范化后冲突 → **必须 human_queue，
  禁止自动并**；
- **M3** 仅题名相似、无坐标或标识符 corroboration（组证据 weak）→ 禁止 merge；
- **M4** 预印本-正式版关系成立（共享标识或材料内证据）→ 允许并入正式版，**canonical 必须是
  正式版**，且必须留谱系；
- **M5** 同第一作者姓 + 同年但题名/容器显著不同 → 禁止 merge（同名作者不同文献保护）。

全部通过才施加 merge：canonical 吸收成员字段（缺失补齐）、双方标识符全部保留进
`other_identifiers`、冲突字段入 `merge_exceptions`（exception list）、预印本谱系写入
`lineage`；输出 `merged_records.jsonl`、`redirect_map.json`（被并 id / 原标签 → canonical）、
`merge_report.json` / `merge_report.md`（逐案 rationale：成员、证据、理由、冲突表、谱系）。

### 阶段 4 — 收口

1. **引用重定向**：按 `redirect_map.json` 把稿件中所有被并 id / 原标签的引用出现点改写为
   canonical 标签；改写后必须复核：

   ```bash
   python3 /skills/weekly-skill/scripts/redirect_check.py \
     --manuscript /app/work/manuscript_updated.txt \
     --redirect_map /app/work/merge/redirect_map.json --out /app/work/redirect
   ```

   有残留即退出码 1，逐行修复后重跑直至干净。
2. 生成归并后文献表（`merged_records.jsonl` 按需转 BibTeX/RIS/GB-T 7714 等目标格式；
   转换是独立步骤，不得改动身份结论）。
3. **回填 result.json**：契约字段照抄不动；结果字段建议包含（按 output_contract 调整命名）：
   - 归并后文献表与改后稿的产物路径；
   - `merge_report` 路径与统计：候选组数、merge / keep_separate / human_queue 各多少、
     记录数变化（归并前→归并后）、重定向条数；
   - 残留复核结论（residual_report 路径、退出码、修复轮次）；
   - 归并可逆性说明（merged_from / redirect_map 位置）。
4. **human_queue 未决清单**：逐条写入结果的不确定性字段（组 id、成员、冲突字段、建议核查
   路径），`status` 如实反映存在未决项。未决清单的每一行都必须能回答三个问题：
   冲突是什么、为什么机器不能判、人应该去看哪里。

## 异常处理表

| 情形 | 处理 |
|---|---|
| 撤回/更正规约（retraction / correction notice） | **不是原文副本，不得并入原文**；作为独立记录保留并在 note 中标注关系，必要时 human_queue |
| 会议扩展版 vs 期刊版（扩展 ≥30% 新内容等） | 是**不同工作** → `keep_separate` 并写理由；只有"同一工作的预印本→正式版"才适用 M4 |
| 任务明确授权且有充分证据的合并 | 执行，不拖延；逐案 rationale 照常生成，不得因"保守"而拒做已授权的明确合并 |
| 数据库导出缺 DOI | 按题名 + 坐标（第一作者/年/容器/卷期页）corroborate，S2 moderate 以上才可 merge；**绝不臆造 DOI** |
| 候选组 >2 条 | 按 signals 中的两两证据表逐对核对；只许一个 canonical，其余全部重定向；任何一对证据存疑即整组 human_queue |
| canonical 选择 | 正式版优先于预印本（M4 强制）；字段全者优先；保留双方标识符；同分时取记录序靠前者并在 reason 中说明 |
| 同 DOI 但年份/卷页冲突（如聚合库导出错误） | M2：human_queue，禁止自动并；核查 DOI 落地页后再裁决 |
| 同姓同年不同文献（题名/容器显著不同） | M5：keep_separate，显式写保护理由，redirect_map 中不得出现其条目 |
| 中英题名对 | 仅在材料内 translation_of 线索或共享标识符下触发 S3；模型臆译一律无效，按 M3 处理 |

## 最小调用示例（合成示例）

见 `examples/minimal_example.md`：`examples/input/records.jsonl` 为 **21 条全虚构合成记录**
（人名、刊名、DOI、arXiv 号、PMID 均为编造，仅用于演示），覆盖 7 个应并重复与 3 个陷阱；
`examples/output/` 是三个脚本在其上**真实运行**的产物。

## 调用命令速查

竞赛环境（评测方把本 skill 安装到 `/skills/weekly-skill`）：

```bash
python3 /skills/weekly-skill/scripts/dedup_candidates.py --records /app/work/records.jsonl --out /app/work/candidates
python3 /skills/weekly-skill/scripts/merge_adjudicate.py --candidates /app/work/candidates/candidates.json \
  --records /app/work/records.jsonl --decisions /app/work/decisions.json --out /app/work/merge
python3 /skills/weekly-skill/scripts/redirect_check.py --manuscript /app/work/manuscript_updated.txt \
  --redirect_map /app/work/merge/redirect_map.json --out /app/work/redirect
```

本地复现（仓库根目录下用相对路径，三者均为确定性、仅标准库、无网络）：

```bash
python3 scripts/dedup_candidates.py --records examples/input/records.jsonl --out examples/output
python3 scripts/merge_adjudicate.py --candidates examples/output/candidates.json \
  --records examples/input/records.jsonl --decisions examples/input/decisions.json --out examples/output
python3 scripts/redirect_check.py --manuscript examples/input/manuscript.txt \
  --redirect_map examples/output/redirect_map.json --out examples/output
```

退出码约定：三个脚本均为 0=成功；merge_adjudicate 与 redirect_check 在拒绝/检出残留时为 1
（前者原子不写产物）；输入读取或用法错误为 2。

## 回退方案

- 任何 merge 都是可逆的：merged_records.jsonl 中 canonical 记录保留 `merged_from`、
  `aliases`、`other_identifiers` 与 `merge_exceptions`，records.jsonl 中的 raw 原文不丢；
  撤销一次合并 = 按 `merged_from` 把成员记录恢复原位 + 按 redirect_map 反向改回引用标签。
- merge_adjudicate.py 校验失败时不写任何产物（原子），修正 decisions.json 后重跑即可，
  不存在"写了一半"的中间态。
- redirect_check.py 检出残留时，按报告的行号逐处改写后重跑，直至退出码 0 再回填
  result.json。

## 限制与适用范围

- 候选挖掘是字符串/标识符层面的确定性信号，不调用任何外部数据库；无材料内证据的身份断言
  一律降级为 human_queue，而不是联网"补全"。
- 题名规范化对改写式变体（换序、同义改写）无能为力；此类候选只能靠 S5 的 Jaccard 信号弱触达，
  默认 keep_separate / human_queue。
- 中英题名对的判定**只**接受材料内线索（translation_of 字段、共享标识符）；模型语言能力
  不得用于"我认为这两个题名是翻译关系"的断言。
- BibTeX 解析为行级简易实现，不处理宏定义与复杂嵌套；RIS/CNKI/EndNote 需先转档为
  records.jsonl。
- Jaccard 阈值 0.8 是候选门槛，不是合并依据；阈值附近的组天然偏向 human_queue。
- M2 的"元数据冲突"精确限定为书目坐标（年/卷/期/页/文章号）规范化后不一致；题名/刊名/
  作者的语种与格式差异（中英译名、罗马化、大小写、连字符样式）不触发 M2，而是记入
  exception list 供人工抽查——详见 references/adjudication_rules.md。
- 本 skill 不做引用格式渲染（GB/T 7714、APA 等）本身，格式转换以归并后的
  merged_records.jsonl 为输入另行处理。
- 本 skill 的裁决保守性意味着它**宁可漏并不可误并**：漏并的代价是人工补一刀，
  误并的代价是错误引用进入成稿。
