# 合成示例（synthetic / 合成）

本目录演示「重算 + 主张审计」管道。**所有数据均为合成，不对应任何真实文献。**

## 植入真值（synthetic_case/corpus.jsonl，77 条合成记录）

| 设计 | 植入方式 |
|---|---|
| 低基线 | 2010–2017 年约 2–4 篇/年 |
| 单年尖峰（波动，非拐点） | 2014 年 = 9 篇 |
| 速率变点 | 2018 年起升至约 6–8 篇/年（2018–2024） |
| 右删失 | 2025 年 = 1 篇（数据截取不全，非衰退） |

- `claims_good.json`：与植入真值一致的主张（2018 变点↑、2010–2024 趋势↑、2014 按波动处理）。
- `claims_bad.json`：与统计矛盾的主张（2025 删失年当衰退、2014 尖峰当拐点、2016 假变点、2010–2024 趋势↓）。

## 运行

```bash
bash examples/run_example.sh
```

脚本依次执行 build_corpus → slice_stats → changepoint → claim_audit，
GOOD 组须退出 0，BAD 组须退出 1 且四种违规（censored_year_as_decline /
fluctuation_as_inflection / unsupported_changepoint / direction_mismatch）全部触发，
否则脚本自身失败。所有断言通过时输出 `ALL CHECKS PASSED`。

## 产物（example_output/，真实运行生成）

- `good/`：canon.jsonl、corpus_meta.json、slices.json/csv、changepoints.json、claim_audit.json
- `bad/`：claim_audit.json、claim_audit_stdout.txt
