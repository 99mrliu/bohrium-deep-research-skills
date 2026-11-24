# budget-runbook-qc

**过程质量控制与预算编排** Skill —— 玻尔 Playground 竞赛题 challenge-32c0210d
（学位论文与长文档写作）五方向 bundle 之一（e 方向）。

把 900 秒 / 64 次模型请求的硬预算变成显式调度对象：

| 组件 | 作用 |
|-|-|
| `scripts/budget_ledger.py` | `/app/work/budget.json` 预算账本：init / tick / status；水位 正常(0–70%) / 收紧(70–85%) / 保底(>85%) 三级，每步先查水位 |
| `scripts/checkpoint.py` | partial-first：读完 case.json 立即把骨架 `result.json`（status=partial、契约键全 null）原子写入 `/app/output`；promote 逐字段升级；finalize 仅在验收门全过后置 complete |
| `scripts/qc_gates.py` | 验收驱动循环：workorder 每条 acceptance 编译成机械断言（grep 缺失/存在、图表引用完整性），编译不出转 manual 门由模型显式判定；输出 `gates_report.json` |
| `scripts/fault_inject.py` | 在 scratch 副本上注入受控故障（删图题、写坏 JSON、删契约键），证明 partial 降级路径全部受控（非零退出 + 问题落盘），产出 `fault_report.json` |
| `references/runbook.md` | T0–T900 分钟级运行手册：阶段预算配额、水位触发动作表、3/5/10 项工单裁剪规则 |
| `references/gates_dsl.md` | 验收断言 DSL 规范 |

## 快速验证

```bash
cd examples/synthetic
/bin/bash run_example.sh            # 端到端跑通并与 expected/ 逐字节比对
/bin/bash run_example.sh --freeze   # 重新固化 expected/（构建者用）
```

`examples/synthetic/` 为**合成示例**（自造 3 个短章节 + case.json + 2 项工单，
与任何真实论文无关），全部产物带 `SYNTHETIC EXAMPLE — 合成示例，非正式案例结果` 标注。

## 约束

python3 标准库实现，无外部依赖；脚本路径全参数化；输出确定性
（相对秒数计时、无绝对路径、无时间戳）；所有写盘原子化（tmp+rename）。
