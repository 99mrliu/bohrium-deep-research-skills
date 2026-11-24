# 质控报告（selfcheck）

- 生成时间：2026-11-24T22:29:25
- 交付目录：`/Users/liuhengshen/Desktop/bhr_product/2e2c-five/bundle-e-qc/outputs/examples/synthetic/output`
- 依据：references/qc_gates.md（G1–G6）
- 总体门：**PASS**（FAIL 0 / WARN 0 / PASS 6）

| 门 | 名称 | 结果 | 说明 |
| --- | --- | --- | --- |
| G1 | 契约字段齐全 | PASS | 契约校验通过：8 个契约字段齐全且类型匹配；case_id 一致；status=complete 规则满足。 |
| G2 | 状态诚实 | PASS | status=complete，不确定性/过程记录齐备 |
| G3 | 结论-条件一致 | PASS | lint 通过（0 硬违规，0 警告） |
| G4 | 证据锚定密度 | PASS | 锚点 36 个（≥3） |
| G5 | 产物可复算校验 | PASS | 复算 10 个文件哈希全部匹配 |
| G6 | 交付物齐全 | PASS | review_report.md / result.json / 预览(review_report.html) 齐备 |
