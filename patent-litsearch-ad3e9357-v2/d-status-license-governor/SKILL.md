---
name: legal-status-license-governor
description: 在专利法律状态核验与多来源技术文献检索任务中强制执行登记优先的法律状态核验协议（含查询日期与滞后声明、状态冲突双保留与登记级优先披露、unknown 作为一等公民的诚实声明），并对全部数据源实施绿黄红三级授权分级与能力降级方案，以措辞守门器拦截未核验的确定性状态表述与越权的自由实施/侵权结论，确保交付物在来源纪律、许可边界与结论诚实性上均可审计。
---

# legal-status-license-governor（法律状态与许可治理）

## 用途与适用条件

本技能是专利与技术文献检索任务中的**合规与核验治理层**，适用于：

- 案例要求核验一件或多件专利的**当前法律状态**（授权、届满、撤回、驳回、 pending、未知）；
- 案例材料来自**多个异质来源**（官方登记簿、官方公报、聚合检索页、转载页、商业付费库），需要判定每个来源能支撑什么、能展示什么；
- 需要在**预算受限**的评测环境中先交付诚实的 partial 骨架，再逐步改进；
- 需要对结论措辞做**交付前合规闸**（未核验不得断言、不作 FTO/侵权结论）。

不适用：本技能不做号码解析、检索式构造、引文逐字对账或复盘打包——那些由其他 bundle 负责；但**任何**案例的交付物在离场前都必须过本技能的 license 分级与措辞守门两道闸（见案例路由表）。

## 运行时契约

- 评测方将本 Skill 安装于 `/skills/weekly-skill`，用官方 DeepSeek Harness 跑 3 个固定隐藏案例。
- 运行时输入：`/input/case.json` + `/input/task.md` + 材料文件（专利记录、USPTO 传真 PDF、对比论文等）。**必须读取真实文件内容，严禁凭文件名臆断内容。**
- 所给材料通常**无法**支撑对当前官方法律状态的核验——此时本技能的核心纪律是**如实声明 unknown**，而不是编造或从聚合页推断。
- 工作目录 `/app/work`；交付 `/app/output/result.json`，字段镜像 `case.json` 中 `output_contract` 的**全部**字段，至少包含 `case_id`、诚实的 `status`（`ok`/`partial`/`failed`）、`sources`、`uncertainty`、`change_records`。
- 预算 64 次请求 / 900 秒：**先用 `scaffold_result.py` 交付诚实 partial 骨架**，再在剩余预算内逐字段填充改进。
- 绝不把聚合/转载页当作登记证据引用；绝不抓取登录墙商业数据库；绝不展示受限来源的原文。
- 仅使用 python3 标准库；脚本退出码：`0`=通过，`1`=治理违规，`2`=用法/输入错误。

## 调用方式（有序流水线）

按以下顺序执行（命令中的路径以 `/app/work` 为工作目录；示例见 `examples/example_walkthrough.md`）：

1. **骨架先行**
   `python3 scripts/scaffold_result.py --case /input/case.json --out /app/output`
   生成镜像 output_contract 全部字段的 `result.json`（默认 `status=partial`）。
2. **登记/分级来源**：阅读真实材料，将每个来源登记进 `sources.json`（tier + license 字段），然后
   `python3 scripts/license_tiers.py classify --sources sources.json --out license_report.json`
   `python3 scripts/license_tiers.py plan --sources sources.json --out degradation_plan.json`
3. **建立状态台账**：对每件涉案专利写一行台账（`patent_ref, asserted_status, status_effective_date, source_id, query_date, note`）；未经登记级来源核验的一律 `asserted_status=unknown`。
4. **校验台账**
   `python3 scripts/status_ledger.py validate --ledger status.jsonl --sources sources.json`
   退出码非 0 时必须先修复（或改为诚实的 `unknown` 声明）再继续。
5. **措辞守门**：起草结论后
   `python3 scripts/wording_guard.py --conclusions conclusions.md --ledger status.jsonl --sources sources.json --out wording_check.json`
6. **填充结果**：把 `license_report`、`degradation_plan`、台账头条状态、冲突披露块、措辞报告合并进骨架，
   `python3 scripts/scaffold_result.py --case /input/case.json --out /app/output --fill fill.json --status partial`
   仅当全部契约字段有真实依据时才将 `status` 置为 `ok`。

