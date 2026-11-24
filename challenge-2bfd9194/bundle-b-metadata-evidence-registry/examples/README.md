# 合成示例走查（synthetic demo）

**这是合成示例，不是正式案例结果。** 输入为本仓库手工编造的 12 个极小文本文件，仅用于演示端到端流程与证据链形态。

## synthetic-input/（12 个文件）

| 文件 | 演示点 |
|---|---|
| metadata.csv | 伴随元数据表（file/project/year/author/data_type 列）；其中 `spectrum_2020_raw.csv` 登记 year=2021，与文件名前缀 2020 **故意冲突** |
| admin_notes.txt | 行政备注（仪器型号/保存期限/来源单位 全局默认） |
| spectrum_2020_raw.csv | 数据文件，正文首部另有"仪器："行（与全局备注不同值 → 第二条冲突） |
| projectA_notes.txt | 正文首部带"项目号：""作者："（L2 证据） |
| 2022_summary.csv | 年份前缀数据文件（普通数据表，不会被当成伴随表） |
| report_v1.txt / report_最终版.txt | 版本对：词干相同、内容不同 → 版本链 |
| alias_a.txt / 别名_数据副本.txt | 别名对：内容逐字节相同 → 按哈希去重 |
| 实验记录_张三.txt | 中文文件名 + 内容"年度：2022" |
| random_memo.txt | 完全无元数据 → 进 _unassigned |
| corrupted_scan_note.txt | 内容标记模拟损坏项（`!!CORRUPTED!!`），照常入库并如实留痕 |

## 复跑命令

```bash
mkdir -p /tmp/r2-test/{input,work,output}
cp -r examples/synthetic-input/* /tmp/r2-test/input/
echo '{"case_id":"synthetic-demo-r2","output_contract":["metadata_registry","library_manifest","coverage_report","audit_report"]}' > /tmp/r2-test/input/case.json
echo '合成示例任务：按 {project}/{year}/{data_type} 组织，元数据须保留出处。' > /tmp/r2-test/input/task.md
python3 scripts/run_case.py all --input /tmp/r2-test/input --work /tmp/r2-test/work --out /tmp/r2-test/output
```

## 目检要点（synthetic-output/ 为真实跑出的产物）

- `result.json`：status=complete，summary 与 audit 一致（input_files=12、duplicate_groups=1、version_chains=1、metadata_conflicts=2、audit PASS 16/FAIL 0）。
- `metadata_registry.jsonl`：42 行，每行 locator 都被 verify_registry.py 回查真实命中（REG-PROV PASS 42/42）。
- `conflicts.json`：2 条——spectrum 的 year（L1=2021 胜 L3=2020）与 instrument（L1 全局备注胜 L2 正文行），全部候选保留。
- `coverage_report.json`：unfilled_files 含 random_memo.txt 等；unassigned 清单逐条写明缺哪些模板字段。
- `LIBRARY_MANIFEST.jsonl`：12 行对应 12 个输入；别名 `别名_数据副本.txt` 记 duplicate_of_canonical；每行带 metadata 子对象与 provenance 摘要。
- `version_chains.json`：report_v1.txt → report_最终版.txt 一条链。
- 重跑幂等：第二次运行 journal 全部为 already_committed_identical，零复制，audit 仍 PASS。
