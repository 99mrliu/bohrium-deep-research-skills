---
name: reasoning-chain-auditor
description: >-
  论文逻辑与论证审查的推理层工作流：审计从前提到结论的推理链是否完整、是否越界。
  当任务是审查 /input 中的科研论文（case.json + task.md + PDF/文本材料）并要求识别
  推理跳跃、隐含假设、替代解释未排除、相关性与因果性混用时使用。核心立场：推理问题
  的特点是"每句都对，连起来不对"——单句审查抓不住，必须把结论句与它的前提句两端
  同时锚定再判断。本 Skill 用 scripts/chainlint.py（纯标准库、确定性、零依赖）检测
  设计类型（观察性 vs 随机对照）、因果动词、局限性讨论、小样本与全称措辞，生成
  R1–R4 机械候选（因果超出设计 / 前提未交付 / 替代解释未讨论 / 小样本全称结论），
  并由 verify 门禁强制每条 finding 同时给出结论句与前提句的句子锚点。判断留给
  审查者。不适用：文字润色、查重、参考文献格式规范、统计复算。
---

# reasoning-chain-auditor：每句都对，连起来对不对

## 定位

本 Skill 的重心在**推理层**，对应题目突破方向 3（推理链完整性）。方法论核心：
**两端锚定**——任何推理类 finding 必须同时给出结论句（conclusion_sentence_id）
与前提句（premise_sentence_ids），评审可一次性核对"从什么推出什么、断在哪一环"。

## 固定路径与运行契约

- 引擎：`/skills/weekly-skill/scripts/chainlint.py`（下文 `$CH`，`python3`，≥3.8，纯标准库）
- 参考：`/skills/weekly-skill/references/reasoning_rules.md`（R1–R4 定义、设计—措辞
  对齐矩阵、误报边界、严重度判据）
- 输入：`/input/case.json`、`/input/task.md`、论文材料（PDF 先转文本）
- 工作区：`/app/work`；交付：`/app/output/result.json` + `report.md`
- `result.json` 必须含原 `case_id` 与 `output_contract` 全部字段；第 0 步先写骨架

## 执行协议

### 第 0 步：读契约、写骨架

读 case.json、task.md；立即写 result.json 骨架（全字段占位 + in_progress）。

### 第 1 步：推理图谱

```bash
python3 $CH scan --paper /app/work/paper.txt --work /app/work
```

`reasoning_map.json`：设计线索（观察性/实验性/相关性词）、因果动词句、局限性
讨论句、全称措辞句、样本量。exit=3（空文本）→ `未检查/no_text_layer` 诚实 partial。

### 第 2 步：R1–R4 候选

```bash
python3 $CH candidates --work /app/work
```

候选规则（详表见 references）：
- R1 因果超出设计：观察性/相关性设计 + 结论位因果动词（导致/驱动/使得/cause…）。
- R2 前提未交付：讨论/结论句关键词 ≥70% 在结果章零覆盖 → 疑似推理跳跃。
- R3 替代解释未讨论：全文无局限性/替代解释段落（论文级候选）。
- R4 小样本全称结论：n≤5 而结论用"所有/任何/均/all"。

### 第 3 步：人工走链（主战场）

对每条 R1/R2 候选回原文走完整链条：结论句 → 它依赖的结果句 → 结果依赖的
方法设计。逐链记录：前提是否真实交付（R2）、设计与结论措辞是否对齐（R1）、
主要替代解释是否被讨论（R3）、结论适用范围是否超出样本（R4）。同时按
task.md 覆盖六类检查项；推理链只是脊柱，事实核验、引用支持等照常逐条做，
每条同样要求 sentence_id + 逐字 quote。

### 第 4 步：verify 门禁

```bash
python3 $CH verify --work /app/work --findings /app/work/findings.json
```

强制：quote 逐字；每条 finding 两端锚定（前提确实不存在时 premise 留空但
status 必须标待复核或 basis 写明"无前提"）；basis 写明断裂点；suggestion ≥15
字且落到改哪句/补哪个推理环节。exit=4 逐条修正重跑。

### 第 5 步：交付

result.json：output_contract 全字段 + case_id + findings（type/severity/
conclusion_sentence_id/premise_sentence_ids/quote/basis/suggestion）+
status（通过/问题/待复核/未检查分列）+ uncertainty + provenance。
report.md 按严重度排序。

## 严重度判据

critical：主结论的因果断言超出设计（R1 落在摘要/结论核心句）或主结论前提
未交付。major：R1/R2 落在关键中间结论；R3 成立且设计存在明显混杂。minor：
R4、局部措辞越界。info：建议。判据写入 basis。

## 反误报规则

1. 转述他人因果观点（带 [n]/(Name, year)）不按 R1 计作者缺陷；只可单独立
   "引用支持"待复核条。
2. 作者自注"假设/有待验证"的因果句不按 R1 定案，最多给 info 建议。
3. R2 的关键词覆盖是机械近似：定性结果、图载体前提会被误判——定案前必须
   回结果章通读确认前提真的缺席。
4. 拿不准 → 待复核 + 说明。

## 预算规划（64 次模型请求 / 900 秒）

工具不占模型预算。第 0–2 步 ≤6 次；第 3 步按候选数均分，R1 > R2 > R3 > R4
排序；第 4–5 步 ≥4 次。未定案项标待复核交付诚实 partial。

## 异常处理

| 情况 | 处置 |
|-|-|
| 扫描版无文本层 | `未检查/no_text_layer` 交付 partial |
| 章节检测失败 | 降级为全文扫描，结果中注明粒度损失 |
| verify exit=4 | 按 chain_verify.json 逐条修正，禁止删锚点绕过 |

## 不适用

文字润色、查重、参考文献格式规范、统计复算、投稿策略。

## 最小示例

`examples/minimal/`（**合成示例，非正式案例**）：横断面问卷研究合成短文，
故意含"相关写成导致""所有岗位均受影响""无替代解释讨论"。
`sh examples/minimal/run_example.sh` 真实执行：scan → R1=3/R2=2 候选 →
伪造 quote 与缺前提锚定的 finding 被拦下（exit=4）→ 两端锚定的合规
findings 通过。产物在 `examples/minimal/outputs/work/`。
