---
name: screening-decision-ledger
description: >
  筛选判定账本——多数据库联合检索场景的纳入/排除判定层。当任务要求对来自 Crossref、
  EuropePMC、出版方等离线响应做题录级筛选，且要求"每条 keep/drop 判定可审计、
  排序/筛选依据可追溯、遗漏说明如实、PRISMA 风格流量计数由判定记录重算而非断言"
  时使用本技能。核心纪律：资格标准只能编译自 task.md（每条标准带原文引用
  source_quote，模型编译的标准整体标记 derived_needs_confirmation 并需人工二次
  确认登记）；每条 include/exclude 判定必须引用标准 id 与记录标题/摘要内的逐字
  证据片段（脚本做子串核验，伪造引用一律拒绝，退出 3），证据不足只能判 borderline
  并标 insufficient_evidence；拿不准的记录进 borderline_queue 由模型一次性批量
  裁定；机器可判标准（发表年份范围、文献类型排除）由脚本预判落账。所有 PRISMA
  风格计数（identified → deduplicated → screened → excluded-with-reasons →
  included）都是对 decision_ledger.jsonl 行的实际计数并带守恒校验。边界：不联网、
  不臆造判定与标准、不做全文质量评价、不做模糊去重（内嵌最小确定性去重仅为喂
  流量计数）、不做状态卫生与召回率统计估计。
---

# screening-decision-ledger：筛选判定账本

## 适用场景与边界

适用：

- 多数据库联合检索（离线材料即响应）后的**题录级资格筛选**：把 task.md 里的
  纳入/排除标准编译成显式标准表，对每条记录给出引用标准 id + 记录内证据片段的
  include / exclude / borderline 判定。
- 评审/交付要求**判定可审计**：任何一条 keep/drop 都能回答"依据哪条标准、
  证据原文是什么、谁判的（脚本还是模型）、处在哪个阶段"。
- 交付要求 **PRISMA 风格流量计数**且计数必须由判定记录**重算**（守恒校验），
  而不是在报告里断言数字；要求"遗漏说明"（未判定、待决边界、证据不足）。

**边界（严格遵守）**：

- **不联网**：本地材料即全部响应；不补全元数据、不拉取全文。
- **不臆造判定**：每条 include/exclude 必须引用 criteria id 与记录内
  **逐字**证据片段；无法给出逐字证据的只能判 borderline 并标
  `insufficient_evidence`。脚本对每条引用做子串核验，伪造引用 → 拒绝并退出 3。
- **标准只能来自 task.md**：每条标准必须带 `source_quote`（task.md 原文）；
  由模型编译的标准整体标记 `derived_needs_confirmation`，需人工二次确认登记，
  确认前 status 一律 partial。
- **不做全文质量评价**：不产出质量评分、风险偏倚评级；output_contract 中此类
  字段置 null 并列入 unresolved。
- **不做**复杂去重（内嵌最小确定性去重仅用于喂流量计数）、不做查询规划、
  不做导入状态卫生、不做统计召回估计。

## 运行环境

- Python 3 标准库，无第三方依赖；`python3 scripts/screening_ledger.py --help`
  退出 0。
- 脚本定位：优先 `${SKILL:-/skills/weekly-skill}/scripts/screening_ledger.py`；
  找不到时回退 `find / -maxdepth 6 -name screening_ledger.py 2>/dev/null`。
- 退出码：`0` 成功（status=ok）；`2` 诚实降级（status=partial，骨架/部分产物
  保留）；`3` 输入无效（status=error；validate-judgments 拒绝非法判定也用 3）。
  `selfcheck` 例外：通过 0 / 失败 1。
- 确定性：材料扫描排序、记录 id 按扫描序赋号、JSON 键排序、产物不含时间戳与
  随机量——同一输入字节级可复现，幂等，可原地重跑。

## 运行契约

- 输入：`/input/case.json`（含 `case_id`、`materials`、`output_contract`）、
  `/input/task.md`、`/input/materials/*`。
- 工作区：`/app/work`（全部中间产物）；交付：`/app/output/result.json`。
- `result.json` 必含：`case_id`、`skill_name`、`status`、**全部**
  `output_contract` 字段（无法填充 → `null` 并列入
  `unresolved_contract_fields`，绝不编造）、`sources`（含 sha256）、
  `uncertainty`（派生标准待确认 / insufficient_evidence / borderline 待决 /
  未判定记录）、`change_records`（含标准确认要求）、`counts`、`checks`。
