---
name: sqlite-query-foundry
description: >-
  当案件材料包含 SQLite 数据库（.db/.sqlite 文件）且任务要求对其进行查询、
  过滤、聚合或行数核对时启用本技能：先建档摸清结构，再以只读方式逐条执行
  SQL 并捕获查询计划，对每条语句做未过滤基线的行数对账与扇出预警，最后用
  独立改写的 SQL 复核关键聚合，保证“实际执行的”与“报告所写的”一致。
  当案件仅含 CSV 等纯文本数据、不涉及任何数据库查询时，不适用本技能。
---

# SQLite 查询铸造厂（sqlite-query-foundry）

## 重心与设计理由

本技能的重心是 **SQLite 查询正确性与行数对账溯源**。挑战赛把“数据库查询
条件漏字段导致行数偏多”列为典型的静默错误：查询能跑通、数字看起来合理，
但语义是错的，而代理往往照抄结果不加核实。本技能对此给出工程化对策：

1. **先制图后动手**：survey 子命令把库结构、行数、NULL 分布、取值范围、
   跨表同名列（潜在 JOIN 键）全部建档，杜绝“凭猜写 SQL”。
2. **执行留痕**：exec 子命令以 `mode=ro` 只读打开数据库，逐条执行落盘的
   `.sql` 文件，捕获 EXPLAIN QUERY PLAN、计时、结果快照 CSV 及其 sha256。
3. **行数对账**：每条语句的结果行数都与 SQL 中命名各表的未过滤 `COUNT(*)`
   基线并列记录，并计算比值；JOIN 查询行数超过最大单表基线时发出扇出预警。
   漏过滤字段（行数偏多）与条件过严（行数异常偏少）都会在比值上现形。
4. **独立复核**：reconcile 子命令要求代理把关键行数与聚合用**第二种写法**
   重写一遍（如 JOIN+GROUP BY 对 IN 子查询、朴素计数对去重计数），由工具
   仲裁 PASS/FAIL。报告中的每个关键数字都必须经此对账，而非单条查询直出。

## 固定路径与运行契约

- 输入只读：`/input/`（`case.json`、`task.md`、数据字典、数据文件）。
- 草稿区：`/app/work/`（survey 建档、`.sql` 草稿、中间产物）。
- 交付区：`/app/output/`（`result.json` 及全部交付物）。
- 数据库文件只读打开，绝不修改 `/input` 内任何文件。

`result.json` 契约：

- `case_id`：与 `/input/case.json` 完全一致；
- `output_contract` 中列出的**每一个字段**都必须出现，缺字段即违约；
- `status`：`ok` / `partial` / `failed`，须诚实；partial 必须逐条说明
  未完成的限制是什么；
- `anomalies`：异常清单，空结果、扇出预警、截断、对账失败、重复批次嫌疑
  等均须在此登记；
- `provenance`：每个数据输入文件的 sha256、SQLite 版本、每条查询对应的
  `.sql` 文件路径、结果快照 CSV 的 sha256、执行耗时；
- 变更记录：对草稿区之外文件的任何写入都须记录；原则上除 `/app/output`
  外不产生任何写入。

## 执行协议

1. **survey 建档**：对案件中每个 `.db` 执行
   `python3 /skills/weekly-skill/scripts/dbfoundry.py survey --db <DB> --work /app/work/survey_<名>`，
   阅读 `survey.md`：行数、列画像、NULL 与去重计数、跨表同名列。
2. **据 task 语义起草 SQL 并落盘**：逐条把查询写成 `/app/work/*.sql`
   （每条业务问题一个文件），过滤条件逐一对照 `task.md` 与数据字典核对，
   特别注意状态字段、NULL 三值逻辑、单位与编码（详见
   `references/sql_playbook.md`）。
3. **exec 逐条执行并对账**：每个 `.sql` 文件执行
   `... exec --db <DB> --sql <文件> --tag <标签> --outdir /app/work/exec`，
   检查 meta JSON：status、`rows_returned`、基线比值、`fanout_warning`、
   查询计划。比值或预警异常时回到第 2 步修正 SQL，并将该轮修正记入变更记录。
4. **reconcile 独立复核关键聚合**：为每个进入最终答案的数字写
   `/app/work/claim.json`，其中每条检查都是**独立改写**的 SQL（不是原查询
   复制粘贴），执行
   `... reconcile --db <DB> --claim /app/work/claim.json --out /app/work/recon.json`。
   全部 PASS 方可采信；任何 FAIL 都必须查明原因后再交付。
5. **填写 result.json**：把查询结果、每条语句的行数对账摘要、结果快照
   sha256、数据库文件 sha256、空结果与预警等异常，全部按契约填入。
