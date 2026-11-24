# examples/ — 合成示例（非正式案例结果）

本目录为**合成示例**，仅用于演示本 Skill 三个脚本的端到端行为，不代表任何正式案例的结果。

## 目录结构

- `case/` — 合成的案例材料：
  - `pipeline.sh`：三条真实命令（预处理 → 训练 → 评估），含 `--lr 2e-5`、`--seed 42` 等 flag；
  - `run.log`：带时间戳的执行记录，命令顺序与脚本一致，含环境信息（Python 3.10.12、torch 2.1.0+cu121、A100）；
  - `README.md`：依赖与数据说明，**故意不写随机种子**；
  - `requirements.txt`：依赖声明；
  - `draft.md`：**故意有缺陷**的章节草稿——把预处理与训练两条命令压成一句、把 `--lr 2e-5` 误写为 `--lr 2e-4`、省略 `--seed 42`、不写种子与环境版本。
- `run_example.sh`：一键依次运行三个脚本，产物写入 `expected/`。
- `expected/`：脚本产物（commands.json/md、steps.md、repro_report.json/md）。

## 运行方式

```bash
bash examples/run_example.sh
```

## 预期结果

1. `command_mine`：提取出三条完整命令（flag 完整，含续行拼接）、环境线索、种子 `seed=42`、数据 URL、依赖；
2. `step_table`：按 `run.log` 时间戳给出 预处理 → 训练 → 评估 的建议顺序；
3. `repro_check`：总体状态 **FAIL**——抓出 `--lr 2e-4`（真实值 `2e-5`）的 flag 改写，
   报出 G6 种子缺口（章节未写种子）、G2 环境版本缺口、G4 评估命令缺失，
   并对"多步压一句"与省略 `--seed 42` 给出 WARN。
   FAIL 是预期行为：草稿确实有缺陷，核验脚本的职责正是拦截它。
