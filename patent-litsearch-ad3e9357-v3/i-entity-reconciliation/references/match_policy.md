# 匹配策略说明(Bands, Thresholds, and Why the Candidate Band Exists)

## 三档判定

每对通过 blocking 进入评分的实体对,按加权得分 `score` 与 policy JSON 中声明的阈值分档:

| 档 | 条件 | 语义 |
|---|---|---|
| `auto` | `score >= thresholds.high` 且无强制 flag | 可直接采用 |
| `candidate` | `thresholds.low <= score < thresholds.high`,或存在强制 flag | **歧义带**:必须列出全部备选 + 五维特征分解,交由人审,绝不静默合并 |
| `non_match` | `score < thresholds.low`,或从未共享任何 blocking 键 | 不匹配;对账行 counterpart 为 `null` |

强制 flag(`order_variant`、`suffix_conflict`)**无视分数**强制落入 candidate——这是安全阀:
语序变体与法域后缀冲突都可能是"看起来极像的不同实体"。

## 特征与权重

| 特征 | 含义 |
|---|---|
| `exact_norm` | 规范化串完全相等(相等时得分**饱和为 1.0**,见下) |
| `core_eq` | 剥离法律后缀后的核心串相等 |
| `core_containment` | 一侧核心 token 集为另一侧子集(如 "acme" ⊆ "acme research lab") |
| `token_jaccard` | 规范化 token 集合的 Jaccard 相似度 |
| `initial_surname` | 两侧均为 person 且(名首字母, 末 token)相同(如 "P. Nair" vs "Priya Nair") |

权重在 policy JSON 的 `weights` 中声明,脚本校验权重键必须属于上述五个特征名。
`exact_norm = 1.0` 时得分直接饱和为 1.0:规范化全等是最强信号,不应因 `initial_surname`
等不适用特征权重未命中而被稀释到 high 阈值以下;该规则在此显式声明,非隐藏行为。

示例 policy(`examples/fixtures/match_policy.json`):`high=0.9, low=0.2`,
权重 `exact 0.4 / core_eq 0.15 / containment 0.15 / jaccard 0.1 / initial_surname 0.2`。

## 为什么必须存在 candidate 档

著录实体消歧的错误代价高度不对称:**错误合并**(把不同实体当成同一实体)会污染整个
对账表且难以事后发现;**错误拆分**只是多一条待审记录。因此本技能在 auto 与 non_match
之间设置显式的歧义带:

1. `score` 落在 `[low, high)` 的实体对全部进入 candidate,连同**全部**备选(不止 top-1)
   与五维特征分解输出,便于人审一次看清证据;
2. 两类结构性风险(`order_variant`、`suffix_conflict`)即使分数可观也强制 candidate;
3. candidate 档在 ledger 行中置 `requires_review: true`,下游(result.json)必须在
   `uncertainty` 中如实保留,不得当作已确认事实;
4. 阈值的取值是**策略声明**而非客观真理:收紧(提高 high)会减少 auto、增加人审量;
   放宽则相反。selfcheck 通过"篡改 high=1.01 后 Acme 对降为 candidate"证明阈值确实
   来自 policy 文件而非硬编码。

## 调参指引

- 语料噪声大(OCR 质量差、缩写多)→ 提高 `high`、降低 `low`,扩大歧义带;
- 需要高吞吐粗对账 → 可降低 `high`,但 `order_variant`/`suffix_conflict` 强制规则仍然兜底;
- 修改权重后务必重跑 `scripts/selfcheck.py` 确认既有断言仍通过。
