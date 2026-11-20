---
name: refset-resolver-governance
description: 参考集构建与治理技能。用于"检索覆盖率与遗漏分析"类任务中可信分母（参考题录集合）的构建、核验、去重、处置与冻结。当需要从案例本地材料（综述 PDF 参考文献、专家清单、留存的参考文献图谱、本地 Crossref/EuropePMC/出版商 API 响应文件）中解析出规范化、可追溯、带出处与处置记录的参考集，并以冻结的 v1.0.0 参考集作为分母测量检索覆盖率、列漏检、做补检时使用。独特能力：以本地留存 API 响应为真值源逐条核验参考题录，产出审计可查的去重合并台账与逐条不可用处置记录，杜绝"以结果定分母"。边界：本技能不判定文献新颖性，不做实时覆盖度声明，不以搜索结果的并集充当分母，不替代后续的领域综述写作。
---

# 参考集构建与治理技能（refset-resolver-governance）

## 适用场景与边界

本技能面向检索覆盖率与遗漏分析任务中"分母先行"的治理环节。其核心命题是：覆盖率的分母必须先可信。只有当参考集中的每一条题录都经过解析、规范化、核验、去重、处置并冻结为带完整出处的版本化文件之后，覆盖测量、漏检清单与定向补检才具备可信基础。

适用场景包括：

- 从综述类 PDF 的参考文献列表中解析题录（可借助 pdftotext 提取文本后再解析，绝不依据文件名臆测内容）。
- 汇总专家给定清单与留存的参考文献图谱文件，形成候选参考集。
- 以案例本地留存的 Crossref、EuropePMC、出版商 API 响应文件为真值源，逐条核验标识符（DOI、PMID、arXiv）与题录字段。
- 对候选记录去重并产出审计可查的合并台账。
- 识别不可用记录（撤稿、标识符不可解析、全文不可得、标识符冲突）并逐条给出处置意见。
- 冻结版本化参考集（v1.0.0），随后以此冻结集合为分母测量覆盖率、列出漏检并执行定向补检。

明确边界：

- 不以任何一次或多次检索的结果并集充当分母；分母仅来自上述参考材料，与检索行为无关。
- 不输出实时覆盖度、新颖性或"最新发表"类声明；一切以案例本地留存材料为真值源。
- 联网 API（urllib 直连 Crossref/EuropePMC）仅在本地响应文件缺失或不足以核验时作为兜底手段，且必须缓存响应、标注来源、离线时诚实降级。
- 不执行付费墙绕过，不抓取受保护内容；全文不可得即记为处置记录，不作臆断。

## 运行环境与定位兜底

- 输入：`/input/case.json` 与 `/task.md`。工作目录为 `/app/work`，最终交付物置于 `/app/output`。
- 运行环境：Python 3，仅使用标准库；不执行 pip 安装，不引入任何第三方依赖。
- PDF 解析：优先使用系统中可用的 `pdftotext` 提取文本；不可用时诚实降级并在产物中注明。
- 图表渲染：仅在 matplotlib 可用时输出覆盖率预览 PNG；不可用或被禁用时静默跳过，报告仍以 Markdown 与 CSV 交付。
- 预算约束：模型请求不超过 64 次，总时长不超过 900 秒；技能资源不超过 50 个 UTF-8 文本文件、单文件不超过 500 KB、合计不超过 2 MB、不含符号链接与二进制文件。
- 定位兜底：任何脚本在材料缺失、网络不可达或解析失败时，均以 `status=partial`（或 `failed`，附原因）诚实降级，绝不伪造数据；所有产物中显式记录局限说明。

## 工作流程

1. **①解析案例与材料清单**：运行 `scripts/parse_case.py` 读取 `/input/case.json` 与 `/task.md`，解析 output_contract 字段要求，扫描材料目录，按类型（PDF、参考文献题录文件、API 响应 JSON、参考图谱）列出材料清单，搭建 `/app/work` 与 `/app/output` 目录骨架，产出 `materials_index.json`。
2. **②参考题录解析**：运行 `scripts/refset_build.py --stage parse`，从 BibTeX、RIS、CSV、JSON 或 PDF 提取文本中解析候选题录，保留原始字段与出处指针（文件名加行号或页码片段）。
3. **③标识符规范化与核验**：将 DOI、PMID、PMCID、arXiv 标识符规范化（规则见 references/identifier_normalization_rules.md），逐一与本地 Crossref/EuropePMC 响应文件比对；本地不足以核验时经缓存的 urllib 请求兜底，并标注 `verification_source`。
4. **④去重与合并台账**：以规范化标识符为强键、标题相似度（分块后排序词组 Jaccard）为弱键做阻塞式去重，合并记录写入 `dedup_log`，逐条保留被并记录与胜出记录。
5. **⑤不可用记录处置**：依据 references/failure_taxonomy.md 识别撤稿、标识符不可解析、全文不可得、标识符冲突等异常，为每条记录生成 disposition（exclude、flag_keep、needs_manual_review 等），写入 `exclusion_log`。
6. **⑥冻结版本化参考集**：汇总为 `reference_set.json`（版本 v1.0.0），每条记录携带 inclusion_reason、source 指针、verification_status、usable 标记；冻结后任何修改必须进入 change_log 并升版本号。
7. **⑦覆盖测量**：运行 `scripts/coverage_check.py`，以冻结参考集为分母，将检索结果记录先按规范化 DOI/PMID 精确匹配，再按标题相似度回退匹配，逐条输出 hit/miss、match_level 与证据指针；产出 `coverage_report.md` 所需的统计数据。
8. **⑧漏检清单**：将全部 miss 记录写入 `miss_list.csv`，一条不漏；漏检条目不得因"找不到"而被丢弃。
9. **⑨定向补检**：运行 `scripts/supplement_probe.py`，对每条漏检执行诊断探针——词表探针（核心术语是否在本地语料出现）、字段探针（作者/期刊/年份字段是否在本地响应中可命中）、时间窗探针（出版年是否落在检索时间窗之外）、来源探针（本地响应中是否存在该来源的覆盖证据）——产出具体到查询要素的归因与证据摘录。
10. **⑩复核与交付**：运行 `scripts/render_report.py` 汇总产物，生成覆盖报告 `coverage_report.md`、组装的 `result.json`（含 case_id 与 output_contract 的全部字段），并逐环节核对状态标记（complete/partial/failed）与证据指针后交付。

