# 最小调用示例（合成示例）

**声明：本示例为合成示例。** `make_fixture.py` 生成的 13 个文件、case.json、
`decisions.synthetic.json` 中的全部元数据与回答均为演示数据，不对应真实文献，
也不是平台正式案例的结果。

## 运行

```bash
cd examples
python3 make_fixture.py     # 生成合成夹具 fixture/input（library + case.json + task.md）
bash run_example.sh         # init -> 预写决策 -> lint -> finalize
```

## 夹具设计（覆盖六类要素）

| 文件 | 演示点 |
|---|---|
| arxiv_2201.00001.pdf / Nature-Energy-2022-GNN-perovskite.pdf / SI-GNN-perovskite.pdf | 预印本/正式版/补充材料三件套与 canonical 裁决 |
| 01-quantum-dots-review.pdf ↔ quantum dots review final.pdf；thesis-final-v3.pdf ↔ thesis-copy-again.pdf | 两组字节级重复下载（同 SHA-256） |
| corrupt-scan.pdf | 损坏 PDF（extract_error） |
| old-scanned-article.pdf | 无文本层扫描件（no_text_layer） |
| no-permission.pdf | 无权限文件（chmod 0，permission_denied） |
| meta.csv / notes-版本说明.md / data-perovskite-bandgaps.csv | 旁挂元数据表、管理员版本说明、数据集 |

## 预期观察点

- `decisions.synthetic.json` 中 F004 的 `doi` 是**故意编造**的值；
  `lint` 步骤应将其降级为 `unknown` 并写入 `conflicts.json`（演示"锚不住就降级"）。
- `fixture/out/result.json`：status=partial（3 个文件因损坏/无文本层/无权限跳过），
  含 output_contract 全部字段。
- `fixture/out/operations.jsonl`：每条操作含双侧 SHA-256；重跑 `finalize` 幂等。
- `fixture/out/metadata_ledger.jsonl`：字段级台账，含降级痕迹。

实际运行输出摘录见 `sample_output.md`。
