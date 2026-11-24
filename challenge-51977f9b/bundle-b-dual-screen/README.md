# slr-dual-screen（bundle-b-dual-screen）

系统性文献综述技能：**双人独立筛选 + Cohen's kappa 一致性量化 + 分歧仲裁留痕 +
纳入集 SHA-256 冻结**。让"换一个人拿着同样的输入和记录，能复跑出基本一致
的纳入集"成为机器可检的流程属性。

## 布局

```
SKILL.md            技能本体（全链工作流程 + 输出合同映射 + 异常处理）
README.md           本页
scripts/
  parse_case.py       防御式解析 /input/case.json + task.md → case_summary.json
  scaffold_result.py  按 output_contract 生成 result.json 占位骨架（第 2 步落盘）
  screen_check.py     决策校验 S1–S5（字段/完整性/排除理由/uncertain/冻结保护）
  kappa.py            po/pe/Cohen's kappa + 逐条分歧清单（手写公式，--help 可查）
  adjudicate.py       仲裁校验 A1–A3 + frozen_set.json 冻结/验证（SHA-256 验篡）
  selfcheck           端到端自检：正负例断言 + 手算 kappa 比对 + py_compile
references/
  dual_screen_protocol.md   两轮双筛流程、pass 隔离纪律、条款代码表与版本纪律
  kappa_guide.md            公式、阈值解读、低 kappa 处置、患病率悖论
  adjudication_policy.md    仲裁人资格、rationale 最低信息、冻结/解冻留痕
examples/           合成示例（12 条虚构题录、两轮决策埋 3 处分歧、负例、手算 kappa）
```

## 快速开始

```bash
python3 scripts/selfcheck    # 全部断言通过 → exit 0
# 或对合成示例逐步运行：见 examples/README.md 的命令清单
```

## 限制

- 脚本只用 Python3 标准库；只做确定性工作，判定与写作由调用方模型完成；
- examples/ 全部为合成示例（synthetic, illustrative），不代表真实文献；
- kappa 存在患病率悖论等局限，须连同样本量如实写入 uncertainty
  （见 references/kappa_guide.md 第 4 节）。
