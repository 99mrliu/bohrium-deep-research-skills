# 最小调用示例（合成示例 / SYNTHETIC DEMO）

> 本目录数据由 `make_data.py` 用固定随机种子模拟生成，**是合成示例，
> 不是真实实验数据**，仅用于演示调用方式与输出结构。

## 数据

`synthetic_case/enzyme_kinetics.csv`：模拟三种酶的米氏动力学测量
（底物浓度、初速度、温度、pH），含 1 个缺失值与 2 条完全重复记录。
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
- `out/export_audit.json`（核心交付）：逐字节导出审计——PNG pHYs
  dpi=300、物理宽 89mm；PDF 字体嵌入、MediaBox 89mm；SVG 活文本、
  89mm；Okabe-Ito 灰度亮度差（蓝/绿临界对给出冗余编码 advisory）；
- `out/check_report.json`：源数据复算一致；
- `out/fig1..fig5`：PNG/PDF/SVG 图件；
- `out/captions.md`：中文图注。

`expected_outputs/` 收录一次真实本地运行（2026-11-24，macOS，
Python 3.13 + matplotlib 3.11）的**文本**产物供比对；图件为二进制
产物，按平台约束不收入 bundle，请按上条命令本地复现。
