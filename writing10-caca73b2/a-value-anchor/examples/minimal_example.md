# 最小端到端示例（value-anchor-rd）

> **本示例为合成示例，输入数据为虚构，仅演示接口与流程，不冒充正式案例结果。**
> `examples/input/` 下的 case.json、task.md 与 materials/ 全部为人工编造的合成数据；`examples/output/` 下的每个文件均由本包脚本真实运行生成（文稿为人依据台账撰写），未做任何手工修饰。

## 目录约定

- 输入：`examples/input/case.json`（case_id = `SYNTH-EXAMPLE-001`，output_contract 含 deliverable / preserved_facts / evidence_map / change_log / status 五键）、`examples/input/task.md`、`examples/input/materials/`（results_table.csv、stats_output.txt、figure_caption.txt）。
- 输出：`examples/output/`（values.json、values_report.md、manuscript_draft.md、audit_report.md、result.json）。

## 实际运行的命令与退出码

以下命令均在本 skill 目录下以 `python3` 真实执行（Python 3.12）：

```bash
# 步骤1：落 result.json 骨架（case_id 原样保留，契约键空但存在，status=partial）
python3 scripts/result_contract.py init --case examples/input/case.json --out examples/output/result.json
# INIT OK: 已写入骨架 examples/output/result.json（contract 键: deliverable, preserved_facts, evidence_map, change_log, status）
# 退出码 0

# 步骤2：扫描材料构建数值台账
python3 scripts/ingest_values.py --materials examples/input/materials --out examples/output/values.json --report examples/output/values_report.md
# INGEST OK: 条目 27，跳过 0 -> examples/output/values.json ; 报告 -> examples/output/values_report.md
# 退出码 0

# 步骤4：依据台账人工撰写 examples/output/manuscript_draft.md（每个数字带 [Vnn] 锚点）

# 步骤5：机器锚定审计
python3 scripts/anchor_audit.py --manuscript examples/output/manuscript_draft.md --ledger examples/output/values.json --tol 0.02 --report examples/output/audit_report.md
# AUDIT: numbers=25 anchors=24 fail=0 warn=0
# INFO  台账条目未被正文引用（可能遗漏关键数据）: V08, V09, V11, V12, V14, V15, V17
# PASS: 全部数字均已锚定且在容差内与台账一致
# 退出码 0

# 步骤6：填写 result.json 后终检
python3 scripts/result_contract.py check --case examples/input/case.json --result examples/output/result.json --output-dir examples/output
# PASS: result.json 满足 output_contract（case_id='SYNTH-EXAMPLE-001'，键数=5，status=complete）
# 退出码 0
```

## 真实输出摘录

### values.json 片段（台账条目 V01、V20）

```json
{
  "id": "V01",
  "kind": "stat",
  "value": 1.85,
  "unit": "mmol/L",
  "error": {"kind": "SD", "value": 0.22},
  "stat": "mean_sd",
  "source": {"file": "figure_caption.txt", "line": 1, "row": null, "col": null},
  "method": "regex",
  "confidence": "high",
  "note": "均值 ± 误差（误差类型: SD）: 1.85 ± 0.22"
}
{
  "id": "V20",
  "kind": "stat",
  "value": 0.001,
  "unit": null,
  "error": {"kind": "none", "value": null},
  "stat": "p",
  "source": {"file": "stats_output.txt", "line": 3, "row": null, "col": null},
  "method": "regex",
  "confidence": "high",
  "note": "p 值（比较符 <）: p < 0.001"
}
```

### audit_report.md 片段（PASS）

```
- 数字总数: 25；锚点总数: 24
- FAIL: 0；WARN: 0；INFO: 1
## 结论: PASS
## INFO
- 台账条目未被正文引用（可能遗漏关键数据）: V08, V09, V11, V12, V14, V15, V17
```

INFO 中的 7 个未引用条目为表格中与图注/统计输出重复的均值与 n 单元格，已在 result.json 的 change_log 中作为人工确认项说明。

### result.json check PASS 行

```
PASS: result.json 满足 output_contract（case_id='SYNTH-EXAMPLE-001'，键数=5，status=complete）
```

## 阴性测试（审计必须能抓错，篡改文件不随包发布）

**阴性测试 1：篡改一个数字。** 将文稿中 `1.85 ± 0.22 mmol/L` 改为 `1.95 ± 0.22 mmol/L`（临时副本，已删除），审计结果：

```
FAIL  L5: 数字 1.95 与句内锚点 V01,V10,V02,V07 的台账值均不吻合（tol=0.02；p/n 要求精确相等）
WARN  L5: 锚点 [V01]（台账值 1.85）与句内数字不对应
FAIL: 存在 1 处锚定违规，必须修复后重审，不得绕过
退出码 1
```

**阴性测试 2：删除一个锚点。** 删除 `t(18) = 7.95 [V19]` 中的 `[V19]`（临时副本，已删除），审计结果：

```
FAIL  L7: 数字 7.95 与句内锚点 V27,V21,V20,V18 的台账值均不吻合（tol=0.02；p/n 要求精确相等）
FAIL: 存在 1 处锚定违规，必须修复后重审，不得绕过
退出码 1
```

两类典型造假（改数不改锚点、有数无锚点）均被确定性判 FAIL，退出码非零，可被 Harness 直接用作质量门。
