> **本文为合成示例文本**（challenge-0999879e · bundle-b 端到端验证专用）。
> 以下全部内容为虚构，文中含 5 处故意植入的问题，用于验证审查脚本，非真实论文。

# 基于轻量注意力网络的合成语音分类研究

## 摘要

本文提出一种轻量注意力网络用于合成语音分类。在自建数据集上，模型准确率达到 94.2%，
总训练时间为 12.5 h。已有工作 [1] 表明注意力机制对时序建模有效，[2] 进一步验证了
轻量结构的可行性，而 [5] 提出的动态卷积为本方法提供了直接动机。

**关键词**：合成语音；注意力；轻量网络

## 1 引言

合成语音检测是语音安全的重要问题。早期工作 [1] 使用深度残差结构取得进展，
[4] 在相同数据集上报告了可比结果。本文沿用上述设置，并参考 [5] 的动机设计网络。

## 2 方法

实验共纳入 n=120 条语音样本，按 8:2 划分训练集与验证集。模型包含 4 个注意力块，
隐藏维度 256。所有实验在单卡上完成，总训练时间为 12.5 h。

## 3 结果

在验证集上，模型最终准确率为 91.8%，差异具有统计显著性（p < 0.05）。
总训练时间为 12.5 h，与摘要所述一致。

## 4 结论

本文方法在 n=128 的样本规模上验证了有效性，准确率为 91.8%。未来将扩大数据规模。

## 参考文献

[1] Zhang W, Li H. Deep residual learning for synthetic speech detection. Journal of Synthetic Examples, 2021, 12(3): 45-56. doi: 10.1234/jse.2021.00345

[2] Wang L, Chen Y. Lightweight attention networks for audio classification. International Conference on Fictional Acoustics, 2022: 112-120. doi: 10.5678/icfa.2022.00078

[3] Kumar R, Smith J. A survey of spoofing countermeasures in speaker verification. Fictional Transactions on Audio Security, 2020, 8(1): 1-19. doi: 10.2345/ftas.2020.00011

[4] Wang L, Chen Y. Lightweight attention networks for audio classification. International Conference on Fictional Acoustics, 2022: 112-120. doi: 10.5678/icfa.2022.00078
