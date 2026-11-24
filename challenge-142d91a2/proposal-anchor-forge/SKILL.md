---
name: proposal-anchor-forge
description: |
  开题报告/研究计划书的上游材料真实性与论断保真管线（Anchor-First Claim Fidelity）。重心不在文采与结构，而在根除开题写作最常见的失败——「材料外事实」：模型凭印象编造文献结论、数字与引用。管线先把 /input 全部材料抽成带稳定锚点（M1-P003）与字符偏移的段落库并做抽取 QC（乱码率/截断迹象/不可读/空文件），再要求开题稿七要素（研究背景与缺口、问题定义、目标、技术路线、阶段计划、风险、预期成果）中每条事实句/数字/引用都登记 fact ledger（锚点 + 逐字引文），最后用核验器做归一化逐字比对，fail/unverifiable 论断机器强制拦截，禁止进入交付稿；inference 论断不强制引文但必须在文中标注「推断」。
  触发：task.md 要求基于给定材料（文献摘录/前期数据/PDF）撰写开题报告、研究计划书、立项依据，且论断须可追溯、引用须可复核时。不触发：自由选题无材料写作、纯语言润色、文献综述代查（不保证材料外检索）、实验方案科学正确性裁决。
  Trigger: grounding a research proposal / grant opening report in supplied source materials with verbatim-claim verification, anchor-locked citations and machine-blocked unverifiable statements. Not for: free-writing without sources, language polish, literature search beyond the supplied corpus, adjudicating scientific soundness.
---

# 开题论断锚定锻造器（Proposal Anchor Forge）

## 0. 定位与差异化

本 Skill 的独占重心是**上游材料真实性与论断保真**。开题稿最致命的失败不是结构不全，
而是「材料外事实」——模型凭训练印象编造文献结论、张冠李戴数字、伪造引用。本管线把
「稿中每个事实字都能指回材料原文」变成机器强制检查，而非模型自述：

1. `anchor_extract.py` 把 `/input` 全部材料（含 case.json、task.md、md/txt、PDF 经
   pdftotext）抽成稳定锚点段落库 + QC 清单（乱码率/截断/不可读/空文件）；
2. Agent 在锚定文本上起草七要素开题稿，每条事实句/数字/引用登记 fact ledger
   （`claim_id/section/claim_text/anchor/quote/kind`）；
3. `verify_claims.py` 归一化逐字核验：quote 必须是锚点文本子串；fail/unverifiable
   论断**禁止进入交付稿**；inference 必须在文中标注「推断」；
4. `result_forge.py` 契约化收尾：字段缺项或核验未全过，强制 `status=partial`。

本 Skill 保证的是**论断保真**；七要素的内容质量由 Agent 在锚定文本上精读完成。

## 1. 运行时契约（评测 harness 约定，必须遵守）

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`、`/input/task.md` 先读；`case.json.output_contract` 决定 result.json 字段，**逐字段抄录，不凭题目猜**。 |
| 工作目录 | `/app/work`（锚点库、QC 清单、台账、草稿中间件）。 |
| 最终交付 | `/app/output/result.json`（含 `case_id` 与全部契约字段）、`anchor_map.jsonl`、`manifest.json`、`fact_ledger.jsonl`、`claim_verification.json`、`proposal_draft.md`。 |
| 预算 | 64 次模型请求 / 900 秒 / 16384 tokens 每响应。**先写有效 partial result.json，再逐步改进**。 |
| Skill 安装路径 | `/skills/weekly-skill`；实际路径不同时相应替换命令中的路径。 |
| PDF | 用真实文件 `pdftotext -layout` 解析；失败记入 manifest.unreadable 与 uncertainty，绝不猜测内容。 |

## 2. 必需工作流（禁止跳步）

### 步骤 0 — 读契约，立即写 partial
读 `/input/case.json` 与 `/input/task.md`，提取 `case_id`、`output_contract` 全部字段、
周期/经费/人员约束。立即执行：
```
python3 /skills/weekly-skill/scripts/result_forge.py init /input/case.json /app/output/result.json \
  --note "contract read; extraction pending"
