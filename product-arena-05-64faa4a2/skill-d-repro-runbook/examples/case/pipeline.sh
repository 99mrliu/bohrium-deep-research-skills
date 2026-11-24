#!/usr/bin/env bash
# 训练流水线（合成示例）：预处理 -> 训练 -> 评估
set -e

export CUDA_VISIBLE_DEVICES=0

python preprocess.py \
    --input data/raw.csv \
    --output data/clean.csv \
    --min-len 5

python train.py --data data/clean.csv --model bert-base-chinese \
    --lr 2e-5 --epochs 3 --batch-size 16 --seed 42

python evaluate.py --data data/clean.csv --ckpt outputs/best.pt --split test
