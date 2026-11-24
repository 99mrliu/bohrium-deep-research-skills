# 合成示例（synthetic）

> 合成示例，非正式案例数据。本目录全部内容为虚构，仅用于演示与回归测试。

## 内容

- `case.json`：3 版候选方案（plan_v1/v2/v3）、带行号定位符的材料（M1-M3）、
  8 字段混合形状的 `output_contract`（JSON-Schema properties 形态）。
- `task.md`：七类约束审查任务书。
- `review_report.md`：通过全部 lint 的正例审查报告。
- `bad_review_report.md`：植入 4 类缺陷的负例（R2/R5 硬违规 + R3/R4 警告）。
- `run_example.sh`：端到端演示；`output/` 为其真实运行产物。

## 运行

```bash
bash run_example.sh    # 期望 exit 0
```

正例链路：parse_contract → 骨架落地 → merge 结论 → lint(--strict) → validate →
render(HTML) → manifest → selfcheck（G1-G6 全 PASS）。
负例链路：lint_review 检出 `bad_review_report.md` 的植入缺陷并以 exit 2 拒绝；
脚本断言该失败「如期发生」，否则自身 exit 1。
