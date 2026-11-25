# 双语对照（case=synthetic-evidence-demo）

## p001 [verdict=verified, basis=literal]
Consistent Estimators for Streaming Language Models

流式语言模型的一致估计量

## p002 [verdict=verified, basis=literal]
Abstract

摘要

## p003 [verdict=verified, basis=termbase]
Streaming language models must update without revisiting the full corpus. We prove that the sliding-window estimator (SWE) is consistent under drift bounded by Δ ≤ 0.1, and the regret grows as O(√T log T). The window size w trades memory against bias; in practice w = 512 works across tasks.

流式语言模型必须在不回访全量语料的前提下更新。我们证明：在漂移量 Δ ≤ 0.1 有界时，滑动窗口估计量（SWE）是一致的，且 regret 按 O(√T log T) 增长。窗口大小 w 在内存与偏差之间折中；实践中 w = 512 在各类任务上均适用。

## p004 [verdict=verified, basis=literal]
Methods

方法

## p005 [verdict=verified, basis=convention]
The SWE keeps a reservoir of w examples and reweights them by recency. When the feature � is corrupted by quantization noise, the estimator falls back to exponential decay with half-life h = 24 h. All hyperparameters follow the protocol of [4].

SWE 保留容量为 w 的样本库并按新近度重加权。当特征 � 被量化噪声破坏时，估计量退化为半衰期 h = 24 h 的指数衰减。全部超参数遵循文献 [4] 的方案。

## p006 [verdict=verified, basis=literal]
Figure 1. Regret versus window size for three drift regimes.

图 1. 三种漂移情形下 regret 随窗口大小的变化。
