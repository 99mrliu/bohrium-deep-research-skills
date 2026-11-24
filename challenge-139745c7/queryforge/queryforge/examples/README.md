# 合成最小示例（queryforge）

**本目录是合成示例，用于说明接口与流程，不是正式案例结果。**

`library/` 内含 4 个合成文件：

- `开题报告_v1_2023-03-01.md`：2023 年初稿（v1），含缓冲液配方（Tris 体系）。
- `开题报告_终稿_2023-06-15.md`：2023 年终稿，缓冲液配方改为 HEPES 体系。
- `HPLC数据_B2023-014_2023-07.csv`：批次 B2023-014 的保留时间数据。
- `旧工艺记录_2021.md`：2021 年旧工艺记录（用于演示年份过滤把它排除）。

`case.json` 三个提问，分别演示：版本硬过滤（终稿）、批次硬过滤
（B2023-014）、以及一个候选必被清零的提问（2025 年终稿 → 诚实 no_match
并给出淘汰轨迹）。

## 运行

```bash
cd examples
python3 run_example.py
```

在本目录生成 `work/queries.json`、`work/query_results.json`、
`output/result.json`。

## 预期结果（合成示例的期望行为）

- q1 命中 `开题报告_终稿_2023-06-15.md`，filter_trace 中 version=final
  的 dropped ≥ 1（v1 与旧记录被淘汰）。
- q2 命中 `HPLC数据_B2023-014_2023-07.csv`。
- q3 状态 `no_match`，note 指出是 year 条件清零了候选，且 filter_trace
  完整；result.json 含 case_id 与 output_contract 全部字段。
