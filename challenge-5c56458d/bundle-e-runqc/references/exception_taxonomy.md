# 异常分类与处置（exception taxonomy）

所有异常归入以下六类之一并写入 analysis_notes.md 的异常清单；
不允许出现"悄悄跳过"的第七类。

## E1 输入缺失（missing input）

现象：声明的文件不存在、目录为空。
处置：列出 /input 实际内容；result.json 相应字段置 unable_to_determine
并注明缺失项；不虚构数据。

## E2 连接与权限（connection / permission）

现象：库文件损坏、只读约束冲突、权限不足。
处置：报告错误原文；本流程从不写源库；派生产物写 /app/work 下的新文件。

## E3 语义歧义（semantic ambiguity）

现象：字段名与任务用词不符、近义字段、未知编码。
处置：歧义清单 + 实际采用的映射 + 依据；无依据时置 unable_to_determine，
不猜。

## E4 查询失败（query failure）

现象：SQL 报错、超时、空结果。
处置：保留报错原文；定位（表名/列名/条件）后修复重跑并记录
"错误→原因→修复"；空结果逐条件放宽定位，不删条件。

## E5 数据质量（data quality）

现象：缺失值、重复记录、异常值、类型不一致、行数膨胀。
处置：先计数、声明处置规则、再统计；处置前后行数都留痕；0 与 NULL
不得混同。

## E6 结果不可解释（unexplainable result）

现象：结果与已知口径/参考冲突且无法定位原因。
处置：如实并列"结果"与"冲突"，标注不确定性；禁止为自洽而改数。

## 预算耗尽的处置

任一门因预算中断时：已通过的门的产物即交付物；result.json 保持
status=partial、limitations 写明"在 G<n> 中断，已完成 G0..G<n-1>"；
checkpoint 使续跑不重做已完成步骤。
