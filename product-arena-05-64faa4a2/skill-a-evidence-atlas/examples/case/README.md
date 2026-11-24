# 合成示例材料（合成示例，非正式案例结果）

本目录是一组**人工编造**的最小材料，仅用于演示 evidence-atlas 的流水线，
不代表任何真实实验。

- `config.yaml`：训练配置（学习率、epoch、批大小、划分比例、随机种子等）。
- `train.log`：训练日志。其中 `learning_rate` 与 config.yaml **故意不一致**，
  用于演示 atlas_scan 的冲突检测。
- `draft.md`：待修章节草稿。其中 dropout 比率是一个**材料中不存在的编造数值**，
  用于演示 ledger_check 能将其判为 UNSOURCED；
  其余数值均可在 config.yaml / train.log 中定位，应判为 BOUND。
