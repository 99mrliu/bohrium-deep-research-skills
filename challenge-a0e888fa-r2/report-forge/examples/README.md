# examples：合成示例（全部为人工编造的合成数据）

**声明：本目录下所有数据均为人工编造的合成数据，仅用于演示交付面渲染管线，
不对应任何真实实验、真实地块或真实结论。**

## 场景设定

模拟一份"土壤重金属汇总表"清洗完成后的产物：

- 源表被注入的故障（虚构）：一个以 g/kg 记录的单位错误、一个非法数值 token
  （`13.6a`）、一整行重复记录、一个落在 IQR 异常阈值的复核值。
- `cleaned.csv`：清洗后汇总表，6 行 × 8 字段，2 个缺失单元格
  （`S03.cd_mg_kg` 源表即缺失；`S05.as_mg_kg` 为非法值剔除后留空，不插补）。
- `ledger.csv`：4 条变更记录（单位换算 1、非法值剔除 1、重复行剔除 1、
  异常标记保留 1）。
- `summary.json`：与两件产物重算值一致的统计摘要 + 直方图字段配置。
- `case.json` / `result.json`：模拟赛题合同与最终交付结果
  （含 `artifact_hashes` 登记）。

## 复现 expected/（三条命令）

```bash
cd examples
# 1) 出图（figures/*.svg + figures_index.json）
python3 ../scripts/figures_svg.py \
  --cleaned cleaned.csv --ledger ledger.csv --summary summary.json \
  --out-dir expected/figures --index expected/figures_index.json
# 2) 渲染报告（quality_report.md / quality_report.html，内联 SVG）
python3 ../scripts/fill_report.py \
  --cleaned cleaned.csv --ledger ledger.csv --summary summary.json \
  --figures-index expected/figures_index.json \
  --out-md expected/quality_report.md --out-html expected/quality_report.html
# 3) 一致性门（consistency_check.json，退出码 0 表示 PASS）
python3 ../scripts/check_consistency.py \
  --case case.json --result result.json \
  --cleaned cleaned.csv --ledger ledger.csv --summary summary.json \
  --report-md expected/quality_report.md --report-html expected/quality_report.html \
  --figures-index expected/figures_index.json --out expected/consistency_check.json
echo "exit=$?"
```

注意：第 1、2 步重跑会逐字节复现 expected/ 中的报告与图表；第 3 步通过的
前提是 `result.json` 的 `artifact_hashes` 与当前文件一致——若你改动了任何
产物，需先按 SKILL.md 步骤 3b 的方式重新登记哈希，再过门。

## expected/ 内容

- `quality_report.md` / `quality_report.html`：全部数字由脚本从产物重算注入；
  HTML 内联 5 张 SVG 图，数字与 summary.json 一致。
- `figures/`：`fig_hist_pb_mg_kg.svg`、`fig_hist_cd_mg_kg.svg`（分布→直方图）、
  `fig_missing_by_field.svg`（缺失分类→分组条形图）、`fig_field_issues.svg`
  （对比→条形图）、`fig_action_composition.svg`（构成→堆叠条形图）。
- `figures_index.json`：每图的类型、选择依据（rationale）与图注。
- `consistency_check.json`：12 项校验全部 PASS。
