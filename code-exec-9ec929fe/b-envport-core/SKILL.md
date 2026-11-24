---
name: envport-core
description: 环境配置与零依赖可移植执行核心。当科研数据分析任务（/input 的 case.json、task.md、CSV 快照或 SQLite 数据库 → /app/output 的 result.json）面临"依赖没装跑不起来、包版本不匹配、换台机器数字变了"的风险时使用。重心在环境层：全部清洗/统计/查询/绘图逻辑固化在纯 Python 标准库单文件 envport.py 中，任何装有 Python≥3.8 的机器无需 pip install 即可逐字节复现统计结果；matplotlib 仅作可选渲染层，缺失时显式降级并保留绘图数据；env 命令固定环境快照，run_log 记录每条命令，finalize 把环境与日志并入 provenance。不适用：必须用 GPU/特定二进制库的计算。
---

# envport-core：让"跑通"不依赖运气

## 重心：环境配置与可移植执行

失败模式"跑不起来"（依赖缺失、版本不匹配、路径写死）和"隔天重跑数字变了"（版本与种子没记录）都是环境层问题。本 Skill 的对策：

1. **零依赖计算核心**：`scripts/envport.py` 只用 Python 标准库实现清洗、描述统计、Welch t 检验（不完全贝塔函数算 p 值）、Pearson 相关、OLS、SQLite 只读查询。不存在 pip install 失败的可能。
2. **显式降级而非中断**：matplotlib 是唯一的可选库且仅用于渲染；缺失时 `figure` 输出 `SKIPPED_no_matplotlib` 回执 + 绘图数据 CSV，你在 result.json 中如实报告，交付继续。
3. **确定性**：无随机源、无时间戳进入统计结果；`env` 快照 + `run_log.jsonl` 使任何人可复算。

你的角色：读题 → 写 rules.json → 按协议调用命令 → 把真实输出填进 result.json。不要重写核心计算。

## 固定路径与运行契约

- 工具：`/skills/weekly-skill/scripts/envport.py`（下文 `$EP`），`python3 $EP --work /app/work --output /app/output <子命令>`
- 输入：`/input/case.json`、`/input/task.md`、数据文件；工作区 `/app/work`；交付 `/app/output`
- result.json 必须含 `case_id`（与 case.json 一致）、output_contract 全部字段、`anomalies`（数组）、`provenance`（finalize 自动并入环境快照与 run_log 路径）
- 诚实 partial：无法完成的字段在 `missing_fields` 说明原因，finalize 会把未落实字段自动降级为 partial——**不要**手工把 status 写成 success

## 执行协议

### 第 0 步：环境快照 + 输入档案

```bash
python3 $EP --work /app/work env
python3 $EP --work /app/work profile /input/数据文件.csv [/input/库.db ...]
```

env.json 固定 Python 版本、平台、可选库有无；profile.json 给出每个文件 sha256、行列、类型、缺失与重复行数。读完再规划。

### 第 1 步：清洗（先写 rules.json，口径显式化）

```json
{"rename": {"原始列": "规范名"}, "select_columns": ["..."],
 "coerce": {"col": "float"},
 "missing": {"policy": "drop_rows | impute | report_only", "columns": ["..."],
             "impute": {"col": "mean|median|字面值"}},
 "dedup": {"policy": "drop_exact | drop_by", "keys": ["id"]},
 "filter": [{"column": "col", "op": ">=", "value": "0"}]}
```

```bash
python3 $EP --work /app/work clean --table /input/x.csv --rules /app/work/rules.json \
  --out /app/work/clean.csv --report /app/work/clean_report.json
```

引用不存在的列会**拒绝执行**（MISSING_COLUMN），这是防静默错误设计，不要绕过。缺失值默认不参与后续统计；impute 仅在任务明确要求时使用并记入 anomalies。

### 第 2 步：统计与查询

```bash
python3 $EP --work /app/work describe  --table /app/work/clean.csv --columns strength,age
python3 $EP --work /app/work aggregate --table /app/work/clean.csv --group-by batch --metrics "strength:mean,strength:std,strength:count"
python3 $EP --work /app/work ttest --table /app/work/clean.csv --column strength --group batch
python3 $EP --work /app/work corr  --table /app/work/clean.csv --x cement --y strength
python3 $EP --work /app/work ols   --table /app/work/clean.csv --y strength --x cement,age
python3 $EP --work /app/work sql --db /input/lab.db --query "SELECT ..." --out /app/work/q1.csv
```

注意：Welch t 检验的 p 值由纯 Python 不完全贝塔函数计算；正态性前提引擎不替你检查，报告 p 值时必须注明检验种类与前提检查情况。SQL 强制只读；0 行结果触发 EMPTY RESULT 警告——先核对表名/连接键/WHERE，不得把空查询当正常答案。

### 第 3 步：图（可选渲染层）

```bash
python3 $EP --work /app/work figure --table /app/work/clean.csv --kind hist --x strength \
  --title "抗压强度分布" --xlabel "strength (MPa)" --out /app/output/fig1.png
```

标题与轴标签（含单位）必须取自数据字典原文。每张图配 `.receipt.json`（源文件哈希、列名、绘入点数、排除缺失点数）。渲染失败只降级、不伪造。

### 第 4 步：填充 result.json 并 finalize

```bash
python3 $EP --work /app/work --output /app/output finalize --input /input
```

finalize 核对 case_id 与契约字段非 null；有缺项时自动把 status 降为 partial 并登记 missing_fields；全部落实才允许 success，并把 env 快照与 run_log 并入 provenance。

## 异常处理与降级阶梯

- 命令非零退出：读 stderr 的具体错误码（MISSING_COLUMN / EMPTY_TABLE / SQL_READONLY / TTEST_ZERO_VARIANCE / OLS_SINGULAR …），修正输入或规则后重跑该步；禁止换一段自写代码绕开。
- matplotlib 缺失 → 已自动降级；pandas/numpy 缺失 → 不需要它们；Python <3.8 → 换用平台 scientific-python 资源并在 provenance 记录实际版本。
- 数据与数据字典冲突：取保守口径并记录两种解释于 anomalies。
- 详见 `references/environment_playbook.md`（依赖声明、版本锁定、隔离、降级与替代的完整清单）。

## 最小调用示例（合成示例，非正式案例结果）

```bash
cd /skills/weekly-skill/examples && bash run_example.sh
```

对 `synthetic_case/`（含缺失、重复行、类型混杂的合成 CSV 与一个合成 SQLite 库）跑通 env→profile→clean→describe/aggregate/ttest/corr/sql→figure→finalize 全链路，并用 `ENVPORT_NO_MPL=1` 演示无 matplotlib 时的诚实降级。示例数据人工合成，输出不对应任何正式案例。
