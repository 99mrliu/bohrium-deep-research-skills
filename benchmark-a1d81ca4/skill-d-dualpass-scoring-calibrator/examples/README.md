# 合成示例 SYNTHETIC EXAMPLE

本目录只包含编造的纳米材料表征文本与手工构造的评分输入，用于验证脚本链路；它不是任何隐藏案例的预制答案，也不得作为真实 benchmark 内容复用。

## 运行

```bash
bash examples/run_example.sh /tmp/a1d81ca4-d-demo-out
# 或不传参数，默认输出到当前目录 ./out
bash examples/run_example.sh
```

## 预期产物

- `work/rubric.json`：识别为 T2，预期 2 道题卡；
- `work/pass1_scores.json` 与 `work/pass2_scores.json`：Q2 的第二条证据机检失败，因此 evidence_anchoring=1；Q2 correctness 分别为 2 与 1；
- `work/disagreements.json`：检出一个分歧 `Q2 / correctness / 2→1`；
- `work/agreement_raw.json`：N=8，Po=7/8=0.875，Pe=44/64=0.6875，Cohen's kappa=(0.875-0.6875)/(1-0.6875)=0.600；
- `work/agreement_report.md`：记录第一条缺 `rationale` 的裁决被拒绝，第二条补全后接受；
- `work/final_scores.json`：`pending_count=0`，Q2 correctness 最终为 1；
- `output/result.json`：`status="成功"`，四个 contract 字段均已填充。

## κ 预期手算

8 个配对中 7 个一致，故 Po=7/8。pass1 的边际分布为 1 个 1 分、7 个 2 分；pass2 为 2 个 1 分、6 个 2 分。Pe=(1/8)(2/8)+(7/8)(6/8)=44/64=0.6875。κ=(0.875-0.6875)/(1-0.6875)=0.6。因 N=8，应同时阅读小样本警示。
