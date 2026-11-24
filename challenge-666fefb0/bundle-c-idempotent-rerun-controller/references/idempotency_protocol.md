# 幂等与回滚协议（过程质量控制细则）

## 不变量（任何时刻对评审可证）

1. **无计划不变更**：`ops_plan.json` 先于一切文件变更存在；plan_hash 覆盖
   全部操作与计划内跳过，改决策必须重新 plan（hash 变化即留痕）。
2. **日志先行**：每条操作完成后立即重写完整 journal（checkpoint），进程在
   任意两条操作之间死亡，journal 都处于一致状态。
3. **续跑等价**：apply 重跑时，已完成且目标哈希核验通过的操作转
   `verified_skip`，不产生新文件；最终输出树与不中断运行逐字节一致。
4. **不覆盖**：目标已存在且内容不同 → `-n` 后缀 + `conflict_renamed`，
   任何已有文件不被覆盖、不被删除。
5. **可回滚**：undo 逆序移除 journal 中的全部落地文件并清空目录，
   `undo_log.json` 记录每个移除路径；回滚后 `tree_after.file_count == 0`。

## 输出树指纹

`tree_fingerprint(root)`：对 root 下全部文件计算
`sorted(relpath:sha256)` 拼接后再 SHA-256。两个指纹相等 ⟺ 两棵树文件名、
相对路径、内容完全一致。

## 幂等证书判定

`certify` 流程：指纹 fp1 → 完整重跑 apply → 指纹 fp2。
`granted = (fp1 == fp2) 且第二次运行无新执行的操作`。
证书被写入 `operations_log.idempotency_certificate` 并影响 status：
未获证书时 status 不得为 complete。

## 断点续跑演示（评审复现路径）

```
apply --stop-after 3   # 注入崩溃：3 条后 exit 3，journal 含 3 条一致记录
apply                  # 续跑：3 条 verified_skip，其余正常执行
certify                # 再完整跑一遍，指纹不变 → 签发证书
```

## 状态机

```
init → plan → apply ⇄ (中断→apply 续跑) → verify → certify → finalize
                       ↘ undo（任意 apply 之后可回滚，回滚后可重新 plan/apply）
```
