---
name: direct-analysis-engine
description: >-
  当评测案件为科研数据分析（/input 内含 case.json、中文 task.md、数据字典以及
  CSV/SQLite 数据文件，要求完成数据清洗、描述统计、图形绘制、SQL 查询并产出
  可核验的 result.json）时使用本技能。本技能提供一个确定性执行引擎
  （scripts/case_engine.py），用一条命令直接替 Agent 完成全部可推断计算并落盘
  result.json 骨架，Agent 的职责缩减为：运行引擎、阅读报告、裁决歧义、复核交付。
  不适用于：模型训练与机器学习建模、机理层面的科学解释、论文与综述写作——
  这些场景超出确定性表格分析的范畴。
---

# direct-analysis-engine：端到端确定性科研数据分析引擎

## 重心与设计理由

本技能的重心是**直接替 Agent 完成计算**，而非仅在事后检查 Agent 的工作。理由如下。

护栏式技能只能发现错误，不能消灭错误：Agent 依然要逐条编写清洗、统计、绘图、
查询代码，每一步都可能引入编造数值、静默丢行、口径含混等问题，再依赖护栏事后
拦截。在 64 次模型请求、900 秒的预算约束下，"写了再查、查了再改"的回路既昂贵
又不可靠。本技能将全部确定性工作收敛进一个零依赖的 Python 引擎：一次执行即完成
输入清点（sha256）、CSV 画像与清洗、描述统计、目标列分组统计、SQLite 调查与
SQL 执行、图形绘制与绘图数据落盘、契约字段映射、result.json 骨架生成，并附
`verify` 子命令以独立代码路径做双通道复核。Agent 的智力只花在引擎无法替它做的
事情上：裁决歧义、补充引擎无法推断的契约字段、确认交付。这最大化了一次跑通率
与结果正确性，也天然满足"先落盘、再改进"的预算纪律。

## 固定路径与运行契约

- 技能安装位置：`/skills/weekly-skill`，引擎入口为
  `/skills/weekly-skill/scripts/case_engine.py`。
- 只读输入：`/input`（含 case.json、task.md、数据字典、CSV/SQLite 数据文件）。
- 暂存区：`/app/work`（清洗后 CSV、engine_report.md、run_log.txt）。
- 交付区：`/app/output`（result.json、statistics.json/md、图形 PNG 与
  figure_data CSV、查询结果 CSV）。
- `/app/output/result.json` 必须包含：`case_id`；`output_contract` 中列出的**每一个
  字段**（无论引擎能否填充）；`status`（`complete` 或 `partial`）；`anomalies`
  （`{kind, detail}` 列表）；`provenance`（含全部输入文件 sha256、Python 版本、
  平台、起止 UTC 时间、引擎版本、所用规则、确定性声明）；`change_records`。
- 诚实 partial 规则：凡引擎无法推断的契约字段，保留该字段并置 null，同时在
  `missing_fields` 中逐字段给出原因；绝不允许编造数值，绝不允许静默类型强转
  或静默丢行。缺失标记（空串、NA、N/A、NaN、nan、null、None、-）一律置 null，
  行默认保留；离群值只标记计数，绝不删除。

## 执行协议

按编号顺序执行，不得跳步。

1. 第 0 步（首个模型请求内必须完成）——运行引擎落盘骨架：

   ```bash
   python3 /skills/weekly-skill/scripts/case_engine.py run \
     --input /input --work /app/work --output /app/output
   ```

   若 task.md 给出 SQL，追加 `--sql /app/work/queries.sql`；若需覆盖清洗规则，
   编写 rules.json 后追加 `--rules /app/work/rules.json`（规则模式见
   `references/engine_design.md`）。此步结束后，一份合法（可能 partial）的
   result.json 已经存在。

2. 第 1 步——阅读 `/app/work/engine_report.md` 与 `/app/output/result.json` 中的
   `missing_fields`。报告第 7 节列出全部待裁决歧义：未映射契约字段、目标列
   猜测、单位存疑等。

