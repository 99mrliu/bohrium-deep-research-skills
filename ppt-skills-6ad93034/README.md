# 学术 PPT 生成与编辑（challenge ppt-6ad93034）：三个独立方向

三个相互独立、零共享代码的 Skill bundle，均在组织方固定案例接口
（`/input/case.json` + `material.json` + `artifacts/slide-workorder.json` +
论文 PDF + 真实模板/起始稿 PPTX）上完整跑通，交付可编辑
`presentation.pptx`、PDF 导出、逐页 PNG 预览与七字段 `result.json`。

## a-contract-gate-slides —— 契约门禁方向

把工单与输出契约编译成 12 条机检门禁（页数、角色覆盖、备注、来源行、
数字命中锚定页、图来自真实裁剪、母版/版式/主题字节级继承、导出页数
一致等），模型只在 plan.json 一个面上创作，result.json 由门禁输出机械
组装，状态诚实。

## b-opjournal-deck-surgeon —— 操作日志外科方向

底稿冻结为 v000 快照，一切改动以带 why/anchor 的操作追加入册
（journal.jsonl），apply 纯重放成稿；入册即校验数字与图，verify 独立
审计；change_journal.md 自动形成，任意操作可回退、任意版本可复现。
天然覆盖 edit/adapt 与多轮迭代场景。

## c-talktrack-first-deck —— 讲稿先行方向

总时长按角色权重分配到每页；先写带秒数、标题、讲稿正文、锚点要点的
talktrack.md（lint 核验总时长 ±10%、语速模型、数字命中、术语锁定），
幻灯片由讲稿机械派生——讲稿与页面永不脱节。

## 目录

每个方向内含 `SKILL.md`、`scripts/`、`resources/`、`examples/`、
`GITHUB_URL.txt`。三 bundle 之间无任何共享文件或依赖。
