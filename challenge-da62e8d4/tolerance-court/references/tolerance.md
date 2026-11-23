# 容差类型学、判定真值表与反作弊模式

> 本文件是 `scripts/preregister.py` 与 `scripts/adjudicate.py` 判定代数的参考依据。
> 所有示例数值均为合成示例（synthetic），非正式案例结果。

## 1. 容差类型学

| 类型 | 来源 | 规则 | 例 |
|---|---|---|---|
| **case_given（案例给定）** | case.json / task.md 显式给出 | **逐字优先**，不得自行收紧或放宽 | 案例写 `accuracy ±0.01` → tol=0.01 |
| **half_ulp（四舍五入半单位）** | 论文报告值的书写有效数字 | 报告值是舍入后的结果，真值落在 ±半个最小书写单位内 | `0.152` → ±0.0005；`72.1` → ±0.05 |
| **科学计数法** | 同上 | 半单位 = 5×10^(指数−尾数小数位−1) | `1.2e3` → 5×10^(3−1−1)=±50 |
| **无小数点整数** | 同上 | 按书写最后一位（个位）为有效位，半单位=0.5 | `1200` → ±0.5（书写位数规则；若论文声明只保留 2 位有效数字，应改用 case_tolerance 登记 ±50） |
| **stochastic 放大（k 倍）** | agent 判断 | 仅当 kind=stochastic；k>1 时**必须在注册时写下 rationale**，并体现在容差文件的 reason/rationale 字段 | 方差大的采样指标 k=2，理由“论文为单种子报告，波动量级未知” |
| **相对容差** | 派生量 | tolerance_rel = tolerance_abs / |paper_value|，随档记录便于跨量级比较 | tol=50, paper=1200 → rel≈4.2% |

原则：**容差是“论文值的不确定性”加上“可接受的实现差异”的事前承诺，不是看到结果后的谈判筹码。**

## 2. 判定代数真值表

对每个“方法 × 指标”，记 paper=论文值（数值），tol=容差，观测序列 values（n=len），
median 为中位数，spread=max−min，deviation=|median−paper|。按优先级匹配：

| # | 条件 | 判定 | attribution_hint |
|---|---|---|---|
| 1 | paper 或 tol 不存在（论文未报告） | `not_comparable` | none |
| 2 | n=0（观测空） | `missing` | none |
| 3 | kind=stochastic 且 n=1 | `insufficient_runs` | none |
| 4 | deviation ≤ tol | `within_tolerance` | none |
| 5 | 超差 ∧ stochastic ∧ spread>0 ∧ ∃v∈values: |v−paper|≤tol | `stochastic_fluctuation` | numerical_noise |
| 6 | 超差 ∧ deviation > 3×spread | `systematic_deviation` | systematic |
| 7 | 其余超差 | `exceeds_tolerance` | none |

附加：stochastic 且 n=2 → 按上表判定，但附加 `insufficient_runs` 告警。
观测含未注册指标 → `not_comparable` + `unregistered_metric` 告警。

退出码：出现 `systematic_deviation` / `exceeds_tolerance` / `missing` 或
`preregistration_violation=true` → 1；否则 0；输入结构错误 → 2。

### 判定依据的直觉

- **规则 5**：随机指标的超差里如果仍有种子落在容差内，说明分布与论文值有重叠，
  偏差可由抽样波动解释——但 n 必须足够（n<3 见告警/规则 3）。
- **规则 6**：观测聚在一起（spread 小）却整体偏离论文值（deviation 大，>3×spread），
  随机波动解释不动，是稳定的系统偏差——指向实现/超参/数据口径差异。

## 3. 波动 vs 系统差异：判别边界与反例

**反例 A：spread 很大 ≠ 随机波动。**
10 个种子的值全部大于 paper 的 1.5 倍，即使 spread 也很大，方向完全一致 = 系统偏差。
规则 5 要求“至少一个观测落在容差内”，正是为了挡住“拿 spread 大当波动借口”。

**反例 B：单值超差不能喊波动。**
deterministic 指标（如同配置应当逐位可复现）超差就是超差，没有“波动”可谈；
规则 5 只对 stochastic 生效。

**反例 C：stochastic_fluctuation ≠ 复现成功。**
它只说“差异在抽样噪声可解释范围内”；若 n=5 里 4 个超差，即便判了 fluctuation，
报告里也必须给出 n 与超差比例，让读者看到证据强度。

**反例 D：within_tolerance（在合成目标上）≠ 论文数值复现。**
组织方合成代码与合成数据 ≠ 作者原代码与原始数据。措辞必须写
“候选实现与合成目标在容差 ±x 内一致（n=k）”，不得升格。

## 4. 常见作弊模式（评测红线）

1. **事后放宽容差**：跑出结果再写/改 tolerances.json。
   防线：容差先落盘 + `adjudicate --runs` mtime 校验 → `preregistration_violation`；
   重建必须 `--force`，旧文件 sha256 进 change_records 随报告公开。
2. **把 mean 当中位数比**：先算一堆统计量，挑一个能过容差的口径。
   防线：判定代数固定用 median；aggregation 只作档案记录，不作选择开关。
3. **挑种子**：跑 20 个种子、报告最听话的 3 个。
   防线：observations.json 要求全量 values 并附 logs 路径；n、spread、MAD 全公开；
   n=1 的 stochastic 指标直接 insufficient_runs。
4. **编造论文值**：论文只给了图，就“目测”一个数当 paper_value。
   防线：paper_value=null → not_comparable；估读必须注明且低置信。
5. **悄悄换 targets**：注册后改动输入指标清单再重跑 preregister 覆盖。
   防线：tolerances.json 内嵌 targets_sha256；覆盖必留 change_records。
