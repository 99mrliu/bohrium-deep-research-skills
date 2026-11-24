# 字段级 provenance 与锚定规则

## 来源层（layer）词表

| layer | 含义 | 证据要求 |
|---|---|---|
| `pdf_text` | PDF 正文抽取（pdftotext 前 3 页） | evidence 为抽取文本中的逐字行（≤200 字符） |
| `pdf_info` | PDF 信息字典（/Title /Author 等） | evidence 为字典原文 |
| `sidecar` | 旁挂说明/元数据表（.md/.csv/.json/.bib） | evidence 含文件名与行/行号 |
| `filename` | 文件名解析 | evidence 为文件名片段 |
| `model_inference` | 模型综合判断 | 仍必须给原文逐字短引；lint 双向锚定 |

不存在第六种来源。任何字段给不出证据 ⇒ `"value": "unknown"`。

## 锚定判定（provenance_lint.py）

1. 空白归一化（小写、压缩空白）后的值是证据池子串 ⇒ `anchored:substring`。
2. 否则值的全部有效 token（字母数字、长度 ≥3）都在证据池中 ⇒ `anchored:tokens`
   （容忍 "Smith, J.; Lee, K." 这类重排）。
3. 都不满足 ⇒ 降级：`value → unknown`，原值记入 `conflicts.json`，
   `lint=downgraded:no_anchor`。
4. 附带的 evidence 短引自身锚不住 ⇒ 记 `evidence_unanchored`（不降级值，但进报告）。

证据池 = 该文件抽取文本（`work/extracted/<fid>.txt`）+ 文件名 + 命中该文件的
旁挂表行。**其他文件的内容不能作为本文件字段的证据。**

## 冲突处置

- 文件名 vs 正文 vs 旁挂表取值不一致：不做静默选择。两（三）值全部留档
  `conflicts.json`，选用值按 `pdf_text > pdf_info > sidecar > filename` 优先，
  并在 `rationale` 写明。
- 预印本年份 vs 正式版年份：以各自文件正文为准分别登记；版本组 canonical 取
  正式版（有 DOI/期刊标识者优先），证据不足 `canonical: null`。

## 命名降级阶梯（缺字段时）

`{authors}-{year}-{title}` 缺作者 → `UnknownAuthor`；缺年份 → `nd`；缺标题 →
`untitled`。三者全缺 → `unidentified-<fid>`。**不得**为了让文件名好看而编字段；
lint 同样锚定 new_name 的组成字段（来自 metadata 的已锚定值）。

## 去重与归档

- 仅 SHA-256 相同的字节级重复可 `archive_dup`（复制到 `_archive_dups/`，保留一份
  `keep`），**不删除任何文件**。
- 同题异版（预印本/正式版/SI/修订版）全部 `keep`，仅在 `version_relations` 登记
  typed relation 与 canonical。
