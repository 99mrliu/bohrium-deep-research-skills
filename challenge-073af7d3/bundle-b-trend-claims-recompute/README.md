# bundle-b-trend-claims-recompute

研究前沿与趋势分析技能包（Playground challenge-073af7d3）。
重心：**时间趋势的统计严谨性——每句趋势主张必须可重算，审计器可证伪矛盾主张。**

## 流水线

```
build_corpus.py  → canon.jsonl + corpus_meta.json   （json/jsonl/csv/bib/ris/txt/md 归一）
slice_stats.py   → slices.json/csv                  （年度/窗口计数 + 泊松 95% CI + 右删失 40% 规则）
changepoint.py   → changepoints.json                （泊松两段 MLE 变点扫描 + MA z 波动检测）
claim_audit.py   → claim_audit.json                 （主张 vs 重算统计；违规退出码 1）
```

全部 Python 3 标准库、确定性、无网络。公式与局限见 `references/statistics_notes.md`，
主张文件 schema 与违规码见 `references/claims_schema.md`。

## 主张审计（差异点）

报告定稿前把每条趋势句写成 claims.json，审计器重算并裁决：

- `censored_year_as_decline`：右删失末年当衰退证据
- `unsupported_changepoint`：CI 未排除 1 却主张显著变点
- `fluctuation_as_inflection`：单年泊松尖峰当真实拐点
- `direction_mismatch`：主张方向与重算计数矛盾且统计可区分

任一违规 → 退出码 1，必须先修主张，禁止绕过。

## 快速验证与布局

`bash examples/run_example.sh`：在 77 条**全合成**记录（植入 2018 变点、2014 尖峰、
2025 删失）上跑通——GOOD 组退出 0，BAD 组退出 1 且四种违规全部触发；
真实产物在 `examples/example_output/`。

- `SKILL.md`：技能说明（执行协议第 5–7 步含主题演化/代表作/研究空白流程）
- `scripts/`：四个流水线脚本；`references/`：统计公式、主张 schema
- `examples/`：合成示例与真实运行产物
