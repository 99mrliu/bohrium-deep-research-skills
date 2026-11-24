---
name: feasibility-precondition-gate
description: 可行性决策取向的科研选题评估技能。当任务是在 /input 给定 case.json（含 case_id 与 output_contract）、task.md 与文献材料及待评提案或约束场景，要求输出可行性判断，并在 /app/output 交付结构化 result.json 时使用。核心立场：可行性是前提审计而不是立场表态——把数据可得性、算力、实验条件、时间窗口、人员能力五类前提逐条登记，每条强制标注依据性质（source 带来源定位 / assumption 带假设理由），feasibility_gate.py 按门控规则生成结论：有 blocked 即不可行、有 unknown 或假设即有条件可行并列出条件清单，全部 unknown/assumption 入风险登记册。不适用：无需资源与条件核查的纯理论评述。
---

# feasibility-precondition-gate：可行性是前提审计

## 核心主张

"技术路线可行"是选题评估里最廉价的一句话：不核查数据在哪、算力够不够、时间窗对不对，结论就不可执行。本技能把可行性判断改成门控审计：**结论由前提台账推出，每条前提必须交代它是来源支持的事实还是裸假设**；评审者看到的不是表态，而是"哪些前提成立、哪些被阻塞、哪些是有待核实的赌注"。

## 运行时契约

1. 输入在 `/input`：`task.md`、`case.json`（`case_id`、`output_contract`）、文献材料与提案/约束场景。逐文件读真实内容；PDF 用实际可用工具从原始文件解析。
2. 若存在 `/input/environment/resources.yaml`，先读确认可用工具。
3. 中间产物入 `/app/work`，最终交付入 `/app/output`；`result.json` 含 `case_id`（逐字一致）与 `output_contract` 全部原始字段。
4. 预算：约 64 次模型请求、900 秒、16384 token/响应。第一阶段写 result.json 骨架（契约字段=null、status=in_progress），逐阶段回填。
5. 诚实状态：`status` ∈ {success, partial, failed}；`insufficient_evidence`（证据不足）是合法的可行性判定，不丢人，硬撑才可耻。
6. 禁止伪造：不把假设写成事实，不给来源不存在的前提贴 source 标签。

## 工作流程

### 阶段 0：契约骨架与材料登记

登记 `/input` 文件；摘 case_id 与 output_contract；写 result.json 骨架。

### 阶段 1：约束场景提取

从 task.md 与 case.json 提取硬约束：可用数据、设备/算力、时间窗、人员配置、提案承诺的实验。写入 `/app/work/constraints.md`，逐条标出处；任务未给的约束标 `未指定`——**未指定的约束通常就是假设的来源**。

### 阶段 2：前提台账登记（本技能核心）

按 `references/precondition_format.md`，把五类前提逐条写入 `/app/work/preconditions.jsonl`：

| 类别 | 核查内容 |
|---|---|
| data | 数据是否存在、可获取、规模与标注是否够、许可是什么 |
| compute | 训练/推理算力、内存/显存、存储 |
| experiment | 实验设备、材料、基线实现可得性 |
| time | 关键路径工期 vs 截止时间 |
| personnel | 所需技能是否在团队内 |

每条：`status`（ok/blocked/unknown）+ `backing`（source 附 `evidence_ref` 定位 / assumption 附 `note` 理由）。文献中的规模数字、任务书中的资源承诺是 source；"应该能申请到"是 assumption。门控规则 G1–G4 与一致性违例 Y1–Y4 见 `references/gate_rules.md`。

### 阶段 3：门控判定

```
python3 /skills/weekly-skill/scripts/feasibility_gate.py \
    --ledger /app/work/preconditions.jsonl \
    --out /app/work/feasibility
```

读 `verdict.json` 与 `feasibility_memo.md`：有违例先修台账；`not_feasible` 时 blocker 清单就是返工清单；`conditional` 时条件清单就是立项前必须关闭的事项。

### 阶段 4：结合文献证据的综合

可行性结论与文献证据联动：方法成熟度（有无复现报道）、数据规模（文献报道的量级 vs 提案需求）、失败模式（文献报道的反例）都要回到台账前提，冲突证据双方登记。

### 阶段 5：收口

判定回填 result.json（可行性字段=verdict + 条件清单）；`preconditions.jsonl`、`feasibility_memo.md`、`risk_register.md` 复制到 `/app/output`。终检：每条 source 前提能报出定位，每条 assumption 能报出理由。

## 异常处理

| 情形 | 处置 |
|-|-|
| 任务完全未给资源约束 | 相关前提全部标 unknown/assumption，verdict 至多为 conditional，并在备忘录声明"约束未指定" |
| 材料不足以判断任何前提 | verdict=insufficient_evidence，status=partial，写明需要补充什么 |
| 提案承诺与约束场景矛盾 | 相关前提标 blocked 并在 note 写明矛盾双方出处 |
| 文献数字相互矛盾 | 取保守值登记，note 写明分歧；不用乐观值粉饰 |
| 预算将尽 | 立即回填当前 verdict（多为 conditional/partial），台账优先于叙述完整 |

## 红线

- 不许把 assumption 写成 source；不许忽略 blocked 前提给"可行"；不许只登记有利前提；不许给没有条件清单的 conditional 结论。

## 最小示例

`examples/` 内有**合成示例**：虚构提案的 8 条前提台账（含 1 条 blocked、2 条假设、1 条 unknown）与一份违例对照，见 `examples/minimal_example.md`。
