# 复现核验报告

章节：`examples/case/draft.md`　总体状态：**FAIL** ❌

## 复现清单（G1-G7）

| 编号 | 检查项 | 状态 | 说明 |
|---|---|---|---|
| G1 | 代码版本 | ❌ missing | 章节未写明代码版本（commit/tag/仓库地址）；若材料亦缺失，需标注为人工确认项。 |
| G2 | 运行环境（硬件/CUDA/框架/Python 版本） | ❌ missing | 部分环境线索未被章节覆盖：Python 3.10.12（README.md:5）；CUDA 12.1（README.md:6）；NVIDIA A100-SXM4-80GB（README.md:6）；cu121（README.md:6）；torch 2.1.0+cu121（README.md:6） |
| G3 | 依赖声明 | ❌ missing | 材料有 3 条依赖线索（如 torch==2.1.0），但章节未提及依赖安装方式。 |
| G4 | 完整命令 | ❌ missing | 以下真实命令未原样出现在章节中：`python train.py --data data/clean.csv --model bert-base-chinese --lr 2e-5 --epochs 3 --batch-size 16 --seed 42`（pipeline.sh:12）；`python evaluate.py --data data/clean.csv --ckpt outputs/best.pt --split test`（pipeline.sh:15） |
| G5 | 数据获取方式 | ✅ present | 章节覆盖 2 条数据线索。 |
| G6 | 随机种子 | ❌ missing | 材料中发现种子 42（如 pipeline.sh:12），但章节未完整写明。 |
| G7 | 预期产物与校验方式 | ✅ present | 章节提及预期指标/校验方式。 |

## 命令一致性

章节中提取命令候选 2 条，完成比对 2 条，一致 1 条；真实命令共 3 条。

## 顺序一致性

- 状态：ok；章节中 2 条可匹配命令的顺序与日志时间线一致。

## 发现项（3）

- ❌ **FAIL** [flag_value_mismatch]（第3行）：flag 值被改写：--lr 章节=2e-4 真实=2e-5
- ⚠️ **WARN** [steps_compressed]（全文）：同一段落命中 2 条真实命令，且至少一条被压入散文句中（命中：`python preprocess.py --input data/raw.csv --output data/clean.csv --min-len 5`；`python train.py --data data/clean.csv --model bert-base-chinese --lr 2e-5 --epochs 3 --batch-size 16 --seed 42`）；建议拆分为独立步骤并逐条恢复原命令。
- ⚠️ **WARN** [flag_omitted]（第3行）：章节命令省略了真实命令中的 flag：--seed=42
