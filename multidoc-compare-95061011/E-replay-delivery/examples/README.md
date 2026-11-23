# examples/ — 最小合成示例（非官方正式案例）

**声明：本目录全部数据为虚构合成示例**（3 篇虚构光催化论文），仅用于演示
"契约 → 记录 → 确定性渲染 → lint → 复跑证明"的完整流水线，不含任何官方正式案例答案。

## 内容

| 路径 | 说明 |
|---|---|
| `corpus/DOC-01.jsonl` | 虚构论文：g-C3N4 降解罗丹明B，96% / 90 min，k=0.035 min⁻¹，投加量 50 mg |
| `corpus/DOC-02.jsonl` | 虚构论文：N-TiO2 降解**亚甲基蓝**（material/pollutant 维度不可比），88% / 120 min，未报告 k |
| `corpus/DOC-03.jsonl` | 虚构论文：g-C3N4-Ag 降解罗丹明B，**只报 k=0.031 min⁻¹**（metric 维度不可比），效率/时间/投加量未报告（budget 未报告） |
| `case.json` | 合成 case：case_id `SYNTH-EXAMPLE-001`，output_contract 含 5 个字段 |
| `comparison-workorder.json` | 合成 v2 工单：判定基准、共同字段、规则 |
| `sample_records/cells.jsonl` | 18 条单元格记录（含 not_comparable 与 not_reported 的如实呈现） |
| `sample_records/decisions.jsonl` | 3 条合成判定（blocked / partial / partial） |
| `run_example.sh` | 一键端到端脚本 |

## 运行

```bash
cd <bundle 根目录>
bash examples/run_example.sh
```

## 预期输出

1. `init_contract` 生成 `examples/work/result.schema.json`（5 个契约字段原样照搬）与
   `examples/output/result.json` 骨架（status=partial）。
2. `render_all` 渲染 `comparison-matrix.md`（主矩阵 + 六维度可比性矩阵 C/N/NR +
   合成判定）、`integration-report.md`（句级 cell_id 引用）、`result.json`；
   自校验（markdown 数字回解析对账）通过。
3. `contract_lint` 通过。result.json 的 `status` 为 **partial**（因为 DOC-02 的
   material/pollutant 不可比、DOC-03 的 metric 不可比与 budget 未报告），
   `uncertainty` 逐条列出缺失边界。
4. 字节确定性：强制重渲染后三个产物与快照 `diff` 为空（脚本输出 `DETERMINISTIC`）。
5. `replay.py` 输出 `replay-report.json`，三个产物全部 `bytes_equal: true`、
   `all_reproducible: true`。

矩阵中应看到：DOC-02 行/格标注 N（不可比）且 k 为 `— ⟦NR⟧`；DOC-03 的
degradation_efficiency_pct / reaction_time_min / catalyst_dosage_mg 为 `— ⟦NR⟧`，
k 格的 metric 列为 N。
