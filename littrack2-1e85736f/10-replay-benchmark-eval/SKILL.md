---
name: replay-benchmark-eval
description: 时间回放基准与增量质量度量（time-replay benchmark evaluation）。当材料中同时存在同一来源的两份快照（t_prev 增量导入状态 + t_now 当前快照）时，机械构造增量真值（new/backfill/out_of_window 三类），用它评测任一候选新增清单：计算 precision/recall/duplicate_rate/false_alert_rate/backfill_misclassification，TP/FP/FN 逐条列出并带 locator；若有多轮运行记录则做回归检测（recall 下降、误报上升、重复率上升、新增漏报）。产出 eval_report.md 与 metrics.json，并在 result.json 中如实报告基准是否可构造；单快照时诚实降级 partial，绝不编造真值。本 Skill 只做测量基础设施，不做增量追踪管道本身、不做 QA 清单式契约检查、不做窗口调度/去重键设计/提醒抑制。
---

# replay-benchmark-eval — 时间回放基准与增量质量度量

## 1. 适用场景与边界

**适用**：评测"最新文献发现与追踪"类任务的增量质量。组织方材料若含同一来源、
不同时刻的两份快照（例如 `previous_snapshot.json` 增量导入状态 + 当前
Crossref/Europe PMC/出版商 API 响应快照），即可把" t_now 有而 t_prev 无"机械地
当作增量真值来源，对任何候选新增清单（case 提供的、或某次运行产生的 new_items）
做可回放、可复算的测量；若材料中还有多轮运行/历史 eval 记录，再做回归对比。

**明确不做**：

- 不实现自己的增量追踪管道，不以产出 new_items 为主结果（只做测量）；
- 不做 QA 清单式契约评分、不做窗口调度、不去重键设计、不做提醒抑制；
- 不做相关性/重要性筛选（真值是"收录层真值"，非"学术价值真值"）；
- 绝不编造文献、DOI、元数据、真值或指标；无法构造真值时如实 partial。

## 2. 运行契约

- **输入**：`/input/case.json` 与 `/input/task.md`。case.json 关键字段：`case_id`、
  `window{start,end}`（闭区间）、`materials_dir`、`output_dir`、`output_contract`
  （其 `required_fields` 决定 result.json 必含字段）、可选 `synthetic`/`synthetic_note`。
- **材料定位**：先按 case.json 的 `materials_dir`（相对 case.json 所在目录解析）；
  缺字段或路径不存在时用 `find /input -name '*.json'` 兜底枚举，再按文件名与内容
  启发式归类（快照对、候选清单、历史运行记录）。不得假设固定文件名。
- **工作目录**：`/app/work`（中间产物 aligned.json / truth.json / metrics.json /
  regression.json / eval_report.md）。
- **最终输出**：`/app/output/result.json`，必含 `case_id` 与 output_contract
  `required_fields` 的全部字段；任一字段无法填写时补 `null` 且 `status="partial"`，
  并在 `notes` 中说明原因。
- **环境**：Python3 标准库、完全离线；不得联网、不得安装依赖。

## 3. 工作流程（编号）

1. **读 case**：解析 case.json 与 task.md，确定 case_id、窗口、材料目录、output_contract。
2. **定位与归类材料**：枚举材料文件，识别（a）快照类文件——含记录列表与时间戳；
   （b）候选新增清单；（c）历史运行/评测记录。快照按 `taken_at`/文件名/内容推断
   先后，取 (t_prev, t_now) 一对；多于两份时取最近邻的一对并在报告中说明。
3. **基准可构造性判定**：若可用快照 < 2 份 → 跳转第 8 步（降级 partial）。
4. **快照对齐**：`scripts/snapshot_align.py --prev P --now N --out work/aligned.json`
   （DOI/arXiv/标题归一化匹配；记录 added/removed/common 与 warnings）。
5. **构造真值**：`scripts/truth_build.py --aligned aligned.json --window-start S
   --window-end E --out work/truth.json`，得到 truth_new / truth_backfill /
   truth_out_of_window / unclassifiable 四类（规则见
   `references/truth_construction.md`）。
