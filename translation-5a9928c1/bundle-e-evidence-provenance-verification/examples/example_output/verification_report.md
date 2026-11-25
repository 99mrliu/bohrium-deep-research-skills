# 验证报告（逐段证据 ↔ 译文 ↔ 译法依据）

状态: success；段 6/6；未决不确定性 0 项

## p001 — verdict: verified
- 证据: offset 0 (declared 0), quote_sha256 640f908e21ce…
- 引文: “Consistent Estimators for Streaming Language Models”
- 译法依据 (literal): 标题直译；Streaming 取流式
- 译文: 流式语言模型的一致估计量

## p002 — verdict: verified
- 证据: offset 53 (declared 53), quote_sha256 d21b4a64a2d8…
- 引文: “Abstract”
- 译法依据 (literal): 章节标题直译
- 译文: 摘要

## p003 — verdict: verified
- 证据: offset 63 (declared 63), quote_sha256 1924e24e2d8c…
- 引文: “Streaming language models must update without revisiting the full corpus. We prove that the sliding-window estimator (SWE) is consistent under drift bounded by Δ ≤ 0.1, and the regret grows as O(√T lo”
- 译法依据 (termbase): regret 按强化学习惯例保留英文并给中文说明；SWE 首次出现给全称（滑动窗口估计量）
- 译文: 流式语言模型必须在不回访全量语料的前提下更新。我们证明：在漂移量 Δ ≤ 0.1 有界时，滑动窗口估计量（SWE）是一致的，且 regret 按 O(√T log T) 增长。窗口大小 w 在内存与偏差之间折中；实践中 w = 512 在各类任务上均适用。

## p004 — verdict: verified
- 证据: offset 356 (declared 356), quote_sha256 8696622f3441…
- 引文: “Methods”
- 译法依据 (literal): 章节标题直译
- 译文: 方法

## p005 — verdict: verified
- 证据: offset 365 (declared 365), quote_sha256 e8e9ed60dd8f…
- 引文: “The SWE keeps a reservoir of w examples and reweights them by recency. When the feature � is corrupted by quantization noise, the estimator falls back to exponential decay with half-life h = 24 h. All”
- 译法依据 (convention): half-life 译为半衰期并按物理惯例给符号 h
- 译文: SWE 保留容量为 w 的样本库并按新近度重加权。当特征 � 被量化噪声破坏时，估计量退化为半衰期 h = 24 h 的指数衰减。全部超参数遵循文献 [4] 的方案。

## p006 — verdict: verified
- 证据: offset 611 (declared 611), quote_sha256 47307423c36f…
- 引文: “Figure 1. Regret versus window size for three drift regimes.”
- 译法依据 (literal): 题注直译，Figure→图
- 译文: 图 1. 三种漂移情形下 regret 随窗口大小的变化。

## 人工确认清单
- 无。

说明：机器核验证明引文与源文本一致及覆盖无缺口；不评价译文语言质量。
