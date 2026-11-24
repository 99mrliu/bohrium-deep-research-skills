# 任务说明(合成示意案例,非正式测评)

对 `mock_paper.txt` 执行以下审查面:

1. **引用规范** — 参考文献元数据是否完整、正文引证与文献表是否一一对应;
2. **伦理审查** — 人体问卷研究是否有伦理批准声明与知情同意;
3. **隐私合规** — 正文/附录是否含受试者可直接识别信息(PII),脱敏是否充分。

输出 `result.json`,含 case_id、status、findings(逐条:位置+逐字摘录+严重度+修改建议)、
not_reviewed、summary、sources、uncertainty、change_log。
