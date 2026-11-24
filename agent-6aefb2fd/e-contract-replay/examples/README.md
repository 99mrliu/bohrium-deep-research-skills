# 最小调用示例（合成示例 / SYNTHETIC EXAMPLE）

> 本示例使用固定种子程序生成的玩具数据（120+3 行 3 列，与任何正式案例无关），
> 仅用于说明接口与流程；输出**不是**正式案例结果。

## 运行

```
python3 examples/make_example.py /tmp/cr-example
```

## 示例做了什么

1. 生成玩具输入（含 3 条完全重复的 raw 表 + case.json）与全套玩具交付物
   （cleaned 表、statistics.json、cleaning_evidence.json、一张直方图、report.md，
   报告数字取自真实计算值）。
2. `contract_seal.py`：`begin` 立即写 partial；故意 fill 一个不存在的
   `/app/output` 路径被 **FILL_REFUSE** 拒绝；填齐字段后 `seal` success。
3. `replay_check.py` 第三方复算：R1 契约完整、R2 cleaned 120 行 ≤ 原始 123 行、
   R3 报告全部数字命中交付 JSON ∪ 复算池 → 通过。
4. 把报告中 m1 均值篡改为 9.876 → R3 判定无源数字，退出码 7。

## 预期打印（节选）

```
CONTRACT_BEGIN: partial written, 6 fields pending
CHECK OK: fill 拒绝悬空 /app/output 路径
CONTRACT_SEAL: status=success problems=0
REPLAY_PASS: R1_contract — case_id 一致、字段与路径完整
REPLAY_PASS: R2_row_accounting — cleaned 120 行 vs 原始 ... 123 行
REPLAY_PASS: R3_number_replay — 报告数字全部可溯源
REPLAY_FAIL: R3_number_replay — 无源数字: [('9.876', ...)]
CHECK OK: 报告数字篡改为 9.876 被复算抓获（退出码 7）
SYNTHETIC EXAMPLE PASSED -> /tmp/cr-example
```
