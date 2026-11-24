---
name: proposal-schedule-oracle
description: |
  阶段计划可计算可行性裁定器（Schedule Feasibility Oracle）。重心在上游「排得开」：把开题报告的技术路线编译为计划 JSON（任务/里程碑/资源约束 schema），经编译门（结构校验 + 依赖图 DAG 检测：成环、悬空依赖、无编制角色、里程碑无交付物一律拦截）与裁定门（CPM 前向/后向 pass：关键路径与总时差、总工期 vs 给定周期、逐月经费 vs 总预算、逐月人力 vs 人员编制、资源窗口、可并行任务组）两级门控，全部判定落盘为机器裁定报告 feasibility_report.json；开题稿阶段计划章节只写经裁定通过的排期，超期/超载/超支裁定直接作为风险章节触发信号的量化依据。
  触发：task.md 要求技术路线与阶段计划、给定周期/经费/人员约束、需要验证里程碑落在条件内时。不触发：引文核验、研究缺口综述、语言润色、全文代写。
  Trigger: computable schedule feasibility — plan schema, DAG compile gate, CPM critical path with budget/staffing/window verdicts, machine feasibility report. Not for: citation verification, gap review, language polish, ghostwriting.
---

# 阶段计划可行性裁定器（Proposal Schedule Oracle）

## 0. 定位与差异化

本 Skill 的重心是**阶段计划的可计算可行性**：开题计划最常见的失败是拍脑袋排期——
里程碑超出给定周期、任务量与人员/经费不匹配、依赖成环。本管线把计划变成可计算对象：

1. 技术路线编译为计划 JSON（`references/plan_schema.md`：TASK/MLS/资源约束）；
2. `plan_compile.py` 编译门：结构 + 依赖图 DAG 校验，坏结构直接拦截；
3. `cpm_check.py` 裁定门：关键路径、总工期 vs 周期、逐月经费 vs 预算、逐月人力 vs
   编制、资源窗口，全部判定写入 `feasibility_report.json`；
4. 裁定 fail 时按压缩建议（关键路径上可并行/可裁剪任务）改计划、迭代至全过；
5. 开题稿阶段计划章节只写经裁定通过的排期（附关键路径与余量说明），风险章节
   引用超期/超载裁定作为触发信号依据。

## 1. 运行时契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`、`/input/task.md` 先读；`case.json.output_contract` 逐字段抄录到 result.json，不凭题目猜。 |
| 工作目录 | `/app/work`（plan.json、compile/feasibility 中间报告）。 |
| 最终交付 | `/app/output/result.json`（含 `case_id` 与全部契约字段）、`feasibility_report.json`、排期摘要；阶段计划章节引用之。 |
| 预算 | 64 次模型请求 / 900 秒 / 16384 tokens 每响应。尽早写有效 partial result.json。 |
| Skill 安装路径 | `/skills/weekly-skill`；路径不同时替换命令前缀。 |
| 材料读取 | 读真实文件（PDF 用 `pdftotext -layout`）；约束数值必须有 case/task 原文依据，推断值记 uncertainty。 |

## 2. 必需工作流（禁止跳步）

### 步骤 0 — 读契约，立即写有效 partial result.json
读 `/input/case.json` 与 `/input/task.md`，然后：
```
python3 /skills/weekly-skill/scripts/resultkit.py init /input/case.json /app/output/result.json
```

### 步骤 1 — 抽取资源约束
从 case.json 的 constraints（优先）与 task.md 文本抽取：周期总月数、人员角色与编制、
总经费、设备/数据可得性窗口。文本抽取的数值在 result.json `uncertainty` 登记出处；
材料未给的约束不得臆造，缺省值须标注。

### 步骤 2 — 编译计划 JSON
按 `references/plan_schema.md` 把技术路线编译为 `/app/work/plan.json`：每个环节一个
TASK（人日工期、依赖、角色、经费、窗口），每个考核节点一个 MLS（交付物 + 考核方式
非空）。工期估算写明依据（材料成本/工作量注记、同类经验），悲观取值。

