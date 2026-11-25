# budget-warden-qc

面向 Playground 竞赛题 challenge-60a8202d「引文追踪与关联文献发现」的 Skill bundle，
工程重心为**过程质量控制与预算治理**：分阶段增量交付、checkpoint 断点续跑、确定性
输出、QC 自检回路、双跑一致性校验。

## 它解决什么

Agent 在 900 秒 / 64 次模型请求的预算内做引文追踪时，最常见的失败模式是：跑到一半
超时或中断、什么都没落盘；或者让模型逐条手工整理文献，结果不可复现。本 Skill 让
Agent 用**一条命令**跑完确定性的 Python 管线：

- stage0 启动数秒内先写 honest partial `result.json` —— 任何时刻中断都有可评交付；
- stage1→3 逐阶段 ingest、浅层扩展、加深合并，每阶段 checkpoint，中断后 `--resume`
  从最近断点续跑；
- result.json 内零时间戳、全排序稳定，重复运行字节一致，`reproduce.py` 可验证；
- `qc_loop.py` 按缺陷清单自检，安全缺陷自动修复并留 change_log。

## 怎么跑

```bash
# 完整管线（Harbor 契约默认值即 /input、/app/output、/app/work）
python3 scripts/warden.py --case /input/case.json --out /app/output --workdir /app/work

# 中断后续跑
python3 scripts/warden.py --case /input/case.json --out /app/output --workdir /app/work --resume

# QC 质量回路
python3 scripts/qc_loop.py --case /input/case.json --out /app/output --workdir /app/work

# 双跑一致性校验
python3 scripts/reproduce.py --case /input/case.json --workdir /app/work --runs 2
```

本地合成示例（离线、数秒完成）：

```bash
python3 scripts/warden.py --case examples/case.json --roots examples/corpus \
    --out /tmp/wq/out --workdir /tmp/wq/work --max-depth 2
```

## 目录结构

```
SKILL.md                     # Agent 视角的使用说明（含运行契约、异常处理表、自查方法）
GITHUB_URL.txt               # 作品 GitHub 链接
scripts/warden.py            # 分阶段编排器（stage0–3、checkpoint、--resume、--time-budget）
scripts/qc_loop.py           # QC 质量回路（Q1–Q7 缺陷清单、自动修复 + change_log）
scripts/reproduce.py         # 双跑一致性校验（逐字节 diff result.json）
references/stage_policy.md   # 阶段划分、checkpoint 格式、预算降级规则
references/qc_checklist.md   # 缺陷清单与修复策略
examples/                    # 合成最小示例（SYNTHETIC，见下）
  case.json / task.md / walkthrough.md
  corpus/                    # 4 个语料文件，5 篇虚构文献 + 1 个不可解析引用目标
  run_out/                   # 合成示例的真实运行产物（result.json、checkpoints、QC 报告）
```

## 合成示例声明

`examples/` 下全部文献均为**虚构（SYNTHETIC, not real papers, 非正式案例结果）**，DOI
一律使用 `10.0000/synth.*` 保留测试段，不对应任何真实出版物。`examples/run_out/` 中的
产物是该合成示例的真实脚本运行结果，仅用于演示流程，不冒充正式案例结果。

## 依赖与约束

Python 3（仅标准库）；默认完全离线；脚本位置无关；全部 UTF-8 文本；无符号链接。
