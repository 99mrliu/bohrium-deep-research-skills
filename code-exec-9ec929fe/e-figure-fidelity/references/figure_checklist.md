# 论文级图表自查清单（figure-fidelity）

## 数据一致性

- [ ] 图的数据来自最终清洗表（receipt.table 指向它），不是中间版本。
- [ ] receipt.n_plotted + n_excluded_missing = 源表行数；排除点在 anomalies
      有对应记录。
- [ ] receipt 值域与源表实测一致（lint 第 3 项机检）；手绘趋势线的参数
      若进图注，必须能在统计结果中找到。
- [ ] 分组图的组名与源表分组键逐字符一致（大小写、空格）。

## 轴与单位

- [ ] xlabel/ylabel 含单位，单位抄自数据字典（lint 第 4 项机检）。
- [ ] 轴标签包含所绘列名（lint 第 5 项机检）；如需更友好的措辞，采用
      "友好名 (列名, 单位)" 形式，保住列名。
- [ ] 数量级 sanity check：直方图值域与 describe 的 min/max 一致；若差了
      10³ 量级，怀疑单位或缩放错误，回数据环节查，不改图了事。

## 渲染与交付

- [ ] PNG 真实存在、非空、哈希与 receipt 一致（lint 第 2 项机检）——防
      "重跑后图换了、回执没更新"与"交付了上次的旧图"。
- [ ] 每张 PNG 配 .data.csv（可复绘）与 .receipt.json（可复核）。
- [ ] result.json figures 字段每项经 figkit check 核对。
- [ ] 渲染库缺失时交付 SKIPPED 回执 + 数据 CSV，并在 result.json 与
      anomalies 如实说明；**禁止**用占位图、旧图或"看起来像"的图充数。

## 常见图表静默错误

| 错误 | 拦截点 |
|-|-|
| 单位写错/张冠李戴 | lint 单位-字典核对 |
| 轴标签与所绘列不符 | lint 列名-标签核对 |
| 缺失点被悄悄丢弃 | receipt.n_excluded_missing + anomalies 对账 |
| 重跑后图与回执脱节 | PNG 哈希核对 |
| 图字段登记了路径但文件没生成 | figkit check |
| 无 matplotlib 时交旧图 | SKIPPED 状态机 + check 要求数据 CSV |
