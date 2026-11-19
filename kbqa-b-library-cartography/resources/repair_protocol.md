# 修复规程（repair protocol）

## 总则

1. 输入只读：不删除、不移动、不改名输入文件；物理整理只写方案进台账，除非任务说明明确要求执行。
2. 一切决策可复跑：分组、排序、保留全部来自确定性判据（哈希、相似度阈值、备注、文件名、时间），不凭模型直觉。
3. 无法判断 → `undecidable`：记成员、记分歧点、记需要什么额外信息（如原始来源、发行记录），不猜。

## 判据表

| 情况 | 判据 | 结果 |
|-|-|-|
| SHA-256 相同 | 字节一致 | 同一别名组；canonical=路径字典序最小者 |
| shingle Jaccard ≥ 0.85 | 内容实质相同 | 同一别名组 |
| 0.60 ≤ Jaccard < 0.85 | 同一文献的修订 | 同一版本链 |
| Jaccard < 0.60 | 无关 | 独立条目 |
| 行政备注"以 X 为准" | 显式权威 | X 标 current_admin；若与哈希/时间排序冲突，记录 conflict |
| 文件名 v1/v2/年份/final | 次级证据 | 版本排序依据（admin 缺位时） |
| mtime | 末位证据 | 仅在前两级都缺位时使用 |

## 冲突登记表

每个冲突记录：组 id、冲突类型（`name_vs_mtime` / `admin_note_overrides` / 其他）、双方排序、处置（取行政备注 / 保持文件名序）、给人工复核的建议。冲突不阻断编目，但 result.json 的 uncertainty 必须提及数量。

## 恢复建议字典

- `no_permission`：请求提权或由组织方重新授权；本条目只入编目，不入问答证据。
- `pdftotext-missing`：安装 poppler 或用平台 OCR 工具；重跑 lib_inventory.py 后自动归位。
- `unsupported_type`：标注需要专用解析器；本次入编目不参与问答。
- `docx 损坏`：从来源重新获取；记录 expected sha（若元数据里有）。
- 目录为空：catalog 空结构 + partial；uncertainty 说明"输入目录无材料"。

## 问答侧约束

- 检索与引用仅限 `current_version=true` 且 `readable=true` 的条目。
- 历史版本引用被 lib_finalize.py 自动移入 `version_caveats`，不静默通过。
- 同一事实在不同链成员中数值不同：并列引用两个版本并注明差异，不裁决，除非行政备注给出权威版本。