6. **交付 checklist**：
   - [ ] `case_id` 与 case.json 一致；
   - [ ] output_contract 全部字段齐备；
   - [ ] 每个关键数字都有 reconcile PASS 记录支撑；
   - [ ] 空结果均已如实登记且未被暗中放宽条件；
   - [ ] 截断（若有）已声明并说明影响；
   - [ ] provenance 含全部输入 sha256 与查询快照 sha256；
   - [ ] status 诚实，partial 的限制已逐条写明。

## 异常处理

- **查询为空**：exec 记录 `status: "empty_result"`，写出仅含表头的 CSV，
  退出码 0。纪律是**记录而非松条件**：区分“条件过严”“语义真空”（阈值
  本就超出物理范围）与“数据缺失”（survey 显示相关列大量 NULL 或表为空），
  在 anomalies 中注明判断依据；绝不静默放宽 WHERE。
- **语法错误 / 表不存在**：exec 记录 `status: "sql_error"` 与错误信息，
  立即停止后续语句并以退出码 1 结束；修正 SQL 后从该文件重跑。
- **超时 / 大行数截断**：单语句默认墙钟超时 30 秒（`--timeout` 可调），
  超时记录 `status: "timeout"` 并以退出码 1 停止；结果超过 `--max-rows`
  （默认 100000）时截断写出，`rows_truncated: true` 如实登记，聚合类结论
  不得基于截断样本下断言。
- **JOIN 扇出预警**：`fanout_warning: true` 表示 JOIN 结果行数超过最大单表
  基线，通常是连接键非唯一或连接条件写错；必须回头核对连接条件，确认属于
  预期笛卡尔放大后方可在 anomalies 中解释保留，否则修正 SQL。
- **只读保护**：任何写语句（INSERT/UPDATE/DDL）会被 `mode=ro` 拒绝并记为
  sql_error，这是契约的一部分，不得绕行。

## 预算意识

总预算 64 次模型请求、900 秒。survey 每库一次即可，不要重复建档；exec 的
sql_error 会立即止损，重跑成本低，但仍应在起草阶段仔细核对条件，把迭代
轮次压到最小；reconcile 只针对**进入答案的关键数字**，不要为中间探索性
查询写复核。到达预算一半时先把已核实的结果写入 `/app/output/result.json`
（status 可为 partial），再完善其余部分，确保任何时刻都有可交付物。

## 最小调用示例（合成示例）

```bash
# 1. 生成合成示例库（纯虚构传感器网络，脚本现场生成，包内不含二进制）
python3 /skills/weekly-skill/examples/make_synthetic_db.py
DB=/skills/weekly-skill/examples/output_demo/sensors_syn.db

# 2. 建档
python3 /skills/weekly-skill/scripts/dbfoundry.py survey --db "$DB" --work /app/work/survey

# 3. 执行并对账（q3 为合法空结果：记录 empty_result，退出码 0）
python3 /skills/weekly-skill/scripts/dbfoundry.py exec --db "$DB" \
  --sql /skills/weekly-skill/examples/queries/q1_valid_readings_per_site.sql \
  --tag q1 --outdir /app/work/exec

# 4. 独立复核（含一条 JOIN+GROUP BY 对 IN 子查询的改写核对）
python3 /skills/weekly-skill/scripts/dbfoundry.py reconcile --db "$DB" \
  --claim /skills/weekly-skill/examples/reconcile_claim.json --out /app/work/recon.json
```

一键复现：`bash /skills/weekly-skill/examples/run_example.sh`（任意目录可运行）。

## 局限性

- `exec` 按分号**朴素切分**语句：字符串字面量内或块注释 `/* */` 中的分号
  会破坏切分，含此类内容的 SQL 请拆成多个文件逐条执行。
- 基线对账的表名提取是**正则启发式**：无法展开子查询，且会把 CTE 名误当
  表名（其 COUNT 失败会如实记录 error）；对账结论应结合人工判断。
- 扇出预警是必要非充分条件：未触发不代表 JOIN 正确，重复行计数等问题仍须
  靠 reconcile 的独立改写暴露。
- survey 对每列做 NULL 计数与去重计数，属全表扫描，超大库（千万行级）建档
  较慢；本技能面向挑战赛规模的库（数百至数万行）设计。
- 超时基于 `set_progress_handler` 的周期性检查，粒度约数千条虚拟机指令，
  不能中断正在进行的单次磁盘 I/O。
- reconcile 的 aggregate 容差为**绝对容差**；复核只核对声明中的检查项，
  不能证明未被声明的结论正确。
