# examples/ — 合成示例（非正式案例结果）

本目录演示 gap-tribunal 三个脚本的端到端用法。**全部为合成材料，非任何正式案例的运行结果。**

## 材料设计（examples/case/）

| 文件 | 刻意埋入的问题 |
| --- | --- |
| `config.yaml` | `epochs: 300`，与日志冲突；数据集只有名字（cifar10），**刻意缺版本/获取方式** |
| `train.log` | 首行 `epochs=500`（与 config 的 300 冲突）；`loss=` 逐 epoch 变化（应被识别为**观测**而非冲突） |
| `draft.md` | 空泛限制句（“某些情况下可能不适用”“未来工作将进一步验证”）；无来源数值（基线准确率 91.7%）；未点名任何 G 编号 |

## 运行

```bash
bash examples/run_example.sh
```

产物写入 `examples/expected/`：

- `gaps.json` / `gaps.md` — 六要素审计。预期：`dataset` 因缺“版本与获取”面向判 **thin**，
  `repro` 因缺“获取途径”判 **thin**，`baselines` 仅草稿一处提及判 **thin**，各生成编号缺口 G00x。
- `conflicts.json` / `conflicts.md` — 预期：抓到 `epochs` 冲突（config.yaml:5 = 300 vs
  train.log:1 = 500，建议取日志值 500，blocking=true）；`loss` 逐 epoch 序列列为 **observation**，
  不误报为冲突。
- `hedge_report.json` / `hedge_report.md` — 预期 **FAIL**（退出码 2）：抓出空泛套话
  命中 3 处（ZH01/ZH02/ZH05，同一句多重命中）、1 个无来源数值（91.7）、全部 G 编号未点名。

## 判定规则速查

- 缺口状态阈值：0 命中 = missing；≥3 命中且 ≥2 类探针且 must 组满足 = sufficient；其余 = thin。
- 冲突 vs 观测：同文件同键多值 = 观测；跨文件单值不一致 = 冲突。
- 裁决优先级：运行日志 > 配置文件 > 脚本默认 > 草稿/转述（详见 `references/adjudication_rules.md`）。
