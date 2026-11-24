# interpretation-tribunal（Bundle D）

Bohrium Playground challenge-c0e1e220「统计分析与结果解读」五方向 Skill
bundle 之一。重心：**结果解释措辞纪律与结论-证据绑定**。

- `pipeline_d.py` 一键完成 数据接入 → 清洗 → 假设门控检验 → 效应量/CI →
  result.json（9 契约字段 + claims 证据绑定数组）+ report.md + digest.md；
- `wording_lint.py` 把「统计显著≠实际意义、p 值不能写成证明、CI 不是个体
  取值范围、partial 必须有不确定性说明」变成机器可执行的 lint（5 个违例码）；
- `claim_bind.py` 强制报告每句结论以 `[ev:Hk]` 结尾，并与
  result.json.claims 在方向、显著性、数值、逐字文本四个层面一致。

## 文件清单

见 SKILL.md「文件清单」。全部 UTF-8 文本，纯标准库（Python 3.9+），
无第三方依赖（scipy 仅开发期交叉校验用，不参与运行）。

## 快速验证

```bash
bash examples/run_example.sh   # 好例 exit 0；5 组埋雷全部命中预期违例码
```

## 合成示例声明

examples/ 下全部数据由 make_synthetic.py 用固定种子合成（大样本小差异，
「显著但不重要」场景），非真实实验数据；example_output/ 为脚本真实跑出的
文本产物。

## 维护

- 版本：1.0.0（statcore_d / pipeline_d / wording_lint / claim_bind 同版）。
- 展示精度约定（p 4 位、效应量/CI/差值 3 位）同时写在
  references/claim-evidence-binding.md；修改 pipeline 模板时必须同步
  wording_lint / claim_bind 的正则。
- 变更后须重跑 examples/run_example.sh 与三个仿真案例
  （iris / concrete / wine）的 harness 仿真。
