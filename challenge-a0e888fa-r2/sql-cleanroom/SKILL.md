---
name: sql-cleanroom-declarative
description: >-
  当任务要求清洗“已发表汇总表的转写件”且其中被显式注入存储/编码故障（哨兵值、
  混写单位、近似重复行、越界值、乱码/BOM、分隔符异常）时使用本技能；尤其适用于
  随附数据字典、按指标给出的单位/QC 规则与明确清洗工单、并要求覆盖“数据库字段”
  的场景。本技能把全部清洗表达为 SQLite（Python 标准库 sqlite3）上的关系操作：
  规则是数据（规则表）、清洗是 SQL（steps.sql）、质量报告是聚合查询
  （report_queries.sql）、谱系是 SQL 脚本加查询日志，全程可重放、逐格可审计。
  不适用于需要从原始实验记录推断总体统计量或插补缺失值的任务（此为铁律禁止项）。
---

# SQL Cleanroom —— 声明式数据清洗（清洗即查询）

## 1. 重心与边界

本技能的差异化不在管道阶段，而在**执行范式**：一切清洗都是 SQLite 上的集合操作。

1. **载入保真**：`scripts/load_raw.py` 把 CSV 逐格按 TEXT 载入 `raw(line_no, …)`，
   不做静默类型转换；编码判定（utf-8-sig / utf-8 / 回退 gb18030 / latin-1）、
   分隔符判定、原始文件 sha256、行列数全部写入 `load_report.json`。
2. **规则即数据**：你（Agent）根据数据字典、单位/QC 规则与清洗工单，把清洗规则写成
   四张 CSV（模板见 `references/rule_tables.md`），每条规则必须注明出处（source）。
   `scripts/run_steps.py` 校验后载入规则表 `rule_*`，缺出处直接失败（退出码 4）。
3. **清洗即查询**：你编写 `steps.sql`（模式库见 `references/sql_patterns.md`），
   由 `run_steps.py` 在**单事务**内逐条执行并写 `query_log.json`（每条语句的序号与
   受影响行数）。缺失 token → NULL 且分类列保留；单位换算 = JOIN `rule_unit_map`；
   去重 = 规范化主键 GROUP BY 且 keep 依据落表；QC = SELECT 生成 `issues` 表；
   逐格变更以 INSERT…SELECT 侧写进 `change_log(line_no, field, old_value, new_value, rule_id)`。
4. **报告即聚合查询**：`report_queries.sql` 中每条 `-- @name:` 标记的 SELECT 产出一个
   报告数字；`scripts/export_report.py` 只做“查询 → 渲染”，数字禁止手写。自检：
   `selfcheck` 查询返回的指标与对库表的独立重算必须一致，不一致退出码 5。
5. **可重放**：`case.db + steps.sql + report_queries.sql + load_report.json +
   query_log.json` 构成完整谱系；任何人重放可得字节一致结果（导出 `cleaned.csv`
   的 sha256 由 `export_report.py` 写入 `report_check.json`，须转写进 result.json）。

## 2. 铁律（违反即失败）

- **不得推断总体统计量**（均值、总量、代表性结论一律禁止）。
- **不得插补缺失/非法源值**：缺失 token 与非法值只能 NULL 化并保留分类/登记 issues。
- **不依据标签补造数据**：不得按 station、parameter 等标签“合理推测”任何单元格。
- **失败与无法解释处必须如实说明**：写进 result.json 的 `uncertainty` 与 issues 表，
  状态如实标 `partial` / `failed`。
- 报告中的每个数字都必须能回溯到一条已执行的查询；手写数字等同造假。

## 3. 路径说明

- 技能安装路径：`/skills/weekly-skill`，下文以 `$SK` 代指。
- 定位命令（找不到时）：

```bash
SK=/skills/weekly-skill
if [ ! -f "$SK/scripts/load_raw.py" ]; then
  SK=$(dirname "$(dirname "$(find / -maxdepth 6 -name 'load_raw.py' 2>/dev/null | head -n1)")")
fi
echo "$SK"   # 应包含 scripts/ references/ examples/ SKILL.md
```

- 运行契约：输入 `/input/case.json` 与工作目录的 `task.md`（含 output_contract）；
  工作区 `/app/work`；最终交付 `/app/output`。
- `result.json` 必须含 `case_id` 与 output_contract 声明的全部字段，含诚实
  `status`（success/partial/failed）、`sources`、`uncertainty`、change records，
  并写入 `cleaned_sha256`（取自 `report_check.json`）。
- 预算 64 次模型请求 / 900 秒：**先把 result.json 骨架落盘**（status 先置 failed，
  随后每完成一步就地更新），再推进流水线，避免超时零交付。

## 4. 分步 runbook

### 4.0 读案 + 固证 + 保底

```bash
mkdir -p /app/work /app/output
cat /input/case.json            # case_id、数据文件、数据字典、单位/QC 规则、工单
cat task.md 2>/dev/null || cat /app/work/task.md 2>/dev/null   # output_contract
# 数据文件拷入工作区并固证（原始字节 sha256 留存）
cp /input/<数据文件>.csv /app/work/raw_input.csv
shasum -a 256 /app/work/raw_input.csv | tee /app/work/input_fingerprint.txt
# 保底骨架：最先落盘
cat > /app/output/result.json <<'EOF'
{"case_id": "<从 case.json 读取>", "status": "failed",
 "uncertainty": "pipeline not completed yet", "sources": [], "change_records": "change_log.csv"}
EOF
```

### 4.1 载入（保真）

