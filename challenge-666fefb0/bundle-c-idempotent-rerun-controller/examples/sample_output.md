# 合成示例实际运行输出摘录

**本页为合成示例的真实运行记录（2026-11-24，macOS，Python 3 + pdftotext）。**
输入为 `make_fixture.py` 生成的演示数据，非正式案例结果。`fixture/` 由脚本生成，
不随 bundle 分发。

```
$ python3 make_fixture.py && bash run_example.sh
--- 1. init ---
{"case_id": "case-synthetic-demo-c", "files": 13, "alias_groups": 2}
--- 2. plan ---
{"plan_hash": "b40ee9ff6e0f0607", "ops": 10, "planned_skipped": 3}
--- 3. apply with INJECTED CRASH after 3 ops (exit code 3 expected) ---
{"executed": 3, "interrupted": true, "remaining": 7}
exit=3 (3 = simulated crash, journal stays consistent)
--- 4. resume apply ---
{"executed": 7, "interrupted": false, "total_ops": 10}
--- 5. verify ---
{"ok": true, "problems": 0}
--- 6. certify idempotency ---
{"granted": true, "fingerprint": "3c51347a5cba8fbc"}
--- 7. finalize ---
{"status": "partial", "indexed": 10, "skipped": 3}
--- 8. undo demo (rollback, then rebuild) ---
{"removed": 10, "rolled_back": true}
{"executed": 10, "interrupted": false, "total_ops": 10}
{"ok": true, "problems": 0}
rollback-then-rebuild OK
```

## 关键产物

- `ops_plan.json`：10 条操作 + 3 条计划内跳过，`plan_hash=b40ee9ff…`；
- `operations.jsonl`：每条含 src/dst 双侧 SHA-256 与状态（`copied` /
  `verified_skip` / `conflict_renamed`）；
- `idempotency_certificate.json`：`granted=true`，两次完整运行的输出树指纹
  均为 `3c51347a5cba8fbc…`（13 文件树逐字节一致）；
- `verify_report.json`：`ok=true`，覆盖率 13/13（10 操作 + 3 显式跳过）；
- `result.json`：`status=partial`（corrupt-scan.pdf 损坏、old-scanned-article.pdf
  无文本层、no-permission.pdf 无权限），含 output_contract 全部字段，
  `operations_log` 内嵌幂等证书；
- `undo_log.json`：10 个移除路径，`tree_after.file_count=0`。
