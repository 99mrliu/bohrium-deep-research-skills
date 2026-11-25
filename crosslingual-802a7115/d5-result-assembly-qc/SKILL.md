---
name: xlang-result-assembly-qc
description: 跨语言检索交付末端的结果组装与过程质量控制（result assembly & contract QC）。assemble_result.py 从 /input/case.json 取真实 case_id 并镜像 output_contract 全部字段组装 /app/output/result.json——未供给的字段写 null 并显式记入 change_records 与 uncertainty，绝不静默丢弃或编造；空命中不得声称 ok。contract_check.py 做提交前 8 项自检：case_id 一致、契约字段齐全且 null 有认领、status 与内容一致、每条命中有 locator 与归因字段（null 归因须附注）、声明语种要么有命中要么有证据化说明、重复/译文视图有去重计数说明、sources 可解析、无占位符。当任务进入交付阶段、需要保证 result.json 可复核、诚实 partial、经得起独立复查时使用；适用于 /input/case.json + task.md 的 Harbor 运行契约。
---

# 结果组装与过程质控（xlang-result-assembly-qc）

## 用途与适用条件

跨语言检索的评分不只看找回什么，还看交付是否**可复核**：case_id 是否真实、
output_contract 字段是否齐全、每条命中能否回指来源、声明语种是否都有交代、
去重计数是否有说明、空结果与冲突是否诚实披露。本 Skill 的重心是**交付末端的
组装纪律与提交前自检**——它不产生任何检索内容，只保证上游产生的证据被完整、
诚实、合规地装进 result.json。

不做：检索、匹配、翻译、语种判定。输入全部来自上游产物与 Agent 整理的 values 文件。

## 运行契约

- 输入：`/input/case.json`（含 `case_id`、`output_contract`）、`/input/task.md`、
  Agent 准备的 values JSON（hits/coverage/sources/uncertainty/change_records/status
  及案例特有字段）。
- 输出：`/app/output/result.json`（唯一权威交付）＋ `/app/work/qc/` 质检报告。
- 诚实 partial：未完成部分以 null＋说明呈现；status 必须反映真实完成度。

## 调用方式

```bash
# 1.（Agent）汇总上游产物，写 /app/work/values.json
#    {"status":"partial","hits":[...],"coverage":{...},"sources":[...],
#     "uncertainty":[...],"change_records":[...], ...案例特有字段...}

# 2. 组装 result.json（镜像 output_contract，缺失字段 null＋留痕）
python3 scripts/assemble_result.py --case /input/case.json \
    --values /app/work/values.json --out /app/output

# 3. 提交前自检（8 项检查，见下）
python3 scripts/contract_check.py --case /input/case.json \
    --result /app/output/result.json --out /app/work/qc

# 4. overall=fail → 按 qc_report.md 逐条修复后重跑 2–3；
#    overall=pass_with_warnings → 人工确认每条 warn 可接受并在
#    change_records 中记录接受理由。
```

完全离线、仅标准库；数秒完成。

## 输出

- `/app/output/result.json`：`case_id`（取自 case.json）、`status`、
  output_contract 全部字段的镜像、sources/uncertainty/change_records 支架。
- `/app/work/qc/qc.json` + `qc_report.md`：8 项检查逐条 verdict 与证据，
  overall ∈ {pass, pass_with_warnings, fail}。

## 检查项（详见 references/qc_checklist.md）

- C1 case_id 与 case.json 一致；
- C2 output_contract 字段齐全，null 字段必须在 uncertainty/change_records 中有认领；
- C3 status 合法且与内容一致（ok 需要非空 hits 或显式空结果说明；partial/failed 需要非空 uncertainty）；
- C4 每条 hit 有 locator（locator/source_file/evidence）与归因字段（source/doi/language/version），null 归因须附 attribution note；
- C5 声明语种覆盖诚实：每语种有命中或有证据化说明；
- C6 出现重复/译文视图时必须有去重计数说明；
- C7 sources 非空且路径可解析；
- C8 无 TODO/XXX/lorem/占位 等占位符。

## 异常处理

| 情况 | 处置 |
|-|-|
| case.json 不可读 | 写出最小 failed result.json（含原因），退出码 2 |
| values 文件缺字段 | 契约字段补 null 并留痕；不编造 |
| status 与内容矛盾 | 组装器自动降级并在 change_records 记录降级理由 |
| QC fail | 不交付；修复后重跑；确无法修复的把 fail 项写入 uncertainty 再交付 partial |
| 案例无 output_contract | 契约检查退化为只查 case_id/status/诚实支架，报告中注明 |

## 自查方法

1. `qc_report.md` overall 为 pass 或 pass_with_warnings，且每条 warn 有接受的留痕；
2. result.json 中每个 null 字段都能在 uncertainty 中找到对应条目；
3. 随机抽 2 条 hit，用其 locator 回指原始语料，确认归因字段与原文一致；
4. status 与实际完成度一致——宁可 partial 不可假 ok。

## 最小调用示例

见 `examples/example_walkthrough.md`（**合成示例**，非正式案例结果）。
