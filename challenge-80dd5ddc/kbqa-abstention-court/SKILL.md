---
name: kbqa-abstention-court
description: 科研知识库问答的"证据充分性法庭"——把每个问题机械分解为证据面（实体/数值/关键词），用确定性脚本生成覆盖矩阵与跨文件冲突登记，据此给出五级充分性裁决（充分可答/基本可答/部分可答/证据不足拒答/无法判读）；模型可以申报更高裁决，但申报高于机器等级两级以上会被强制回降并留痕，措辞不能绕过证据；拒答必须带"查过哪里、缺什么、补什么可答"三要素。Use when a QA task over a document library requires calibrated uncertainty, conflict surfacing, and honest refusal for unsupported questions (不确定性提示, 证据不足, 拒答, 冲突登记, 覆盖矩阵, 证据充分性, /input/case.json, result.json).
---

# 证据充分性法庭（kbqa-abstention-court）

重心在**认识侧**：本 Skill 不追求答得多，而追求每个答案的可信等级与证据
严格匹配，且对库中无依据的问题给出可复核的拒答。裁决由机器推导、模型
申报受机器约束——这是与"自信作答型"流程的本质区别。

## 何时使用 / 不适用

适用：`/input/case.json` + `/input/task.md` + 资料库，任务要求带不确定性
提示的问答、证据冲突交代、对无依据问题明确拒答。
不适用：只要求摘抄原文的单文件任务（覆盖矩阵开销大于收益）。

## 运行时合同

1. 先读 `/input/case.json`、`/input/task.md`：case_id、问题、output_contract。
2. `/app/work` 中间产物；`/app/output` 交付：result.json（case_id +
   output_contract 全部字段 + 诚实 status/sources/uncertainty/change_log）、
   coverage_matrix.json、conflict_registry.json、verdicts.json。
3. 预算 64 次模型请求 / 900 秒：四步脚本全部确定性；模型预算只花在
   L3–L5 等级问题的实际作答文字上。骨架 result.json 在第 1 步即落盘。

## 工作流（$SKILL=/skills/weekly-skill）

```bash
SKILL=/skills/weekly-skill

# 1) 索引（含数值事实预抽）+ 问题解析 + 保底 result.json
python3 $SKILL/scripts/suff_index.py --input /input --work /app/work --out /app/output

# 2) 覆盖矩阵：每题分解为证据面并逐面检索
python3 $SKILL/scripts/suff_matrix.py --work /app/work --out /app/output

# 3) 冲突登记：跨文件/版本同语境数值不一致检测
python3 $SKILL/scripts/suff_conflict.py --work /app/work --out /app/output

# 4) 机器裁决；可选：模型申报写入 /app/work/model_verdicts.json 后重跑本步
python3 $SKILL/scripts/suff_verdict.py --work /app/work --out /app/output
```

第 4 步后：L4/L5 的问题由模型作答（论断带 [Fxx|sha8] 坐标）；L3 只答已
覆盖部分并逐面列出未知；L2 按 references/abstention_protocol.md 的
四要素拒答；L1 说明阻塞与解除动作。最后把答案写回 result.json 的
answers（保持 verdict 字段与 verdicts.json 一致，禁止手工提高等级）。

## 硬性规则

- 任何答案的等级不得高于 verdicts.json 中该题的 final_level；回降记录
  必须保留在 uncertainty。
- L2 拒答必须含四要素：拒答句、检索留痕（覆盖率与未命中面）、缺口说明、
  补救路径；缺一即为不合格拒答。
- 冲突相关的答案必须交代采用哪一侧与依据；不得静默任取一侧。
- 判据语义以 references/sufficiency_rubric.md 为唯一权威。

## 异常与失败处置

0 个可索引文件 → 全部 L1，result.json 标 partial 并说明阻塞；问题解析不
出证据面 → 该题 L1；PDF 无文本层/权限不足 → 记 uncertainty，相关证据面按
未命中处理；行政备注与文件内容矛盾 → 冲突登记并以行政备注为准作答、明示
矛盾。所有脚本 exit 0，失败只进入产物记录。

## 自查清单

1. 每题 verdict 与 coverage_matrix 的覆盖率一致？缺面清单非空（L2/L3）？
2. 拒答题是否四要素齐全？
3. 冲突登记非空时，相关答案是否交代了取舍依据？
4. model_verdicts 的申报与回降是否如实留痕？
5. result.json 的 status/uncertainty 是否把"不知道"说得和"知道"一样清楚？

最小调用示例见 [examples/minimal_example.md](examples/minimal_example.md)
（**合成示例**，非正式案例结果）。
