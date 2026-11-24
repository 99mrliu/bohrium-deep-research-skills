---
name: cleaning-ledger-qc
description: 过程质量控制取向的多步骤数据分析规程。清洗被当作复式记账：clean_ledger.py 按固定优先级（结构修复→完全重复→主键冲突→缺失填补→异常只标记）执行并强制核对行数会计恒等式，不平衡即拒绝交付；ledger_check.py 以独立重算复核台账，自报与重算不一致即失败。适用于要求"清洗规则透明、零静默丢数据、每一步可复核"的科研表格案例（如 UCI Concrete/Iris/Wine 的缺失/重复/异常处理与后续统计报告）。
---

# Cleaning-Ledger QC —— 清洗即记账，不平衡即失败

核心主张：**分析链最常见的失真是清洗阶段的静默丢数据。**
本 Skill 把过程质量控制放在重心：每条清洗规则是一条会计分录，台账必须配平；
复核器独立重算，不接受自报。统计与绘图按通用要求完成，但它们的输入必须是
配平台账产出的 cleaned 表，报告中的行数口径一律以台账为准。

## 运行契约（评测环境）

- 输入 `/input/case.json`（`case_id`、`output_contract.fields`）与 `/input/task.md`；
  数据文件在 `/input`。
- 工作于 `/app/work`；交付物入 `/app/output`；`result.json` 含原样 `case_id` +
  全部契约字段 + `status`/`sources`/`uncertainty`，先 partial 后增强。
- 预算约 8–12 次请求。

## 流程

**0. 读题 + 保底 partial。** 读 case.json / task.md，记录契约字段与任务专项要求。
立即写 partial result.json（含 case_id 与空契约字段，status=partial）——可以用任何
方式写，但必须在第一次分析前落盘。

**1. 导入与字段核对。** 用 pandas 读取 `/input` 中的 CSV 与 SQLite
（`pd.read_sql_query('SELECT * FROM <表>', sqlite3.connect(...))`）。若同一数据集有
CSV 与 SQLite 两个来源：逐列比对行数与值，一致则在报告中声明"双源一致"并任选其一
（建议 CSV）；不一致则在 uncertainty 中写明差异列，选用其一并说明理由。表画像
（行列数、dtype、缺失计数）记入 `/app/work/profile.json`。

**2. 清洗（本重心）。** 把待清洗表存为 CSV 后运行：

```
python3 /skills/weekly-skill/scripts/clean_ledger.py --table /app/work/raw_<name>.csv \
    --name <name> --out /app/work
python3 /skills/weekly-skill/scripts/ledger_check.py --table /app/work/raw_<name>.csv \
    --name <name> --work /app/work
cp /app/work/cleaned_<name>.csv /app/output/cleaned_data.csv
```

- 需要主键去重时加 `--key-cols col1,col2`；需要改阈值时提供 `--rules rules.json`
  并把该文件复制到 /app/output 作为证据。
- `clean_ledger.py` 退出码 4 = 台账不平衡：**这是缺陷信号，不是噪声**；检查输入表
  是否被上游改动，修复后重跑，禁止绕过。
- `ledger_check.py` 退出码 5 = 自报与独立重算不一致；同样必须修复后重跑。
- 读 `anomaly_register.json`：watch/critical 条目（缺失率 >5% 的列、异常值 >5% 的列）
  必须原样进入报告"异常说明"和 result.json 的 `exceptions`。

**3. 统计（按任务要求，前提先行）。**

- 组间差异（Iris 4 指标 ×3 种 / Wine 13 指标 ×3 类）：每组先 Shapiro-Wilk + Levene；
  全满足 → ANOVA + Bonferroni 两两比较；任一不满足 → Kruskal-Wallis + Dunn
  （Bonferroni 校正）。报告 p、效应量（η²/ε²）、前提结论；多指标族声明 Bonferroni
  校正后的 α。
- 连续目标（Concrete）：Spearman 相关 + 标准化 OLS（β、R²、VIF、残差正态性）。
- 区分度排序（Wine）：按单指标 η²（或 Kruskal H）降序列出 Top 指标。
- 写入 `/app/output/statistics.json`：每检验一条 {question, premises, method, p,
  effect_size, n, note}。

**4. 可视化。** matplotlib（Agg，150dpi PNG → `/app/output/figures/`）：分组箱线+
散点（组间分布）、Spearman 热图（关联）、横向条形图（区分度排序）。登记
`figures_manifest.json`（file, intent, source_table, columns）。图的数据必须是
cleaned 表，与统计同源。

**5. 报告与 result.json。** `report.md`：①数据与字段核对 ②清洗台账摘要
（初始行→最终行、各规则删除数、填补格数、异常标记数——**只能引用
cleaning_ledger.json 的数字**）③统计结果 ④图目录 ⑤结论 ⑥异常与不确定性。
result.json 填全部契约字段；`quality_evidence` 至少含 cleaning_ledger.json、
ledger_check.json、anomaly_register.json、figures_manifest.json 的路径。
最终自查：契约字段非空、引用路径存在、行数口径与台账一致、异常未静默。
无法满足的字段保持空并写 uncertainty，status=partial。

## 异常处置表

| 情形 | 处置 |
|-|-|
| 台账不平衡（退出码 4） | 检查输入是否被中途改写；修复重跑；禁止手工改台账数字 |
| 复核不一致（退出码 5） | 按 stderr 明细定位规则；修复后重跑两条命令 |
| 输入表无缺失无重复无异常 | 正常：台账全零分录也是完整证据，照常交付 |
| 列全空 | R1 已登记；该列不参与统计，报告中声明 |
| 主键列名写错 | R3 跳过并记 notes；修正后重跑 |
| scipy 不可用 | 描述统计与台账照常；推断检验标"不可用"并 partial |

## 资源

- `scripts/clean_ledger.py` — 规则引擎 + 台账 + 异常登记册（本重心）。
- `scripts/ledger_check.py` — 独立重算复核器。
- `references/rule_priority.md` — 规则优先级论证、会计规则、异常分级阈值。
- `examples/make_example.py` + `examples/README.md` — 合成示例（含篡改台账被抓获演示）。

## 边界与不适用

- 近重复（浮点噪声级）不在默认规则内，需要领域容差时先声明再扩展。
- 缺失机制（MAR/MNAR）不可由通用规则判定；>5% 缺失列一律不填补。
- 多因素交互模型、时间序列、文本分析超出范围。
