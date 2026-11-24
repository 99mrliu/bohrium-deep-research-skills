# 方法与实验（草稿，合成示例）

我们在单张 A100 上完成全部实验，随后运行 python preprocess.py --input data/raw.csv --output data/clean.csv --min-len 5 并训练 python train.py --data data/clean.csv --model bert-base-chinese --lr 2e-4 --epochs 3 --batch-size 16 得到最优模型 outputs/best.pt，最后在测试集上评估得到准确率 0.879。
