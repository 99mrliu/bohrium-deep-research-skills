# 阶段计划 JSON Schema（proposal-schedule-oracle 核心资源）

开题报告的阶段计划必须编译为**可计算对象**后方可裁定可行性。本 schema 是
`plan_compile.py`（结构/DAG 校验）与 `cpm_check.py`（关键路径/经费/人力裁定）的共同输入契约。
任何字段缺失或违例，计划在编译期即被拦截，不进入裁定阶段。

## 1. 顶层结构

```json
{
  "plan_id": "字符串，计划标识",
  "constraints": { "见第 2 节" },
  "tasks": [ "见第 3 节" ],
  "milestones": [ "见第 4 节" ]
}
```

## 2. 资源约束 `constraints`

| 字段 | 类型 | 说明 |
|---|---|---|
| `period_months` | 正数 | 给定周期总月数（如 24）。CPM 总工期超过它即判超期 fail |
| `staff` | 对象 | 角色 → 在编人数（正整数），如 `{"研究生": 2}`。任务的 `required_role` 必须在此有编制 |
| `total_budget_cny` | 正数 | 总经费（元）。全部任务 `cost_cny` 之和超过它即判超支 fail |
| `resource_windows` | 对象，可缺省 | 窗口名 → `[起始月, 截止月]`（1 起算、含端点），刻画设备/数据可得性窗口；任务经 `requires_window` 引用 |

约束来源：`case.json` 的结构化约束优先；缺失时从 `task.md` 文本抽取（周期、人员、经费的
数字必须有原文依据），抽取值一律在 result.json 的 `uncertainty` 登记来源。

## 3. 任务 `TASK`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | 字符串 | 唯一，建议 `T01…` 顺序编号 |
| `name` | 字符串 | 任务名称（可证伪、对应技术路线的一个环节） |
| `duration_person_days` | 正数 | 工期（人日）。按 21 人日/月折算 |
| `depends_on` | 数组 | 前置任务 id 列表，无前置为 `[]`；引用必须存在（悬空 fail）、不得成环（成环 fail） |
| `required_role` | 字符串 | 执行角色，须在 `constraints.staff` 中有编制 |
| `cost_cny` | 非负数 | 经费估算（元），在执行区间内逐月均匀摊销 |
| `assigned_workers` | 正整数，缺省 1 | 实际投入人数；有效工期（月）= 人日 / (21 × assigned_workers)；不得超过该角色编制 |
| `earliest_start_month` | 正数，缺省 1 | 最早开始约束（1 起算），CPM 前向 pass 的下界 |
| `parallelizable` | 布尔，缺省 false | 可由多人分摊：压缩建议允许提高 `assigned_workers` |
| `trimmable` | 布尔，缺省 false | 范围可裁剪（如缩减样本量）：压缩建议允许缩短人日 |
| `requires_window` | 字符串或 null，缺省 null | 引用 `resource_windows` 的窗口名；任务执行区间必须整体落入窗口，否则裁定 fail |

## 4. 里程碑 `MLS`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | 字符串 | 唯一，建议 `M1…` |
| `task_id` | 字符串 | 挂接的任务 id，必须存在；里程碑随该任务完成而达成 |
| `deliverable` | 字符串 | 交付物，**非空**，缺失即 fail（无交付物的里程碑不可考核） |
| `assessment` | 字符串 | 考核方式，**非空**（如「≥30 例样本入库」「报告经导师组评审」） |

## 5. 两级门控语义

1. **编译门（plan_compile.py）**：schema 结构、字段类型、角色编制、悬空依赖、DAG 无环、
   里程碑交付物。任何问题 → `valid:false`，退出码 1，报告逐条 `problems`。
2. **裁定门（cpm_check.py）**：在编译通过的计划上做前向/后向 pass，输出
   `feasibility_report.json`：关键路径与总时差、总工期 vs `period_months`（超期 fail，
   给出超出量与压缩建议 = 关键路径上 `parallelizable`/`trimmable` 任务）、逐月经费累计
   vs 总预算（超支 fail）、逐月人力需求 vs 编制（超载月份 fail）、窗口违例（fail）、
   可并行任务组清单。任一 fail → `feasible:false`，退出码 1。

**纪律**：开题稿的「阶段计划」章节只允许写经两级门控通过的排期；裁定未过时必须
先改计划（压缩关键路径、消除超载、削减经费），不得改裁定。裁定信号（超期量、超载
月份、超支额）是「风险与备选」章节触发信号的法定依据。
