---
name: run-gate-keeper
description: Run scientific database analysis cases through budget-aware quality gates with checkpointed recovery and a pre-submission self-audit. Use when a case must produce a contract-valid result.json under tight budget — bootstrap an honest partial deliverable first, execute the analysis as gated checkpointed steps that resume after failure, classify exceptions by taxonomy, and verify GO/NO-GO before declaring completion. 过程质量控制：门禁流水线、partial 兜底、断点续跑、提交前自检。
---

# Run Gate Keeper：分析过程的质量控制与诚实交付

本 Skill 的重心是**过程可靠性**：900 秒 / 64 次请求的预算下，真正的风险不是不会分析，而是中途失败留下不可评审的半成品、数字没留痕、异常被静默吞掉。它把一次案例执行组织成 G0–G4 门禁流水线：先落契约兜底，再逐步门禁推进，任何时刻中断都有已验证的部分交付物。

## 运行约定（先读）

先读 `/input/case.json` 与 `/input/task.md`。`/app/output/result.json` 必须含原始 `case_id` 与 `output_contract` 全部字段。工作目录 `/app/work`。技能目录解析：`/skills/weekly-skill` → `$WEEKLY_SKILL` → 本文件所在目录。

## 工作流

1. **G0 契约兜底（第一件事）**：`python <skill>/scripts/bootstrap.py --case /input/case.json --outdir /app/output`。立刻得到 status=partial、含全部 contract 字段的 result.json。此后任何崩溃都有合法交付物。
2. **制定计划**：把案例拆解为门禁步骤，写 `/app/work/plan.json`（格式见下）。步骤应覆盖 `references/gate_checklists.md` 的 G1（模式与口径）→ G2（查询执行）→ G3（结果核验）→ G4（交付完成）；每步声明 `produces` 产物。
3. **门禁执行**：`python <skill>/scripts/gate.py --plan work/plan.json --state work/run_state.json --logdir work/logs`。每步子进程执行、日志落盘、产物非空校验、checkpoint 写盘。**失败即停**：修复后重跑同一命令，已完成步骤自动跳过（断点续跑）。
4. **异常分类**：所有异常按 `references/exception_taxonomy.md` E1–E6 归类写入 analysis_notes.md；不存在"悄悄跳过"。
5. **就地升级 result.json**：每过一门，把占位符替换为真实结果；G3 通过后才允许把 status 改 complete 的候选。
6. **提交前自检**：`python <skill>/scripts/selfcheck.py --case /input/case.json --outdir /app/output --out work/selfcheck.json --md work/selfcheck.md`。**NO-GO 不交付 complete**：按 blocking 清单修复或降级为诚实 partial。

plan.json 格式：

```json
{"steps": [{"name": "G1_schema", "gate": "G1",
            "cmd": ["python3", "...", "..."],
            "produces": ["/app/work/schema.json"]}]}
```

## 异常处理

除 E1–E6 分类处置外：

| 情况 | 处置 |
|-|-|
| 任一步骤失败 | gate 停止、状态落盘；读该步 log 定位；修复后重跑自动续跑。 |
| 预算将尽 | 停止开新门；把当前 result.json 定为 partial，limitations 写明"在 G<n> 中断"；已完成门的产物保留在 /app/output。 |
| selfcheck NO-GO | 按 blocking 修复；无法修复的字段保留占位符并在 limitations 逐条解释。 |
| output_contract 结构异常 | bootstrap 递归查找字段；找不到时以 case.json 全文为准手写字段清单并记录。 |

## 附带脚本与资源

- `scripts/bootstrap.py` — case.json → partial result.json 骨架（递归提取 case_id/output_contract）。
- `scripts/gate.py` — 门禁流水线执行器：子进程、日志、产物校验、checkpoint、断点续跑。
- `scripts/selfcheck.py` — 交付前 C1–C7 自检，GO/NO-GO 判定（JSON+Markdown）。
- `references/gate_checklists.md` — G0–G4 各门检查项。
- `references/exception_taxonomy.md` — E1–E6 异常分类与处置。

## 最小调用示例（合成示例，非正式案例结果）

合成输入：脚本生成合成 `case.json`（含 case_id 与三字段 output_contract）与一个三步 plan（其中一步演示失败→修复→续跑）。执行：

```
python <skill>/scripts/bootstrap.py --case case.json --outdir output
python <skill>/scripts/gate.py --plan plan.json --state run_state.json --logdir logs
python <skill>/scripts/selfcheck.py --case case.json --outdir output --out selfcheck.json --md selfcheck.md
```

示意输出（示例，非正式结果）：bootstrap 立即产出 partial result.json；gate 第一步失败后重跑自动跳过已完成步骤；selfcheck 对完整交付判 GO、对缺失字段的交付判 NO-GO 并列出 blocking。完整可跑脚本见 `examples/run_example.sh`。

## 边界与限制

本 Skill 管理过程质量，不替代表查询/统计/渲染方法本身（与各专项 Skill 互补）；gate 的步骤命令由分析者按案例编写，脚本只保证执行纪律与留痕；selfcheck 校验契约完备性与引用一致性，不能验证科学正确性。
