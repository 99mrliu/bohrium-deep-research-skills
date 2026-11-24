# 最小调用示例（合成示例）

**声明：本示例为合成示例。** 夹具文件、overrides 与输出均为演示数据，
不对应真实文献，也不是平台正式案例结果。

## 运行

```bash
cd examples
python3 make_fixture.py     # 生成合成夹具 fixture/input（13 个文件）
bash run_example.sh         # init(提案) -> 预写覆盖 -> finalize(落地+渲染)
```

## 观察点

1. init 的确定性提案（`fixture/work/proposal.json`）：每条带 `signals`（判定依据）
   与 `confidence`；损坏/无文本层/无权限文件直接提案 skip。
2. `overrides.synthetic.json` 只写 2 条覆盖（缩短过长命名；把数据集从
   00-admin 改判到 datasets/）+ 版本关系 + 检索回答——演示"模型只补提案的错"。
3. finalize 渲染四件套：`catalog.md`（人读目录）、`catalog.csv`（机读平表）、
   `tree_diff.md`（前后目录树对照）、`verify_report.md`（哈希复核）。
4. fid 交叉链接：catalog 条目 → operations.jsonl → result.json library_index。
5. 重跑 finalize 幂等（verified_skip）。

实际运行输出摘录见 `sample_output.md`。
