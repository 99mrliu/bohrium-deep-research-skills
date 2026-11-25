# 排序稳定性方法说明（permutation-stability-ranker）

本文件是 `scripts/stability_engine.py` 的方法学依据。所有评分确定、可解释、可手工复算；任何定义同时写在 `features.json` 的 `meta.feature_definitions` 中，保证"看到的分数"与"文档中的定义"一致。

## 1. 特征定义

词元化：小写后按 `[a-z0-9]+` 或单个 CJK 字切分，去除一小组英文停用词（清单在 meta.tokenization）。记 Q = tokens(research_question) ∪ tokens(queries)。

| 特征 | 定义 | 取值 |
|---|---|---|
| `title_overlap` | \|Q ∩ tokens(title)\| / \|Q\| | [0,1]；Q 为空则 null |
| `abstract_overlap` | \|Q ∩ tokens(abstract)\| / \|Q\| | [0,1]；无摘要则 null |
| `year_in_scope` | 记录年份落在 retrieval_scope 可解析年份区间内为 1.0，区间外 0.0 | {0,1}；年份或范围不可解析则 null |
| `has_abstract` | 摘要非空 | {0,1} |
| `has_doi` | DOI 非空 | {0,1} |
| `venue_tier` | **启发式（heuristic:true）**：venue 字符串含 preprint 标记（arxiv/biorxiv/medrxiv/ssrn/preprint 等）→ 0.3；含期刊型标记（journal/proceedings/letters/review/transactions 等）→ 1.0；其余 0.7 | {0.3,0.7,1.0}；无 venue 则 null |
| `recency_norm` | (year − min_year) / (max_year − min_year)，在候选池内归一 | [0,1]；无年份 null；全部同年则全体 0.5 |
| `semantic_score` | 可选：judgments 文件给出的逐条语义相关分（正式运行时一次批量模型调用产出；>1 的值按 0–100 刻度除以 100，截断到 [0,1]） | [0,1]；无 judgments 则整特征跳过 |

**中性插补**：null 特征值按 `权重 × 0.5` 计入（0.5 为特征值域中点），保证缺元数据的记录不被丢弃也不被隐性惩罚，且行为有据可查。

## 2. 评分与权重依据

基准分 = Σ w_i·v_i / Σ w_i（对实际使用的特征归一，因此分数 ∈ [0,1] 且对权重整体缩放不变）。weights.json 中声明但所有记录都缺失的特征整列跳过。

示例权重（`examples/minimal/weights.example.json`）的依据：

- `title_overlap`(0.35)、`abstract_overlap`(0.30) 最高：标题是最刻意的相关性信号，摘要次之但更噪。
- `venue_tier`(0.10)、`recency_norm`(0.10) 中等：有用但分别是启发式和弱代理，不应主导。
- `year_in_scope`/`has_abstract`/`has_doi`(各 0.05)：硬约束与元数据完整性的小幅奖惩。
- `semantic_score`（示例 0.15）：可选；注入后它只是一个普通加权特征，同样参与抖动。

## 3. 扰动设计

排序可信的操作化定义：**在合理地不确定的建模选择下，结论不应改变**。两类最普通的不确定来源：

1. **候选输入顺序**：导出工具的排序是偶然的。每次运行用播种生成器重洗输入顺序；基准排序的平分打破规则是 record_id 升序，而扰动运行故意用**当次输入顺序**打破平分——于是输入顺序敏感性（若存在）会被直接测出，而非被假设掉。
2. **特征权重**：权重是判断，不是测量。每次运行把每个权重独立乘以 1 + U(−0.10, +0.10)。±10% 是"同一判断的合理重估"量级：大到足以暴露近平分记录的次序翻转，小到不推翻权重族本身。

全部随机数取自 `random.Random(20261125)`（种子固定并写入 stability.json），因此**同一 case + 同一 weights 必得逐字节相同的 stability.json**，可独立复核。runs 默认 50：对 9 条规模的池，50 次运行足以让名次极差收敛到其支撑集边界附近，且耗时可忽略。

## 4. Kendall's W 和谐系数

m 次扰动运行、n 条记录。记 R_i 为记录 i 在 m 次运行中的名次之和，S = Σ (R_i − m(n+1)/2)²，并列修正 T_j = Σ(t³ − t)（对第 j 次运行的每个并列组，t 为组内记录数）。则

**W = 12S / ( m²(n³ − n) − m·Σ_j T_j )**

W = 1 当且仅当 m 个名次表完全一致；W → 0 表示毫无一致性。代码手工实现该公式（含并列修正），不依赖任何第三方库；n < 2 时约定 W = 1（平凡一致）。W 报告的是**整体**一致性；逐条记录的责任由名次极差与翻转计数承担。

## 5. 稳定性阈值与处置

对每条记录，rank_range = 其在 N 次运行中的最高名次 − 最低名次：

- **stable**：rank_range ≤ 1 —— 扰动下至多移动一个相邻位次。
- **fragile**：rank_range ≥ 3 —— 扰动下横跨至少三个位次，其基准名次不可单独信任。
- **watch**：其余（rank_range = 2）—— 保留在正式排序中但在输出中显式标记。

**为什么 fragile 进 pending_review 而非排除**：名次不稳定不是"不相关"的证据，而是"本流水线无法可靠定位"的证据。排除会丢失记录且无法复核；移入 pending_review 带（位于 stable 保留记录之后）同时做到：全记录覆盖不破坏、变更留痕（`change_records` 逐条写明 "rank unstable under perturbation (rank range X)"）、把判断权交还人工。watch 不移带，因为它的不稳定性幅度尚不构成对名次的根本质疑，但必须可见。

## 6. 平局协议

平分检测在 6 位小数上进行。基准排序：score 降序 → record_id 升序；平分记录共享同一名次（竞赛排名 "1224" 式）并在 `tie_group` 中列出全部成员。扰动运行：score 降序 → 当次洗牌后的输入顺序。assemble 输出的 final_rank 不允许无 `tie_group` 说明的重复，validate 强制执行。

## 7. 限制

- 词元重叠是词法代理：同义改写、缩写、跨语言会漏配；它度量"词面相关"，不度量"真正回答研究问题"。后者由可选 semantic_score 补充。
- venue_tier 是字符串启发式（已标注 heuristic:true），不替代真实 venue 元数据核验。
- 稳定性结论以权重族为前提：扰动的是 ±10% 的权重值，不是特征集合本身；特征设计错误不在本方法检测范围内。
- 候选池是有限快照，不对快照外召回作任何声明。
- W 对记录数敏感：池很小时少量翻转即可显著拉低 W，解读时结合逐条 rank_range。
