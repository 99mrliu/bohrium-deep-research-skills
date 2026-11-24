# 稳定 dedup_key 规则（dedup-key-rules）

目标：同一篇文献无论来自哪个源、哪种标识形态、标题大小写/标点如何变化，
都得到**稳定、可复算**的去重键；且每次判定都能指出命中了哪条规则。

## 1. 标识规范化

### 1.1 DOI 规范化
按顺序执行：
1. `strip()` 去首尾空白；
2. 整体转小写；
3. 去前缀：`https://doi.org/`、`http://doi.org/`、`https://dx.doi.org/`、
   `http://dx.doi.org/`、`doi:`；
4. 去结尾句点（Crossref 偶发 `...12373.`）。

例：`10.1038/Nature12373` → `10.1038/nature12373`；
`https://doi.org/10.1038/nature12373` → `10.1038/nature12373`。

### 1.2 arXiv 号解析
- 接受 `arXiv:2506.01234v2`、`http(s)://arxiv.org/abs/2506.01234v2`、
  裸号 `2506.01234v2`、旧式 `hep-th/9901001v1`；
- 拆为 `(base, version)`：`2506.01234v2` → base=`2506.01234`，version=2；
- **判重只用 base（剥掉 vN）**，version 单独参与版本更新判定。

### 1.3 标题指纹
按顺序执行：
1. Unicode NFKD 分解；
2. 删除所有组合变音符号（category = Mn），如 `é` → `e`；
3. 转小写；
4. 所有非字母数字字符折叠为单个空白（Unicode aware，`str.isalnum()`）；
5. 压缩连续空白并去首尾空白。

例：`A SYNTHETIC STUDY ON LITHIUM MIGRATION IN SOLID ELECTROLYTES.`
与 `A synthetic study on lithium migration in solid electrolytes`
指纹相同 → `a synthetic study on lithium migration in solid electrolytes`。

## 2. dedup_key 优先级链

对单条题录，取第一个可用标识：

| 优先级 | 条件 | 键形态 | 规则号 |
|---|---|---|---|
| 1 | 有规范化 DOI | `doi:<normalized>` | K1-doi |
| 2 | 有 arXiv base | `arxiv:<base>`（无版本号） | K2-arxiv |
| 3 | 有标题指纹 | `title:<fingerprint>` | K3-title |

一条文献在注册表中的 `dedup_key` 以**首次见到时**的链式结果为准并保持稳定；
后续轮次只向其合并新标识（例如预印本条目后来补到 DOI），不回溯改写键。

## 3. 增量判定规则（按优先级短路）

| 规则号 | 条件 | 判定 |
|---|---|---|
| R1-exact-doi | 规范化 DOI 已注册 | duplicate |
| R1-exact-arxiv | arXiv base 已注册且版本号不更高 | duplicate |
| R2-arxiv-version | arXiv base 已注册且新版本号 > 已知最大版本号 | version_update |
| R3-preprint-published-link | 关系字段（如 Crossref `relation.has-preprint`）中的 arXiv/DOI 已注册 | version_update（预印本→正式版） |
| R4-title-fingerprint | 标题指纹已注册 | duplicate |
| R0-new | 以上均未命中 | new |
| RX-out-of-window | 题录日期不在 `[window_start, window_end)` | skipped |
| RX-no-date | 日期无法解析 | skipped |

注意 R3 排在 R4 之前：当正式版 DOI 与已知预印本同时满足“关系链接”与
“标题相同”时，优先记为版本链更新而非普通重复。

## 4. 已知局限（须写入 uncertainty）

- 标题指纹对极短标题（如单单词）或完全不同措辞的同文重复可能误判；
- 同一实体的多个注册表条目不做并查集合并（merge 只补充标识），极端情况
  下同一文献可能残留两个键——回放结果仍逐字节一致，但清单可能多列；
- Crossref 日期粒度为日级、arXiv 为秒级，统一规范化为 UTC 秒级后比较。
