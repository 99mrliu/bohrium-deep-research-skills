# 代表作遴选口径（representative_select.py 的完整规格）

设计目标：**可审计**。每一个候选的每一分都能被复核，遴选理由可以逐条向
评审解释；"为什么选它"永远有数字答案，"为什么不选引用更高的那篇"也是。

## 1. 打分公式（多准则模式，默认）

对每个阶段（phases.json），阶段内每条记录：

```
total = 0.5 * citation_percentile
      + 0.3 * term_centrality
      + 0.2 * method_first_bonus
```

- **citation_percentile**（0–1）：仅**阶段内**比较。按 (citations 升序,
  id 升序) 排名，percentile = rank / n（n = 阶段内记录数，rank 从 1 起）。
  阶段内比较的理由：早期阶段文献积累引用的时间长、最新阶段几乎没有，
  全局比较会把"年代"误当"影响力"。
- **term_centrality**（0–1）：该记录全部词项的**阶段内份额**之和
  （词项份额 = 该词项在阶段内各年文献计数之和 / 阶段内全部词项计数之和），
  再除以阶段内候选的最大值归一。它度量"这条记录有多贴着本阶段的核心
  词汇工作"，让代表作必须代表阶段主题，而不是离题的高引文。
- **method_first_bonus**（0 或 1）：当且仅当
  (a) `record.year <= phase_start + 1`，且
  (b) 该记录是某个**本阶段 emerging term**（首见年落在本阶段、阶段 df≥2）
      的**最早出现年**里包含该词项的文献之一。
  确定性实现：emerging term 的首见年取 term_year_matrix 中该词项计数>0
  的最小年份；该年内所有含此词项的记录均为"引入者"。这一档把
  "开创方法的首发文献"拉进候选——它们常被引用 mid-life 综述性高引文压过。

权重 0.5/0.3/0.2 是显式常数（写在 representatives.json 的 `weights` 里），
不是学出来的；改权重即改口径，必须在报告中声明。

## 2. 每阶段配额与闸门

- 每阶段固定选 top-K（默认 K=2，`--per-phase`），**按 total 降序、同分按
  record_id 升序**决胜——完全确定性。
- 配额的意义：阶段覆盖是硬性结构约束，不是分数的副产品。
- **覆盖率闸门**：coverage = 有 ≥1 代表作的阶段数 / 阶段总数。
  - 多准则模式：某阶段 0 代表作（只可能是语料空洞）→ 打印 WARNING 并写入
    `warnings`，exit 0——空洞必须被报告，而不是被掩盖；
  - baseline 模式：coverage < 1.0 → **exit 1** 并点名未覆盖阶段。

## 3. 反模式基线：--baseline top-citations

模拟"全局引用 top-N"（N = K × 阶段数，同引按 id 升序决胜），随后跑同一个
覆盖率闸门。它存在的唯一目的就是**让反模式可证伪**：

- 为什么原始引用 top-N 必然偏斜：**幸存者偏差朝向 mid-life 阶段**。
  早期阶段文献虽开创，但绝对引用常被后来集大成者超越；最新阶段文献还
  没有积累时间。全局 top-N 因此集中在中段"积累足够久 × 仍被持续引用"
  的阶段——在合成语料上，全局 top-6 全部落在第二阶段，第一、三阶段
  覆盖为 0，闸门 exit 1（见 examples/example_output/bad/）。
- 交付前可跑一次 baseline：若你的多准则结果覆盖率 = 1.0 而 baseline < 1.0，
  这个对比本身就是"使用增益"的直接证据，写进报告。

## 4. 输出（representatives.json）

`candidates` 含**每个候选**的一行：record_id、title、year、phase_id、
citations、三个分项分数、total_score、selected。整张表进证据矩阵；
任何人可以按同一公式复算并质疑每一行的取舍——这就是"遴选口径可说明"。

## 5. 限度

- 打分排序决定**候选与口径**，最终表述仍须代理读摘要确认该文确属该阶段
  核心工作（打分不懂语义）。
- citations 字段缺失/全零时 citation_percentile 退化为纯 id 序，此时应
  在 uncertainty 中声明引用信号不可用。
