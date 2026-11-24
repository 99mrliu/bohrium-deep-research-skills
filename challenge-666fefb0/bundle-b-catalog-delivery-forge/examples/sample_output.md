# 合成示例实际运行输出摘录

**本页为合成示例的真实运行记录（2026-11-24，macOS，Python 3 + pdftotext）。**
输入为 `make_fixture.py` 生成的演示数据，非正式案例结果。`fixture/` 由脚本生成，
不随 bundle 分发。

## 控制台输出

```
$ python3 make_fixture.py && bash run_example.sh
fixture written to .../examples/fixture/input (13 library files)
--- init (inventory + deterministic proposal) ---
{"case_id": "case-synthetic-demo-b", "files": 13, "proposal_low_confidence": []}
--- install synthetic overrides (replaces the model step) ---
--- finalize (apply + render + result) ---
{"status": "partial", "ops": 10, "skipped": 3, "verify_ok": true,
 "deliverables": ["catalog.md", "catalog.csv", "tree_diff.md", "verify_report.md"]}
--- deliverables ---
catalog.csv  catalog.md  library  operations.jsonl  result.json
tree_diff.md  verify_report.json  verify_report.md
```

重跑 `finalize`：10 条操作全部转 `verified_skip`，输出不变（幂等）。

## catalog.md 摘录（人读总目录）

```
### journal-articles/2022

- **Smith-2022-GNN Screening of Perovskite Catalysts** (`F002`)
  - 原始路径: `Nature-Energy-2022-GNN-perovskite.pdf` → 归档: `library/journal-articles/2022/Smith-2022-GNN Screening of Perovskite Catalysts.pdf`
  - SHA-256: `d77d3342a4e9…` | 年份: 2022 | DOI: 10.1038/s41560-022-0001-x — 版本关系: preprint_of / published_version / supplementary_of (canonical: F002)
```

## catalog.csv 摘录（机读平表，14 列）

```
F001,archived,journal-articles,journal-articles,2020,Chen-2020-Advances in Quantum Dot Photovoltaics,01-quantum-dots-review.pdf,journal-articles/2020/Chen-2020-Advances in Quantum Dot Photovoltaics.pdf,24362df0…,758,2020,10.1021/acs.chemrev.00002,keep,
```

## verify_report.md 摘录（哈希复核）

```
结论: 全部一致 ✓
| 操作 | 源 SHA-256 | 目标 SHA-256 | 结论 |
| op-F001 | `24362df0d853…` | `24362df0d853…` | 一致 ✓ |
…（10 条全部一致）
```

## 提案-覆盖留痕

init 提案将 F002 判定为 `journal-articles`（信号："正文自称 published version 且含
DOI"、"含 DOI"，confidence=high）；模型仅覆盖 2 条（缩短 F003 命名；把 F006 数据集
从 00-admin 改判到 datasets/），覆盖原因写入 change_log 的 `override` 条目。
`result.json`：status=partial（3 个 skipped：损坏/无文本层/无权限），含
output_contract 全部字段与 `deliverables` 清单。
