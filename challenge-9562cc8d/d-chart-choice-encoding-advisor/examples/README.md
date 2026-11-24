# 最小调用示例（合成示例 / SYNTHETIC DEMO）

> 本目录数据由 `make_data.py` 用固定随机种子模拟生成，**是合成示例，
> 不是真实实验数据**，仅用于演示调用方式与输出结构。

## 数据

`synthetic_case/soil.csv`：模拟四个采样点的土壤含水率、pH、有机质、
硝态氮测量，含 1 个缺失值与 1 条完全重复记录。重新生成：
`python3 make_data.py`。

## 一条命令端到端运行

```bash
python3 ../scripts/run_case.py \
    --case synthetic_case/case.json \
    --input-dir synthetic_case \
    --work ./work --out ./out
```

## 预期输出

- `out/result.json`：`status=success`，含 `output_contract` 全部字段；
- `out/chart_decisions.json`（核心交付）：每个图件的选定图型、编码
  映射、选择理由、被否决图型及否决理由（如 dynamite plot、双 y 轴、
  3D 散点、未固定色标热图），全局强制约束（禁饼图、零基线、色盲
  安全）与对数轴决策记录；
- `out/check_report.json`：源数据复算一致；
- `out/fig1..fig5`：PNG/PDF/SVG 图件（按决策文件渲染）；
- `out/captions.md`：中文图注。

`expected_outputs/` 收录一次真实本地运行（2026-11-24，macOS，
Python 3.13 + matplotlib 3.11）的**文本**产物供比对；图件为二进制
产物，按平台约束不收入 bundle，请按上条命令本地复现。
