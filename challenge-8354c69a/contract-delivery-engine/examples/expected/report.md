# 实验结果解释与异常分析 — 交付报告

| 项 | 值 |
|-|-|
| case_id | `synthetic-delivery-demo-001` |
| status | **success** |
| 字段数 | 7 |

## 结果趋势
载荷先升后降，峰值出现在位移 3.5mm 附近（traces.json::peak_stats）

## 异常点
trace_013、trace_027 峰值超出 IQR×1.5（findings.json::peak_outlier_traces）

## 可能原因
候选1: 样品差异（支持: findings.json::peak_stats；排除: 无饱和签名）

## 复核步骤
重跑 run 脚本复算（findings.json）；回查 trace_013.txt 第 30-40 行

## 后续实验建议
对离群样加做平行重复（依据 findings.json::thresholds）

## 依据与风险
依据 findings.json 全部阈值字段；风险: 原型误识别（task.md）

## 确认项
单位约定需专家确认（task.md 未注明）

## 元信息
### limitations

### sources
- findings.json (合成示例)

### uncertainty
- 尚未开始分析

### change_records
- scaffold: partial-first
- set field: 结果趋势
- set field: 异常点
- set field: 异常点
- set field: 可能原因
- set field: 复核步骤
- set field: 后续实验建议
- set field: 依据与风险
- set field: 确认项
- 示例：全部字段补齐，置 success
