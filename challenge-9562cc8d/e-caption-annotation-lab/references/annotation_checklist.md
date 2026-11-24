# 标注一致性审计清单（caption_lint.py 实现）

## 机器检查项

| 检查 | 内容 | 失败含义 |
|---|---|---|
| completeness:figN:样本量 | 图注含 `n=\d+` | 图注不可独立阅读 |
| completeness:figN:数据来源 | 含"数据来源" | 来源不明 |
| completeness:figN:清洗口径 | 含清洗说明 | 口径不明 |
| completeness:fig2:误差线/须线含义 | 箱线图图注含须线定义 | 误差语义缺失 |
| numeric:caption_r_values | 图注每个 r 都在 statistics 的相关集合中 | 手抄/过期数字 |
| numeric:caption_n_values | 图注每个 n 都在 {总 n, 各组 n, 相关 n} 集合中 | 手抄/过期数字 |
| legend:group_levels_1to1 | figdata 分组水平 == 统计分组水平 | 图例与数据脱节 |
| panels:sequential | (a)(b)(c) 连续 | 面板引用混乱 |
| units:declared | 单位嵌入列名的变量在轴标/图注声明单位 | 单位缺失 |

## 轴标与图例规范

- 轴标 = 变量名 + 单位（`名称 [单位]`）；列名内嵌单位（如
  `sepal_length_cm`、`Cement (component 1)(kg in a m^3 mixture)`）
  自动解析并归一化（`kg in a m^3 mixture` → `kg/m³`）；
- 对数轴在轴标末尾追加"（对数尺度）"；
- 图例条目直接取数据中的分组取值，不做无说明的重命名；整数编码
  分组显示为原始编码（1/2/3）并在图注说明其语义；
- 面板字母位于面板标题开头，格式 `(a) `，全文引用一致。

## 审计输出

`caption_audit.json`：`checks[]`（每项含 passed 与 detail）、
`n_pass`/`n_fail`、`all_passed`。失败项同步进入 `result.json` 的
`uncertainty`，`status` 降 `partial`——图注问题与数据问题同等
严重，不区别对待。
