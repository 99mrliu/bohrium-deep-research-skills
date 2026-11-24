# 报告模板说明（build_report.py 的组装逻辑）

## 章节与数据来源

| 章节 | 来源产物 | 缺失时 |
|---|---|---|
| 1 检索范围 | search_protocol.json（search_date、逐库字段/日期/语种、快照声明） | 标"数据缺失"并进入缺失清单 |
| 2 流程计数 | counts.json | 同上 |
| 3 流程图 | flow.md（render_flow.py 产物） | 同上 |
| 4 排除理由分布 | decisions_summary.json 或 counts.json 的 exclusion_reasons | 同上 |
| 5 双人标注一致性 | decisions_summary.json 的 agreement | 同上 |
| 6 待人工确认 | counts.json 的 needs_human | 同上 |

## 组装纪律

1. **渲染层不生成新数字**：报告只复述输入产物；一致性百分比这类派生值
   由模板从 agreement 原始计数现算并给出算式上下文（agreed/both_judged）；
2. **缺失要喊出来**：任何一节缺数据即标注"数据缺失"，末尾汇总缺失清单——
   空白章节比编造一节诚实；
3. **pending 措辞固定**：待人工确认一节固定声明"模型判定仅为 pending 建议"，
   防止报告读者把建议当结论；
4. **与流程图同源**：报告内嵌的 Mermaid 与交付 SVG 来自同一份 counts，
   禁止手工改其中一份。

## 改写指引

模板面向题录筛选阶段的通用结构；案例有额外合同字段要求时，
可以增节（在现有节后追加），但不要删节——删节会丢失缺失标注机制。
