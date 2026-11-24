# 任务说明（合成教学案例 synthetic-coverage-001）

> 本案例为 SYNTHETIC teaching data：所有文献、DOI、PMID 均为虚构，仅用于演示
> 覆盖审计逻辑。

围绕研究问题完成 crossref、europepmc、publisher 三个数据库的联合检索，
并交付候选集、覆盖说明与遗漏说明。

## 检索编排记录

执行方记录如下：检索式 "graph neural network catalyst screening" 被逐字（verbatim）同时发送至 crossref 与 europepmc 两个数据库，未按各自语法改写。

publisher 库的导出文件由合作方直接提供，未附任何检索式或请求参数记录。

## 交付要求

输出 result.json，包含 case_id 与 output_contract 声明的全部字段；
对无结果、冲突、缺失元数据与覆盖缺口做出明确说明。
