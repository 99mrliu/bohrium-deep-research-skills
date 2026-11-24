---
name: human-confirmation-gate
description: 系统性文献筛选的人机权责门禁。当案例要求明确"哪些判断必须由研究者确认、模型输出在什么条件下只能作为待复核建议"时使用。重心在人机边界工程：升级触发器（T1–T6）分诊、pending 状态契约、人工决定回填校验（V1–V5）、推翻留痕与队列闭合。不伪造人工复核——无真实人工输入时如实记 partial，绝不生成模拟人工决定。
---

# human-confirmation-gate — 人工确认门禁与待复核队列

系统综述里最伤可信度的不是模型判错，而是**把没经过人工的判断说成经过了**。
本技能把人机权责边界做成可执行契约：哪些记录必须人工确认、人工决定如何
回填校验、未完成时如何诚实地降级交付。

## 1 适用场景与红线

**适用**：案例含双人独立判断、冲突意见（如平台标注的合成冲突 fixture）、
边界题录（无摘要/语种不符/部分重叠），或要求说明"哪些判断只能作为建议"。

**红线**：
- 不伪造人工复核：没有真实人工输入时，队列保持 pending，status 记 partial；
- 不掩盖分歧：标注者冲突（T4）必须仲裁留痕，禁止平均或多数和稀泥；
- 不吞未决项：unresolved/rejected 非空即 exit 3，不得声称 completed；
- 不静默放行：自动放行的记录也登记 confirmation_status。

## 2 运行环境

- Python 3 标准库，无第三方依赖；脚本在 `$SKILL/scripts/`；
- 退出码：0=队列闭合；2=输入缺失/格式不合法；3=人工复核未完成（诚实阻断）。

## 3 端到端运行契约（平台案例）

1. 读 `/input/case.json` 与 `/input/task.md`，确认 case_id、判定材料
   （含冲突意见 fixture）、output_contract 字段。
2. **尽早**落 `/app/output/result.json` 骨架（status=in_progress）。
3. 完成题录判定后执行第 4 节管线；案例中给出的冲突意见逐条进入 T4 分诊，
   仲裁结论与依据写入 change_records。
4. 评测环境通常没有真实人工输入：此时交付 = review_queue.json +
   final_decisions.json（队列记录 final_label=null、pending），
   result.json status=partial，uncertainty 声明"人工复核未执行、
   队列规模与优先级分布"。这是**设计上的正确结果**，不是失败。
5. result.json 填齐全部合同字段，缺数据字段置 null 并说明。

## 4 门禁管线（编号步骤）

0. **[脚本] 分诊**：`triage.py --decisions /app/work/decisions.json
   --out /app/work/review_queue.json` → 队列（P1–P3 排序）+ 自动放行清单。
   判定行可带 boundary_flags / screener_labels / evidence_snippet /
   abstract_present；缺这些字段时按谨慎原则处理（见触发器表）。
1. **[模型] 队列说明**：把 queue_reasons 翻译成每条记录一句人读的
   "为什么需要你确认"，供研究者使用（写入报告，不回写判定）。
2. **[人工] 复核**：研究者按 references/reviewer_form.md 填
   human_decisions.csv。此步只能由真实研究者完成。
3. **[脚本] 回填合并**：`merge_review.py --queue ... --decisions ...
   --human ... --out /app/work/final/` → final_decisions.json +
   confirmation_ledger.json。exit 3 时按 rejected/unresolved 清单补齐重跑。
4. **[模型] 汇总**：confirmed/overridden/override_rate、队列分布、
   未决清单填入 result.json；高推翻率在 uncertainty 中给出模型口径
   修正建议（建议，不自动改判）。

## 5 输出合同映射（常见字段）

| 合同字段 | 来源产物 |
|---|---|
| case_id | case.json |
| status | 队列闭合 → completed；无人工输入/有未决 → partial（如实） |
| product | review_queue.json + final_decisions.json |
| evidence_matrix | 每条记录的 queue_reasons / confirmation_status / rationale |
| sources | 判定材料与冲突意见 fixture 清单（快照内） |
| uncertainty | unresolved 清单、rejected 行、未执行人工复核的声明、高推翻率提示 |
| change_records | 仲裁结论与依据、推翻记录（human_overridden + rationale） |
| counts | stats（total/queued/auto、按优先级与触发器分布、override_rate） |
| checks | 队列闭合状态（exit 0/3）、V1–V5 校验结果 |

## 6 异常处理表

| 异常 | 处理 |
|---|---|
| 无真实人工输入（评测常态） | 队列原样交付，status=partial，uncertainty 明确声明 |
| 人工 CSV 行被拒（V1–V5） | rejected_rows 逐行给原因；修正后重跑 merge |
| 队列记录无人决定 | unresolved 点名；exit 3；status 至多 partial |
| 标注者僵持（仲裁也无法定） | 该记录 final_label=needs_fulltext 或保持 pending，僵持事实写 uncertainty |
| 队列占比异常高 | uncertainty 提示标准定义或材料质量问题，不放宽触发器 |
| decisions.json 有重复 record_id | triage exit 2，先回上游修判定表 |

## 7 最小调用示例（合成数据）

```bash
cd <bundle 根目录>
python3 scripts/run_example.py
```

10 条**合成**判定 → 分诊 6 条入队（T1–T6 全覆盖，P1/P2/P3 各 2 条）、
4 条自动放行；用完整人工决定表（合成填写）回填 → COMPLETE exit 0
（confirmed=4、overridden=2）；用残缺表回填（一行推翻无理由被 V4 拒、
一行不在队列被 V1 拒、一条队列记录未决定）→ INCOMPLETE exit 3，
unresolved=2、rejected=2。产物在 `examples/minimal/output/`，
详见 `examples/minimal/RUNLOG.md`。示例中的"人工决定"是合成的演示数据，
真实场景必须由研究者填写。

## 8 自查方法

- 重跑 run_example.py，三步结论与 RUNLOG 一致；
- 抽一条 auto_accepted 记录，确认它确实未命中任何触发器；
- 把完整 CSV 删一行再 merge，unresolved 应立即出现且 exit 3；
- 确认 result.json 的 status 与队列闭合状态一致，无"未完成却 completed"。
