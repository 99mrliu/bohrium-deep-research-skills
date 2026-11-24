---
name: narrative-first-deck
description: 学术汇报 PPT 制作，先主线后页面。把论文组织为 claim 图（problem→method→results→limitations 的依赖序），一页一个主张，讲稿按受众/时长做计时预算，plan_lint 七条叙事规则门禁不过不构建。适用于有论文 PDF + 模板 pptx + 固定受众/时长/页数的学术汇报任务。
---

# narrative-first-deck：先主线后页面的学术汇报 Skill

## 用途与重心

本 Skill 的重心是**叙事主线与讲解逻辑**，不是通用排版管线。架构围绕两个产物：

1. **`storyline.json`（创作核心）**：mainline 四句话（problem/method/results/limitations）+
   claim 图——每条主张挂证据锚点（p.N / Figure N / Table N），depends_on 编码叙事先后。
2. **`plan_lint.py`（spike 门禁）**：构建前对 storyline + slide_plan 做七条规则校验
   （页型覆盖 / 一页一个主张 / 证据锚定 / 图-主张绑定 / 顺序 / 计时预算 / 数字逐字），
   输出 `plan_lint_report.json`；**fail 则拒绝构建**。

deck.pptx 只从**通过门禁的计划**生成；备注 = 讲稿 + `⏱ ~Ns` 计时行 + 证据锚点。

**四条铁律**：先主线后页面；一页一个主张；讲稿计时对得上时长；lint 不过不构建。

## 适用与不适用

- 适用：论文 PDF + 模板/起始 pptx → 学术汇报（组会、答辩预演、会议短报告）；
  任务给出固定受众、时长、页数区间；要求证据可追溯、导出可复核。
- 不适用：海报/长文档排版；无论文源材料的自由创作 PPT；以像素级视觉还原为目标的
  模板工程（那是 d2/d3 方向）。

## 环境依赖与自检

- python3 ≥ 3.10；依赖 python-pptx、PyMuPDF、pillow（prepare 自动检测，缺则
  `pip install`，失败记 degraded 不静默）；示例另需 matplotlib。
- 导出：`soffice`（LibreOffice）与 `pdftoppm`（poppler）；缺失只记 degraded，不中断。
- 自检：`bash examples/run_example.sh`（端到端正例）与 `bash examples/lint_negative_demo.sh`
  （顺序违规负例，门禁必须 fail）。

## 输入输出契约

- 输入：`/input/case.json`（case_id、output_contract.fields）、`/input/task.md`
  （受众/时长/页数等约束）、科研材料（论文 PDF、模板 pptx）。**必须读真实文件**，
  不得按文件名猜内容。
- 工作目录 `/app/work`：`storyline.json`、`slide_plan.json`（Agent 唯一需要创作的两份）、
  `paper/source_index.json`（抽取事实：页/图/表/数字候选句）、`template_report.json`、
  `config.json`。
- 交付 `/app/output/`：`deck.pptx`（可编辑）、`deck.pdf`、`preview/slide-*.png`、
  `storyline.json`（被校验主线副本）、`plan_lint_report.json`、`build_report.json`、
  `qa_report.json`（页数一致性）、`result.json`。
- `result.json` 含 case.json `output_contract` 声明的全部字段 + case_id；状态诚实
  （success|partial|failed，partial 写明缺什么）；含 sources、uncertainty（含计时估计的
  不确定性）、change_log；所有产物带 sha256。**先存 partial，再增量完善。**

## 两阶段标准流程

```bash
S=/skills/weekly-skill
python3 $S/scripts/run_case.py prepare --input /input --work /app/work --output /app/output
# → 引导依赖；读 case/task/材料；PyMuPDF 抽取论文文本+图+数字候选；解剖模板
# → 立即写 partial result.json（全字段）→ 预填 storyline.json + slide_plan.json 骨架
# → 打印 NEXT ACTION
# Agent 编辑 /app/work/storyline.json（先 mainline 与 claims）和 slide_plan.json（唯一创作步骤）
python3 $S/scripts/run_case.py finish --input /input --work /app/work --output /app/output
# → plan_lint 门禁（fail 则不构建、result.json=failed）→ build_deck → export_render →
#   汇总 evidence_map/artifacts(sha256)/uncertainty/change_log → 最终 result.json
```

## 本方向 spike：plan_lint 七条规则（详见 references/narrative-rules.md）

| 规则 | 内容 | fail 条件 |
|-|-|-|
| R1 coverage | title/background/method/results/discussion/conclusion 页型齐备 | 缺页型 |
| R2 one_claim_per_slide | 一页一个 claim_id，命中 storyline；不复用 | 缺/错/复用 |
| R3 evidence_anchor | 每条 claim ≥1 证据锚点且全部可解析到抽取源 | 无锚点/不可解析 |
| R4 figure_claim_binding | 页面展示 Figure N ⟺ 该页 claim 引用 Figure N | 图无主张绑定 |
| R5 order | 页面 claim 序符合 storyline 依赖序 | 顺序倒退/依赖后置 |
| R6 time_budget | 讲稿估计总长在 duration±15% 内（中文≈4字/秒、英文≈2.2词/秒） | 超预算 |
| R7 numbers_verbatim | bullets 数字与源文本逐字一致 | 数字找不到出处 |

时长解析优先级：storyline.duration_min > task.md > 缺省 12 min。warn 不阻塞但使
status=partial 并写入 uncertainty。

## 异常处理表

| 异常 | 处置 |
|-|-|
| 模板缺版式 | build 按名字回退（Title and Content→Title Only→Blank→首个含 title+body 版式），记入 build_report |
| 占位符缺失 | 文本框兜底并记录 `*_fallback` 字段，不静默 |
| 文本溢出 | 不压字号硬塞：bullets 正文 14pt、主张行 15pt；超长内容应拆页（R2 允许同 kind 多页，各挂不同 claim） |
| 字体缺失 | pptx 内不写死字体名（继承模板主题字体）；导出环节的字体替换在 qa_report/uncertainty 声明 |
| 图缺失 | figure 文件不存在则不上页并记 figure_issues；claim 引用缺失图会被 R3 fail 提前拦住 |
| 导出失败 | soffice/pdftoppm 缺失或失败只记 degraded；qa_report 页数不一致 → status=partial |
| lint fail | 不构建；result.json=failed 并列出失败规则；修 plan 后重跑 finish |

## 预算守则

- Agent 总共 ~4–6 次模型调用：prepare（1 次）→ 读 source_index 并编辑 storyline/slide_plan
  （1–2 次）→ finish（1 次）→ 视 lint 结果修补（1–2 次）。
- 先 partial 后完善：prepare 已写全字段 partial result.json，任何中断都有诚实交付。
- 不要手工改 XML，除非审计定位明确且无可替代。

## 最小示例

见 `examples/`（**合成示例**，非正式测试案例）：`run_example.sh` 端到端跑通；
`lint_negative_demo.sh` 演示顺序违规被门禁精确拦下。

## 限制

- 计时是语速模型估计，非实测；±15% 是判定阈值而非精度承诺。
- 证据锚点解析依赖 PDF 文本抽取质量；扫描件/乱码 PDF 会使 R3/R7 误报（此时如实记
  uncertainty，不要绕过门禁）。
- 模板套用做到"版式与占位符真实继承 + 兜底记录"，不做像素级母版审计与逐像素渲染 QA
  （属 d2/d3 方向）。
- 数字逐字校验只覆盖 bullets（页面文字）；讲稿 notes 允许口头转述。
