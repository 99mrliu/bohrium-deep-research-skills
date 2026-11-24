---
name: twin-pass-redundant-reconciliation
description: >-
  科研汇总数据清洗的“双实现冗余对账”过程质量控制技能。当任务给出发表汇总表的转写件、
  数据字典、按指标给出的单位/QC 规则与明确清洗工单，要求确定性清洗（缺失分类标记、
  单位换算、归一化主键去重、物理界 QC 标记）且结果必须可信、可审计时触发。核心机制：
  先写唯一 rules.json 规约（每条规则带 source 出处），再用两个结构独立的 stdlib
  引擎（行流式 engine_row.py 与列集合式 engine_col.py）分别执行，diff_runs.py 逐格
  对账并做幂等核验；零分歧且幂等通过才放行 /app/output，否则进入分歧处理循环或
  如实 partial。本技能不做字节取证、不做渲染、不做字典编译；绝不插补缺失/非法源值，
  绝不推断总体统计量。
---

# twin-pass-redundant-reconciliation：双实现冗余对账的清洗质量控制

## 一、重心与边界

本技能把过程质量的根基放在**冗余执行**（N-version 执行学）：同一份规则规约、两个
结构上独立的实现、逐格 diff，**不一致不交付**。它防的是两类单管道审计防不住的
问题——实现错误（引擎缺陷）与规约歧义（同一段文字两种合理解读）。

与其他方向的错位（不要越界）：

- **不做字节取证**：不鉴定编码故障如何注入、不做字节级溯源；只在步骤 1 做中性的
  编码规范化（UTF-8 / NFC / 去 BOM / 统一 LF），并保留原始件与哈希。
- **不做渲染**：不产出图表、报告排版；产物仅为清洗表、台账、计数摘要与对账结论。
- **不做字典编译**：不把数据字典解析成规则库；规约由 Agent 阅读字典与工单后**人工
  编写**为一份 rules.json，每条规则必须带 source 出处定位。

组件：

| 组件 | 角色 |
| --- | --- |
| `scripts/engine_row.py` | 引擎 A：行流式实现（csv.reader 逐行、命令式循环） |
| `scripts/engine_col.py` | 引擎 B：列集合式实现（DictReader→dict-of-lists、集合运算与推导式） |
| `scripts/diff_runs.py` | 对账与幂等核验：逐格 diff + 重跑引擎 A 要求字节一致 |
| `references/rules_spec.md` | rules.json 完整 schema（编写规约前必读） |
| `references/redundancy_method.md` | 冗余方法论、分歧分类学、收敛流程（处理分歧前必读） |
| `examples/` | 合成示例：先跑出真实分歧、再修规约收敛的完整过程留痕 |

两个引擎**不共享任何代码**，且各自文档化了相反的默认平局倾向（A 取首现、B 取末
现）：规约若没写清平局规则，双跑必然分歧，迫使歧义回到规约层面解决——这是设计
意图，不是缺陷。

## 二、铁律（不可违背）

1. **不插补**：缺失/非法源值（未检测、低于检出限、录入缺失）只分类标记，绝不填入
   估计值、均值、0 或任何替代数。
2. **不推断总体统计量**：summary 只允许过程计数（行数、各类标记数、换算数）；禁止
   均值、中位数、标准差、检出率等任何总体推断。
3. **原值留痕**：越界值保留原值并加 flag；被去重丢弃的行在台账记录；一切改动在
   ledger.csv 中可溯源到规则出处。
4. **不依据标签补造数据**：不得因“看起来应该是某物”而改写源值。
5. **分歧不掩盖**：双引擎不一致时禁止取平均、投票或任选其一交付；必须定位到规约
   歧义或引擎缺陷，修复后双跑至零分歧；无法收敛则如实 partial 并列出未解决分歧。
6. **失败如实说明**：任何步骤失败都要在 result.json 的 status/uncertainty 中讲清
   楚，不得粉饰为成功。

## 三、路径与资源定位

技能安装路径：`/skills/weekly-skill`。 runbook 中统一用变量 `$SK` 指代：

```bash
SK=/skills/weekly-skill
ls "$SK/scripts/engine_row.py" 2>/dev/null || SK=$(dirname "$(find / -maxdepth 6 -name 'engine_row.py' 2>/dev/null | head -n1)")
echo "SK=$SK"   # 期望 .../scripts 的父目录，例如 /skills/weekly-skill
```

若 `find` 也找不到，说明技能未安装：停止执行并在 result.json 中如实报告
（status=failed，说明缺失技能资源），不得临时重写引擎充数。

## 四、运行契约

- 输入：`/input/case.json` 与工作目录的 `task.md`（含 output_contract，逐字阅读，
  以其声明的字段清单为准）。
