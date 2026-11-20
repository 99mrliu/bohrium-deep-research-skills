---
name: targeted-supplement-loop
description: >-
  用途：在检索覆盖率与遗漏分析任务中，对基线检索的漏检部分执行“定向补检”，
  并将补检当作可度量的投资来治理——每条补充查询都从具体漏检记录的原文词项生成，
  带有假设、目标漏检、成本与边际收益记账，在显式停止规则下终止，
  最后以确定性复跑与人工抽检复核形成闭环。
  适用时机：已完成或可获得初始检索结果，需要证明补检真实减少遗漏、
  而非同义词空转式“伪补检”时。典型输入为 /input/case.json 与 /task.md，
  工作目录为 /app/work，交付目录为 /app/output。
  独特能力：漏检驱动的四类查询原型（原词补全式、作者+年锚定式、引文追踪式、
  来源切换式）、按批次核算的边际覆盖率收益（marginal_coverage_gain）、
  STOP-1/2/3 显式停止规则、残余遗漏逐项归因与“何种条件可检回”的说明、
  端到端确定性复跑与“边界命中全量复核 + 每第 5 条干净命中抽检”的审计协议。
  边界：仅对本地组织者留存材料（实际 PDF、真实 Crossref/EuropePMC/出版商
  API 响应文件、真实参考文献图）离线执行，不发起任何远程请求，
  不声称任何实时覆盖率或新颖性；覆盖率分母一律来自冻结参考集，
  绝不以检索结果自身推导分母；对无法核验的命中一律降级标注，绝不虚构。
---

# targeted-supplement-loop：定向补检的边际收益治理与闭环复核

## 适用场景与边界

本技能适用于“检索覆盖率与遗漏分析”类任务中已完成初始检索、
需要对漏检部分进行可证明有效的定向补检的场景。其核心立场是：
补检必须像投资一样被度量——每条补充查询都有明确假设、目标漏检记录、
生成依据（引用漏检记录原文词项）与边际收益核算，并在可验证的停止规则下终止。

本技能的适用边界如下：

1. 一切检索与核验均在本地组织者留存材料上离线完成：
   实际 PDF 文本（必要时用 pdftotext 抽取）、
   Crossref／EuropePMC／出版商 API 的真实响应文件、真实参考文献图。
   本地响应文件是事实来源（source of truth）。
2. 覆盖率分母必须来自冻结参考集（见 `freeze_refset.py`），
   绝对禁止用检索结果的并集反向构造分母；未检出的参考记录必须作为
   漏检持续跟踪至残余遗漏报告，不得静默丢弃。
3. 每条边际收益都必须用同一冻结参考集重新匹配核验；
   零收益的补检批次如实记为零收益，禁止以同义词替换冒充新增覆盖。
4. 不处理撤稿判定本身（由参考集解析侧标注），但补检命中撤稿记录时
   必须如实标注并在报告中单列；不虚构任何网络获取结果，
   网络缺失或超时一律降级为 `status=partial` 并写明限制。

## 运行环境与定位兜底

- 运行位置：以 `/app/work` 为工作目录，读取 `/input/case.json` 与 `/task.md`，
  最终交付物写入 `/app/output`。所有路径均可通过命令行参数覆盖，
  便于在本地目录中复现。
- 解释器：Python 3，仅使用标准库；不依赖 pandas、requests、numpy 等第三方包。
- 技能资源约束：全部文本文件为 UTF-8，技能包不超过 50 个文件、
  单文件不超过 500 KB、总计不超过 2 MB；不含符号链接与二进制文件。
- 每个脚本均支持 `--help`；统一退出码：`0` 正常；
  `2` 材料不足时的诚实降级；`3` 校验失败（确定性复跑不一致等）。
- matplotlib 若可用可用于绘制边际收益曲线（可选，PNG 输出）；
  该图永远不是必需交付物，缺省时以表格形式呈现相同信息。

## 工作流程

① 材料清点与参考集冻结。
运行 `scripts/parse_case.py` 清点 `/input/case.json` 声明的全部材料
（存在性、字节数、可读性），再运行 `scripts/freeze_refset.py`
从本地参考图与响应文件中解析出参考记录，按标识符与规范化标题去重，
赋予稳定编号 `R0001…`，计算内容哈希 `refset_hash` 作为冻结凭证，
产出 `work/refset.json` 与 `work/refset.csv`（含来源文件与指针的
provenance）。此后一切覆盖率计算均引用该冻结集。

