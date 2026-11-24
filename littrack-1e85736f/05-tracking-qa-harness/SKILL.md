---
name: tracking-qa-harness
description: >-
  过程质量控制与自评测工具（QA harness）：在「最新文献发现与追踪」类任务中，对一次
  追踪运行产出的 result.json 执行机器可复核的质量门禁——输出契约校验、证据 locator
  逐字段抽查比对、窗口新鲜度与防旧文重报、质量指标计算、汇总诚实 QA 报告。
  触发场景：追踪运行已完成、交付 result.json 之前的自检与修复闭环；评测方复核
  产出可信度。边界：本 Skill 不生产追踪结果本身（不做增量判定、窗口规划、提醒策略、
  重试编排），只对已有产出做验证、量化并指导修复。差异化能力：每个断言都能经
  locator（文件 + JSON 路径）回溯到固化的源材料，全程离线、仅标准库、零网络、
  不编造任何 DOI 或元数据，fail 时给出逐条阻断项。
---

# tracking-qa-harness：追踪产出的质量控制与自评测

## 1. 适用场景与边界

**适用场景（触发条件）**

- challenge-1e85736f「最新文献发现与追踪」类任务：案例材料为组织方本地固化的
  Crossref / Europe PMC / 出版商 API 题录响应、参考图谱，以及"本地增量导入状态"
  快照（previous_snapshot）；你（或上游流程）已经组装出一份候选 result.json，
  需要在交付前做机器可复核的自检；
- 需要对"别人/别的流程产出的追踪结果"做独立复核（评审、复跑、验收）；
- 需要量化一次追踪运行的质量：窗口覆盖率、去重失败率、提醒精确率、隔离率、
  locator 可解析率。

**硬性边界（本 Skill 做什么、不做什么）**

| 做 | 不做（属于其他方向） |
|---|---|
| 校验 result.json 是否满足 case.json 的 output_contract | 增量判定本身（决定哪些记录算"新增"） |
| 解析 locator 并逐字段比对源材料 | 窗口规划（窗口起止、粒度、时区策略） |
| 核验窗口归属与防旧文重报 | 提醒策略（提醒谁、何时提醒、通道选择） |
| 计算质量指标并汇总 QA 报告 | 重试编排（失败任务的重跑调度） |
| fail 时列出阻断项并指导修复闭环 | 生产追踪结果本身（new_items 的生成） |

**数据纪律**：全程离线，脚本永不发起网络请求；不得编造 DOI、元数据、检索结果；
result.json 中任何字段值必须来自案例材料，并附 locator（`文件#/json/pointer`）供复核。

## 2. 运行环境与输入定位兜底

- 运行环境：Python 3（**仅标准库**，本 Skill 全部脚本零第三方依赖）；模型只做判断
  与写作，确定性工作全部交给脚本；运行预算约 64 次模型请求 / 900 秒——除必要的
  修复判断外，不要为脚本能做的事消耗模型请求。
- 平台约定：Skill 安装在 `/skills/weekly-skill`，案例输入在 `/input/case.json` 与
  `/input/task.md`，工作目录 `/app/work`，最终写 `/app/output/result.json`。
- **不要假设固定布局**。上手先用 find 定位输入（兜底顺序：显式路径 → 常见目录 → 全盘浅搜）：

```bash
find /input /app /skills /tmp -maxdepth 4 \( -name 'case.json' -o -name 'task.md' \
  -o -name 'previous_snapshot*.json' -o -name '*snapshot*.json' \) 2>/dev/null
find /input /app -maxdepth 5 -name '*.json' -path '*material*' 2>/dev/null
```

- 定位不到 case.json 时：检查 `/input`、`/app/work`、当前目录；仍无则在 result.json 中
  `status: "partial"` 并说明"未找到 case.json，QA 门禁无法执行"。
