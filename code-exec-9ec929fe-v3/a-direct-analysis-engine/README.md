# direct-analysis-engine

端到端确定性科研数据分析引擎（Deterministic end-to-end engine for scientific
data-analysis cases）。一条命令完成清洗、统计、图形、SQL 与 result.json 骨架；
Agent 只负责裁决歧义与复核交付。详见 `SKILL.md`（中文正式文档）。

## Requirements / 运行要求

- Python 3.9+，仅标准库（csv, sqlite3, json, hashlib, statistics, math, argparse,
  pathlib, datetime, platform, sys, os, re, unicodedata）。
- matplotlib 可选：存在时输出 PNG 图形；缺失时自动降级为图形规格 JSON +
  绘图数据 CSV（退出码仍为 0）。
- 无网络访问需求。

## Usage / 用法

```bash
# 运行引擎（落盘全部产物与 result.json 骨架）
python3 scripts/case_engine.py run --input /input --work /app/work --output /app/output \
    [--rules rules.json] [--sql queries.sql]

# 双通道复核（独立代码路径重算 n/mean/std，校验契约与哈希）
python3 scripts/case_engine.py verify --input /input --work /app/work --output /app/output
```

退出码：run/verify 正常完成为 0；verify 有 FAIL 为 1；`--input` 目录不存在为 2；
未预期异常为 3（带 traceback 写 stderr）。

## File map / 文件清单

| 路径 | 说明 |
|---|---|
| `SKILL.md` | 技能主文档（YAML frontmatter + 中文执行协议） |
| `README.md` | 本文件 |
| `GITHUB_URL.txt` | 源码仓库地址 |
| `scripts/case_engine.py` | 引擎本体（run / verify 两个子命令，stdlib-only） |
| `references/engine_design.md` | 设计说明：rules 模式、清洗策略、异常分类、映射与复核方法 |
| `examples/synthetic_case/` | 合成演示输入（CSV + case.json + task.md，均为合成数据） |
| `examples/run_example.sh` | 一键演示脚本（run → verify → 打印结果） |
| `examples/output_demo/` | 演示输出（运行 run_example.sh 后生成） |