```
此后任何时刻 result.json 都是有效的诚实 partial。

### 步骤 1 — 锚点抽取 + QC
```
python3 /skills/weekly-skill/scripts/anchor_extract.py /input /app/work/anchors
```
读 `/app/work/anchors/manifest.json`（判据见 `references/extraction_qc.md`）：
- `unreadable` 非空 → 逐条写入 uncertainty，相关论断一律不许引用该材料；
- `garble_suspect` → 该材料引文降级为 inference 或注明可信度存疑；
- `truncation_suspect` → 结论性/指标性论断改用 partial 措辞；
- `empty_files` → 不计入来源，uncertainty 说明。
从每个材料抽 1–2 个锚点用 `char_start/char_end` 回切复读，确认无乱码错位后再继续。

### 步骤 2 — 锚定起草七要素 + 登记台账
通读 anchor_map，起草开题稿七要素（研究背景与缺口、问题定义、目标、技术路线、
阶段计划、风险、预期成果），落 `/app/work/proposal_draft.md`；同时逐条登记
`/app/work/fact_ledger.jsonl`（schema 见 `references/anchor_schema.md` 第 2 节）：
- **quote 逐字复制**锚点 `text`，禁止凭记忆改写；数字连同单位、条件一起引；
- 指标阈值（如效率保持率目标）必须锚到材料中的依据，锚不到就写 inference 并标注「推断」；
- 阶段计划/风险中的周期、经费、人员数字锚到 case.json 的约束段；
- 稿中论断句尾标 `[Cxxx]`，与台账一一对应。

### 步骤 3 — 机器核验，拦截失真论断
```
python3 /skills/weekly-skill/scripts/verify_claims.py /app/work/anchors/anchor_map.jsonl \
  /app/work/fact_ledger.jsonl /app/output/claim_verification.json \
  --accepted /app/output/fact_ledger.jsonl
```
退出码非 0 即有拦截：
- `fail`：修正 quote 为逐字文本后重跑；无法修正的从草稿与台账删除；
- `unverifiable`：补 anchor/quote（或改为带「推断」标注的 inference）后重跑；
- 直到 `all_verified: true`；台账为空时诚实说明「无可锚定论断」，结果保持 partial。

### 步骤 4 — 交付与收尾
草稿定稿（只含核验通过的论断）落 `/app/output/proposal_draft.md`，然后：
```
python3 /skills/weekly-skill/scripts/result_forge.py final /input/case.json /app/output/result.json \
  --status ok --verification /app/output/claim_verification.json \
  --set proposal_draft="proposal_draft.md" --set fact_ledger="fact_ledger.jsonl" \
  --set claim_verification="claim_verification.json" [--set 其余契约字段=...]
```
契约字段有空或核验未全过时，`final` 会强制 `partial` 并在 uncertainty 点名——
不要试图绕过，修正后重跑。

## 3. 异常处置

| 情况 | 处置 |
|---|---|
| 材料缺失 / 全部不可读 | result.json 置 `failed`，uncertainty 逐条列 unreadable 原因，不产出任何论断 |
| 乱码 / 截断 | 按步骤 1 分级降级；相关结论改 partial 措辞并在 uncertainty 点名材料 |
| 周期过短（任务要求周期 < 材料支持的合理周期） | 阶段计划按材料锚定的最小可行周期写，缺口写成 risk 条目（触发信号+备选），不硬凑 |
| 指标不可达（目标超出材料锚定的基线太多） | 目标拆「保底/争取」两档，争取档标 inference；禁止把文献最优值直接当本课题目标 |
| 预算不足（64 请求/900s 吃紧） | 优先保证步骤 0+1+3：锚点库 + 已核验的部分台账 + partial 状态，胜过未核验的完整稿 |
| 重复运行 | 同一输入必得同一锚点集；任何手工改动抽取文本记入 `change_records` |

## 4. 交付前自查清单

- [ ] result.json 含 `case_id` 与全部 output_contract 字段，`status` 诚实（缺项=partial）
- [ ] `claim_verification.json` 的 `fail=0` 且 `unverifiable=0`，回链率 = 1.0（合法无引文 inference 除外）
- [ ] 交付稿中每条事实句/数字/引用句尾的 `[Cxxx]` 都在 accepted 台账中
- [ ] inference 论断在文中均有「推断」字样，且未被当作材料事实陈述
- [ ] 七要素齐全；计划数字（月数/经费/人员）锚定到 case.json 约束段
- [ ] uncertainty 如实覆盖 unreadable / garble / truncation / 空文件

## 5. 最小示例

`examples/` 为**合成示例（非正式案例结果）**：合成「钙钛矿太阳能电池稳定性」开题
材料（case.json + task.md + 前期数据 + 文献摘录），预制 8 条 fact ledger，其中故意
1 条 quote 不逐字（fail）、1 条缺 anchor（unverifiable），`run_example.sh` 端到端演示
抽取 → 核验拦截 → 诚实 partial 收尾；`examples/expected/` 为真实跑出的产物。
