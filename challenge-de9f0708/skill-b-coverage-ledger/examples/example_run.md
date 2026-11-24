# 示例运行说明(合成示例,非正式测评结果)

## 这是什么

本目录是一个**合成示意案例**的端到端运行示例,演示 skill-b-coverage-ledger 的核心机制:
检查清单实例化 → 保底 partial 落盘 → 覆盖矩阵对账抓漏。所有输入(mock_case.json、
mock_task.md、mock_paper.txt、mock_findings.json)均为虚构合成,人物、单位、电话
号码、文献均为编造,仅用于演示脚本行为。

## 合成案例设计

- `mock_case.json` / `mock_task.md`:声明 **3 个审查面**——引用规范、伦理审查、
  隐私合规;output_contract.required_fields 齐全。
- `mock_paper.txt`(约 2 页合成论文)埋入 3 个已知问题:
  1. 参考文献 `[3]` 缺出版年份(引用面,CIT-02);
  2. 412 名本科生人体问卷研究,全文无伦理批准声明与知情同意(伦理面,ETH-01/02);
  3. 正文 2.3 节出现疑似手机号 `13812345678` 随原始数据存档且未剥离(隐私面,PRV-01)。
- `mock_findings.json`:**故意只覆盖引用+伦理两面**(reviewed_facets 只有这两项,
  findings 只含 F-001/F-002),隐私面被遗漏——用于演示覆盖矩阵抓漏。

## 如何复跑

```bash
bash examples/run_example.sh
```

脚本内做四步(输出全部写入 `examples/output/`,每次运行先清空重生成,确定性可复现):

1. `case_intake.py`:识别出 3 个声明审查面(citation/ethics/privacy),实例化
   20 条检查项写入 `output/work/checklist.json`;同时立即落保底 partial
   `output/result.json`(此时快照留存于 `output/work/result_skeleton_snapshot.json`)。
2. `budget_log.py`:记 intake 相位账(4s / 1 请求)。
3. `budget_log.py`:记"逐面审查"相位账(故意只审了引用+伦理,120s / 9 请求)。
4. `coverage_check.py`:生成 `output/coverage_matrix.json` 并更新
   `output/result.json`;最后 `budget_log.py --status` 看总账。

## 输出如何解读

实测运行结果(连续两次运行 diff 为空,输出确定性):

| 检查点 | 实测结果 |
|--------|----------|
| 保底 result.json | intake 后即存在;快照 `work/result_skeleton_snapshot.json` 显示 status=partial、contract 8 字段齐备、uncertainty="审查进行中" |
| 覆盖矩阵 | 3 面中 citation/ethics 覆盖(covered=true),**privacy covered=false** |
| 抓漏 | `uncovered_facets: ["privacy"]`,result.json 的 not_reviewed 如实写入 privacy 面及原因 |
| 状态纪律 | 覆盖率 66.7% < 100%,**status 保持 partial**;另测得:即使输入伪造 complete,脚本也会自动降级回 partial |
| findings 统计 | summary:findings_count=2,severity_counts={critical:1, major:1} |
| 预算账 | `work/budget.jsonl` 两笔,总计 124s / 10 请求,未触预警线(48 请求/720s) |

埋入问题与脚本行为的对应:引用面与伦理面的两个埋入问题以 findings 形式进入对账
(F-001 文献缺年份、F-002 缺伦理声明);隐私面的埋入问题(手机号)因 findings 草稿
故意遗漏而被覆盖矩阵标为未覆盖——这正是本 skill 的核心演示:**漏面不会静默通过,
而是进入 not_reviewed 并压住 status**。

## 输出文件清单

- `output/result.json` — 对账后的最终交付物(partial,含 findings 与 not_reviewed)
- `output/coverage_matrix.json` — 覆盖矩阵(每面 checks/findings/覆盖状态)
- `output/work/checklist.json` — 实例化检查清单(20 条,状态=未开始)
- `output/work/result_skeleton_snapshot.json` — 开工 60 秒内的保底 partial 快照
- `output/work/budget.jsonl` — 追加式预算账
