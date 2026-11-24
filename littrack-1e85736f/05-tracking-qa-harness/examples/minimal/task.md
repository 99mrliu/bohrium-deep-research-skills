# 任务说明（合成示例 / synthetic demo）

> ⚠️ 本目录是 tracking-qa-harness 的**合成示例**：全部题录、DOI、快照与投递记录均为虚构，
> 仅用于演示 QA 门禁的端到端运行，不代表任何真实文献检索结果。

## 背景

某文献追踪流程已对窗口 `2026-10-01 ~ 2026-10-31`（UTC 闭区间）完成一轮增量追踪，
产出了候选结果 `candidate_result.json`。在交付前，必须用本 Skill 的 QA harness
对该产出执行质量门禁。

## 材料

- `case.json`：案例定义（case_id、output_contract、窗口、材料清单）
- `materials/crossref_response.json`：固化的 Crossref 风格题录响应（合成，5 条）
- `materials/europepmc_response.json`：固化的 Europe PMC 风格题录响应（合成，2 条）
- `materials/previous_snapshot.json`：上一窗口结束时的增量导入状态快照（合成）
- `materials/delivery_log.json`：期刊关注列表与提醒投递记录（合成）
- `candidate_result.json`：待检候选产出（**故意埋有 3 处错误**，见 README.md）
- `fixed_result.json`：修复后的产出（应当全部门禁通过）

## 要求

1. 对 `candidate_result.json` 运行全部门禁（contract_validate → evidence_spotcheck
   → freshness_check → metrics → qa_report），检出全部错误并在 qa_report 中列出阻断项；
2. 修复产出得到 `fixed_result.json`，重跑门禁直至 overall_status = pass；
3. 所有断言必须可经 locator 回溯到源文件，禁止编造任何 DOI 或元数据；
4. 全程离线，脚本不得发起任何网络请求。

## 一键运行

在 bundle 根目录（本文件的上两级）执行：

```bash
python3 scripts/run_minimal_example.py
```

产物写入 `examples/minimal/output/`。
