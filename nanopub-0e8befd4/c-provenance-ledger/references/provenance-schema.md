# 来源记录 schema 与标识符优先级

## sources.json（mint_nanopubs.py 输入）

```json
[
  {"source_id": "paper-v1",
   "title": "<从材料读出的标题>",
   "creators": ["<作者1>", "<作者2>"],
   "year": 2013,
   "identifier": {"kind": "arxiv", "value": "1303.3997"},
   "version": "v2",
   "path": "/input/paper.pdf",
   "sha256": "<可选：声明值；脚本总会重算并比对>",
   "supersedes": "paper-v0"}
]
```

| 字段 | 必填 | 规则 |
|-|-|-|
| source_id | 是 | 本地唯一；同名不同文件用后缀区分（如 `-v2`、`-supp`） |
| title | 是 | 从材料读出；读不到写 "unavailable"，不猜 |
| creators | 建议 | 按材料署名顺序；不可得写 [] |
| year | 建议 | 材料标注的发表/提交年；不可得写 null |
| identifier | 建议 | 见下方优先级 |
| version | 建议 | 版本串或日期；无版本概念写 "unversioned" |
| path | 是 | 文件实际路径；脚本据此重算 sha256 |
| sha256 | 否 | 仅作声明值；与重算不一致 → E_SOURCE_MISMATCH |
| supersedes | 否 | 指向被本版本取代的 source_id，形成版本链 |

## 标识符优先级

1. DOI（`{"kind":"doi","value":"10.xxxx/..."}`）；
2. arXiv ID（含版本：`{"kind":"arxiv","value":"1303.3997v2"}`）；
3. 其他稳定标识（PMID、ISBN、数据集 accession）；
4. 都不可得：`{"kind":"title-hash","value":"th-<sha256(title)前12位>","derived":true}`，
   必须标 `derived:true`，**不得伪造 DOI/arXiv**。

## 断言侧绑定（claims JSONL 增加字段）

- `source_id`：该断言证据所在来源；多来源佐证时每个来源一条断言记录，
  落账时按语义键合并；
- `evidence.quote/location`：逐字引文与定位（由前置流程保证质量）。

## 输出语义

- `nanopubs.jsonl`：每行一条唯一断言；`sources[]` 是完整来源绑定链
  （来源身份 + 指纹 + 该来源下的证据）；
- `nanopubs.trig`：每条断言四个命名图；`provenance` 图含 `prov:wasDerivedFrom`
  指向来源节点，来源节点携带 title/identifier/sha256；
- `provenance-report.json`：指纹核验（ok/mismatch/file_missing/no_path）、
  合并日志、冲突项、版本对照；`summary.gate` 有任何 `E_SOURCE_*` 即 `fail`。

## 诚实性约定

- 内容寻址 URI（`https://nanopub.local/RA...`）是本地方案：未注册、非 Trusty URI、
  不保证跨环境可解析；对外发布前按任务要求替换命名空间或接入注册服务。
- `dcterms:created` 是运行时钟，不参与内容寻址哈希；重跑 URI 稳定，created 变化。