② 初始覆盖测量。
将基线检索得到的候选记录集（`retrieved`，可来自组织者留存的
Crossref／EuropePMC 响应文件或基线代理的交付物）交由
`scripts/match_coverage.py`，以“标识符精确匹配 + 规范化标题相似度
（difflib，阈值默认 0.90）”双轨匹配，产出 `work/coverage_initial.json`：
分母、覆盖数、覆盖率、Wilson 置信区间、逐条匹配明细
（方法、得分）与漏检清单。

③ 漏检归类。
读取 `coverage_initial.json` 的漏检清单，按可判别性分组：
有标题有标识符（可补检）、有标题无标识符（词项补检）、
标识符冲突（同一标识符指向不同标题，需人工裁决）、
记录异常（标题与标识符俱缺）。归类结果作为查询生成的输入。

④ 漏检驱动查询生成。
`scripts/supplement_engine.py` 对每条漏检记录抽取判别词项
（在参考集内按文档频率逆序选择低频词，而非同义词表），
按下述四类原型生成查询，且每条查询携带：
假设（针对哪类漏检）、`target_miss_ids`、`generated_from`
（记录指针 + 被引用词项原文）、来源、时间戳（审计模式下去时间戳以保证确定性）。

⑤ 补检执行与边际收益记账。
查询按原型分批次离线执行于本地材料；每批结束后用同一冻结参考集
重新匹配，核算该批边际收益并逐查询写入 `work/supplement_log.csv`：
`query_id, batch, archetype, hypothesis, target_miss_ids, generated_from,
quoted_terms, source, files_searched, candidates_returned,
newly_covered_ids, marginal_gain, verdict`。
`verdict` 取 `effective`（带来新增覆盖）、`marginal`（与命中相关但未新增）、
`zero`（零收益）。

⑥ 停止规则判定。
每批之后依次判定 STOP-1（连续两批边际收益为零）、
STOP-2（执行预算——查询数或秒数——耗尽并注明是哪一项）、
STOP-3（残余漏检全部具备探针证据的归因，说明继续查询为何无效）。
触发即停，判据写入 `work/supplement_state.json`。

⑦ 残余遗漏报告。
对每条残余漏检给出：`attributed_cause`
（`来源库未收录`／`记录异常`／`标识符冲突`／`需人工核查`）、
探针证据（标识符在哪些本地文件命中、标题词项命中计数、探针文件数）、
以及“需要什么条件才能检回”的具体说明（如“需访问未留存的出版商全文页”），
写入 `work/residual_misses.json`，并由 `render_report.py` 渲染为
人类可读报告；禁止“可能未收录”这类模糊归因。

⑧ 确定性复跑。
`scripts/audit_replay.py` 以固定顺序、固定参数、固定环境变量
端到端复跑 ①—⑥，比较两次运行的 `refset_hash`、覆盖集合、
补检停止规则与新增覆盖集合；任何不一致写入 `change_log` 并
以退出码 3 报告校验失败。

⑨ 抽检复核。
审计抽样协议：全部边界命中（得分落在边界带的相似度匹配）100% 复核；
干净命中按确定性规则抽样——按 `ref_id` 排序后每第 5 条抽取
（比例约 20%，规则与依据写入报告）。复核内容包括：
重匹配结论是否一致、命中证据是否能在至少一个本地源文件中复现。
一致性比率写入 `work/audit_report.json`，分歧进入 `change_log` 并触发重跑。

⑩ 交付。
`scripts/render_report.py` 汇总上述工件，生成
`/app/output/coverage_report.md`（含补检前后对照表、逐批边际收益表、
残余遗漏与复核摘要）与 `/app/output/result.json`
（含 `case_id`、任务 `output_contract` 的全部字段、
诚实状态、来源清单、不确定性说明与变更记录）。

## 边际收益公式与停止规则

设第 `b` 批补检执行前已覆盖集合为 `C_{b-1}`、执行后为 `C_b`，
该批查询数为 `q_b`，则：

```
marginal_coverage_gain(b) = |C_b − C_{b-1}| / q_b
```

