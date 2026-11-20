# 人工复核清单（review_checklist）

> 由 risk_grade.py 自动生成；分级日期 2026-11-20。

## C-low（grade=low, score=10）
- [ ] 重新查询官方登记簿，更新 query_date 与 staleness 备注
- [ ] 在结论中写明'仅观察到的链接，不构成完整同族'，必要时人工核查 INPADOC
- [ ] 列出未覆盖的语料缺口（如未提供的同族成员/对比文件），结论限缩到已覆盖范围
- [ ] 补充第二独立来源；补不到则在结论中标注'单一来源'
- [ ] 先跑 scripts/quote_audit.py 修复引文，再重新分级
- [ ] 按 rules/legal_status_protocol.md 执行登记优先查询；仍未知则保持'未知'措辞
