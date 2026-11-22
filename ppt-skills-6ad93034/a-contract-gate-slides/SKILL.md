---
name: contract-gate-slides
description: 契约门禁式学术 PPT 生成。当任务给出 case.json / material.json / slide-workorder.json 与真实模板（target-template.pptx，或 edit 模式的 starting-deck.pptx），要求围绕论文 PDF 生成可编辑学术演示稿时使用。方法核心：先把工单与输出契约编译成 12 条机检门禁（requirements.json），再规划、成稿、逐门验收——页数、角色覆盖、备注、来源行、数字命中锚定页、图来自真实裁剪、母版/版式/主题字节级继承、导出 PDF 页数一致，全部由脚本判定而非自述。result.json 仅由门禁输出机械组装，状态诚实（completed/partial/failed）。适用于模板约束强、要求证据可复核的组会/开题/答辩/评审汇报；不适用于无模板自由设计或无 PDF 的场景。
---

# contract-gate-slides：契约门禁式学术汇报生成

## 方法论一句话

**先编译契约，再写内容；每一页交付前必须过机检门禁。** 评分里的典型失败（页数不符、数字凭印象、图是占位图、模板被改、导出不一致）全部被转化为脚本能判定的门禁项，模型只做一件事：在 plan.json 里写好每页的标题、带锚点的 bullet、图选择和备注。

## 输入 / 输出

| 项 | 内容 |
|-|-|
| 输入 | `/input/case.json`、`material.json`、`artifacts/slide-workorder.json`、`*.pdf`、`target-template.pptx`（edit 模式另有 `starting-deck.pptx`） |
| 输出 | `/app/output/presentation.pptx`、`presentation.pdf`、`previews/*.png`、`result.json`、`assets/figures/*.png` |
| 完成标准 | 两门（plan/deck）全 pass 且 status=completed；任一门 hard fail 则修复后重跑，禁止绕过 |

## 执行序列（严格按序，勿跳步）

```bash
export CASE_INPUT_DIR=/input CASE_WORK_DIR=/app/work CASE_OUTPUT_DIR=/app/output
mkdir -p /app/work /app/output
S=<SKILL_DIR>/scripts   # <SKILL_DIR> 为本 skill 安装目录，如 /skills/weekly-skill
```

**① 探针（纯脚本）**：`python3 $S/survey.py` → 读打印的假设清单；若 paper 或 template 为 false，后面相应门禁会记 skip/fail 并如实进入 exceptions。

**② 论文抽取（纯脚本）**：`python3 $S/mine_paper.py` → 生成文本层、章节、图表清单与**真实图裁剪**（`output/assets/figures/`），以及 `work/paper_digest.md`。

**③ 骨架（纯脚本）**：`python3 $S/plan_scaffold.py` → `work/plan.json`（页序与角色已按工单分好）。

**④ 你撰写 plan.json（1–2 次模型调用，全程唯一的创作步骤）**：
- 只读 `work/paper_digest.md` 与 `work/plan.json` 的 `_schema`；**不要读整篇论文**（预算 64 次调用/900 秒）；
- 每条 bullet 必须带 `anchor`（`p页码` / `figN` / `tabN`），**数字只能写 digest 里出现的**；
- `figure` 只能从打印的 `figures_available` 里选；
- `notes` 写 1–3 句真讲稿（对本案例受众）。edit 模式可为保留页加 `"action":"keep"`。

**⑤ 计划门禁**：`python3 $S/gate.py plan` → 有 hard 就改 plan.json 重跑（≤3 轮）。**禁止**通过删锚点、删数字来过门；数字不在锚定页就改数字或改锚点。

**⑥ 成稿（纯脚本）**：`python3 $S/build_deck.py` → 在模板/起始稿上填占位符成稿；不设字体名；自动加来源行与备注。

**⑦ 导出**：`python3 $S/render.py` → PDF + 每页 PNG 预览；环境无 soffice 时不阻塞，记 exceptions。

**⑧ 成稿门禁**：`python3 $S/gate.py deck` → 校验页数/备注/来源行/字体零覆盖/母版字节级一致/PDF 页数。hard fail 回到 ④ 或 ⑥ 修复。

**⑨ 交付**：`python3 $S/result.py` → `output/result.json`（七根字段齐全，status 由门禁结果决定）。打印 fails 非空时必须再修一轮。

## 禁止事项（对应评分失分点）

- 禁止整段复制摘要/正文进文本框（G12 密度门禁会拦）；
- 禁止编造或取整数字（G06 会拿锚定页文本核对每一个数字）；
- 禁止用任何非 `mine_paper.py` 裁剪的图（G07）；
- 禁止在 run 级设置字体名/主题色（G08 字节级比对模板部件）；
- 禁止手写 result.json（只能由 `result.py` 组装，保证状态诚实）。

## 异常处置

| 情形 | 处置 |
|-|-|
| 论文为扫描件无文本层 | mine_paper 记 warning；锚点改用 figN/tabN；result 记 partial 并说明 |
| 图裁剪 caption-not-located | 该图不可用，plan 不得引用（门禁强制） |
| 模板缺失 | survey 记假设，用默认模板成稿，exceptions 声明 |
| 页数超限 | 压缩 result 角色页，禁止超页交付 |
| soffice 缺失 | render 记 error，deck 照常交付，status=partial |

## 资源与依赖

- `resources/plan_guide.md`：plan.json 撰写细则与好/坏 bullet 对照；
- `resources/contract_notes.md`：12 条门禁与输出契约字段含义；
- 依赖：python3 + python-pptx；pdftotext/pdftoppm/soffice/pymupdf 任一可用即可，全部缺失时脚本降级并在 exceptions 如实记录（环境已按 resources.yaml 预装科学计算与办公渲染工具）。
