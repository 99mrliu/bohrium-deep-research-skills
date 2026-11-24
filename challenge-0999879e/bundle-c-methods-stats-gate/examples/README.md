# examples/ 说明

**合成示例，非正式案例结果。** 本目录输入与输出均为人工构造的合成示例文本，
仅用于验证 bundle-c-methods-stats-gate 的流程正确性，不代表任何真实案例的
审查结论。

- `synthetic-input/`：`case.json` + `task.md` + `manuscript.md`
  （稿件开头已显著标注"本文为合成示例文本"）。稿件植入 4 类问题：
  1. 结果节只有 p<0.05，无检验名称、无效应量、无 CI（报告不全）；
  2. 无对照组却在结论下"证明药物有效"的因果结论（方法缺陷 critical）；
  3. 方法节写 n=30 但未说明估算依据（报告不全 minor）；
  4. 对 5 项指标逐一显著性判断却未做多重比较校正（方法缺陷 major）。
- `synthetic-output/`：用 `synthetic-input/` 真实跑出的 `result.json` 与
  `review_report.md` 拷贝。预期检出：fail_design 2 条（critical 1 + major 1）、
  fail_reporting 6 条、unable_to_check 2 条、pass 6 条。

复现方式见 SKILL.md「分步工作流」。
