# work_plan.md — risk-warden 六步勾选清单

生成时间：2026-11-24T14:16:23Z
case_id：synthetic-ec02b694-001

- [x] 1. intake 与首份 partial 落盘（warden_boot 已完成：intake_manifest.json + result.json[partial]）
- [ ] 2. 汇总异常事实（约束冲突/缺失材料/指标矛盾/设备报错/权限问题），运行 scripts/triage.py 得到机器可判定动作
- [ ] 3. 按 triage 动作执行主体工作：proceed / proceed_with_degradation（降级并记录）/ handoff_to_human（转人工，停止自主决策）/ terminate（终止并写明理由）
- [ ] 4. 填充 output_contract 全部字段；每条推荐参数值必须附可行性证据引用，或显式标注"待确认"
- [ ] 5. 交付前运行 scripts/final_audit.py；存在违例时按其结论回退 partial 并写明 partial_reason
- [ ] 6. 对账：核对 status / uncertainty / change_log 一致后交付 /app/output

预算提醒：剩余约 8 次模型请求时立即停止改进，转入第 4–6 步收尾。
