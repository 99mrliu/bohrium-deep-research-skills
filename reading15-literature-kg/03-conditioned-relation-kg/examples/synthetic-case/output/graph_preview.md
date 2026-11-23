# 图谱可读预览（SYNTHETIC 示例）

## 节点（9）
- `n_transA` [model] TransA —— 证据 SYN-P1/SYN-P1.abs.p1: “two translation models, TransA and TransB”
- `n_transB` [model] TransB —— 证据 SYN-P1/SYN-P1.abs.p1: “TransA and TransB, on the low-resource benchmark”
- `n_distilT` [model] DistilT —— 证据 SYN-P2/SYN-P2.abs.p1: “We present DistilT, a compact translation model”
- `n_lstmM` [model] LSTM-M —— 证据 SYN-P1/SYN-P1.s3.p2: “the LSTM-M baseline reaches 24.1 BLEU”
- `n_lowmt` [dataset] LowMT-100 —— 证据 SYN-P1/SYN-P1.s2.p1: “the LowMT-100 training split consisting of 10,000 sentence pairs”
- `n_wmt` [dataset] WMT (high-resource) —— 证据 SYN-P1/SYN-P1.s1.p1: “the high-resource WMT benchmark”
- `n_bleu` [metric] BLEU —— 证据 SYN-P1/SYN-P1.s2.p1: “evaluated with BLEU on the official test split”
- `n_lowres` [condition] low-resource 10k-pair budget —— 证据 SYN-P1/SYN-P1.abs.p1: “under a 10k sentence-pair training budget”
- `n_mt` [task] machine translation —— 证据 SYN-P1/SYN-P1.abs.p1: “two translation models”

## 边（9）
- `n_transA` outperforms → `n_transB`（voice=primary-results；条件：condition=n_lowres, dataset=n_lowmt, metric=n_bleu；测量 margin=2.6 BLEU）
- `n_transA` measured_on → `n_lowmt`（voice=primary-results；条件：condition=n_lowres, dataset=n_lowmt, metric=n_bleu；测量 score=32.4 BLEU）
- `n_transB` measured_on → `n_lowmt`（voice=primary-results；条件：condition=n_lowres, dataset=n_lowmt, metric=n_bleu；测量 score=29.8 BLEU） 【⚠冲突保留】
- `n_lstmM` measured_on → `n_lowmt`（voice=primary-results；条件：condition=n_lowres, dataset=n_lowmt, metric=n_bleu；测量 score=24.1 BLEU）
- `n_transB` measured_on → `n_wmt`（voice=cited-background；条件：condition=high-resource, dataset=n_wmt, metric=n_bleu；测量 score=41.2 BLEU） 【背景转述·非一手证据】
- `n_distilT` outperforms → `n_transB`（voice=primary-results；条件：condition=n_lowres, dataset=n_lowmt, metric=n_bleu；测量 margin=0.5 BLEU）
- `n_distilT` measured_on → `n_lowmt`（voice=primary-results；条件：condition=n_lowres, dataset=n_lowmt, metric=n_bleu；测量 score=31.0 BLEU）
- `n_transB` measured_on → `n_lowmt`（voice=primary-results；条件：condition=n_lowres, dataset=n_lowmt, metric=n_bleu；测量 score=30.5 BLEU） 【⚠冲突保留】
- `n_distilT` derives_from → `n_transB`（voice=primary-results；条件：condition=n_lowres, dataset=n_lowmt）

## 合并/不合并
- 合并：n_lowmt（依据：P1 写作 LowMT-100（SYN-P1.s2.p1），P2 写作 LowMT100（SYN-P2.s2.p1）；两者均指 10,000 句对训练划分，合并为单节点 n_lowmt，别名保留。）
- 不合并：n_transB ≠ TransB-ft（理由：P2 明确说明 TransB-ft 是 TransB 面向医学领域的微调变体且不在本次评估范围；同名前缀不等于同一对象，禁止合并，且 TransB-ft 不作为实体节点入图。）

## 共现记录（共现≠直接关系，不建边）
- n_transA、n_distilT：不建边：两篇仅共现于低资源翻译主题，P2 明确写到 no direct comparison between them has been reported；跨篇共现不是直接关系。
