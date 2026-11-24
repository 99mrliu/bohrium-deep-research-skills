---
name: anchor-provenance-guardian
description: |
  论文结构诊断的上游证据锚定管线（Anchor-Grounded Provenance Pipeline）。重心不在诊断算法，而在输入数据真实性与来源可复核：先把 /input 的稿件材料抽成带稳定锚点与字符偏移的段落库并做抽取 QC（乱码率、截断迹象、不可读文件），再要求每条结构诊断携带锚点 + 逐字引文，最后用机器核验器强制验证全部引文，使「说得清」成为可重跑检查而非自述。六类结构问题（研究问题/章节结构/论证链/段落关系/重复内容/结论边界）在锚定层之上由模型精读判定。
  触发：task.md 要求对论文/稿件做结构诊断、逻辑审查、改稿建议且需保留来源时。不触发：纯语言润色、语法校对、科学正确性裁决、查重。
  Trigger: source-grounded structural diagnosis of manuscripts with verifiable anchors and verbatim-quote verification. Not for: language polish, grammar, scientific-correctness adjudication, plagiarism.
---

# 锚定溯源诊断器（Anchor Provenance Guardian）

## 0. 定位与差异化

本 Skill 的重心是**上游数据真实性**：结构诊断最常见的失败不是判错，而是引文失真——模型凭印象引用原文、锚点漂移、把抽取乱码当成稿件内容。本管线把「每条判断可指回原文位置与依据」变成机器强制检查：

1. `anchor_extract.py` 把材料抽成稳定锚点库（`S1-P007` 式锚点 + 字符偏移），并给出乱码率/截断/不可读的 QC 清单；
2. 所有诊断 finding 必须带 `anchor` + 逐字 `quote`；
3. `verify_quotes.py` 强制核验每条 quote 逐字命中锚点文本，未通过者不得进入最终结果；
4. `result_kit.py` 保证 result.json 逐字段满足 `case.json.output_contract`，partial 状态诚实可查。

诊断本身（六类缺陷的识别）由 Agent 在锚定文本上精读完成——本 Skill 保证的是**诊断引用的每一个字都可独立复核**。

## 1. 运行时契约（评测 harness 约定，必须遵守）

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`、`/input/task.md` 先读；`case.json.output_contract` 决定 result.json 字段，**逐字段抄录，不凭题目猜**。 |
| 工作目录 | `/app/work`（锚点库、QC 清单、诊断中间稿）。 |
| 最终交付 | `/app/output/result.json`（含 `case_id` 与全部 output_contract 字段）、`anchor_map.jsonl`、`manifest.json`、`diagnosis.json`、`quote_verification.json`、`editing_plan.md`。 |
| 预算 | 64 次模型请求 / 900 秒 / 16384 tokens 每响应。**先写有效 partial result.json，再逐步改进**。 |
| Skill 安装路径 | `/skills/weekly-skill`；若实际路径不同，命令中的路径相应替换。 |
| PDF | 用真实文件 `pdftotext -layout`；失败如实记录，绝不猜测内容。 |

## 2. 必需工作流（禁止跳步）

### 步骤 0 — 读契约，写 partial
读 `/input/case.json` 与 `/input/task.md`，提取 `case_id`、`output_contract` 全部字段、受众/体裁约束。立即：
```
python3 /skills/weekly-skill/scripts/result_kit.py init /input/case.json /app/output/result.json --note "contract read; extraction pending"
```
此后任何时刻 result.json 都有效。

### 步骤 1 — 锚点抽取 + QC
```
python3 /skills/weekly-skill/scripts/anchor_extract.py /input /app/work/anchors
```
读 `/app/work/anchors/manifest.json`：
- `unreadable` 非空 → 记入 result.json 的 `uncertainty`，相关维度诊断降级；
- `garble_suspect` → 标注受影响来源，引文可信度在 finding 中注明；
- `truncation_suspect` → 结论边界类判断改为 partial 措辞。
抽查 3–5 个锚点人工复读原文，确认无乱码/错位后再继续。

### 步骤 2 — 六维精读诊断（模型在锚定文本上工作）
通读 anchor_map（长稿按来源分段读），对六类各产出 findings 或「已检查无重大问题 + 检查方式」记录。finding 字段见 `references/anchor_schema.md` 第 3 节：`id/dimension/anchor/quote/defect_class/action/severity`。
- **quote 必须逐字**从 anchor_map 的 `text` 字段复制，禁止凭记忆改写；
- `action` 是可执行编辑动作（移动/合并/拆分/收窄/删重/补过渡），不是「建议作者注意」；
- 六类缺类 = 不完整，写入 `/app/work/diagnosis.json`：`{"case_id":..., "findings":[...], "dimension_clearance":{...}}`。

### 步骤 3 — 机器核验引文
```
python3 /skills/weekly-skill/scripts/verify_quotes.py /app/work/anchors/anchor_map.jsonl /app/work/diagnosis.json /app/output/quote_verification.json
```
- `fail`：修正 quote 为逐字文本后重跑；无法修正的删除该 finding；
- `unverifiable`：补 anchor/quote 或删除；
- 直到 `all_verified: true` 或剩余 finding 数为 0（0 时诚实说明「未发现可锚定的重大缺陷」）。

### 步骤 4 — 交付与收尾
把核验后的 diagnosis 落到 `/app/output/diagnosis.json`；写 `/app/output/editing_plan.md`（按 severity 排序的编辑动作清单，每条指回 finding id 与锚点）；最后：
```
python3 /skills/weekly-skill/scripts/result_kit.py final /input/case.json /app/output/result.json --status ok --findings <N> --verified <ok/total>
```
契约字段有缺时状态必须 `partial` 并在 uncertainty 点名缺失项。

## 3. 异常处置

| 情况 | 处置 |
|---|---|
| 无可读材料（unreadable 覆盖全部来源） | result.json 置 `failed`，uncertainty 逐条列失败原因，不产出任何诊断 |
| 缺章节/无参考文献 | 不是异常：在 finding 中作为「章节结构」类缺陷记录并锚定到现存文本 |
| 重复运行 | 同一输入必得同一锚点集；手工改动抽取文本须记 change_record |
| 预算不足 | 优先保证步骤 1+3 完成：锚点库 + 已核验的部分 findings + partial 状态，胜过未核验的完整诊断 |

## 4. 自查清单（交付前）

- [ ] result.json 含 `case_id` 与全部 output_contract 字段，`status` 诚实
- [ ] `quote_verification.json` 的 `fail` 与 `unverifiable` 为 0
- [ ] 六类均有 finding 或带检查方式的 clearance
- [ ] 每条 finding 的 action 是可执行编辑动作
- [ ] uncertainty 如实覆盖 unreadable/garble/truncation

## 5. 最小示例

`examples/` 内含**合成示例**（非正式案例结果）：合成稿件 + 合成 case.json，运行 `run_example.sh` 端到端演示抽取→诊断→核验→收尾；`examples/expected/` 为真实跑出的示意输出，仅供说明接口。
