# 合成示例声明

本目录（`synthetic-input/` 与 `synthetic-output/`）为**完全虚构**的教学
示例，仅用于演示 capture–recapture 召回估计管线：

- 案例 `synthetic-recall-cc-001` 的研究问题、全部文献标题、作者、刊名
  均为虚构；DOI 前缀 `10.99977` 不对应任何真实注册机构；PMID 为虚构
  序号；不指向任何真实论文。
- `synthetic-input/materials/` 下的 crossref / europepmc / publisher 文件
  是手工构造的**离线响应样式**数据，不是真实 API 抓取结果。
- `synthetic-input/materials/truth.json` 是合成示例的参考答案：
  **真实案例不存在真值文件**。该文件只有在命令行显式传入 `--truth`
  时才被读取，用于演示「估计 vs 真值」的误差报告（本例：Chao1 N̂=16.6
  vs 真值 20，误差 −3.4，真值落在 95% CI [15.2171, 26.7916] 内——
  直观展示 Chao1 作为下界估计的典型低估行为）；管线默认不读取它。
- `synthetic-output/` 为对输入**真实运行脚本**得到的产物
  （见其中的 `run-record.md`，含命令、退出码与复算验证），非手工编写。

若复跑：删除 `synthetic-output/` 后按 `run-record.md` 中的命令重跑即可，
产物字节一致（确定性）。
