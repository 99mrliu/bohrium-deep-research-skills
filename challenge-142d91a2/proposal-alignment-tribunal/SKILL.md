---
name: proposal-alignment-tribunal
description: |
  七要素对齐的判据工程管线（RQ-OBJ-STEP-VAL-OUT-RSK Alignment Tribunal）。重心不在文字生成，而在「对得上」：开题稿最常见失败是各写各的——目标不与问题对应、技术路线不服务任何目标、预期成果无法考核、指标阈值无依据。本管线把研究问题/目标/步骤/验证/成果/风险六表收敛为一张对齐矩阵作为单一事实源，用合取式纳入条件机器裁定（孤儿步骤、缺阈值依据、无验证的目标、三连缺风险、悬空引用逐条拦截），矩阵过门后才允许按矩阵展开执笔，从机制上保证各写各的不可能发生。
  触发：task.md 要求撰写开题报告/研究计划书且含研究问题、目标、技术路线、预期成果、风险等多要素对齐要求时。不触发：纯文献综述、语言润色、科学内容正确性裁决、经费审计。
  Trigger: alignment-gated proposal writing (RQ-OBJ-STEP-VAL-OUT-RSK matrix adjudication with orphan-step / unverifiable-objective / dangling-reference interception). Not for: pure literature review, language polish, scientific-correctness adjudication, budget audit.
---

# 开题对齐裁定庭（Proposal Alignment Tribunal）

## 0. 定位与差异化

本 Skill 的重心是**判据工程——「对得上」**。基础 Agent 写开题稿的典型失效不是文笔，
而是要素错配：目标句放之四海皆准（不挂任何可证伪的问题）、技术路线塞进无人考核的
「顺便做」步骤、预期成果只有「发表论文若干」、风险段落只有「积极应对」。四层判据：

1. **矩阵 schema**（`references/alignment_schema.md`）：RQ/OBJ/STEP/VAL/OUT/RSK 六表，
   每个 OBJ 恰有 metric+threshold+threshold_basis+time_point，每个 STEP 必须服务
   ≥1 个 OBJ，每个 RSK 必须有触发信号+备选方案+决策时点；
2. **失败模式手册**（`references/fail_playbook.md`）：六类「各写各的」错配的裁定口径
   与修复动作；
3. **裁定庭**（`scripts/alignment_check.py`）：机器校验合取式纳入条件，逐项 pass/fail
   裁定报告 + 覆盖率统计，退出码可阻断执笔与交付；
4. **契约纪律**（`scripts/contract_result.py`）：result.json init/final，缺项或对齐门
   未过强制 partial。

写作 judgment 由 Agent 作出；本 Skill 保证**先对齐、后成稿、稿句可回查矩阵 id**。

## 1. 运行时契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`、`/input/task.md` 先读；`case.json.output_contract` 逐字段抄录到 result.json，**不凭题面猜字段**。 |
| 工作目录 | `/app/work`（约束抽取、对齐矩阵、裁定报告、草稿）。 |
| 最终交付 | `/app/output/result.json`（含 `case_id` 与全部契约字段）及契约指定的可编辑产物。 |
| 预算 | 64 次模型请求 / 900 秒 / 16384 tokens 每响应。先播种有效 partial，再逐步填充。 |
| Skill 安装路径 | `/skills/weekly-skill`；路径不同时相应替换命令前缀。 |
| 材料读取 | 读真实文件（PDF 用 `pdftotext -layout`）；不可读部分如实记入 uncertainty，不猜内容。 |

## 2. 必需工作流（禁止跳步）

### 步骤 0 — 读契约，立即播种有效 partial
```
python3 /skills/weekly-skill/scripts/contract_result.py init /input/case.json /app/output/result.json
```
result.json 从第一分钟就有效（partial）；契约字段缺位立即可见。

