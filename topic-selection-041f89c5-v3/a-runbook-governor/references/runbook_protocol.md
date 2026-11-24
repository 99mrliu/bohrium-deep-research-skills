# 运行簿协议（runbook protocol）

## 阶段定义与每阶段最小产出

| 阶段 | 目的 | 最小产出（/app/work） | 退出条件 |
|-|-|-|-|
| intake | 输入清点、契约骨架 | inventory.md、deliverables.md、result.json 骨架 | 全部输入文件登记完毕 |
| question | 研究问题结构化 | question_frame.md | 五要素齐全或标注"未指定" |
| retrieve | 检索与筛选留痕 | screening_log.md、coverage_boundary.md | 每条候选记录有决策与理由 |
| extract | 证据提取 | evidence_table.md | 纳入文献的核心字段提取完毕（或按 L1 裁剪） |
| synthesize | 四项交付起草 | synthesis.md | 比较/创新/可行性/不确定性四节成稿 |
| closeout | 回填与终检 | result.json（/app/output）、附件副本 | finalize 校验通过 |

规则：
- 阶段串行；同一时间只有一个 active 阶段；enter/exit 成对出现。
- exit 必须附 `--note`（≥8 字符），写明该阶段实际完成了什么——这是事后审计的唯一依据。
- 每次模型调用回合结束后 `tick --n N` 自报消耗；宁可高估不可漏报。

## 预算降级阶梯

用量比 = max(已用请求/请求预算, 已用时间/时间预算)。

| 级别 | 用量比 | 行为约束 |
|-|-|-|
| L0 | < 0.6 | 无约束 |
| L1 | 0.6–0.8 | 停止新增检索与新的分析线程；只用已收集证据综合；裁剪非核心文献的提取 |
| L2 | ≥ 0.8 或剩余时间 < 120 秒 | 立即停止分析；`triage` 强制合法 partial；`finalize --status partial --reason ...` |

理由：评测运行被硬切断时，只有已落盘的 /app/output 算数。L1/L2 的存在是为了
把"来不及"从崩溃模式变成受控模式。

## checkpoint 的机检项

1. result.json 可解析、顶层为对象；
2. `case_id` 与 case.json 逐字一致；
3. `status` 属于 {success, partial, failed, in_progress}；
4. output_contract 声明的字段全部存在（值允许为 null——null 合法，缺键非法）。

finalize 在 checkpoint 的基础上追加：
- `success`：全部契约字段非空（null/""/[]/{} 均视为空）；
- `partial` / `failed`：必须附理由（缺什么、为什么），不允许无声降级。