```bash
python3 "$SK/scripts/load_raw.py" \
  --input /app/work/raw_input.csv \
  --db /app/work/case.db \
  --report /app/work/load_report.json
echo "exit=$?"   # 0 成功；3 载入失败（坏编码/空表，按第 5 节处理）
cat /app/work/load_report.json   # 核对编码判定、分隔符、行列数是否合乎数据字典
```

### 4.2 据数据字典/工单编写规则 CSV（规则即数据）

模板与出处要求见 `references/rule_tables.md`；现成可抄的实例见 `examples/rules/`。

```bash
mkdir -p /app/work/rules
$EDITOR /app/work/rules/missing_tokens.csv   # token,class,source
$EDITOR /app/work/rules/unit_map.csv         # field,from_unit,to_unit,factor,source
$EDITOR /app/work/rules/qc_bounds.csv        # field,lo,hi,action,source
$EDITOR /app/work/rules/key_fields.csv       # field,role,source
```

### 4.3 编写 steps.sql（清洗即查询）

模式库：`references/sql_patterns.md`；完整可运行示例：`examples/steps.sql`。
必须覆盖：change_log/issues 建表 → 缺失分类 → 单位换算 → 归一化主键去重
（keep 依据落表）→ cleaned 落表 → change_log 侧写 → issues 登记。

```bash
$EDITOR /app/work/steps.sql
```

### 4.4 事务执行

```bash
python3 "$SK/scripts/run_steps.py" \
  --db /app/work/case.db \
  --rules /app/work/rules \
  --steps /app/work/steps.sql \
  --log /app/work/query_log.json
echo "exit=$?"   # 0 成功；2 SQL 报错（日志含出错语句序号，逐条定位）；4 规则缺出处/非法
cat /app/work/query_log.json
```

### 4.5 导出 + 自检（报告即聚合查询）

```bash
$EDITOR /app/work/report_queries.sql   # 参照 examples/report_queries.sql，必含 selfcheck
python3 "$SK/scripts/export_report.py" \
  --db /app/work/case.db \
  --queries /app/work/report_queries.sql \
  --outdir /app/output
echo "exit=$?"   # 0 自检通过；5 报告数字与独立重算不一致（禁止交付，先修查询）
```

### 4.6 交付清单（/app/output）

| 文件 | 来源 |
| --- | --- |
| result.json | 你更新：case_id、output_contract 全字段、status、sources、uncertainty、change_records、cleaned_sha256 |
| cleaned.csv / change_log.csv / issues.csv | export_report.py |
| quality_report.md / report_check.json | export_report.py |
| steps.sql / report_queries.sql / load_report.json / query_log.json / case.db | 从 /app/work 复制（谱系） |

更新 result.json 后逐字段对照 task.md 的 output_contract 再核一遍。

## 5. 异常处理

| 症状 | 处置 |
| --- | --- |
| 坏编码（load_raw 退出码 3） | 手工复核字节（`xxd`），确认真实编码后临时转码为 UTF-8 再载入；转码事实与依据写进 result.json 的 uncertainty，源文件 sha256 已固证不丢。 |
| 空表/无表头（退出码 3） | 核对是否拿错文件或分隔符误判；确属空数据则 status=partial，如实说明，不造数。 |
| 规则表校验失败（退出码 4） | 按报错行号补 source 或修正数值列；禁止为了通过校验编造出处——找不到出处的规则宁可不用并写入 uncertainty。 |
| SQL 报错（退出码 2） | query_log.json 记录了出错语句序号与预览；把 steps.sql 单独在 `sqlite3 /app/work/case.db` 里逐条重放定位，修好后整段重跑（事务已回滚，库仍干净）。 |
| 主键冲突/重复 | 全部保留在 issues（duplicate_removed）与 duplicates_dropped 表，keep 依据写明；禁止静默丢弃。 |
| 自检不一致（退出码 5） | 报告数字与库表重算不符：修 report_queries.sql，禁止改重算逻辑迎合报告。 |
| 单位换算遇非数值 | 模式库 S9：置 NULL 并记 non_numeric_source，不猜测。 |

## 6. 最小示例

`examples/` 内含一份**人工编造的合成**案例（`water_quality.csv`：哨兵 -999/ND/空白、
µg/mL 与 mg/L 混写、大小写空格近似重复行、越界值），四张规则 CSV、`steps.sql`、
`report_queries.sql` 以及 `expected/` 下的真实运行产物。复现：

```bash
cd /tmp && mkdir -p demo && cd demo
python3 "$SK/scripts/load_raw.py" --input "$SK/examples/water_quality.csv" \
  --db case.db --report load_report.json
python3 "$SK/scripts/run_steps.py" --db case.db --rules "$SK/examples/rules" \
  --steps "$SK/examples/steps.sql" --log query_log.json
python3 "$SK/scripts/export_report.py" --db case.db \
  --queries "$SK/examples/report_queries.sql" --outdir out
# 数据产物字节级一致（sha256 亦写入 report_check.json）
for f in cleaned.csv change_log.csv issues.csv quality_report.md; do
  diff "out/$f" "$SK/examples/expected/$f" && echo "$f OK"
done
# JSON 报告含机器相关绝对路径，按字段比对（sha256、行列数、自检结果必须一致）
SK="$SK" python3 - <<'PY'
import json, os
exp = json.load(open(os.path.join(os.environ["SK"], "examples/expected/report_check.json")))
new = json.load(open("out/report_check.json"))
assert exp["cleaned_sha256"] == new["cleaned_sha256"], "cleaned.csv 摘要不一致"
assert exp["checks"] == new["checks"], "自检结果不一致"
print("replay OK")
PY
```
