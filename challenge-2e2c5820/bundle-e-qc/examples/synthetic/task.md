# 任务书（合成示例，非正式案例数据）

case_id：SYNTH-QC-001

请对 `case.json` 中的 3 版候选实验方案（plan_v1 / plan_v2 / plan_v3）做可行性审查，
完成以下七类约束核查：

1. 科学合理性（工艺窗口、材料依据）
2. 资源可得性（设备、手套箱、预订规则）
3. 预算约束（合同上限 20000 元，需真实算术核算）
4. 时间排期（机时上限 32 小时、4 周截止）
5. 安全与合规（手套箱操作规范）
6. 参数域合法性（退火温度 100-200°C、XRD 轮次 1-4）
7. 可复现性（结论须带证据锚点，如 [L12]、（第3节））

## 交付要求

- `/app/output/result.json`：含 case_id、`output_contract` 全部字段、status、sources、
  uncertainty、change_record；状态必须诚实（complete/partial/failed）。
- `/app/output/review_report.md`：人读审查报告，结论词与条件清单一致，关键结论带锚点。
- 渲染预览（HTML，条件允许时另出 PDF/PNG）。
- manifest（输入输出 SHA-256）与 qc_report（selfcheck）。

## 诚实要求

未经合同确认的信息不得写成事实；无法完成的约束类别保持 partial 并在 uncertainty
中逐条说明缺口。禁止编造数据。
