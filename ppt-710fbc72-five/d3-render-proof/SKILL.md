---
name: render-proof-deck
description: 学术 PPT 模板适配的下游渲染工程 Skill。当任务要求把论文/科研材料组织成可编辑 pptx 并保证导出件（PDF/PNG）与源文件逐页一致时使用：构建 deck 后经 soffice 导出、pdftoppm 栅格化，对每页做像素级 QA（溢出/丢图/字体替换/空页/页数一致性），并由有界自动修复闭环（字号阶梯降档、拆分续页、图片重嵌）消除缺陷，全部留痕可复核。
---

# render-proof-deck — 渲染即交付的学术 PPT Skill

## 用途与重心

本 Skill 的重心是**下游渲染工程**：pptx 只是中间态，导出的 PDF/PNG 才是交付。
它回答一个其他流水线不回答的问题——**“导出件里看到的，能被证明就是 pptx
里的内容吗？”** 做法是：每一页栅格化后逐像素检查，任何修复由重渲染裁决。

标志性交付物：`render_proof.json`（逐页像素 QA + 修复留痕）。

## 适用与不适用

适用：论文+模板 → 可编辑 pptx + 导出件，且要求导出一致性可逐页核对；
批量册子的溢出/丢图/字体替换排查；需要可复跑渲染证据的评审场景。

不适用：追求视觉设计创意（本 Skill 不做美化）；纯内容校对（那是上游任务，
页内事实核对只做证据映射透传）；无渲染环境时的强保证（只能诚实降级）。

## 环境依赖与自检

- python3 + `python-pptx`、`PyMuPDF`、`pillow`（prepare 缺则自动 pip 安装并记录）。
- `soffice`（LibreOffice，PDF 导出）、`pdftoppm`（栅格化，缺则 pymupdf 兜底）、
  `fc-list`（字体核对，缺则降级为仅列请求字体）。
- **任何工具缺失只记 degraded，不中断、不伪造**：render_proof.json 会明确
  写出哪些检查因此未执行。

## 输入输出契约

- 输入：`/input/case.json`（case_id + output_contract + materials）、
  `/input/task.md`、材料文件（论文 PDF、模板 pptx；**必须读真实文件**）。
- 工作区：`/app/work`（slide_plan.json、paper/ 抽取物、deck.pptx、build_log.json）。
- 交付：`/app/output/`：deck.pptx（可编辑）、deck.pdf、preview/slide-N.png、
  render_proof.json、result.json。
- result.json 含 case_id 与 output_contract 全部字段；status 诚实
  （success|partial|failed），partial 指名缺什么、哪几页；
  所有产物与 sources 附 sha256。
- **partial-first**：prepare 一结束就写 partial 骨架，再增量完善。

## 两阶段标准流程

```bash
S=/skills/weekly-skill
python3 $S/scripts/run_case.py prepare --input /input --work /app/work --output /app/output
# → 引导依赖 → 读 case.json/task.md/材料 → PyMuPDF 抽取论文（全文/页图/图候选）
# → 立即写 partial result.json → 预填 slide_plan.json（含 _candidates 证据候选）
# → 打印 NEXT ACTION
# 【Agent 唯一创作步】编辑 /app/work/slide_plan.json
python3 $S/scripts/run_case.py finish --input /input --work /app/work --output /app/output
# → 校验 plan → 构建 deck.pptx → soffice 导出 → 逐页 PNG
# → 像素 QA → 有界自动修复循环（≤3 轮）→ 最终渲染与报告 → result.json
```

## 本方向 spike：RENDER-QA + AUTO-FIX LOOP

`scripts/render_pipeline.py` 是核心，逐页执行五类检查（算法与阈值见
`references/render-qa.md`，阈值随 render_proof.json 导出可复算）：

| 检查 | 判定 |
|-|-|
| 页数一致性 | pptx 页数 == PDF 页数，否则 fail |
| OVERFLOW | 墨迹进入页面外圈 2% 边框带 ≥0.1% → fail（≥0.05% warn） |
| IMAGE-LOSS | 期望图区域墨迹 <2%（且整页低于下限）→ fail；偏白降级 warn |
| FONT-SUB | pptx XML 请求字体 vs fc-list，缺失列 warn |
| 空渲染页 | 整页墨迹 <0.05% → fail |

`scripts/fix_loop.py` 由失败项驱动，≤3 轮：**溢出 → 字号沿 20→18→16→14→12
阶梯降一级重渲；到下限 10pt 仍溢出 → 拆分「（续）」页；丢图 → 重新定位
重嵌**。硬规则：字号绝不低于 10pt、图片绝不拉伸、修复走阶梯不硬塞、
修不了就 status=partial 指名页码。幂等：重跑 finish 不产生新修复，
历史 fix_log 保留并汇总进 result.json change_log。

## 异常处理表

| 异常 | 处置 |
|-|-|
| 模板缺版式/占位符 | build_deck 找同名版式→兜底任何含正文占位符的版式；占位符缺失用 textbox 并在 build_log 记 fallback_textbox |
| 文本溢出 | OVERFLOW fail → 阶梯降字号（下限 10pt）→ 仍溢出拆「（续）」页 → 再不行 unfixable/partial |
| 字体缺失 | FONT-SUB warn：列请求字体与缺失清单，写入 uncertainty；不阻断 |
| 图缺失/丢图 | 构建期文件缺失直接 fail；渲染期区域空白 fail → 按 basename 重定位重嵌 → 找不到记 unfixable |
| 导出失败（无 soffice） | renderer.degraded=true，像素 QA 跳过，status=partial 并写明“一致性未验证” |
| 空渲染页 | fail 且不自动修（多为导出级故障），记 unfixable |
| 页数不一致 | fail；提示 LibreOffice 可能拆出了额外页 |

## 预算守则

- 全流程 ~4 次模型调用：prepare →（编辑 plan）→ finish；脚本不重入对话。
- 先存 partial 再完善；finish 幂等，可放心重跑。
- 不要手工改 OOXML：版式问题走 plan/模板层；除非渲染 QA 定位明确才动 XML。

## 最小示例

`examples/run_example.sh` 在 mktemp 临时目录非交互跑通全流程（合成案例，
**非正式评测**），并故意让一个 results 页过载，现场演示
“溢出 → 18pt→16pt → 重渲通过”的修复闭环。详见 `examples/README.md`。

## 限制

- 外圈 2% 边框带规则对全出血装饰版式可能误报（当前无模板白名单）；
- 白底为主的图可能触发 IMAGE-LOSS 的 warn（刻意不判 fail）；
- 只保证“不被页面边缘裁切”，不保证页内布局美观；
- 字体核对是请求级，同名字体不保证度量一致——最终以 PNG 为准；
- 无 soffice 环境下只能交付 pptx + 诚实降级说明，不能声称导出已核。
