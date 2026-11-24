# Cohen's kappa 一致性指南（slr-dual-screen）

## 1. 公式（kappa.py 的手写实现与此一致）

把每条记录的判定二分类：**include vs 非 include**（exclude、uncertain 均归非 include）。

- 观测一致率：`po = 双方判定一致的记录数 / N`
- 期望一致率：`pe = (nA+/N)(nB+/N) + (nA−/N)(nB−/N)`，其中 nA+/nB+ 为 A/B 判
  include 的条数，nA−/nB− 为判非 include 的条数
- Cohen's kappa：`kappa = (po − pe) / (1 − pe)`

kappa=1 完全一致；kappa=0 一致程度不优于随机；kappa<0 不如随机。pe=1 的退化
情形（边际分布全同）下，po=1 记 kappa=1，否则记 0。

## 2. 阈值解读（本技能默认 0.6）

| kappa | 解读（Landis & Koch 的常用分级，仅作参考） | 本技能处置 |
|-------|------|------|
| < 0.6 | 中等及以下一致 | `requires_extended_adjudication=true`；--enforce 时 exit 3 阻断 |
| 0.6–0.75 | 实质性一致 | 可进入仲裁，但在 uncertainty 注明仍有提升空间 |
| ≥ 0.75 | 高度一致 | 常规仲裁即可 |

阈值是治理线不是科学定律：选题窄、记录少时 kappa 波动大，应在 uncertainty 中
给出 kappa 的点值与样本量（如 "round2 kappa=0.545, N=5"），让读者自行判断。

## 3. 低 kappa 的处置路径（按序执行）

1. **澄清条款**：低 kappa 最常见原因是条款歧义（如"远程康复"是否含电话随访）。
   回到 criteria.json，把分歧点写成无歧义表述 → 升版本 → 写 change_records →
   对受影响记录重筛（见 dual_screen_protocol.md 版本纪律）。
2. **加轮筛选**：澄清条款后，对原分歧子集（必要时全量）重跑一轮双筛。
3. **扩大仲裁**：仍低于阈值时，全部分歧提交仲裁，并在 result.json 的
   uncertainty 与 counts 中如实记录"一致性未达标，纳入集主要由仲裁决定"，
   这是可复现性下降的诚实声明，不得隐藏。
4. 分歧比例 > 30% 时，直接判定条款体系失败，回到第 1 步重做条款，不要靠
   仲裁硬压。

## 4. kappa 的局限（必须如实写入 uncertainty）

- **患病率悖论（prevalence paradox）**：当纳入率极高或极低（边际分布严重偏斜）
  时，pe 被推高，即使 po 很高 kappa 也可能很低。例：本技能合成示例 round 2 中
  N=5、纳入率约 70%，po=0.80 但 kappa 仅 0.545。此时应同时报告 po 与 kappa，
  并说明"低 kappa 部分由边际分布偏斜导致"。
- **样本量小**：N 小时 kappa 置信区间很宽，单条分歧即可大幅改变 kappa。
- **二分类损失信息**：include/exclude/uncertain 被压成二类，uncertain 与
  exclude 的差异被抹平；需结合分歧清单逐条阅读。
- kappa 只度量两名筛选者之间的一致性，**不度量判定本身的正确性**——两人都错
  也会高 kappa。质量仍需靠条款、仲裁留痕与全文核验保证。
