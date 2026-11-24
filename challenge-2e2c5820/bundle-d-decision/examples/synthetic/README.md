# 合成示例（合成示例，非正式案例数据）

本目录是一个**手工构造**的最小端到端示例，用于验证 Bundle D 的全部脚本可运行、
校验规则可触发。**所有课题内容、合同、价格、档期、分数、风险均为虚构，不是正式案例数据。**

## 场景

课题：慢性社交挫败应激（CSDS）后小鼠社交行为与海马神经元活性研究。3 个候选版本：

| 版本 | 内容 | 伦理涉及 | 演示重点 |
|---|---|---|---|
| v1 | 离体细胞系 + 公开数据集替代版 | 危险试剂=true | 基准加权分第 1（3.40） |
| v2 | 小鼠行为学观察版 | 动物实验=**undetermined** → 确认项 | 与 v1 仅差 0.05，敏感性分析中“假设与变量 +20%”情景发生**排名翻转** |
| v3 | 动物行为学+组织学完整版 | 动物实验=true、危险试剂=true → **需办理** IACUC / EHS 备案 | 审批前置条件措辞演示 |

## 输入文件

- `case.json`：含 3 版本方案、组织方合同、有限参数域、伦理涉及提示、output_contract（5 个字段）。
- `task.md`：任务说明。
- `scores.json`：逐版 7 维证据化打分（每格带 locator + 逐字 quote，quote 均摘自 case.json 原文）。
- `risks.json`：8 条风险，5 字段齐全；第 1、2 条触发信号为**有意的近似重复**，用于演示 lint 警告。
- `involvement.json`：逐版伦理涉及状态。
- `conditions.json`：三版均为有条件可行（v1：1 条危化品备案条件；v2：3 条完整条件；v3：2 条完整条件）。

## 运行

```bash
bash run_example.sh
```

产物写入 `output/`：`inspection.json`、`decision_matrix.md`、`ranking.json`、
`risk_register.md`、`ethics_paths.md`、`conditions_list.md`、`overall_verdict.json`、`result.json`。

`output/` 中当前的内容即为一次真实运行的产物（见 `result.json` 的 change_record）。
