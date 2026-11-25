# 字段信任分模型与修复规则表

本文件是 `trust_scores.py` 与 `repair_fields.py` 的规则说明，供复核与维护。
所有规则都是**保守**的：宁可标 missing/untrusted，也不猜值、不覆盖、不合并。

## 1. 字段信任状态（field_trust）

每条记录的每个字段取五态之一：

| 状态 | 含义 | 典型来源 |
| --- | --- | --- |
| `trusted` | 原值存在且通过全部检查 | 默认态 |
| `repaired` | 经**可验证**安全修复 | mojibake 修复、HTML 实体反转义、控制字符清除、DOI 规范化 |
| `filled` | 经快照内保守补全 | cross_fill_by_doi / cross_fill_by_title（留痕可溯） |
| `missing` | 缺失或占位符（"N/A"、"."、空串、空列表） | 无强键可补时保持此态 |
| `untrusted` | 存在但未通过校验 | 畸形 DOI、越界/非数字年份、异常页码、不可修复乱码 |

严重度排序（用于多来源标记合并）：
`untrusted > missing > filled > repaired > trusted`；
`repaired` 与 `filled` 的留痕标记总是生效（可追溯优于沉默）。

### 关键字段与 quarantine

关键字段：`title`、`abstract`、`year`/`publication_year`。记录进入
quarantine 的条件（满足其一）：

1. 任一关键字段为 `untrusted`；
2. 存在不可修复乱码（`flagged_untrusted`）的文本字段；
3. `doi` 字段为 `untrusted`（畸形 DOI 会破坏下游引用链）。

`missing` **不**进 quarantine：摘要缺失是证据限制，不是数据不可信，
是否可用由下游（纳排/证据抽取）决定。

## 2. 修复规则表

| 规则名 | 触发条件 | 动作 | 安全论证 |
| --- | --- | --- | --- |
| `text_health_safe_repair`（控制字符） | 字段含 C0 控制字符（除 \t\n\r）、DEL、零宽字符、内嵌 BOM | 删除 | 这些字符不承载文献语义 |
| `text_health_safe_repair`（mojibake） | 检出 UTF-8-as-Latin-1 指纹（见 encoding_and_identifier_notes.md） | 整串 Latin-1→UTF-8 round-trip；失败则逐字符簇修复 | 接受条件：可疑模式数严格下降 且 不引入 U+FFFD；否则放弃 |
| `text_health_safe_repair`（HTML 实体） | 检出 `&name;`/`&#NN;`/`&#xNN;` | `html.unescape` | 标准库确定性反转义 |
| `doi_normalize` | DOI 带 `https?://(dx.)doi.org/` 前缀、`doi:` 前缀、尾标点、大小写混杂 | 去前缀、去尾标点、小写化 | 均为 DOI 显示层差异，不改变标识符本体 |
| `cross_fill_by_doi` | 目标字段 missing/占位符；同快照另一记录规范化 DOI 精确一致且持有该字段；键组内取值唯一 | 补字段并留痕（record、field、old、new、source_record_id、rule） | 强键 + 唯一取值；冲突即不补 |
| `cross_fill_by_title` | 同上，但强键为规范化题名（小写、去非字母数字、长度 ≥12） | 同上 | 长度门槛防 "Intro" 类短题名碰撞 |

### 保守补全的硬约束

- **只补字段、不合并记录**：输入 N 条记录，输出恰好 N 条。
- **绝不覆盖**已有非占位符值（哪怕它可疑——可疑走 untrusted，不走改写）。
- **无强键宁可不补**：占位符 DOI、空 DOI 不参与构键。
- **冲突不补**：键组内同一字段出现 ≥2 个不同归一化取值时，记入
  `conflicts`，谁也不补（两源说法不一致时采信任一都是臆断）。
- 补全白名单仅限书目事实字段（doi/year/journal/volume/issue/pages/
  authors/abstract/language/keywords/publication_type/issn/pmid），
  不补任何结论性字段。

## 3. 取值域 sanity 规则

| 字段 | 规则 | 违规标记 |
| --- | --- | --- |
| year / publication_year / pub_year | 4 位数字（int 或 str），范围 1800–当前年+1 | `year_not_4digit_int` / `year_out_of_range_*` |
| pages | 形如 `112-120`、`e55`、`A1-A9`（字母可选前缀+数字+可选区间） | `pages_odd_shape` |
| doi | 规范化后匹配 `^10\.\d{4,9}/\S+$` | `doi_malformed` |

## 4. 语种鉴定

字符脚本优先：假名→ja，谚文→ko，汉字占优→zh，西里尔占优→ru，
阿拉伯字母占优→ar；拉丁脚本用停用词打分（en/pt/es/fr/de）。
置信度 high/medium/low；**low 仅供参考**。guess 不在
eligible_languages 内即置 `language_flag`，不据此排除记录
（纳排是下游职责）。

## 5. 已知局限

- 停用词表小，短标题的拉丁语种判定可能不准 → 以置信度呈现。
- mojibake 修复只覆盖"UTF-8 被按 Latin-1 读"这一类；GBK/Big5 误读
  不在启发式内，会落入不可修复 → untrusted（保守方向正确）。
- 规范化题名键对"同题不同文"（如 erratum 与原文同题）可能误配；
  冲突检测会在字段取值不一致时拦住补全，但同值字段仍可能被串补——
  下游应结合 quarantine 与 change_records 复核。
