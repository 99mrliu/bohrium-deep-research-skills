# 方法与实验步骤表（骨架）

> 由 step_table.py 自动生成。`判断条件` 列留待模型依据材料补全；
> 本脚本不臆造任何命令、输入或输出。

- 顺序依据：日志时间线（run.log 等 3 条带时间戳的执行记录）。

| 步骤号 | 名称 | 输入 | 命令/操作 | 预期输出 | 判断条件（待模型补全） | 来源 |
|---:|---|---|---|---|---|---|
| 1 | 数据预处理 | data/raw.csv | `python preprocess.py --input data/raw.csv --output data/clean.csv --min-len 5` | data/clean.csv | 待补：依据材料写明退出码/产物存在性/指标阈值等 | pipeline.sh:7；日志 2025-06-01 09:00:04 |
| 2 | 模型训练 | data/clean.csv | `python train.py --data data/clean.csv --model bert-base-chinese --lr 2e-5 --epochs 3 --batch-size 16 --seed 42` | （待模型补全） | 待补：依据材料写明退出码/产物存在性/指标阈值等 | pipeline.sh:12；日志 2025-06-01 09:00:42 |
| 3 | 模型评估 | data/clean.csv | `python evaluate.py --data data/clean.csv --ckpt outputs/best.pt --split test` | （待模型补全） | 待补：依据材料写明退出码/产物存在性/指标阈值等 | pipeline.sh:15；日志 2025-06-01 10:12:58 |

## 下一步

1. 模型逐行补全 `判断条件`：可观察、可判定的标准（如退出码为 0、`data/clean.csv` 存在、
   日志出现 `eval done`、指标不低于某阈值），并为每个判断条件标注材料来源。
2. 模型据此撰写章节正文，保持步骤号与命令原样，不得改写任何 flag。
3. 写完后运行 repro_check.py 核验命令一致性与顺序一致性。
