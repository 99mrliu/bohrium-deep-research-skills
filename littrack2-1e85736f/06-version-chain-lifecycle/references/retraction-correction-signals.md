# 撤稿 / 勘误 / 版本关系信号清单

本清单是 `scripts/chain_link.py` 与 `scripts/lifecycle.py` 判定依据的对照表。
所有信号命中时都必须把 locator（文件名 + JSON 指针）写入证据。

## 1. Crossref `relation` 字段的 relation-type

快照中常见形态：`item.relation[] = {"id-type": "doi", "id": "...", "relation-type": "..."}`
（本 Skill 统一按小写连字符风格比较，抽取时做大小写归一）。

| relation-type | 语义 | 用途 |
| --- | --- | --- |
| `is-preprint-of` | 本记录是目标 DOI 的预印本 | 成链（R1） |
| `has-preprint` | 本记录有预印本 | 成链（R1） |
| `is-version-of` / `has-version` | 版本关系 | 成链（R1） |
| `is-retraction-of` | 本记录是目标 DOI 的撤稿声明 | 成链（R1）+ 撤稿信号 |
| `has-retraction` | 本记录已被撤稿，指向声明 | 成链（R1）+ 撤稿信号 |
| `is-correction-of` / `has-correction` | 勘误声明 / 被勘误 | 成链（R1）+ 勘误信号 |
| `is-expression-of-concern-of` / `has-expression-of-concern` | 关注声明 | 成链（R1）+ EoC 信号 |
| `is-supplement-to` / `has-supplement` | 补充材料 | **不**用于成链（非同一成果的版本） |

## 2. Crossref `update-to` / `update-policy`

`item.update-to[] = {"type": "retraction"|"correction"|"erratum"|..., "DOI": "..."}`
是出版商登记的更新标记：`type=retraction` 是强撤稿信号，`correction`/`erratum`
是勘误信号；按 DOI 把标记方与被标记方并入同一链（R2）。

## 3. arXiv 版本信号

- `id` 形如 `http://arxiv.org/abs/YYMM.NNNNNvK`：base id 相同、vK 不同 →
  同一链的不同版本（R3），最大版本号 > 1 且只有预印本时状态为 `revised`。
- `arxiv:comment` / 版本注释中出现 `retracted`、`withdrawn` → 撤稿信号
  （弱于 DOI 级信号，但同样要求 critical 预警）。
- arXiv 数据 DOI 约定 `10.48550/arXiv.YYMM.NNNNN`：用于与 Crossref
  `has-preprint`/`is-preprint-of` 关系对齐（R1 跨源成链的关键）。

## 4. Europe PMC / 出版商侧

- `pubType` 含 `retraction` → retraction-notice。
- Europe PMC 记录一般无 `relation` 字段时，退化为 R3/R4 后备链接。
- 出版商页面快照中若固化了 "Retracted" / "Expression of Concern" 标记字段，
  视同对应类型信号处理（本 bundle 示例未含此类快照）。

## 5. 信号强度与后备规则

1. DOI 级信号（relation / update-to）最强，直接成链并定状态。
2. arXiv 版本号信号次之，只在同源内成链。
3. 标题归一化 + 第一作者一致仅作后备（R4，confidence=low）：用于补齐
   缺关系字段的快照，但必须在证据中标注低置信，措辞上不得断言
   "确定为同一成果"。
4. 任何信号都不得静默使用：命中即落 locator 证据。
