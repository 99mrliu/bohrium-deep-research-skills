# 最小调用示例（合成示例 / SYNTHETIC EXAMPLE）

> 本示例使用 `examples/data/` 的**合成玩具数据**（service 字段为虚构的
> `synthetic-translator v0-synthetic`），仅说明接口与产物形态，
> **不是**平台正式案例的结果。

## 输入（合成）

- `concepts.json`：C1 pyroptosis、C2 NLRP3 inflammasome（各仅 en 变体）。
- `translations.json`：5 条译名条目，刻意覆盖全部质检分支——
  E001 pt 回译一致；E002 de 缺回译；E003 es 回译漂移（"cell death"）；
  E004 pt 一致；E005 缺 term（invalid）。

## 调用

```bash
python3 scripts/translation_ledger.py --concepts examples/data/concepts.json \
    --translations examples/data/translations.json \
    --langs en,pt,es,de,ja,zh --out examples/out
```

控制台输出（本次实际运行）：
`{"status": "ok", "entries": 5, "by_status": {"verified": 2, "no-evidence": 1, "degraded": 1, "invalid": 1}, "gaps": 6}`

## 产物要点（本次实际运行已目检，`examples/out/ledger.json` + `roundtrip_report.md`）

| entry | 分支 | 结果 |
|-|-|-|
| E001 piroptose | 回译与 label 一致 | verified / full-weight |
| E002 Pyroptose | 无回译证据 | no-evidence / half-weight |
| E003 piroptosis(es) | 回译为 cell death，漂移 | degraded / half-weight，score 0.00 |
| E004 inflamassoma NLRP3 | 回译一致 | verified / full-weight |
| E005 | 缺 term | invalid / hold-for-review |

`to_translate` 列出 6 个 concept×语种 缺口（C1 缺 ja/zh；C2 缺 es/de/ja/zh）。

## 复核方式

`ledger.json` 每条含 `roundtrip_score` 与 `reason`，可手工重算 token Jaccard 验证；
usage 列直接决定下游检索中的权重与标记策略。
