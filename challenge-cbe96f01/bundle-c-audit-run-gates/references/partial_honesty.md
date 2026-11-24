# 诚实 partial 的判定与写法

## 何时必须标 partial（任一满足）

- 六类覆盖中任一类为 partial/unchecked；
- 任一交付门（G1–G9）未通过但因预算/材料原因无法继续修复；
- 关键材料不可得（被引原文、数据库权限、扫描件无 OCR）且影响结论；
- 运行中断后从 checkpoint 恢复，但恢复点之后的产物未能全部补齐。

## 写法要求

1. `status="partial"`，`unchecked_items` 逐条写：**缺什么**（具体条目/类别/阶段）、**为何缺**（预算、材料、工具、权限）、**补做路径**（命令或来源）。
2. `uncertainties` 写判断层面的不确定（如"引用支持判定未核读原文"），与 unchecked_items 的"没做"区分开：没做 ≠ 不确定。
3. 禁止：
   - 把未检查写成 checked；
   - 用笼统一句"时间有限"代替逐条清单；
   - 为显得完整而补写没有证据的 finding。
4. blocked 与 partial 的区分：blocked = 材料无法获取导致审查根本未开展（findings 必须为空）；partial = 审查已开展但未完成。

## 恢复记录

从 checkpoint 恢复时，run_log 必须记录：`{"t": "recover", "action": "resume from checkpoints/stageN", "status": "ok"}` 以及恢复后重跑的门结果。复核者应能据此重走完整过程。
