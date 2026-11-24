---
name: draft-lint-quality-gates
description: 文献证据驱动写作——过程质量控制（草稿静态检查与交付门禁）。当任务要求依据科研材料成稿、且评分关注"说得准"（数字与原文一致、相关不写成因果、弱证据不写成强结论、引用不悬空）时使用。本 Skill 的重心在"写作过程的中段"：成稿每个事实句带论断标记〔C#〕，lint 脚本对草稿做确定性逐句检查（数字溯源、引文闭环、占位符、措辞越级、因果滑移），门禁脚本按策略文件裁决 PASS/FAIL，FAIL 不许交付。把基础 Agent 写完才发现的数字错位、引用悬空、过度推断，变成可机器拦截的交付前门禁。
---

# 草稿静态检查与质量门禁（Draft Lint & Quality Gates）

## 这个 Skill 解决什么问题

基础 Agent 的成稿常带三类"看着像对"的硬伤：数字与原文错位（1.8 写成 1.6）、相关性证据被写成因果结论、引文编号悬空或文献列而未引。人工复核这些要逐句回原文，正是评分里"人工返工"的大头。本 Skill 用**标注约定 + 确定性 lint + 策略化门禁**把返工前置为机器检查：每个事实句标〔C#〕，lint 脚本逐句核验数字是否出现在证据摘录原文中、因果措辞是否与证据表述相称、引文是否闭环；门禁脚本按策略裁决，FAIL 的草稿不允许进入 result.json。

## 何时使用

- 已有证据登记（claims/evidence/refs），需要把草稿质量变成可检查、可裁决、可留痕；
- 改稿、校对、综述写作等需要"写得准"多于"写得多"的任务。

不适用：无来源要求的自由写作；证据尚未登记的从零写作（先做证据登记，再启用本门禁）。

## 运行契约

- 输入：`/input/case.json`、`/input/task.md`、材料文件；工作区 `/app/work`；产物与 `result.json` 放 `/app/output`。
- `result.json` 含原样 `case_id` 与 `output_contract` 全部键；门禁 FAIL 时如实交付 partial 并附 lint/门禁报告，不得绕过门禁。
- 预算意识：lint 与门禁是秒级脚本，多轮"修稿→lint→门禁"循环不耗模型请求；尽早落一版全键 partial。

## 依赖

- Python ≥3.9 标准库，无网络依赖。
- 脚本：`scripts/draft_lint.py`（静态检查）、`scripts/gate_check.py`（门禁裁决）；策略与规则：`references/lint_rules.md`、`references/gate_policy.json`。

## 工作流（严格按序执行）

**步骤 0 — 读契约，建登记**
```bash
mkdir -p /app/work /app/output
python3 -c "import json;d=json.load(open('/input/case.json'));print(d.get('case_id'),sorted(d.get('output_contract',{})))"
```
阅读材料、提取证据（逐字摘录 quote），按 `references/lint_rules.md` 的结构建立 `/app/work/evidence_registry.json`（claims/evidence/refs/number_allowlist），并为每条 evidence 判定 strength 且写理由。

**步骤 1 — 带标记写作（模型）**
写 `/app/output/deliverable.md`。每个事实句以 `〔C#〕` 结尾、引文用 `[n]`；每个数字保证来自某条 quote 原文。结构性数字（章节号等）列入 number_allowlist 并写理由。

**步骤 2 — 静态检查（脚本）**
```bash
python3 /skills/weekly-skill/scripts/draft_lint.py --draft /app/output/deliverable.md \
  --registry /app/work/evidence_registry.json \
  --out /app/work/lint_report.json --report /app/output/lint_report.md
```

**步骤 3 — 门禁裁决（脚本）**
```bash
python3 /skills/weekly-skill/scripts/gate_check.py --lint /app/work/lint_report.json \
  --policy /skills/weekly-skill/references/gate_policy.json \
  --report /app/output/gate_report.md
```
- FAIL：按门禁报告的阻断项清单逐项修复（修草稿或修登记），回到步骤 2；确属误报且经判断可豁免的，把 waiver（规则+行号+理由）写入策略文件副本 `/app/work/gate_policy.json` 并用它重跑——豁免记录留在门禁报告中；
- PASS 或仅剩豁免项：进入步骤 4。

**步骤 4 — 交付**
result.json 按 output_contract 组装：deliverable、lint_report.md、gate_report.md 都放入 /app/output；`change_log` 记录 lint 发现的 error 数与修复轮次；门禁最终 FAIL 的，status=partial 并在 limits 说明哪些项未通过、需要什么才能通过。

**步骤 5 — 自查**
①lint 报告 error=0（或全部有 waiver）；②门禁 PASS；③每个〔C#〕可回溯到登记与 quote；④number_allowlist 每项有理由；⑤result.json 键齐、case_id 原样。

## 异常处理

- 证据登记缺失或结构错误：lint 把未登记标记全部报 CLAIM-UNKNOWN/CITE-ORPHAN——先修登记，不许删除标记逃避检查；
- 材料不足导致数字无法溯源：该句删除或降级为定性表述，并在 uncertainty 说明；不允许把数字留在文中加 waiver；
- 门禁策略文件不可读：退回默认口径（error 全阻断），在 change_log 记录。

## 最小调用示例（合成示例，非正式案例结果）

`examples/input/` 含合成证据登记与两版草稿：`draft_bad.md` 刻意含 4 类硬伤（数字错位、相关写成因果、引文悬空、占位符），`draft_good.md` 为修复后版本。执行：
```bash
python3 scripts/draft_lint.py --draft examples/input/draft_bad.md \
  --registry examples/input/evidence_registry.json --out /tmp/lint.json
python3 scripts/gate_check.py --lint /tmp/lint.json \
  --policy references/gate_policy.json --report /tmp/gate.md
```
对 draft_bad：lint 报 4 error，门禁 FAIL；对 draft_good：lint 0 error，门禁 PASS。真实输出见 `examples/minimal_example.md` 与 `examples/output/`。

## 限制与维护

- lint 是确定性词表与字符串匹配：数字等价写法（1.8 vs 1.80）会触发告警（设计如此），词表外的越级措辞会漏报；模型写作时仍须守强度纪律，lint 是兜底。
- 规则词表与阈值集中在 `draft_lint.py` 顶部常量与 `references/lint_rules.md`；门禁口径集中在 `gate_policy.json`；扩展规则时三处同步。
