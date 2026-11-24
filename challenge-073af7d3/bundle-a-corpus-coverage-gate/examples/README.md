# examples/ — 合成示例（SYNTHETIC / 合成数据）

本目录所有数据均为**合成示例数据**，每条记录带 `"synthetic": true`，不对应任何真实文献。

## synthetic_case/

- `corpus.jsonl`：10 条合成记录，故意植入三类异常：
  1. **R009**：与 R001 **DOI 完全相同** → 去重时 `doi_exact` 规则应触发；
  2. **R010**：R002 的**标题变体**（换序、不同 DOI）→ `title_jaccard>=0.9` 规则应触发；
  3. **R008**：**缺少年份** → `date_provenance="missing"`，缺失率 1/8 = 0.125 ≤ 0.2，门禁仍为 pass；
  4. 保留记录年份分布为 2023:3 / 2024:3 / 2025:1，末年计数低于 `0.4 × median(0,3,3)=1.2`，
     `right_censoring.assessment` 应为 `suspected_partial`（右删失预警）。
  另有 R004（print 2024 vs online 2023）与 R006（online 2024 vs preprint 2023）用于演示
  日期策略对年份归属的影响（默认 `--date-policy print`）。
- `tampered_ledger.json`：被篡改的覆盖度台账，`closure` 为 `10 ≠ 8+2+1=11` 且
  `closure_ok` 被恶意置为 `true`，用于证明 `gate_check.py` 重算闭环方程而非信任文件内标志。

## 运行

```bash
bash examples/run_example.sh
```

- GOOD：ingest → coverage → gate，预期 `gate=pass`、exit 0；工件复制到 `example_output/good/`。
- BAD：ingest → 注入篡改台账 → gate，预期 `gate=fail`、exit 1，
  违规含 `coverage_closure_mismatch`；工件复制到 `example_output/bad/`。

`example_output/` 中的文件是本脚本真实运行产生的工件，不是手写样例。
