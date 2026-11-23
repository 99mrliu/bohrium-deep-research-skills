---
name: provenance-gate
description: 当任务提供论文材料并要求核对论文指标、参数或复现结论时使用；先用逐字引文、物理页码和 PDF 文本层的机器可核验证据门确认“论文确实这样报告”，再让通过项进入参数复原、代码运行和指标比较，未通过项显式隔离。
---

# Provenance Gate：上游证据真实性门

## 1. 用途与适用条件

当评测任务给出论文 PDF、任务说明或候选代码，并要求回答“论文报告值是多少”“参数是否与论文一致”“复现结果是否达到论文指标”时，启用本 Skill。它特别适用于以下风险：

- 模型记住了类似论文的数值，但把别的论文、排行榜或二手解读当成目标值；
- 引文是复述、拼接或“看起来像”的句子，并非论文逐字原文；
- 页码来自论文排版页码、阅读器页码或臆测，不能落到实际 PDF 物理页；
- 合成代码或合成数据上的结果，被误写成作者原始代码、原始数据上的论文数值复现。

本 Skill 的重心只有一件事：**在任何参数复原、环境搭建、候选代码运行和数值比较之前，先证明目标值确实来自论文本身。** 环境、运行和统计只做轻量衔接，不替代完整的论文复现流水线。

## 2. 平台评测契约（必须遵守）

- 平台把 Skill 安装到 `/skills/weekly-skill`，用官方 DeepSeek Harness 运行 3 个固定案例。
- 每个案例的输入位于 `/input/case.json` 与 `/input/task.md`；`case.json` 含有 `case_id` 与 `output_contract` 字段清单。
- 材料按题目提供：通常是真实 PDF 论文且没有预抽取文本层；可能含两份候选数值方法代码，需要实际运行核对；原始数据或作者仓库缺失是预期情况，必须显式登记，不得补造。
- 工作目录是 `/app/work`，最终产物目录是 `/app/output`。
- `/app/output/result.json` 是合约产品，必须包含正确的 `case_id`、`output_contract` 列出的全部字段、诚实的 `status`（`success`、`partial`、`unable` 或 `refused`）、来源定位、不确定性和变更记录。
- 预算约为 64 次模型请求与 900 秒。时间过半后停止开启新实验，优先保存证据、已验证结果和诚实的 `partial`。
- 本子场景是“参数/代码/指标验算与差异归因”。组织方合成代码不等于作者原代码；合成数据上的通过不能写成论文数值复现。禁止编造数据、引文、页码、日志或结论。

## 3. 核心思想

先证明“论文真的这么写”，再谈“我有没有复现”。

每个论文目标值必须先形成一个可机检条目：

```json
{
  "name": "accuracy",
  "value": "0.152",
  "unit": "fraction",
  "page": 7,
  "quote": "The proposed method achieves an accuracy of 0.152."
}
```

`gate.py` 对 PDF 文本层和引文做归一化后的机械子串匹配，并检查 `value` 字面出现在 `quote` 中。只有通过者进入后续比较；未通过者写入 `quarantined.json` 和报告，**隔离不等于丢弃，也绝不允许静默放行**。

## 4. 五条铁律

1. **读真实文件，不臆造。** 数值、页码、引文、代码输出和文件哈希必须来自实际读取或运行；不记得、不猜、不补全。
2. **引文不过门即隔离。** `quote_not_found`、`value_not_in_quote`、`page_mismatch` 均不得进入后续比较；必须保留在 `quarantined.json`、报告和 `result.json` 中。
3. **缺失显式登记。** 原始数据、作者仓库、依赖、文本层、随机种子、硬件等缺失都写入 `missing_materials.json` 与最终不确定性；不能伪造替代品。
4. **合约即产品。** `result.json` 必须含 `case_id` 和 `output_contract` 的每一个字段；无法完成的字段填诚实说明，不能漏键或虚构成功。
5. **预算纪律。** 900 秒预算时间过半后，不再开启新实验；先保存 `pages.jsonl`、门报告、原始运行日志、已验证数值和诚实的 `partial` 结果。

## 5. 固定流程

以下 `$SKILL` 指技能目录；平台上通常为：

```bash
export SKILL=/skills/weekly-skill
mkdir -p /app/work/pages /app/work/gate /app/work/runs /app/output
```

