# QC 报告（budget-warden-qc）

- 结论：**ok=true**
- 结果文件：`examples/run_out/output/result.json`
- 自动修复 0 处；未决 critical 0 项、major 0 项

## 检查明细

- ✅ **Q1** [info] case_id 正常：synthetic-demo-60a8202d-e001
- ✅ **Q2** [info] 必备顶层字段齐全
- ✅ **Q3** [info] output_contract 镜像完整（9 字段）
- 🟡 **Q3b** [minor] 契约空值字段：review_notes
- ✅ **Q4** [info] 全部记录与边均带 source locator
- ✅ **Q5** [info] stub 比例 16.7%（1/6）
- ✅ **Q6** [info] status 与完成阶段一致（ok/stage3）
- ✅ **Q7** [info] checkpoint 链完整：stage [0, 1, 2, 3]
