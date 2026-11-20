# OCR 粘连与边界规则（rules/ocr_boundary.md）

与 `scripts/patent_numbers.py: try_split_merged` 及 `scripts/extract_facsimile.py` 同步。WO 合并 OCR 的粘连边界在抽取结果中**保留原样**，拆分仅以事件形式记录，不改写原始文本。

## 粘连类型与处置

| 类型 | 示例 | 处置 |
|-|-|-|
| 国家码边界粘连 | `EP1234567A1EP7654321B1` | 在内部国家码/kind 边界尝试拆分；**唯一可行拆分**才接受，记 `ocr_split` 事件并提示人工核对原文影像 |
| 多解粘连 | 同一粘连串存在 ≥2 种合法拆分 | 不拆分，记 `ocr_split_failed`，保留原样 + 警告 |
| 无解粘连 | 超长数字串无任何合法边界 | 同上，不猜测 |
| INID 码与内容粘连 | `(54)Title(57)Abstract` 同行 | 按 `(NN)` 出现位置切段，天然分离；切段结果记录 |
| 重复 INID | 同一 `(72)` 出现两次（OCR 重影/续行） | 合并为一段，记 `inid_duplicate` 事件，提示人工核对 |
| 无国别码申请号 | `15/654,321`（USPTO 传真） | 按文献国别回退规范化，记 `cc_fallback` 事件，提示人工核对 |
| 首页无 INID | 图像 PDF 未 OCR / 版式异常 | `extraction_status=degraded`，记 `no_inid`，不伪造字段 |

## 总原则

- 拆分是"建议 + 事件"，不是"改写"：原始文本与原始号码串始终保留在 `raw` 字段。
- 任何不确定的拆分都进入 `evidence_events` 并汇入 result.json 的 uncertainty，供人工复核。
- 禁止为多解/无解粘连选择一种解释当作事实。
