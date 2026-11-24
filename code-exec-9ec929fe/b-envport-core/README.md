# envport-core（challenge-9ec929fe 作品 B）

环境配置与零依赖可移植执行核心：清洗/描述统计/Welch t/Pearson/OLS/SQLite
只读查询/绘图全部用纯 Python 标准库实现，任何 Python≥3.8 环境免安装复现；
matplotlib 缺失时显式降级并保留绘图数据；env 快照 + run_log + finalize
保证可复核。

## 使用

```bash
python3 scripts/envport.py --work /app/work --output /app/output env
python3 scripts/envport.py --work /app/work profile /input/data.csv /input/lab.db
python3 scripts/envport.py --work /app/work clean --table /input/data.csv \
  --rules rules.json --out /app/work/clean.csv --report /app/work/clean_report.json
# describe / aggregate / ttest / corr / ols / sql / figure ...
python3 scripts/envport.py --work /app/work --output /app/output finalize --input /input
```

## 合成示例

`bash examples/run_example.sh` —— 在人工合成数据（`examples/synthetic_case/`）
上跑通全链路，并演示无 matplotlib 时的诚实降级。统计实现已与 scipy
交叉核对（Welch t 与 Pearson r/p 差异 <1e-10）。

详见 [SKILL.md](SKILL.md) 与 [references/environment_playbook.md](references/environment_playbook.md)。
