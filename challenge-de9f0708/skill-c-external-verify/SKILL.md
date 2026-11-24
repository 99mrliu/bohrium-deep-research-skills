---
name: skill-c-external-verify
description: 学术规范审查中需要核验参考文献"是否真实存在、元数据是否一致"时使用。对论文做参考文献抽取与本地 lint，再以严格预算（默认 ≤12 次网络请求）对 Crossref/DOI 做真实检索并逐字段比对；两信号规则才可判疑似捏造；断网时联网项全部优雅降级为"待复核"，本地可判项照常出结论。适用于引用真实性、元数据一致性、张冠李戴错引、著录规范等审查面。
---

# skill-c-external-verify：外部事实核验（上游数据真实性）

## 1. 用途与新增价值

被引文献"是否真实存在、元数据是否一致"**不靠模型印象**，而靠脚本对
Crossref/DOI 的真实检索记录逐字段比对。新增价值：
- 比对结果只写"检索到的真实记录"（`retrieved_records` + `query_log` 可审计）；
- 严格预算纪律：全部网络请求共用 `--max-queries`（默认 12）计数器；
- 两信号规则：`fabrication_suspected` 仅在"检索无结果 + DOI 不可解析"齐备时给出
  （仍待人工终裁）；**绝不把"没搜到"直接判为"文献不存在"**；
- 断网/`--offline` 时联网项全部 `pending_review` 并如实记录原因，本地可判项照常出结论。

## 2. 适用条件与不适用情况

适用：材料为论文/综述（含参考文献表），审查面涉及引用真实性、元数据一致性、
错引、著录规范。文本可由 pdftotext 预抽为 .txt。
不适用：无参考文献表的材料；需要全文事实核查（超出文献核验范围）；
对抓取结果直接当结论使用（lint 输出全部是候选，须复核）。

## 3. 运行时契约与路径

- 输入：`/input/case.json`、`/input/task.md`、论文材料（PDF 先 `pdftotext` 抽为文本）。
- 工作目录：`/app/work`（中间产物 refs.json / lint.json / crossref.json）。
- 交付：`/app/output/result.json`，必须含 `case_id` 与 case.json `output_contract`
  要求的全部字段，诚实标注 `status`/`sources`/`uncertainty`/`change_log`。
- 脚本路径：`/skills/weekly-skill/scripts/…`，规程查阅
  `/skills/weekly-skill/references/verification_protocol.md` 与 `severity_rubric.md`。

## 4. 工作流（编号步骤，命令可直接复制）

0. 读 `/input/case.json` 与 `task.md`，列出**全部审查面**；把材料 PDF 抽成文本：
   `pdftotext -layout /input/paper.pdf /app/work/paper.txt`（无 pdftotext 时用可用工具）。
1. **先落保底 partial**：按 output_contract 写一份 status=partial 的 result.json 到
   `/app/output/result.json`（findings 空、not_reviewed 列全部审查面）。
2. 抽取参考文献与引文语境：
   `python3 /skills/weekly-skill/scripts/extract_refs.py --input /app/work/paper.txt --output /app/work/refs.json`
3. 本地初筛（不耗预算）：
   `python3 /skills/weekly-skill/scripts/lint_refs.py --input /app/work/refs.json --output /app/work/lint.json`
4. 外部核验（在线；预算 ≤12）：
   `python3 /skills/weekly-skill/scripts/crossref_check.py --input /app/work/refs.json --lint /app/work/lint.json --output /app/work/crossref.json --max-queries 12`
   断网或需演示降级时加 `--offline`。
5. 逐条处置：match → 销项；mismatch → 按 severity_rubric 定级，证据引
   `retrieved_records` 原文；not_found 单信号 → `待复核`；两信号 →
   `fabrication_suspected / critical / 待人工终裁`。
6. 完成案例声明的**全部审查面**（lint 未覆盖的面由 Agent 人工/模型完成，
   每条 finding 指回原文逐字摘录）；无法覆盖的面写入 `not_reviewed` 并说明原因。
7. 汇总更新 `/app/output/result.json`（见 §5），把 refs/lint/crossref 三份 JSON
   一并拷入 `/app/output/` 作为可复跑证据。

## 5. 输出契约（result.json）

必填：`case_id`、`status`(complete/partial/blocked)、`findings`、`not_reviewed`、
`uncertainty`、`sources`、`change_log`（以 case.json `output_contract` 为准，缺键按空处理）。
每条 finding：`id`、`type`（fabrication_suspected/metadata_mismatch/
claim_citation_mismatch/duplicate_reference/missing_field/format_inconsistency/
suggestion）、`severity`(critical/major/minor/info)、`category`(fact_error/
insufficient_evidence/norm_issue/suggestion)、`location`{file,page,section,quote 逐字}、
`evidence`（本地规则名 / 外部来源 URL + 检索到的原文）、`suggestion`、
`verdict_status`(确认/待复核+理由)。

## 6. 失败模式与止损表

| 失败模式 | 信号 | 止损动作 |
|---|---|---|
| 断网/超时 | query_log 出现 network error | 脚本自动降级 pending_review；result.json 标 partial，联网面入 not_reviewed |
| 预算耗尽 | budget.remaining=0 | 剩余条目 pending_review；不得为省预算跳过 P0 条目 |
| 参考文献表未识别 | refs.json ref_count=0 | 人工定位文献表或按整文扫描 citations；notes 已说明，不得硬编条目 |
| 抽取字段错位 | lint missing_field 大面积出现 | 判为抽取失败，对照原文手工著录后再跑 crossref_check |
| "没搜到"想判捏造 | 仅信号 A | 禁止。按两信号规则只能 pending_review/待复核 |
| 作者拼写差异误报 | authors mismatch 但姓氏集合重叠 | 按比对口径归一化后重判，不构成 mismatch |

## 7. 降级策略（honest partial）

任何时候预算/时间/网络不足：保留已完成的本地结论与已检索记录，
未完成项逐一列入 `not_reviewed`（含原因与复核路径），status=partial 并在
`partial_reason`/`uncertainty` 中说明局限。断网演示见
`/skills/weekly-skill/examples/run_example.sh`（离线跑通全流水线）。

## 8. 预算意识

- 顺序永远是：先存 partial 保底 → 本地免费检查（extract/lint）→ 联网花预算
  （crossref）→ 迭代补全。
- 网络请求总数 ≤ `--max-queries`（默认 12），优先级排序见
  references/verification_protocol.md §1；模型请求预算留给需要判读的环节
  （claim_citation_mismatch 终裁、剩余审查面），机械比对全部交给脚本。
