# 取证规则（forensics rules）

本文件是 corpus-forensics-registry 的判据说明，与 `scripts/` 中的常量一一对应。
原则：**只报告证据，不臆断**——所有判定必须能由注册表中的数值证据复核。

## 1. 文档身份鉴定（identity verdict）

- **规范化文本**：NFKC → 小写 → 非字母数字字符（保留 CJK）替换为空格 → 折叠空白。
- **fingerprint** = sha256(规范化全文)。两份文档 fingerprint 相同 → `exact_duplicate`。
- **shingle**：规范化 token 序列的 8-gram 集合（全文不足 8 token 时退化为单一 shingle）。
- 逐篇与已接受的 canonical 文档比较 shingle Jaccard `J` 与标题 token Jaccard `TS`：

| 条件 | verdict |
|---|---|
| fingerprint 相同 | `exact_duplicate` |
| `J ≥ 0.70` | `near_duplicate` |
| `0.20 ≤ J < 0.70` 且 `TS ≥ 0.50` | `probable_version_pair`（同一论文的不同版本） |
| 其他 | `unique`（进入 canonical 集合） |
| 文档不可读 | `undetermined`（诚实标注，不猜） |

- 只有 `unique` 文档是**规范文档**，下游比较只能以规范文档为单位；
  重复/版本文档保留记录（含 related_to、J、TS 证据）但不得进入矩阵。
- 版本对中内容冲突的数值（如示例 DOC-A vs DOC-C 的速率常数）**保留冲突、不得合并**；
  引用以处理顺序上的首个版本为规范版本，并在 uncertainty 中说明存在其他版本。

## 2. 解析保真（parse_fidelity）

PDF 用 `pdftotext <pdf> -` 提取，并运行 `pdftotext -layout` 交叉比对；
`difflib.SequenceMatcher` 作用于折叠空白后的两种提取文本，`layout_diff_rate = 1 - ratio`。

| 信号 | 阈值 |
|---|---|
| 提取总字符数 < 100，或 pdftotext 非零退出/异常 | `failed` |
| `pdftotext` 不在 PATH | `tool_missing` |
| 替换字符 U+FFFD(�) 占比 > 0.005 | `degraded` |
| `layout_diff_rate > 0.30` | `degraded` |
| 空页（\f 分页后字符 < 20 的页）比例 > 0.30 | `degraded` |
| 其余 | `good` |

- `failed` / `tool_missing` 的文档**不得抽取**，在 result.json 中记 `unreadable`。
- `degraded` 文档可抽取，但每个单元格的 uncertainty 必须注明解析降级。
- 备用路径：pdftotext 失败时可 `pdftoppm` 渲染 + OCR；OCR 文本一律记 `degraded` 并注明来源。
- 纯文本 / markdown / jsonl 语料直接锚定，不做 layout 比对。

## 3. 段落锚定

- 空行切分段落；`paragraph_id = <DOCID>-P<三位序号>`。
- `content_hash = sha256(规范化段落文本)[:12]`。
- `.jsonl` 语料若自带 `paragraph_id` 字段则沿用原 id，仍另算 content_hash。
- 所有下游引用必须同时给出 `paragraph_id` 与 `content_hash`；机检重算 hash，
  不一致即视为语料被换版或锚点伪造。

## 4. 相关性门控（relevance gate）

- 维度词来源：递归提取 comparison-workorder.json 中的字符串
  （跳过 case_id / 路径 / URL / output_contract 类键；过滤编号与路径形态的字符串）
  + 内置常见维度词表（光催化/环境化学高频词）。
- 归一化后做**词边界匹配**（避免 "mb" 误命中 "number"）。
- `score` = 命中的 distinct 维度词数；`score ≥ 2` → `in_scope`，否则 `out_of_scope`。
- `out_of_scope` 文档保留记录（含命中词证据）但不进入矩阵；机检 R4 强制拦截。
- 工单缺失时全部记 `in_scope` 并注明 `no_workorder`。

## 5. 单元格机检规则（verify_anchors.py）

R0 status ∈ {reported, not_reported, unclear, conflict}；
R1 文档在注册表中；R2 不得引用非规范文档；R3 不得引用解析失败文档；
R4 不得引用 out_of_scope 文档；R5 段落已注册；R6 content_hash 一致；
R7 quote 逐字出现于所引段落；R8 reported 格 value 非空且其中数字出现于 quote；
R9 not_reported 格不得携带 value。

## 6. 取证伦理

- 不得编造任何取值、段落或 hash；解析失败就如实标注。
- 相似度判定是**证据而非结论**：报告 J/TS/指纹，让人与下游可以复核。
- 重复与版本文档不删除、不修改，只标记；冲突数据原样保留。
- 本 bundle 的 examples/ 全部为合成示例，不包含任何官方正式案例的答案。
