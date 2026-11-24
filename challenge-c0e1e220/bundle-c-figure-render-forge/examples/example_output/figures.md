# figures.md — 图表证据清单（figure_forge.py 生成，机器可审计）

- case_id: synth-figforge-demo
- channel: svg（matplotlib 可用: False；--force-svg: True）
- seed: 20240501 | 生成(utc): 2026-11-24T16:16:29+00:00
- 选择规则: 分组数值比较→箱线+抖动散点（每组 n<10 强制全点）；非参路线→加 ECDF；两数值变量→散点+OLS；分类计数→频数条形图；**禁止** n<30 的 bar+SE/SD 组间比较图

## fig1 — fig1.svg
- file: fig1.svg
- channel: svg
- type: boxplot_jitter
- analyses: a1
- rationale: 分组数值比较（design=k_group，k=3）→ 箱线图+抖动散点叠加；control n=8（全部 8 点（n<10 强制全点））；treatA n=9（全部 9 点（n<10 强制全点））；treatB n=10（全部 10 点）
- caption: 图1｜箱线图+抖动散点｜rt 按 group 分组比较（单位：ms）｜组 control：n=8，均值=9.84，SD=0.85；组 treatA：n=9，均值=11.77，SD=1.21；组 treatB：n=10，均值=13.06，SD=1.37｜检验：Kruskal-Wallis H(2)=14.36，p=0.0008，α=0.05｜散点：control 全部 8 点（n<10 强制全点）；treatA 全部 9 点（n<10 强制全点）；treatB 全部 10 点｜数据区间 [8.87, 14.78]
- data_range: [8.87, 14.78]

## fig2 — fig2.svg
- file: fig2.svg
- channel: svg
- type: ecdf
- analyses: a1
- rationale: 主检验为非参路线（Kruskal-Wallis）→ ECDF 展示分布形态（规则：分布形态→ECDF）
- caption: 图2｜ECDF 分布形态｜rt 按 group 分组比较（单位：ms）｜组 control：n=8，均值=9.84，SD=0.85；组 treatA：n=9，均值=11.77，SD=1.21；组 treatB：n=10，均值=13.06，SD=1.37｜检验：Kruskal-Wallis H(2)=14.36，p=0.0008，α=0.05｜选择理由：主检验为非参路线（Kruskal-Wallis），以 ECDF 呈现分布形态避免箱线掩盖偏态/双峰｜数据区间 [8.87, 14.78]
- data_range: [8.87, 14.78]

