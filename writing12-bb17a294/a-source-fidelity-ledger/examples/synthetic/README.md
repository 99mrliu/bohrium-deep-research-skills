# 合成示例 / Synthetic example

**本目录为合成示例（synthetic example）：所有文本与数据均为虚构，仅用于演示流程，不构成任何真实研究。**

## 内容 / Contents

| 文件 | 说明 |
|---|---|
| `source.txt` | 手写的虚构英文学术段落（输入）。含年份、样本量、百分数、区间、单位量、大额数字（2.5 million）、三种引用形态 [12] / (Smith, 2020) / Li et al. (2021)、图/表引用。 |
| `translation_zh.md` | 手写中文译文（输入）。保留全部事实；其中 **2.5 million USD → 250 万美元** 是唯一一处刻意的跨 locale 改写（应判为 `normalized`）。 |
| `extraction_manifest.json` | `extract_source.py` 的真实输出（text-passthrough，单伪页，含逐页字符数与 sha256 覆盖校验）。 |
| `facts.jsonl` | `build_fact_ledger.py` 的真实输出：24 条事实（F0001–F0024）。 |
| `audit_report.json` | `audit_translation.py` 的真实输出：23 preserved / 1 normalized / 0 missing / 0 altered / 0 added，退出码 0。 |

## 复现 / Reproduce

```bash
B=.../a-source-fidelity-ledger            # bundle 根目录
W=$(mktemp -d)
python3 "$B/scripts/extract_source.py" "$B/examples/synthetic/source.txt" -o "$W"
python3 "$B/scripts/build_fact_ledger.py" "$W"
python3 "$B/scripts/audit_translation.py" "$W/facts.jsonl" \
    "$B/examples/synthetic/translation_zh.md" -o "$W/audit_report.json"
echo $?                                    # 期望 0
```

预期：`build_fact_ledger` 报告 24 facts；`audit_translation` 报告
`total=24 preserved=23 normalized=1 missing=0 altered=0 added=0`，
且 F0017（`2.5 million` → `250 万`）为唯一的 `normalized`。

## 负例自检 / Negative self-check

删除译文中的 `2,004 美元`（或把 `8.2%` 改成 `8.7%`）后重跑
`audit_translation.py`，应得到退出码 1，且对应事实分别判为
`missing`（或 `altered`，并伴随一条 `added` 警告）。
