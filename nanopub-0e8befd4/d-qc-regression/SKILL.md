---
name: qc-regression
description: 面向科研阅读交付物的质量门与反例回归技能。对断言台账做逐条对抗性核验（逐字引文、方向、数值、模态、来源、冲突、状态标签），每条判定给出可复现依据，并用 12 例已知错误合成题集回归证明检测力。适用于 Nanopublication 的质量检查、交付前门禁、异常处置。不适用：替代原文阅读本身、无台账的 free-form 问答。
---

# qc-regression — 质量门：每条判定都有可复现依据

**核心立场：信任但要核验。交付物先过门再谈质量；门本身先用已知错误证明自己拦得住。**

本技能的重心在**质量检查与异常处置**：断言拆解与绑定由 Agent 按通用契约完成，
本技能提供独立对抗性核验层与诚实状态机。全部脚本仅用 Python 3.9+ 标准库。

## 运行契约（平台评测环境）

1. 先读 `/input/case.json`、`/input/task.md` 与 `environment/resources.yaml`（如存在）。
   记录 `case_id`、`output_contract` 字段。**任务 schema 优先**。
2. 工作区 `/app/work`，交付区 `/app/output`；`result.json` 含原 `case_id` 与全部契约
   字段，状态必须由质量门结果支撑。
3. 预算 64 次模型请求 / 900 秒：先写 result.json 草稿（诚实 partial）再过门修复；
   核验脚本不耗模型请求。
4. 本技能目录记为 `SKILL_DIR`；脚本以 `python3 SKILL_DIR/scripts/...` 调用，绝对路径。

## 工作流（Agent 逐步执行）

### 第 1 步：读材料、起草台账

按 task.md 覆盖范围产出断言台账 `/app/work/ledger.json`：

```json
{"case_id": "<原 case_id>",
 "source_text": "<提取的原文全文（或分段拼接）>",
 "source": {"title": "…", "identifier": "…"},
 "claims": [{"id": "…", "text": "…", "subject": "…", "relation": "…",
             "object": "…", "qualifiers": [], "polarity": "positive",
             "modality": "asserted", "evidence": {"quote": "…", "location": {}},
             "confidence": {"level": "high", "rationale": "…"}, "status": "asserted"}]}
```

特殊条目的 status：`not_reported`（题目问到但材料未报告，必须带 searched_scope）、
`conflict`（与另一条冲突，双方互指 conflict_with）、`inferred`（间接推论，带推理说明）。

### 第 2 步：过质量门

```
python3 SKILL_DIR/scripts/qc_gate.py \
  --ledger /app/work/ledger.json --out /app/work/qc-report.json
```

每个判定都带可复现依据（命中的词、缺失的数值、重复对 ID），代码与处置见
[references/error-catalog.md](references/error-catalog.md)。判定语义：

- `reject`（含 `E_*`）：修复、降级为 not_reported/inferred，或删除；不得带病交付；
- `review`（仅 `W_*`）：逐条判读，保留的写 adjudication 理由；
- `pass`：可直接进入交付。

### 第 3 步：状态机（诚实交付）

门的汇总决定 `result.json.status` 的上限（细则见
[references/review-protocol.md](references/review-protocol.md)）：

- 有 reject 未处理 → 禁止 `success`；修复到 0 reject 后复检；
- 有 review 未写 adjudication → 最高 `success` 受限，建议 `partial` 或补判读记录；
- 存在 conflict/not_reported/受阻区域 → `partial` 并逐项说明；
- 材料不可得/无文本层 → `blocked` 或 `partial`，写清人工接管位置。

### 第 4 步：用反例回归自证（交付前）

```
python3 SKILL_DIR/scripts/run_regression.py \
  --fixtures SKILL_DIR/examples/regression/fixtures.json \
  --out /app/work/regression-report.json
```

12 个合成已知错误（改数值、丢模态、主客颠倒、打包、假定位…）必须全部被对应代码
捕获；任何漏检说明门被改动或失效，先修门再交付。**题集是合成反例，不是正式案例。**

## 异常处理

| 情形 | 门内处置 |
|-|-|
| 引文非逐字 | E_QUOTE_NOT_VERBATIM → reject；修复或删除 |
| 扫描件无文本层 | 台账 source_text 置 null 并标记 ocr_blocked；引文核验降级为人工目检记录，状态 partial |
| 断言找不到支撑 | 改 status=not_reported + searched_scope，或删除 |
| 材料冲突 | 双方保留、互指 conflict，写 adjudication 后 W_CONFLICT_UNRESOLVED 才消除 |
| 字段缺失 | E_*_MISSING → 补齐再交 |
| 题目问到但材料没有 | not_reported 条目本身即答案的一部分，缺失视为覆盖不完整 |

## 本地最小示例（合成）

`examples/minimal/`：同一合成来源的 good/bad 两份台账过门对比。
`examples/regression/`：12 例已知错误题集与回归运行。**均为合成示例，非正式案例结果。**

## 边界与限制

- 门核验的是可机械检查的性质（逐字性、一致性、完备性），不证明语义蕴含；
  review/adjudication 记录是留给人与下游的判读界面。
- 关系词表是通用集；任务自带词表时以任务为准，门的 E_RELATION_UNKNOWN 用任务词表。
- 回归题集覆盖已知错误类型，不证明对未知错误类型的检测力。