- 诚实 partial：存在待决边界、未判定记录、派生标准未确认、材料被隔离或契约
  字段无法填充时，`status="partial"`、退出 2，原因显式列入 `uncertainty`。

## 工作流程

0. **读 case + task（脚本）**：`parse` 先校验 case.json（缺失/无 case_id →
   退出 3）；`run-all` 在读任何输入**之前**先写 `result.json` 骨架
   （status=partial）。
1. **嗅探+规范化（脚本）**：按结构嗅探 crossref（`message.items`）/
   europepmc（`resultList.result`）/ publisher（JSON 数组、JSONL、CSV）/
   reference_graph / import_state / unknown（隔离，绝不强解）；规范化 DOI、
   标题（NFC+去 HTML+折叠空白）、年份、第一作者姓氏；写 `normalized.jsonl`。
   内嵌**最小去重**（规范化 DOI 精确，否则规范化标题+年份+第一作者姓氏全同；
   保留每条记录的 sources 列表）仅用于喂流量计数，写 `dedup_summary.json`。
2. **骨架先行（脚本）**：`result.json` 骨架已在第 0 步写入 `/app/output/`。
3. **编译资格标准（模型职责，一次批量请求）**：通读 task.md，把纳入/排除
   标准编译为 `/app/work/criteria.json`：每条
   `{id, kind: inclusion|exclusion, definition, source_quote}`，
   `source_quote` 必须是 task.md 的原文片段；机器可判的排除标准附 `machine`
   块（`{"type":"year_range","min":..,"max":..}` 或
   `{"type":"document_type","exclude_types":[..]}`）；task.md 无明确标准时
   整体标 `"derived_needs_confirmation": true`。规则详见
   `references/criteria-playbook.md`。
4. **机器预判（脚本）**：`prescreen` 应用 machine 块标准（发表年份范围、
   文献类型排除）；命中的记录落 exclude 判定（criterion id + 字段值证据，
   decided_by=script），其余保持 pending。字段缺失不自动排除。
5. **模型批量判定（模型职责，一次批量）**：对 `prescreen_pending.json` 中的
   记录一次性产出 `/app/work/judgments.json`，每条
   `{record_id, decision: include|exclude|borderline, criterion_ids,
   evidence_quote, rank?, rationale?}`。`evidence_quote` 必须是该记录
   标题/摘要的逐字片段；include/exclude 必须引用 ≥1 标准 id；拿不准判
   borderline；记录缺摘要时判定降级为 title-only（标 `basis`）；完全无据可判
   时判 borderline 并标 `evidence_status: "insufficient_evidence"`。
6. **校验+落账（脚本）**：`validate-judgments` 严格校验（schema、decision
   枚举、criterion id 必须存在于 criteria.json、引用必须是该记录文本的逐字
   子串——伪造引用详细报错并退出 3）；`ledger` 合并 prescreen + 判定 + 边界
   裁定 → `decision_ledger.jsonl`（每记录一行：record_id, stage, decision,
   criterion_ids, evidence, decided_by, 逻辑序号 seq，无时间戳）；未决边界
   进 `borderline_queue.json`。
7. **边界裁定（模型职责，一次批量）**：阅读 `borderline_queue.json` 的 pending
   记录，一次性产出 `borderline_decisions.json`（每条
   `{record_id, decision: include|exclude, criterion_ids, evidence_quote,
   rationale}`），再重跑 `ledger`（或带 `--borderline-decisions` 的
   `run-all`）。
8. **重算与交付（脚本）**：`flow` 由账本行逐条计数出 `prisma_flow.json`
   （identified per source、duplicates_removed、records_screened、excluded
   按标准计数、included、borderline_pending）并断言守恒（identified − dedup
   == screened 等，见 `references/prisma-counting.md`），渲染
   `prisma_flow.md`；`report` 生成 `screening_report.md`（标准表含 task.md
   原文引用、纳入清单含理由、排除原因矩阵、边界裁定、局限）；`finalize`
   产出 `candidate_set.json`（模型 rank 否则稳定序）与最终 `result.json`。
9. **自查（脚本）**：`selfcheck` 校验契约键、守恒、每条 exclude ≥1 标准、
   每条引用逐字核验、result.json 计数与账本重算一致；退出 0/1。

