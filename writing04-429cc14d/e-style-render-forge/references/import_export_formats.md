# 导入/导出格式与保真承诺（style-render-forge）

## 1. records.json 字段级格式（schema: style-render-forge/records/v1）

顶层：

| 键 | 说明 |
| --- | --- |
| `schema` | 固定 `style-render-forge/records/v1` |
| `generator` | 生成器标识 |
| `record_count` | 记录数 |
| `warnings` | 文件级警告（重复键、风味判定、格式跳过等） |
| `meta` | 各来源元数据（@string 逐字、注释、@preamble、RIS 风味等） |
| `records` | 记录数组，按 `id` 字典序排列（确定性） |

记录字段（JSON 键序固定）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | BibTeX citation key / RIS 顺序号或 ID 标签 / CNKI 文本顺序号 |
| `type` | string | journal-article / book / inproceedings / incollection / thesis / report / newspaper / electronic / misc |
| `authors` | list | 作者**原样**列表（导入不改写姓名形式） |
| `editors` | list | 编者原样列表 |
| `title` / `title_alt` | string/null | 题名 / 其他题名信息（双语题名都保留） |
| `year` | string/null | 4 位年份字符串（源值异常时保留原样并警告） |
| `venue` | string/null | 刊名 / 文集题名 / 来源 |
| `volume` / `issue` | string/null | 卷 / 期 |
| `pages` | string/null | 页码或页码范围（`-` 或 `–`） |
| `article_number` | string/null | 文章号（无页码期刊） |
| `publisher` | string/null | 出版者；学位论文为培养单位（BibTeX `school`、RIS `PB`） |
| `address` | string/null | 出版地 / 地点 |
| `doi` / `url` / `isbn` | string/null | 标识符，原样保留 |
| `language` | string | zh / en / mixed / unknown（粗判，只影响模板选择） |
| `type_tag` | string/null | GB/T 类型标识（J/M/C/A/D/R/N/EB/OL） |
| `raw_source` | string | 该条目在来源文件中的**逐字原文** |
| `unmapped_fields` | object | 未映射标签/字段，verbatim 保留，**绝不丢弃** |
| `warnings` | list | 条目级解析警告（未解析宏、未映射标签、类型默认等） |
| `raw_fields` | object（仅 BibTeX） | 每个字段的 raw 值表达式（如 `"journal": "jscis"`） |

缺失字段一律为 `null`（或空列表/空对象），**不存在"自动编造字段"路径**。

## 2. 来源格式映射表

### 2.1 BibTeX

| BibTeX | records.json |
| --- | --- |
| `article/book/inproceedings/conference/incollection/inbook/phdthesis/mastersthesis/techreport/online/unpublished/misc` | journal-article / book / inproceedings / incollection / thesis / report / electronic / misc（未知类型 → misc + 警告） |
| `author` / `editor` | `authors` / `editors`（按 ` and ` 切分，原样） |
| `title` | `title` |
| `journal` / `journaltitle` / `booktitle` | `venue` |
| `year` / `date`（取首个 4 位） | `year` |
| `volume` / `number` / `issue` | `volume` / `issue` |
| `pages` / `eid` | `pages` / `article_number` |
| `doi` / `url` / `isbn` | `doi` / `url` / `isbn` |
| `publisher` / `school` / `institution` | `publisher` |
| `address` / `location` | `address` |
| 其余（`note`、`abstract`、`keywords`、`issn` …） | `unmapped_fields` + 警告 |

`@string` 宏：读取时解析进 resolved；raw 表达式存 `raw_fields`；宏表、注释、
`@preamble` 逐字存 `meta`。未定义宏：resolved 即宏名本身 + 警告（保留原样不
手改）。`#` 连接：逐段解析后拼接。保护花括号：纯文本目标下去除（文档化行为）。

### 2.2 RIS（含 CNKI RefWorks 风味）

