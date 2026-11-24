# 最小合成示例（synthetic minimal example）

> ⚠️ **合成示例声明**：本目录下全部数据（case.json、materials/*、candidate_result.json、
> fixed_result.json、output/*）均为作者新造的**虚构数据**，仅用于演示 tracking-qa-harness
> 的 QA 门禁端到端运行。DOI 仅借用真实存在的前缀格式（如 10.1038、10.1126），
> 不指向、不代表任何真实文献。

## 目录内容

| 文件 | 说明 |
|---|---|
| `case.json` | 案例定义：case_id、output_contract、窗口 2026-10、材料清单（标注 synthetic） |
| `task.md` | 任务说明 |
| `materials/crossref_response.json` | 合成 Crossref 风格题录响应（5 条） |
| `materials/europepmc_response.json` | 合成 Europe PMC 风格题录响应（2 条） |
| `materials/previous_snapshot.json` | 合成增量导入状态快照（3 个已知 DOI） |
| `materials/delivery_log.json` | 合成期刊关注列表与投递记录 |
| `candidate_result.json` | 待检候选产出，**故意埋 3 处错误** |
| `fixed_result.json` | 修复后产出（应全部门禁通过） |
| `output/` | `run_minimal_example.py` 的真实运行产物 |

## 埋错的 3 处错误（QA 必须全部检出）

1. **locator 不可解析**：`new_items[2]`（10.7554/elife.90001）的 locator 指向
   `materials/europepmc_response.json#/resultList/result/7`，但该数组只有 2 条记录
   （下标越界）→ 由 `evidence_spotcheck.py` 检出；
2. **日期落在窗口外**：`new_items[3]`（10.1016/j.cell.2026.08.015）发表日期
   2026-08-20 落在窗口 2026-10-01~2026-10-31 之外，且无 backfill 标记
   → 由 `freshness_check.py` 检出；
3. **旧文重报**：`new_items[4]`（10.1038/s41586-026-00001-x）已在
   `previous_snapshot.json` 的 known_dois 中 → 由 `freshness_check.py` 检出。

此外，候选产出遗漏了 2 条窗口内应新增记录（10.1021/jacs.6c09988、
10.1101/2026.10.09.555001），`metrics.py` 的窗口覆盖率会如实反映（0.6 而非 1.0）。

## 一键运行

在 **bundle 根目录**（本文件上两级）执行：

```bash
python3 scripts/run_minimal_example.py
```

脚本依次对 candidate / fixed 两份产出运行全部门禁，校验"3 处埋错全部检出、
修复版全部通过"的期望，产物写入 `output/`：

- `output/candidate/`：contract_validate / evidence_spotcheck / freshness_check /
  metrics 子报告 + `qa_report.json` / `qa_report.md`（overall=fail，3 个阻断项）
- `output/fixed/`：同上（overall=pass）
- `output/run_summary.json`：端到端自检结论
