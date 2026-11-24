# 排序规则（selection rubric）

`design_space.py select` 的默认规则，以及所有可改参数。

## 默认排序

1. **可行性门控**：只有 `feasible.overall = true` 的设计可入选。
   被否决设计连同完整 `reject_reasons` 列入 selection.json 的
   `rejected` 表（这是"选哪个设计是算术结论"的证据链）。
2. **信息度降序** `info_score`：

```
info_score = 10 × n_conditions
           +  5 × covarying_pairs
           +  2 × levels_sum
           +  1 × min(replicates, 3)
```

   - `n_conditions`：去重条件数（主效应/交互可估性的规模代理）；
   - `covarying_pairs`：发生联合变化的因子对数（联合取值组合数 >
     两因子各自水平数的最大值）；OFAT 设计与拉丁方主效应计划此项为 0，
     保留了交互网格的设计得分更高；
   - `levels_sum`：各因子覆盖的不同水平数之和（覆盖均匀性）；
   - `replicates`：重复次数，封顶 3（边际收益递减）。
3. **核算总成本升序**（信息度相同时省预算）。
4. **est_days 升序**（再相同则早交付）。
5. **id 字典序**（确定性兜底，保证可复现）。

推荐 = 第 1 名；备选 = 其后 `--alternates`（默认 2）名。

## 可改参数

| 参数 | 位置 | 效果 |
|---|---|---|
| `--min-replicates N` | score | 放宽/收紧重复次数门控（默认 2） |
| `--weights '{"conditions":10,"pairs":5,"levels":2,"replicates":1}'` | score / select | 改信息度权重；select 端给出时按表内 info_components 重算 |
| `--alternates K` | select | 备选数量 |
| `--factors` / `--levels` | enumerate | 只看因子子集 / 限制每因子水平数 |
| `--model model.json` | score | 覆盖 per_sample 消耗模型（须记入 assumptions） |
| `--no-candidates` | score | 只核算策略，不核算候选方案 |

## 改规则的纪律

- 权重或门控一旦改动，必须在 result.json 的 change_log 记录
  "改了什么、为什么、对结论的影响"（例如：放宽 min_replicates 到 1 后
  S1 从被否决变为可行但无误差估计，仍不推荐）。
- 不允许为了让某个候选"赢"而调参：候选方案（candidate_*）与新策略
  （strategy_*）适用同一套规则，这是本 skill 的核心主张。
- 无 feasible 设计时 select 输出 partial 与降级建议（缩水平数、
  放宽重复、申请追加预算/延期），不得硬推一个不可行设计。
