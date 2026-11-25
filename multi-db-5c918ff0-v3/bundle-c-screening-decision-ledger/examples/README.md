# examples/ — 合成示例声明

**本目录全部为合成教学数据。**

- `synthetic-input/` 中的研究问题（虚构肽 "NX-3" 治疗慢性失眠）、全部论文
  标题/摘要/作者/期刊、DOI（`10.99977/...`）与 PMID（`391xxxxx`）均为虚构，
  不对应任何真实文献实体，可安全公开发布。
- `crossref_response.json` / `europepmc_response.json` 仅模拟两类 API 响应的
  **信封结构**（`message.items` / `resultList.result`），内容虚构；
  `publisher_records.json` 模拟出版方 JSON 数组；`reference_graph.json` 与
  `import_state.json` 为组织方留存材料的最小示例。
- `criteria.json` / `judgments.json` / `borderline_decisions.json` 是**手工
  编写**的模型步骤产物，用于演示脚本期望的输入格式与逐字引用纪律（每条
  evidence_quote 都是对应记录标题/摘要的真实子串）。
- `synthetic-output/` 是脚本**实际运行**的产物（非手工编写），确切命令、
  退出码与负数测试见 `synthetic-output/run-record.md`。

数据工程设计（供核对流量计数）：14 条原始记录（crossref 6 / europepmc 5 /
publisher 3），2 对跨源重复（一对 DOI 精确、一对标题+年份+第一作者），
去重后 12 条规范记录；其中 5 条明确纳入、4 条按四个不同标准明确排除
（人群 I2、年份 E1、对照 I3、文献类型 E2）、3 条边界经裁定后 2 排除 1 纳入
——最终 included=6、excluded=6、borderline_pending=0。
