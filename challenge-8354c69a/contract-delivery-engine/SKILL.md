---
name: contract-delivery-engine
description: 面向「实验结果解释与异常分析」的下游交付工程 Skill。以 output_contract 为唯一事实源驱动 result.json 全生命周期（partial-first 骨架→逐字段填写→L1-L5 交付 QA 门禁→人读报告与完成度图渲染），确保任何时刻可交付、交付物字段全覆盖、每条结论带可机检证据定位。当任务要求产出结构化、可复核、字段完整的分析结果时触发。
---

# contract-delivery-engine：输出契约与交付渲染工程

## 用途与重心

本 Skill 的重心是**下游交付工程**。平台契约要求 `result.json` 含原始 `case_id`、`output_contract` 全部字段、诚实状态与证据定位——最常见的丢分不是分析错，而是交付层面：字段漏填、case_id 拷贝错、status=success 却带着「待完成」的 limitations、结论没有任何可回查定位。本 Skill 把交付做成可机检的工程对象：**lint 不过，就不算交付**。

**边界**：
- 不做统计分析本身；它承载任何分析过程（Agent 手工/其他脚本）产出的结论，并保证交付形态正确、完整、可核验。
- L3 证据定位是机检底线（出现文件名/位置/页码），不替代人工判断定位是否真实支撑结论。
- 纯 stdlib；PNG 渲染依赖 matplotlib，缺失时自动降级（report.md 始终生成）。

## 运行时契约

- 输入：`/input/case.json`（`case_id` + `output_contract`）、`/input/task.md`。
- 工作目录 `/app/work`；成果目录 `/app/output`：`result.json` + `report.md`（+ `summary.png` 若可用）。
- `result.json`：原始 `case_id`、契约全部字段、`status`（success/partial/unable_to_determine/refused）、`sources`、`uncertainty`、`change_records`。
- 预算：约 64 次模型请求 / 900 秒 / 每响应 16384 tokens。**partial-first**：scaffold 必须是对成果目录的第一次写入。
- 脚本路径以 `/skills/weekly-skill/scripts/` 书写；安装路径不同逐字替换前缀。

## 标准流程

```bash
S=/skills/weekly-skill/scripts
# 0) partial-first（第一动作）
python3 $S/contract_engine.py scaffold --case /input/case.json --out /app/output/result.json
# 1) 分析推进中，逐字段填写（长文本建议先写成 JSON 文件再 --file 注入，避免转义事故）
python3 $S/contract_engine.py set --out /app/output/result.json \
    --field "结果趋势" --value "载荷-位移曲线整体先升后降…（依据 traces/scan 结果，见 work/trends.json::peak_stats）"
# 2) 每完成一段就渲染一次，肉眼检查
python3 $S/render_report.py --result /app/output/result.json --outdir /app/output
# 3) 交付前 QA 门禁（不过不许收工）
python3 $S/contract_engine.py lint --case /input/case.json --out /app/output/result.json
```

## 交付 QA 门禁（L1–L5）

| 门禁 | 内容 |
|-|-|
| L1 | `case_id` 与 case.json 完全一致 |
| L2 | 契约字段全覆盖（不得 null/空串/空表） |
| L3 | 每个已填字段至少含一个可机检定位：`文件名.扩展名`、`文件::位置`、`p.N/第N页` |
| L4 | status 合法；success 时 limitations 不得含「待/未完成/尚未」 |
| L5 | `sources`/`uncertainty`/`change_records` 非空 |

## partial 的诚实写法

- 分析未完成 → `status=partial`，`limitations` 精确到字段：「异常点、可能原因未完成：缺少批次对照数据」。
- 材料本身不足 → `unable_to_determine` 仅用于整体无法判断；局部缺失仍 partial。
- 任何中断后恢复：先读现有 result.json 的 change_records 续写，不重头覆盖。

## 渲染与预览

`render_report.py` 生成 `report.md`（全字段人读版）与 `summary.png`（字段完成度红绿图，供快速目检）。约定：JSON 是契约成果，渲染件是给人看的——两者由同一 result.json 生成，禁止手改渲染件。

## 最小示例

`examples/`（**合成示例**）：合成 case.json（7 个契约字段）+ 模拟填写部分字段 → lint 失败（L2/L3）→ 补齐后 lint 通过 → 渲染 report.md 与 summary.png。见 `examples/README.md`。
