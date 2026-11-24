---
name: window-backfill-scheduler
description: >-
  时间窗工程与延迟入库补抓。当任务要求把增量文献条目挂到"连续无缝、边界明确"的 UTC
  固定长度窗口链上、处理 Crossref/Europe PMC/出版商 API 中精度不一的日期（date-parts
  只有年/年月/年月日、ISO 时间戳、带时区偏移）、区分 published 与 indexed 时间、
  并把"发表在已关闭窗口但本轮才出现"的延迟入库条目补抓回其原窗口时，使用本 Skill。
  差异化能力：窗口链无缝接续证明（seam_proof）、左闭右开 [start, end) 边界归属规则、
  日期精度区间归一化（[earliest, latest]）、backfill 事件生成（原窗口号+延迟时长+
  late_indexing 原因）、无法定日期条目的 undated 清单。明确不做：源完整性校验
  （HTTP 状态/截断/重试）、跨源去重归并、提醒抑制与通知策略、抓取调度与重试编排。
---

# window-backfill-scheduler：时间窗工程与延迟入库补抓

## 1. 适用场景与边界

适用：案例给出上一轮窗口状态快照（previous_snapshot）、若干源题录响应快照
（Crossref / Europe PMC / 出版商 API 的本地固化 JSON），要求：

1. 从快照窗口终点无缝接续出新窗口（prev.end == next.start），并逐接缝证明无 gap、
   无 overlap；
2. 把源中五花八门的日期（date-parts 年/年月/年月日三种精度、ISO 时间戳、
   带 +08:00 等时区偏移的时间）归一化为 UTC 区间 `[earliest, latest]`；
3. 判定条目归属：**入库（indexed）时间决定增量归属，发表（published）时间决定内容
   窗口**；边界条目（恰好等于窗口端点）按写死规则 **左闭右开 `[start, end)`** 归属；
4. 识别延迟入库条目（published 落在已关闭窗口、本轮才在源中出现），生成 backfill
   事件（原窗口号、延迟时长、原因 `late_indexing`），计入本轮新增但单独标记；
5. 无法定日期的条目进 undated 清单并诚实标注；
6. 汇总为 result.json：本窗口新增 + backfill + seam_proof + undated + change_records。

边界（**本 Skill 明确不做**，属于其他方向）：源响应完整性校验（截断、HTTP 状态、
字段缺失审计）；跨源去重与条目归并；提醒/通知的抑制策略；抓取重试与调度编排。
若案例材料暗示这些问题存在，只在 uncertainty 中诚实记录，不越权处理。

## 2. 运行环境与输入定位兜底

- 平台把本 Skill 安装到 `/skills/weekly-skill`，工作目录 `/app/work`，最终必须写
  `/app/output/result.json`。
- 脚本仅依赖 Python 3 标准库，**永不发起网络请求**；所有字段值必须来自案例材料，
  并附 locator（文件 + JSON 路径）供复核。
- **不假设固定输入布局**。先用 `find` 定位输入（每个取最合理的一个，多个候选时
  在 uncertainty 里说明选择依据）：

```bash
find /input /app -maxdepth 4 -name 'case.json' 2>/dev/null
find /input /app -maxdepth 4 -name 'task.md' 2>/dev/null
find /input /app -maxdepth 4 \( -name '*snapshot*.json' -o -name '*previous*.json' \) 2>/dev/null
find /input /app -maxdepth 4 -name '*.json' 2>/dev/null | head -50   # 源题录响应快照
```

- 若快照/材料文件名与默认约定（`case.json`、`previous_snapshot.json`、`materials/`）
  不同，用各脚本的 `--case-file / --snapshot-file / --materials` 参数显式指定。
- 先读 `case.json` 的 `output_contract`：result.json 的字段以它为准，本 Skill 的
  默认字段是映射模板，不是硬性清单。

## 3. 编号工作流程（完整案例求解闭环）

所有确定性计算交给脚本；模型只做：读 case、判断输入文件归属、核对产物、写
uncertainty 与文字说明。总预算 64 次模型请求 / 900 秒，请把模型请求控制在个位数。

设 `SKILL=/skills/weekly-skill`，`IN=<case.json 所在目录>`，`OUT=/app/output`
（先 `mkdir -p /app/work /app/output`，中间产物写 `/app/work`）。

1. **读 case**：读 `case.json`（case_id、window_config、output_contract、材料清单）
   与 `task.md`，确认窗口长度、时区（应为 UTC）、需新开窗口数。
2. **窗口规划**：
   `python3 $SKILL/scripts/window_planner.py --case-dir $IN --out $WORK/window_plan.json`
   从 previous_snapshot 最后一个窗口终点接续生成当前窗口（另附一个 future 参考窗口
   用于右端点/未来条目归属判定）。
3. **接缝证明**：
   `python3 $SKILL/scripts/seam_proof.py --plan $WORK/window_plan.json --out $WORK/seam_proof.json`
   逐接缝验证 prev.end == next.start，`overall_pass` 必须为 true；若为 false，
   停止并在 result.json 标 `status=partial`，说明哪条接缝断裂。
