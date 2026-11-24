---
name: idempotent-retry-journal
description: >-
  文献增量导入的「失败重试与幂等恢复」专项 Skill。触发场景：最新文献发现与追踪任务中
  需要把本地固化的 Crossref / Europe PMC / 出版商 API 题录快照做增量导入，且存在源
  故障（截断、限流、超时、结构漂移、缺字段、空窗口）、上一轮中断需断点续跑、或必须
  保证重跑零二次推送时。差异化能力：六类故障分类与确定性退避计划（retry_journal.jsonl）、
  「源×窗口」粒度 checkpoint 断点续跑、按投递键去重的幂等投递（delivery_log.jsonl）、
  诚实降级与 partial 标注。边界：全程离线、只处理已固化材料；不做源真实性评分、窗口
  规划、提醒内容策略与 QA 评分。
---

# idempotent-retry-journal：失败重试与幂等恢复

## 1. 适用场景与边界

**适用**：最新文献发现与追踪类案例中，源响应已被固化为本地材料（JSON 快照），
要求完成增量导入并保证：

- 任一源故障时不整体崩溃：按故障分类决定 可恢复重试 / 跳过并降级 / 阻断；
- 每次尝试留痕：`retry_journal.jsonl` 记录 attempt_no、故障类别、确定性退避计划
  （如 5s/30s/120s；离线不真的 sleep，只记录计划与决策）；
- 断点续跑：`checkpoint.json` 按「源 × 窗口」记录完成状态，重跑已完成的源直接跳过；
- 幂等投递：`delivery_log.jsonl` 按 `case_id|window|item_key` 去重，重跑零二次推送；
- 诚实降级：不可用源进 `degraded_sources` 并写明原因，`status=partial`，
  `uncertainty` 明确缺失覆盖。

**硬性边界**：完全离线，脚本永不发起网络请求；不得编造 DOI、元数据、检索结果；
任何产出字段值必须来自案例材料，并带 locator（文件 + JSON 路径）供复核。

## 2. 运行环境与输入定位兜底

- Python 3（仅标准库），工作目录 `/app/work`，最终交付 `/app/output/result.json`。
- 不假设固定布局，先用 `find` 定位输入：

```bash
CASE=$(find /input /app -name case.json 2>/dev/null | head -n 1)
[ -n "$CASE" ] || { echo "case.json not found"; exit 1; }
find "$(dirname "$CASE")" -name '*.json' | head -n 50   # 查看材料布局
mkdir -p /app/work /app/output
```

- case.json 中 `sources[].material` 的相对路径以 case.json 所在目录为基准解析
  （脚本已内置）；若材料实际在别处，用 `find / -name '<材料文件名>' 2>/dev/null`
  定位后在 case 副本中改写路径，改写记录进 `change_records`。

## 3. 编号工作流程

1. **读 case**：解析 `case_id`、`task`、`window`、`sources[]`、`output_contract`。
2. **勘察材料**（可选但推荐）：对每个 `sources[].material` 先跑一次
   `python3 scripts/failure_classify.py <材料路径>`，预先了解哪些源健康、
   哪些会触发哪类故障。
3. **跑引擎**：
   `python3 scripts/retry_engine.py --case "$CASE" --work /app/work`
   产出 `retry_journal.jsonl`、`checkpoint.json`、`delivery_log.jsonl`、`runs.jsonl`。
4. **检查断点与降级**：`python3 scripts/checkpoint.py show /app/work/checkpoint.json`，
   确认哪些源 completed、哪些 degraded 及原因。
5. **可恢复故障的处置**：若 degraded 源的故障是可恢复类
   （rate_limit/timeout/parse_error），且材料已有修复版/替代快照，把材料
   指向修复版后**重跑步骤 3** —— 已完成的源会被 checkpoint 跳过，只补
   未完成部分。阻断类（source_revision）不得自动重试，保留降级并说明。
6. **组装交付**：
   `python3 scripts/assemble_result.py --case "$CASE" --work /app/work --out /app/output/result.json`
7. **复核**：确认 result.json 含 `case_id` + `output_contract` 全部字段 +
   `sources` + `uncertainty` + `change_records`；每条 item 带 locator，
   用 locator 回查材料原文抽查 1~2 条。
8. **幂等自检**（预算允许时）：重跑一次步骤 3 与 6，比较
   `retry_journal.jsonl` / `delivery_log.jsonl` 行数应零增长；也可用
   `python3 scripts/delivery_dedup.py check /app/work/delivery_log.jsonl <case_id> <window> <item_key>`
   验证投递键已存在。

## 4. 输出契约（result.json）

由 `assemble_result.py` 生成，字段对照 case.json 的 `output_contract`：

| 字段 | 含义 |
| --- | --- |
| `case_id` | 与 case.json 一致 |
| `status` | `ok`（全部源完成且无降级）/ `partial`（存在降级、阻断或未处理） |
| `window` | 窗口配置原样透传 |
| `items` | 已投递题录：`doi/title/source/window/locator/extra`，全部来自材料 |
| `degraded_sources` | 降级源清单：`source/window/failure_class/reason/attempts` |
| `sources` | 逐源状态：`done/degraded/pending`、尝试次数、材料 locator |
| `uncertainty` | 缺失覆盖说明：降级源、被跳过记录、空窗口、未产出字段 |
| `change_records` | 每轮运行摘要 + 终止性决策事件（来自 runs.jsonl 与 journal） |

`output_contract` 中流水线无法产出的字段置 `null` 并在 `uncertainty` 声明，
**绝不编造**。

## 5. 异常处理与诚实 partial

- 六类故障及策略见 `references/failure-taxonomy.md`：rate_limit/timeout/
  parse_error 可恢复重试（确定性退避 5s→30s→120s，耗尽后降级）；
  source_revision 阻断待人工；missing_field 记录级跳过；empty_window 正常完成。
- 任一源×窗口未进入 completed → `status=partial`，原因进 `degraded_sources`
  与 `uncertainty`。
- 材料缺失/不可读按 timeout 类处理；checkpoint 的 `case_id` 与当前案例不符
  时拒绝复用（防止串案例污染）。
- 幂等机制设计见 `references/idempotency-design.md`（崩溃窗口分析、键设计）。

## 6. 最小调用示例

`examples/minimal/` 是**合成示例**（数据人工构造，已标注 synthetic）。在 bundle
根目录一键跑三阶段：

```bash
python3 scripts/run_minimal_example.py
```

第 1 次运行：源 eupmc_b 为截断 JSON（parse_error）→ 3 次尝试记入 journal、
断点保存、result_run1 为 partial；第 2 次运行：材料换成修复版 → checkpoint
续跑只补 eupmc_b，result_run2 为 ok；第 3 次运行：幂等重跑 → 零新事件、
零二次投递，并做重复投递抑制自检。产物（journal、checkpoint、delivery_log、
三份 result、idempotency_report）全部写入 `examples/minimal/output/`。

## 7. 与其他方向的边界划分（明确不做）

- **不做**源真实性/可信度评分（属 source-integrity-audit 方向）；
- **不做**窗口规划与调度决策（窗口来自 case 配置，原样使用）；
- **不做**提醒内容策略与推送文案（本方向只保证投递幂等，不决定发什么）；
- **不做**QA 评分与答案质量打分（属 tracking-qa 方向）；
- 本方向只负责：**故障分类、重试与断点续跑、幂等投递、诚实降级与交付组装**。
