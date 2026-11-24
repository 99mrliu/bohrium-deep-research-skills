# 审查任务（合成示例）

请对 `manuscript.md` 执行**方法设计与统计报告完备性**门禁审查
（bundle-c-methods-stats-gate），要求：

1. 用确定性模式扫描建立统计报告要素矩阵（样本量、检验名称、p 值、CI、
   效应量、多重比较校正、随机化、盲法、对照、重复、剔除、软件、误差棒）。
2. 按 references/stats_reporting_checklist.md 的 16 条清单逐条登记
   pass / fail_reporting（报告不全）/ fail_design（方法缺陷）/ unable_to_check。
   必须把"方法本身有缺陷"与"方法可接受但报告不全"分开，禁止笼统的
   "统计报告不规范"式评语。
3. 每条 fail 必须给出原文定位（小节 + 偏移 + 引证句）或显式 absent 说明，
   并按 methods_severity_rubric.md 标注 critical/major/minor。
4. 产出 result.json（含 case_id 与 output_contract 全部字段）与
   review_report.md（先方法缺陷、再报告不全、再待复核，分组呈现）。
5. 无法从文本判定的条目如实记 unable_to_check，待复核不凭空补结论。
