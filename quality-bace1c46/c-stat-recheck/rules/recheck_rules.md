# 一致性重算规则（recheck rules）

本文件是 `scripts/recheck.py` 的规则明文。每条规则给出：触发条件、重算方法、
容差、三态判定。**discrepancy ≠ 论文错误**，只表示"报告内部不一致，需人工核对"。

## 0. 三态定义

- `pass`：报告值与重算值在容差带内一致。
- `discrepancy`：报告值与重算值超出容差带，存在内部不一致，需人工核对。
- `not_recomputable`：重算所需信息不全（缺自由度、缺总 n、缺配对 CI 等），
  不做任何推断性补全。

另：报告完整性缺口行使用 `reported / absent / not_applicable / unclear`
（absent 是缺口记录，不是过失判定）。

## 1. 频数 ↔ 百分比（check_type: freq_vs_percent）

- 触发：同句匹配到 `a/b (p%)`（count/total 与百分比同现）。
- 重算：`computed = 100 * a / b`。
- 容差：±0.5 个报告末位单位。报告 `52%`（0 位小数）→ ±0.5 个百分点；
  报告 `46.7%`（1 位小数）→ ±0.05 个百分点。
- 判定：`|computed - reported| ≤ 容差` → pass，否则 discrepancy。
- 摘录：side[0]=所在句，side[1]=匹配片段，均带页锚。

## 2. 分层求和（check_type: stratified_sum）

- 触发：同句出现 ≥2 个 `n=NN`。
- 同句 ≥3 个：取最大值为总 n，其余求和比对，容差 0（整数必等）。
- 同句 2 个：求和后在全文其他位置找等值总 n → pass；找到偏差 ≤10% 的
  近似总 n → discrepancy 且入 needs_semantic（确认两处 n 是否同一总体）；
  找不到可比对总 n → not_recomputable。

## 3. 摘要 ↔ 正文（check_type: abstract_vs_body）

- 触发：文献含 `Abstract` 节标题且非仅摘要条目；以"数值指纹"配对——
  摘要与正文中**相同语境词**（数字前最近的长度≥4 的英文词）+ 百分比数值。
- 判定：数值差 ≤0.05 个百分点 → pass；否则 discrepancy 且入
  needs_semantic（确认是否同一指标，语义裁决可推翻）。
- 仅摘要文献不执行本规则（无正文可比）。

## 4. p 值粗复核（check_type: p_value_recompute）

- 触发：采集到检验统计量（t/z/χ²/F）**且自由度齐全**。缺 df 时先在句内
  找 `df=N`；仍缺 → `not_recomputable`。
- 重算（全部为近似，标准库实现）：
  - t（双侧）：`p = I_{df/(df+t²)}(df/2, 1/2)`，正则化不完全 β 函数，
    连分式实现（Numerical Recipes betacf 移植），收敛阈 3e-12。
  - z（双侧）：`p = erfc(|z|/√2)`（math.erfc）。
  - χ²（上尾）：`p = Q(k/2, x/2)`，正则化上不完全 γ，级数（x<a+1）/
    连分式（x≥a+1）实现。自由度 ≤100 已验证稳定，更大 df 同法外推。
  - F（上尾）：`p = I_{d2/(d2+d1·f)}(d2/2, d1/2)`。
  - 典型绝对误差 <1e-9；但**报告值本身带舍入**，故判定使用容差带而非精确相等。
- 配对 p：同句优先，其次同页 ±200 字符内最近 p 值；找不到 → needs_semantic。
- 容差与判定（reported 为报告 p，computed 为重算 p）：
  - 报告 `p < α`：computed < α → pass；computed ≥ α + 0.005 → discrepancy；
    边界带 [α, α+0.005) 内按 pass 处理并注明近似边界。
  - 报告 `p > α`：对称处理。
  - 报告 `p = v`：容差 `max(0.005, 0.2·v)`，带内 pass，带外 discrepancy。
- 边界情形（computed 落在报告声明边界附近）一律在 note 注明"近似重算，
  谨慎解读"。

## 5. 效应方向（check_type: effect_direction）

- 触发：OR/HR/RR 点估计与同句或 ±250 字符内的 95% CI 配对；无 CI →
  not_recomputable。
- 判定（任一命中即 discrepancy）：
  1. 点估计不在 CI 区间内；
  2. CI 跨 1（lo<1<hi）但同句声称 significant（且未被 not/non/no 否定）；
  3. CI 不跨 1 但同句声称 not significant。
- 三项均不命中 → pass（方向自洽）。

## 6. 汇总分级阈值（aggregate_grade.py 实现与本节一一对应）

计数口径：机械复核行 = check_type 不以 `completeness:` 开头的行；
"已验证"= 通过 verify_quotes.py 摘录校验且未降级；关键缺口 absent =
完整性行中 absent 数。

1. 机械复核行数 = 0 → **ungradable**。
2. 已验证 discrepancy ≥ 3，或有判定行（pass+discrepancy）≥5 且已验证
   discrepancy 占比 ≥ 30% → **serious_concerns**。
3. 否则，已验证 discrepancy ≥ 1，或未验证（降级）discrepancy ≥ 2，或
   关键缺口 absent ≥ 2 → **concerns**。
4. 否则，pass ≥ 1 → **adequate**。
5. 否则（全部 not_recomputable）→ **ungradable**。
6. 全部可解析文献均为仅摘要条目 → 附加 `limited=true`（不直接改等级，
   但结果不得外推摘要口径之外）。
7. 恰好 1 条未验证 discrepancy：不足以触发第 3 条升级，但必须写入
   uncertainties 提示人工核对。

## 7. 归一化与校验（verify_quotes.py）

- 归一化：先还原连字符断行（`-\n` → 删除），再把全部空白折叠为单空格。
- 校验：归一化摘录在所标页的归一化文本中做子串匹配，报告字符偏移区间
  `[start, end)`；页内不命中则搜全文档，命中他页记 `page_mismatch`，
  完全不命中记 `not_found`。
- 任一 side 失败 → 整行 `downgraded=true`，其 discrepancy 在分级中按
  未验证降权（见第 6 节）。
- 无摘录行（absent 缺口类）不参与锚定校验，标记 `no_quote`。