### 步骤 3 — 编译门：结构与 DAG 校验
```
python3 /skills/weekly-skill/scripts/plan_compile.py /app/work/plan.json /app/work/compile_report.json
```
退出码非 0 时按 `problems` 逐条修复（成环重理依赖、悬空补任务、角色换有编制的、
里程碑补交付物），直到通过。

### 步骤 4 — 裁定门：CPM 可行性计算
```
python3 /skills/weekly-skill/scripts/cpm_check.py /app/work/plan.json /app/work/feasibility_report.json
```
`feasible:false` 时读 `compression_suggestions`（关键路径上 parallelizable/trimmable
任务）与超载/超支明细，回到步骤 2 调整：压缩关键路径、重排依赖消除超载月份、
削减经费或申请追加。迭代至退出码 0。**不得改裁定报告冒充通过。**

### 步骤 5 — 写稿与收尾
- 阶段计划章节：只写通过裁定的排期，给出关键路径、各任务总时差、周期余量
  （= 周期 − 总工期）、逐月人力/经费表的摘要；
- 风险章节：把裁定信号量化为触发信号（如「注释任务工期上浮 20% 即超期」
  「第 X 月人力已达编制上限，任何插单即超载」）并给出备选方案；
- 填契约字段并收尾：
```
python3 /skills/weekly-skill/scripts/resultkit.py set /app/output/result.json schedule '<JSON 或 @文件>'
python3 /skills/weekly-skill/scripts/resultkit.py final /app/output/result.json
```
缺项被 final 强制 partial 并点名——保持诚实，不得删 uncertainty 充数。

## 3. 异常处置

| 情况 | 处置 |
|---|---|
| 材料缺失（无周期/经费/人员约束） | 以 task.md 原文数字为准；全无则在 uncertainty 声明「约束缺失」，按常见学制/项目规模给默认并标注，不得当事实引用 |
| 材料乱码/PDF 不可解析 | pdftotext 重试 `-layout`/`-raw`；仍乱码则该材料仅作存在性记录，约束改从 case.json 取，记 uncertainty |
| 周期过短（压缩建议用尽仍超期） | 如实保留 `feasible:false`，在 result.json 与风险章节写明超出量与「需申请延期/砍范围」，**禁止**通过虚减人日蒙混 |
| 指标不可达（窗口与依赖冲突，如测序窗口早于样本就绪） | 调整 earliest_start 或重排依赖；物理上不可调和时在 uncertainty 点名该窗口矛盾 |
| 预算不足 | 先裁 trimmable 低优先级任务；仍超支则 fail 并写明超支额与追加申请建议，不得把超支改写为通过 |
| 角色无编制 | plan_compile 拦截 `role_not_staffed`；改用有编制角色或在计划中说明借调依据 |
| 重复运行 | 脚本幂等，同名报告覆盖；resultkit 的 change_records 追加不覆盖 |

## 4. 交付前自查清单

- [ ] plan_compile 退出码 0（无环、无悬空依赖、里程碑均有交付物）
- [ ] cpm_check 退出码 0：总工期 ≤ 周期、累计经费 ≤ 预算、无超载月份、无窗口违例
- [ ] feasibility_report.json 落盘 /app/output；关键路径与余量写入阶段计划章节
- [ ] 每个里程碑挂到 TASK 且考核方式非空；里程碑日期与 CPM 计算一致
- [ ] 风险章节触发信号引用了裁定数值（超期量/超载月份/超支额），非泛泛而谈
- [ ] result.json 契约字段齐备或诚实 partial（缺项在 uncertainty 点名）

## 5. 最小示例

`examples/`：**合成示例**（非正式案例）。单细胞转录组解析肿瘤微环境
（24 个月、2 名研究生、30 万元）。`bash examples/run_example.sh` 演示：
坏结构计划被编译门拦截 → 预制计划（关键路径 26 个月、第 21–22 月人力超载）
被裁定门 fail 并给出压缩建议 → 修复后计划两级门控全过 → 诚实 partial 的
result.json。`expected/` 为真实执行输出，以未修复版的拦截报告为主展示。
