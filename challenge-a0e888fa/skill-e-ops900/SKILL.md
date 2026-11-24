---
name: ops900-budget-ops-pipeline
description: >-
  面向 900 秒/64 次请求/16K tokens 预算的科研数据清洗运行时工程。当案例
  要求在受限 harness 预算内可靠完成"缺失分类、单位换算、去重、异常标记、
  质量报告、result.json"全流程时使用。核心策略：一次命令跑完全部机械工序
  （确定性、幂等、检查点续跑）、Agent 只读 <2KB 紧凑摘要、预算水位降级
  阶梯、任何时刻都有合法的 result.json 可交付。绝不插补缺失/非法源值。
---

# ops900：预算内的确定性清洗作战室

## 重心

harness 预算（64 请求 / 900s / 每响应 16384 tokens）下最常见的失败不是
算错，而是**没跑完**：读文件读到一半超时、result.json 最后才写导致交白卷、
长输出把上下文挤爆。本技能把运行时当工程问题管理：机械工序全部压进
**一次** `pipeline.py` 调用；模型请求只花在三个真正需要判断的地方——
读材料、写 rules.json、审 digest。


脚本路径说明：技能默认安装在 `/skills/weekly-skill`，下文以 `$SK` 代指该目录；
若不在该路径，用 `find / -maxdepth 6 -name 'scripts' -path '*skill*' 2>/dev/null` 定位技能根。
所有脚本均为 Python 3 标准库、确定性、只读输入文件。

## 预算分配（总预算 64 请求 / 900s）

| 阶段 | 请求 | 说明 |
|---|---|---|
| 0 读案+固证+保底 | ≤6 | case.json/task.md/材料各一次；立即落 result.json 骨架 |
| 1 写 rules.json | ≤4 | 对照字典/工单填配置（唯一需要判断的产物） |
| 2 跑管道 | 2 | 一次运行 + 一次 digest |
| 3 审阅与补正 | ≤8 | digest 发现的问题→改 rules.json→`--resume` 重跑 |
| 4 交付 | ≤4 | result.json 填齐、status 定版、复制产物 |
| 余量 | ≥40 | 全部留给异常与返工 |

## 流程

```bash
python3 $SK/scripts/timewatch.py start --workdir /app/work     # 开工打点
mkdir -p /app/output
# 读案后：先写 /app/output/result.json 骨架（case_id + 合同全字段占位 +
#   status=in_progress），再固证输入（sha256 记入 /app/work/notes.md）
# 若输入有编码故障：先修复为规范 CSV 存 /app/work/，以其为 pipeline 输入
python3 $SK/scripts/pipeline.py --rules /app/work/rules.json \
    --workdir /app/work --outdir /app/output
python3 $SK/scripts/digest.py /app/output                       # <2KB 摘要
python3 $SK/scripts/timewatch.py status --workdir /app/work     # 预算水位
```

- 工序中途崩溃/被截断：`pipeline.py --resume` 从检查点续跑，幂等。
- digest 暴露问题：只改 rules.json 再 `--resume`（已完成的工序自动跳过）。
- rules.json 写法见 `references/rules_spec.md`；降级阶梯见
  `references/degradation_ladder.md`。

## 三条铁律

1. **保底优先**：result.json 骨架先于一切分析落盘，此后只增量更新；
2. **机器干活**：缺失分类/换算/去重/标记/报告数字全由脚本重算，模型不手算、
   不手抄数字；
3. **诚实降级**：review_queue 非空 → status=partial 并在 limitations 写明；
   工序失败 → status=failed + 断点说明；绝不插补缺失/非法源值。

## 异常处理

- 空表/坏表：pipeline 报错退出码 6，骨架已在 → 填 status=failed 即完成交付；
- 键冲突：全部保留进 review_queue.csv，不静默删；
- 未知单位：配置里没有的换算就不发生，原值保留；
- 预算水位 >750s：停止一切新工序，立即定版交付。

## 最小示例

`examples/`：合成表 + 填好的 rules.json + 一次完整运行与一次 `--resume`
续跑的真实产物，见 `examples/README.md`。数据为人工编造。
