---
name: defect-tribunal-audit
description: >-
  当任务要求对论文或研究报告做缺陷审查并输出结构化定级（缺陷类别：事实错误/证据不足/规范问题/建议/待复核；
  严重度：critical/major/minor/editorial）时使用。区别于一般审查技能，本技能以"对抗裁决庭"机制校准判断质量：
  每条候选发现经提出席举证（原文引用+位置）、辩护席四问、裁决留痕（维持/降级/改类/转待复核/驳回），
  并由 stdlib 校验脚本强制一致性（事实错误须附原文内部冲突证据、critical 须附结论后果、转待复核须附所缺材料），
  机械性阻断"未报告误判为做错"、严重度虚高或实缺陷被降级为建议等常见判断失真。
---

# defect-tribunal-audit — 缺陷定性与严重度校准的对抗裁决

## 适用场景与边界

适用：对给定论文/报告（PDF 或文本）执行缺陷审查，产出审查单（audit_sheet.md，每条含
原文位置/缺陷类型/严重度/依据/修改建议）与 result.json；重点保证**定性正确、定级成比例、裁决可审计**。

本技能不做（边界）：

- 不检索外部文献、不做查重或新颖性判断；
- 不润色、不改写原文，只输出缺陷与修改建议；
- 不下投稿/录用/拒稿结论；
- 数值精确重算**非本重心**：涉及需精确重算方可定论的数值主张时，标 `待复核` 并写明
  `missing_material`；可做的轻量核对仅限方向性检查（加减自洽、百分比合计、量纲、
  结论方向与表格方向是否一致），核对结论作为定性的内部证据使用。

## 运行环境

- 校验脚本：`$SKILL_DIR/scripts/tribunal_validate.py`，仅依赖 python3 标准库；
- `SKILL_DIR` 默认为 `/skills/weekly-skill`；若该目录不存在，回退为本 SKILL.md 所在目录
  （用 `ls` 或 `test -d` 探测，**禁止 `find /`**）；
- 工作目录 `/app/work`，交付目录 `/app/output`；预算 64 次模型请求、900 秒。

## 工作流程

1. **定合同、立即脚手架**：读 `/input/case.json` 与 `task.md`，以 case 自身 `output_contract`
   为准；立即在 `/app/output` 写出 `result.json` 脚手架（`case_id` + 合同全部字段填
   `PENDING::*`，`status="partial"`），并建 `audit_sheet.md` 空壳。此后每完成一个阶段就增量更新。
2. **提取全文**：将论文文本抽取到 `/app/work/paper.txt`（PDF 可用可用工具转文本），
   保留页码/节标题/表号，作为 quote 与 location 的依据。
3. **五面候选生成（宽进）**：按 `references/facets_brief.md` 的研究设计/变量定义/统计方法/
   样本量/结果报告五面逐条发问，产出候选发现写入 `/app/work/candidate_findings.jsonl`；
   每条必须带逐字 quote 与 location；此阶段宁多勿漏，定性与定级只是"指控"，允许虚高。
4. **分批对抗裁决**：每批 5–8 条候选放在一个模型 pass 内，按
   `references/adjudication_protocol.md` 执行：提出席陈述指控（quote+location）→
   辩护席回答四问（引用真实性/他处是否已说明/是否混淆未报告与做错/降一级是否仍成立）→
   裁决（维持/降级/改类/转待复核/驳回 + 一句话理由）。每条裁决追加写入
   `/app/work/adjudication_log.jsonl`（字段见协议第 4 节），**驳回与降级同样留痕**。
5. **脚本校验**：运行
   `python3 "$SKILL_DIR/scripts/tribunal_validate.py" /app/work/adjudication_log.jsonl --summary /app/work/validation_summary.txt`；
   任一违规即 exit≠0 并逐条列出，修复后重跑，直至通过；汇总表（类别×严重度）直接供审查单使用。
6. **组装审查单**：`audit_sheet.md` 正文只收录 ruling ∈ {维持, 降级, 改类} 的发现，每条含
   原文位置/缺陷类型/严重度/依据（quote 与 internal_evidence 等）/修改建议；
   `驳回` 与 `转待复核` 的记录全部进入附录"裁决留痕"，待复核项须写明 `missing_material`。
7. **定稿 result.json**：填齐合同字段；`status` 按实际诚实填写（complete/partial/failed）；
   `sources` 只列实际使用过的文件与页面；`uncertainty` 如实写明未覆盖章节、未复核数值、
   待复核事项。

## 注意事项

- **未报告 ≠ 做错**：缺少报告 → 规范问题；只有原文内部证据能证明"做了且做错"才可定事实错误
  （此时必须填写 `internal_evidence`，脚本强制）。详见 `references/defect_taxonomy.md`。
- **严重度就低不就高**：每条候选先按可成立的最低级处理，仅当辩护四问失败（尤其 q4）方可升级；
  critical 必须写 `consequence` 说明哪条结论将不成立。锚点见 `references/severity_rubric.md`。
- **预算纪律**：候选生成 1–2 个 pass；裁决分批（5–8 条/批）；脚本校验本地运行不消耗模型请求；
  先落盘部分交付物再迭代，任何时候中断都有可用产出。
- **examples/ 为合成示例**：仅演示日志格式、裁决走向与校验门的真实拦截，其论文与数据均属虚构，
  不得照抄结论或当作真实文献引用。
