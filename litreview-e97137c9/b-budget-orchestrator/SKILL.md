---
name: contract-first-budget-orchestrator
description: 文献综述生成的"过程质量控制与资源调度"协议。当任务给出一批文献与明确 output_contract、要求在有限预算（64 次模型请求 / 900 秒 / 单次响应 ≤16384 token）内产出可复核综述时使用。核心机制：契约先行——动手之前先把 output_contract 逐字段解析为产出计划（contract_map.json），并立即写出 status=in_progress 的 partial result.json（全部契约字段先填 null，任何中断都留有可核对交付物）；预算编排——按文献数与相关度把 64 次请求分配到筛选/摘要/主题/证据/草稿各阶段，预留 6 次校验修复保底，按"研究问题关键词重叠得分+tier"为每篇文献裁定阅读深度（全文精读→章节精读→仅摘要的降级阶梯）；断点续跑——state.json 记录每阶段状态与产物路径，一致性校验脚本核对"标记完成的阶段产物真实存在、契约字段完备、change_log 覆盖所有阶段"。适用于文献规模与预算不匹配、运行可能中断、交付契约严格的综述任务；不负责来源取证（题录核验）与定量单位归一化。
---

# contract-first-budget-orchestrator：契约先行与预算编排的文献综述生成

## 1. 本 Skill 解决什么问题

综述任务最常见的失败不在"写"，而在**过程失控**：文献有 40 篇而预算只有 64 次请求，逐篇精读必然中途耗尽；运行在第 30 分钟中断，已完成的阶段与产物对不上账；最终 result.json 漏了 output_contract 的两个字段，或某字段被悄悄编造。本 Skill 的重心是**把过程本身纳入管控**：

1. **契约先行（contract_probe.py）**：任何模型调用之前，把 output_contract 逐字段映射为"来源产物 + null 策略"（contract_map.json），同时立即写出 `status=in_progress` 的 partial result.json——全部契约字段先填 null。null 是合法占位，**漏字段不允许**；此后每一分钟中断，交付目录里都有结构完整的可核对产物。同时从 task.md 抽出含"必须/须/不得"的硬性要求句写 requirements.md。
2. **预算编排（budget_ledger.py）**：把 64 次请求显式分配到各阶段——reserve（verify+repair）6 次保底、筛选 1 次、逐文档 digest 按深度分批（每批 ≤8 篇合并 1 次请求）、主题综合 3–8 次、草稿 2–4 次；按 tier 与"研究问题关键词 token 重叠得分"为每篇文献裁定阅读深度（full/sections/abstract/skip）；预算不足时按降级阶梯收缩（见 rules/degradation_ladder.md），而不是跑到哪里算哪里。
3. **断点续跑与一致性校验（budget_ledger.py status / consistency_check.py）**：state.json 是账本——每阶段 pending/completed、产物路径、实耗请求数；`status` 子命令随时打印剩余预算与已完成阶段；consistency_check.py 核对"标记完成的阶段产物真实存在、result.json 含契约全部字段、change_log 覆盖所有阶段"，输出 consistency_report.json，未通过以退出码 1 报警。

## 2. 适用条件与不适用范围

适用：文献数量与预算可能不匹配、运行时间较长存在中断风险、交付契约（output_contract）严格、需要可审计过程记录的综述任务。不适用：来源取证与撤稿检测（见 bundle A）、数值证据的单位归一化与冲突检测、渲染层审计。本 Skill 复用 SPEC 的解析/锚点/摘录规范，但不重复实现身份核验。

## 3. 输入契约（防御式解析）

Harbor 运行契约：输入 `/input/case.json` 与 `/input/task.md`；材料由 case 指定或在 `/input/` 下发现；工作 `/app/work`；交付 `/app/output/`。**不得假设字段名**：

1. `case_id`：依次 `case_id`/`caseId`/`id`；缺失用文件名并记入 uncertainties。
2. 研究问题：递归查 `research_question`/`question`/`topic`/`title`/`objective`/`rq`；再读 task.md，task.md 具体要求优先。研究问题同时是阅读深度排序的关键词来源。
3. 文献清单：递归查 `documents`/`papers`/`references`/`files`/`literature`/`corpus`/`materials`；元素可为路径字符串或含 `path`/`file`/`pdf`/`url`/`title` 的字典；都不命中则按 `*.pdf → *.txt → *.md → *.html` 扫描 `/input/`。URL 无本地文件记 `metadata_only`，不伪造全文，阅读深度记 skip。
4. `output_contract`：递归查 `output_contract`/`contract`/`output_fields`/`required_fields`；contract_probe 逐字段生成产出计划，build_result 逐字段镜像，缺内容填 null 并说明，**不得漏字段**。

零文献或全部解析失败：照常写出 `status="blocked"` 的 result.json 与说明，不得空跑。

## 4. 运行方式

```bash
S=<skills 目录>/contract-first-budget-orchestrator/scripts
python3 $S/run_case.py init     --case /input/case.json --task /input/task.md \
                                --input-dir /input --work /app/work --out /app/output --budget 64
# …模型阶段（第 5 节阶段 1–5），每完成一个阶段登记一次：
python3 $S/budget_ledger.py mark --work /app/work --phase digests --requests 4
python3 $S/budget_ledger.py status --work /app/work      # 随时查看剩余预算/已完成阶段
python3 $S/run_case.py check    --work /app/work --out /app/output
python3 $S/run_case.py finalize --work /app/work --out /app/output
```

