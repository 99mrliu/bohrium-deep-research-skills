# facet-gap-atlas

科研选题评估技能的**结构化比较数据建模**方向：已有工作比较 = 类型化记录表，
研究空白 = 表上的确定性查询。

- 核心脚本：`scripts/atlas.py`（仅标准库）——`validate` 机检记录完整性
  （必填字段、受控枚举、年份区间、重复键）；`gap` 计算切面覆盖矩阵与空白格、
  指标覆盖缺口、不可比对记录对（附原因）。
- 运行契约：`/input` → `/app/work`（records.jsonl、vocabulary.md、atlas 报告）
  → `/app/output`（result.json 含 case_id 与全部 output_contract 字段，
  诚实 partial；图谱附件随附）。
- 模式与方法学：`references/schema.md`、`references/gap_method.md`。
- 最小示例（合成）：`examples/`，`bash examples/run_example.sh` 一键复跑。

维护：作者随 Playground challenge-041f89c5 提交；Python ≥3.8，无第三方依赖。
