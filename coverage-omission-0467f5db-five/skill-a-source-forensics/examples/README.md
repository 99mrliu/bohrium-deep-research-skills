# 最小调用示例（合成示例，非正式测试案例）

本目录演示技能的完整调用流程。`input/` 下全部为**合成数据**：12 条题录（含 1 条撤稿、1 条重复、1 条标识符冲突、1 条无标识符）、3 条查询的命中结果、1 份合成 Crossref 响应（JSONL）。

## 运行

```bash
python3 scripts/forensics_pipeline.py \
  --input examples/input --work examples/run/work --output examples/run/output
```

## 预期产物（合成示例输出）

- `examples/run/output/result.json`：case_id=`synthetic-demo-forensics-001`，含 output_contract 全部 5 个字段；
- `examples/run/output/reference_set.json`：冻结参考集 v1.0.0，12 条解析 −1 合并重复 = 11 条记录，其中 1 条 `exclude_retracted`、1 条 `identifier_conflict`、1 条 `flag_keep_unverified`；
- `examples/run/output/coverage_report.md`：分母 10（11 −1 撤稿排除），命中 6，漏检 4，覆盖率 0.6；漏检分别带查询词缺失、时间窗截断、来源未覆盖核对、标识符异常等归因；
- `examples/run/work/authenticity_manifest.json`：4 份输入材料的 SHA-256 监管链。

`examples/run/` 下是真实执行本命令生成的产物，供接口对照；正式案例结果由平台运行产生，本目录不代表正式成绩。
