---
name: source-reconcile-first
description: 上游数据真实性优先的多步骤数据分析规程。在任何清洗/统计/绘图之前，先用 source_audit.py 对 /input 的全部数据文件做哈希存证、字段画像与逐单元格双源对账（CSV×SQLite×Excel），按公开规则裁决分析主源；此后所有下游产物必须引用审计结论，result.json 的 sources 直接来自审计哈希。适用于案例同时提供同一数据集的多个来源（快照+数据库）、要求核对字段一致性并交付可复核结果的科研表格分析任务（如 UCI Concrete/Iris/Wine 双源案例）。
---

# Source-Reconcile-First —— 先证明数据是真的，再谈分析

核心主张：**多源案例的最大风险不是算错，而是算了一份未经核验的数据。**
本 Skill 把"数据来源真实性"作为一等交付物：`scripts/source_audit.py` 在分析前产出
带哈希、逐单元格差异定位和主源裁决的 `source_audit.json/.md`；后续每个阶段都必须
引用它。重心在上游对账；下游统计/绘图按本规程的通用要求完成，全部数字以审计过的
主源为唯一依据。

## 运行契约（评测环境）

- 输入：`/input/case.json`（含 `case_id` 与 `output_contract.fields`）、`/input/task.md`、数据文件。
- 工作目录 `/app/work`；最终产物全部入 `/app/output`，含 `result.json`。
- `result.json` 必须含：原样 `case_id`、**全部** `output_contract` 字段（典型为
  `cleaned_data, statistics, figures, report, quality_evidence, exceptions`）、
  `status`、`sources`、`uncertainty`。先保 partial，再增强，最后 seal。
- 预算 64 次请求 / 900 秒：本规程全流程约 8–12 次请求，不要展开无必要的逐列手工探索。

## 流程（顺序执行，不要跳步）

**0. 读题与保底 partial（1 次请求内完成）**

读 `/input/case.json` 与 `/input/task.md`，记录 case_id、契约字段名、任务特别要求
（如"找出区分度最强的指标"）。立即：

```
python3 /skills/weekly-skill/scripts/result_ledger.py init --case /input/case.json --out /app/output/result.json
```

**1. 上游审计（本 Skill 的重心）**

```
python3 /skills/weekly-skill/scripts/source_audit.py --input /input --case /input/case.json --out /app/work
cp /app/work/source_audit.json /app/work/source_audit.md /app/output/
```

读打印的摘要行与 `source_audit.md`。裁决规则全文见 `references/reconciliation_rules.md`：

- 全部对账 `content_identical` → 采用裁决主源，报告中一句话声明一致性及双方哈希。
- 任何 `*_divergent` → **禁止直接分析**：打开 JSON 定位差异列/差异行示例，结合
  task.md 判断是单位、精度、行序还是快照截断问题；在报告与 `uncertainty` 中如实写明，
  再按 §4 得分规则选定主源继续。
- materials 声明缺失文件 → 记为案例材料异常（`result_ledger.py note`），不猜测顶替。

把 `source_audit.md` 内容并入最终报告的"数据来源与一致性"一节。

**2. 清洗（基于主源，规则先行）**

用 pandas 写一段短脚本处理主源表，规则与口径写进 `/app/work/cleaning_log.json`
（每条规则：`rule, predicate, rows_in, rows_out, rows_affected`）：

- 完全重复行：保留首条，删除其余，记录删除数（Concrete 原始数据确有重复行）。
- 缺失：数值列缺失率 ≤5% 中位数填补并记录；>5% 不填补，保留并标记。
- 异常值：1.5×IQR **只标记不删除**，输出 `outlier_flags.csv`。
- 清洗后表写 `/app/output/cleaned_data.csv`，并核对 `rows_in − rows_out = Σ各规则删除数`。

**3. 统计（按任务要求选方法，前提先行）**

