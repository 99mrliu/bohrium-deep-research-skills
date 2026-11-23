---
name: contract-pilot
description: Run a literature-reading case under strict process control — a contract-driven skeleton result from minute one, budget checkpoints, schema-subset validation, null-reason and status-honesty enforcement, and an append-only audit trail — so the final result.json is always complete, contract-faithful and honestly graded (success / partial / failed). Use for any reading, extraction, Q&A or notes case where delivery validity and honest degradation matter more than tooling novelty.
---

# Contract Pilot

重心在过程质量控制：本 Skill 不替你读论文——它保证“读论文这件事”始终在合同、预算与诚实状态的轨道上。骨架先行、检查点推进、校验把关、审计留痕；partial 是一等公民，空交付与假 success 是不可接受事件。

## 运行契约

- 输入：`/input/case.json`（`case_id` + `output_contract`）、`/input/task.md`、真实论文材料。工作区 `/app/work`，交付区 `/app/output`。
- 最终交付 `/app/output/result.json`（`case_id` + 合同全部字段）、`plan.json`、`validation.json`（如生成）、`audit-trail.jsonl`。
- 状态诚实：`success` 需零硬问题；任何缺口 → `partial` 且 `limits` 逐项命名；材料不可读/任务不可能 → `failed` 或 `refused` 并写明 `failure`/`reason`。预算 64 请求 / 900 秒。

## 流程（K 为本 SKILL.md 所在目录）

### 1. 先落骨架，再读论文

```sh
python3 "$K/scripts/pilot.py" init --case /input/case.json --out /app/output
```

这一步在任何阅读之前完成：`result.json`（in_progress 骨架）、`plan.json`（预算检查点 + 合同必需字段清单）、`audit-trail.jsonl` 同时落盘。此后任何时候中断都有一份合法交付物。

### 2. 阅读与撰写（Agent 的工作，工具不代劳）

用平台 PDF 文本/渲染/OCR 工具读真实材料，把内容直接写进 `/app/output/result.json`（或先写 `/app/work` 草稿再合并）：

- 合同字段的键名、嵌套、类型必须与 `output_contract` 完全一致；不确定的字段先填 `null` 并在 `null_reasons` 写明检索范围与理由（格式：`{"$.answer.q2": "查过 Methods/Results 全文，无 X 的报告"}`）。
- 每个关键论断附锚点（页码/段落/图表定位）与逐字引文，放在合同允许的位置或 `evidence` 附加字段。
- 到达检查点时打卡：`python3 "$K/scripts/pilot.py" checkpoint --out /app/output --phase t40 --note "已完成初稿"`。检查点期望见 [references/operating-contract.md](references/operating-contract.md)。

### 3. 校验

```sh
python3 "$K/scripts/pilot.py" validate --case /input/case.json \
  --result /app/output/result.json --out /app/output/validation.json
```

校验内容：required/类型/enum/pattern/minItems/maxItems/minLength/maxLength、未知 schema 关键字（警告）、无理由 null、status 与内容一致性。报告即修复清单；支持的 schema 子集见 [references/schema-support.md](references/schema-support.md)。

### 4. 定稿

```sh
python3 "$K/scripts/pilot.py" finalize --case /input/case.json \
  --result /app/output/result.json --out /app/output
```

finalize 重新校验：零硬问题 → success；有硬问题 → 自动把 `success` 降为 `partial` 并把缺口逐条并入 `limits`，**绝不删除已写内容**。同时把校验结论写入 `result.validation` 并在审计轨迹留痕。

## 异常处理

- 材料不可读（扫描件/加密/无文本层）：result.json 写 `status: failed` + `failure`（实际原因）+ `handover`（平台 OCR 工具接管位置），finalize 会保持该状态。
- 合同字段无法理解：保留原名填 `null` + `null_reasons`，不得改键名“凑型”。
- 预算将尽：t70 之后禁止新增章节/工具，只做核查与修复；t100 必须 finalize。
- 审计轨迹是只追加文件：任何状态修改、降级、修复都应有对应条目。

## 最小示例（合成）

```sh
sh "$K/examples/synthetic-case/run_example.sh /tmp/cpl-demo"
```

示例含嵌套合同与两处故意的 null 字段，演示 null_reasons 纪律与 honest partial；材料为虚构，输出标注为合成示例。

## 依赖

Python 3.9+ 标准库，零外部依赖；阅读环节使用平台自带 PDF 文本/渲染/OCR 工具。