4. **日期归一化**：
   `python3 $SKILL/scripts/date_normalize.py --case-dir $IN --out $WORK/normalized_items.json`
   把每条目的 published 类与 indexed 类字段归一化为 UTC 区间，记录 precision 与
   locator。
5. **窗口归属**：
   `python3 $SKILL/scripts/assign_windows.py --case-dir $IN --work-dir $WORK --out $WORK/assigned_items.json`
   按 `[start, end)` 判定内容窗口与增量归属，输出 current_additions / backfill 候选 /
   deferred / undated 分类。
6. **延迟入库补抓**：
   `python3 $SKILL/scripts/backfill.py --work-dir $WORK --out $WORK/backfill_events.json`
   对 published 落在已关闭窗口、indexed 落在当前窗口的条目生成 backfill 事件
   （original_window、delay_days、reason=late_indexing、locator）。
7. **组装结果**：
   `python3 $SKILL/scripts/assemble_result.py --case-dir $IN --work-dir $WORK --out /app/output/result.json`
   生成含 case_id + output_contract 全部字段 + sources + uncertainty +
   change_records 的 result.json。
8. **模型复核（少量请求）**：抽查 result.json——seam_proof 全部通过；边界条目
   （左端点入当前窗、右端点归下一窗）归属正确；backfill 事件原窗口号与延迟时长
   合理；undated 清单无漏；每个字段值都能在材料中找到 locator。发现问题改脚本
   参数重跑，不要手改 JSON 产物。
9. **异常即 partial**：任一输入缺失/无法解析、接缝断裂、output_contract 字段无法
   填全时，仍写出 result.json，`status="partial"`，在 uncertainty 中逐条说明限制
   与缺失原因。宁可 partial 也不可编造。

## 4. 输出契约（result.json 默认字段）

以 case.json 的 `output_contract` 为准；默认映射如下：

| 字段 | 内容 |
| --- | --- |
| `case_id` | 原样取自 case.json |
| `status` | `complete` / `partial` |
| `window_plan` | 窗口链（previous closed + current + future reference），UTC ISO 边界 |
| `seam_proof` | 逐接缝证明（prev_end、next_start、gap_seconds=0、overlap_seconds=0、pass） |
| `current_window_additions` | 本轮新增且内容窗口=当前窗口的条目（含 low_precision、boundary_left 等 flag 与 locator） |
| `backfill_events` | 延迟入库补抓事件（original_window、delay_days、reason=late_indexing、locator） |
| `deferred_items` | 内容窗口落在未来窗口的条目（如恰好等于右端点，归下一窗口） |
| `undated_items` | 无法定日期的条目及原因，诚实标注 |
| `sources` | 每个输入文件的路径、条目数、角色 |
| `uncertainty` | 精度不确定、时区假设、输入选择依据等 |
| `change_records` | 本轮流水线各步骤记录（脚本、输入、输出、计数） |

## 5. 异常处理与诚实 partial

- 缺 case.json / snapshot / 材料文件：能定位多少做多少，result.json 标 partial 并
  在 uncertainty 列出缺失项与 `find` 证据。
- 某条目日期无法解析：进 undated_items，附原始字段值与 locator，不猜日期。
- 精度跨越多个窗口（如只有年份）：计入本轮新增（前提 indexed 在当前窗口）但打
  `low_precision_date` flag，content_window 标 `indeterminate`，写入 uncertainty。
- seam_proof 不过：不要静默继续，标 partial 并指明断裂接缝。
- 任何字段值不得来自模型记忆；只能来自案例材料文件。

## 6. 最小调用示例说明

`examples/minimal/` 是**合成示例**（synthetic，数据为本 Skill 作者新造，DOI 仅为
格式样例）。在 bundle 根目录一键端到端运行：

```bash
python3 scripts/run_minimal_example.py
```

产物写入 `examples/minimal/output/`（window_plan.json、seam_proof.json、
normalized_items.json、assigned_items.json、backfill_events.json、result.json）。
示例刻意覆盖：1 条延迟入库、1 条左端点、1 条右端点（归下一窗口）、1 条仅年份
低精度、1 条 +08:00 时区、1 条无日期。详见 `examples/minimal/README.md`。

## 7. 与其他方向的边界划分

| 方向 | 归属 |
| --- | --- |
| 窗口链连续性、边界归属、日期归一化、延迟入库补抓 | **本 Skill** |
| 源响应完整性（截断/状态码/字段缺失审计） | 其他 Skill（source-integrity 方向），本 Skill 仅在 uncertainty 记录疑点 |
| 跨源去重、同一文献多源归并 | 其他 Skill，本 Skill 按源原样处理，不做合并 |
| 提醒抑制、通知频率策略 | 其他 Skill |
| 抓取调度、失败重试编排 | 其他 Skill，本 Skill 完全离线，永不联网 |
