---
name: ppt-redteam-tribunal
description: 对抗式红队复核的论文转学术 PPT 流程。当需要把论文/PDF/科研材料整理成学术汇报 PPT/PPTX/slides/演示，并要求证据可追溯、质量可收敛时触发——第一稿是"被告"，确定性检测器发起结构化攻击，finding 入账修复或正式裁决，收敛门禁达标才允许交付。
---

# ppt-redteam-tribunal — 对抗式红队复核

## 核心立场

论文转 PPT 的第一性问题不是"做得好看"，而是**过程质量控制**：模型生成
的第一稿必然混入数值幻觉、悬空引用、转述冒充原文等缺陷，且模型自查
（"请检查一遍"）对这些缺陷系统性失明——因为写稿和审稿是同一套偏差。
本 Skill 把第一稿当作"被告"：一组确定性检测器（零模型请求、可复现）
对其发起结构化攻击，每条 finding 进台账，必须修复（fix）或正式裁决
（disposition: accept-risk / reject，需理由），**不得静默删除**；
收敛门禁达标之前，产物状态不允许报 success。

## 三支柱

1. **事实池锚定**：一切判定基于 `facts.json`——captions 索引、带单位数值
   锚点、分页文本（逐字校验）、章节列表、limitation 线索，全部从论文 PDF
   确定性提取（降级链 pdftotext → pymupdf → pypdf）。
2. **对抗检测 R1–R8**：数值幻觉 / 悬空引用 / 引文不逐字 / 栏目名标题 /
   段落搬运 / 备读者复读 / 局限缺失 / 示意图当数据，全部机器可判
   （定义见 references/defect-taxonomy.md）。
3. **台账与门禁**：状态机 open → fixed | dispositioned，禁物理删除；
   两轮收敛协议（无 open error 且新一轮无新增 error）通过才出成品
   （规则见 references/tribunal-rules.md）。

## 输入契约

- `/input/case.json`：`case_id` + `output_contract`（字段列表运行时读取，禁止硬编码）。
- `/input/task.md`：受众、时长、页数上限、模板要求。
- `/input/` 科研材料：paper.pdf（必有），可能有 target-template.pptx、起始稿、data.csv。
- **先读真实文件，禁止凭文件名猜内容。**
- 中间产物一律写入 `/app/work`（下文本地示例相对路径 `work/` 即对应 `/app/work`）；最终交付物写入 `/app/output`。

## 输出契约

`/app/output/`（本地验证为 `runs/d/output/`）：

| 产物 | 说明 |
|------|------|
| presentation.pptx | 可编辑成品（python-pptx 构建，备注齐全，无空占位符） |
| presentation.pdf + preview-*.png | 真实渲染证据（soffice → pdftoppm） |
| facts.json / findings_round*.json / tribunal.json / convergence.json / fixes_report.json | 红队过程交付物 |
| result.json | 评测契约文件 |

result.json 字段（按 case.json 的 output_contract 原字段名输出，
另加 uncertainties、change_records）：

| 字段 | 形态 |
|------|------|
| case_id | 来自 case.json |
| status | success / partial / failed（partial 必写明缺什么、为什么） |
| editable_source | {path, format:"pptx", slides, notes_present} |
| export_artifact | {pdf, rendered, previews[], pages}；未渲染则 rendered=false + exceptions 记 tool_missing |
| content_map | 每页 {slide, role, title, claims[], figures[], table, sources[{kind,ref,locator,quote}], notes_present, notes_time_sec}，quote 必须逐字命中论文 |
| compliance_checks | [{check, expected, actual, pass}]，actual 全部来自脚本真实测量；**必含 redteam_converged**（actual 取自 convergence.json） |
| exceptions | 材料缺失 / 无法判断 / 运行失败分别说明 |
| uncertainties | 启发式与降级路径的诚实声明 |
| change_records | [{version, slide, change, reason, rollback}]，来自台账 |

## 分阶段流程

