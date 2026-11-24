# 命令与环境线索挖掘结果

材料目录：`examples/case`；扫描文件数：5；线索总数：35。

类型统计：command=6, data=9, dep=3, env=15, seed=2

| id | 类型 | 内容 | 来源 | 日志时间 |
|---:|---|---|---|---|
| 1 | env | `CUDA_VISIBLE_DEVICES=0` | pipeline.sh:5 | - |
| 2 | env | `export CUDA_VISIBLE_DEVICES=0` | pipeline.sh:5 | - |
| 3 | command | `python preprocess.py --input data/raw.csv --output data/clean.csv --min-len 5` | pipeline.sh:7 | - |
| 4 | data | `data/raw.csv` | pipeline.sh:7 | - |
| 5 | command | `python train.py --data data/clean.csv --model bert-base-chinese --lr 2e-5 --epochs 3 --batch-size 16 --seed 42` | pipeline.sh:12 | - |
| 6 | data | `data/clean.csv` | pipeline.sh:12 | - |
| 7 | seed | `seed=42` | pipeline.sh:12 | - |
| 8 | command | `python evaluate.py --data data/clean.csv --ckpt outputs/best.pt --split test` | pipeline.sh:15 | - |
| 9 | data | `data/clean.csv` | pipeline.sh:15 | - |
| 10 | data | `https://example.org/datasets/raw.csv` | README.md:1 | - |
| 11 | data | `wget https://example.org/datasets/raw.csv -O data/raw.csv` | README.md:1 | - |
| 12 | env | `Python 3.10.12` | README.md:5 | - |
| 13 | env | `A100` | README.md:6 | - |
| 14 | env | `CUDA 12.1` | README.md:6 | - |
| 15 | env | `NVIDIA A100-SXM4-80GB` | README.md:6 | - |
| 16 | env | `cu121` | README.md:6 | - |
| 17 | env | `torch 2.1.0+cu121` | README.md:6 | - |
| 18 | data | `https://example.org/datasets/raw.csv` | README.md:12 | - |
| 19 | env | `A100` | draft.md:3 | - |
| 20 | env | `CUDA 12.1` | run.log:1 | 2025-06-01 09:00:03 |
| 21 | env | `Python 3.10.12` | run.log:1 | 2025-06-01 09:00:03 |
| 22 | env | `cu121` | run.log:1 | 2025-06-01 09:00:03 |
| 23 | env | `torch 2.1.0+cu121` | run.log:1 | 2025-06-01 09:00:03 |
| 24 | env | `A100` | run.log:2 | 2025-06-01 09:00:03 |
| 25 | env | `NVIDIA A100-SXM4-80GB` | run.log:2 | 2025-06-01 09:00:03 |
| 26 | command | `python preprocess.py --input data/raw.csv --output data/clean.csv --min-len 5` | run.log:3 | 2025-06-01 09:00:04 |
| 27 | data | `data/raw.csv` | run.log:3 | 2025-06-01 09:00:04 |
| 28 | command | `python train.py --data data/clean.csv --model bert-base-chinese --lr 2e-5 --epochs 3 --batch-size 16 --seed 42` | run.log:5 | 2025-06-01 09:00:42 |
| 29 | data | `data/clean.csv` | run.log:5 | 2025-06-01 09:00:42 |
| 30 | seed | `seed=42` | run.log:5 | 2025-06-01 09:00:42 |
| 31 | command | `python evaluate.py --data data/clean.csv --ckpt outputs/best.pt --split test` | run.log:7 | 2025-06-01 10:12:58 |
| 32 | data | `data/clean.csv` | run.log:7 | 2025-06-01 10:12:58 |
| 33 | dep | `torch==2.1.0` | requirements.txt:1 | - |
| 34 | dep | `transformers==4.38.2` | requirements.txt:2 | - |
| 35 | dep | `numpy>=1.24` | requirements.txt:3 | - |
