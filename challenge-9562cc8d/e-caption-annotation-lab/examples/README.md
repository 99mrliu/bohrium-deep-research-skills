# 最小调用示例（合成示例 / SYNTHETIC DEMO）

> 本目录数据由 `make_data.py` 用固定随机种子模拟生成，**是合成示例，
> 不是真实实验数据**，仅用于演示调用方式与输出结构。

## 数据

`synthetic_case/cell_assay.csv`：模拟三处理（vehicle/drug_low/
drug_high）细胞活性实验的存活率、凋亡率、ROS 与 ATP 测量，含 1 个
缺失值（"na"）与 1 条完全重复记录。重新生成：`python3 make_data.py`。

## 一条命令端到端运行

```bash
python3 ../scripts/run_case.py \
    --case synthetic_case/case.json \
    --input-dir synthetic_case \
    --work ./work --out ./out
```

## 预期输出

- `out/result.json`：`status=success`，含 `output_contract` 全部字段；
- `out/caption_audit.json`（核心交付）：图注机器审计——完备性（n、
  来源、清洗口径、须线含义）、图注数字与 statistics.json 一致、
  图例分组取值 1:1、面板编号连续（`all_passed=true`）；
- `out/check_report.json`：源数据复算一致；
- `out/fig1..fig5`：PNG/PDF/SVG 图件；
- `out/captions.md`：中文图注（程序化生成，可独立阅读）。

`expected_outputs/` 收录一次真实本地运行（2026-11-24，macOS，
Python 3.13 + matplotlib 3.11）的**文本**产物供比对；图件为二进制
产物，按平台约束不收入 bundle，请按上条命令本地复现。
