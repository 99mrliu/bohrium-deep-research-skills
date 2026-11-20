# 命中判定规范（match_rules）

本文件为三级命中判定的完整口径，权威实现为 `scripts/adjudicate.py`。任何覆盖率数字必须
可由该口径从命中矩阵独立复算。

## 0. 总则

- 判定单元为「参考集条目 × 检索记录中的查询（query_id × source × executed_at）」。
- 每个单元取结果文件中与该参考条目匹配度最高的一条候选记录，输出
  `{status, match_level, score, rank_in_results, evidence}`。
- `status ∈ {hit, ambiguous, miss}`；`ambiguous` 一律不计入命中。
- 判定只读取本地响应/索引文件，不联网，不依据文件名臆断。

## 1. 归一化函数

| 对象 | 规则 |
| --- | --- |
| DOI | 小写化；去除 `https://doi.org/`、`http://dx.doi.org/`、`doi:` 等前缀；去首尾空白与末尾句点 |
| PMID | 仅保留数字串 |
| arXiv | 去除 `arXiv:` 前缀；小写化；去除版本后缀 `vN`（`1706.03762v3` → `1706.03762`） |
| 标题 token | 小写化；NFKD 分解去重音；非标点字母数字以外字符替换为空白；按空白切分；取集合 |
| 作者姓氏 | 支持 `Zhang, Wei` 与 `Wei Zhang`；取逗号前段或末段；小写、去重音、仅保留字母 |
| 年份 | 从 `year/published_year/pubyear/published/date/issued` 中提取首个四位数 |

token F1 定义：`F1 = 2·|A∩B| / (|A|+|B|)`，其中 A、B 为两侧标题的 token 集合；
任一侧为空则 F1 = 0。

## 2. L1 标识符精确命中

归一化 DOI、PMID、arXiv 三者任一相等 → `hit`，`match_level=L1`，`score=1.0`。

例外（标识符冲突）：标识符相等但两侧标题 token F1 < 0.3（且两侧标题均非空）→ 不判 L1，
转入 L3，原因记 `identifier_conflict`。该规则防止「DOI 错挂」造成假命中。

## 3. L2 题录近似命中

同时满足：

1. 标题 token F1 ≥ 0.6；
2. 第一作者姓氏归一化后相等；
3. 年份差 ≤ ±1。

满足 → `hit`，`match_level=L2`，`score` 记录实际 F1（不是 1.0），`evidence` 记录
`f1 值、姓氏、年份核验通过`。技能严禁在不记录分数的情况下放行 L2。

年份缺失（任一侧无法提取）→ 无法核验条件 3，即使 F1 ≥ 0.6 且姓氏相等也转入 L3，
原因记 `year_unverifiable`。

## 4. L3 裁决队列

进入队列的三类情形：

| 情形 | 触发条件 | reason |
| --- | --- | --- |
| 临界近似 | 0.5 ≤ F1 < 0.6，且姓氏相等，且年份差 ≤ 1 | `borderline_f1` |
| 标识符冲突 | 标识符相等但标题 F1 < 0.3 | `identifier_conflict` |
| 年份不可核验 | F1 ≥ 0.6 且姓氏相等但年份缺失 | `year_unverifiable` |

队列条目含 `queue_key = ref_id::query_id|source|executed_at`、双方标题、分数、位次与原因。
裁决方式：由 Agent（或人）逐条给出 `accept`/`reject`，写入 decisions 文件后以
`adjudicate.py --decisions` 回灌；`accept` 计命中（`match_level` 后缀 `(adjudicated)`），
`reject` 计漏检，未裁决保持 `ambiguous`。

## 5. 算例（合成示例，仅说明口径）

| # | 参考条目 | 候选记录 | 判定 | 说明 |
| --- | --- | --- | --- | --- |
| 1 | doi `10.1234/ABC.2021.001` | `https://doi.org/10.1234/abc.2021.001` | L1 hit | 归一化后相等 |
| 2 | 标题 "Deep learning for symbolic mathematics"，作者 "Lample, G."，2019 | "Deep Learning for Symbolic Mathematics"，"Guillaume Lample"，2020 | L2 hit | F1=1.0，姓氏相等，年份差 1 |
| 3 | "Attention is all you need"，"Vaswani"，2017 | "Attention is all you require for efficient vision transformers"，"Vaswani"，2017 | L3 | F1≈0.571 ∈ [0.5,0.6)，须裁决 |
| 4 | doi `10.9999/x1`，标题 "Graph kernels" | doi `10.9999/x1`，标题 "Protein folding survey" | L3 | 标识符相等但标题 F1=0，冲突 |
| 5 | "Neural machine translation of rare words"，"Luong"，2015 | 标题相似 F1=0.72，"Luong"，无年份字段 | L3 | 年份不可核验 |
| 6 | 任意 | 无候选 | miss | 进入漏检归因流程 |

## 6. 与覆盖率的接口

- 单元判定完成后由 `hit_matrix.py` 汇总：参考条目在任一单元 `status=hit` 即计为命中。
- 分母＝冻结参考集中 `usable=true` 的条目数；撤稿、重复、题录缺失的剔除清单随
  `coverage.json` 一并公布，禁止以检索结果反向构造分母。
