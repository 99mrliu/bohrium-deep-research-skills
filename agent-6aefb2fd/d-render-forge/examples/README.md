# 最小调用示例（合成示例 / SYNTHETIC EXAMPLE）

> 本示例使用固定种子程序生成的玩具数据（3 组 ×50 行，与任何正式案例无关），
> 仅用于说明接口与流程；输出**不是**正式案例结果。

## 运行

```
python3 examples/make_example.py /tmp/rf-example
```

## 示例做了什么

1. 生成玩具 cleaned 表与 `statistics.json`（group_compare 模式，m1 显著、
   m2 不显著）。
2. `figure_forge.py` 按 spec 渲染 3 张图：分组箱线+散点（m1、m2）、Spearman
   热图、区分度横向条形图（值轴零起点）；每张非空且 manifest 记录谱系。
3. `report_forge.py scaffold` 机器渲染统计表格；填写的小节只引用有源数字，
   `verify` 通过。
4. 把报告中 η²=0.9883 篡改为 0.9812 → `verify` 以退出码 6 阻断并定位
   `UNSOURCED_NUMBER: 0.9812`。

## 预期打印（节选）

```
FIGURE_FORGE_STATUS: ok figures=3 manifest=/tmp/rf-example/output/figures/figures_manifest.json
CHECK OK: 3 张图渲染成功且非空，manifest 谱系完整（含 axis_policy 与 spec 原文）
REPORT_VERIFY_STATUS: ok all ≥3-sig-digit numbers traced to sources
CHECK OK: scaffold 渲染 + 填写后 verify 通过（所有 ≥3 位有效数字有源）
UNSOURCED_NUMBER: 0.9812
CHECK OK: 无源数字 0.9812 被 verify 阻断（退出码 6）
SYNTHETIC EXAMPLE PASSED -> /tmp/rf-example
```
