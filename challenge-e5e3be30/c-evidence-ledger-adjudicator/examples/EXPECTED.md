# EXPECTED.md — 合成示例实际输出说明

> 本文档记录 `run_example.sh` 的**实际运行输出**（非手写预期）。
> 全部为**合成示例**：`paper.txt` 是虚构论文，`demo_ledgers/` 是预填演示输入。

## 最终判定（verdict_engine 确定性输出，两次运行逐字节一致）

| 论断 | base（命中规则） | 最终 verdict | conflict |
|---|---|---|---|
| C1 空腹血糖显著降低 | supported（R2） | **supported** | false |
| C2 HbA1c 降低 30% | supported（R4）→ R7 降级 | **partially_supported** | true |
| C3 对 ALT 无影响 | contradicted（R3） | **contradicted** | false |
| C4 改善睡眠质量 | insufficient_evidence（R6） | **insufficient_evidence** | false |

四条论断恰好覆盖四种判定结果。

## 关键输出摘录（实际终端输出）

### [1/7] ledger_init
```
已生成 .../demo_work/ledger-C1.json（锚点 5 个：A1:condition, A2:number, A3:number, A4:comparator, A5:comparator）
已生成 .../demo_work/ledger-C2.json（锚点 4 个：A1:condition, A2:number, A3:comparator, A4:number）
已生成 .../demo_work/ledger-C3.json（锚点 1 个：A1:negation）
已生成 .../demo_work/ledger-C4.json（锚点 3 个：A1:condition, A2:comparator, A3:number）
```
注意 C2 的 `30%` 锚点自动带变体：`["30%", "30％", "0.3", "thirty percent", "百分之三十", "30", "thirty", "三十"]`；
`HbA1c` 中的 "1" 未被误提为数值锚点。

### [3/7] ledger_validate（演示输入里 C4-E1 故意过度标注）
```
OK      [ledger-C1.json] 通过（claim_id=C1, 证据 1 条）
OK      [ledger-C2.json] 通过（claim_id=C2, 证据 2 条）
OK      [ledger-C3.json] 通过（claim_id=C3, 证据 1 条）
WARNING [ledger-C4.json] W2 evidence[0](E1): topical 证据却覆盖全部锚点（疑似把主题相关当作直接证据，请复核强度档）
```
W2 正是"模型想把主题相关当直接证据"的机检信号；WARNING 不阻塞（exit 0）。

### [4/7] verdict_engine --explain（C2 与 C4 的推导）

C2（摘要 30% vs 表 1 的 8%，direct 对撞）：
```
S1 证据分组: pro_same=1 (direct=1), con_opp=1 (direct=1)
S2 强度: pro_rank=3, con_rank=3
S3 覆盖: ... pro_full=True; con_direct 覆盖=[A1..A4] → con_core=True
S4 冲突: conflict=True（锚点重叠对 1 组）
S5 命中规则 R4 → 基准判定 base=supported
S6 R7 冲突降级: supported → partially_supported
⇒ VERDICT: partially_supported (base=supported via R4, conflict=True)
```

C4（"主题相关被压回"演示：模型 annotator_note 写明初判倾向 supported）：
```
S1 证据分组: pro_same=2 (direct=0), con_opp=0 (direct=0)
S2 强度: pro_rank=1, con_rank=0
S3 覆盖: pro 覆盖=[A1..A3] → pro_full=False（无 direct，覆盖不计入）
S5 命中规则 R6 → 基准判定 base=insufficient_evidence
S7 备注: 存在 pro 证据但最高仅 topical —— 主题相关≠支持，按 R6 判 insufficient_evidence
⇒ VERDICT: insufficient_evidence
```

### [6/7] conflict_pairs
```
CONFLICT [C2] E1 <-> E2 共享锚点 ['A1', 'A2', 'A3', 'A4']
  pro (摘要, p.1): 结果：…糖化血红蛋白（HbA1c）较基线降低 30%；…
  con (3 结果 / 表 1, p.3): 表 1. … HbA1c 较基线变化 | -8% | -1% | 0.04 …
已写入 .../demo_work/conflicts.json（共 1 条冲突记录）
```
冲突记录并列双方 quote 与定位，直接供 result.json 的 conflicts 字段引用。

### [7/7] 组装
```
C1 -> supported (base=supported, conflict=False)
C2 -> partially_supported (base=supported, conflict=True)
C3 -> contradicted (base=contradicted, conflict=False)
C4 -> insufficient_evidence (base=insufficient_evidence, conflict=False)
```
产物：`demo_work/ledger-C{1..4}.json`（含写回的 adjudication）、
`demo_work/conflicts.json`、`demo_work/result-demo.json`。

## exit code 实测

- 四个脚本 `--help` → 0；流水线整体 → 0。
- 缺文件/坏 JSON → 2；空 claims 结构错误 → 1；台账 schema ERROR
  （非法 strength、covers 指向不存在锚点）→ validate 与 engine 均 exit 1 并阻塞。
