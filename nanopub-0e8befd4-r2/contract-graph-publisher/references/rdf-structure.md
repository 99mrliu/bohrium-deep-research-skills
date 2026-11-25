# Nanopublication 四图结构与合格断言

## 1. 一个 case 的四个 named graphs

每个 RDF 请求把一个 case 生成为一个本地 nanopublication，TriG 与 JSON-LD 都必须恰好具有四个不同图名：Head、assertion、provenance、pubinfo。图名和 publication IRI 是由原 `case_id` 百分号编码得到的本地 URN，不能解释为可解析注册地址。

### Head

Head 只承担 nanopublication 身份与三部分连接：publication 的类型为 `np:Nanopublication`，并恰好各有以下一条链接：

- `np:hasAssertion → assertion graph`；
- `np:hasProvenance → provenance graph`；
- `np:hasPublicationInfo → pubinfo graph`。

三部分不能合并到一个 unnamed JSON 数组或默认图；TriG 使用 `<graphIRI> { ... }`，JSON-LD 使用顶层 `{"@graph": [{"@id": graphIRI, "@graph": [...]}, ...]}` 的展开 named-graph 形式。

### Assertion：reify 而非无条件泄漏

每个 claim 以独立 statement IRI 表示，并具有：

- `rdf:type rdf:Statement`；
- `rdf:subject`、`rdf:predicate`、`rdf:object`；
- 本地 vocab 的 `claimId`、`polarity`、布尔 `hedged`；
- 输入存在时保留 `condition`、`hedge`、`uncertainty` 字面量。

工具对正断言也统一 reify，以避免下游误把未限定三元组当作无条件事实。对负、条件或 hedged claim，必须不存在任何图中的直接 `(original subject, original predicate, original object)` 三元组。`rdf:subject/predicate/object` 是 reification 的组成描述，不等于原命题被无条件肯定。输出 JSON 仍保留原 claim 结构及限定字段。

### Provenance：显式引用 assertion

provenance 图含 `provenanceGraph cgp:describesAssertion assertionGraph`，并让每条 statement 通过 `prov:wasDerivedFrom` 指向其 evidence 节点。Evidence 节点保留 evidence_id，按 `source_ids` 连接 source 节点；输入提供 evidence 文本、source title 或 locator 时也在此图保留。引用校验确保没有伪造或不存在的 ID。

### Pubinfo：显式引用 publication，元数据不猜

pubinfo 图含 `pubinfoGraph cgp:describesPublication publicationIRI`，并对 publication 明确记录：

- `cgp:iriStatus = "local-unregistered"`；
- `cgp:trustyStatus = "not-generated"`。

仅当 `manifest.publication` 明确给出 `creator_iri` 或 `license_iri`，才分别增加 `dcterms:creator` 或 `dcterms:license`；仅明确给出 `created` 字符串才生成 `dcterms:created` 的 xsd:dateTime typed literal。缺省时不补当前时间、不假定作者、不猜 CC license。其他未知 publication 元数据字段被拒绝。

这里 `cgp` 表示本地命名空间 `urn:contract-graph-publisher:vocabulary:`，`np` 为 `http://www.nanopub.org/nschema#`，`prov` 为 `http://www.w3.org/ns/prov#`，`dcterms` 为 `http://purl.org/dc/terms/`。实际 TriG 为减少前缀解析歧义全部写绝对 IRI。

## 2. 双格式一致性与自检

同一内部 quad 模型先分别渲染 TriG 和 JSON-LD，再从磁盘读取：

1. 严格 TriG 子集解析器识别四个图、IRI、字符串、language tag 和 datatype，并把 quad 与原模型比较；它不是通用 Turtle/TriG 解析器。
2. JSON-LD 解析回读仅接受生成器使用的展开 named-graph 子集，并把 `@type`、`@id`、typed/language literal 还原为 quad 比较。
3. 性能无关地检查四图数量、Head 三条 part links、Nanopublication 类型、每个 claim 唯一 reified statement、provenance→assertion、pubinfo→publication、本地非 Trusty 状态。
4. 对负/条件/hedged claim 扫描所有图，直接 S-P-O 泄漏数必须为 0。
5. `validation-report.json` 记录每图 quad 数、reified claim 数、回读状态和限制。

这些是具有真实回读的严格结构自检，不是外部注册、内容真实性证明、完整 W3C RDF 语法/语义验证或 Trusty URI 生成。详见 `review-boundaries.md`。
