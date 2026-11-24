# 任务说明（合成示例 · SYNTHETIC）

> 本示例全部数据为手工编造的合成数据，仅用于演示，非真实检索结果。

## 背景

本地已有历史增量状态：`materials/previous_journal.jsonl`（第 0 轮运行记录）
与 `materials/previous_snapshot.json`（第 0 轮后的水位与已知条目注册表）。

## 要求

1. 第 1 轮（窗口 2025-06-01T00:00:00Z ≤ t < 2025-06-08T00:00:00Z）：
   读取 `materials/round1_crossref.json`、`materials/round1_arxiv.json`，
   把增量判定证据追加到 journal，推进水位。
2. 第 2 轮（窗口 2025-06-08T00:00:00Z ≤ t < 2025-06-15T00:00:00Z）：
   读取 `materials/round2_crossref.json`、`materials/round2_arxiv.json`，
   其中刻意包含：
   - 1 条真正新增（arXiv 2506.04567v1）；
   - 1 条 arXiv 版本更新（2506.01234v1 → v2）；
   - 1 条预印本→正式版版本链（Crossref DOI 10.1038/s41586-025-00001-x，
     经 relation 字段链接到 arXiv 2506.01234）；
   - 1 条跨源标题差异重复（arXiv 2506.09988v1 与第 1 轮 Crossref 条目仅
     大小写/结尾标点不同）；
   - 1 条 DOI 规范化重复（10.1038/Nature12373，大小写差异）。
3. 回放第 1、2 轮，输出 replay_diff（期望 status=consistent）。
4. 对第 2 轮做幂等校验（期望零新事件、零二次投递、journal 逐字节不变）。
5. 组装 `output/result.json`，覆盖 `case.json` 的 `output_contract` 全部字段，
   并附 sources / uncertainty / change_records。

## 一键运行

在 bundle 根目录：

```bash
python3 scripts/run_minimal_example.py
```
