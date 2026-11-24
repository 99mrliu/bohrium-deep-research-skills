# 最小示例运行记录（合成示例）

> 本示例的判定文件与台账均为**合成数据**，仅演示审计机制，不对应真实筛选。

## 输入

- `decisions_run_a.json`：6 条合成判定（2 included / 3 excluded / 1 needs_human）；
- `decisions_run_b.json`：与 a 相同，但 `rec-005` 翻转成 excluded+EX-POPULATION
  （模拟非确定复跑）；
- `decisions_run_b_fixed.json`：与 a 内容相同、顺序相反（验证集合语义与顺序无关）。

## 实际执行与结果（2026-11-24，Python 3，macOS arm64）

```text
[1] 正确台账 200 → dedup 23 → screened 177 → 12+160+5
    VALIDATE PASS (4 checks)   C1/C2 差额=0
[1b] 篡改台账 excluded 160→159（临时副本）
    VALIDATE FAIL              C2-screening-closure 差额=1，exit 3
[2] manifest create(2 files) → verify PASS
[2b] 篡改产物后 verify（临时副本） FAIL，changed=["audit_ledger.json"]，exit 3
[3] rerun_diff a vs b    → NONDETERMINISTIC，flips=1（rec-005），exit 3
[4] rerun_diff a vs b_fixed → DETERMINISTIC，exit 0
EXAMPLE PASS
```

退出码 0；重跑 run_example.py 结论一致（台账时间戳固定为 2026-11-24T00:00:00Z，
产物逐字节可复现）。

## 产物目检结论（output/）

- `audit_ledger.json`：6 条阶段记录，operator=example-driver，basis 指向示例目录；
- `closure_report.json`：C1–C4 全 PASS，每条含算式与差额 0；
- `rerun_report_ab.json`：deterministic=false，label_flips 恰为 rec-005；
- `rerun_report_fixed.json`：deterministic=true，common=6；
- `manifest.json`：覆盖 output 下 4 个产物，sha256 齐备。
