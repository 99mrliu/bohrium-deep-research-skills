# 交付契约与自检清单（handoff-renderer references）

## 为什么交付是独立的质量维度

检索结果只存在于对话里就等于没有交付。本技能把交付物当作工程产品：
每个输入可追踪、每种格式有读者、每个可编辑产物有渲染证据。

## 交付包字段

| 文件 | 读者 | 作用 |
|-|-|-|
| result.json | 评测/程序 | 契约结果：case_id + output_contract 全字段 + status/uncertainty |
| manifest.json | 程序 | 输入→交付映射；completeness 自检（每个输入恰好一次） |
| INDEX.md / index.html | 人 | 总览、提问与回答、异常清单、F 编号图例 |
| metadata.csv | 表格程序 | 全文件元数据 |
| tree.md | 人 | 目录树与版本族 |
| structure.svg | 人（可编辑） | 库结构/版本关系矢量图 |
| preview_*.png | 人（目检） | 对应可编辑产物的真实渲染预览 |
| answers.json | 程序 | 提问回答（含 no_match 与检索词） |
| preview_report.json / checklist_report.json | 程序 | 渲染回读校验与自检结果 |

## 完整性自检语义

`completeness.ok = (n_inputs == n_mapped == 去重后映射数)`。即：不少映射、
不重复映射。不可读文件也必须作为条目出现（status 记 unreadable），
漏掉它比标记它更糟。

## PNG 预览的真实性

预览由 `handoff_preview.py` 用纯标准库（zlib+struct）写出 8 位灰度 PNG，
并回读签名与 IHDR 尺寸做有效性校验（结果在 preview_report.json）。
非 ASCII 字符渲染为方框字形，文件身份由 INDEX.md 的 F 编号对照给出；
预览的目的是证明"产物可被真实渲染"，不是版式还原。

## 豁免规则

内容完全被另一产物覆盖的可编辑文件（index.html/metadata.csv/tree.md
均被 INDEX.md 覆盖）可不单独出预览，但必须在 result.json 的
`preview_exempt` 中登记理由；无豁免又无预览 → 自检失败。
