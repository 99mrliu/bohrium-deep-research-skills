# stat-assumption-tribunal

统计推断合规裁决 Skill（Bohrium Playground challenge-9ec929fe 提交物 b）。
核心主张：**前提检验不过关就不许报 p 值；一切统计量口径显式化。**

## 概览

`scripts/stattool.py` 是纯标准库的统计计算与裁决工具：

| 子命令 | 功能 | 退出码 |
|---|---|---|
| `descriptive` | 描述统计：n、n_missing、均值、中位数、ddof=0/1 双标准差与方差、inclusive/exclusive 双四分位、矩法偏度与超出峰度、标准误、均值 95% t 置信区间；可按组分列 | 0 成功 / 1 错误 |
| `compare` | 组间比较裁决：最小样本量 → D'Agostino-Pearson K² 正态性 → Brown-Forsythe 方差齐性 → 通过则 Welch（主）+ Student（并列），失败则改判 Mann-Whitney U（k=2）或 Kruskal-Wallis（k>2） | 0 按请求执行 / 2 已改判 / 1 无法计算 |
| `corr` | Pearson r（含 t 检验双侧 p）+ Spearman ρ，成对剔除缺失 | 0 / 1 |
| `verify-claims` | 按本工具口径独立复算 claims.json 中每条断言，相对容差 1e-6（p 值绝对容差 1e-3） | 0 全 PASS / 1 存在 FAIL |
| `selftest` | 特殊函数数值自检（18 项：正态／t／F／卡方 CDF 已知点、恒等式、MWU 手算点等） | 0 / 1 |

所有输出为 JSON，含输入文件 sha256、行数、缺失策略、去重策略与公式说明；
`--out PATH` 可落盘。特殊函数（正则化不完全 beta／伽马、t／F／卡方 CDF、t 分位数）
为自行实现，数值精度由 `selftest` 保障。

## 运行要求

- Python ≥ 3.9，**仅标准库**（argparse、csv、json、math、statistics、hashlib、
  datetime、pathlib、sys）；无网络、无第三方依赖。
- 输入 CSV 须为 UTF-8（兼容 BOM），首行为表头。

## 文件地图

```
b-stat-assumption-tribunal/
├── SKILL.md                          # 技能说明（重心、运行契约、执行协议、异常处理、局限性）
├── README.md                         # 本文件
├── GITHUB_URL.txt                    # 仓库地址
├── scripts/
│   └── stattool.py                   # 裁决工具（stdlib-only，含 selftest）
├── references/
│   └── statistical_playbook.md       # 口径表、阈值依据、改判矩阵、禁止事项、公式附录
└── examples/
    ├── run_example.sh                # 全流程演示（任意 cwd 可跑，自检退出码）
    └── synthetic_case/
        ├── two_groups_syn.csv        # 82 行虚构数据：A~N(100,15)，B 右偏，4 缺失 + 2 重复
        └── claims_demo.json          # 6 条断言：4 条取自工具真实输出，2 条故意写错

# run_example.sh 运行后会在 synthetic_case/_out/ 生成实际输出 JSON（本地缓存，未随包发布）
```

## 快速开始

```bash
python3 scripts/stattool.py selftest          # 数值自检，期望 18/18 PASS
bash examples/run_example.sh                  # 全流程演示，期望 "ALL EXPECTATIONS MET"
```

合成示例的真实裁决结果：B 组正态性 K² p≈2.53e-8 → 改判 Mann-Whitney U
（U=596，p≈0.101，rank-biserial≈-0.216），compare 退出码 2；
verify-claims 对演示断言给出 4 PASS / 2 FAIL，退出码 1。

## 设计边界

见 `SKILL.md` 的「局限性」与 `references/statistical_playbook.md` 的
「禁止事项清单」。简言之：小样本秩检验为近似、多重比较只报告不自动校正、
仅支持单分组一维设计。
