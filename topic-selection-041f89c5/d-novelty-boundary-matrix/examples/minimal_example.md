# 最小调用示例（合成示例，非正式案例结果）

全部输入为**虚构合成数据**，仅演示接口与流程。

## 输入

- `input/claims.json`：虚构提案的 4 条创新陈述（方法×2、数据×1、结论修正×1），含检索边界声明；
- `input/judgments.jsonl`：与 3 篇虚构已有工作（W1–W3）的 6 条对账记录；
- `input/judgments_bad.jsonl`：故意违例版（covers 缺 evidence_anchor、引用不存在的 C9）。

## 调用与预期输出（真实运行产生，已目检）

```bash
# 1. 正常对账 → 全绿
python3 scripts/novelty_matrix.py \
    --claims examples/input/claims.json \
    --judgments examples/input/judgments.jsonl \
    --out examples/output
# 退出码 0；判定：C1 covered、C2 covered、C3 partial、C4 uncovered
# （C4 的 uncovered 依赖 claims.json 中的 search_boundary 声明）

# 2. 违例对账 → 拦下
python3 scripts/novelty_matrix.py \
    --claims examples/input/claims.json \
    --judgments examples/input/judgments_bad.jsonl \
    --out examples/output_bad
# 退出码 1；2 条违例：C1×W1 covers 缺锚点（X1）、引用不存在的 C9（X2）；
# 且缺对账记录的 C2/C3/C4 全部降为 indeterminate
```

产物：`examples/output/` 下 `novelty_matrix.md`（●/◐/○ 覆盖矩阵）、`verdicts.json`、`boundary_memo.md`；`examples/output_bad/` 为违例版对照。
