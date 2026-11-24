# Source Schemas（各来源的信封与条目期望）

门控按以下期望做**格式嗅探 → 分类 → 模式认证**。分类只依据内容形状，不依赖文件名。

## 1. crossref（Crossref REST 响应）

- 识别：JSON 对象，`message` 为对象且 `message.items` 为列表；正常时 `status == "ok"`。
- 信封检查：`message` 存在且为对象；`message.items` 为列表；`status` 为 `"ok"`（否则 `ENVELOPE_STATUS_NOT_OK`）。
- 截断检查：`message.total-results`（整数）> 实际 `items` 长度 → `COUNT_MISMATCH`。
- 条目必填：`DOI`（字符串）、`title`（列表或字符串）、`issued`（对象，`date-parts` 可提取年份）。
- 条目定位符（locator）：`message.items[i]`。
- 标识符抽取：`DOI`（规范化：小写、去 `https://doi.org/`、`doi:` 前缀）。
- 摘要：`abstract` 字段若含 HTML 标签 → `HTML_RESIDUE`（剥离供检查，原始保留）。

## 2. europepmc（Europe PMC 响应）

- 识别：JSON 对象，含 `resultList` 或 `hitCount`。
- 信封检查：结果列表取自 `resultList.result`（兼容顶层 `result`）。
- 截断检查：`hitCount` ≠ 结果列表长度 → `COUNT_MISMATCH`。
- 条目必填：`id`、`source`、`title`。
- 条目定位符：`resultList.result[i]`。
- 标识符抽取：`id`、`pmid`、`pmcid`、`doi`（同规范规则）。
- 摘要：`abstractText` 同样做 `HTML_RESIDUE` 检查。

## 3. publisher（出版商记录）

三种可接受形态：

1. **JSON 数组**：元素为记录对象，必填 `doi` 或 `title` 至少其一；定位符 `[i]`。
2. **JSONL**：逐行 JSON 对象（整文件解析失败后按行尝试）；定位符 `line[i]`。
3. **HTML 片段**：含 `<div>/<article>/<meta>` 等标签或 `<!doctype` 开头；不做结构核验，
   仅抽取 DOI 级标识符（`10.\d{4,9}/...` 正则），定位符 `html_body.doi_match[i]`，记 `HTML_FORMAT_LIMITED`。

- 载荷内重复 DOI → `DUPLICATE_IDENTIFIER`。
- `abstract` 字段做 `HTML_RESIDUE` 检查；`year` 类型异常记 `FIELD_TYPE_MISMATCH`。

## 4. reference_graph（保留引用图）

- 识别：JSON 对象，含 `nodes` 或 `edges` 列表。
- 节点：期望 `id`（或 `identifier`）；节点的 `doi`/`pmid` 亦并入标识符宇宙。
- 边：期望 `{"from": ..., "to": ...}`（兼容二元数组）。
- 一致性：每条边的两个端点都应在**任一材料**的标识符宇宙中可解析；
  不可解析 → `DANGLING_EDGE`（报告，不致命）。
- 该类型不产出文献记录（`record_count` 记为边数，仅供审计）。

## 5. import_state（组织方本地增量导入状态）

- 识别：JSON 对象，含 `records`/`imported` 列表（条目含 `db` + `identifier`），
  或 `{"db": "...", "identifiers": [...]}` 形态。
- 逐条核验：条目声称 "imported from db X id Y"：
  - 案例中**不存在** db X 的源工件 → `IMPORT_NOT_VERIFIABLE`（声明缺口，not_verifiable）；
  - 源工件存在但 **id Y 不在其标识符集合中** → `IMPORT_INCONSISTENT`（该条目隔离）；
  - 否则记 `verified`。
- db 名规范化：小写并去除非字母数字字符（`Europe PMC` ≡ `europepmc`）。

## 6. unknown（无法分类）

- 任何不满足上述形状、或完全不可解析的工件 → `classification = "unknown"`，
  判 `quarantined`，但**完整记录在台账**（sha256、大小、编码探针、原因码），绝不沉默丢弃。

## 标识符规范化规则（跨工件一致性共用）

`normalize_identifier(v)`：去首尾空白 → 小写比较 → 剥离 `https://doi.org/`、`http://doi.org/`、
`https://dx.doi.org/`、`http://dx.doi.org/`、`doi:` 前缀。因此
`10.x/y`、`DOI:10.x/y`、`https://doi.org/10.X/Y` 视为同一标识符。
