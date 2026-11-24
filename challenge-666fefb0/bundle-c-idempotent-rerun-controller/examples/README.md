# 最小调用示例（合成示例）

**声明：本示例为合成示例。** 夹具文件、决策与输出均为演示数据，不对应真实文献，
也不是平台正式案例结果。

## 运行

```bash
cd examples
python3 make_fixture.py     # 生成合成夹具 fixture/input（13 个文件）
bash run_example.sh         # 完整过程质量链路（含崩溃注入与回滚演示）
```

## 链路（八步）

1. `init`：只读盘点 + 保底 partial result.json；
2. `plan`：生成带 `plan_hash` 的操作计划（10 操作 + 3 计划内跳过）；
3. `apply --stop-after 3`：**注入崩溃**（exit 3），journal 保留 3 条一致记录；
4. `apply`：续跑，3 条转 `verified_skip`，剩余 7 条执行；
5. `verify`：哈希与覆盖率复核；
6. `certify`：完整重跑一遍，输出树指纹逐字节一致 → 签发
   `idempotency_certificate.json`（granted=true）；
7. `finalize`：终版 result.json（status=partial，3 个 skipped 如实列出）；
8. `undo` + 重建：回滚至空树（removed=10, rolled_back=true），再 apply/verify
   完整重建——证明回滚与重建都可证。

实际运行输出摘录见 `sample_output.md`。
