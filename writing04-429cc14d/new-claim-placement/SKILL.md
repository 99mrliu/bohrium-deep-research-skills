---
name: claim-placement
description: >-
  以句子和原文证据为单位制作可复核的引用位置计划，不以段末引用覆盖整段。 用于科研稿件的参考文献与引用管理。
---

# 论断级引用定位

本技能的重心：以句子和原文证据为单位制作可复核的引用位置计划，不以段末引用覆盖整段。 详细判定边界见 [references/method.md](references/method.md)。

## 平台运行契约与完整任务
读取 /input/case.json、/input/task.md 和实际材料；若有 environment/resources.yaml，按其中声明寻找资源。不要凭文件名或标签猜测内容；对 PDF 用文本提取和页面检查，Office 文件保留可编辑形式。将临时文件写 /app/work，交付物写 /app/output。先保存可恢复的初稿和 result.json，再迭代。result.json 逐字保留 case_id 和 output_contract 的全部字段，字段结构与类型遵守原案例；记录产物路径、来源位置、修改、状态与未完成事项。无法验证或未完成时明确 partial 及原因，不凭记忆补造。

按 task.md 完成全部要求：读取稿件和全部文献库，建立原始记录与改动映射；逐句检查引用是否支持论断；仅有可靠依据时修正位置、去重和元数据；按要求的格式重排引用及参考文献，包含图注、脚注和附录；输出可编辑稿件、同步文献表与证据/改动台账。无权或无法确认的保留并标待核，不把未检出当作不存在。编号前保留稳定文献键，复核正文到文末与文末到正文的双向关系。样式要求不明时说明假设，禁止声称完全符合未核验规范。对于 DOCX 等交付文件生成实际 PDF/PNG 预览并检查；工具不可用时注明限制。

脚本是针对特定局部的辅助工具，不直接读取任意案例，也不替代语义判断。Agent 先从真实材料抽取例子同结构的 JSON（保留定位符），运行脚本并审查报告，再将确认的修改应用到实际稿件。处理范围之外按上述工作流完成。脚本仅依赖 Python 3 标准库；在 /skills/weekly-skill 下运行，示例命令见下。

## 合成示例
examples/input.json 为虚构数据，不代表真实论文或评测结果。运行：

```sh
python3 scripts/check.py examples/input.json /tmp/claim-placement-example.json
cat /tmp/claim-placement-example.json
```

期望：反例 s1 虽有逐字锚点仍需语义核对；s2 为缺证据。
