# 合成示例（synthetic example）说明

**本目录全部数据均为合成示例（synthetic）**：case.json、previous_snapshot.json、
materials/ 下两个源响应快照均为本 Skill 作者新造；DOI 字符串（如
10.1038/nature12373）仅借用真实存在的格式样例，条目内容、日期、窗口状态均为
虚构，不对应任何真实抓取结果。

## 运行

在 bundle 根目录：

```bash
python3 scripts/run_minimal_example.py
```

产物写入 `examples/minimal/output/`：window_plan.json、seam_proof.json、
normalized_items.json、assigned_items.json、backfill_events.json、result.json。

## 窗口设定

- 快照含两个已关闭窗口：W2026-10-05（10-05~10-12）、W2026-10-12（10-12~10-19）；
- 本轮无缝接续当前窗口 **W2026-10-19**（2026-10-19T00:00:00Z ~
  2026-10-26T00:00:00Z），另附 future 参考窗口 W2026-10-26 供右端点归属判定。

## 刻意设计的 6 个条目

| DOI | 设计意图 | 期望分类 |
| --- | --- | --- |
| 10.1038/nature12373 | published 2026-10-08（已关闭窗口 W2026-10-05），indexed 2026-10-21 本轮才出现 | backfill（late_indexing） |
| 10.1126/science.adr0001 | published 日区间 earliest 恰等于当前窗口左端点 2026-10-19T00:00:00Z | current_addition + boundary_left |
| 10.7554/eLife.99001 | published 只有年份 [[2026]]，区间跨越多个窗口 | low_precision（计入新增并标记） |
| 10.1016/j.cell.2026.10.001 | published 恰等于右端点 2026-10-26T00:00:00Z | deferred + boundary_right（归下一窗口） |
| 10.1101/2026.10.18.654321 | published 带 +08:00 偏移 → UTC 2026-10-20T00:30:00Z | current_addition |
| 10.15252/embj.2026115001 | published 为 "in press"，无法解析 | undated（诚实标注） |

## 验收点

- seam_proof 三条接缝全部 pass（gap=0、overlap=0）；
- backfill 事件恰好 1 条，original_window=W2026-10-05，delay_days≈12.38；
- 左端点条目在当前窗口新增中，右端点条目在 deferred_items 中；
- undated_items 恰好 1 条且注明不猜测。