| RIS | records.json |
| --- | --- |
| `TY`: JOUR/BOOK/THES/CONF/CHAP/ELEC/RPRT/NEWS/GEN | 对应 `type` 与 `type_tag`（未知 TY → misc + 警告） |
| `TI`/`T1` | `title` |
| `T2`/`JO`/`JF` | `venue` |
| `AU`/`A1`、`ED`/`A2` | `authors`、`editors`（多行累加） |
| `PY`/`Y1`（取首个 4 位） | `year` |
| `VL`/`IS` | `volume`/`issue` |
| `SP`/`EP` | 合并为 `pages`（`SP-EP`，单页合法） |
| `M1` | `article_number` |
| `M3` | `type_tag`（本 skill 导出时写入 GB/T 标识） |
| `T3`/`X1` | `title_alt` |
| `DO`/`UR`/`PB`/`CY`/`SN`/`LA` | `doi`/`url`/`publisher`/`address`/`isbn`/`language` |
| `ID` | 往返时还原记录 `id`（见 §3） |
| 其余（`AB`、`KW`、`K1`、`N1` …） | `unmapped_fields` + 警告，verbatim |

风味判定：命中 `A1/Y1/JF/K1/LA` 提示标签 ≥2 个判为 `cnki-refworks`，否则
`standard-ris`；判定只写入报告与 meta，不改变映射。续行（非标签格式行）并入
上一标签值。`#` 开头行视为注释跳过。

### 2.3 CNKI 文本导出（`键: 值` 行式，空行分记录）

| 键 | records.json |
| --- | --- |
| 题名/标题 | `title` |
| 作者（`;`/`；`/`,`/`，`、`、` 切分） | `authors` |
| 来源/刊名 | `venue` |
| 年/发表时间（取首个 4 位） | `year` |
| 卷/期/页码/页数 | `volume`/`issue`/`pages` |
| DOI / 链接、URL / 出版社 / 出版地 | `doi` / `url` / `publisher` / `address` |
| 其余（关键词、摘要、作者单位…） | `unmapped_fields` + 警告 |

该格式不携带文献类型：一律默认 `journal-article` + `[J]` 并挂警告，人工按实际
情况修正。

## 3. 往返规程（import → export → import）

**官方往返载体：RIS 或 CSL-JSON。** 步骤：

```
style_render.py --records records.json --style ris --out roundtrip.ris
import_records.py --file roundtrip.ris --out rt
field_lint.py --records records.json --roundtrip rt/records.json --out rt
```

L8 对以下字段做**字段级 diff**：`id, type, authors, editors, title, title_alt,
year, venue, volume, issue, pages, article_number, publisher, address, doi, url,
isbn, language, type_tag`。要求：**diff 为零，或每一条都可解释**。

保真承诺：

- RIS 导出写入 `ID`（原 id）、`M3`（类型标识）、`LA`（语言）、`M1`（文章号），
  使核心字段逐字节还原；示例库实测 L8 diff 为零（见 examples/output/roundtrip/）。
- 未映射字段：两位大写标签（如 CNKI `K1`）在 RIS 导出中原样写回；非两位标签
  （如 BibTeX `note`）在 BibTeX 导出中写回；跨载体无法表达的未映射字段保留在
  records.json 内，不冒充已导出。
- **已知例外（可解释的 diff）**：BibTeX 往返不承诺 `id` 逐字还原——citation
  key 字符集不含 `#` 等字符（如重复键后缀 `dup1#dup2` 导出时改写为
  `dup1_dup2`）；其余核心字段不受影响。需要 id 级往返时请走 RIS/CSL-JSON。

## 4. 确定性承诺

- 记录排序固定（按 `id` 字典序）；JSON 键序固定；无随机数、无时间戳、无网络。
- 同一输入多次运行，`records.json` / 渲染文本 / 报告逐字节一致（示例库已实测
  `diff` 为空）。
- 合并多个来源文件时，跨文件 id 冲突加 `~N` 后缀并警告；同一 BibTeX 文件内
  重复 citation key 加 `#dupN` 后缀并警告——双保留，不覆盖、不静默去重。
