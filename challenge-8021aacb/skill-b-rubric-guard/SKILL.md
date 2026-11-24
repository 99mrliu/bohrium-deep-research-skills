---
name: six-dim-rubric-guardian
description: |
  六维结构缺陷的判据工程管线（Rubric-Gated Six-Dimension Diagnosis）。重心不在文本处理机械，而在「诊得准」的判定质量：为研究问题/章节结构/论证链/段落关系/重复内容/结论边界六维各配缺陷子类与合取式纳入条件，用误报控制手册把结构缺陷与风格偏好严格分开，再用覆盖门机器检查六维无缺、finding 字段齐全、空话建议清零。线索扫描只产候选位点，立案与否必须过判据。
  触发：task.md 要求论文/稿件结构诊断且强调定位准确、不得虚构缺陷时。不触发：语言润色、语法校对、科学内容裁决、查重。
  Trigger: rubric-gated structural diagnosis with false-positive control (structural defect vs style preference discrimination) and six-dimension coverage gate. Not for: language polish, grammar, scientific-correctness adjudication.
---

# 六维判据守卫（Six-Dim Rubric Guardian）

## 0. 定位与差异化

本 Skill 的重心是**判据工程**：基础 Agent 做结构诊断的典型失效是两类——给一堆放之四海皆准的写作原则（诊不准），或把风格偏好当结构错误（误报）。本管线用三层判据解决：

1. **分类法**（`references/taxonomy_six.md`）：六维 × 缺陷子类 × 合取式纳入条件——不满足全部纳入条件不立案；
2. **误报手册**（`references/false_positive_playbook.md`）：立案/排除对照例 + 可证伪表述要求 + 空话黑名单；
3. **覆盖门**（`scripts/coverage_gate.py`）：机器检查六维无缺、字段齐全、空话清零，退出码可阻断交付。

诊断 judgment 由 Agent 在真实稿件文本上作出；本 Skill 保证**每条立案都过判据、每个维度都有交代**。

## 1. 运行时契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`、`/input/task.md` 先读；`case.json.output_contract` 逐字段抄录到 result.json，**不凭题目猜字段**。 |
| 工作目录 | `/app/work`（抽取文本、候选扫描、诊断中间稿）。 |
| 最终交付 | `/app/output/result.json`（含 `case_id` 与全部契约字段）、`diagnosis.json`、`coverage_report.json`、`editing_plan.md`。 |
| 预算 | 64 次模型请求 / 900 秒 / 16384 tokens 每响应。先播种有效 partial，再填充。 |
| Skill 安装路径 | `/skills/weekly-skill`；路径不同时相应替换命令前缀。 |
| 材料读取 | 读真实文件（PDF 用 `pdftotext -layout`）；不可读部分如实记入 uncertainty，不猜内容。 |

## 2. 必需工作流（禁止跳步）

### 步骤 0 — 播种契约骨架
```
python3 /skills/weekly-skill/scripts/contract_seed.py /input/case.json /app/output/result.json /app/work/diagnosis.json
```
result.json 立即有效（partial）；diagnosis.json 六维 clearance 容器就位，缺维从第一分钟就可见。

### 步骤 1 — 抽取稿件文本
把稿件抽成纯文本 `/app/work/ms.txt`（md/txt 直读；PDF 用 pdftotext；docx 按 zip+xml 容错）。记录行号基线；乱码/截断/不可读入 uncertainty。

### 步骤 2 — 线索扫描（只产候选）
```
python3 /skills/weekly-skill/scripts/dimension_scan.py /app/work/ms.txt /skills/weekly-skill/references/cue_lexicon.json /app/work/candidates.json
```
输出按维度分组的候选位点。**候选 ≠ 缺陷**；命中率低的维度不等于无缺陷，仍需精读。

### 步骤 3 — 逐维裁定（判据是核心）
对每一维：结合候选位点定向精读 + 全文通读，按 taxonomy_six.md 的纳入条件逐条裁定：
- 立案 → finding：`id/dimension/location(章节+段落)/quote(逐字)/defect_class(子类名)/action(可执行编辑动作)/severity/rationale(闭环影响)`；
- 排除 → 在该维 `dimension_clearance` 记「候选 X 条，立案 Y 条，排除理由」，无候选时记「全文通读 + 检查方式」。
- action 禁止空话（黑名单见 false_positive_playbook.md），必须是移动/合并/拆分/收窄/删重/补过渡/补限制 + 位置。

### 步骤 4 — 覆盖门（不过门不交付）
```
python3 /skills/weekly-skill/scripts/coverage_gate.py /app/work/diagnosis.json /app/output/coverage_report.json
```
退出码非 0 时按 `problems` 逐条修复重跑，直到 `gate_pass: true`。把通过的 diagnosis.json 复制到 `/app/output/`，据 findings 写 `editing_plan.md`（按 severity 排序，每条指回 finding id 与位置）。

### 步骤 5 — 收尾 result.json
填契约字段；`status`：六维过门且契约字段齐 = `ok`，否则 `partial` 并在 uncertainty 点名缺项；`change_record` 记录每轮门控修复。

## 3. 异常处置

| 情况 | 处置 |
|---|---|
| 材料不可读/截断 | 受影响维度 clearance 注明「无法完成检查 + 原因」，result 降 partial |
| 通读后某维确无缺陷 | clearance 必须写 how_checked（通读范围 + 排查的候选数），空 clearance 视同缺维 |
| 候选位点爆炸（>200） | 按 severity 子类优先级裁定，未裁定候选在 uncertainty 如实交代 |
| 预算不足 | 优先 high 子类（RQ 悬空、论证断裂、结论超界），其余如实 partial |

## 4. 自查清单

- [ ] coverage_gate 退出码 0 且报告归档
- [ ] 每条 finding 的 defect_class 是 taxonomy 子类名而非「结构问题」
- [ ] 每条 action 含操作动词与位置，无黑名单空话
- [ ] 六维 clearance 均有 how_checked
- [ ] result.json 契约字段齐、status 诚实

## 5. 最小示例

`examples/`：**合成示例**（非正式案例）。`bash examples/run_example.sh` 端到端演示播种→扫描→覆盖门（含故意触发的空话拦截与缺维拦截）；`expected/` 为真实跑出的示意输出。
