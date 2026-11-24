# 卷宗（docket）格式

JSONL，每行一条记录，两种类型。

## evidence 记录

```json
{"type":"evidence","group":"G1","side":"support","claim":"断言原文",
 "source_file":"paper_a.txt","quote":"从文本层复制的逐字引文",
 "locator":"paper_a.txt 第2页",
 "quality":{"directness":"direct","evidence_kind":"experimental",
            "method_rigor":"high","year":2024}}
```

| 字段 | 取值 | 说明 |
|-|-|-|
| group | 断言组 ID（G1、G2…） | 承载同一结论的证据同组 |
| side | support / counter | 支持或反驳该断言 |
| claim | 字符串 | 组内所有记录的断言原文保持一致 |
| quote / locator | 字符串 | 逐字引文与定位；转述不得充当 quote |
| quality.directness | direct / indirect | 证据是否直接测量断言所指对象 |
| quality.evidence_kind | experimental / observational / simulation / review | 证据产生方式 |
| quality.method_rigor | high / medium / low | 方法严谨度（对照、样本、可重复性） |
| quality.year | 1900–2100 整数 | 证据发表年份 |

## counter_search 记录

```json
{"type":"counter_search","group":"G1",
 "scope":"翻检输入材料集全部 9 个来源的结果与讨论段",
 "found":true,"note":"在 paper_c.txt 第3页发现相反结论"}
```

- 每个断言组**至少一条**；found=false 时 note 必须 ≥8 字符，写清检索方式
  （翻了哪些文件、哪类段落）。
- found=true 时组内必须有对应的 counter evidence 登记。

## lint 机检项

1. 记录类型、side、quality 枚举、year 区间合法；
2. evidence 五要素（claim/source_file/quote/locator/quality）齐全；
3. 每组 ≥1 条 support 且 ≥1 条 counter_search；
4. found=true 的组必须有 counter 证据；found=false 必须有检索说明。
