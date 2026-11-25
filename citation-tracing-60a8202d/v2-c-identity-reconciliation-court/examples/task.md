# 任务说明（合成示例 / SYNTHETIC，非正式案例结果）

> 本示例全部文献与 DOI（形如 `10.0000/synth.*`）均为虚构，仅用于演示
> `identity-reconciliation-court` 的调用方式与产物形态。

1. 对 `corpus/` 下的三个跨库风格 JSON 文件（Crossref / EuropePMC / OpenAlex 风格）
   做递归解析与身份合并：
   - 同一论文的 arXiv 预印本版与期刊版应被识别为版本谱系并合并，保留合并证据；
   - 一对「同名不同文」（标题高度相似但作者/年份/DOI 全不重叠）不得被误并；
   - 一对「同文不同名」（DOI 相同但标题差异大）应被合并并保留双标题证据；
   - 一条缺 DOI 缺年份的残缺记录应保持为独立实体并在不确定性中交代。
2. 以 `case.json` 中的种子（`10.0000/synth.a1`）为起点做 1–2 层引用扩展。
3. 交付 `result.json`（逐字段镜像 `output_contract` 全字段）与 `merge_report.md`。
