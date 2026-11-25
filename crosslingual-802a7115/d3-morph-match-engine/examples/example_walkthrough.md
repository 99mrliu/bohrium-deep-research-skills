# 最小调用示例（合成示例 / SYNTHETIC EXAMPLE）

> 本示例使用 `examples/data/` 的**合成玩具数据**，仅说明接口与产物形态，
> **不是**平台正式案例的结果。

## 输入（合成）

- `examples/data/terms.json`：2 个概念（pyroptosis：en/pt/de/ja/zh 变体，
  zh 变体标 verified=false；inflammasome：en/pt/de 变体）。
- `examples/data/corpus.jsonl`：4 条合成记录——`doc-pt`（葡语）、
  `doc-de`（德语，标题含复合词 Zellpyroptose）、`doc-mixed`（中英日混排）、
  `doc-en-none`（英语，主题无关，应零命中）。

## 调用

```bash
python3 scripts/xmatch.py --terms examples/data/terms.json \
    --roots examples/data --out examples/out
```

控制台输出（本次实际运行）：
`{"status": "ok", "records_with_hits": 3, "langs": ["de", "en", "ja", "pt", "zh"]}`

## 产物要点（本次实际运行已目检，`examples/out/matches.json` + `match_report.md`）

- `doc-pt`：piroptose、inflamassoma 经 `nfkd_fold` 命中（含 São→sao 折叠）。
- `doc-de`：Pyroptose 词边界命中；**Zellpyroptose 经 `compound_match` 命中 2 处**——
  德语复合词通道生效；Inflammasom 命中。
- `doc-mixed`：pyroptosis（拉丁词边界）、パイロトーシス（`nfkd_fold`＋`kana_romaji`
  双通道）、细胞焦亡（CJK 子串，带 [UNVERIFIED] 标记）均命中。
- `doc-en-none`：零命中，`coverage_by_lang` 中无该记录——未误中 "inflammatory cell death"。

## 复核方式

每条命中含 `rule`、`matched_form`、`offset`、`context`；在 `matches.json` 中取任一条，
按其 rule 重放归一化（如 NFKD 折叠原文后在 offset 处应读到 matched_form）。
