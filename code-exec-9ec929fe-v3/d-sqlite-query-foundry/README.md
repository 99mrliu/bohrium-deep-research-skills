# sqlite-query-foundry

面向“科研代码生成与执行：科研数据分析”挑战（challenge-9ec929fe）的 Skill 包，
重心为 **SQLite 查询正确性与行数对账溯源**：针对“查询条件漏字段导致行数偏多”
这类静默错误，提供“建档 → 只读执行留痕 → 基线行数对账 → 独立改写复核”的
完整工具链，保证实际执行的查询与报告所写的结果一致。

## 工作流

1. `survey`：对数据库建档（结构、行数、NULL/去重计数、数值范围、跨表同名列）。
2. `exec`：只读（`mode=ro`）逐条执行落盘的 `.sql`，捕获 EXPLAIN QUERY PLAN、
   计时、结果快照 CSV 及 sha256，并对每条语句做未过滤基线的行数对账与扇出预警；
   空结果如实记 `empty_result`（退出码 0），错误记 `sql_error` 并止损（退出码 1）。
3. `reconcile`：把进入答案的关键行数/聚合用第二种写法重写，由工具仲裁 PASS/FAIL。

## 运行要求

- Python 3.9+，仅标准库（sqlite3、csv、json、hashlib、argparse、pathlib、
  datetime、time、sys、re）；无网络访问；全部为 UTF-8 文本。
- 示例数据库由 `examples/make_synthetic_db.py` 现场生成，包内不含任何二进制。

## 文件清单

| 路径 | 说明 |
| --- | --- |
| `SKILL.md` | 技能定义：重心、运行契约、执行协议、异常处理、预算、示例、局限 |
| `README.md` | 本文件 |
| `GITHUB_URL.txt` | 源码仓库地址 |
| `scripts/dbfoundry.py` | 三子命令工具：survey / exec / reconcile |
| `references/sql_playbook.md` | 高频静默错目录、行数对账方法论、空结果纪律、查询计划阅读要点 |
| `examples/make_synthetic_db.py` | 生成合成示例库 sensors_syn.db（含故意埋设的重复批次陷阱） |
| `examples/queries/q1_valid_readings_per_site.sql` | 示例查询：各站点有效读数计数 |
| `examples/queries/q2_region_mean.sql` | 示例查询：各区域均值（JOIN+GROUP BY） |
| `examples/queries/q3_empty_result.sql` | 示例查询：合法空结果 |
| `examples/reconcile_claim.json` | 与真实执行结果一致的复核声明（含独立改写检查） |
| `examples/run_example.sh` | 一键复现：生成库 → 建档 → 执行 → 复核，任意 cwd 可运行 |

## 快速验证

```bash
bash examples/run_example.sh
```

预期：q1/q2 状态 `ok`，q3 状态 `empty_result` 且退出码 0，reconcile 全部
PASS（退出码 0）；示例库中埋设的 17 行重复批次由第 3 项复核检查暴露。
