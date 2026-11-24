# examples/minimal — 合成示例（synthetic）

> **合成示例声明**：本目录下全部数据（`case.json`、`task.md`、`materials/`
> 及 `output/` 产物）均为演示而**编造**，不代表真实检索结果或真实文献。
> 个别 DOI 借用了真实存在文献的格式（如 `10.1038/nature12373`），仅为格式
> 演示用途；每个数据文件内含 `"synthetic": true` 标记。

## 内容

- `case.json` — 模拟案例输入：`case_id`、`task`、`window`（2026-10-22 ~
  2026-11-21，以终点为"现在"）、`materials_dir`、`output_contract`。
- `task.md` — 模拟任务书。
- `materials/` — 模拟组织方本地固化的上游快照：
  - `crossref_response.json`：4 条题录，埋入 1 条未来日期
    （#/records/1，published 2027-01-15）、1 条非法 DOI
    （#/records/2，"10.123/abc def"）、1 条撤稿标记
    （#/records/3，retracted=true + 标题前缀 + relation）；
  - `europepmc_response.json`：3 条题录，埋入 1 条源内重复
    （#/records/1 与 #/records/0 同 DOI）、1 条同时具有非法 PMID、
    空标题、缺失日期（#/records/2）；
  - `arxiv_response.json`：2 条题录，埋入 1 条非法 arXiv 号
    （#/records/1，"2026.abc"）；
  - `previous_snapshot.json`：模拟"本地增量导入状态"，其中 epmc-000
    已不在当前源快照中（source_record_disappeared）；
  - `crossref_snapshot_v1.json` / `crossref_snapshot_v2.json`：同一归档源
    的两个历史快照，演示结构漂移检测（authors→author_list、
    published→publication_date、新增 license）。
- `output/` — 一键脚本的真实运行产物（非手写）。

## 运行

在 bundle 根目录（本目录的上两级）执行：

```bash
python3 scripts/run_minimal_example.py
```

预期：10 类异常各检出 1 个，gating = `proceed_with_quarantine`，
quarantine 6 条，`result.json` 通过 output_contract 自检（全部 PASS）。
异常与 locator 的对应表见 `references/anomaly-taxonomy.md` 末节。
