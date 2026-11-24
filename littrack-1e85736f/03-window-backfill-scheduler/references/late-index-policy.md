# 延迟入库补抓策略（late-index policy）

## 1. 两种时间，两种用途

- **published（发表时间）**：内容属性，决定条目属于哪个内容窗口。
- **indexed / created（入库时间）**：流程属性，决定条目何时在源中可见、
  属于哪一轮增量。

二者经常不一致：出版商先于入库上线电子版（indexed < published），或源端
延迟数周才把旧文献编入索引（indexed >> published）。本 Skill 只关心后者。

## 2. backfill 触发条件

一条目同时满足：

1. published 归一化区间完整落在某个**已关闭**窗口 W_old（W_old.end ≤ 当前窗口
   start）；
2. 本轮才在源中出现：indexed 落在当前窗口（indexed 缺失时按本轮处理并打
   flag + uncertainty，不静默放过）。

则生成 backfill 事件：

```json
{
  "doi": "...",
  "original_window": "W2026-10-05",
  "arrival_window": "W2026-10-19",
  "delay_days": 12.3842,
  "reason": "late_indexing",
  "locators": {"item": "...", "published": "...", "indexed": "..."}
}
```

- `delay_days = (indexed − published.latest) / 86400`，用 published 区间**右端**
  计算，得到延迟的保守下界（真实延迟只会更长）；保留 4 位小数。
- backfill 条目**计入本轮新增**（它是本轮才知道的知识），但在 result.json 中
  单列 `backfill_events`，与 `current_window_additions` 分开，绝不混入。
- 若 indexed 落在比当前更早的窗口（arrival_not_in_current_window），仍然生成
  事件但打 flag 提示可能已被上一轮导入——是否重复属于去重方向的职责，
  本 Skill 只如实记录。

## 3. 低精度日期条目

- 仅年份/月份的 published 区间常跨越多个窗口，无法唯一定窗：不猜、不取区间
  中点，标 `content_window=indeterminate` + `low_precision_date`，计入本轮
  新增（前提 indexed 在当前窗口）并写入 uncertainty。
- 低精度条目**不**触发 backfill：无法证明它发表在已关闭窗口，按保守原则只
  标记不补抓。

## 4. 无日期条目（undated）

- 无 published 字段，或字段值无法解析（如 `"in press"`、空串）：进入
  `undated_items`，记录原因（`no_published_date` /
  `unparseable_published_date`）、原始值与 locator。
- 明确写出"不做猜测"的 honest_note；这是诚实 partial 的一部分，不是缺陷。

## 5. 与相邻方向的边界

- 条目是否已在本地库中（重复导入判定）→ 去重/幂等方向，本 Skill 不查重。
- 源为何延迟入库、响应是否被截断 → 源完整性方向，本 Skill 只在 uncertainty
  中记录疑点。
- backfill 事件是否触发提醒 → 提醒策略方向，本 Skill 只产出事件本身。
