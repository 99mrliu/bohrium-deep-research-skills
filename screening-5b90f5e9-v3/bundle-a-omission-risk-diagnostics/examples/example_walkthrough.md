# 合成示例走查（example walkthrough）

> **声明：本目录全部输入与输出均为合成示例，非真实评测案例。** 12 条题录为虚构，
> judgments 为手工构造的输入夹具，仅用于演示与验证诊断流程。

## 1. 示例设定

- 研究问题：肥胖青少年（12–18 岁）中，GLP-1 受体激动剂相对安慰剂/生活方式干预能否在 RCT 中
  降低 BMI z-score（见 `input/case.json`，含 5 个 facet 与 output_contract）。
- 上游输入夹具：`input/records.json`（12 条虚构题录）+ `input/judgments.json`
  （逐条判定：4 纳入、8 排除）。
- 夹具中刻意埋入的遗漏风险：
  - `R03`/`R09`：恰好一条判据 not_met 的单理由排除（`single_criterion_exclusion`）；
  - `R05`：干预判据 uncertain（tirzepatide 双靶点归属）+ 单理由排除；
  - `R06`：设计判据证据锚定弱（quote "Weight trajectories" 并不能证明非 RCT）；
  - `R11`：被排除但没有任何 not_met 判据（仅凭 uncertain 结局判据排除），风险最高；
  - `F3_comparator`（生活方式对照）：纳入的 4 篇全部为安慰剂对照 RCT，该 facet 零纳入，
    用于演示"可能是检索遗漏而非真空"的报警；
  - `R04`/`R08`/`R12`：多条判据 not_met 的稳健排除，作为对照组不进险漏队列。

## 2. 如何运行

```bash
bash examples/run_example.sh
```

脚本将 `examples/input/` 复制到 `examples/run/input/`（模拟评测 `/input`），以
`examples/run/work`、`examples/run/output` 模拟 `/app/work`、`/app/output`，
按 SKILL.md 工作流顺序执行 6 个脚本并打印各自真实 exit code。

## 3. 预期产物与看点

| 产物 | 看点 |
|---|---|
| `run/output/result.json` | 合同 10 字段齐备；selfcheck 通过后 status=completed |
| `run/work/near_misses.json` | 险漏队列 5/8：R11(6) > R05(5)=R06(5) > R03(3)=R09(3)；R04/R08/R12 稳健排除不入队 |
| `run/work/fragility_report.json` | 理由码分布 EX_POP_AGE×3 / EX_DESIGN_NOT_RCT×2 / EX_OUTCOME_NO_BMI×2 / EX_INT_NOT_GLP1×1；单理由排除 4/8；fragile_share=0.625 ≥ 0.5 → fragile_flag=true |
| `run/work/facet_coverage.json` | F1/F2/F4/F5 有命中；F3_comparator 零纳入 → zero_inclusion_alarm |
| `run/work/recheck_worklist.json` | 按风险分降序的人工复核队列，全部 pending_human_recheck |
| `run/output/omission_statement.md` | 六节结构化遗漏说明（排除概况/稳健性/复核条目/facet 报警/无法回答的问题/后续动作） |
| `run/work/selfcheck.json` | 合同完整性、54 条证据 quote 锚定校验、status 终置三项全 pass |

## 4. 走查结论（人工目检）

- 险漏队列排序与夹具设计意图一致：唯一"无 not_met 依据"的 R11 排第一；证据锚定弱的 R06 与
  uncertain 的 R05 并列第二梯队；两条干净单理由排除居后；三条稳健排除正确地被排除在队列外。
- F3 报警解释措辞守住边界：只说"须人工回查"，未定性为检索遗漏或真空。
- 遗漏说明第 5 节明确列出本快照无法回答的问题，未声称全局召回。
- 降级路径（judgments 缺失 → 全链 exit 2、status=partial；证据被篡改 → selfcheck exit 3）
  均已实测，见 `selftest_log.md`。