6. **候选评测**：若存在候选清单 → `scripts/metrics.py --truth truth.json
   --candidates C --aligned aligned.json --out work/metrics.json`；指标与计数规则
   见 `references/metrics_definitions.md`，TP/FP/FN 逐条带 locator。
7. **回归检测**：若存在历史运行记录 → `scripts/regression.py --current metrics.json
   --history H --out work/regression.json`（阈值见 `references/regression_thresholds.md`）。
8. **生成报告**：`scripts/report.py` 生成 `eval_report.md`（计数全部可回放到
   truth.json/metrics.json 的逐条清单）。
9. **汇总结果**：`scripts/assemble_result.py` 生成 `result.json`，按 output_contract
   补齐字段、判定 status、如实填写 `benchmark_constructible` 与 `limitations`。
10. **自查**：按第 6 节清单逐项核对后再交付。

## 4. 异常处理

- **单快照（无法构造真值）**：`benchmark_constructible=false`，`status="partial"`，
  notes 说明"只有一份快照 X，缺 t_prev/t_now 中的哪一份"；仍交付已能确定的信息
  （快照记录数、记录清单、缺什么）。**绝不**用启发式猜真值。
- **候选清单缺失**：基准（truth.json）与构造说明照常产出；metrics/regression 字段
  为 null，`status="partial"`，notes 说明"材料中无候选新增清单，仅完成基准构造"。
- **窗口缺失**：added 无法按窗口分类时，全部记为 unclassifiable 并 partial 说明；
  不得擅自假定窗口。
- **published 缺失**：该记录进 unclassifiable，不参与指标分母，报告中显式提示。
- **快照内重复主键/无键记录**：进 aligned.json 的 warnings，不静默丢弃。
- **历史记录缺失**：regression status=`no_history`，不算失败。
- 任何脚本非零退出：捕获 stderr 写入 notes，对应产物字段置 null，status=partial。

## 5. 输出契约

`/app/output/result.json`（字段以 case.json 的 output_contract.required_fields 为准，
本 Skill 的标准集如下）：

| 字段 | 含义 |
| --- | --- |
| `case_id` | 与 case.json 一致 |
| `status` | `ok` / `partial` |
| `synthetic` | 材料是否为合成数据（如实透传，未知为 null） |
| `benchmark_constructible` | 是否成功由快照对构造真值 |
| `snapshot_pair` | `{prev, now, added_count}` |
| `truth_summary` | 真值四类计数 |
| `metrics_summary` | counts + metrics（含 TP/FP/FN 数） |
| `regression_summary` | status / baseline_run_id / verdict / flags |
| `artifacts` | 各产物文件路径 |
| `limitations` | 假设与局限声明 |
| `notes` | 降级原因、异常、合成数据声明等 |

同时交付 `eval_report.md`（人类可读报告）与 `metrics.json`（机器可复算的逐条计数）。

## 6. 自查清单

1. result.json 含 case_id 且与 case.json 一致；output_contract 全部 required_fields
   均在，缺失键已补 null 且 status=partial。
2. benchmark_constructible 与事实一致；单快照场景未编造真值。
3. truth_new/backfill/out_of_window 计数 = 快照对齐 added 计数（±unclassifiable，
   合计恒等），可在 truth.json 中逐条核对。
4. TP+FP = unique_claims；TP+FN = |truth_new|；candidate_entries − duplicates =
   unique_claims；三组恒等式成立。
5. 每条 TP/FP/FN 都有 locator，能在快照文件中定位到原始记录。
6. backfill 被报为 new 的条目已单独计数（backfill_misclassification），未混入普通 FP 噪声。
7. 指标与 references/metrics_definitions.md 的公式一致，且能用计数手算复核。
8. 回归对比使用了同一真值基准；所用阈值已写入 regression.json。
9. 合成数据全程显式标注 synthetic，未冒称真实文献。
10. `python3 scripts/run_minimal_example.py` 端到端自检全部 PASS。
