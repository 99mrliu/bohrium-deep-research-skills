# 合成示例（synthetic，非正式案例结果）

本目录是一个**完全合成**的可运行示例：所有"论文"、DOI、期刊、作者均为虚构，
仅用于演示 a-source-verifier 流水线。其中故意埋了一个年份不一致：
`papers/beta_paper.txt` 正文自称 2022 年，而 `snapshots/europepmc_beta.json`
快照声称 pubYear=2021——crosscheck 应当把它标成 `mismatch`（仅 year 字段）。

## 输入布局

```
examples/input/
├── case.json                        # 含 output_contract 的合成案例
├── papers/
│   ├── alpha_paper.txt              # Synthetic Demo Paper Alpha（应与 Crossref 快照完全吻合）
│   └── beta_paper.txt               # Synthetic Demo Paper Beta（故意制造 year mismatch）
└── snapshots/
    ├── crossref_alpha.json          # Crossref 风味快照（单条 work）
    └── europepmc_beta.json          # EuropePMC 风味快照（resultList）
```

## 实际运行的命令

```bash
B=/path/to/a-source-verifier
W=$(mktemp -d); O=$(mktemp -d)

python3 "$B/scripts/fingerprint.py" --input-dir "$B/examples/input" \
    --workdir "$W" --output-dir "$O" --case "$B/examples/input/case.json"
python3 "$B/scripts/crosscheck.py" --workdir "$W"
python3 "$B/scripts/build_result.py" --workdir "$W" --output-dir "$O" \
    --case "$B/examples/input/case.json"
```

实际运行日志（三步退出码均为 0）：

```
manifest written: /tmp/asv_work.0Von/manifest.json (5 files)
skeleton result written: /tmp/asv_out.bCFe/result.json
verification written: /tmp/asv_work.0Von/verification.json
summary written: /tmp/asv_work.0Von/verification_summary.md
result.json written: /tmp/asv_out.bCFe/result.json (status=partial)
provenance_report written: /tmp/asv_out.bCFe/provenance_report.md
```

## 真实输出节选

`$W/verification_summary.md`（注意 beta 被标为 mismatch，且仅 `year` 字段不一致）：

```
| 文本文件 | 判定 | 说明 |
|---|---|---|
| papers/alpha_paper.txt | verified | - |
| papers/beta_paper.txt | mismatch | 见 pairs 明细 |

### papers/beta_paper.txt → mismatch
- [mismatch] `Synthetic Demo Paper Beta: Imaginary Metrics for Hypothetical Datasets`
  (doi=10.5555/synth.beta.2021, year=2021) mismatched=['year'] 字段不一致: year
```

alpha 的逐字段核对（`$W/verification.json` 节选，全部命中）：

```json
{
  "snapshot_title": "Synthetic Demo Paper Alpha: A Fictional Study of Placebo Widgets",
  "checks": {
    "title_exact": true, "title_fuzzy": true, "title_fuzzy_score": 1.0,
    "year_match": true, "doi_in_text": true, "first_author_surname_in_text": true
  },
  "mismatched_fields": [],
  "verdict": "verified"
}
```

`$O/result.json` 节选（case_id、镜像的 output_contract、诚实的 partial 状态）：

```json
{
  "case_id": "synthetic-demo-001",
  "status": "partial",
  "output_contract": {
    "overall_quality_grade": null,
    "per_source_trust": null,
    "key_findings": null
  },
  "main_results": {
    "counts": {"files": 4, "verified": 3, "mismatch": 1, "unverifiable": 0,
               "snapshot_records": 2, "duplicate_groups": 0, "version_conflicts": 0}
  },
  "uncertainties": [
    "output_contract 字段已镜像但值为 null：本技能仅完成来源真实性核验，下游文献质量判断需绑定 verified 来源后另行填充",
    "来源核验未全部通过: verified=3, mismatch=1, unverifiable=0；下游论断仅允许绑定 verified 来源，mismatch 已如实上报且未做静默修复"
  ]
}
```

`$O/provenance_report.md` 节选：

```
| 来源文件 | 类型 | 快照风格 | 判定 | 可用于评估 |
|---|---|---|---|---|
| papers/alpha_paper.txt | txt | - | verified | 是 |
| papers/beta_paper.txt | txt | - | mismatch | 否 |
| snapshots/crossref_alpha.json | json | crossref | verified | 是 |
| snapshots/europepmc_beta.json | json | europepmc | verified | 是 |
```

说明：`case.json` 作为编排文件被 fingerprint 登记，但被排除在 ledger 之外
（见 result.json 的 change_records）。output_contract 字段镜像为 null 是
有意为之——本技能只做来源核验，不做下游质量评级。

## 负例自检（空输入目录）

空输入目录下流水线同样跑通且不崩溃：fingerprint 生成 0 文件的 manifest，
build_result 产出 `status=partial`、空 `provenance_ledger` 与解释性
uncertainties（"输入目录中未发现任何来源文件"）。
