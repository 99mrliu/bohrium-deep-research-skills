# 任务说明（合成示例，非正式案例）

给定合成成稿 `draft.md` 与合成修改记录 `edit_plan.json`：

1. 把 `draft.md` 编译为干净的可编辑 DOCX（`deliverable.docx`）。
2. 按 `edit_plan.json` 编译带真·Word 修订留痕（w:ins / w:del）的改稿
   （`deliverable_tracked.docx`），并输出逐条复核表 `review_record.csv`。
3. 对两份 DOCX 做 round-trip 验证（zip 完整性 / XML 良构 / 文本保留率 ≥ 0.99），
   输出 `forge_report.md`。
4. 真实渲染预览（探测 soffice → pandoc → textutil+cupsfilter → qlmanage，
   全不可用则生成 preview.html 兜底并如实记录）。
5. 装配 `result.json`，原样保留 `case.json` 中 `output_contract` 的全部键。
