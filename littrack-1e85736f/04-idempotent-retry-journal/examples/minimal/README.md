# 合成示例（SYNTHETIC EXAMPLE）：idempotent-retry-journal 最小演示

> **声明**：本目录全部内容（case.json、task.md、materials/、output/）均为
> **人工构造的合成示例**，仅用于演示失败重试与幂等恢复流程。其中出现的 DOI
> （如 10.1038/nature12373）仅借用真实存在的 DOI 格式样例，题录文本均为虚构，
> 与真实文献追踪任务无关。

## 一键运行

在 bundle 根目录执行：

```bash
python3 scripts/run_minimal_example.py
```

脚本会先重置 `output/` 并把 `materials/source_b.json` 还原为损坏版，然后依次
演示三个阶段，全部产物写入 `output/`。脚本可反复执行，结果一致。

## 三阶段说明

| 阶段 | 场景 | 预期 |
| --- | --- | --- |
| 第 1 次运行 | `eupmc_b` 材料是截断 JSON（parse_error） | 3 次尝试记入 `retry_journal.jsonl`（退避计划 +5s/+30s/+120s，仅记录不 sleep）；`checkpoint.json` 保存 crossref_a、publisher_c 已完成；`eupmc_b` 降级；`result_run1.json` 为 `status=partial` |
| 第 2 次运行 | `materials/source_b.json` 被修复版覆盖 | checkpoint 命中跳过 crossref_a / publisher_c，只补 eupmc_b；修复版中第 2 条缺 `title`，按 missing_field 记录级跳过并写入 uncertainty；`result_run2.json` 为 `status=ok` |
| 第 3 次运行 | 无任何变化 | 全部源命中 checkpoint：journal 零新事件、delivery_log 零新投递；另做一次重复投递键抑制自检；结论写入 `idempotency_report.json` |

## 文件地图

- `case.json` / `task.md`：合成案例定义（含 output_contract 与窗口配置）
- `materials/source_a.json`：Crossref 风格快照（正常，2 条）
- `materials/source_b_broken.json`：Europe PMC 风格快照（**刻意截断**）
- `materials/source_b_fixed.json`：修复版（第 2 条**刻意缺 title**）
- `materials/source_b.json`：运行期由脚本在损坏版/修复版之间切换的工作副本
- `materials/source_c.json`：出版商简单风格快照（空窗口，0 条）
- `output/`：真实运行产物
  - `work/retry_journal.jsonl`：每次尝试一条（attempt_no、故障类别、退避计划、决策）
  - `work/checkpoint.json`：源×窗口粒度的断点状态
  - `work/delivery_log.jsonl`：幂等投递账本（delivery_key 去重）
  - `work/runs.jsonl`：每轮运行摘要
  - `result_run1.json` / `result_run2.json` / `result_run3.json`：三阶段交付快照
  - `result.json`：最终交付（= 第 3 次运行结果）
  - `idempotency_report.json`：幂等校验结论
