# 六要素缺口审计报告

- 材料目录: `/Users/liuhengshen/Desktop/bhr_product/writing09-5dir/bundles/skill-c-gap-tribunal/examples/case`
- 扫描文件数: 3

| 要素 | 证据状态 | 命中数(截断) |
| --- | --- | --- |
| 步骤 (steps) | thin | 1 |
| 实验设置 (setup) | sufficient | 6 |
| 参数与来源 (params) | sufficient | 12 |
| 数据集与划分 (dataset) | thin | 5 |
| 对照 (baselines) | thin | 1 |
| 复现与限制 (repro) | thin | 2 |

## 编号缺口清单（待作者确认）

- **G001** [步骤 / thin] 请补充方法的完整执行步骤（命令行或编号步骤）：当前材料中步骤证据薄弱，章节若直接给出步骤将被视为无来源陈述。
- **G002** [数据集与划分 / thin] 请说明数据集的确切版本与获取方式（版本号/下载链接/校验值）：当前材料仅见数据集名称或划分信息，版本证据薄弱。（缺失面向：版本与获取）
- **G003** [对照 / thin] 请补充对照设置（基线名称、来源与配置；是否有消融）：当前材料中对照证据薄弱。
- **G004** [复现与限制 / thin] 请补充复现所需的完整信息（运行命令、依赖清单、数据获取途径）：当前材料中复现证据薄弱。（缺失面向：获取途径）

## 命中证据明细（file:line）

### 步骤 (steps) — thin
- `draft.md:5` [流程词] 首先对图像做预处理，然后训练分类器，最后在测试集上评估。

### 实验设置 (setup) — sufficient
- `config.yaml:8` [随机性控制] seed: 42
- `draft.md:9` [硬件/驱动] 硬件环境为 A100。训练 300 轮，批大小 64，学习率 0.001，随机种子 42。
- `draft.md:9` [随机性控制] 硬件环境为 A100。训练 300 轮，批大小 64，学习率 0.001，随机种子 42。
- `train.log:1` [随机性控制] 2024-05-01 10:00:00 run started with epochs=500 lr=0.001 batch_size=64 seed=42
- `train.log:2` [硬件/驱动] 2024-05-01 10:00:01 env cuda=11.8 torch=2.1 python=3.10 gpu=A100
- `train.log:2` [框架与版本] 2024-05-01 10:00:01 env cuda=11.8 torch=2.1 python=3.10 gpu=A100

### 参数与来源 (params) — sufficient
- `config.yaml:5` [超参数名] epochs: 300
- `config.yaml:6` [超参数名] lr: 0.001
- `config.yaml:7` [超参数名] batch_size: 64
- `draft.md:9` [超参数名] 硬件环境为 A100。训练 300 轮，批大小 64，学习率 0.001，随机种子 42。
- `draft.md:10` [参数赋值] 注：训练日志显示实际运行为 500 轮，与配置不一致，待裁决。
- `draft.md:14` [参数赋值] 对比基线准确率为 91.7%。
- `train.log:1` [超参数名] 2024-05-01 10:00:00 run started with epochs=500 lr=0.001 batch_size=64 seed=42
- `train.log:1` [参数赋值] 2024-05-01 10:00:00 run started with epochs=500 lr=0.001 batch_size=64 seed=42
- `train.log:2` [参数赋值] 2024-05-01 10:00:01 env cuda=11.8 torch=2.1 python=3.10 gpu=A100
- `train.log:3` [超参数名] 2024-05-01 10:00:02 [epoch 1/500] loss=0.912 acc=0.61
- `train.log:3` [参数赋值] 2024-05-01 10:00:02 [epoch 1/500] loss=0.912 acc=0.61
- `train.log:4` [超参数名] 2024-05-01 10:05:40 [epoch 2/500] loss=0.744 acc=0.70

### 数据集与划分 (dataset) — thin
- `config.yaml:4` [数据集名] dataset: cifar10
- `config.yaml:9` [划分信息] train_ratio: 0.8
- `config.yaml:10` [划分信息] val_ratio: 0.1
- `config.yaml:11` [划分信息] test_ratio: 0.1
- `draft.md:5` [划分信息] 首先对图像做预处理，然后训练分类器，最后在测试集上评估。

### 对照 (baselines) — thin
- `draft.md:14` [基线词] 对比基线准确率为 91.7%。

### 复现与限制 (repro) — thin
- `draft.md:16` [限制词] ## 限制
- `draft.md:18` [限制词] 本方法在某些情况下可能不适用，未来工作将进一步验证。
