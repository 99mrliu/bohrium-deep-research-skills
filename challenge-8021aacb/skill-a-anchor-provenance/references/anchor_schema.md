# 锚点与诊断记录 Schema（Skill A 专用）

## 1. 锚点命名

- 形式：`S{来源序号}-P{三位段落号}`，例如 `S1-P007`。
- 来源序号按 `/input` 下文件名排序分配，`S1` 为排序第一的可读材料文件；`case.json`、`task.md` 不作为证据来源。
- 段落按空行切分，段内换行保留；锚点只增不改，重跑同一输入得到同一锚点集（确定性）。
- 每个锚点记录 `char_start`/`char_end`（在抽取文本中的字符偏移），供复核者独立定位。

## 2. anchor_map.jsonl 行格式

```json
{"anchor": "S1-P007", "source": "S1", "file": "manuscript.md", "para_index": 7,
 "char_start": 1523, "char_end": 1891, "text": "<段落原文>"}
```

## 3. 诊断 finding 必备字段（供 verify_quotes.py 强制核验）

| 字段 | 要求 |
|---|---|
| `id` | `F001` 起顺序编号 |
| `dimension` | 六类之一：研究问题 / 章节结构 / 论证链 / 段落关系 / 重复内容 / 结论边界 |
| `anchor` | 必须存在于 anchor_map；引图表时取图注所在段锚点 |
| `quote` | **逐字**摘自该锚点段落（空白差异由核验器归一，字符不得改） |
| `defect_class` | 缺陷子类，如「论据闲置」「结论超界」；不许只写「结构问题」 |
| `action` | 可执行编辑动作：移动到哪 / 与哪段合并 / 从哪里拆分 / 哪句收窄 |
| `severity` | high / medium / low，判定依据见 references/extraction_qc.md 第 3 节 |

缺 `anchor` 或 `quote` 的 finding 会被核验器记为 `unverifiable` 并拉低
`quote_verification.verified_fraction`；宁可少报，不可无锚。

## 4. result.json 与锚定层的衔接

- `sources`：逐条列 `{source, file, paragraphs, garble_suspect}`，与 manifest.json 一致。
- `change_record`：每条 `{finding_id, anchor, before_quote, action}`。
- `uncertainty`：乱码、截断、不可读文件、未核验 finding 的原因，逐条如实列出。
- `quote_verification.verified_fraction`：取 verify_quotes.py 报告的 `ok/total`。
