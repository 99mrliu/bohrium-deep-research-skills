# 支持的语料格式与判定逻辑（corpus formats）

`scripts/source_audit.py` 递归扫描候选根（顺序：`--roots` 指定 >
`/input` > `/app/work` > cwd），处理以下扩展名：
`.json .jsonl .csv .tsv .edgelist .bib`。判定失败的文件登记为
`unknown`（unparsed），解析异常登记为 `failed`，均不中断扫描。

## JSON / JSONL

按以下顺序判定（命中即停）：

| 判定格式 | 结构特征 | 记录提取 |
|---|---|---|
| `crossref` | 对象含 `message`，且 `message.items` 为列表，或 `message` 本身含 `DOI`/`title`（单条 work） | `items[i]`：`title[0]`、`author[]`（given+family）、`issued.date-parts[0][0]` 年、`DOI`、`container-title[0]`、`reference[]`（`DOI`/`article-title`/`unstructured`/`key`） |
| `europepmc` | 对象含 `resultList.result` 列表 | `result[i]`：`title`、`authorString`（`;` 分隔）、`pubYear`、`doi`、`journalTitle`、`referenceList.reference[]`、`citedByList.citedBy[]` |
| `openalex` | 对象含 `results` 列表，或单对象含 `id`+`referenced_works` | `display_name`/`title`、`authorships[].author.display_name`、`publication_year`、`doi`、`primary_location.source.display_name`、`referenced_works[]`（作为引用目标 raw_id） |
| `generic-nodes` | 顶层为 dict 列表，或含 `nodes/papers/records/works/data` 列表 | 每条含 `title/doi/year/authors/venue` 及 `references[]`/`citations[]`（字符串或对象） |
| `generic-single` | 单对象含 `title`/`doi` | 作为一条节点记录 |
| `unknown` | 以上皆不命中 | 不产出记录，登记原因 |

JSONL 逐行判定，文件级格式取各行判定的众数；坏行跳过（行号不占用记录）。

## CSV / TSV

- 表头含 `source` 与 `target` 列 → `edge-list`：每行产出一条边记录
  （kind=edge），供构建阶段并入引用图。
- 表头含 `title` 或 `doi` → `node-table`：每行产出一条文献记录；
  `references` 列若存在，按 `;` 或 `|` 分隔为引用目标。
- 其余 → `unknown`。

## .edgelist

每行两个 token（空白/逗号/制表符分隔），`#` 开头为注释；产出 kind=edge
记录。token 可为 DOI 或标题文本，构建阶段按 DOI→标题→alt_id 顺序解析。

## .bib（BibTeX）

按 `@type{key, field = {...}}` 解析；提取 `title/author（and 分隔）/year/
doi/journal|booktitle`；条目键记入 `alt_ids`（`bibkey:<key>`）。
BibTeX 一般不带引用列表，故仅贡献节点。

## 规范化记录的统一形态

```json
{
  "kind": "work",
  "title": "...", "authors": ["..."], "year": 2019,
  "doi": "10.xxxx/...", "venue": "...",
  "references": [{"doi": "...", "label": "...", "raw_id": "...", "pointer": "/message/items/0/reference/3"}],
  "citations":  [...],
  "alt_ids": ["..."],
  "source_format": "crossref",
  "locator": {"file": "<相对路径>", "pointer": "<JSON 路径或行号>"}
}
```

边记录形态：`{"kind":"edge","source":"...","target":"...","locator":{...}}`。

## 引用目标解析顺序（构建阶段）

1. 规范化 DOI 精确匹配；
2. 规范化标题（label）匹配；
3. raw_id 对记录 `alt_ids` 精确匹配。

三步皆失败 → 保留 stub（见 veracity_policy.md 第 3 条）。
