# examples/minimal — 合成示例（SYNTHETIC）

> **本目录全部内容为手工编造的合成数据**，仅用于端到端演示与回归测试；
> 不代表任何真实 Crossref / arXiv 检索结果。DOI（如 `10.1038/nature12373`）
> 仅借用真实存在的格式，对应的题录内容均为虚构。

## 目录内容

| 文件 | 角色 |
|---|---|
| `case.json` | 合成案例定义（case_id、task、windows、output_contract） |
| `task.md` | 任务说明 |
| `materials/round0_*.json` | 第 0 轮（历史轮次）源响应，用于生成 previous 状态 |
| `materials/previous_journal.jsonl` | 第 0 轮真实运行生成的 append-only journal |
| `materials/previous_snapshot.json` | 第 0 轮后的水位 + 已知条目注册表 |
| `materials/round1_*.json` | 第 1 轮两个源的固化题录响应 |
| `materials/round2_*.json` | 第 2 轮两个源的固化题录响应 |
| `output/` | `run_minimal_example.py` 的真实运行产物 |

## 刻意设计的判定场景（第 2 轮）

| 条目 | 期望判定 | 命中规则 |
|---|---|---|
| arXiv 2506.04567v1（新题） | new | R0-new |
| arXiv 2506.01234v2 | version_update | R2-arxiv-version |
| Crossref 10.1038/s41586-025-00001-x（relation 链接 2506.01234） | version_update | R3-preprint-published-link |
| arXiv 2506.09988v1（标题仅大小写/结尾标点差异） | duplicate | R4-title-fingerprint |
| Crossref 10.1038/Nature12373（DOI 大小写差异） | duplicate | R1-exact-doi |

另：第 1 轮 arXiv 材料含 1 条窗口外条目（2025-05-20），期望 `skipped` /
RX-out-of-window。

## 运行方式

在 **bundle 根目录**（`02-replayable-increment-ledger/`）执行：

```bash
python3 scripts/run_minimal_example.py
```

脚本依次：复制 previous 状态 → 第 1 轮 record → 第 2 轮 record →
回放两轮 → 第 2 轮幂等校验 → 组装 `output/result.json`，最后打印
PASS/FAIL 摘要。期望：两轮 replay 均 `consistent`，幂等 `pass`
（零新事件、零二次投递），result `status=complete`。

重复执行本脚本会先清空 `output/` 再重跑，产物确定可复现。
