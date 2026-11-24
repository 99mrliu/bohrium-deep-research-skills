# 最小示例（合成示例，非正式案例结果）

本示例演示 archetype-interpreter 的完整接口与使用流程。输入为**合成数据**
（40 条弯曲 trace，含人工埋入的 2 条离群、1 条饱和、1 组重复曲线），
不对应任何真实实验，也不代表平台正式案例的答案。

## 运行

```bash
cd examples
python3 make_synthetic_input.py --outdir ./demo
python3 ../scripts/run_all.py --input ./demo/input --work ./demo/work --output ./demo/output
python3 ../scripts/result_contract.py check --case ./demo/input/case.json --out ./demo/output/result.json || true
```

## 预期（本仓库 captured 于 expected/）

- 识别原型 `bending_traces`（40 条两列 trace ≥30 阈值）；
- `peak_outlier_traces` 含 trace_013、trace_027；
- `saturated_traces(plateau>=5)` 含 trace_005；
- `duplicate_trace_groups` 含 [trace_030.txt, trace_031.txt]；
- result.json 中「异常点」「复核步骤」「依据与风险」「确认项」由脚本预填，
  「结果趋势」「可能原因」「后续实验建议」留待 Agent 撰写（status=partial，
  limitations 点名）——这演示诚实 partial 契约。

`expected/` 目录为一次真实本地运行的输出副本，供比对结构（数值为合成数据结果）。
