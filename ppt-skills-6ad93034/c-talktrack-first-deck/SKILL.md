---
name: talktrack-first-deck
description: 讲稿先行的学术汇报生成。当任务给定受众与时间预算（case.json/slide-workorder.json 中的 audience、time_minutes、slide_count）并要求围绕论文生成可编辑演示稿与讲稿时使用。核心方法：先按角色权重把总时长分配到每页（time_budget），再撰写带页标号、秒数、标题、讲稿正文、带锚点要点的 talktrack.md——讲稿是第一交付物，幻灯片由讲稿机械派生（compile_deck.py），保证"讲什么"与"放什么"永不脱节。lint_track.py 在成稿前核验：页序完整、总时长偏差 ≤10%、每页讲稿长度与秒数匹配、要点数字命中锚定页、术语保持论文写法（glossary 锁定）。适用于组会/开题/答辩/评审等有明确受众与限时的话术驱动场景；不适用于无时间约束的纯文档排版。
---

# talktrack-first-deck：讲稿先行的学术汇报生成

## 方法论一句话

**先写完能讲出口的逐页讲稿，再让幻灯片从讲稿里长出来。** 基础 Agent 的常见失败是"页面堆满、讲者无话"或"讲稿与页面两张皮"。本 Skill 反转依赖方向：talktrack.md 是源头，presentation.pptx 是它的投影——页标题、要点、图、备注全部由讲稿派生，改讲稿即改稿。

## 输入 / 输出

| 项 | 内容 |
|-|-|
| 输入 | `/input/case.json`、`material.json`、`artifacts/slide-workorder.json`、`*.pdf`、`target-template.pptx`（edit 模式另有 `starting-deck.pptx`） |
| 输出 | `/app/output/talktrack.md`（讲稿正本）、`presentation.pptx`、`presentation.pdf`、`previews/`、`result.json` |
| 完成标准 | lint 全过 + 终检全过；总时长偏差 ≤10%；每页备注即讲稿正文 |

## 执行序列（严格按序）

```bash
export CASE_INPUT_DIR=/input CASE_WORK_DIR=/app/work CASE_OUTPUT_DIR=/app/output
mkdir -p /app/work /app/output
S=<SKILL_DIR>/scripts   # 如 /skills/weekly-skill/scripts
```

**① 简报（纯脚本）**：`python3 $S/brief.py`
输出：受众/时长/页数、`time_budget.json`（逐页秒数，按角色加权）、`paper_notes.md`（论文摘要）、`glossary.json`（术语锁定）、图裁剪与可用图清单。**按打印的受众确定语域**（见 resources/audience_registers.md）。

**② 你撰写 talktrack.md（1–2 次模型调用，唯一创作步骤）**——只读 `paper_notes.md` 与 `time_budget.json`，格式严格：

```
[S1 | 40s | 封面：一句话定位]
今天向各位评审汇报这项工作：它用纯注意力架构同时解决翻译质量与训练成本两个问题。
- 纯注意力序列转导，训练 12 小时 8 卡即达 SOTA (anchor p2)

[S2 | 75s | 背景：循环架构的顺序瓶颈]
……
- RNN 顺序计算限制并行 (anchor p2)
{fig:fig1}
```

规则：每页一个 `[Sn | 秒数 | 标题]` 头；秒数尽量贴近 time_budget；讲稿正文 1–4 句口语化但术语精确；要点每条以 `(anchor pN/figN/tabN)` 结尾（anchor 不进幻灯片文字，只进来源行）；`{fig:figN}` 单独一行且只能用 figures_ok 里的图。

**③ 讲稿过检**：`python3 $S/lint_track.py`
核验页序/总时长/逐页时长与讲稿长度匹配/要点锚点/数字命中锚定页/术语大小写/图可用。hard 失败改 talktrack.md 重跑（≤3 轮）。

**④ 派生成稿（纯脚本）**：`python3 $S/compile_deck.py`
标题←页头；要点←`- `行（去 anchor 后缀）；备注←讲稿正文；图←`{fig:}`；来源行←anchors。edit 模式改写起始稿对应页、超出部分追加。

**⑤ 导出**：`python3 $S/export_deck.py`（PDF + 逐页 PNG，空白页检测）

**⑥ 终检交付**：`python3 $S/wrap_up.py`
页数/备注/来源行/模板部件字节级一致/导出一致的最终测量 → `result.json`（content_map 带逐页秒数与讲稿长度），并把 talktrack.md 一并交付到 output。

## 受众语域（硬约束，见 resources/audience_registers.md）

- 评审专家：创新点与证据强度先行，每页讲稿回答"凭什么信"；
- 导师：进展、问题、下一步；方法细节可深；
- 同行：可复现性细节（超参、数据、代码可得性）。

术语与符号永远照抄论文写法（glossary 锁大小写与连字符）。

## 禁止事项

- 禁止先建 PPT 再补备注——备注必须由讲稿派生；
- 禁止讲稿写书面段落粘贴摘要——讲稿是"说出口的话"，lint 用语速模型核查；
- 禁止总时长超标（lint 硬卡 ±10%）；
- 禁止数字无锚点或不命中锚定页；禁止引用无裁剪的图；
- 禁止 run 级字体设置；禁止手写 result.json。

## 异常处置

| 情形 | 处置 |
|-|-|
| 页时长与预算冲突 | 优先保总时长，单页可偏离（warn），在 result 记 uncertainty |
| 讲稿写超字数 | lint 语速模型报警：压缩讲稿或上调秒数（总盘不变） |
| 术语被大小写改写 | 按 glossary 规范改回论文写法 |
| 无论文文本层 | 记 partial；锚点仅用图表号；讲稿数字人工标注待核 |
| soffice 缺失 | 记 exceptions，pptx 与 talktrack.md 照常交付 |
