# 行政版本备注句式正则清单（E1 语法）

E1 从备注类文本中逐行提取替代关系。捕获组语义统一：`new`=替代者（新版本），
`old`=被替代者（旧版本）；连边方向 **old → new（supersedes）**。
每条命中记录 `locator = 文件相对路径#L行号` 与原文整行，作为边的 evidence。

实现：`scripts/lineage.py` 的 `ADMIN_PATTERNS`。文件名字符类：
`[A-Za-z0-9_\-\.一-鿿]`（字母/数字/`_ - .`/CJK；**不含空格**，含空格的文件名
无法被捕获——已知限制，模型可按 task.md 用 overrides 手工补边）。

## 备注文件识别

- 文件名（NFC，大小写不敏感）含任一：`备注`、`notes`、`note`、`version`、`版本`、`行政`、`admin`；
- 或 task.md 中用"备注文件：xxx" / "note file: xxx" 显式指定。

## 句式清单

| id | 句式 | 正则骨架 | 例 | 边 |
|---|---|---|---|---|
| zh_tidai | X 替代/取代 Y | `(?P<new>…+?)\s*(替代\|取代)\s*(?P<old>…+)` | `scan_final.pdf 替代 scan_old.pdf` | scan_old→scan_final |
| zh_zuofei | X 作废，以 Y 为准 | `(?P<old>…+?)\s*作废[，,；;]?\s*以\s*(?P<new>…+?)\s*为准` | `报告_v2.docx 作废，以 报告_v3.docx 为准` | v2→v3 |
| zh_beiti | Y 已被 X 替换/取代/替代 | `(?P<old>…+?)\s*已被\s*(?P<new>…+?)\s*(替换\|取代\|替代)` | `旧表.csv 已被 新表.csv 替换` | 旧表→新表 |
| zh_yiweizhun | X 不再使用，以 Y 为准 | `(?P<old>…+?)\s*不再使用[，,；;]?\s*以\s*(?P<new>…+?)\s*为准` | `草稿.txt 不再使用，以 定稿.txt 为准` | 草稿→定稿 |
| en_replaces | X replaces Y | `(?P<new>…+?)\s+replaces\s+(?P<old>…+)`（忽略大小写） | `v2.pdf replaces v1.pdf` | v1→v2 |
| en_supersedes | X supersedes Y | `(?P<new>…+?)\s+supersedes\s+(?P<old>…+)`（忽略大小写） | `final.pdf supersedes draft.pdf` | draft→final |

## 解析与冲突

1. 捕获到的名字先按**文件名精确匹配**解析到扫描记录；失败再按**词干唯一匹配**；
   同名多文件或词干多文件 → 无法唯一解析，记 `unresolved_admin_reference` 冲突，**不猜、不连边**。
2. 两端解析为同一内容（同 SHA-256）→ 记 `admin_self_edge` 冲突，不连边。
3. E1 边与 E3 候选边方向矛盾 → E1 优先，E3 候选记入 `e1_overrides_e3`（自动解决）。
4. E1 指认的文件对词干不同也照连（行政备注为准）。
5. 行首编号（`1.`、`2.`）不会污染捕获：编号后无法直接续上句式关键词，正则自动滑到真正的文件名起点。

## 校验器回查

`verify_lineage.py` 对每条 `basis=admin_note` 的边做 locator 回查：
读 locator 所指文件的对应行，重跑同组正则，两端必须解析到与边一致的 SHA-256，
否则 audit 记 FAIL。这保证"行政备注依据"不是编出来的。
