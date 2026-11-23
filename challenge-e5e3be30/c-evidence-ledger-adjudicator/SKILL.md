---
name: evidence-ledger-adjudicator
description: 文献证据溯源与事实核验中的"支持度判定"工具。当需要对一组待核验论断逐条给出 supported / partially_supported / contradicted / insufficient_evidence 四级判定、且要求判定可复现、可审计、可反驳时使用：模型只负责取证并填写证据台账（强度档 direct/indirect/topical、极性 same/opposite、锚点覆盖），最终判定由脚本按公开决策规则从台账确定性地算出。适用于系统性综述核查、论文事实核验、摘要与正文一致性检查、多论断批量裁决；不适用于无明确论断列表的开放式主题调研、无需审计轨迹的一次性问答。
---

# evidence-ledger-adjudicator：台账式机器裁决

**核心理念**：模型直接"感觉"判定级别是不可审计的——同样的证据两次跑可能给出不同
级别。本 Skill 把职责拆开：

- **模型只做两件事**：(1) 取证——从论文中摘录逐字 quote 并给每条证据标
  **强度档**（direct / indirect / topical）、**极性**（same / opposite）、
  **锚点覆盖**（covers）；(2) 填台账。
- **脚本做判定**：`verdict_engine.py` 按 `references/verdict-rules.md` 的公开
  决策规则从台账**确定性**地算出四级判定——同一份台账永远得到同一个 verdict。
  冲突检测（正反 direct 证据对撞）由 `conflict_pairs.py` 完成。

> **红线**：不允许绕过脚本直接定级。不同意裁决结果时，只能补充/修正台账中的
> 证据条目（或修正锚点），重新跑 `verdict_engine.py`，并在 result.json 的
> `change_records` 中说明改了什么、为什么。

## 1. 评测运行契约（必须遵守）

- 评测方把本 Skill 安装到 `/skills/weekly-skill`；下文 `<skill>` 即
  `/skills/weekly-skill`，脚本路径形如 `<skill>/scripts/verdict_engine.py`。
- 输入在 `/input/`：
  - `case.json`（含 `case_id` 与 `output_contract`）
  - `task.md`
  - `claims-to-verify.json`（论断是**待核验的问题**，不是权威事实）
  - 论文 PDF；`environment/resources.yaml`（若有）
- 工作目录 `/app/work`；最终成果 `/app/output`，**必须有 `result.json`**，
  包含：`case_id` + `output_contract` 全部字段 + 诚实的 `status`
  （complete / partial / failed）+ `sources` + `uncertainty` + `change_records`。
- 预算：**64 次请求 / 900 秒 / 每响应 16k tokens**。
- 保存策略：**先写骨架 `result.json`（status=partial）再增量覆写**，每完成一个
  论断的裁决就覆写一次，防止预算耗尽时成果全丢。
- 四级判定语义：`supported` / `partially_supported` / `contradicted` /
  `insufficient_evidence`；**主题相关 ≠ 支持**；**未报告 ≠ 反驳**；
  冲突时**并列双方原话与定位**。

## 2. 何时用 / 不用

**用**：有明确论断清单需要逐条核验；判定需要审计轨迹与复现性；需要检测
论文内部（摘要 vs 正文）或论文之间的证据冲突；批量论断需要一致的判定口径。

**不用**：开放式文献调研无论断清单；只需定性总结无需定级；论断无法落到任何
可引用证据（此时直接 insufficient_evidence 并说明，不必硬造台账）。

## 3. 输入盘点（开工先做，1 次请求内完成）

1. 读 `case.json`：记录 `case_id`，逐字段抄下 `output_contract`（最终
   result.json 的字段以此为准）。
2. 读 `task.md`：确认任务变体与额外约束。
3. 读 `claims-to-verify.json`：数论断条数，估算每条预算。
4. 列出 PDF 清单与 `resources.yaml`（若有）。
5. 立即写 `/app/output/result.json` 骨架：`case_id` 照抄、`status:"partial"`、
   每条论断 verdict 暂填 `insufficient_evidence` 并注明"待核验"，
   `sources/uncertainty/change_records` 置空数组，其余字段按 output_contract
   置占位值。

## 4. 流水线（取证归模型，裁决归脚本）

工作目录建议：`/app/work/ledgers/`。

| 步 | 执行者 | 动作 | 命令/产物 |
|---|---|---|---|
| 0 | 模型 | 输入盘点 + 骨架 result.json | 见 §3 |
| 1 | 脚本 | 生成台账骨架（含锚点预提取：数值及变体、比较词及反义对、否定词、条件短语、因果词、范围量词） | `python3 <skill>/scripts/ledger_init.py /input/claims-to-verify.json --outdir /app/work/ledgers` |
| 2 | 模型 | 读 PDF 取证，逐条填 `evidence`（见 §5） | 直接编辑 `ledger-<id>.json` |
| 3 | 脚本 | 机检 | `python3 <skill>/scripts/ledger_validate.py /app/work/ledgers`（WARNING 不阻塞，ERROR 必须先修） |
| 4 | 脚本 | 确定性裁决并写回 | `python3 <skill>/scripts/verdict_engine.py /app/work/ledgers --explain --update` |
| 5 | 脚本 | 冲突对撞检测 | `python3 <skill>/scripts/conflict_pairs.py /app/work/ledgers --out /app/work/conflicts.json` |
| 6 | 模型 | 组装 result.json 并覆写（status 视完成度） | verdicts 逐条抄裁决结果 + 理由骨架 |
| 7 | 模型 | 自查清单（§8）后收尾 | 覆写 result.json |

