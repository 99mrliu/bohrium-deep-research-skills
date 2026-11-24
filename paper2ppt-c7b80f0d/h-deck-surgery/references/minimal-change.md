# minimal-change.md — 最小改动原则、delete_slide 使用边界、主题保护规则

## 最小改动原则

手术的目标是**用最少、最可解释的 op 达到任务要求**，而不是把 deck 重写一遍。

1. **能 replace_text 就不 set_bullets，能 set_bullets 就不 delete_slide + insert_slide。**
   改动粒度越小，diff 越可读，回滚越精确，surgery_lint 的"未涉及页"集合越大、证明力越强。
2. **每刀必须有 reason**：引用 plan_ops 诊断、evidence 锚点或 task.md 条款。
   没有 reason 的改动 = 账外改动，surgery_lint 会以 change_records_complete 卡住。
3. **未涉及页必须字节级不动**：手术前后，凡没有任何文本类 op
   （set_title/replace_text/set_bullets/add_figure）指向的原始页，其 text_hash
   （标题+正文，不含备注）必须不变。surgery_lint 通过 ops_journal 重放页索引簿记
   （insert/delete/move 移位）逐位校验，发现账外改动即 error（退出码 1）。
4. **顺序建议**：先原始页码的文本修改 → 再结构性 op（insert/delete/move）→
   最后按最终页码 set_notes。这样页码坐标系清晰、journal 易审。

## 何时允许 delete_slide

delete_slide 是破坏性 op，仅当满足**全部**条件时使用：

- task.md 页数上限迫使减页，或该页与任务明确无关（如遗留的目录页、致谢页）；
- 该页不承载任何 evidence 锚点（caption、关键数值、limitations）——承载证据的页
  只能改写不能删；
- reason 中写明删页依据，并确认被删页内容没有需要抢救到其他页的要点
  （有则先 set_bullets 转移再删）。

禁止：为了"好看"删页、删 limitations 页、批量删页凑页数。

## 主题保护规则

- **禁止改写主题**：不得替换/编辑 `ppt/theme/themeN.xml`，不得整体更换模板、
  改主题字体与配色。task.md 说"keep the theme"时这是硬约束；surgery_lint 对
  v1 与最终稿做主题字节级比对（theme_unmodified），不一致即 error。
- 允许的内容级操作：标题/正文文本、要点、备注、在页内贴图（add_figure）。
  这些操作经 python-pptx 保存不会触碰 theme 部件。
- 单页排版调整（文本框位置、字号）不属于本 Skill 的 op 集合；确需调整时
  在 uncertainties 中说明，不要为排版动主题。
- insert_slide 必须使用现有 slide_layouts 中的版式（按名匹配），保持模板气质一致。

## 幂等与回滚纪律

- 任何修改先写进 ops_journal 再执行；**禁止脚本外手工改 deck**（会产生账外改动）。
- 复跑同一 journal 是安全的（op_id 去重 + 内容级幂等）；修正错误的做法是
  改 journal 后重跑，failed op 自动重试，已 applied 自动 skipped。
- 回滚：每个 applied op 的 rollback 指向应用前版本 versions/vK.pptx；
  整体回滚 = 取 v1.pptx；部分回滚 = 从某个 vK 续跑新 journal。
