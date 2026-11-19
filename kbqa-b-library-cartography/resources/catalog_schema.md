# catalog.json 模式（六维编目）

顶层结构：

```json
{
  "built_at": "<ISO8601>",
  "input_dir": "/input",
  "dimensions": { ...六维... },
  "conflicts": [ ... ],
  "entries": [ ...逐文件记录... ]
}
```

## dimensions（六维，缺数据写空结构 + uncertainty 说明，不省略）

| 维度 | 字段 | 内容 |
|-|-|-|
| 文件类型 | `file_types` | `{".pdf": 12, ".md": 3, ...}` 扩展名分布 |
| 元数据字段 | `metadata_fields` | 来源文件清单 + 解析出的记录；缺字段为 null，不编造 |
| 目录层级 | `directory_tree` | `{目录: [entry_id,...]}` 原始目录结构 |
| 重复文件 | `duplicates` | 每组：成员、保留项、判定依据（哈希/相似度） |
| 版本差异 | `version_diffs` | 每条版本链：成员、角色（current/historical）、排序依据 |
| 权限与来源 | `permissions_sources` | 可读计数、不可读计数、skipped 清单与原因 |

## entries（逐文件）

```json
{
  "entry_id": "E003",
  "path": "papers/2022/report_v2.md",
  "name": "report_v2.md",
  "type": ".md",
  "size": 18124, "mtime": 1690000000.0, "sha8": "a3f2c1d9",
  "readable": true,
  "extract_status": "ok",
  "group_id": "G02",
  "role": "current",
  "current_version": true,
  "n_lines": 342
}
```

`role` 取值：`unique`（独立文件）、`canonical`/`duplicate`（别名组）、`current`/`historical`（版本链）、`current_admin`（行政备注指定的当前版本，会记录冲突）。

## 引用坐标

问答证据引用编目条目：`[E003|a3f2c1d9|L12-L14]"逐字引文"`。行号对该 entry 的抽取文本（work/extracted/E003.txt）起算。历史版本仅允许在"明确要求查版本演变"时引用，且必须声明其在链中的角色。
