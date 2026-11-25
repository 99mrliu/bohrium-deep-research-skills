# 任务说明（SYNTHETIC 合成示例）

> 本文件与 `case.json`、`materials/` 全部为**手工构造的合成数据**，仅用于离线演示与测试
> `query-coverage-engineering` Skill；所有文献记录、DOI、PMID、arXiv ID 均为虚构。

## 研究问题

Which recent studies apply **graph neural networks** to **molecular property prediction**
in **drug discovery** settings?

## 追踪窗口

2024-01-01 至 2026-06-30（闭区间）。

## 要求

1. 从 `case.json` 的结构化 `concepts`（object / method / scenario 三个概念块）生成
   Crossref / Europe PMC / arXiv 三个源方言的可审计布尔检索式（块内 OR、块间 AND）。
2. 对检索式做静态 lint（未加引号的短语、裸 OR、过宽单词、通配符兼容性等），逐条给出修改建议。
3. 用 `materials/reference_graph.json` 中保留的 4 颗种子文献做已知项召回验证：
   - 逐源（crossref / europepmc / arxiv）判断每颗种子是 `hit` / `miss` /
     `absent_from_snapshot` / `outside_window`；
   - 对 `miss` 的种子给出诊断（哪个概念块挡掉了它、缺哪个同义词），并给出最小化查询修订建议；
   - 应用修订后重跑覆盖验证，确认漏检种子被救回。
4. 汇总写出 `output/result.json`，包含 `case.json` 的 `output_contract` 列出的全部字段，
   事实性字段值带 locator（文件路径 + JSON 指针），并给出遗漏说明。

## 埋点说明（评测自检用）

- `seed-3`（Chemprop 论文）的标题/摘要只出现 "directed message passing"，
  初始 `method` 概念块（graph neural network / GNN / message passing neural network）
  缺少同义词 "message passing"，因此初始检索式在 crossref 与 arxiv 快照中都会漏检 seed-3；
  诊断应指出漏配块为 `method`、top-1 修订建议为加入 "message passing"；修订后应转为 hit。
- `seed-3` 在 europepmc 快照中不存在（`absent_from_snapshot`），
  `seed-4` 仅存在于 europepmc 快照，用于演示"源未收录/快照未覆盖"与"检索式漏检"的区别。
- `object` 块中故意放了过宽单词 `property`，lint 规则 QL003 应给出 warn。