- 组间差异（Iris 4 指标 × 3 种；Wine 13 指标 × 3 类）：每组每指标先 Shapiro-Wilk
  正态性 + Levene 方差齐性；全满足→单因素 ANOVA + Bonferroni 两两比较；任一不满足
  →Kruskal-Wallis + Dunn（Bonferroni）。报告每个检验的 p、效应量（η² 或 ε²）、
  前提检验结论。多指标族必须声明多重比较控制（Bonferroni α=0.05/m）。
- 连续目标（Concrete 强度）：Spearman 相关 + 标准化 OLS（报告 β、R²、VIF、
  残差正态性），说明相关≠因果。
- 区分度排序（Wine）：按单指标 η²（或 Kruskal H）降序给出 Top 指标表。
- 结果写入 `/app/output/statistics.json`（结构化：每个检验一条记录，含前提、方法、
  p、效应量、样本量）。

**4. 可视化（matplotlib，Agg，150dpi PNG → `/app/output/figures/`）**

- 组间分布：分组箱线图+散点叠加（每指标一幅或拼接面板）。
- 关联总览：Spearman 相关热图。区分度排序：横向条形图。
- 每幅图登记 `figures_manifest.json`：`file, intent, source_table, columns, aggregation`。
- 坐标轴不得截断误导；聚合层级与底层数据一致。

**5. 报告与封口**

`/app/output/report.md` 结构：①数据来源与一致性（并入 source_audit.md）②清洗规则与
行数会计 ③统计结果（前提→方法→p→效应量）④图目录 ⑤结论 ⑥异常与不确定性。
报告中的每个数字必须能在 `statistics.json` / `cleaning_log.json` / `source_audit.json`
中找到同源值，禁止凭记忆回填。

```
python3 /skills/weekly-skill/scripts/result_ledger.py fill --out /app/output/result.json \
  --set cleaned_data=/app/output/cleaned_data.csv --set statistics=/app/output/statistics.json \
  --set figures='["/app/output/figures/xxx.png"]' --set report=/app/output/report.md \
  --set quality_evidence='["/app/output/source_audit.json","/app/work/cleaning_log.json","/app/output/figures_manifest.json"]' \
  --set exceptions="异常说明文本或 JSON"
python3 /skills/weekly-skill/scripts/result_ledger.py seal --case /input/case.json --out /app/output/result.json --status success
```

seal 拒绝时：修复空缺；确实无法补齐的用 `note` 写明原因，以 partial 诚实交付。

## 异常处置表

| 情形 | 处置 |
|-|-|
| 双源对账不一致 | 不分析、先定位；写入 uncertainty；按得分规则选主源并在报告声明 |
| 无 pandas | 本 Skill 不可用，退回手工分析并把该限制写入 uncertainty |
| SQLite 打不开 | 记为来源异常，以 CSV 快照为主源继续（若有），uncertainty 声明 |
| 列名与 task.md 提到的目标列不符 | 以实际列名为准，报告中说明映射（禁止按标签臆造列） |
| scipy 不可用 | 描述统计与清洗照常；推断检验标注"不可用"，保持 partial 并说明 |
| seal 校验失败 | 按提示补齐；无法补齐 → partial + uncertainty |

## 资源

- `scripts/source_audit.py` — 上游审计引擎（本重心）。
- `scripts/result_ledger.py` — result.json 契约记账（init/fill/note/seal，sources 自动取自审计哈希）。
- `references/reconciliation_rules.md` — 对账容差、裁决等级、主源得分规则的完整条款。
- `examples/make_example.py` + `examples/README.md` — 合成示例（双源植入差异，端到端跑通审计与封口）。

## 边界与不适用

- 行序敏感的对账是刻意设计（见规则 §6）；行序不同属来源不一致，须先说明再处理。
- 本 Skill 不做多因素交互/协变量模型；案例若明确要求，声明超出范围。
- 文本/NLP 列只画像不分析。
