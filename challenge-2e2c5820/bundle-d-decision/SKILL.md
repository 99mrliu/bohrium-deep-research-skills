---
name: versioned-plan-decision-governance
description: 多版本实验方案的决策治理与风险伦理路径评估。对 case 中的 3 个版本化候选方案做证据化打分（每格必须带引文定位）、加权排序与权重敏感性分析，建立含降级路径与转人工节点的完整风险登记表，按规则表生成伦理/安全审批路径（未定项=确认项、涉及项=需办理，绝不写成已批准），最终汇总裁决与可执行条件清单（责任方/验证方法/阻断性），产出 PI 可直接行动的 result.json。杜绝“结论停留在建议进一步确认”和“未确认事项被写成已批准事实”两类失败模式。
---

# 多版本决策治理与风险伦理路径（Bundle D）

## 解决什么问题

可行性评估的终点必须是一个 **PI 能直接执行的决定**，而不是一堆“建议进一步确认”：

1. **可辩护的版本排序**：7 维证据化打分 + 加权总分 + 权重 ±20% 敏感性分析；排序不稳时如实报告翻转，而不是把基准排名当作无争议事实。
2. **完整风险登记**：每条风险含触发信号、后果、降级路径、转人工节点，分类限于六类 taxonomy；转人工条件触发时自动流程必须停止。
3. **伦理/安全审批路线图**：逐项判定涉及/未定/不涉及。**undetermined → 确认项**（须专家书面关闭），**true → 需办理**（前置条件，绝不写“已批准”）。
4. **可执行的“有条件可行”**：每条条件必须有责任方、验证方法、阻断性、关联项；阻断条件未关闭前，任何版本不得表述为“可行”。

## 输入输出契约

- 输入：`/input/case.json`（**字段名不固定，必须先 inspect 再取值**）、`/input/task.md`。case 内含真实科学材料、组织方资源/价格/预约合同、3 个版本化候选方案、有限参数域。
- 中间产物（工作目录 `/app/work`）：inspection.json、scores.json、risks.json、involvement.json、conditions.json。
- 输出：`/app/output/result.json`，含 `case_id` + `output_contract` 声明的**全部字段** + `status`（complete/partial/failed）+ `sources` + `uncertainty` + `change_record`。无法完成的字段保持 null 并在 uncertainty 中说明，**禁止编造**。

## 严格按序工作流

运行时脚本位于 `/skills/weekly-skill/scripts/`，参考文件位于 `/skills/weekly-skill/references/`。以下步骤**不得跳序**：

1. **inspect**：`python3 /skills/weekly-skill/scripts/inspect_case.py /input/case.json work/inspection.json`
   定位 plans/versions、contracts、伦理涉及声明、output_contract 字段清单。字段名以实际文件为准。
2. **逐版证据化打分（模型完成）**：按 `references/rubric.md` 的 7 维量规，对每一版每一格给出
   `score`(0–4) + `evidence.locator` + `evidence.quote`（**逐字摘录原文**），写入 `work/scores.json`。
   找不到证据的版本标记 `{"status":"unscorable","reason":"..."}`，**不猜**。
3. **score_matrix**：`python3 /skills/weekly-skill/scripts/score_matrix.py work/scores.json work/`
   校验空证据（拒绝则修复重跑）→ 加权总分与排名 → 每维权重 ±20% 共 14 个情景的敏感性分析 →
   产出 `decision_matrix.md`（每格带证据）与 `ranking.json`（含 rank flips）。可用 `--weights` 覆盖默认权重。
4. **风险登记（模型完成）**：按 `references/risk_taxonomy.md` 逐项识别风险，每条 5 字段齐全
   （risk/trigger_signal/consequence/degradation_path/escalation）+ 六类 category + plan_locator，写入 `work/risks.json`。
5. **validate**：`python3 /skills/weekly-skill/scripts/validate_risk_register.py work/risks.json work/risk_register.md`
   缺字段 exit 2（修复重跑）；近似重复触发信号与缺失定位只警告，但警告必须在 result.json 的 uncertainty 中交代。
6. **伦理 involvement 判定（模型完成）**：逐版对 动物实验/人体样本/危险试剂/个人数据 给出
   true/false/undetermined，写入 `work/involvement.json`。**证据不足一律 undetermined，禁止默认 false。**
7. **ethics_path**：`python3 /skills/weekly-skill/scripts/ethics_path.py work/involvement.json work/ethics_paths.md`
   按 `references/ethics_rules.json`（通用模板，具体以机构规定为准）生成审批级别、材料清单、周期范围。
8. **汇总裁决+条件清单（模型完成）**：逐版给出 可行/有条件可行/不可行；有条件可行的每条条件写明
   description/owner/verification_method/blocking/linked_item；不可行须 ≥1 条 gating_reason。写入 `work/conditions.json`。
9. **check_conditions**：`python3 /skills/weekly-skill/scripts/check_conditions.py work/conditions.json <总体裁决> work/conditions_list.md`
10. **assemble**：`python3 /skills/weekly-skill/scripts/assemble_result.py --case /input/case.json --artifacts work/ --out /app/output/result.json --status <complete|partial|failed> --note "<限制说明>"`
    只填充仍为 null 的契约字段（绝不覆盖非空），change_record 追加。
11. **自查**：
    - decision_matrix.md 每一格都有 locator + quote；
    - 敏感性表存在，rank flip 如实报告；
    - 风险登记无缺字段，警告已交代；
    - 凡“需办理”无一处写成“已批准”，凡 undetermined 均列为确认项；
    - 有条件可行的条件全部五要素齐全；
    - result.json 含 case_id + 全部 output_contract 字段 + status/sources/uncertainty/change_record。

## 异常处理

- **某版材料缺失** → 该版在 scores.json 标记 `unscorable` 并写明原因，不参与排名，**禁止猜分**；在 uncertainty 中登记。
- **伦理状态未定** → involvement 记 `undetermined`，ethics_path 自动列为确认项；确认前按“可能涉及”管理，绝不按“不涉及”推进。
- **scores/risks/conditions 被脚本拒绝（exit 2）** → 阅读 stderr 列出的问题格/字段，修复输入后**重跑同一脚本**，不要绕过脚本手工改产物。
- **case.json 读不出（inspect exit 3）** → result.json 以 status=failed + uncertainty 说明收尾，不编造任何字段。
- **合同/档期与方案冲突** → 在时间成本维度如实扣分并生成风险条目，不要假设“应该能解决”。

## 预算意识

约 64 次模型请求 / 900 秒。分配建议：inspect 与阅读材料 ≤ 8 次；逐版打分（含引文摘录）≤ 24 次；
风险登记 ≤ 10 次；伦理判定 ≤ 4 次；裁决与条件 ≤ 6 次；脚本调用与自查走 shell 不耗模型请求。
证据摘录优先复用 inspect 命中的路径，避免反复全文重读 case.json；超长材料先按版本分块再打分。
