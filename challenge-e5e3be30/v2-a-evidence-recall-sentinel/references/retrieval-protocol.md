# 高召回检索与无证据审计协议

## 1. 唯一目标

减少证据漏检，并让 `insufficient_evidence` 可被复核。检索命中只进入候选集，绝不等同于 `supported`。主题相关、单页相似或数值出现均不能代替 Agent 的语义裁决；未报告不能写成 `contradicted`。若候选彼此冲突，审查记录必须保留双方 candidate ID 与冲突说明。

## 2. 先写 partial，再检索

1. 读取 `case.json`、`task.md`、`claims-to-verify.json`。claims 始终是问题，不是已经成立的事实。
2. 从 `case.json.output_contract` 动态生成 `/app/output/result.json` 骨架，立即落盘，`status=partial`。
3. 读取 Skill 根目录的 `environment/resources.yaml`（若存在），仅解析扁平的 `max_requests`、`request_budget`、`max_seconds`、`time_budget_seconds`，硬上限为 64 / 900 秒。
4. 文本按实际 form-feed 分页；PDF 只调用已有 `pdftotext -layout -enc UTF-8`。转换器缺失、PDF 损坏或 UTF-8 读取失败都诚实报错并保持 partial，不创建伪页面。

## 3. 两阶段查询变体计划

每个问题在 `/work/retrieval-plan.json` 中有独立 `query_families`。第一阶段通常从实体词和原始措辞起步；第二阶段必须针对第一阶段漏检风险扩展，而不是重复改写同一句话。

- **entity**：作者、药物、疾病、队列、干预、对照、缩写、连字符和空格变体。
- **numeric**：数值、上下限、单位、百分比/小数、时间点、样本量；同时尝试 `18%`、`18.0%` 等表达。
- **synonym**：临床术语/通俗说法、学名/缩写、结局指标替代表述。挑选会改变召回的词，不做无意义同义句替换。
- **figure_table**：`Table`、`Figure`、`caption`、`appendix`、`supplement`、`Kaplan-Meier`、坐标轴/行列名等。
- **restriction**：人群、时间、剂量、亚组、终点、统计口径等限制条件。
- 每个 query variant 可选择 `exact_phrase`、`token_overlap`、`numeric_match` 通道。第一阶段可故意较窄，但生成无证据证书前必须补足语义扩展族。

若 claims 未提供查询计划，引擎只创建明确标记为不足的 bootstrap entity 族。Agent 应在审查前扩展输入计划；此时不能签发无证据证书。

### 停止条件

只有在下列情况同时成立时才可停止补查：

1. 计划族和变体全部执行；没有静默省略。
2. 至少两个查询族、至少三种 kind；有 synonym 族，且有 entity 或 restriction 族；数值问题另有 numeric 族。上述是脚本最低门槛，不是领域充分性的替代品。
3. 每个变体扫描全部已成功抽取页面，包括正文、表图说明和所提供补充文档。
4. 所有候选均为逐条 `reviewed` 或 `unreviewed`；要形成 complete 结果，未审候选必须为零。若暂留 unreviewed，则每条必须有解释，整体保持 partial。
5. 主题不符候选有具体排除理由；不能仅写“irrelevant”。

## 4. 多通道融合

- exact phrase 保留原始措辞命中。
- token overlap 容许词序和少量措辞变化，低覆盖单词命中不得进入。
- numeric match 规范化阿拉伯数字，让 `18%` 与 `18.0%` 可相遇。
- 每个查询族内部先按通道分别排序，再用 reciprocal-rank fusion；同一 claim/page 跨族累加 fusion 分数。
- 不按 top-k 截断；任何通道命中的所有页面均保留为候选。排序只用于审查，不用于删除召回尾部。
- `origin_families` 和 `matched_variants` 记录每条候选由哪些族找回。`search-audit.jsonl` 记录每个变体的扫描页和各通道命中页，并固定 `semantic_verdict=null`。

## 5. Agent 语义审查

Agent 读取 `pages.jsonl` 的全页上下文和 `candidates.jsonl`，独立写 `review.json`。对每个候选给出 reviewed/unreviewed、relevant、排除理由；对每个问题给出四级 verdict、rationale、evidence candidate IDs、conflicts 与 uncertainty。

- supported：已审候选在语义上回答该问题。
- partially_supported：只有所问范围的一部分得到证据。
- contradicted：有语义上直接冲突的证据；不是“没有搜到”。
- insufficient_evidence：没有足够证据，并且需要证书。
- 冲突候选不能因采用某一方而从审查文件删除。`conflicts` 至少保留两个不同 candidate IDs，并描述双方。

## 6. 无证据证书

每个 insufficient 结果内嵌 `no_evidence_certificate`，包含：

- 所有查询族 kind、每个 variant 的 ID、原始查询与通道，以及未满足的充分性原因；
- 预期全页清单、每个变体实际扫描页、文档来源；
- planned variants 是否全执行；
- 候选数、reviewed/unreviewed 状态、每个非采用候选的排除理由；
- `valid` / `status=issued` 或 `not_issued`。

`insufficient_recall_audit_certificate_not_issued` 意味着只能说“当前检索审计不足”，不能把 insufficient 升级为“已证明无证据”。`finalize` 对缺族、扫页不全、未解释未审/排除候选或缺证书写 partial 并退出 1。

## 7. 契约与交付

最终输出必须保留 `case_id`、`status`、`sources`、`uncertainty`、`change_records`，以及 output_contract 声明的全部字段。契约可为字段列表、字段/type 映射、`properties` + `required`、`fields`、`result_fields` 或 `output_fields`。未知业务字段先按类型生成骨架，Agent 可用 `review.json.result_overrides` 填值。

最终另有 `/work/pages.jsonl`、`retrieval-plan.json`、`search-audit.jsonl`、`candidates.jsonl` 和 `review.json`。脚本只生成数据和文本 SVG；报告呈现不是本 Skill 的目标。
