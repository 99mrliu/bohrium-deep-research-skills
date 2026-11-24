---
name: fact-provenance-ledger
description: 审稿回复与论文修改场景的事实台账与落地守卫 Skill——先把基线与意见摘要编译成带来源锚点的事实台账，再让修订稿与回复信中的每个数字和事实性论断强制回溯到台账，材料外事实由脚本机器拦截。
---

# fact-provenance-ledger：审稿回复与论文修改（事实溯源版）

## 用途与适用条件

适用：给定基线稿（可能是组织方摘要，非完整原稿）与审稿意见摘要（非逐字审稿报告）的「审稿回复与论文修改」任务。本 Skill 的第一公民是**事实台账**：改稿和写信之前，先把材料编译成 `facts.jsonl`（每个数字、单位、术语、引用、关键论断都带来源锚点：文件/章节/段序/逐字 quote）；之后任何新文本中的每个数字与事实性论断必须能回溯到台账，材料外事实由脚本机器拦截并列出警告。

不适用：无 materials 目录、或任务要求补做真实实验/冒充编辑部决定等越权操作（此类需求只能记为未到位证据）。

## 运行契约

- 运行时输入：`/input/case.json` 与 `task.md`；材料在 `materials/manuscript-baseline.md`（组织方基线摘要）与 `materials/reviewer-comments.md`（意见摘要）；可能有 `environment/resources.yaml`。
- 工作目录：`/app/work`；最终产物与 `result.json` 放 `/app/output`。
- `result.json` 必须含**原始 case_id** 和案例 `output_contract` 的**全部字段**（字段名以 case.json 里的 output_contract 为准，不得凭经验假设），并含诚实 `status`、`sources`、`uncertainty`、修改记录。
- 部分完成必须说明界限：材料缺失 / 无法判断 / 运行失败分别说明。不得冒称真实审稿人逐字要求、真实补做实验、原作者已改稿、编辑部已接收或整篇全文返修完成。
- 预算 64 次模型请求、900 秒：**第一条命令就落一个合法的部分 result.json**，机械工作全由脚本做，Agent 只做判断。

## 快速路径（两条命令，路径与 cwd 无关）

```bash
SKILL=/skills/weekly-skill
# 1) 立即落一个合法的部分 result.json + 编译事实台账 + 拆解意见骨架
python3 "$SKILL/scripts/make_result.py" --case /input/case.json --materials-dir /input/materials --out /app/output/result.json --status partial --note "boot: partial result placeholder" && \
python3 "$SKILL/scripts/fact_ledger.py" --materials /input/materials --out /app/work/facts.jsonl

# 2) Agent 在 /app/work 写好 decisions.json 与 edits.json 后，一键落稿+核验+定稿
bash "$SKILL/examples/run_example.sh" --harness   # harness 模式：/input -> /app/work -> /app/output
```

harness 模式等价于依次执行：`apply_edits.py`（锚点落稿）→ `fact_ledger.py` → 生成回复信骨架 → `ground_guard.py`（落地守卫）→ `make_result.py`（定稿，output_contract 全字段映射）。Agent 也可以逐步手动调脚本，见下文工作流程。

## 工作流程

机械工作全部由脚本完成。**Agent 唯一需要手写的是判断文件 `decisions.json`**（每条意见子要求的处置决策与理由），以及由决策直接导出的 `edits.json`（锚点落稿指令）。

1. **准备**：跑快速路径第 1 条命令。得到 `/app/work/facts.jsonl` 与合法的 partial `result.json`。
2. **读意见**：`reviewer-comments.md` 按摘要逐条拆解为子要求（sub_request），每条标注四种证据状态之一（见事实红线）。
3. **写 `decisions.json`**：`{case_id, decisions:[{sub_request, action∈{edit,respond_only,cannot_do}, reason, evidence_status}]}`。
4. **导出 `edits.json`**：`{change_id, sub_request, action 新增/修改/删除, anchor 基线逐字引用, new_text}`。anchor 必须是基线中逐字且唯一的片段；new_text 中只允许台账内事实。
5. **落稿**：`apply_edits.py` 锚点唯一匹配才落稿，自动打 `<!-- CHG-xx begin/end -->` 标记；未命中/不唯一进 `pending_review`，绝不猜位置。
6. **写信**：按 decisions 生成回复信草案；引用意见时注明「按意见摘要转述」，不得冒称逐字原文。
7. **核验**：`ground_guard.py` 对修订稿与回复信做落地检查，材料外事实列入 `ground_report.json`；--strict 时 exit 1。
8. **定稿**：`make_result.py` 把 output_contract 全部字段映射到产物路径，更新 status/sources/uncertainty/change_records。

## 事实红线

1. 只修订指定基线，不动材料外的任何文件内容。
2. 不新增材料外事实：修订稿/回复信中的每个数字、单位、术语、引用、事实性论断必须出现在 `facts.jsonl` 或白名单中，否则被 ground_guard 机器拦截。
3. 意见按摘要引用并注明「转述自意见摘要」，不冒称逐字审稿原文。
4. 四种证据状态分清：`supported`（台账内有锚点）、`baseline_only`（仅基线声称、无独立证据）、`absent`（材料中找不到，列入未到位证据清单）、`infeasible`（需真实补实验/外部数据，本环境无法完成，只能声明不能伪造）。

## 异常处理表

| 异常 | 处置 |
|---|---|
| 锚点未命中/不唯一 | 该项进 `pending_review`，其余继续；result.json 记 uncertainty |
| 意见冲突 | 两条都回应，decisions.json 说明取舍理由，回复信中向编辑说明 |
| 意见疑似有误 | 不照改；回复信礼貌反驳并引用台账事实，status 仍可 success |
| 无法补实验 | 标 `infeasible`，只声明限制，绝不伪造数据 |
| 基线缺失 | status=unable_to_determine，说明材料缺失 |
| output_contract 冲突/字段不明 | 以 case.json 实际字段为准，全部映射，不明字段值置 null 并 note |
| 多轮返修 | 在既有 CHG 标记基础上追加新 change_id，不抹除历史标记 |
| 脚本失败 | 不阻断：记录 stderr 到 result.json 的 notes，保留已产出的中间文件，status=partial |

## 脚本清单与依赖说明

| 脚本 | 作用 | 依赖 |
|---|---|---|
| `scripts/fact_ledger.py` | 扫描 materials 编译事实台账 facts.jsonl（自动排除 case.json 形状的 JSON） | 仅 Python 3 标准库 |
| `scripts/ground_guard.py` | 草稿落地检查 → ground_report.json；--strict 时 exit 1；支持白名单 | 仅标准库 |
| `scripts/apply_edits.py` | 锚点落稿引擎，打 CHG 标记，派生 changes.json / apply_report.json | 仅标准库 |
| `scripts/make_result.py` | 写/更新 result.json：case_id、status、sources、uncertainty、output_contract 全字段 --artifact 映射、change_records | 仅标准库 |

无任何强制第三方依赖。可选工具（pdftotext、matplotlib）缺失时自动降级：PDF 材料无法抽取时记 uncertainty 并以文本材料为准；不生成图、只交文本产物，并在 result.json 注明降级。

## 最小示例

`examples/` 内含一个完整可运行的**合成示例，非正式案例结果**：`bash examples/run_example.sh` 端到端跑通 quick path，产物写入 `examples/output/`。示例 decisions.json / edits.json 已填好，可直接对照学习判断文件写法。
