# 最小调用示例（合成示例）

> **本示例为合成示例**：输入库与输出均为虚构数据，仅说明接口与完整流程，
> 不是平台正式案例的结果，也不代表正式评分依据。

## 输入（由 make_fixture.py 生成的虚构资料库）

```
input/
  case.json                 # case_id=synthetic-demo-001，2 个问题 + output_contract
  task.md
  papers/report_v1.txt      # 历史版本（效率 23.1%，行政备注已作废）
  papers/report_v2.txt      # 当前版本（效率更正为 24.6%）
  papers/copy_of_report_v2.txt  # v2 的字节级重复副本
  notes/版本说明.txt         # 行政备注：v2 为当前有效版本，v1 作废
  data/results.csv
  data/locked_raw.bin       # 权限 000，模拟不可读文件
```

## 调用

```bash
bash examples/run_example.sh          # 一键：建夹具 → 三步脚本 → 打印报告
# 或分步：
python3 scripts/forensic_scan.py --input <root>/input --work <root>/work --out <root>/output
python3 scripts/lineage.py        --work <root>/work --out <root>/output
python3 scripts/catalog_check.py  --input <root>/input --work <root>/work --out <root>/output
```

## 示意输出（实际运行得到，数据虚构）

forensic_scan：`{"files": 6, "unique_contents": 4, "byte_duplicate_groups": 1,
"stats": {"unreadable": 1, "ok": 5, ...}}`

lineage：识别 1 个版本组——`report_v2.txt` 依据行政备注 `F003:L2`
（"report_v2.txt 为当前有效版本，数据以该版为准。"）裁定 role=current；
`report_v1.txt` 为 historical；`copy_of_report_v2.txt` 为 current_copy。

catalog_check：独立重算哈希复核 5 个可读文件全部一致（catalog_pass=true），
`locked_raw.bin` 记 unverifiable；修复台账：

```
- [proposed] quarantine_duplicate → papers/copy_of_report_v2.txt（identical sha256）
- [proposed] needs_attention → data/locked_raw.bin（需恢复权限后重扫）
- [proposed] designate_current_version → papers/report_v2.txt（行政备注 F003:L2）
```

基于该编目回答 q2（"当前有效版本报告的初始转换效率"）时，只能引用
`[F006|5f3ecf45]`（v2，24.6%），v1 的 23.1% 必须标注为历史版本数值。
