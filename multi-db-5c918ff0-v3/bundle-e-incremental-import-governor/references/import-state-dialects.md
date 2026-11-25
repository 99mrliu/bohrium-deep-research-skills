# import_state 方言(dialects)与规范化映射

本技能支持三种组织者本地导入状态的方言。检测顺序:**文件名提示优先**
(文件名含 `import_state` / `import-state` / `ingest_state` 或形如
`state.json`),再做结构推断;与出版方记录文件的关键区分点是——状态行
含哈希键(`content_hash`/`fields_hash`/`hash`)而**不含 `title`**。

## 方言 a:records + watermarks(能力最强)

```json
{
  "watermarks": {"crossref": {"cursor": "...", "offset": 20},
                 "europepmc": {"cursorMark": "..."},
                 "publisher": {"last_seq": 1042}},
  "records": [
    {"identifier": "10.xxxx/...",         // 或 doi / pmid 键
     "source_db": "crossref",
     "content_hash": "<sha256>",           // 或 hash / fields_hash
     "imported_at": "ingest-run-2025-09",  // 或 seq(逻辑序号,不透解析)
     "fields": {"title": "...", "authors": [...], "year": "2021",
                "venue": "...", "doi": "...", "pmid": "..."}}
  ]
}
```

- 检测规则:顶层为对象且 `records` 为(可空)对象数组。
- 规范化:`identifier` ← `identifier` | `doi` | `pmid`(后者补 `pmid:`
  前缀);`content_hash` ← 首个出现的 `content_hash` | `hash` |
  `fields_hash`;`imported_at` ← `imported_at` | `seq`,作为不透明逻辑
  记号保留;`watermarks` 原样保留。
- **`fields` 存在时 `stores_fields=true`**:changed 条目可给出 field 级
  before→after;否则只能声明 `changed_fields_unavailable`。

## 方言 b:扁平映射

```json
{
  "10.xxxx/...": {"hash": "<sha256>", "source_db": "crossref"},
  "pmid:39000001": {"content_hash": "<sha256>", "source_db": "europepmc"}
}
```

- 检测规则:顶层为对象,所有值都是对象且均含哈希键。
- 规范化:键即 `identifier`;无 watermarks(水印提案中各库按
  `no previous` → initialize/hold 处理);无 fields →
  `changed_fields_unavailable`。

## 方言 c:JSONL 状态行

```
{"identifier": "10.xxxx/...", "content_hash": "<sha256>", "source_db": "crossref"}
{"identifier": "pmid:39000001", "hash": "<sha256>", "source_db": "europepmc"}
```

- 检测规则:文件非整体 JSON,逐行均为对象,且每行含标识符键
  (`identifier`/`doi`/`pmid`/`id`)与哈希键、不含 `title`。
- 规范化:逐行同方言 a 的记录映射;无 watermarks。

## 内容指纹(content fingerprint)的精确定义

`changed` 判定的唯一标准。对字段子集
`{title, authors, year, venue, doi, pmid}`:

1. `title` / `venue`:Unicode NFKC → casefold → 折叠连续空白为单个空格
   → 去首尾空白;空值归一为 null。
2. `authors`:保持顺序,逐作者按 title 同规则规范化;字符串形式按
   `;` 或 `|` 切分。
3. `year`:取首个匹配的四位年份(1500–2199)。
4. `doi`:去 `https://doi.org/`、`doi:` 等前缀,casefold。
5. `pmid`:取首个数字串。
6. 对上述规范化对象做 canonical JSON(sort_keys, 紧凑分隔符)的
   sha256,十六进制小写。

**任何对本定义的修改都是指纹语义变更**,必须同步修改
`scripts/import_governor.py::fingerprint_fields` 与本文件,并重跑合成
示例验证确定性。

## 六路分类的判定规则(diff)

对状态∪当前响应的标识符并集(按别名匹配:doi / pmid / 源内 id 任一
相交即同一实体):

| 类别 | 规则 |
| --- | --- |
| `new` | 当前响应存在,状态无任何别名匹配 |
| `unchanged` | 匹配成功且 content_hash == content_fingerprint |
| `changed` | 匹配成功但指纹不等;方言存字段 → field 级 before→after,否则 `changed_fields_unavailable=true` |
| `withdrawn` | 状态记录在案,声称来源库响应**在场**,记录已消失,且状态行自身一致 → 子类 `source_present_but_record_gone` |
| `unverifiable_withdrawal` | 状态记录在案但其来源库响应**缺席** → 子类 `source_absent_too`,无法区分"撤回"与"源未提供" |
| `inconsistent_state` | 记录未匹配且状态行自相矛盾(identifier 与自带 fields.doi/fields.pmid 冲突)**或**标识符形态不符合声称来源库(如 crossref 记录不是 DOI 形态) |

分区不变量:六类互不重叠、完备,计数之和 = 并集大小(脚本内 assert +
selfcheck 复核)。

## 未知方言怎么办

1. 不猜测、不按近似结构解析;
2. 写 `work/sniff_report.json`,附失败原因(不符合 a/b/c 哪条规则);
3. `parse` 返回 2;`run-all` 落诚实 partial 的 result.json
   (status=partial,uncertainty 含 sniff_degradation),退出码 2;
4. 由组织者把状态文件转换为方言 a/b/c 之一后重跑。