## 输出

`/app/output/result.json`，镜像 output_contract 全部字段，其中本技能负责：

- `legal_status`：每件专利的头条状态 + 依据来源 tier + `query_date` + 滞后声明；
- `license_report` / `degradation_plan`：`license_tiers.py` 的两份输出；
- `conflicts`：状态冲突披露块（双保留 + 登记级优先 + `conflict_disclosed=true`）；
- `wording_check`：`wording_guard.py` 的扫描报告；
- `sources`：实际使用来源（含 tier 与 color）；
- `uncertainty`：含滞后声明、license 未澄清声明、无法访问声明；
- `change_records`：scaffold → 各次填充的时间线。

## 关键方法

1. **登记优先协议（register-first）**：法律状态断言只能由 `register` / `official_gazette` 级来源支撑；聚合、转载、未知层级来源只能支撑「未核验」声明（规则 S1）。详见 `references/legal_status_protocol.md`。
2. **unknown 是一等公民**：`unknown` 是枚举内的合法诚实取值，不是失败；材料无法支撑核实时必须声明 `unknown` 并附查询日期，禁止用聚合页印象冒充登记结论。
3. **绿/黄/红分级与能力降级**：绿=公开可全文；黄=仅字段/仅引述/需注册/license 未澄清；红=付费/受限/登录墙/禁止展示。红级 `do_not_fetch`，黄级按许可范围降级展示，详见 `references/authorization_boundary.md`。
4. **冲突双保留 + 登记级优先 + 披露**：同一专利的状态冲突不掩盖、不投票抹平；双方断言均保留进 `conflicts` 块，头条状态取登记级来源（register > official_gazette > 其他），并显式标记 `conflict_disclosed=true`。

## 案例路由表

| 案例类型 | 路由 |
|---|---|
| 法律状态核验 / 授权边界类（主场景） | 完整跑 6 步流水线：scaffold → classify/plan → 台账 → validate → wording guard → fill |
| 号码/主题检索类（非本技能主场景） | 仍必须跑 `license_tiers.py classify`（来源分级）+ `wording_guard.py`（结论草稿）作为**交付前闸**；若结论涉及任何法律状态表述，补跑台账校验 |
| 材料中混有付费库/转载页 | 先分级再使用：红级只标「无法访问」，黄级只取许可字段 |

## 异常处理表

| 异常 | 处置 |
|---|---|
| `case.json` 缺失/非法/契约字段缺失 | `scaffold_result.py` 降级产出最小骨架并警告，退出码仍 0；不得停工 |
| 台账校验退出码 1 | 逐条修复违规；无法取得登记级依据时改为 `asserted_status=unknown`（保留 query_date） |
| query_date 超 90 天 | S3 仅警告：在 `legal_status` 与 `uncertainty` 中附加「状态可能滞后」声明并尽量复核 |
| 同一专利多来源状态冲突 | 不判失败：冲突块双保留、登记级头条、披露标记；在 `uncertainty` 中说明 |
| 来源 license 字段缺失/未知 | 按黄级处理直至澄清，并在 `uncertainty` 声明 |
| 结论草稿被 wording_guard 拦截（退出码 1） | 按行号逐条改写为标准措辞模板（见 references），改写后重跑 |
| 预算不足 | 保持骨架交付，`status=partial`，在 `uncertainty` 列出未完成字段 |

## 自查

```bash
python3 scripts/selfcheck.py    # 21 项断言全部 PASS，退出码 0
```

## 最小示例

```bash
cd /app/work
python3 /skills/weekly-skill/scripts/scaffold_result.py --case /input/case.json --out /app/output
python3 /skills/weekly-skill/scripts/license_tiers.py classify --sources sources.json --out license_report.json
python3 /skills/weekly-skill/scripts/status_ledger.py validate --ledger status.jsonl --sources sources.json
python3 /skills/weekly-skill/scripts/wording_guard.py --conclusions conclusions.md --ledger status.jsonl --sources sources.json --out wording_check.json
```

完整可复现示例（含真实输出）见 `examples/example_walkthrough.md`。