### 步骤 0：盘点输入、建立合约骨架

```bash
python3 "$SKILL/scripts/inventory.py" \
  --input /input \
  --work /app/work \
  --output /app/output
```

该命令生成：

- `/app/work/inventory.json`：递归文件清单、字节大小和 SHA-256；
- `/app/work/missing_materials.json`：缺失材料登记骨架；
- `/app/output/result.json`：不覆盖已有文件的合约骨架；如需重建，人工确认后加 `--force`。

### 步骤 1：抽取 PDF 物理页文本

若盘点确认论文位于 `/input/paper.pdf`：

```bash
python3 "$SKILL/scripts/pdf_text.py" \
  --input /input/paper.pdf \
  --out /app/work/pages/pages.jsonl
```

若实际文件名不同，只替换 `--input` 的路径；页码一律按物理 PDF 页（从 1 开始）。输入为 `.txt` 或 `.md` 时，脚本按单页处理。PDF 无文本层的处理见异常表。

### 步骤 2：为每个论文目标值登记证据

创建 `/app/work/targets.json`，根节点必须是数组。每个待比较的指标、参数或表格值一项：

```json
[
  {
    "name": "accuracy",
    "value": "0.152",
    "unit": "fraction",
    "page": 7,
    "quote": "从指定物理页逐字复制、长度足以唯一核验的原文"
  }
]
```

`value` 必须是论文字面字符串（例如 `"0.152"`），不是计算后的浮点数；`quote` 必须逐字复制；`page` 是实际 PDF 物理页。不要先跑代码再倒推引文。

### 步骤 3：执行证据门

```bash
set +e
python3 "$SKILL/scripts/gate.py" \
  --targets /app/work/targets.json \
  --pages /app/work/pages/pages.jsonl \
  --out /app/work/gate
GATE_STATUS=$?
set -e
printf 'gate exit code: %s\n' "$GATE_STATUS"
```

退出码含义：

- `0`：`GATE: PASS`，全部目标通过；
- `1`：`GATE: FAIL`，至少一项被隔离，只允许 `gated.json` 中的项进入比较；
- `2`：结构错误，修正 `targets.json` 或 `pages.jsonl` 后重跑，不得绕过。

`page_mismatch` 表示引文能在论文中找到，但不在声明页。允许回到证据登记修正页码后重新过门；每次修正都写入变更记录。

### 步骤 4：只比较过门目标，轻量衔接运行证据

1. 读取 `/app/work/gate/gated.json`，它定义了允许比较的指标全集。
2. 读取 `/app/work/gate/quarantined.json`，把每项原因写入最终不确定性或差异归因。
3. 对候选代码分别记录代码路径与哈希、命令、环境、随机种子、完整 stdout/stderr 和产物路径。
4. 合成数据上的通过只能表述为“合成方法代码在合成输入上通过自检”，不能表述为“复现论文数值”。
5. 若作者原始数据或仓库缺失，在 `/app/work/missing_materials.json` 与 `result.json` 显式登记，并把相应结论降为 `partial` 或 `unable`。

### 步骤 5：填写并校验合约产品

在完成人工填写后，至少执行：

```bash
python3 -m json.tool /app/output/result.json >/dev/null
python3 - <<'PY'
import json
with open('/input/case.json', encoding='utf-8') as f:
    case = json.load(f)
contract = case['output_contract']
if isinstance(contract, dict):
    fields = list(contract.get('fields', contract))
else:
    fields = [x if isinstance(x, str) else x.get('name') or x.get('field') for x in contract]
with open('/app/output/result.json', encoding='utf-8') as f:
    result = json.load(f)
missing = [x for x in ['case_id', *fields] if x not in result]
assert not missing, missing
assert result['case_id'] == case['case_id']
assert result['status'] in {'success', 'partial', 'unable', 'refused'}
print('result.json contract check: OK')
PY
```

## 6. 输入与输出解释

### 输入

- `/input/task.md`：自然语言任务、比较口径和交付要求；
- `/input/case.json`：`case_id` 与 `output_contract`；
- `/input/` 下其他文件：论文 PDF、候选代码、合成数据或说明文件，以 `inventory.json` 为准；
- `targets.json`：由 agent 从论文中逐字登记，绝不能由记忆生成。