`init` 在 10 秒内完成：ingest（解析+抽取+分级+近重复分组）→ contract_probe（契约映射 + partial result.json + requirements.md）→ budget_ledger plan（run_plan.json + state.json）。中断恢复：`budget_ledger.py status` 看账本，`check` 找"标记完成但产物缺失"的阶段，从未完成的阶段继续，最后 `finalize`。

## 5. 工作流程（预算内完成：64 次请求 / 900 秒 / 16k token）

### 阶段 0：解析、契约探针与预算编排（脚本，0 次模型请求）

`run_case.py init` 完成后先读三份文件再动手：`work/contract_map.json`（每个契约字段由什么产物填充、缺失时如何 null）、`work/run_plan.json`（每篇文献的阅读深度与批次提示、各阶段请求分配、已触发的降级项）、`work/requirements.md`（task.md 硬性要求）。**run_plan 是执行合同：深度与批次数不得擅自突破**；认为分配不合理时，重跑 `budget_ledger.py plan` 并在 change_log 说明，不得静默偏离。

### 阶段 1：筛选（模型 1 次）

写 `work/screening_log.json`：纳入/排除标准绑定研究问题；metadata_only/failed/duplicate_of 文献不进阅读计划但必须在筛选记录中说明。完成后 `budget_ledger.py mark --phase screening --requests 1`。

### 阶段 2：逐文档 digest（模型按 run_plan 分批）

按 run_plan 的 reading_plan 执行：full 档每批 ≤2 篇、sections 档每批 ≤4 篇、abstract 档每批 ≤8 篇，每批合并 1 次请求。full 档按 `pages/<doc_id>.jsonl` 锚点通读；sections 档只读与主题最相关章节；abstract 档只读摘要页，证据强度 ≤ suggestive。每批写 `work/digests/<doc_id>.md`。完成后 mark。

### 阶段 3：主题综合与证据表（模型 3–8 次 + 2 次）

主题从 digest 簇归纳（禁止套固定模板），写 `work/themes.json`；证据写 `work/evidence_ledger.jsonl`，每行
`{"evidence_id","doc_id","locator":"p<页>.¶<段>","verbatim_quote","supports","theme","strength": established|suggestive|contested}`，
摘录逐字（仅允许归一化空白/断词），冲突并列 contested。分别 mark。

### 阶段 4：草稿（模型 2–4 次）

按 `templates/review_draft.md` 写 `work/review_draft.md`：中文书面语、无第一人称、实质句尾标 `[E#]`、推断句前缀 `[推断]`、证据未覆盖处 `[证据缺口]`。完成后 mark。

### 阶段 5：校验与修复（reserve 6 次内）

`run_case.py check` 生成 consistency_report.json：阶段-产物一致性、契约字段完备性、change_log 覆盖。发现问题用 reserve 预算修复（补产物或改 state），修复后再 check；两轮仍不过则将问题写入 uncertainties 并以 partial 交付。最后 `run_case.py finalize` 组装 result.json（status ∈ completed/partial/blocked）。

## 6. 异常处置（必须写进 uncertainties）

- 预算不足触发降级：每条降级决策（砍润色、砍主题细分、深度降档、尾部 skip）自动记入 run_plan.degradations 并进入 uncertainties。
- 仅摘要：abstract 深度，strength ≤ suggestive，草稿标注 abstract_only。
- 元数据不全：以文件名标识，不猜测补齐。
- 近重复：仅代表篇分配阅读预算，其余 skip 并注明 duplicate_of。
- 结论冲突：并列 contested，不调和、不取平均。
- 中断后产物与账本不符：consistency_check 判不通过，虚报阶段改回 pending 重做，不得带伤 finalize。
- 语料为空/全部解析失败：`status="blocked"`，照常交付。

## 7. 默认输出结构（output_contract 缺失时）

```json
{"case_id":"…","status":"completed|partial|blocked",
 "research_product":{"question":"…","themes":[…],"draft_file":"review_draft.md","bottom_line":"…"},
 "evidence_matrix":[{"evidence_id":"E1","doc_id":"D1","locator":"p3.¶2","verbatim_quote":"…","supports":"…","theme":"…","strength":"…"}],
 "screening_log":{…},"run_plan":{…},"consistency_report":{…},
 "budget_summary":{"total":64,"used":…,"remaining":…},
 "uncertainties":[…],
 "sources":[{"doc_id":"D1","ref":"…","sha256":"…","tier":"fulltext","reading_depth":"full","metadata":{}}],
 "change_log":[…]}
```

## 8. 文件清单

- `scripts/run_case.py`：init/check/finalize 编排器。
- `scripts/ingest.py`：防御式解析、材料发现、抽取、分级、近重复分组。
- `scripts/contract_probe.py`：契约字段产出计划、partial result.json、硬性要求提取（签名脚本）。
- `scripts/budget_ledger.py`：预算分配、阅读深度裁定、state.json 账本（plan/mark/status，签名脚本）。
- `scripts/consistency_check.py`：阶段-产物一致性、契约完备性、change_log 覆盖校验（签名脚本）。
- `scripts/build_result.py`：result.json 组装与 output_contract 镜像。
- `rules/degradation_ladder.md`：降级阶梯与中断恢复规则。
- `rules/contract_mapping.md`：契约字段映射与 null 策略。
- `templates/run_plan.md`、`templates/review_draft.md`。
- `examples/`：合成示例（`make_example.py` 端到端生成并运行，含中断恢复演示，产物标注 simulated）。
