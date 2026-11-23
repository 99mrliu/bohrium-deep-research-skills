# 证据锚点与引文规范

## 1. 定位语法

所有证据必须写成：

```text
<文件名>#<锚点ID>
```

`文件名` 是 `source_index.json` 中的原始文件名，不写目录。`锚点ID` 由索引器稳定分配：

- PDF：`docN.p页码`，例如 `paper.pdf#doc1.p3`；兼容 `paper.pdf#p3`、`paper.pdf#p.3`。
- txt/md：`docN.para段落号`，例如 `source.txt#doc1.para7`；兼容 `source.txt#para7`。
- JSON：`docN.record记录号`，例如 `table.json#doc1.record2`。

锚点只对同一次 `source_index.json` 有效。材料、文件名或索引器修复抽取缺陷后，必须重建索引并复跑 `quote_gate.py`。

## 2. 引文规则

1. `quote` 必须是源文本中的连续片段，逐字复制，不得概括、翻译或补词。
2. 引文应足够短而完整；表格行可以整行复制。
3. 一个论断引用多个不连续片段时，拆成多条 `evidence`，不要把不连续文本拼接成一条。
4. 机器只做归一化后的逐字匹配，不做语义等价判断；同义改写不会被接受。

## 3. 归一化规则

索引器对原文和引文执行同一算法：

1. Unicode NFKC，全角/半角及兼容字符统一；
2. `ﬁ/ﬂ/ﬃ/ﬄ/ﬀ` 等连字还原为普通字母；
3. 行尾断词 `hyphen-\nation` 接回为 `hyphenation`；
4. 连续空白折叠为一个 ASCII 空格，去除首尾空白；
5. 保留归一化字符到原文字节解码后偏移的 `offset_map`，因此命中后可报告原文 span。

归一化只处理排版差异，不修复错字，也不允许改写引文。

## 4. 示例

```json
{
  "locator": "source_excerpt.txt#doc1.para1",
  "quote": "在 500 °C 下，催化剂 A 的产率为 82%"
}
```

机器将先在该锚点的 `normalized_text` 中查找；找不到会再查全库。仅在别处命中判 `fail`（锚点漂移），全库不命中判 `fail` 或（存在明确抽取缺陷时）`degraded`。