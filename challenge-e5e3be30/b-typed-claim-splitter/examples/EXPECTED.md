# EXPECTED.md — 示意输出说明（合成示例）

> 本目录 paper.txt / claims.json / case.json 均为**合成示例**（虚构论文与
> 论断），仅用于演示流水线。以下所有输出均为 `bash examples/run_example.sh`
> **实际运行**（2026-11-23，macOS arm64，Python 3）的真实结果，非手工编造。

## 步骤 1：cue_scan（exit 0）

```
cue_scan 完成：3 条论断 → 14 个槽位，7 个原子子判断 → examples/_run/atoms.json
```

复合论断 c1（比较×2 + 因果 + 条件 + 范围）被拆为 4 个原子子判断：

| atom_id | type | 子判断文本 | 认领槽位 |
|---|---|---|---|
| c1#a1 | comparison | HX-300 在 600°C 退火下抗拉强度比 500°C 退火提高约 30% | s1(condition 在 600°C 退火下), s2(提高), s3(30%) |
| c1#a2 | comparison | 生产成本较传统工艺降低 12% | s4(降低), s5(12%) |
| c1#a3 | causal | 因为纳米晶粒细化与弥散相析出 | s6(因为) |
| c1#a4 | scope | 适用于所有铝合金 | s7(适用于), s8(所有) |

c2 拆为 2 个 comparison（a2 带 significance 修饰"显著"）；c3 为单
comparison 并给出"比较词但未拆分"提示。拆分点依据：强分隔"并且"、因果
标记"因为"、范围标记"适用于"恒拆；"，且"经两侧谓词检查后拆分。

## 步骤 2：coverage_matrix 破坏版（exit 1，打回演示）

将 `atoms.json` 中 `c1#a1` 的 `covers_slots` 人为清空后：

```
论断 c1：覆盖矩阵（子判断 × 槽位）
  atom_id        | type           | s1 | s2 | s3 | s4 | s5 | s6 | s7 | s8
  c1#a1          | comparison     | .  | .  | .  | .  | .  | .  | .  | .
  c1#a2          | comparison     | .  | .  | .  | 1  | 1  | .  | .  | .
  c1#a3          | causal         | .  | .  | .  | .  | .  | 1  | .  | .
  c1#a4          | scope          | .  | .  | .  | .  | .  | .  | 1  | 1
  [OMISSION] c1#s1 (condition '在 600°C 退火下')：槽位未被任何子判断认领（拆解遗漏，必须返工）
  [OMISSION] c1#s2 (comparator '提高')：…
  [OMISSION] c1#s3 (comparator '30%')：…
  → 未通过：存在遗漏，拆解必须返工
总计：3 条论断，omission=3，overlap 警告=0
exit=1
```

## 步骤 3：coverage_matrix 正常版（exit 0）

原始 `atoms.json`：14 个槽位全部被认领、无重叠 → `omission=0`，
`"passed": true`，exit 0。

## 步骤 4：aggregate（三条论断均 exit 0，--explain 逐步推导）

- **c1 → contradicted（规则 R2）**：a1/a2/a3 supported，但核心范围子判断
  a4"适用于所有铝合金"被原文"仅适用于 6xxx 系铝合金"直接反驳 →
  核心反驳一票否决。
- **c2 → partially_supported（规则 R6）**：a1（延伸率 15.2%）supported；
  a2（热导率提升 20%）原文声明"未测量热导率"→ insufficient_evidence
  （未报告≠反驳）；supported 与 insufficient 混合 → partially_supported。
- **c3 → insufficient_evidence（规则 R4）**：唯一子判断涉及腐蚀速率，
  原文声明"未开展任何腐蚀性能测试"→ 全部 insufficient。

## 步骤 5：汇总（实际输出）

```
c1 -> contradicted  (规则 R2)
c2 -> partially_supported  (规则 R6)
c3 -> insufficient_evidence  (规则 R4)
ALL OK：预期 exit code 均符合（cue_scan=0，coverage 破坏版=1，coverage 正常版=0，aggregate=0）
```

产物（`examples/_run/`，由脚本生成，可随时删除重建）：atoms.json、
atoms_broken.json、coverage_broken_report.json、coverage_report.json、
subjudgments_c{1,2,3}.json、verdict_c{1,2,3}.json。

## exit code 约定速查

| 脚本 | 0 | 1 | 2 |
|---|---|---|---|
| cue_scan.py | 成功 | 输入/运行错误 | 用法错误（argparse） |
| coverage_matrix.py | 通过（可带 overlap 警告） | 存在 omission（必须返工） | 输入/运行错误 |
| aggregate.py | 成功 | 输入/校验错误 | 用法错误（argparse） |
