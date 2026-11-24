# 合成示例任务（synthetic demo task）

> 本文件是合成示例的一部分，模拟评测 harness 下发的 task.md。

给定：

- `case.json`：窗口配置（7 天、UTC、新开 1 个窗口）与 output_contract；
- `previous_snapshot.json`：上一轮窗口状态（两个已关闭窗口，最后一个终于
  2026-10-19T00:00:00Z）；
- `materials/`：两个源题录响应快照（crossref、europmc），共 6 条合成条目。

要求：

1. 从快照终点无缝接续出当前窗口（另附 future 参考窗口），逐接缝证明
   prev.end == next.start；
2. 归一化全部条目的 published / indexed 日期为 UTC 区间；
3. 按左闭右开 [start, end) 判定内容窗口与增量归属；
4. 延迟入库条目生成 backfill 事件（原窗口号、延迟天数、late_indexing）；
5. 无法定日期的条目进入 undated 清单并诚实标注；
6. 组装 result.json，包含 output_contract 全部字段及 sources、uncertainty、
   change_records。