### 步骤 1 — 抽取案例约束
从 task.md 与 case.json 抽取硬约束（周期、经费、人员、材料清单、考核要求）写入
`/app/work/constraints.md`；PDF 材料用 pdftotext 解析。约束缺失入 uncertainty，不编造。

### 步骤 2 — 填对齐矩阵
按 `references/alignment_schema.md` 填 `/app/work/alignment_matrix.json`：
RQ 1–3 个且各含判断标准；每个 OBJ 挂唯一 RQ 并填齐 metric/threshold/threshold_basis/
time_point；STEP 的 serves 非空；每个 OBJ 配 ≥1 条 VAL（含对照与统计判据）与
≥1 个 OUT（含验收判据）；RSK 三连齐全。阈值依据必须锚定前期数据/文献并在
fact_source_map 建条。

### 步骤 3 — 裁定庭（不过门不动笔）
```
python3 /skills/weekly-skill/scripts/alignment_check.py /app/work/alignment_matrix.json /app/work/alignment_report.json
```
退出码非 0 时按报告 `fails` 逐条修矩阵重跑，直至 `gate_pass: true`。
预算不足无法修全时：保留 fail，result 记 honest partial 并在 uncertainty 点名，
**禁止删规则假装通过**。

### 步骤 4 — 按矩阵执笔开题稿
章节从矩阵展开：研究问题章=RQ 表；目标章=OBJ 逐条成段，**每句目标标注对应 id
（如「（对应 OBJ2）」）**；技术路线章=STEP 按 depends_on 拓扑排序；验证与成果章
=VAL/OUT；风险章=RSK 表。稿中不得出现矩阵之外的承诺性目标句。

### 步骤 5 — 收尾一致性回查与 final
逐句检查稿中目标句能在矩阵找到 id（回查失败=稿矩阵不一致，回步骤 3）；填齐契约字段后：
```
python3 /skills/weekly-skill/scripts/contract_result.py final /input/case.json /app/output/result.json
```
字段齐备且对齐门过 = `status:"ok"`；否则强制 partial 并点名缺项。

## 3. 异常处置

| 情况 | 处置 |
|---|---|
| 材料缺失/不可读 | 涉及阈值依据的 OBJ 标 uncertainty（basis 注明「待补」），result 降 partial；不得编造数据 |
| 材料乱码/截断 | 记录受影响字段；能抢救的部分入 fact_source_map 并注明截断位置 |
| 周期过短 | 砍 RQ（保 1 个主问题）与 STEP（孤儿优先删），矩阵重裁定；不得压缩 validation |
| 指标不可达 | 调整 threshold 并在 threshold_basis 写明降级依据；无依据的阈值宁可标 uncertainty |
| 预算不足 | 优先级：RQ-CRIT > OBJ-FIELDS > OBJ-COVER > RSK-FIELDS；未修 fail 如实 partial |
| 重复运行 | init 幂等（重播骨架覆盖）；final 重复执行只追加 change_records，不丢 uncertainty |

## 4. 交付前自查清单

- [ ] alignment_check 退出码 0（或 fail 已如实记入 partial 的 uncertainty）
- [ ] 每个 RQ 有 decision_criterion，每个 OBJ 四字段齐全且 threshold_basis 可溯源
- [ ] 无孤儿 STEP；每个 OBJ ≥1 VAL（含统计判据）且 ≥1 OUT（含验收判据）
- [ ] 每个 RSK 有触发信号+备选方案+决策时点
- [ ] 稿中每个目标句标注并回查到矩阵 id
- [ ] result.json 契约字段齐、status 诚实（ok/partial 有据）

## 5. 最小示例说明

`examples/`：**合成示例**（青藏高原草地样带放牧强度调查，非正式案例结果）。
预制矩阵故意含 1 个无 VAL 的 OBJ、1 个孤儿 STEP、1 个缺触发信号的 RSK，
`bash examples/run_example.sh` 端到端演示三类 fail 的拦截与 honest partial 收尾；
`expected/` 为真实跑出的产物。
