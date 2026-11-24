# 最小调用示例（合成示例 / SYNTHETIC DEMO）

> 本目录数据由 `make_data.py` 用固定随机种子模拟生成，**是合成示例，
> 不是真实实验数据**，仅用于演示调用方式与输出结构。

## 数据

`synthetic_case/absorption.csv`：模拟三批次浓度-吸光度测量（近似
比尔-朗伯关系），含 2 个缺失值（空与 "?"）与 1 条完全重复记录。
重新生成：`python3 make_data.py`。

## 一条命令端到端运行

```bash
python3 ../scripts/run_case.py \
    --case synthetic_case/case.json \
    --input-dir synthetic_case \
    --work ./work --out ./out
```

## 预期输出

- `out/result.json`：`status=success`，含 `output_contract` 全部字段；
- `out/replay_report.json`（核心交付）：流水线在隔离目录完整复跑
  一遍，全部文本产物与 PNG 逐字节一致，PDF/SVG 归一化挥发性元数据
  后一致（`all_passed=true`）；
- `out/ledger.json`：阶段检查点序列 + 全部产物 SHA-256 清单；
- `out/check_report.json`：源数据复算一致；
- `out/fig1..fig5`：PNG/PDF/SVG 图件；
- `out/captions.md`：中文图注。

`expected_outputs/` 收录一次真实本地运行（2026-11-24，macOS，
Python 3.13 + matplotlib 3.11）的**文本**产物供比对；图件为二进制
产物，按平台约束不收入 bundle，请按上条命令本地复现。
