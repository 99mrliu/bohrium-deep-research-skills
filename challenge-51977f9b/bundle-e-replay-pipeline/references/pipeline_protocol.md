# 标准流水线协议（pipeline protocol）

本协议定义 slr-replay-pipeline 的标准环节序列、每个环节的输入/输出/登记要求与完成定义。
任何环节产物一经生成立即 `runlog.py record` 登记；模型（LLM）判断环节的产物作为
"冻结输入"登记，确定性脚本环节同时写入 manifest 供 replay 复跑。

## 环节序列总览

```
ingest → dedupe → screen_ta → screen_ft → appraise → extract → synthesize → deliver
```

| 环节 | 主要执行者 | 可确定性重放 | 关键产物 |
|---|---|---|---|
| ingest 摄入 | 脚本/模型 | 视来源而定 | 原始题录库、检索式记录 |
| dedupe 去重 | 脚本 | 是 | 去重后题录、duplicates_removed 计数 |
| screen_ta 题录级筛选 | 模型判定+脚本计数 | 计数部分 | decisions.jsonl（ta）、题录级排除理由计数 |
| screen_ft 全文级筛选 | 模型判定+脚本计数 | 计数部分 | decisions.jsonl（ft）、全文级排除理由计数、flow.json |
| appraise 质量评价 | 模型 | 否（冻结登记） | 质量评价表（逐维度+依据） |
| extract 证据提取 | 模型+模板 | 否（冻结登记） | 证据表（比较字段+原文定位） |
| synthesize 综合 | 模型 | 否（冻结登记） | 结论、冲突证据、研究空白 |
| deliver 交付 | 脚本 | 是 | result.json、checks 三校验记录 |

## 各环节定义

### 1. ingest（摄入）
- **输入**：`/input/case.json`、`/input/task.md`、随案例材料（PDF、题录清单等）。
- **动作**：读取并原样保存材料；记录检索式（数据库、字段、布尔逻辑、同义词、时间/语言
  限制、每段意图——由模型按 SKILL.md 工作流程撰写，存为 `search_strategy.md`）。
- **登记**：`runlog.py record --step ingest --actor agent --inputs <原始材料...>
  --outputs <原始材料副本/检索式...>`。原始材料既作 inputs 也作 outputs（原样入账，
  后续任何改动都能被 verify 发现）。
- **完成定义**：所有输入材料均已登记哈希；检索式成文且可追溯。

### 2. dedupe（去重）
- **输入**：原始题录。
- **动作**：用确定性脚本去重（键：规范化标题+年份，或 DOI），输出 `duplicates_removed`。
- **登记**：outputs = 去重后题录文件；同时把本步命令写入 manifest。
- **完成定义**：`identified - duplicates_removed = screened` 可成立（reconcile F1）。

### 3. screen_ta（题录级筛选）
- **输入**：去重后题录、条款化纳排标准（模型先行成文）。
- **动作**：模型逐条判定 include/exclude 并给**一个主排除理由码**，写入
  `decisions.jsonl`（每行 `{"record_id","stage":"ta","decision","reason"}`）；
  脚本汇总计数。
- **登记**：outputs = decisions.jsonl、计数文件；判定标准版本同时登记。
- **完成定义**：`screened = Σ excluded_title_abstract + fulltext_assessed`（reconcile
  F2）轧平；若给 decisions，F5 对账通过。

### 4. screen_ft（全文级筛选）
- **输入**：题录级通过集、可得全文。
- **动作**：同 screen_ta，stage="ft"；全文不可得必须计入排除理由，不得漏记。
  结束后由脚本生成/更新 `flow.json`。
- **登记**：outputs = 更新后的 decisions.jsonl、flow.json、冻结纳入清单。
- **完成定义**：F3 轧平（`fulltext_assessed = Σ excluded_fulltext + included`）；
  `reconcile.py --flow flow.json --decisions decisions.jsonl` exit 0。

### 5. appraise（质量评价）
- **输入**：纳入集、适用量表（RCT 用 RoB2 维度，观察性研究用 NOS 维度等）。
- **动作**：模型逐研究逐维度给出判断+依据位置+总体等级，并说明等级如何影响结论权重。
- **登记**：outputs = 质量评价表。本环节含模型判断，不进 manifest；其产物作为
  后续环节的冻结输入登记。
- **完成定义**：每篇纳入研究有逐维度判断与依据，无"质量较高"式空话。

### 6. extract（证据提取）
- **输入**：纳入集全文、提取模板。
- **动作**：模型按模板提取比较字段（人群、干预、对照、结局、效应值、原文位置）。
- **登记**：outputs = 证据表（evidence_matrix 的数据源）。
- **完成定义**：每条结论所需字段齐备，定位（页/段/表）可回查。

### 7. synthesize（综合）
- **输入**：证据表、质量评价。
- **动作**：模型形成综合结论；显式区分**材料事实 / 合理推断 / 无法确定**；列出冲突
  证据与研究空白；低质量证据降权说明。
- **登记**：outputs = 综述正文草稿。
- **完成定义**：每条论断均有证据回链；不确定项进入 uncertainty 而非被掩饰。

### 8. deliver（交付）
- **输入**：全部前序产物、runlog、manifest。
- **动作**：跑齐三次校验（runlog verify / reconcile / replay），把 exit 码与摘要写入
  `result.json.checks`；counts 直接取 flow.json；组装最终 result.json。
- **登记**：outputs = result.json 及可复核制品。
- **完成定义**：checks 三项 exit_code 全为 0（或有明确的 partial 降级说明）。

## 人工干预纪律

任何人工改动（修正误判、补充理由、编辑产物）必须：
1. 改动前先 `runlog.py status` 确认当前断点；
2. 改动后立即 `runlog.py record --step <所属环节> --actor human --inputs ... --outputs ... --note "<干预原因>"`；
3. 在 result.json.change_records 追加一条 {actor:"human", step, note} 记录。
