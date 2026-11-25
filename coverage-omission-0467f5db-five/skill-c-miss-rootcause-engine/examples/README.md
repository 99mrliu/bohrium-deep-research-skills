# 最小调用示例（合成示例，非正式测试案例）

`input/` 为**合成数据**：8 条参考题录（1 条无标识符）、2 条查询、1 份合成 Crossref 响应（含摘要）、1 份合成补检轮结果。

## 运行

```bash
python3 scripts/rootcause_engine.py \
  --input examples/input --work examples/run/work --output examples/run/output
```

## 预期产物（合成示例输出）

- 覆盖：分母 8、命中 5、漏检 3，覆盖率 0.625；
- `examples/run/work/miss_diagnosis.json`：R005 诊断出 `query_term_missing`（"halide" 不在任何查询式，附语料定位）、R006 诊断出 `time_window_cutoff`（2017 落在 2019–2024 之外，附查询出处）、R007 诊断出 `identifier_missing`；部分记录带多类别并存归因；
- `examples/run/work/supplement_queries.json`：由归因反向生成的定向补检式（新增鉴别词、扩展窗口、标识符修复）；
- `examples/run/work/omission_delta.json`：`measured=true`，miss_before=3、recovered=2、miss_after=1，残余 R007 保留原诊断；
- `examples/run/output/result.json`：含 case_id 与契约全部 5 个字段。

`examples/run/` 下产物为真实执行生成，仅作接口对照，不代表正式案例成绩。