一键全链路：

```bash
python3 ${SKILL:-/skills/weekly-skill}/scripts/screening_ledger.py run-all \
  --input /input --work /app/work --output /app/output \
  --criteria /app/work/criteria.json \
  --judgments /app/work/judgments.json \
  --borderline-decisions /app/work/borderline_decisions.json
# 缺 --criteria → 保留骨架并退出 2；判定非法 → 退出 3
```

## 输出合同映射表

| 产物 | 位置 | 内容 |
|---|---|---|
| `result.json` | `/app/output/` | case_id + 全部 output_contract 字段（或 null+unresolved）+ status/sources/uncertainty/change_records/counts/checks |
| `decision_ledger.jsonl` | `/app/work/` | 每记录一行判定：stage/decision/criterion_ids/evidence/decided_by/seq |
| `prisma_flow.json` / `prisma_flow.md` | `/app/work/` | 由账本重算的流量计数 + 守恒校验 + 文本流程图 |
| `screening_report.md` | `/app/work/` | 标准表（含 task.md 原文引用）、纳入理由、排除矩阵、边界裁定、局限 |
| `candidate_set.json` | `/app/work/` | 纳入记录，含 rank + rationale + 逐字证据 |
| `borderline_queue.json` | `/app/work/` | 待决边界 / 未判定 / 已裁定清单 |
| `criteria.json` | `/app/work/`（模型写） | 编译自 task.md 的资格标准 |
| `judgments.json` / `borderline_decisions.json` | `/app/work/`（模型写） | 批量判定 / 边界裁定 |
| `normalized.jsonl` / `dedup_summary.json` | `/app/work/` | 规范化记录与最小去重摘要（喂流量计数） |

## 异常处理表

| 情形 | 行为 |
|---|---|
| case.json 缺失 / 无 case_id / JSON 非法 | 退出 3 |
| task.md 无明确标准 | criteria 标 `derived_needs_confirmation`，finalize 如实 partial（退出 2）并在 uncertainty 与 change_records 中登记确认要求 |
| 缺 `--criteria`（run-all） | 保留 result.json 骨架，退出 2 |
| 判定引用非逐字 / criterion id 未知 / decision 非法 / include/exclude 无标准 id | validate-judgments 详细报错，退出 3 |
| 记录缺摘要 | 判定降级 title-only（judgment 标 `basis`），报告与 uncertainty 中声明 |
| 记录无任何可引用证据 | 只能判 borderline + `evidence_status: insufficient_evidence`；include/exclude 用 insufficient_evidence 会被拒绝 |
| 材料形状无法识别 / 文件缺失 | 隔离（quarantined），不强行解析；finalize partial |
| 存在待决边界或未判定记录 | status=partial（退出 2），列入 uncertainty 与 borderline_queue |
| 守恒校验失败 | status=error，退出 3 |
| 顶层未捕获异常 | 兜底打印错误并退出 3，绝不裸栈 |

## 合成最小示例

`examples/synthetic-input/` 为**合成教学数据**（虚构肽 NX-3、伪造 DOI
`10.99977/...` 与 PMID `391xxxxx`、虚构作者与期刊）：14 条原始记录
（crossref 6 / europepmc 5 / publisher 3）去重后 12 条——5 条明确纳入、
4 条按不同标准明确排除（错误人群 I2、错误年份 E1、错误对照 I3、错误文献
类型 E2）、3 条边界（年龄下限 16 岁、交替分配、潜伏期仅次要结局）经裁定后
2 排除 1 纳入、2 对跨源重复（DOI 精确一对、标题+年份+第一作者一对）。
`synthetic-input/` 同时给出模型步骤的手工产物 `criteria.json` /
`judgments.json` / `borderline_decisions.json`；`examples/synthetic-output/`
为**实际运行**产物（含负数测试记录见 `run-record.md`）。

## 诚实声明

- 计数零断言：prisma_flow 的每个数字都是对 `decision_ledger.jsonl` 行（与
  `dedup_summary.json` 去重组）的实际计数，selfcheck 会重算核对。
- 标准与判定都可能出错：模型编译的标准需人工确认登记；判定证据只核验
  "逐字存在于题录"，不核验"解释是否正确"——这正是 borderline 队列存在的
  意义。
- 去重是最小确定性规则，可能漏掉变体重复（在报告局限中声明）；本技能不承诺
  召回率完整性。
