# SYNTHETIC EXAMPLE / 合成示例 —— 合成任务说明

> 本文件为虚构任务说明，仅用于演示 deck-runbook-governor 的六阶段治理流程，
> 不对应任何真实测评案例。

把 `materials/synthetic_paper.txt`（合成短文）组织成一份 12 分钟、10 页的
学术汇报 deck，听众为跨学科评审委员会。要求：

1. 提取研究问题、方法、结果与限制，形成主线；数字逐字转录并带页级定位。
2. 每页恰好一个 message，附讲稿备注；图表引用与页内结论一一对应。
3. 按 work_order 指定的模板生成可编辑演示文件（模板在本合成示例中缺席，
   用于演示"模板缺失"异常的记录路径）。
4. 导出真实渲染的 PDF/PNG 预览，并交付页级证据映射。
5. result.json 含真实 case_id 与 output_contract 全部五个根字段
   （editable_deck / export_preview / content_map / compliance_checks /
   exceptions），状态诚实。
