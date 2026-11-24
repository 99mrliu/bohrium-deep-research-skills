# bundle-c-theme-evolution-cartography

Playground challenge-073af7d3（研究前沿与趋势分析）Skill bundle。
重心：**主题演化语义层与代表作遴选**——演化结论必须来自可复算的词项队列
矩阵，术语漂移（换词）必须被识别为改名而非新主题，代表作必须用可审计的
多准则打分 + 每阶段配额遴选，拒绝"引用 top-N=代表作"。

## 内容

- `SKILL.md` — Skill 主体（中文）：定位、固定路径、7 步执行协议（契约建档 →
  语料归一 → 时间趋势 → 词项队列 → 阶段划分 → 代表作 → 研究空白 → 回链定稿）、
  输出契约、预算规划、异常处理表、不适用边界。
- `scripts/`（Python3 stdlib only、确定性、无网络）：
  - `build_corpus.py` — json/jsonl/csv/bib/ris/txt/md → canon.jsonl
  - `term_cohorts.py` — 词项抽取（unigram+bigram、min_df、同义词合并）
    → term_year_matrix / year_vectors / record_terms / top_terms
  - `phase_segment.py` — 相邻年余弦距离 + 1-2-1 平滑 + median+1×MAD 边界
    → phases.json + drift_report.json（术语漂移检测器）
  - `representative_select.py` — 0.5 引用百分位 + 0.3 词项中心度 + 0.2 方法
    首发奖励，每阶段 top-K，完整打分表；`--baseline top-citations` 复现
    反模式并在覆盖率 < 1.0 时 exit 1
- `references/` — 词项归一口径、代表作遴选口径（公式/权重/闸门/为何反模式失败）
- `examples/` — 30 条**合成**记录（2010–2024，埋三阶段 + 一对术语漂移 +
  引用陷阱）；`bash examples/run_example.sh` 跑 GOOD（exit 0）与 BAD
  （exit 1）双路径，产物在 `examples/example_output/`

## 快速验证

```bash
bash examples/run_example.sh
```

预期：检测到 2010-2015 / 2016-2020 / 2021-2024 三阶段（±1 年）；
drift_report 显示 pretrained language model → foundation model 改名；
每阶段 2 代表作；baseline 覆盖率 1/3 违规 exit 1。
