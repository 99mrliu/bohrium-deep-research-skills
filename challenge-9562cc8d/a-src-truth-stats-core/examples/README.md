# 最小调用示例（合成示例 / SYNTHETIC DEMO）

> 本目录数据由 `make_data.py` 用固定随机种子模拟生成，**是合成示例，
> 不是真实实验数据**，仅用于演示调用方式与输出结构。

## 数据

`synthetic_case/plant_growth.csv`：模拟三组施肥处理（对照/低肥/高肥）
各 30 株的株高、叶数、根质量、叶绿素测量；故意含 2 个缺失值与 1 条
完全重复记录，用于演示清洗留痕。重新生成：`python3 make_data.py`。

## 一条命令端到端运行

```bash
python3 ../scripts/run_case.py \
    --case synthetic_case/case.json \
    --input-dir synthetic_case \
    --work ./work --out ./out
```

## 预期输出

- `out/result.json`：`status=success`，含 `output_contract` 全部字段；
- `out/verification_report.json`：第二套独立实现（Welford/type-7）
  复核约百余项全部通过（`all_passed=true`）；
- `out/check_report.json`：重读源 CSV 复算 mean/n/r 一致；PNG 300dpi、
  PDF 字体嵌入、SVG 活文本；
- `out/fig1..fig5`：PNG/PDF/SVG 图件（含缺失分布图 fig5）；
- `out/captions.md`：中文图注（n、须线含义、来源、清洗口径）。

`expected_outputs/` 收录一次真实本地运行（2026-11-24，macOS，
Python 3.13 + matplotlib 3.11）的**文本**产物供比对；图件为二进制
产物，按平台约束不收入 bundle，请按上条命令本地复现。