## 漏检归因原则（具体到查询/字段/时间窗/来源）

漏检归因拒绝模糊结论（如"数据库覆盖不足"）。每条漏检必须落到以下至少一个具体要素，并附证据摘录：

- **查询要素**：缺失的是哪个检索词或概念组；在本地语料中是否存在该词的变体（复数、英美拼写、同义词）导致原查询失配，证据须引用语料中出现而查询未包含的词形。
- **字段要素**：命中失败发生在哪个字段（标题、摘要、作者、期刊名、MeSH 主题词）；须指出本地响应记录中该字段的实际值与查询指定值之差。
- **时间窗要素**：给出漏检记录的出版年与检索式声明的时间窗上下界，以年比较得出窗口内/外结论。
- **来源要素**：指出漏检记录所属来源（期刊、数据库子集）在本地留存响应中是否存在覆盖证据，以及检索请求是否限定了来源集合。

证据一律以"文件名加定位（行号或 JSON 路径）加原文摘录"形式记录，保证可复核。

## 异常处置（撤稿/重复/无全文/标识符冲突/超时）

- **撤稿**：本地响应中存在撤稿标记（如 Crossref `relation` 中的 update、PubMed `retracted` 标记）时，该记录 `usable=false`、`disposition=exclude_retracted`；若撤稿信息仅来自单一渠道，标记 `needs_manual_review`。
- **重复**：标识符相同或标题高度相似的记录合并，保留字段更完整者，全过程写入 `dedup_log`；禁止静默丢弃。
- **无全文**：全文不可得不影响其作为分母成员（题录级核验仍有效），但 `usable_for_fulltext=false`，处置记为 `flag_keep_no_fulltext`。
- **标识符冲突**：同一记录携带的 DOI 与 PMID 在本地响应中指向不同文献时，标记 `identifier_conflict`，以字段更全、来源更权威的响应为准并记录取舍依据。
- **超时与网络失败**：联网兜底请求设置超时与缓存；超时即降级为本地核验结果，`status=partial`，并在 limitation 中记录失败请求与时间点，绝不重试至无限等待。

## result.json 契约

`result.json` 由 `scripts/render_report.py` 组装，必须包含：

- `case_id`：与 `case.json` 一致。
- output_contract 的全部字段：逐一取自对应产物，缺失字段以 `null` 填充并写入 change_log 说明。
- `status`：`complete` / `partial` / `failed` 之一，反映整个闭环中最弱环节。
- `sources`：实际使用过的全部材料与响应文件清单（路径加使用方式）。
- `uncertainty`：逐条记录不确定项，例如仅凭标题相似度匹配的记录、单一渠道核验的记录。
- `change_log`：参考集冻结后的任何变动、降级事件、人工修订，均带时间戳与原因。
- 覆盖率字段：`denominator`（冻结参考集条目数）、`hit`、`miss`、`coverage_ratio`，分母一经冻结不得改动。

## 失败与降级

- 退出码约定：`0` 表示正常完成；`2` 表示材料不足以构建可信分母（诚实降级，仍交付可用的部分产物与说明）；`3` 表示产物校验失败（例如 result.json 缺 output_contract 字段、参考集条目缺少必需出处字段）。
- 全部脚本支持 `--help`；解析失败不静默跳过，记录到对应日志并计入状态判定。
- 离线环境自动跳过联网兜底，核验范围缩至本地响应文件并在 limitation 中注明。
- 任何阶段产物缺失时，后续阶段以既有产物继续，状态降级为 `partial`，不得虚构数据补齐。

## 最小调用示例

```bash
python3 scripts/parse_case.py --case /input/case.json --task /task.md --workdir /app/work --outdir /app/output
python3 scripts/refset_build.py --workdir /app/work --outdir /app/output
python3 scripts/coverage_check.py --workdir /app/work --outdir /app/output --results /app/work/search_results.json
python3 scripts/supplement_probe.py --workdir /app/work --outdir /app/output
python3 scripts/render_report.py --workdir /app/work --outdir /app/output
```

若本地无检索结果文件，`coverage_check.py` 与 `supplement_probe.py` 将以 `status=partial` 输出空清单与说明，参考集治理产物不受影响。