- 材料目录（题录响应、快照）通常由 case.json 的 `materials` 字段声明（相对 case.json
  所在目录）；未声明时，在 case.json 同级及 `materials/`、`data/`、`snapshots/`
  子目录中探测。locator 解析根目录（`--base`）缺省为 result.json 所在目录。

## 3. 编号工作流程（案例求解闭环）

QA 在**追踪运行之后、交付之前**执行；但本 Skill 必须支撑完整案例求解闭环。

**步骤 0 — 定位与通读输入。** 用上面的 find 定位 `case.json`、`task.md`、materials、
previous_snapshot。读取 case.json：`case_id`、`output_contract`（交付字段清单）、
`window`（窗口起止）、`materials`（材料清单）。读取 task.md 明确任务目标。

**步骤 1 — 执行追踪主链（产出候选 result.json）。** 本 Skill 不实现增量判定；
按 task.md 要求，用脚本（可复用本包 `qa_lib.py` 的题录适配器：crossref/europepmc
DOI/标题/日期/作者提取、日期窗口判定、snapshot DOI 集合）或一次性 Python 脚本完成：
遍历源题录 → 取窗口内记录 → 与 previous_snapshot 去重 → 为每条新增生成 locator
（`材料相对路径#/json/pointer`）。得到候选 `candidate_result.json`。

**步骤 2 — QA 门禁 1：输出契约校验。**

```bash
python3 /skills/weekly-skill/scripts/contract_validate.py \
  --case /app/work/case.json --result /app/work/candidate_result.json \
  --out /app/work/qa/contract_validate.json
```

校验 case_id 一致、output_contract 全部字段存在且非空、类型正确。缺字段即 fail
并逐个列出。退出码：0=pass / 2=warn / 1=fail。

**步骤 3 — QA 门禁 2：证据 locator 抽查。**

```bash
python3 /skills/weekly-skill/scripts/evidence_spotcheck.py \
  --result /app/work/candidate_result.json --base /app/work \
  --out /app/work/qa/evidence_spotcheck.json
```

对 `new_items` 每条解析 locator 并逐字段比对源记录：DOI（必须一致）、标题
（近似记 warn）、日期（同年月记 warn）、首作者（warn 级）。locator 不可解析即 fail。

**步骤 4 — QA 门禁 3：新鲜度与防旧文重报。**

```bash
python3 /skills/weekly-skill/scripts/freshness_check.py \
  --case /app/work/case.json --result /app/work/candidate_result.json \
  --out /app/work/qa/freshness_check.json
```

每条日期必须落在窗口内（窗口外且无 `backfill: true` 标记 → fail）；DOI 不得出现在
previous_snapshot（旧文重报 → fail）；result 内部不得有重复 DOI。

**步骤 5 — 质量指标。**

```bash
python3 /skills/weekly-skill/scripts/metrics.py \
  --case /app/work/case.json --result /app/work/candidate_result.json \
  --spotcheck /app/work/qa/evidence_spotcheck.json \
  --freshness /app/work/qa/freshness_check.json \
  --out /app/work/qa/metrics.json
```

计算窗口覆盖率（宽松/严格）、去重失败率、提醒精确率、隔离率、locator 可解析率
（定义见 `references/metrics-definition.md`）。不可计算的指标输出 null 并说明原因。

**步骤 6 — 汇总 QA 报告。**

```bash
python3 /skills/weekly-skill/scripts/qa_report.py \
  --case /app/work/case.json --result /app/work/candidate_result.json \
  --reports /app/work/qa/contract_validate.json /app/work/qa/evidence_spotcheck.json \
            /app/work/qa/freshness_check.json /app/work/qa/metrics.json \
  --out-json /app/work/qa/qa_report.json --out-md /app/work/qa/qa_report.md
```

overall_status 取各门禁最差：fail > warn > pass。fail 时 `blocking_items` 逐条列出
阻断项（tool / id / message / locator）。

