# 导出契约：schema、列序与下游消费

任务 output_contract 优先；本文件是缺省约定。

## 1. 输入 claims.json schema

顶层：`case_id`（必填）、`source`（title/identifier/…）、`claims[]`。
每条断言：

| 字段 | 类型 | 约束 |
|-|-|-|
| id | string | 非空、集合内唯一 |
| text / subject / relation / object | string | 非空 |
| qualifiers | array | 字符串或 {"text": ...} |
| polarity | enum | positive / negative |
| modality | enum | asserted / hedged / speculative / proposed |
| status | enum | asserted / not_reported / conflict / inferred |
| evidence.quote | string | status=asserted 时必填 |
| evidence.location | object | 自由定位（page/part/…），原样透传 |
| evidence.kind | string | direct / indirect（缺省 direct） |
| confidence.level | enum | high / medium / low |
| confidence.rationale | string | 非空 |
| searched_scope | string | status=not_reported 时必填 |
| conflict_with | array/string | status=conflict 时使用 |

校验失败导出中止并列出全部违例（行号 + 原因），不静默截断。

## 2. 导出文件

| 文件 | 形态 | 用途 |
|-|-|-|
| claims.jsonl | 每行一个 JSON，键序固定 | 无损机器交换（下游主入口） |
| claims.csv | RFC 4180，列序固定 | 表格工具/快速核查（有损：qualifiers 拼接） |
| review.md | 按 status 分组的勾核单 | 人工复核，可回填 verdict |
| review.html | 自包含静态页 | 目检预览，全量 HTML 转义 |
| export-manifest.json | 逐文件 SHA-256 + 条数 + 列序 | 完整性核验依据 |

CSV 列序（manifest.csv_columns 同步记录）：
`id, text, subject, relation, object, qualifiers, polarity, modality, status,
confidence_level, confidence_rationale, evidence_quote, evidence_location,
evidence_kind, source_id`

## 3. 下游消费示例（无需清洗）

```
# jq：取全部 high 置信断言文本
jq -r 'select(.confidence.level=="high") | .text' claims.jsonl

# pandas：读 CSV 并统计关系分布
python3 -c "import csv,collections;r=list(csv.DictReader(open('claims.csv')));print(collections.Counter(x['relation'] for x in r))"
```

## 4. 一致性不变量（check_exports.py 核验）

1. JSONL 逐行可解析，条数与 ID 集合 == 输入；
2. CSV 可被标准 csv 模块解析，条数与 ID 集合 == 输入，列序 == manifest；
3. review.md / review.html 覆盖全部 ID；
4. manifest 哈希与磁盘重算一致。

任一不成立 → FAIL，导出不得交付。

## 5. 变更记录

导出后修改断言集合 → 必须重跑导出与回读；manifest 哈希变化即变更证据。
在 result.json 的 change_records 里记录每次重导出的原因。