| 阶段 | 动作 | 脚本 | 产出 | 门禁 |
|------|------|------|------|------|
| 1 锚定 | 提取事实池 | extract_facts.py paper.pdf --out facts.json | facts.json | 退出码 0；否则 exceptions 记 tool_missing 走 partial |
| 2 被告 | 撰写 deck v1 并立即落盘 | （Agent 手写 deck.json） | deck_v1.json | 落盘即扫，不打磨 |
| 3 攻击 | 全量扫描 R1–R8 | redteam_scan.py deck_v1.json facts.json --round 1 | findings_round1.json | 检出全量入账 |
| 4 立案 | 入账台账 | tribunal_log.py --findings ... --ledger tribunal.json | tribunal.json | 幂等，禁删 |
| 5 处置 | 机器修 R1/R2；人工修 R3/R4/R6/R7；R5/R8 可裁决 | apply_fixes.py；tribunal_log.py --fix / --disposition | deck_v2.json, fixes_report.json | 每次处置回写台账 |
| 6 复扫 | 全量 round 2 | redteam_scan.py deck_v2.json facts.json --round 2 | findings_round2.json | — |
| 7 门禁 | 收敛判定 | converge_gate.py --prev round1 --cur round2 | convergence.json | verdict=pass 才继续；fail 走第 3 轮定向复扫或报 partial |
| 8 出品 | 构建 pptx | build_deck.py deck_v2.json --template ... --fig-dir figs/ | presentation.pptx, build_report.json | 空占位符移除 |
| 9 交付 | 渲染 + 汇总 | make_result.py（内部调 soffice/pdftoppm） | result.json, PDF, PNG | compliance_checks 全 pass 才 success |

## 预算纪律（64 请求 / 900 秒）

| 用途 | 模型请求 | 说明 |
|------|----------|------|
| 读材料 + 写 deck v1 | ~8–12 | 含读 PDF 文本与模板结构 |
| 人工修复 finding | 每条 1–2 | error 优先；warn 可 disposition |
| 组装复核 | ~4 | result.json 核对 |
| 检测器/台账/门禁/构建/渲染 | **0** | 全部确定性脚本 |
| 预留 | ≥10 | 门禁 fail 时的第 3 轮定向复扫 |

先存后优检查点：facts.json → deck_v1.json → findings_round1.json →
deck_v2.json → convergence.json → result.json。任何一步超时，以最新
检查点报 partial（详见 references/budget-protocol.md）。

## 异常速查表

| 异常 | 处理 |
|------|------|
| PDF 加密 / 纯扫描件 | extract_facts 退出码 2 → exceptions 记 tool_missing，status=partial |
| 图抽不出 / fig 文件缺失 | build_deck 记 figures_missing，保留文字引用，不伪造 |
| 公式为图片 | 不进锚点池；相关论断只能引用 caption 文字 |
| 模板占位符不足 | 回退版式 + warnings；空占位符一律移除保证 placeholder_free |
| 字体缺失 | 照常渲染，uncertainties 声明字体替换 |
| 页数超限 | 合并内容页后重扫复收敛；禁止靠删 finding 过关 |
| 预算将尽 | 停止优化：入账 → 门禁 → 按 verdict 报 success/partial |

## 诚实 partial 规则

- 收敛门禁 fail：status 必须是 partial，exceptions 附 open error 清单，
  禁止声称 success。
- 渲染链断裂：export_artifact.rendered=false + tool_missing，
  **禁止未渲染却声称渲染通过**。
- 检测器降级（如 pypdf 兜底）：在 uncertainties 声明所用引擎。
- 不提交预制答案；result.json 全部数字来自脚本真实测量。

## 自查清单

- [ ] facts.json 存在且 engine 已记录
- [ ] findings_round1/2、tribunal.json、convergence.json 齐全且 verdict=pass
- [ ] 台账无 open error；warn 均有 fix 或带理由的 disposition
- [ ] result.json 含 output_contract 全字段 + uncertainties + change_records
- [ ] compliance_checks 含 redteam_converged，actual 来自 convergence.json
- [ ] content_map 每条 quote 在论文分页文本逐字命中
- [ ] PDF/PNG 为本次真实渲染产物
