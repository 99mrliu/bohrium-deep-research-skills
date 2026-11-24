# run-forensics（challenge-9ec929fe 作品 D）

运行调试与过程取证重心：`runcap exec` 把每次执行变成带完整现场的结构化
事件（命令行、退出码、耗时、stdout/stderr 全文、输入哈希、失败自动分
类）；`replay` 生成可逐步重放的 replay.sh；`report` 汇总失败分类与重试
链；`seal` 把台账并入 provenance 并强制诚实 partial。纯 Python 标准库。

## 使用

```bash
python3 scripts/runcap.py init --input /input --work /app/work --output /app/output
python3 scripts/runcap.py exec --work /app/work --tag clean --hash /input/x.csv -- \
  python3 your_step.py ...
python3 scripts/runcap.py report --work /app/work
python3 scripts/runcap.py replay --work /app/work
python3 scripts/runcap.py seal --input /input --work /app/work --output /app/output
```

## 合成示例

`bash examples/run_example.sh` —— 三步管道（clean/stats/sql），sql 步第一次
故意查错表名以演示失败捕获与分类，修复后同 tag 重跑形成重试链；随后
report/replay/seal，replay.sh 真实重放成功。数据人工合成。

详见 [SKILL.md](SKILL.md) 与 [references/failure_playbook.md](references/failure_playbook.md)。
