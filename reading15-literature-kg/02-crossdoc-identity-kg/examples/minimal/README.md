# 最小调用示例（合成数据）

**声明**：`input/papers.json` 中两段文字是为演示人工编写的合成文本，
DOI 为虚构占位，不是真实论文；`output/` 全部产物仅说明接口与流程，
**不冒充正式案例结果**。

## 运行

```bash
python3 scripts/run_example.py   # 重新生成 examples/minimal/output/
python3 scripts/selftest.py      # 正向端到端 + 负向守门测试
```

## 输入（input/）

- `papers.json`：两篇合成论文（SYN-A / SYN-B），各 5 个 JATS 风格段落；
- `mentions.json`：12 条提及（Agent 语义抽取的模拟结果），含别名、
  定义性属性与测量值；
- `relations.json`：12 条关系，均带 source_id + paragraph_id + 逐字短引；
- `queries.json`：4 条查询规格（neighbors / filter / path / filter）；
- `case.json`：模拟 case（含迷你 output_contract，演示动态镜像）。

## 预期裁决

| 候选对 | 裁决 | 依据 |
|-|-|-|
| LLZO（M-A1 × M-B1） | MERGE | 化学式 Li7La3Zr2O12 一致 |
| LATP（M-A6 × M-B6） | MERGE | 化学式一致 |
| sintering（M-A2 × M-B2） | KEEP_DISTINCT | 烧结条件 1100 C/12 h vs 1230 C/2 h 冲突 |
| random forest model（M-A4 × M-B4） | KEEP_DISTINCT | R2 数值 0.81 vs 0.74 冲突 |
| SynthIon-1 × SynthIon-2 | KEEP_DISTINCT | 数据集版本不同 |
| XRD（M-A3 × M-B3） | UNDECIDED | 仅通用术语别名相同，证据不足 |

## 输出（output/，由脚本生成）

`result.json`、`graph.json`、`graph.jsonl`、`identity-decisions.json`、
`conflicts.json`、`queries.json`、`verification-report.json`、
`graph.dot`、`graph.svg`、`preview.txt`。
终图 12 节点（含 2 个合并节点、2 个来源作用域指标节点）、12 条边；
4 条查询全部实际执行成功；1 条跨篇测量冲突（LLZO 电导率 3.2e-4 vs
1.1e-3 S/cm）分别保留并记录。