3. 第 2 步——人工裁决并补充引擎无法推断的契约字段：对照 task.md 与数据字典，
   为 `missing_fields` 中的每个字段填入有依据的值或明确说明无法推断的理由；
   每次修改都向 `change_records` 追加一条记录（record_id 递增、UTC 时间戳、
   修改内容与理由）。引擎产物中已有的数值字段不得手工改动。

4. 第 3 步——双通道复核：

   ```bash
   python3 /skills/weekly-skill/scripts/case_engine.py verify \
     --input /input --work /app/work --output /app/output
   ```

   verify 用与 run 不同的代码路径独立重算每个数值列的 n、mean、std（ddof=1），
   校验图形数据行数、result.json 契约完整性与全部产物 sha256。必须全部 PASS
   （退出码 0）；任何 FAIL 须回到对应步骤修复后重新复核。

5. 交付前 checklist：
   - result.json 含 case_id 与 output_contract 列出的全部字段；
   - status 与实际填充情况一致（有 missing_fields 则必须为 partial）；
   - anomalies 非空项均有可读 detail；
   - provenance 含输入 sha256 与版本时间信息；
   - change_records 记录了引擎初填之后的每一次人工修改；
   - verify 退出码为 0。

## 异常处理策略

- 输入文件缺失（无 case.json / 无 CSV / 无数据库）：记录 `missing_file` 或
  `no_csv_found` 异常，以现有材料继续，退出码仍为 0；仅当 `/input` 目录本身
  不存在时以退出码 2 终止并给出明确信息。
- CSV 无法解码：依次尝试 utf-8-sig 与 gb18030，均失败则记录 `undecodable_csv`
  并跳过该文件，不中断其他文件。
- SQL 返回空集：记录 `empty_result`，视为正常结果而非错误；SQL 语法错误记录
  `sql_error` 并继续执行后续语句。
- matplotlib 不可用：不生成 PNG，改写 `figures_spec.json` 与 `figure_data_*.csv`
  （绘图数值完整保留），记录 `figure_degraded` 异常，退出码仍为 0。
- 未知契约字段：置 null 并写入 `missing_fields`（含原因）与
  `unmapped_contract_field` 异常，交由人工裁决。
- 一切错误信息写 stderr，前缀 `[case_engine]`；引擎内部不使用任何随机数，
  同一输入必得同一输出。

## 预算意识

评测预算为 64 次模型请求、900 秒、每次响应 16384 tokens。纪律如下：**第一个
模型请求就必须运行引擎**（执行协议第 0 步），使一份合法的 partial result.json
从第一分钟起即已落盘；此后的每一次请求只做增量改进——裁决一个歧义、补充一个
字段、复核一次——每完成一处即写盘。严禁先长篇规划再动手；严禁在 verify 未 PASS
时进行与修复无关的润色。

## 最小调用示例

`examples/` 内含一个完整的最小示例：合成合金强度数据集
（`synthetic_case/alloy_strength_syn.csv`，含缺失值、3 条精确重复行、2 个明显
离群值与 1 处非数值故障）、配套 case.json 与 task.md，以及一键脚本
`run_example.sh`（从任意工作目录均可运行，依次执行 run 与 verify 并打印
result.json 与报告尾部）。示例数据与输出均为**合成示例**，仅用于演示引擎行为，
其中刻意包含一个无法映射的契约字段以演示诚实 partial。

## 局限性

- 引擎只做描述性分析与确定性变换，不做推断统计、建模或因果解释。
- 契约字段映射基于名称归一化相似度，语义含糊的字段仍需人工裁决。
- 目标列识别依赖命名模式（class|target|label|类别|强度|strength），命名非常规时
  需人工确认。
- 图形最多两张（直方图 + 散点），不替代面向出版的可视化。
- verify 复核覆盖 n/mean/std 与文件哈希，不能证明语义层面的任务理解正确。