其中 `C_b` 必须用同一冻结参考集重新匹配得到，不得沿用查询返回数。
单条查询级边际收益记账于 `supplement_log.csv` 的
`newly_covered_ids` 与 `marginal_gain` 列；
零收益查询如实记 `verdict=zero`，计入成本但不虚增收益。

停止规则（判定顺序固定，全部记录于 `supplement_state.json`）：

- STOP-1：连续两个补检批次的边际收益均为零。
- STOP-2：执行预算耗尽；必须注明耗尽的是查询数还是秒数。
- STOP-3：全部残余漏检均已归因，且每个归因附带探针证据
  （标识符命中文件清单、标题词项命中计数），
  并说明继续查询为何无法带来新增覆盖。

判定细节与必填日志字段见 `references/stop_rules.md`。

## 异常处置

- 材料缺失或不可解析：对应阶段置 `status=partial`，
  在 `result.json` 的 `limitations` 中逐条说明，绝不虚构内容；
  若连冻结参考集都无法构建，退出码 2。
- 网络不可用：本技能不发起网络请求，故无网络异常路径；
  若上游材料声称依赖远程抓取，标注为不可核验。
- 超时：补检引擎以 `--max-seconds` 预算自查，超时即触发 STOP-2。
- 重复记录：冻结参考集阶段按标识符与规范化标题去重，
  合并时保留全部 provenance。
- 撤稿记录：补检命中被标注撤稿的参考记录时，
  计入覆盖但在报告中单列说明，不作为补检收益宣传。
- 标识符冲突：同一 DOI 指向不同标题时，该条目不自动裁决，
  进入 `标识符冲突` 类并列入人工复核清单。
- 全文不可用：以本地响应文件与参考图中的题录字段为准，
  并在 `limitations` 中注明“未核全文”。

## result.json 契约

`/app/output/result.json` 至少包含：

- `case_id`：与 `case.json` 一致。
- `output_contract` 字段全集：逐字段复制任务约定值，
  无法取得的字段置 `null` 并在 `contract_fields_missing` 中列明。
- `status`：`ok`／`partial`／`error`，逐阶段状态见 `stage_status`。
- `sources`：实际读取的全部本地文件清单（含哈希或字节数）。
- `coverage`：`denominator`、`covered_before`、`covered_after`、
  `coverage_before`、`coverage_after`、`wilson_ci`（前后各一）。
- `supplement`：批次数、总查询数、逐批边际收益、触发的停止规则。
- `residual_misses`：残余漏检及其归因与检回条件。
- `audit`：确定性复跑结论与抽检一致性比率。
- `uncertainty`：置信区间、未核全文说明等。
- `change_log`：复核分歧与重跑记录。

## 失败与降级

| 情形 | 行为 | 退出码 |
| --- | --- | --- |
| 全部脚本正常、停止规则触发并完成复核 | 完整交付 | 0 |
| 部分材料缺失，但冻结参考集可构建 | 对应阶段 `partial`，如实记录 | 0 |
| 无法构建冻结参考集（无可用参考记录） | 诚实降级，说明缺什么 | 2 |
| 确定性复跑不一致／抽检发现不可解释分歧 | 写入 `change_log`，拒绝交付结论 | 3 |

## 最小调用示例

```bash
python3 scripts/parse_case.py --case /input/case.json --task /task.md --work /app/work
python3 scripts/freeze_refset.py --parsed /app/work/parsed_case.json --materials /input --work /app/work
python3 scripts/match_coverage.py --refset /app/work/refset.json --retrieved /app/work/retrieved.json --out /app/work/coverage_initial.json
python3 scripts/supplement_engine.py --refset /app/work/refset.json --coverage /app/work/coverage_initial.json --materials /input --work /app/work
python3 scripts/audit_replay.py --case /input/case.json --retrieved /app/work/retrieved.json --materials /input --work /app/work
python3 scripts/render_report.py --work /app/work --out-dir /app/output
```

各脚本均支持 `--help` 查看全部参数与默认值。
查询原型的构造规则与反例见 `references/query_generation_playbook.md`，
审计协议细节见 `references/audit_protocol.md`。
`examples/` 下的全部文件均为合成示例，仅用于演示工件格式。
