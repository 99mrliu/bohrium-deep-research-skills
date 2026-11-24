# 最小调用示例（合成示例）

> **本示例为合成示例**：输入库与输出均为虚构数据，仅说明接口与完整流程，
> 不是平台正式案例的结果。

## 输入（make_fixture.py 生成的虚构资料库）

```
input/
  case.json              # case_id=synthetic-forge-001，2 个问题 + output_contract
  task.md
  reports/se07_report.txt  # 虚构实验报告（界面阻抗数据）
  reports/memo.txt         # 虚构备忘录（注明循环伏安数据尚未入库）
  data/impedance.csv
```

q1（60 °C 界面阻抗）库内有答案；q2（循环伏安扫描速率）库中无依据。

## 调用

```bash
bash examples/run_example.sh    # 一键演示：夹具 → init → 检索 → 核验 → 收尾
```

分步接口见 SKILL.md 工作流；citations.jsonl 与 answers.json 的格式见
references/citation_contract.md。

## 示意输出（实际运行得到，数据虚构）

1. `qa_init`：`{"questions": 2, "indexed_files": 3}`，保底 result.json
   落盘（status=partial）。
2. `qa_retrieve`：q1 命中 `F003`（se07_report.txt）L4；q2 检索命中备忘录
   中"循环伏安数据尚未整理入库"一行。
3. `qa_verify`：`{"total": 1, "passed": 1, "verdict": "all_passed"}` ——
   引文 `[F003|de5c206e|L4-L4]"60 摄氏度下界面阻抗降至 45 Ω·cm²。"`
   通过版本坐标与逐字核验。
4. `qa_finalize`：`status=completed`；q1 论断 verification=passed；
   q2 判为 no_basis（"库中无依据"）；sources 仅含实际被引的 F003。

演示中还验证过反例：故意把引文 file_id 写错时，核验报告
`reason=quote_not_found`、finalize 强制把该论断降级为 unsupported 且
status 回落 partial —— 闸门不允许失效引文进入交付物。