- 工作区：`/app/work`（固证、规范化副本、规约、双引擎产物、对账产物均放这里）。
- 交付：`/app/output`。**只在 verdict=PASS 且幂等 PASS 后放行清洗产物**；
  `result.json` 必须含 `case_id` 与 output_contract 声明的**全部字段**，含诚实
  status（success/partial/failed）、sources、uncertainty、change records。
- **最先落骨架**：读案后第一件事是在 `/app/output/result.json` 写入覆盖全部合同
  字段的骨架（status 先写 failed），此后每完成一个阶段就地更新；这样任何中途
  崩溃留下的都是诚实的失败而非缺失交付。
- 预算纪律：64 次模型请求 / 900 秒。双跑、对账、幂等都是本地命令，把模型请求
  留给规约编写与分歧判定，不要把模型当计算器逐格清洗。

## 五、标准流程（runbook）

以下命令可直接复制；路径按实际案例调整。

### 步骤 0：读案、固证、先落骨架

```bash
cat /input/case.json
cat task.md            # 重点：output_contract 字段清单、清洗工单、单位/QC 规则
mkdir -p /app/work/evidence /app/output
cp /input/case.json /app/work/evidence/   # 表格、字典等随案文件一并复制固证
python3 - <<'PY'
import hashlib, json, pathlib
ev = pathlib.Path('/app/work/evidence')
sums = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(ev.iterdir()) if p.is_file()}
(ev / 'SHA256SUMS.json').write_text(json.dumps(sums, indent=2, sort_keys=True) + '\n')
print(json.dumps(sums, indent=1))
PY
# 立刻落 result.json 骨架（status 先 failed，字段覆盖 output_contract 全部要求）
python3 - <<'PY'
import json, pathlib
case = json.loads(pathlib.Path('/input/case.json').read_text())
skeleton = {
  "case_id": case.get("case_id", "UNKNOWN"),
  "status": "failed",
  "uncertainty": ["run not completed; skeleton written first per twin-pass runbook"],
  "sources": [],
  "change_records": []
  # TODO: 按 task.md 的 output_contract 补齐其余字段（占位 None + uncertainty 注明）
}
pathlib.Path('/app/output/result.json').write_text(
    json.dumps(skeleton, indent=2, ensure_ascii=False) + '\n')
PY
```

### 步骤 1：编码规范化工作副本

只做中性规范化，不改语义；原始件已在 evidence/ 固证。

```bash
python3 - <<'PY'
import pathlib, unicodedata
src = pathlib.Path('/app/work/evidence/table.csv')   # 改成实际表文件
text = src.read_bytes().decode('utf-8-sig')          # 去 BOM；非 UTF-8 源先判定再转码
text = unicodedata.normalize('NFC', text)            # μ / µ 等兼容字符归一
text = text.replace('\r\n', '\n').replace('\r', '\n')
pathlib.Path('/app/work/norm.csv').write_text(text, encoding='utf-8', newline='')
print('normalized ->', '/app/work/norm.csv')
PY
```

### 步骤 2：编写 rules.json（唯一规约）

先读 `$SK/references/rules_spec.md` 全文，再据数据字典 + 单位/QC 规则 + 工单编写
`/app/work/rules.json`。要点：

- 每条规则（哨兵分类、单位映射、物理界、去重）都必须带 `source` 字段，定位到
  字典/规则/工单的章节或行号；没有出处的规则不得写入。
- **平局规则必须显式**：`dedup.tie` 写 `first_occurrence` 或 `last_occurrence`。
  若工单确实没规定，写入你向工单最贴近的解读并在 result.json 的 uncertainty 中
  声明——不要留空，留空等于把决定权交给引擎默认值（双引擎默认相反，必分歧）。
- 单位换算只作用于 `convert_units: true` 的测量列；百分比等无量纲列不要换算。
- 参照 `$SK/examples/rules.json` 的写法。

### 步骤 3：双引擎各自运行

```bash
python3 "$SK/scripts/engine_row.py" --rules /app/work/rules.json --csv /app/work/norm.csv --outdir /app/work/out_row
echo "engine_row exit=$?"   # 0 成功；3 规约校验失败；4 输入表错误
python3 "$SK/scripts/engine_col.py" --rules /app/work/rules.json --csv /app/work/norm.csv --outdir /app/work/out_col
echo "engine_col exit=$?"
```

每个引擎各自产出 `cleaned.csv`、`ledger.csv`、`summary.json`。退出码非 0 时按
第六节处理，不要带着错误产物进入对账。

### 步骤 4：对账

```bash
python3 "$SK/scripts/diff_runs.py" --a /app/work/out_row --b /app/work/out_col --outdir /app/work/diff
echo "diff exit=$?"   # 0 PASS；6 存在分歧
cat /app/work/diff/twin_pass_verdict.json
```

