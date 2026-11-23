# examples/ — 最小合成示例（SYNTH-EXAMPLE-001）

**本目录全部为合成（虚构）示例**：三篇虚构光催化论文、虚构工单与虚构合成请求，仅用于演示
comparability-court 的裁定与守门机制，**不含任何官方正式案例答案**。

## 语料设定（corpus/）

| 文档 | 材料 | 污染物 | 指标 | budget |
|---|---|---|---|---|
| DOC-01 | g-C3N4 | RhB | η = 96%（90 min） | 0.5 g/L |
| DOC-02 | N-TiO2 | 亚甲基蓝（MB） | η = 88%（60 min） | 1.0 g/L |
| DOC-03 | g-C3N4-Ag | RhB | k = 0.031 min⁻¹ | 未报告 |

## 运行

```bash
bash examples/run_example.sh        # 在 bundle 根目录执行；或先 cd examples 再 bash run_example.sh
```

全流程：`build_profiles.py`（quote 逐字落地机检）→ `decide.py`（裁定）→
`pool.py` ×2（permit 例与 block 例）→ `render_court.py`（矩阵/报告模板/result.json + lint）。
产物写入 `examples/output/`。

## 预期裁定结果

- **DOC-01 × DOC-02**：pollutant = **blocked**（RhB vs MB，不同染料禁止合并）；
  material/budget = subset_only；task/metric/units = comparable；总裁定 = **blocked**。
- **DOC-01 × DOC-03**：metric = **subset_only**（η vs k）；units = subset_only（% vs min⁻¹ 不可换算）；
  material = subset_only（g-C3N4 vs g-C3N4-Ag）；budget = **undecidable**（DOC-03 未报告投加量）；
  task/pollutant = comparable；总裁定 = **undecidable**（最严者胜出）。
- **DOC-02 × DOC-03**：pollutant blocked + budget undecidable；总裁定 = **blocked**。

## 预期守门结果

- `sample_synthesis_request_permit.json`（REQ-PERMIT-01，DOC-01 × DOC-03 定性对照，
  仅要求 task/pollutant/material 三维度）→ **PERMIT**，附 material 维度 subset_only 的口径警告。
- `sample_synthesis_request_block.json`（REQ-BLOCK-01，"对 DOC-01、DOC-02 的 η 求均值并排名"，
  quantitative、缺省六维度）→ **BLOCK**，阻断维度：pollutant（blocked）、
  material 与 budget（subset_only 不满足 quantitative 白名单），并给出双方取值与 quote 定位。

## 注意

- pool.py 退出码恒为 0，permit/block 以输出 JSON 的 `status` 字段为准，便于脚本串联。
- `verdict-report.md` 是模板：评测时 agent 可扩写叙述，但每个比较句必须保留/引用
  `[DEC-…]` 或 `[PERMIT-…]`；改完用 `render_court.py --lint <报告路径>` 复检。
