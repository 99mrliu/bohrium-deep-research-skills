# 最小调用示例（合成示例 / SYNTHETIC EXAMPLE）

> 本示例使用 `examples/data/` 下的**合成玩具数据**，仅说明接口与产物形态，
> **不是**平台正式案例的结果，不得当作正式答案提交。

## 输入（合成）

`examples/data/`：

- `records.jsonl`：3 条记录。`rec-pt-001`（葡语，标注 pt，有 DOI）；
  `rec-mislabeled-002`（**正文为葡语但故意标为 en**，无 DOI）；
  `rec-en-003`（英语，有 DOI）。
- `copy_of_en003.txt`：`rec-en-003` 标题+摘要的逐字副本（完全重复）。
- `short_note.txt`：仅 13 字符的缩写便签（无法判语种）。

## 调用

```bash
python3 scripts/corpus_audit.py --roots examples/data --out examples/out
```

控制台输出（本次实际运行）：

```json
{"status": "ok_with_findings", "counts": {"documents": 5, "findings": 5, "duplicate_pairs": 1}}
```

## 产物（本次实际运行已目检）

`examples/out/provenance_ledger.json` 与 `examples/out/audit_report.md`，关键内容：

| record | declared | detected | conf | 说明 |
|-|-|-|-|-|
| rec-pt-001 | pt | pt | 0.842 | 标签与正文一致 |
| rec-mislabeled-002 | en | **pt** | 0.70 | 触发 `language_label_mismatch` |
| rec-en-003 | en | en | 0.957 | 一致 |
| copy_of_en003.txt | — | en | 0.957 | 与 rec-en-003 构成 `near_duplicate`（similarity 1.0） |
| short_note.txt | — | und | 0.0 | 触发 `language_undetermined` |

findings 含 3 条 `missing_doi`、1 条 `language_label_mismatch`、1 条 `language_undetermined`；
重复对 1 对（相似度 1.0，建议计数一次、保留双方归因）。

## 复核方式

打开 `examples/out/audit_report.md`，逐条 finding 对照 `source_file` 回指原始文件，
确认：误判标签记录的正文确为葡语；重复对文本逐字一致；便签确无法判语种。
