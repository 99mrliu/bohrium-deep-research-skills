# 双通道渲染：PNG / SVG 等价要素与降级策略

figure_forge.py 的两条渲染通道共享**同一份几何计算**，保证视觉要素逐项等价、结果可复现。

## 通道选择

| 条件 | 通道 | 说明 |
|---|---|---|
| matplotlib 可 import（默认） | PNG | `Agg` 后端，figsize=(8.0,5.6)，dpi=150；仅用 matplotlib 内置 DejaVu 字体，不依赖系统字体 |
| matplotlib 不可用（try/except 优雅降级） | SVG | 纯 Python 手写 `<rect>/<line>/<circle>/<polyline>/<text>`，800×560 viewBox |
| `--force-svg` / `--force-png` | 强制 | 用于测试与复现；`--force-png` 在无 matplotlib 时 exit 2 |

## 等价要素清单（两通道逐项一致）

1. **箱体**：同一 Tukey 五数（Q1/中位/Q3 用线性插值分位数，与 numpy 默认一致）。
2. **须**：1.5×IQR **相邻值**（界内最极端观测），两通道同值。
3. **散点**：同一点集——n≤50 全点；n>50 同一确定性子样本（`random.Random(seed+gi*131).sample` 后排序）。
4. **抖动**：同一黄金比偏移 `((i*φ)%1 - 0.5)`，无随机数，跨通道逐点一致。
5. **坐标轴**：同一 y 范围（4%  Padding + nice ticks 1/2/2.5/5×10^k）、同一刻度值与格式。
6. **文字**：图题含检验方法；轴标签含变量名与单位；非 ASCII 文本统一走 `ascii_safe` 兜底
   （图内用 ASCII 占位，完整中文在 figures.md 图注中），两通道行为一致。
7. **颜色**：同一固定调色板（10 色，按组序取色）。
8. **确定性**：无任何系统字体、时区、随机源依赖；同 seed 重跑产物字节级一致（SVG 侧）/
   像素级一致（PNG 侧，同 matplotlib 版本）。

## 降级策略

- matplotlib 导入失败 → 自动切 SVG，figures.md 的 `channel` 字段记录实际通道，交付不中断。
- PNG 侧任何渲染异常 → 该图回退 SVG 并在 exceptions 记录（当前实现为整体通道选择，异常即整批 SVG）。
- 无图形环境也不阻断：图的几何数据（五数、点集、刻度）始终可从 analysis_data.json 复算。

## 审计钩子

`figure_audit.py` 对两通道分别验签：

- PNG：8 字节 magic（`\x89PNG\r\n\x1a\n`）+ IHDR 宽/高 ≥100 + 文件 ≥400 字节；
- SVG：前 2KB 含 `<svg`、ElementTree 可解析、根元素为 svg、viewBox ≥200×150、
  图元（rect/line/circle/polyline/path）≥5 个、文件 ≥400 字节。

占位图、空壳 SVG、伪扩展名都会命中 `BAD_SIGNATURE`。
