---
name: claim-evidence-alignment-strength
description: 文献证据驱动写作——论断与证据的语义对齐核验和证据强度标定。当任务要求"每句话有依据且措辞与证据强度相称"（对得上、说得准）时使用，适合综述、论文段落、审稿回复等论断密集型写作。本 Skill 的重心在"论断与证据之间的语义接口"：align_check.py 对每条论断做逐字锚定、数字保真、方向一致、否定审视四层确定性核验，strength_map.py 按研究设计把证据定为 A–D 级并检查成稿措辞是否越级。把基础 Agent 最常见的数字错位、方向反转、相关写成因果、单篇小样本写成领域共识，变成可机器拦截的判定。
---

# 论断–证据对齐与强度标定（Claim–Evidence Alignment & Strength Calibration）

## 这个 Skill 解决什么问题

"有引用"不等于"对得上"：基础 Agent 常出现引文真实存在但数字错位（1.8→1.6）、方向反转（降低写成升高）、否定极性丢失、以及措辞强度超过证据等级（单项观察性研究写成"研究表明"）。本 Skill 把论断–证据接口做成两层机器判定：**对齐核验**（证据原文是否说了论断说的话）与**强度标定**（措辞是否与证据等级相称）。机器判定不了语义支持关系本身——那一层由模型判定并写理由，脚本负责拦截所有可确定判定的错位。

## 何时使用

- 论断密集型写作：综述、基金申请书、论文引言/讨论、审稿回复；
- 需要显式区分"原始研究/综述/指南/预印本"并让措辞与之相称的任务。

不适用：无论断结构的描述性写作；无逐字证据可用的纯观点文本。

## 运行契约

- 输入：`/input/case.json`、`/input/task.md`、材料文件；工作区 `/app/work`；产物与 `result.json` 放 `/app/output`。
- `result.json` 含原样 `case_id` 与 `output_contract` 全部键；核验失败的论断不得进入成稿事实句，相关降级写入 `change_log`，缺口写入 `limits`。
- 预算意识：两个脚本均为秒级；"对齐核验→修复→复验"循环不耗模型请求。

## 依赖

- Python ≥3.9 标准库；页码回填需要提取文本旁的 `<source>.pages.json`（可用任何 PDF 提取工具生成，格式见下），无索引时页码留空但不阻断。
- 脚本：`scripts/align_check.py`（四层对齐核验）、`scripts/strength_map.py`（定级+措辞校准）；口径：`references/strength_rubric.md`。

## 工作流（严格按序执行）

**步骤 0 — 读契约、备文本**
```bash
mkdir -p /app/work/text /app/output
python3 -c "import json;d=json.load(open('/input/case.json'));print(d.get('case_id'),sorted(d.get('output_contract',{})))"
```
把材料全文提取到 `/app/work/text/<source>.txt`（`\f` 分页；PDF 用 `pdftotext -layout`）。`<source>.pages.json` 格式：`[{"page":1,"start":0,"end":N}, ...]`。

**步骤 1 — 论断原子化与证据登记（模型）**
写 `/app/work/claims.json`：每条论断一句、含可检验要素（对象/方向/数值/条件）；每条证据登记 source、quote（连续原文 25–300 字符）、relation（supports/partial/contradicts，由模型判定并写理由）。登记研究设计信息到 `/app/work/claims_meta.json`（design/n/consistent，枚举见 strength_rubric.md）。

**步骤 2 — 对齐核验（脚本）**
```bash
python3 /skills/weekly-skill/scripts/align_check.py /app/work/claims.json /app/work/text /app/work/align.json --report /app/output/alignment_report.md
```
- failed 证据：按 strength_rubric.md 第 3 节判定原因修复（重摘 quote、改正数字、修正方向）后复验；无法修复的论断降级为〔未锚定〕或删除，记入 change_log；
- review（NEGATION-REVIEW）：人工核对语义，结论写进证据表，不得跳过。

**步骤 3 — 强度标定与措辞校准（脚本）**
```bash
python3 /skills/weekly-skill/scripts/strength_map.py --meta /app/work/claims_meta.json \
  --draft /app/output/deliverable.md --out /app/work/strength.json --report /app/output/strength_report.md
```
OVERSTATED 的句子按报告中的"允许措辞"改写后复验，直至退出码 0。

**步骤 4 — 成稿铁律（模型）**
- 只有 supported 论断能写成事实句；partial 论断只写被 anchored 证据覆盖的部分；〔未锚定〕不得出现为事实；
- 措辞强度不得超过 strength_map 给出的等级上限；相关性证据不写因果动词；
- 冲突证据（relation=contradicts）必须双方都呈现，写入 uncertainty。

**步骤 5 — 交付与自查**
result.json 按 output_contract 组装；`sources` 列出全部来源；`uncertainty` 收冲突与 review 项；自查：①align 全部 supported/partial 且 partial 已限幅；②strength 退出码 0；③报告文件在 /app/output 可复核；④case_id 与契约键原样。

## 异常处理

- 来源文本缺失（SOURCE-MISSING）：该证据 failed，不得"凭印象"保留论断；
- 材料只有摘要可用：定级不得超过 C，且 quote 必须来自摘要原文，limits 说明"仅摘要可及"；
- claims.json 结构错误：脚本按 failed 处理而非崩溃——先修登记再写作。

## 最小调用示例（合成示例，非正式案例结果）

`examples/input/` 含 2 份合成来源文本、claims.json（3 条论断：1 条正常、1 条数字错位、1 条方向反转）、claims_meta.json 与一版含越级措辞的草稿。执行：
```bash
python3 scripts/align_check.py examples/input/claims.json examples/input/text /tmp/align.json
python3 scripts/strength_map.py --meta examples/input/claims_meta.json \
  --draft examples/input/draft.md --out /tmp/strength.json
```
align 结果：C1 supported（anchored），C2 因数字错位（1.6 vs 原文 1.8）failed，C3 因方向反转 failed，脚本退出码 1；strength 把 C1 定为 C 级（单项队列）并检出草稿中"证据表明"越级，退出码 1。真实输出见 `examples/minimal_example.md` 与 `examples/output/`。

## 限制与维护

- 对齐是字符串级判定，同义改写会被拒绝（有意的严格口径）；语义支持关系由模型判定，脚本不替代；
- 词表与分级规则集中在脚本顶部常量与 `references/strength_rubric.md`，扩展时两处同步；
- 英文成稿需在 FORBIDDEN/ALLOWED 补充英文措辞（当前覆盖中文）。
