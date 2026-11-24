# 窗口语义（window semantics）

本文件写死本 Skill 的时间窗语义，脚本（window_planner / seam_proof /
assign_windows）与本文档不一致时以本文档为准并修正脚本。

## 1. UTC 固定边界窗口链

- 窗口是 UTC 上的半开区间 `[start, end)`，长度固定（案例给出，如 7 天），
  只允许 UTC，不允许本地时区或夏令时。
- 窗口链 = previous_snapshot 中的已关闭窗口 + 本轮新开的 current 窗口 +
  1 个 future 参考窗口（仅供右端点/未来日期归属判定，不是本轮成果）。
- **无缝接续**：新窗口的 start 必须等于快照最后一个窗口的 end
  （prev.end == next.start）。不允许以"当前时刻"或"抓取时刻"作为起点——
  那会制造 gap 或 overlap。
- **接缝证明**（seam_proof.py）：对链中每对相邻窗口计算
  `gap_seconds = max(0, next.start - prev.end)` 与
  `overlap_seconds = max(0, prev.end - next.start)`，
  两者都为 0 才 pass；全部接缝 pass 则 overall_pass=true。
  任何一条不通过，result.json 必须标 `status=partial` 并指明断裂接缝。

## 2. 边界规则：左闭右开 `[start, end)`

- published 时间恰好等于某窗口 `start` → 归**该**窗口（flag `boundary_left`）。
- published 时间恰好等于某窗口 `end` → 归**下一**窗口（flag `boundary_right`），
  本窗不收，进入 `deferred_items`，等下一轮自然落入。
- 该规则对链中所有窗口一致适用，保证每个时刻在全链上有且仅有一个归属窗口。

## 3. 日期精度与归一化

源日期统一归一化为 UTC 区间 `[earliest, latest]`（两端皆闭），区间宽度表达
精度不确定：

| 源形式 | precision | 区间 |
| --- | --- | --- |
| date-parts `[[2026]]` | year | [2026-01-01T00:00:00Z, 2026-12-31T23:59:59Z] |
| date-parts `[[2026,10]]` | month | 该月首末瞬间 |
| date-parts `[[2026,10,8]]` / `2026-10-08` | day | 当日首末瞬间 |
| ISO 时间戳（Z 或 ±HH:MM） | second | 偏移换算为 UTC 后 earliest == latest |
| 无时区标记的时间戳 | second | 假定 UTC 并记 `assumed_timezone` 与 uncertainty |

例如 `2026-10-20T08:30:00+08:00` 归一化为 `2026-10-20T00:30:00Z`。

## 4. 归属判定

- **入库（indexed）时间决定增量归属**：条目是否算"本轮新到"由 indexed 落在
  哪个窗口决定；indexed 缺失时按本轮处理并打 flag + uncertainty。
- **发表（published）时间决定内容窗口**：用归一化区间判定：
  - earliest 与 latest 落在同一窗口 → 内容窗口唯一确定；
  - 区间跨越多个窗口或超出链覆盖（如仅年份）→ `indeterminate`，
    打 `low_precision_date`，计入本轮新增但单独标记并写入 uncertainty，
    不强行指定窗口、不猜更精确的日期。
- 分类优先级：无 published → undated；内容窗口=current → current_addition；
  内容窗口为 closed → backfill；内容窗口为 future → deferred；
  indeterminate → low_precision。

## 5. locator 约定

每个进入结果的值都带 locator：`<材料文件路径>#/items/<序号>/<字段>`，
例如 `materials/crossref_response.json#/items/0/published`，供复核人员直接
定位到原始字段值。
