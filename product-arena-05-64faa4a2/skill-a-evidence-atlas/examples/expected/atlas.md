# 材料清单与参数台账摘要（atlas.md）

- 输入目录：`/Users/liuhengshen/Desktop/bhr_product/writing09-5dir/bundles/skill-a-evidence-atlas/examples/case`
- 文件总数：4（已解析 4 / 未解析 0）
- 候选参数：24；取值冲突：1
- 解析备注：
  - config.yaml: 使用 PyYAML 结构化解析

## 文件清单

| 文件 | 大小(B) | sha256(前12) | 类型 | 状态 | 备注 |
| --- | ---: | --- | --- | --- | --- |
| `README.md` | 678 | `563256eef2a2` | markdown | parsed |  |
| `config.yaml` | 302 | `80d9cdd4b12d` | yaml | parsed |  |
| `draft.md` | 622 | `1413449c84b3` | markdown | parsed |  |
| `train.log` | 424 | `620fa19ae286` | log | parsed |  |

## 参数候选表

| ID | 名称 | 取值 | 单位 | 类别 | 来源(file:line) | 原文 |
| --- | --- | --- | --- | --- | --- | --- |
| P001 | `model` | `resnet18` | — | parameter | `config.yaml:3` | model: resnet18 |
| P002 | `optimizer` | `adam` | — | parameter | `config.yaml:4` | optimizer: adam |
| P003 | `learning_rate` | `0.0003` | — | parameter | `config.yaml:5` | learning_rate: 0.0003 |
| P004 | `weight_decay` | `0.0001` | — | parameter | `config.yaml:6` | weight_decay: 0.0001 |
| P005 | `epochs` | `50` | — | parameter | `config.yaml:7` | epochs: 50 |
| P006 | `batch_size` | `32` | — | parameter | `config.yaml:8` | batch_size: 32 |
| P007 | `seed` | `42` | — | parameter | `config.yaml:9` | seed: 42 |
| P008 | `train_split` | `0.8` | — | parameter | `config.yaml:10` | train_split: 0.8 |
| P009 | `val_split` | `0.1` | — | parameter | `config.yaml:11` | val_split: 0.1 |
| P010 | `test_split` | `0.1` | — | parameter | `config.yaml:12` | test_split: 0.1 |
| P011 | `device` | `cuda:0` | — | parameter | `config.yaml:13` | device: cuda:0 |
| P012 | `flag:config` | `config.yaml` | — | flag | `train.log:1` | [run] command: python train.py --config config.yaml --epochs 50 --batch-size 32 |
| P013 | `flag:epochs` | `50` | — | flag | `train.log:1` | [run] command: python train.py --config config.yaml --epochs 50 --batch-size 32 |
| P014 | `flag:batch-size` | `32` | — | flag | `train.log:1` | [run] command: python train.py --config config.yaml --epochs 50 --batch-size 32 |
| P015 | `python` | `3.10` | — | version | `train.log:2` | [run] environment: python 3.10, torch 2.1, cuda 12.1 |
| P016 | `torch` | `2.1` | — | version | `train.log:2` | [run] environment: python 3.10, torch 2.1, cuda 12.1 |
| P017 | `cuda` | `12.1` | — | version | `train.log:2` | [run] environment: python 3.10, torch 2.1, cuda 12.1 |
| P018 | `learning_rate` | `0.001` | — | parameter | `train.log:3` | [run] effective config loaded: learning_rate=0.001 weight_decay=0.0001 seed=42 |
| P019 | `weight_decay` | `0.0001` | — | parameter | `train.log:3` | [run] effective config loaded: learning_rate=0.001 weight_decay=0.0001 seed=42 |
| P020 | `seed` | `42` | — | parameter | `train.log:3` | [run] effective config loaded: learning_rate=0.001 weight_decay=0.0001 seed=42 |
| P021 | `train_loss` | `0.213` | — | parameter | `train.log:5` | [epoch 49/50] train_loss=0.213 val_loss=0.305 |
| P022 | `val_loss` | `0.305` | — | parameter | `train.log:5` | [epoch 49/50] train_loss=0.213 val_loss=0.305 |
| P023 | `val_acc` | `0.873` | — | parameter | `train.log:6` | [done] final val_acc=0.873 |
| P024 | `path` | `/app/work/ckpt/resnet18_final.pt` | — | path | `train.log:7` | [done] checkpoint saved to /app/work/ckpt/resnet18_final.pt |

## 取值冲突（同名参数多处取值不一致，须人工裁决后方可写入正文）

- `learning_rate`：
  - 取值 `0.0003` ← `config.yaml:5`
  - 取值 `0.001` ← `train.log:3`

## 未解析 / 跳过清单

（无）