### 步骤 5：分歧处理循环（exit=6 时）

```bash
column -s, -t /app/work/diff/reconciliation_queue.csv | less   # 或直接读 CSV
```

逐条阅读 reconciliation_queue.csv（行/字段/引擎A值/引擎A理由/引擎B值/引擎B理由；
理由列自动引自各引擎自己的 ledger），按 `$SK/references/redundancy_method.md` 的
分类学判定：

- **规约歧义** → 改 rules.json 把语义写死（如补 dedup.tie），双跑；
- **引擎缺陷** → 改出错的那一侧引擎（另一侧作为参照），双跑；
- **非确定性来源**（dict 序、浮点格式、时间戳、文件序）→ 修引擎消除隐状态，双跑；
- 修完回到步骤 3，直到零分歧。**每一轮都要双跑**，禁止只跑被改的一侧。

### 步骤 6：幂等核验

```bash
python3 "$SK/scripts/diff_runs.py" --a /app/work/out_row --b /app/work/out_col --outdir /app/work/diff \
  --idempotence --engine "$SK/scripts/engine_row.py" --rules /app/work/rules.json --csv /app/work/norm.csv
echo "final diff exit=$?"   # 必须 0：reconciliation=PASS 且 idempotence=PASS
```

### 步骤 7：交付

```bash
cp /app/work/out_row/cleaned.csv /app/work/out_row/ledger.csv /app/work/out_row/summary.json /app/output/
cp /app/work/diff/twin_pass_verdict.json /app/output/
# 更新 /app/output/result.json：status=success；写入 verdict 摘要；change records 引自
# ledger.csv；sources 引自 rules.json 各 source 字段；uncertainty 如实列出保留事项。
```

## 六、异常处理（诚实 partial 的打开方式）

| 情形 | 处置 |
| --- | --- |
| 空表（只有表头/无表头） | 引擎退出码 4。不得交付空清洗结果充数；result.json 记 status=partial 或 failed，说明表为空及证据位置。 |
| 规约校验失败（退出码 3） | 按 stderr 逐条修 rules.json（缺 source、bounds min>max、未知 normalize 步骤等）。若字典/工单信息不足以写出合法规约，status=partial 并列出缺失信息清单。 |
| 输入表错误（退出码 4：缺列、长短行、未知单位标签） | 缺列/长短行：核对规范化副本与字典，属案情异常的如实报告。未知单位标签：把该单位连同字典给出的换算因子补进 `unit_column.factors` 后双跑；字典无依据时不得编造因子，status=partial 并列出该单位。 |
| 一侧引擎报错另一侧正常 | 正常侧结果**不得直接交付**；把报错侧修通后双跑对账。 |
| 双引擎都报错 | 不交付任何清洗数据；result.json status=failed，附两侧 stderr 摘要与已固证材料位置。 |
| 分歧无法收敛（多轮后仍有分歧） | 禁止掩盖。status=partial；result.json 必须列出未解决分歧清单（逐条：行/字段/两引擎值与理由/你的初步判断），并附 reconciliation_queue.csv 到 /app/output。 |
| 幂等核验失败 | 视为存在非确定性来源（见 redundancy_method.md 第三节），消除后双跑；无法消除则 partial 并说明。 |

## 七、最小示例

`$SK/examples/` 内含全部人工编造的合成数据与一个完整的“分歧→收敛”过程：

```bash
cd "$SK/examples"
# round 1：规约故意缺 dedup.tie → 双引擎在 caffeine 平局对上选择不同行 → FAIL（exit 6）
python3 ../scripts/engine_row.py --rules expected/round1/rules_round1.json --csv lab_table.csv --outdir /tmp/r1_row
python3 ../scripts/engine_col.py --rules expected/round1/rules_round1.json --csv lab_table.csv --outdir /tmp/r1_col
python3 ../scripts/diff_runs.py --a /tmp/r1_row --b /tmp/r1_col --outdir /tmp/r1_diff; echo $?
# final：rules.json 补 tie=first_occurrence → 对账 PASS + 幂等 PASS（exit 0）
python3 ../scripts/engine_row.py --rules rules.json --csv lab_table.csv --outdir /tmp/f_row
python3 ../scripts/engine_col.py --rules rules.json --csv lab_table.csv --outdir /tmp/f_col
python3 ../scripts/diff_runs.py --a /tmp/f_row --b /tmp/f_col --outdir /tmp/f_diff \
  --idempotence --engine ../scripts/engine_row.py --rules rules.json --csv lab_table.csv; echo $?
diff -r /tmp/f_row /tmp/f_col && echo IDENTICAL
```

预期产物已与仓库内 `expected/round1/`、`expected/final/` 中的留痕一致；
详见 `$SK/examples/README.md`。
