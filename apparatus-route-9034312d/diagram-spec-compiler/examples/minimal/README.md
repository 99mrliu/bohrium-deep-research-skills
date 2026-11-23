# examples/minimal — 合成最小示例（非真实文献数据）

这是一个**完全虚构的合成示例**（spec 与图题中均已标注“合成示例”）：一套微型
催化加氢循环工艺流程，仅用于演示 spec 写法与编译效果，不对应任何真实论文。

## 覆盖的特性

- `kind: apparatus`，8 个节点（unit / data 两种节点形态，R-101 带子隔室 `parts`）
- 3 种 flow_type：material（实线）、energy（长虚线）、information（点线）
- 1 条物料回流边 `e06`（V-101 → E-101 循环氢，DFS 检测为回边，底部通道绕行 +
  强制虚线 + 反向箭头）
- 1 条信息回流边 `e08`（V-101 → P-101 联锁信号）
- 1 条跨层前向边 `e07`（H-101 → E-101，跨越一层，底部通道正向绕行）
- 每个节点/边均带 `source{locator,quote}` 溯源字段（内容为虚构合成文本）
- `canvas: "auto"` → 画布自动适配

## 调用方式

```bash
cd examples/minimal
python3 ../../scripts/check_spec.py figure_spec.json --report validation_report.json
python3 ../../scripts/compile_figure.py figure_spec.json --svg figure.svg \
    --log render_log.json --check-determinism
python3 ../../scripts/export_svg.py figure.svg --pdf /tmp/b.pdf --png /tmp/b.png \
    --report export_report.json
# 确定性验证：再编译一次并 diff
python3 ../../scripts/compile_figure.py figure_spec.json --svg /tmp/figure2.svg \
    --log /tmp/log2.json
diff figure.svg /tmp/figure2.svg   # 应无任何输出（字节一致）
```

## 文件说明

| 文件 | 说明 |
|---|---|
| `figure_spec.json` | 输入：声明式图稿 spec（手写，JSON DSL） |
| `validation_report.json` | `check_spec.py` 输出：校验报告 |
| `figure.svg` | `compile_figure.py` 输出：可编辑 SVG（分层/分组/真实文本） |
| `render_log.json` | 编译日志：画布、缩放、回边、图例条目、字体链、告警、SHA-256 |
| `export_report.json` | 导出报告：本包内只保留报告；PDF/PNG 产物请导出到临时目录 |

## 预期校验结果

- errors = 0、warnings = 0（本示例所有节点/边均带完整 source 与非空 label）。
- source 字段缺失等轻量问题只会产生 warning、不阻塞编译——溯源是"必须记录"
  但不是门禁。
