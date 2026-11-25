# Synthetic fixture task — not a formal case

这是 synthetic 合成示例，不是正式案例、作者原始数据、真实论文、作者原代码、物理实验或 PMLB。它只测试数据审计和 result 结构，不包含需要运行的两个候选数值方法，因此最终状态必须是 partial。

用于测试 claim 核对的三句合成规范原文如下，并非真实 PDF 引文：

- 第 1 页：“The combined synthetic table has 14 rows.”
- 第 1 页：“The synthetic task uses 3 features.”
- 第 1 页：“The synthetic split has 8 train rows and 6 test rows.”

train 和 test 故意共享两个 feature-only 键：键 `(5,0,0)` 的 target 相同，因而也是全行重复；键 `(7,0,0)` 的 target 不同，因而不是全行重复。该设计只验证计数代码，不提供任何真实数据来源、合成判定或标签泄露证明。
