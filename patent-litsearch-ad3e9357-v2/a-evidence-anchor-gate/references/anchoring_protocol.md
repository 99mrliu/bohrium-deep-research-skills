# 逐字引用锚定协议（Anchoring Protocol）

本协议定义 `verbatim-anchor-evidence-gate` 技能中"什么必须被锚定、锚点如何书写、
审计如何归一化"的全部规则。审计器为 `scripts/quote_audit.py`，裁决是确定性的。

## 1. 必须锚定的内容

凡写入 `result.json` 的**字段级事实**，一律要求逐字引用锚点，包括但不限于：

- 专利著录项目：公开号、申请号、申请日、公开日、优先权日、申请人、发明人、
  代理人、IPC/CPC 分类号；
- 专利族与法律状态：同族成员号、法律状态文本、审查历史事件；
- 论文题录：题名、作者、期刊/会议、卷期页、DOI、收稿日期；
- 任何从材料中抽取的技术性结论或数值（性能数字、参数、对比结论）。

不要求锚定的内容：`case_id`（复制自 case.json）、`status`、`change_records`、
`uncertainty` 中的过程性说明、以及明确标注为"未找到/不适用"的 null 占位。

## 2. 锚点格式

一个锚点是包含以下字段的 JSON 对象，可出现在 `evidence_records[]`，也可嵌套在
`candidates[]`、`extracted_fields[]` 等任意层级（审计器递归收集所有同时含
`quote` 与 `source_sha256`/`source_path` 的对象）：

```json
{
  "field": "candidates[0].publication_number",
  "quote": "公开号：US0000000EX1",
  "source_path": "/input/src_patent_EX1001.txt",
  "source_sha256": "<登记表中的 sha256>",
  "tolerance_used": false
}
```

定位器（locator）两种形态：

- **file:sha256（必选）**：`source_sha256` 必须等于 `source_register.py` 登记表中
  某条目的 sha256；这是文件身份的权威标识。
- **file:path（强烈建议）**：`source_path` 的 basename 必须与该 sha256 对应登记条目的
  路径一致；不一致即判失败（防止张冠李戴）。
- 可选扩展：建议在锚点中附带 `file:line` 形式的行号提示（如 `"line_hint": 12`），
  便于人工复核；审计器不强校验行号。

## 3. 归一化规则

审计比对前，对 quote 与源文本施加**唯一**归一化：

```
normalized = re.sub(r"\s+", " ", text).strip()
```

即：连续空白（空格、制表符、换行、全角空格以外的 Unicode 空白）折叠为一个半角空格，
去除首尾空白。除此之外不做任何处理——不做大小写折叠、不做全半角转换、不去标点。

因此跨行摘录天然安全（换行被折叠），但**任何字符级的改写、补全、翻译、标点替换
都会使精确匹配失败**。

## 4. 判定规则

1. `source_sha256` 缺失或不在登记表 → FAIL（missing file hash）；
2. `source_path` basename 与 sha256 对应条目不一致 → FAIL（path/hash 不匹配）；
3. 归一化后 quote 是源文本精确子串 → PASS；
4. 否则进入容差判定（见 `tolerance_declaration.md`）；无双重声明 → FAIL；
5. 登记条目无可用文本（如 PDF 未抽取）→ FAIL（无法核验，宁可退回）。

任何 FAIL 都会打印锚点 JSON 路径（如 `$.evidence_records[0]`）与原因，审计 exit 1。
全部通过打印汇总，exit 0。

## 5. 写作纪律

- **先复制，后引用**：quote 必须是从源文本中复制出来的片段，而不是对字段值的重述；
  推荐的顺序是"定位源文 → 复制片段为 quote → 再从 quote 中提取字段值"。
- 一条 quote 只锚定一个字段声明；不要把整页文本塞进一个 quote。
- 找不到逐字出处的字段：留 `null` 并写入 `uncertainty`，status 保持 `partial`。
