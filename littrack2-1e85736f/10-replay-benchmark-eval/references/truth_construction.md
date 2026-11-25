# 真值构造假设与局限

## 1. 构造规则（机械、无人工标注）

输入：同一来源的两份快照——t_prev（上一次增量导入状态，如组织方的
`previous_snapshot.json`）与 t_now（当前 API 响应快照），以及时间窗口
`[window.start, window.end]`（两端含）。

1. **对齐**：按规范化匹配键（DOI > arXiv > 标题，见 `metrics_definitions.md`）
   对齐两侧记录；
2. **新增候选**：`added = t_now − t_prev`（在 t_now 出现而在 t_prev 不存在的记录）；
3. **按 published 与窗口修正**：
   - published 在窗口内 → `truth_new`（应被发现的新增）；
   - published 早于窗口起点 → `truth_backfill`（晚入库的旧文献，
     追踪系统不应把它报为"新文献"）；
   - published 晚于窗口终点 → `truth_out_of_window`；
   - published 缺失/无法解析 → `unclassifiable`，诚实单列，绝不猜测。

注意：分类依据是 **published（文献发表日期）** 而非 ingested_at（入库时间）。
backfill 的典型形态正是"published 很旧、ingested_at 落在窗口内"的晚入库记录；
若改用 ingested_at 分类会把这类旧文献错标为 new，失去真值意义。ingested_at 仅作
辅助证据保留在输出中。

## 2. 前提假设

- A1：两份快照来自**同一来源、同一收录口径**，差异只来自时间推进；
- A2：记录具有稳定标识符（DOI / arXiv / 标题至少其一）且在两份快照中一致；
- A3：published 字段可信（出版商给出的发表日期）；
- A4：窗口语义为闭区间，且与追踪系统的提醒窗口一致。

## 3. 已知局限

- L1：**单快照无法构造真值**。只有 t_now（或只有导入状态）时，"新增"无从谈起；
  此时必须降级 partial 并说明缺哪一份快照，绝不编造真值。
- L2：**元数据漂移**。若同一条记录在两份快照间被改写标题且缺 DOI/arXiv，
  会被误判为"removed + added"。缓解：warnings 中报告 removed 计数，人工抽查；
  本 Skill 不做模糊匹配猜测。
- L3：**published 口径不统一**（online first vs issue date 等）可能使临界日期记录
  在 new/backfill 之间错分。缓解：把窗口边界 ±3 天内的记录列入人工复核（当前实现
  如实输出 published，便于复核）。
- L4：**真值是"收录层真值"**，不是"学术重要性真值"：它度量追踪系统是否发现了
  快照层面的新增，不评价文献相关性（相关性筛选属另一方向，不在本 Skill 范围）。
- L5：**候选清单缺失时**，基准（真值集）仍可产出，但指标无从计算；此时只交付
  truth.json 与构造说明，metrics 相关字段为 null，status=partial。
- L6：unclassifiable 记录不参与任何指标分母；若其占比高，应在报告中显式提示
  真值质量风险。

## 4. 诚实性约定

- 真值集永远只由快照对机械生成，生成过程记录 `source_basis`；
- 任何无法构造/无法分类的情形都显式列出，不用启发式补齐；
- 合成示例显式标注 synthetic，绝不冒称真实文献或真实检索结果。
