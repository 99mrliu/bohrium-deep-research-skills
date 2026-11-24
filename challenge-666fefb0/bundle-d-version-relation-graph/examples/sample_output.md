# 合成示例实际运行输出摘录

**本页为合成示例的真实运行记录（2026-11-24，macOS，Python 3 + pdftotext）。**
输入为 `make_fixture.py` 生成的演示数据，非正式案例结果。`fixture/` 由脚本生成，
不随 bundle 分发。

## 控制台输出

```
--- init ---
{"case_id": "case-synthetic-demo-d", "files": 13}
--- graph (multi-signal typed edges + canonical arbitration) ---
{"nodes": 13, "edges": 5, "clusters": 9, "pending_candidate_edges": 0}
--- finalize (archive + render graph + result) ---
{"status": "partial", "ops": 10, "skipped": 3, "verify_ok": true, "clusters": 9}
```

## graph.md 摘录（人读邻接表 + 边证据）

```
### C1 — canonical: F002
- `F002` Nature-Energy-2022-GNN-perovskite.pdf
- `F003` SI-GNN-perovskite.pdf
- `F004` arxiv_2201.00001.pdf
  - **supplement_of** F002 ↔ F003 roles={'F002': 'main', 'F003': 'supplement'}
    - 证据: titles: 'GNN Screening of Perovskite Catalysts' ≈ 'Supplementary Information for …'
  - **version_of** F002 ↔ F004 roles={'F002': 'published', 'F004': 'preprint'}
    - 证据: notes-版本说明.md 行3: - arxiv_2201.00001.pdf 是预印本；Nature-Energy-… 是同一工作的正式版…
### C8 — canonical: F001
- `F001` 01-quantum-dots-review.pdf
- `F011` quantum dots review final.pdf
  - **duplicate_of** F001 ↔ F011
    - 证据: SHA-256 identical: 24362df0d853256b…
```

## arbitration_log.json 摘录

```
C1 -> F002 | 管理员说明指定 (F002)，覆盖打分
C8 -> F001 | 纯 duplicate 簇：字节级一致，保留最小 fid 为 canonical
```

## result.json 要点

`version_relations` 由图谱簇直接导出（簇成员、边类型集合、canonical、证据）；
`status=partial`（3 个内容不可用文件进 skipped 并标注"仅以文件名/哈希入图"）；
含 output_contract 全部字段与 `graph_artifacts` 清单。