### 中间输出

- `inventory.json`：输入事实与文件完整性证据；
- `missing_materials.json`：缺失材料登记表；
- `pages.jsonl`：每行 `{"page": n, "text": "..."}`；
- `gated.json`：通过证据门、允许比较的项；
- `quarantined.json`：未通过项及机器可处理原因；
- `gate_report.md`：首行为 `GATE: PASS` 或 `GATE: FAIL` 的人读报告。

### 最终输出

`/app/output/result.json` 必须同时满足：

- `case_id` 与 `/input/case.json` 完全一致；
- `output_contract` 的全部字段都存在；
- `status` 诚实；有隔离项、缺失材料或只能验证合成代码时通常为 `partial`；
- 每个比较值都能追溯到 `gated.json` 的引文、物理页和 PDF 文件哈希；
- 明确列出不确定性、隔离项、缺失材料和变更记录；
- 不把合成数据结果写成作者原始结果，不把合成代码写成作者代码。

## 7. 异常处理表

| 异常 | 处理方式 | 对结果的影响 |
|---|---|---|
| PDF 无文本层、扫描件或三种抽取后端都失败 | 使用平台提供的 `pdf-render` / OCR 工具生成可核验文本；仍失败则记录无法过门 | 不臆造引文；相应字段为 `unable` 或 `partial` |
| `quote_not_found` | 引文未通过门，写入 `quarantined.json`；回 PDF 重新逐字复制后重跑 | 修正前不得比较该目标 |
| `value_not_in_quote` | 数值字面不在引文中；检查是否复制错句、表值与正文混用 | 修正并重新过门前隔离 |
| `page_mismatch` | 引文存在但页码错；标出实际匹配页，允许 agent 改页码后重过门 | 修正记录进入变更日志 |
| 原始数据或作者仓库缺失 | 显式登记为预期缺失；不下载来历不明替代数据 | 结论不得声称完整论文复现 |
| 候选代码运行失败 | 保存命令、环境、stdout/stderr 与失败点；不得编造指标 | 运行结论为失败或 `partial` |
| 时间过半 | 停止新实验，保存证据门、已有日志和诚实结果 | 优先交付 `partial`，不追求虚假完整 |

## 8. 运行契约

- 只在 `/app/work` 写中间文件，只在 `/app/output` 写最终交付物。
- 不修改 `/input`；所有读取都可通过 `inventory.json` 的 SHA-256 复核。
- `result.json` 是最终机器可读合约；Markdown 报告可以辅助，但不能替代它。
- `success` 只用于合约要求的证据、运行和比较都完成且口径清楚；隔离项、缺失材料、OCR 失败、运行失败或只完成合成验证时，应使用 `partial` 或 `unable`。
- `refused` 仅用于任务要求本身违反约束（例如要求编造论文值），并说明拒绝范围。

## 9. 最小示例

`examples/` 含完整可运行的**合成示例（synthetic），非正式案例结果**：

- `examples/input/paper.txt`：虚构的一页论文文本；
- `examples/input/targets.json`：两条正确引文和一条故意臆造引文；
- `examples/input/case.json`：合成合约；
- `examples/run_example.sh`：串联盘点、文本抽取和证据门；
- `examples/expected/`：该合成示例的预期输出副本。

运行：

```bash
bash "$SKILL/examples/run_example.sh" /tmp/provenance-gate-example
```

该示例预期以退出码 `1` 结束，因为第三条目标必须被隔离。它只用于验证工具行为，不代表任何真实论文结论。

## 10. 限制与自查方法

- 本 Skill 保证“目标值与所给 PDF 文本层相符”，不保证 PDF 本身是作者最终版，也不替代论文同行评审。
- 归一化是机械近似；极端排版、公式、图片表格或无文本层 PDF 可能需要 OCR 后人工复核。
- 过门只证明引文存在，不自动证明均值/中位数、数据集、置信区间或实验设置口径一致；这些必须按 `references/evidence_rules.md` 继续核对。
- 自查清单：每个比较值是否在 `gated.json`？每个隔离值是否进入 `quarantined.json` 和最终结果？每个文件是否有哈希？每个数值是否有物理页与逐字引文？`result.json` 是否含全部合约字段？`status` 是否保守诚实？
