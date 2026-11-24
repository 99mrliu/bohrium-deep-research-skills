---
name: contract-first-deliverables
description: 下游交付工程取向的科研选题评估技能。当任务是在 /input 给定 case.json（含 case_id 与 output_contract）、task.md 与科研材料，要求完成文献综述、深度研究、选题或创新性评估并在 /app/output 交付结构化 result.json 与人读报告时使用。核心立场：交付物是被契约驱动的工程产物——先用 contract_scaffold.py 把 output_contract 编译成 result.json 骨架（case_id 即刻锁定），各阶段只回填不重构，交付前用 contract_validate.py 机检契约字段齐全、case_id 一致、status 与回填状态相符，报告由 render_review_pack.py 从结构化载荷确定性渲染，保证"同数据同报告"可复核。不适用：无结构化输出契约的开放式写作。
---

# contract-first-deliverables：契约驱动的交付工程

## 核心主张

选题评估类任务最常见的交付失败不是内容差，而是**契约违约**：result.json 缺字段、字段名自创、case_id 串号、status 写 success 却半数字段为空、报告与 JSON 各说各话。本技能把交付当作工程问题：契约先编译成骨架，回填与校验分离，人读报告由数据确定性渲染——**内容可以因材料所限而是 partial，形式合规必须满分**。

## 运行时契约

1. 输入在 `/input`：`task.md`、`case.json`（含 `case_id`、`output_contract`）、材料文件（文献记录、PDF 等）。逐文件读真实内容，不依据文件名猜测；PDF 用实际可用工具从原始文件解析。
2. 若存在 `/input/environment/resources.yaml`，先读它确认可用工具。
3. 中间产物写入 `/app/work`，最终交付写入 `/app/output`。
4. `result.json` 含 `case_id`（与 case.json 逐字一致）与 `output_contract` 全部原始字段，字段名逐字照抄。
5. 预算：约 64 次模型请求、900 秒、单次响应 16384 token。骨架先行，增量回填。
6. 诚实状态：`status` ∈ {success, partial, failed}；partial 写明缺口与原因；材料缺失、无法判定、运行失败分别说明。
7. 禁止伪造数据与不存在的文献。

## 工作流程

### 阶段 0：契约编译（最先做，≤2 次模型调用）

```
python3 /skills/weekly-skill/scripts/contract_scaffold.py \
    --case /input/case.json \
    --out /app/output/result.json \
    --report /app/work/contract_fields.md
```

得到：result.json 骨架（case_id 已锁定、契约字段=null、status=in_progress）与契约字段清单。此后**所有结论写入这份骨架的对应字段**，不在别处另起结构。契约形态（对象/数组/字符串）的兼容规则见 `references/contract_binding.md`。

### 阶段 1–3：阅读材料、组织证据、形成判断

- 研究问题结构化（对象/变量/基线/预期方向/可证伪条件），写入 `/app/work/question_frame.md`；任务未指定的要素标 `未指定`。
- 文献整理与筛选留痕：候选、纳入、排除理由记入 `/app/work/screening_log.md`；证据抽取写入结构化载荷 `/app/work/payload.json`（结构见 `references/payload_format.md`，即 render_review_pack.py 的输入格式）。每条证据带来源定位（文件名+页码/记录 ID）。
- 判断成形：已有工作比较、创新点逐条划界（covered/partial/uncovered/indeterminate）、可行性前提逐条标 `[来源]` 或 `[假设]`，全部落入 payload 的对应键。冲突证据双方保留。

### 阶段 4：回填 result.json

把 payload 中各结论按 `contract_fields.md` 的字段名逐字回填到骨架。字段语义与契约说明不符时，以契约原文为准调整取值形式，不改字段名。

### 阶段 5：确定性渲染

```
python3 /skills/weekly-skill/scripts/render_review_pack.py \
    --payload /app/work/payload.json --out /app/output
```

生成 `evaluation_report.md` 与 `evidence_matrix.md`。报告只能由渲染产生；要改报告先改 payload 再重渲染，禁止手改渲染产物造成 JSON 与报告漂移。

### 阶段 6：交付前机检（不过不交付）

```
python3 /skills/weekly-skill/scripts/contract_validate.py \
    --case /input/case.json \
    --result /app/output/result.json \
    --out /app/work/contract_check
```

硬失败（缺字段、case_id 不一致、status 非法、success 但有空字段）必须修复后重检；警告（契约外字段、partial 未写 uncertainty）逐项确认。校验报告留在 `/app/work/contract_check.md` 供复核。

## 异常处理

| 情形 | 处置 |
|-|-|
| output_contract 解析不出字段 | result.json 只含 case_id+status=failed， uncertainty/说明字段写明契约不可解析；不臆造字段名 |
| 材料不足无法回填某字段 | 该字段写入"材料未提供/无法判定"的显式说明而非 null；status=partial |
| 校验报 success 但有空字段 | 要么补齐，要么改判 partial；不允许带空字段宣称成功 |
| 预算将尽 | 骨架+已回填字段即合法半成品；立即跑 contract_validate 并按结果落 status |

## 红线

- 不改写契约字段名、不丢字段、不串 case_id；不手改渲染产物；不让报告与 result.json 结论不一致；不带硬失败交付。

## 最小示例

`examples/` 内有**合成示例**（虚构 case.json 与 payload），演示 骨架生成→渲染→校验 全链路，含一次故意违约（漏字段+status 误标 success）被 validator 拦下的过程，见 `examples/minimal_example.md`。