预算紧张时：优先保证每条论断至少跑完步骤 1 与 4（空台账 → R1 自动判
insufficient_evidence），已取证的论断优先补全。

## 5. 台账填写规范（模型侧唯一职责）

每条证据一个对象，字段缺一不可（validate 会查）：

| 字段 | 取值 | 说明 |
|---|---|---|
| `evidence_id` | E1, E2, … | 台账内唯一 |
| `side` | pro / con | 该证据被归档到支持方还是反驳方 |
| `strength` | direct / indirect / topical | 判定标准见 `references/strength-rubric.md` |
| `polarity` | same / opposite | 证据方向/数值与论断一致或相反（**未报告 ≠ opposite**） |
| `covers` | ["A1", …] | 该证据**实际覆盖**的锚点 id；direct 不允许为空 |
| `quote` | 逐字原文 | 禁止改写、禁止省略关键数字；可用 "…" 拼接同段两处 |
| `page` | 整数或 null | PDF 页码 |
| `section` | 字符串或 null | 如 "3 结果 / 表 1" |

锚点（anchors）由 `ledger_init.py` 启发式预提取：数值含等价变体
（`30%` ↔ `0.3` ↔ `thirty percent` ↔ `百分之三十`）、比较词带反义对
（higher↔lower / 提升↔降低）、否定词、条件短语、因果词、范围量词
（all/only/任何）。**预提取是启发式的**：模型可增删锚点或修正锚点文本，
但每次增删必须写进 `change_records`。

标注的一致性由 `ledger_validate.py` 机检（WARNING 示例）：direct 证据 covers
为空（W1）；topical 证据却覆盖全部锚点（W2，疑似把主题相关当直接证据）；
side 与 polarity 不一致（W5）；adjudication 与证据构成矛盾（W3/W4/W6）。

## 6. 机裁规则（引用 references/verdict-rules.md）

决策树 R1–R7，自上而下先命中先生效（完整定义与记号见该文件）：

- **R1** 空台账 → insufficient_evidence
- **R2** pro direct 覆盖全部锚点且无 con direct 核心覆盖 → supported
- **R3** con direct 覆盖全部核心锚点（数值/比较词/否定）且强度 ≥ pro → contradicted
- **R4** 正反 direct 同时成立 → 基准 supported，进入 R7
- **R5** pro 仅 indirect 或 direct 未全覆盖 → partially_supported
- **R6** 只有 topical → insufficient_evidence（把"主题相关"压回）
- **R7** 正反 direct 锚点对撞 → 降一档 + conflict 标记，result.json 并列双方
  quote 与定位

`verdict_engine.py --explain` 打印 S1–S7 逐步推导（证据分组、强度、覆盖、
冲突、命中规则、降级）；`--update` 把 `adjudication`（verdict、base_verdict、
base_rule、anchor_table、reasons、conflict_pairs）写回台账。

## 7. 冲突处置

1. 跑 `conflict_pairs.py`，每条冲突记录含 pro/con 双方的 quote、page、section
   与共享锚点。
2. result.json 的冲突字段**逐字并列双方原话**，不做"调和式"改写。
3. 冲突论断的最终判定已由 R7 自动降级；在 `uncertainty` 中说明冲突未消解
   的原因（如"摘要与表 1 数值不一致，需作者更正"）。

## 8. 输出契约自查清单（提交前逐项打勾）

- [ ] `case_id` 与输入 case.json 完全一致
- [ ] `output_contract` 声明的字段一个不少
- [ ] 每条论断的 verdict 来自台账 `adjudication.verdict`（非模型手填）
- [ ] 每条 verdict 可回溯：理由骨架引用规则编号（R1–R7）与 evidence_id
- [ ] 冲突论断并列了双方 quote + page/section
- [ ] `sources` 列出实际使用的论文与定位
- [ ] `uncertainty` 诚实列出未消解项；`change_records` 记录全部人工干预
  （含锚点增删、证据补充、重跑）
- [ ] `status` 诚实：未跑完所有论断 → partial
- [ ] 未核验论断一律 insufficient_evidence 并注明"预算内未核验"

## 9. 异常处理表

| 异常 | 处置 |
|---|---|
| `claims-to-verify.json` 缺失/结构错误 | ledger_init 退出 1/2；result.json status=partial，uncertainty 记录，verdicts 尽力按已有信息填 insufficient_evidence |
| PDF 无法解析/缺页 | 该来源标不可用在 sources 注明；受影响论断只能依靠其余证据，不足则 R1/R6 自然落到 insufficient_evidence |
| validate 报 ERROR（exit 1） | 阻塞：先修台账再裁决；不允许带 ERROR 进 verdict_engine（引擎也会拒绝） |
| validate 报 WARNING | 不阻塞，逐条复核；W2/W5 通常意味着模型标注越界，应修正后重跑 |
| verdict_engine exit 2 | 路径/JSON 错误：检查台账文件完整性后重跑 |
| 请求/时间预算将尽 | 立即覆写 result.json：已完成论断写实判，其余 insufficient_evidence + uncertainty 注明"预算内未核验"，status=partial |
| 不同意引擎裁决 | 只允许改台账证据/锚点并重跑；全过程写入 change_records；禁止手改 verdict |

## 10. 示例

`examples/` 含合成示例（虚构论文，含正文、结果表、限制段及一处摘要与正文
数值不一致）：`run_example.sh` 端到端跑通 初始化→演示台账→机检→裁决→
冲突检测→组装 result；4 条论断分别落在四种判定，其中 C4 演示"模型想把
主题相关判 supported，被 R6 压回 insufficient_evidence"。实际输出见
`examples/EXPECTED.md`。
