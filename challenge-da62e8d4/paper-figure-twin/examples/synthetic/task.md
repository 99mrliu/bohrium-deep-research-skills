# 最小合成任务

这不是论文复现，也不是作者代码评价。`paper_figure.svg` 是组织方自创的文本 SVG“合成论文原图”；paper points 是手工指定的 pixel 采样。

实际运行两个候选数值方法：candidate_a 应接近采样曲线，candidate_b 带有递增系统偏差。使用 `spec.json` 中比较前已声明的容差 RMSE ≤ 0.05 mV、MAE ≤ 0.05 mV、max abs error ≤ 0.05 mV。仅在共同 x 区间内的 paper x 处对 candidate 做线性插值，不外推；误差定义为 candidate − paper。

最终需要 comparison.json、mapping.json、report.md、result.json、每个 pair 的 overlay/error SVG 和真实 PNG，以及 side-by-side SVG/PNG。合成图满足容差只能称为“对手工合成采样点的数值一致”，不能称论文复现。
