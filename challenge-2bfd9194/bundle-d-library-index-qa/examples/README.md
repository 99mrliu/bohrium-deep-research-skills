# 合成示例走查（**合成示例，非正式案例结果**）

本目录演示 library-index-qa 的完整闭环。输入是人工编造的小文件，输出是本地真实跑出的结果。**正式案例不会内置任何答案。**

## synthetic-input/（12 个极小文本）

覆盖题目要求的全部典型情形：

| 文件 | 情形 |
|---|---|
| 量子点发光二极管实验记录.txt | 可全文检索的中文实验记录（含温度条件，问题 1 素材） |
| 量子点实验记录-副本.txt | **别名对**：与上行逐字节相同（内容哈希去重） |
| XRD原始数据说明.txt + xrd_2024-05-12.dat | 中文说明 + 数据文件（问题 2 素材） |
| report_v1.txt / report_最终版.txt | **版本对**：词干相同内容不同 |
| 实验参数metadata.csv | 伴随元数据表 |
| 行政版本备注.txt | 行政版本备注（谁替代谁） |
| 会议纪要2024-春.txt | 中文名行政文件 |
| supplementary_图注.txt / draft_分析草稿.txt | supplementary / drafts 分桶 |
| 损坏文件占位.txt | 模拟损坏项（含 `[[SIMULATED-CORRUPT` 标记，扫描器记录 skipped 不崩溃） |

## 复跑命令

```bash
mkdir -p /tmp/r4-test/{input,work,output}
cp -r examples/synthetic-input/* /tmp/r4-test/input/
echo '{"case_id":"synthetic-demo-r4","questions":["量子点实验的温度条件是什么？","XRD 数据存放在哪个文件？"],"output_contract":["library_manifest","qa_log","index_stats","audit_report"]}' > /tmp/r4-test/input/case.json
echo '合成示例任务：组织资料并回答 case.json 中的 questions。' > /tmp/r4-test/input/task.md
python3 scripts/run_case.py all --input /tmp/r4-test/input --work /tmp/r4-test/work --out /tmp/r4-test/output --auto-answer
```

`--auto-answer` 仅示例用：把 top-1 snippet 作为答案草稿（confidence=low、status=partially_answered、note="auto draft, 合成示例"）。**正式运行时由模型读 `work/query_raw.json` 后撰写 `work/qa_answers.json`，再用 `run_case.py qa --answers ...` 合并**（见 SKILL.md 第 4、5 节）。

## synthetic-output/（真实跑出的产物，catalog.db 为二进制故未收录）

- manifest 12 行 = 输入 12 个文件（含 1 个跳过项）；files 表 12 行。
- duplicates.json：1 组别名（量子点实验记录-副本 → 量子点发光二极管实验记录）。
- version_chains.json：1 条链（report_v1 → report_最终版）。
- QA_LOG.json：2 问均带真实 evidence（fts5_and 命中），auto draft 标注齐全。
- audit_report.json：6 项全 PASS（含 snippet 逐条子串核对、20% 哈希抽查、REBUILD_DIFF 为空）。
- result.json：status=partial——因为 1 个模拟损坏文件被如实跳过（诚实降级示例，非缺陷）；无跳过项的案例应为 complete。
- REBUILD_DIFF.json：empty_diff（只凭清单 + library/ 无损重建）。
- REBUILD_DIFF.json 中的绝对路径反映演示运行环境（/tmp/r4-test），属正常。
- 重跑 `all` 收敛零复制（幂等），audit 保持 PASS（已实测）。
