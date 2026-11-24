# index_schema.md — index.json 结构（schema: `xref-index/v1`）

由 `scripts/build_index.py` 生成。所有位置为相对文件名 + 1 起始行号；
不含绝对路径与时间戳，输出确定性。顶层字段：

```json
{
  "schema": "xref-index/v1",
  "chapters_dir": "chapters",            // 目录基名
  "files": ["chapter1.md", "..."],       // 扫描到的章节文件（排序）
  "note": "...",                          // 可选，--note 传入，随报告传播
  "term_groups": [{"canonical": "UV固化胶", "variants": ["UV固化胶", "紫外固化胶"]}],
  "headings": [
    {"file": "chapter1.md", "line": 1, "level": 1, "number": "1", "text": "1 引言"}
  ],
  "floats": [                             // 题注（行首出现的 图/表/Figure/Fig./Table + 编号）
    {"file": "chapter2.md", "line": 17, "kind": "figure",
     "number": "2-1", "caption": "图 2-1 丁基橡胶涂布位置示意图"}
  ],
  "float_refs": [                         // 正文引用点（非题注行内的同模式匹配）
    {"file": "chapter2.md", "line": 15, "kind": "figure",
     "number": "2-1", "context": "丁基橡胶的涂布位置如图 2-1 所示。"}
  ],
  "citations": {
    "bibliography_found": true,
    "bibliography_files": ["chapter3.md"],
    "references": [                       // [n] 引用点；[1-3]/[1,3] 已展开为 numbers
      {"file": "chapter1.md", "line": 5, "numbers": [1], "context": "..."}
    ],
    "entries": [                          // 参考文献小节内的条目
      {"file": "chapter3.md", "line": 15, "number": 1, "text": "[1] 张某某. ..."}
    ]
  },
  "abbreviations": {
    "definitions": [                      // 全称（ABBR）定义点
      {"file": "chapter1.md", "line": 5, "full": "钙钛矿太阳能电池", "abbr": "PSC"}
    ],
    "uses": [                             // 缩略语 token 的全部出现位置
      {"abbr": "PSC", "file": "chapter1.md", "line": 5, "column": 1,
       "is_definition_site": true}
    ]
  },
  "term_forms": {                         // --terms 指定变体的全部出现位置
    "UV固化胶": [{"file": "chapter1.md", "line": 11, "column": 12, "context": "..."}]
  },
  "counts": {"files": 3, "headings": 10, "floats": 4, "float_refs": 4,
             "citation_points": 3, "reference_entries": 3,
             "abbrev_definitions": 3, "term_variants": 2}
}
```

## 扫描口径（重要）

- 编号归一化：全角数字→半角；`- ‑ ‒ – — −`→`-`；编号内 `.`→`-`，
  故"图 2‑1""图2-1""图２-１""Figure 2-1"都归一为 `figure / 2-1`。
- 题注 vs 引用：剥掉行首 markdown 修饰符后以浮动体 token 开头者记为题注；
  否则行内全部匹配记为引用点。`示意图 2-1` 中的"图"被 `(?<!意)` 排除。
- 标题行、参考文献小节内的条目行不参与 float/citation/term/abbr-use 扫描；
  参考文献条目编号只记入 `citations.entries`（条目标题保持原文，不计术语漂移）。
- `--terms` 语法：`规范写法|变体1|变体2;术语B|变体B1`；组内首个为规范写法。
