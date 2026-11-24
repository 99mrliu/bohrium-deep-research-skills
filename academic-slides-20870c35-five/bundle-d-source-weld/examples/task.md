# SYNTHETIC EXAMPLE — 示例任务书（非正式测试案例）

> 本文件是 source-weld-verifier bundle 的合成示例任务书，结构模仿平台
> `/input/task.md`，全部内容虚构，仅用于演示。

## 任务

基于 `examples/materials/` 下的三份合成材料（两篇合成全文 txt +
一份演示时生成的合成单页 PDF），为一个 10 分钟、8 页的评审汇报组织内容：

1. 提取研究问题、方法、结果与限制，形成主线；每条结果标注证据强度
   （established / preliminary / contextual）与定位
   （file / pdf_page / printed_page / section / exhibit）。
2. 为每页写恰好一个主张（slide_text），并给出逐字锚点（anchor）。
3. 数字连同单位与条件逐字转录，不得凭记忆。
4. 输出 claims.json 并通过 anchor_audit 门控（回链率 1.0 才允许交付）。

## 演示断言

- `claims_good.json`：6/6 verified，exit 0，linkage_rate = 1.0。
- `claims_bad.json`：exit 1，且五个埋雷各自触发设计好的违例码
  （not_verbatim / page_mismatch / number_not_in_source /
  strength_overclaim / doc_missing）。
