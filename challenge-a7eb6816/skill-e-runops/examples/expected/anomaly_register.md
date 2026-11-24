# 异常登记表 anomaly_register

- 条目总数: 6
- 存在 halt 项: 否
- 分类统计: confidentiality=3, conflict=1, length_conflict=1, missing_input=1

| kind | locator | evidence | disposition | note |
| --- | --- | --- | --- | --- |
| missing_input | case.json -> inputs/missing_table.csv | 引用的路径 'inputs/missing_table.csv' 在磁盘上不存在 | mark-gap | 相关内容留空并写入 limitations；待人工补充后重跑 |
| conflict | 锚点「能量密度」跨文件: main.md, task.md | main.md:3 取值 320; task.md:8 取值 350 | mark-gap | 数值冲突，保守上报；须人工确认唯一口径后方可写入交付物 |
| confidentiality | main.md:17 | 命中标记「未发表」: ## 未发表数据声明 | proceed | 仅本地处理、禁止外发；限制须写入 result.json 的 limitations |
| confidentiality | main.md:19 | 命中标记「保密」: 本节涉及未发表数据：界面阻抗原位演化曲线与第三方安全测试结果尚未投稿，保密期内仅本地处理，不得外传。 | proceed | 仅本地处理、禁止外发；限制须写入 result.json 的 limitations |
| confidentiality | main.md:19 | 命中标记「不得外传」: 本节涉及未发表数据：界面阻抗原位演化曲线与第三方安全测试结果尚未投稿，保密期内仅本地处理，不得外传。 | proceed | 仅本地处理、禁止外发；限制须写入 result.json 的 limitations |
| length_conflict | task.md vs main.md | task 字数上限 300 字 < 源文 35 个关键信息点×25 字 ≈ 875 字下限 | mark-gap | 篇幅约束冲突：须删减覆盖范围并在 limitations 声明，或与需求方确认 |
