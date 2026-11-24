# 题录字段定义与规范化规则（record_schema）

> 本协议是 verify_corpus.py 的字段语义依据。任何进入筛选的题录必须先按本协议
> 规范化，再接受 V1–V8 核验。

## 1. 记录字段定义

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | 字符串 | **是** | 语料内唯一标识；缺失 → V1 invalid |
| title | 字符串 | **是** | 文献题名；缺失或空串 → V1 invalid |
| authors | 数组（推荐）或字符串 | 建议 | 作者列表；用于 V4 精确重复键 |
| year | 整数或可解析字符串 | 建议 | 出版年；缺失跳过 V3，越界 → suspicious |
| venue | 字符串 | 建议 | 期刊/会议名；参与 V6 撤稿信号扫描 |
| doi | 字符串 | 可选 | 数字对象标识；非法格式 → V2 suspicious |
| type | 字符串 | 可选 | article / review / conference；缺省时由 V7 推断 |
| language | 字符串 | 可选 | en / zh / other；缺省时由 V7 推断 |
| abstract | 字符串 | 可选 | 摘要；参与语言检测 |
| note | 字符串 | 可选 | 导出备注；参与 V6 撤稿信号扫描 |

records 文件接受两种格式：`.json`（顶层为数组，或含 records/references/items/data
键的对象）与 `.jsonl`（每行一个 JSON 对象）。

## 2. 规范化规则

### 2.1 文本规范化（NFKC）

一切参与比较的文本（题名、作者、DOI）先做 Unicode NFKC 规范化：
全角字符折半、兼容字符归一，再去首尾空白并转小写。这保证全角标点、
全角数字与半角形式在比较中等价。

### 2.2 题名比较键

`norm_title_key(title)` = NFKC 规范化后删除一切非字母数字字符（含标点、空格、
连字符）。"Title: A Study" 与 "Title - a study" 的比较键相同。

### 2.3 DOI 规范化

`norm_doi(doi)` = NFKC + 小写 + 去除常见解析器前缀
（`https://doi.org/`、`http://doi.org/`、`http(s)://dx.doi.org/`、`doi.org/`、
`doi:`）+ 去空白。语法校验（V2）作用于**规范化后**的 DOI：
`^10\.\d{4,9}/\S+$`。导出工具常带解析器前缀，直接对原始字符串做语法判定会
误杀合法记录——这是本协议刻意修正的已知陷阱。

### 2.4 第一作者姓提取（启发式）

1. authors 为数组：取第一个元素；为字符串：按 `;` 或 ` and ` 切分取首段。
2. 首段含逗号 → 视为 "Last, First" 形式，姓为逗号前部分。
3. 首段以 CJK 字符（U+4E00–U+9FFF）开头 → 中文姓名，姓为第一个字。
4. 否则视为西文 "First Last" 形式，姓为最后一个空白分隔词。

**局限**：字符串形式的作者列表（如 `"Zhang W, Li X"`）与 "Last, First" 形式
存在歧义，解析结果为启发式结论。建议上游一律提供数组形式 authors；仅作
字符串提供时，V4 重复键的置信度下降，应在 uncertainty 中注明。

### 2.5 年份解析

接受整数或字符串；从字符串中提取第一个 3–4 位数字作为年份。合理区间为
`[1450, 当前年+1]`（1450 为印刷术时代下限，+1 容纳提前在线出版）。
无法解析或越界 → V3 suspicious。year 缺失时跳过 V3 并在 checks_passed 中
注明 "V3(无年份，跳过)"，不得视为通过。

## 3. 语言与文献类型打标（V7）

- 语言：统计 title+abstract 中 CJK 字符与 ASCII 字母数，CJK 多 → `zh`，
  ASCII 字母多 → `en`，皆无 → `other`。
- 类型：显式 type 字段合法（article/review/conference）时直接采用；否则按
  venue 含 proceeding/conference/symposium/会议 → conference；题名含
  systematic review/meta-analysis/review/综述 → review；有 venue → article；
 否则 unknown。打标不改变核验状态，仅服务筛选与分层。
