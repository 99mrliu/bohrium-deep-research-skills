# 合成示例走查（**合成示例，非正式案例结果**）

本目录演示 version-lineage-rebuilder 的端到端行为。`synthetic-input/` 是人工构造的
13 个极小文本文件（PDF 用纯文本模拟），`synthetic-output/` 是**真实运行** `run_case.py all`
得到的输出（裁剪到核心 JSON/MD）。它们仅用于说明与自检，不是正式案例答案。

## 输入覆盖点（synthetic-input/）

| 文件 | 考什么 |
|---|---|
| report_v1.txt / report_v2.txt / report_最终版.txt | 三版本链：同词干不同内容，E3 候选边，顺序 v1→v2→最终版 |
| admin_notes.txt | 行政备注："scan_final.pdf 替代 scan_old.pdf" → E1 边（词干不同也照连，locator 回查） |
| scan_old.pdf / scan_final.pdf（文本模拟） | E1 连接跨词干文件对 |
| data_copy.txt / 实验数据备份.txt | 别名对：同内容不同名 → E2 别名，不重复入库 |
| projA/notes.txt / projB/notes.txt | 同名 notes.txt、不同项目内容 → **不得**误判为版本（备注类文件不参与 E3），落库撞名自动 __v2 |
| 实验记录_2024春.txt | 中文文件名（NFC） |
| metadata.csv | 伴随元数据表 |
| 损坏数据_corrupt.txt | SIMULATED-CORRUPT 头标记 → 模拟损坏，记入 skipped 不入库 |

## 复跑命令

```bash
mkdir -p /tmp/r3-test/{input,work,output}
cp -r examples/synthetic-input/* /tmp/r3-test/input/
echo '{"case_id":"synthetic-demo-r3","output_contract":["version_graph","lineage_report","library_manifest","audit_report"]}' > /tmp/r3-test/input/case.json
echo '合成示例任务：重建版本世系，保留版本关系。' > /tmp/r3-test/input/task.md
python3 scripts/run_case.py all --input /tmp/r3-test/input --work /tmp/r3-test/work --out /tmp/r3-test/output
```

## 目检要点（真实运行已验证）

- report 三版成链且顺序 v1→v2→最终版，latest=`report_最终版.txt`，落库为 `supplementary/report.txt`；
- E1 边 `scan_old.pdf→scan_final.pdf`，basis=admin_note，locator=`admin_notes.txt#L2` 回查命中原文；
- 两个 notes.txt 未被误判为版本：均为 orphan，落库 `admin/notes.txt` 与 `admin/notes__v2.txt`（撞名自动后缀，记入 plan_conflicts）；
- 别名 `data_copy.txt` 不入库，manifest 中 role=alias 且带 alias_of；
- 被替代版本进 `_versions/report/` 与 `_versions/scan_final/`；
- `损坏数据_corrupt.txt` 在 skipped_and_conflicts.json 中如实披露；
- audit_report.json 全 PASS（11/11），result.json status=complete；
- 重跑 `all` 收敛零新操作（journal 全为 already_committed_identical，输出字节级一致）。
