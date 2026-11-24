# 输入形态与取证适配说明

平台固定三类案例形态（运行时以实际 /input 为准，本说明仅先验）：

1. **197 条原始弯曲 traces + 样品工作簿 + MATLAB 脚本**
   - 重点：F1（重复 trace 文件）、F3（载荷通道饱和）、F8（.m 脚本引用的文件名
     与数值常量是否与实到数据一致）。
2. **5 split × 2 estimator Iris 计算实验记录**
   - 重点：F2（记录行重复）、F6（两个文件数值完全相同 → 同一份结果的重复提交）。
   - 计算实验无湿测量，finding 的处置不得引用「样品」「批次」等湿实验概念。
3. **Cefixime 12-sheet 主工作簿 + 论文 PDF**
   - 重点：F5（mg/mL vs µg/mL 等单位歧义）、F7（隐藏 sheet）、
     F6（sheet 间数值重叠）。

## result.json 契约要点
- `case_id` 原样复制自 case.json；`output_contract` 全部字段逐一填写，
  无法填写的字段保留 null 并在 limitations 点名（诚实 partial）。
- `sources` 至少包含 forensics_report.json 与被引用的原始文件定位。
- `uncertainty` 登记：取证启发式的误判风险、单位歧义、专家确认项。
- `change_records` 记录每次状态迁移（partial → success 必须对应一次 flags 处置记录）。