**步骤 7 — 修复闭环。** 对每条阻断项做最小修复（修 locator、移除窗口外/重复条目、
补漏报、补契约字段），得到修正版 result.json，然后**从步骤 2 重跑全部门禁**。
循环直至 overall_status = pass（或仅剩可解释的 warn）。

**步骤 8 — 组装并交付。** 最终 `/app/output/result.json` 必须包含：
`case_id` + case.json output_contract 列出的全部字段 + `sources`（材料清单）+
`uncertainty`（不确定项，含全部 warn 与不可计算指标的原因）+ `change_records`
（变更记录；**把 QA 结论写进来**：overall_status、报告路径、每轮修复摘要，或放入
专门的 `qa` 字段）。QA 报告文件一并保留在 `/app/work/qa/`（或复制到 `/app/output/`）
供复核。

## 4. 输出契约

QA harness 自身产出（每次运行）：

| 文件 | 内容 |
|---|---|
| `qa/contract_validate.json` | 门禁 1 报告（pass/fail/warn + 逐条检查） |
| `qa/evidence_spotcheck.json` | 门禁 2 报告（每条 locator 与逐字段比对） |
| `qa/freshness_check.json` | 门禁 3 报告（窗口归属 / 快照去重 / 内部重复） |
| `qa/metrics.json` | 指标值 + 不可计算项原因 |
| `qa/qa_report.json` / `qa/qa_report.md` | 汇总报告：overall_status、gates、blocking_items、warnings、metrics、uncertainty、verdict |

交付的 result.json：含 `case_id` + output_contract 全部字段 + `sources` +
`uncertainty` + `change_records`；部分完成时 `status: "partial"` 并说明限制。

## 5. 异常处理与诚实 partial

- **case.json 缺失/损坏**：无法执行门禁 → result.json `status: "partial"`，
  uncertainty 说明"契约校验、新鲜度核验未执行"，仍交付已完成部分。
- **materials 缺失**：证据抽查退化为"locator 不可解析"批量 fail——此时区分是
  result 错了还是材料路径错了：先用 find 确认材料真实位置，修正 `--base` 后重跑。
- **previous_snapshot 缺失**：freshness_check 记 warn 并跳过去重检查；
  必须在 uncertainty 披露"旧文重报风险未排除"。
- **日期精度不足**（源记录只有年份）：按 warn 处理，不硬 fail，但写入 uncertainty。
- **任何指标不可计算**：输出 null + 原因，绝不编造数字。
- 修复循环超过 3 轮仍有阻断项：停止循环，`status: "partial"`，在 change_records
  如实记录剩余阻断项与已尝试的修复。

## 6. 最小调用示例

bundle 自带合成示例（`examples/minimal/`，全部数据虚构并标注 synthetic）：
`candidate_result.json` 故意埋 3 处错误（locator 指向不存在的记录、日期落在窗口外、
已在 previous_snapshot 中出现），QA harness 全部检出；`fixed_result.json` 演示全 pass。

在 bundle 根目录一键运行（端到端，产物写入 `examples/minimal/output/`）：

```bash
cd /skills/weekly-skill   # 或本 bundle 实际安装位置
python3 scripts/run_minimal_example.py
```

期望输出：candidate 轮 overall=fail 且 3 处埋错全部检出（阻断项 ≥3）；
fixed 轮 overall=pass；脚本退出码 0。详见 `examples/minimal/README.md`。

## 7. 与其他方向的边界划分

- **增量判定方向**负责决定"哪些是新增"；本方向只在事后核验其产出是否正确、
  可回溯、未重报——即使 QA 全 pass，也不证明增量判定算法本身最优，只证明
  本次产出通过质量门禁。
- **窗口规划方向**负责窗口起止与滚动策略；本方向只读取 case.json 给定的窗口
  做归属核验，不修改窗口。
- **提醒策略方向**负责提醒的组织与投递；本方向只对照投递记录计算一致性指标。
- **重试编排方向**负责失败任务的重跑调度；本方向的"修复闭环"只针对 result.json
  的内容修复，不调度任何外部任务重试。
