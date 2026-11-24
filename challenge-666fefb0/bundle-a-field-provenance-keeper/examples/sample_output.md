# 合成示例实际运行输出摘录

**本页为合成示例的真实运行记录（2026-11-24，macOS，Python 3 + pdftotext）。**
输入为 `make_fixture.py` 生成的演示数据，非正式案例结果。`fixture/` 由脚本生成，
不随 bundle 分发。

## 控制台输出

```
$ python3 make_fixture.py && bash run_example.sh
fixture written to .../examples/fixture/input (13 library files)
--- init ---
{"case_id": "case-synthetic-demo-a", "files": 13, "alias_groups": 2}
--- install synthetic decisions (replaces the model step) ---
--- lint ---
{"checked": 32, "passed": 31, "downgraded": 1}
--- finalize ---
{"status": "partial", "ops": 10, "skipped": 3, "verify_ok": true}
--- summary ---
status: partial
indexed: 10  skipped: 3  ops: 10
uncertainties: 2
```

## 关键产物摘录

整理后目录树（`fixture/out/library/`）：

```
00-admin/data-perovskite-bandgaps.csv
00-admin/meta.csv
00-admin/notes-版本说明.md
_archive_dups/Chen-2020-Advances in Quantum Dot Photovoltaics (duplicate).pdf
_archive_dups/Zhang-2023-Solid-State Battery Interface Engineering (duplicate).pdf
journal-articles/2022/Smith-2022-GNN Screening of Perovskite Catalysts.pdf
preprints/2021/Smith-2021-GNN Screening of Perovskite Catalysts (arXiv preprint).pdf
reviews/2020/Chen-2020-Advances in Quantum Dot Photovoltaics.pdf
supplementary/2022/Smith-2022-Supplementary Information for GNN Screening of Perovskite Catalysts.pdf
theses/2023/Zhang-2023-Solid-State Battery Interface Engineering.pdf
```

`conflicts.json`（故意编造的 DOI 被 lint 拦下）：

```json
[{"fid": "F004", "field": "doi", "issue": "lint_downgrade",
  "rejected_value": "10.48550/arxiv.2201.00001",
  "note": "value could not be verified against extracted text/filename/sidecars; downgraded to unknown"}]
```

`operations.jsonl` 首条（双侧哈希）：

```json
{"op_id": "op-F001", "fid": "F001", "src": "01-quantum-dots-review.pdf",
 "src_sha256": "24362df0d853…", "dst_rel": "reviews/2020/Chen-2020-Advances in Quantum Dot Photovoltaics.pdf",
 "status": "copied", "dst_sha256": "24362df0d853…", "dst_present": true}
```

`result.json` 要点：`status=partial`（corrupt-scan.pdf 损坏、old-scanned-article.pdf
无文本层、no-permission.pdf 无权限，逐一列入 `skipped` 并附恢复建议）；
`version_relations` 登记预印本/正式版/SI 三件套且 canonical=F002；
`answers` 三条均带 evidence；`sources` 含全部 13 个输入文件的 SHA-256。

重跑 `finalize` 输出不变（操作转为 `verified_skip`，verify_ok 保持 true）。
