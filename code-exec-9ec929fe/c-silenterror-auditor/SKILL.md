---
name: silenterror-auditor
description: 结果验证重心：静默错误猎手。当科研数据分析任务（/input 的 case.json、task.md、CSV/SQLite → /app/output/result.json）的最大风险是"代码跑通了但算错了"时使用——缺失值被当 0 参与均值、重复记录没去重就分组、t 检验前提没检查就报 p 值、SQL 漏条件行数偏多、单位口径不一致。本 Skill 提供与主分析独立代码路径的审计器：scan 在计算前扫描数据中的经典陷阱并试算其影响（如缺失当 0 会使均值偏移多少），audit 把 result.json 里每个数值登记为 claim 并从原始输入独立重算，任一 MISMATCH 即以退出码 1 阻断 success。不适用：无法从原始数据重算的结论（如人工判读）。
---

# silenterror-auditor：不信任何跑通的管道

## 重心：结果验证

本场景最危险的失败是静默错误——退出码 0、图也出来了，但数字是错的。本 Skill 的对策是制度化怀疑：

1. **计算前** `scan`：把数据里已知的静默错误形态全部挖出来，并**试算影响**（"若把 3 个缺失当 0，均值由 35.82 变为 35.41"），让处置决定有据可依。
2. **交付前** `audit`：result.json 里每个数值型结论登记成 claim，审计器从 `/input` **原始数据**（不是工作表！）用独立实现重算；CONFIRMED 才允许写进结果，MISMATCH/UNVERIFIABLE 阻断交付。
3. **复核时** `diff`：对比任意两版 result.json，向复核者展示修正前后分歧。

你的角色：自由完成主分析（任何工具均可），但**每个写进 result.json 的数字都必须有对应 claim 且通过 audit**。没有 claim 的数字不得写入。

## 固定路径与运行契约

- 工具：`/skills/weekly-skill/scripts/secaudit.py`（纯标准库，`python3` 运行）
- 输入：`/input/case.json`（case_id、output_contract）、`/input/task.md`、数据文件
- 工作区：`/app/work`（scan 报告、claims.json、audit 报告）；交付：`/app/output/result.json` 与附件
- result.json 必须含 `case_id`、output_contract 全部字段、`anomalies` 数组、`provenance`（含输入哈希与审计报告路径）
- 诚实 partial：某字段无法通过 audit 时，修正分析；确实无法完成时 status=partial 并在 `missing_fields` 说明——**禁止**调大 tolerance 或删除 claim 蒙混

## 执行协议

### 第 0 步：陷阱扫描（先于一切统计）

```bash
python3 /skills/weekly-skill/scripts/secaudit.py scan /input/*.csv /input/*.db \
  --out /app/work/scan_report.json
```

逐条处置报告中的风险：修正（去重、剔除哨兵值、统一缺失标记）或在 result.json 的 `anomalies` 中写明不修正的理由。未处置的风险 = 评审判定的静默错误。

### 第 1–2 步：主分析（任意方法）

按 task.md 完成清洗、统计、图、SQL 查询。唯一要求：**保留从原始行到最终统计行的行数链条**（原始→去重→剔缺失→用于统计），它本身也应登记为 claim。

### 第 3 步：登记 claims 并独立重算

`/app/work/claims.json`：

```json
[{"id": "rows_raw", "kind": "row_count", "source": "/input/raw.csv", "value": 1030},
 {"id": "miss_slump", "kind": "n_missing", "source": "/input/raw.csv", "column": "slump", "value": 3},
 {"id": "mean_strength", "kind": "mean", "source": "/input/raw.csv",
  "column": "strength", "value": 35.82, "tolerance": 0.01},
 {"id": "n_wine", "kind": "sql_scalar", "db": "/input/wine.db",
  "query": "SELECT COUNT(*) FROM wine", "value": 178}]
```

kind 支持 `row_count / n_missing / distinct_count / count_where / mean / median / std / min / max / sum / count / sql_scalar`。`count_where` 用 `op`（==,!=,>,>=,<,<=,na,notna）+ `value_of`。统计类 claim 默认在**非缺失数值**上计算（与引擎口径一致）；若你的主分析用了别的口径（如插补后），claim 的 source 应指向派生表并在 anomalies 说明。

```bash
python3 /skills/weekly-skill/scripts/secaudit.py audit \
  --claims /app/work/claims.json --out /app/work/audit_report.json
```

退出码 1 = 存在 MISMATCH/UNVERIFIABLE：回到对应分析步骤修正数字（或修正 claim 的口径），重跑至全 CONFIRMED。audit 报告路径写入 provenance。

### 第 4 步：交付

result.json 全部契约字段落实、anomalies 记录全部已处置/未处置风险、provenance 含输入哈希与 audit 报告路径后，方可 status=success。

## 静默错误清单与检测点

见 `references/silent_error_taxonomy.md`：缺失当 0、未去重分组、前提未检的 p 值、COUNT(col) 与 COUNT(*) 口径、连接放大行数、单位错配、索引错位、浮点字面比较——每类给出 scan/audit 的具体拦截方式。

## 最小调用示例（合成示例，非正式案例结果）

```bash
cd /skills/weekly-skill/examples && bash run_example.sh
```

在埋了四类陷阱（NA 缺失、完全重复行、-999 哨兵、重复主键）的合成数据上演示：scan 挖出全部风险 → 一份故意带错的 naive claims 被 audit 拦截（exit 1）→ 修正后的 claims 全部 CONFIRMED → diff 展示两版分歧。示例数据人工合成，不对应任何正式案例。
