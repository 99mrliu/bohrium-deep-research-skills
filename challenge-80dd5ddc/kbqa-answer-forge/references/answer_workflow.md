# 问答生产线操作细则（模型侧）

脚本负责确定性环节（索引、检索、核验、组装）；模型负责四个判断环节。
每个环节的判断都落到文件，保证过程可复核。

## 环节 1：问题分解（模型，记入 work/notes_qX.md）

- 把每个问题拆成 1–3 个可独立验证的子论断，每个子论断标注所需证据类型
  （数值 / 定义 / 版本指认 / 名录 / 结论）。
- 为每个子论断拟定 2–4 个检索式：原词、同义词、关键数值、中英对照。

## 环节 2：检索与选段（脚本 qa_retrieve + 模型选段）

- 每个检索式都跑 qa_retrieve.py；**零命中也是结果**，检索日志自动留痕。
- 从命中行及上下文窗口中截取候选引文：必须整句或完整短语，不截半句。
- 同一事实多个版本都有时，只从当前版本取引文（历史版本仅用于对比说明，
  引用时明示"历史版本"）。

## 环节 3：论断-证据配对（模型，写 work/citations.jsonl + work/answers.json）

- 一个论断至少一条引文；关键数值论断的引文必须含该数值本身。
- 引文不支持论断中的任何修饰词（"首次""最优""显著提高"），除非引文
  原文就有该措辞；否则删修饰词或标 paraphrase。
- 库中无依据：answer 写"库中无依据"，state 由 finalize 判为 no_basis，
  uncertainty 写清缺什么（缺哪类文件 / 哪个版本 / 哪个字段）。

## 环节 4：核验后修订（模型，按 citation_verification.json 执行）

- 逐条处理 pass=false：按 references/citation_contract.md 的处置规则改写
  或降级，改写后**必须重跑 qa_verify.py**，直到 verdict=all_passed
  或该论断降级为 unsupported。
- 最后跑 qa_finalize.py 组装 result.json；status 由 finalize 按硬闸门
  判定，模型不得手工把 status 改成 completed。

## 预算纪律（64 次模型请求 / 900 秒）

- qa_init 之后骨架 result.json 已在 /app/output，任何时候中断都有诚实
  的部分交付。
- 建议分配：读题+分解 ≤6 次；每题检索+选段 ≤6 次；citations/answers
  撰写 ≤8 次；核验修订 ≤6 次；收尾 ≤2 次。剩余不足 1/3 时停止开新题，
  已完成的题先 finalize。
