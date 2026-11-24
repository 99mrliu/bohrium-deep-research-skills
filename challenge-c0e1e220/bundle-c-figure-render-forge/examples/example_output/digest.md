# digest.md — 待确认裁决（≤5 项，确认或 decide 覆盖后 finalize）

1. **分组变量**: `group`（3 个水平，自动评分选出）。覆盖：`python3 pipeline_c.py decide --work <work> --set group_by=<列名>`
2. **结局变量**（1 个）: rt。覆盖：`--set outcomes=a,b,c`
3. **检验路线**:
   - a1: rt by group → Kruskal-Wallis（NON_NORMAL_OR_SMALL_N->KRUSKAL_WALLIS），p=0.0008
4. **假设警告**: rt/treatA 非正态（K2 p=0.00211）；rt/treatB 非正态（K2 p=0.01771）
5. **alpha** = 0.05；单位映射见 report.md。覆盖：`--set alpha=0.01`

确认无误后直接 finalize；任何覆盖后必须重新 finalize + figure_forge + figure_audit。
其他 decide 键：`focus=28,90`、`rename.<列>=<新名>`、`duplicate_policy=dedupe_exact_keep_first`、`figure_waiver.<分析id>=<理由>`、`max_figures=N`。
