# 最小调用示例（合成示例）

> **本示例为合成示例**：输入库与输出均为虚构数据，仅说明接口与完整流程，
> 不是平台正式案例的结果。

## 输入（make_fixture.py 生成的虚构资料库）

```
input/
  case.json            # case_id=synthetic-court-001，2 个问题 + output_contract
  task.md
  reports/cat9_v1.txt   # 历史版本：CO 转化率 78%（已作废）
  reports/cat9_v2.txt   # 当前版本：更正为 85%
  reports/版本备注.txt   # 行政备注：v2 有效，v1 作废
```

## 调用

```bash
bash examples/run_example.sh
```

## 示意输出（实际运行得到，数据虚构）

1. `suff_index`：2 个问题、3 个文件、预抽数值事实若干；保底 result.json。
2. `suff_matrix`：q1 覆盖率 4/4=1.0；q2（水热稳定性）覆盖率 1/3≈0.33，
   未命中证据面"稳定性、测试结"等。
3. `suff_conflict`：登记 3 条冲突，核心是"CO 转化率 78%（v1，F001:L2）
   vs 85%（v2，F002:L2）"。
4. `suff_verdict`：
   - q1 机器裁决 **L4 基本可答**（覆盖率 1.0，存在相关冲突须按行政备注
     消解，作答须注明"以 v2 为准，历史版本为 78%"）。
   - q2 机器裁决 **L2 证据不足拒答**；示例演示模型越级申报 L5 后被
     强制回降至 L3 并在 result.json 的 uncertainty 留痕：
     "问题 q2 模型申报 L5 被机器裁决回降（机器 L2）"。

拒答形态（L2 自动写入骨架）："证据不足，拒答。缺少证据面：稳定性、
测试结"——正式运行时模型应补齐四要素（拒答句、检索留痕、缺口说明、
补救路径），见 references/abstention_protocol.md。
