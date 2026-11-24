---
name: gated-pipeline-deck
description: 过程质量控制型学术 PPT 流水线。当需要把科研论文/材料按指定模板组织成可编辑、证据可追溯、导出可复核的学术汇报 PPT，且要求过程可断点续跑、每阶段有机器门禁、先存诚实 partial 再增量完善、预算（64 请求/900 秒）可控时使用。不适用：纯美化设计、无源材料的自由创作 PPT。
---

# gated-pipeline-deck — 阶段机 + 检查点 + 机器门禁的学术 PPT 流水线

## 用途与重心

本 Skill 的重心是**过程质量控制**：把"论文+模板 → 可编辑 deck + 导出预览"做成一台
**阶段机（stage machine）**——10 个阶段（S0–S9），每阶段写 sha256 检查点，
输入未变自动跳过，失败记录精确恢复命令；两个机器门禁（S5 plan-gate、S8 qa-gate）
把守内容真实性与交付质量；`/app/output` 从 S1 起就始终是合法诚实的 partial。
它不是"又一个生成 PPT 的脚本"：架构目标是让 Harness Agent 在 64 请求/900 秒
预算内**可断点续跑、可复核、失败可定位**，门禁不过就不许交付 success。

## 适用与不适用

- 适用：给定论文 PDF + 模板 pptx 的学术汇报；要求证据映射、数字逐字、模板真实
  继承、导出一致；运行可能中断需要续跑；需要给评审可复跑的记录。
- 不适用：无固定源材料的自由创作；追求视觉设计竞赛级美化；交互式逐页精修
  （本流水线批量构建，逐页精修请在产出 deck.pptx 后人工进行）。

## 环境依赖与自检

- python3 ≥3.10；python 包：python-pptx、PyMuPDF、pillow（S0 缺了会自动
  `pip install`，装不上记 degraded 并在使用处给精确失败）。
- 外部工具：soffice（LibreOffice，导出 PDF）、pdftoppm（poppler，PDF→PNG）。
  缺失不中断：无 soffice → PDF/预览门禁 degraded；无 pdftoppm → pymupdf 栅格回退。
- 自检：`python3 scripts/run_case.py status --input ... --work ... --output ...`
  查看阶段/门禁/工具状态；工具版本与 degraded 清单见
  `/app/output/pipeline_manifest.json` 的 `tools` / `degraded_tools`。

## 输入输出契约

- 输入：`/input/case.json`（`case_id`、`output_contract.fields`、可选
  `materials.paper/materials.template` 路径声明）、`/input/task.md`、材料文件。
  **必须读真实文件**，材料以 case.json 声明优先，否则按扩展名发现。
- 工作目录 `/app/work`：checkpoints/、paper/（抽取产物）、slide_plan.json、
  gates/、tools.json、build_report.json、export_report.json。
- 交付 `/app/output/`：
  - `result.json`：含 `case_id` + output_contract 全部字段；
    `status ∈ {success|partial|failed}`，partial 必须在 uncertainty 写明缺什么；
    `sources`/`uncertainty`/`change_log` 必备。
  - `deck.pptx`（可编辑）、`deck.pdf`、`preview/slide-*.png`（真实渲染预览）。
  - `qa_gates.json`：六个机器门禁，`overall`=最差门禁。
  - `pipeline_manifest.json`：阶段墙钟、产物 sha256、逐阶段续跑指令、工具版本。
- **诚实 partial**：S1 完成后 result.json 即存在且合法；之后每阶段增量重写。
  预算耗尽时 `/app/output` 永远是可提交的 partial。

## 两阶段标准流程

```bash
S=/skills/weekly-skill
python3 $S/scripts/run_case.py prepare --input /input --work /app/work --output /app/output
# → S0–S4：依赖引导/读输入/抽取论文/解剖模板/预填 slide_plan.json
# → 立即写 partial result.json；打印 NEXT ACTION
# Agent 编辑 /app/work/slide_plan.json（唯一需要创作的一步：
#   提炼 mainline/claim/bullets/notes；数字逐字；evidence.quote 必须是原文片段）
python3 $S/scripts/run_case.py finish --input /input --work /app/work --output /app/output
# → S5 plan-gate → S6 构建 deck.pptx → S7 导出 PDF/PNG → S8 qa-gate → S9 finalize
# → 打印逐页核对清单与 gates overall
```

随时可用 `status` 子命令查看进度与续跑提示。阶段/检查点/门禁的完整语义见
`references/pipeline-contract.md`（**修改脚本前必读，契约不可破坏**）。

## 本方向 spike：机器门禁与断点续跑

- S5 plan-gate：schema 校验；页型 title→conclusion 且含 method/results；
  每页 evidence 锚点必须解析到抽取产物（页码有效、quote 逐字命中该页、图标签
  存在、figures[].path 文件存在）；bullets/claim 中每个数字 token 必须在源文中
  逐字出现（空白归一化 + 拆行兜底）。失败时逐条打印 `slide k bullets[j]: ...`。
- S8 qa-gate 六门禁：contract-fields-present / evidence-anchors-resolve /
  numbers-verbatim-vs-source / template-layouts-used / export-page-parity /
  preview-pages-rendered。overall=最差门禁；**未全 pass 不允许 success**。
- 断点续跑：检查点 = 输入指纹 + 产出清单；重跑同一命令即可，日志出现
  `skip Sn (checkpoint valid)` 表示幂等跳过；输入变化级联失效下游。
- S4 防呆：finish 时若 plan 与预填骨架字节一致（说明 Agent 没编辑），
  直接失败并给出编辑提示——杜绝"骨架直接变 deck"。

## 异常处理表

| 异常 | 行为 | 恢复 |
|-|-|-|
| 缺 case.json / 材料 | S1/S2/S3 FAIL，stdout 给精确提示 | 按 RESUME 行修复输入后重跑 |
| python 包缺失 | S0 自动 pip install；失败记 degraded | 手工 pip install 后重跑 |
| 模板无匹配版式 | S6 用"第一个带正文占位符的版式"兜底并记录 | 检查 build_report.json `layout_resolved_by` |
| 占位符缺失 | S6 加 textbox 兜底，template-layouts-used 记 degraded | 接受 degraded 或换模板 |
| 文本过多 | 字号阶梯 18/16/14pt，下限 14pt 不硬塞 | 精简 bullets |
| 字体缺失 | 不干预（用版式继承字体）；导出差异由页数一致性/预览门禁暴露 | 在导出环境装字体 |
| 图文件缺失/损坏 | S6 跳过该图并记录 fallback | 修复 figures[].path |
| soffice 缺失/超时 | export-page-parity 记 degraded，不伪造 PDF | 安装 LibreOffice 后删 S7 检查点重跑 finish |
| pdftoppm 缺失 | pymupdf 栅格回退，preview 门禁 degraded | 安装 poppler |
| plan-gate 失败 | 逐条列出 slide/bullet 定位，非零退出 | 修 plan 后重跑 finish |

## 预算守则

- **两次命令 + ≤6 次模型调用**：prepare(1) → 读骨架与抽取摘要(≤2) →
  编辑 slide_plan.json(1) → finish(1) → status 核对(1)。
- **先 partial 后完善**：不要在 prepare 之前写任何交付文件；S1 已替你写好。
- 脚本阶段失败看 `RESUME:` 行，不要用模型调用去"猜"修复。
- 不要手工改 pptx/XML，除非 build_report 明确指出兜底位置不可接受。
- 预算将尽：停手即可，当前 `/app/output` 就是合法 partial。

## 最小示例

`examples/run_example.sh`（**合成示例**，非正式案例）：在 `mktemp -d` 中生成
合成 case（template.pptx + paper.pdf + case.json + task.md），跑通
prepare → 自动填 plan → finish，随后删除 S6–S9 检查点演示断点续跑，
最后 `status` 汇总。详见 `examples/README.md`。

## 限制

- PDF 抽取为文本层抽取：扫描件 PDF（无文本层）会让 S2 产出空文本并在门禁失败；
  矢量图页以整页渲染代替精确图裁切。
- 数字逐字核验是 token 级包含匹配，不能理解单位换算（"41.7%" ≠ "0.417"）——
  这是刻意的保守：只允许逐字引用。
- 版式映射是名称/类型启发式（Title Slide / Title and Content），高度定制模板
  可能落到兜底版式（会记录）。
- 文本溢出只做字号阶梯与换行，不做逐页像素级溢出测量。
- soffice 导出与原 pptx 的字体/渲染差异只能被"页数一致性 + 预览存在性"门禁
  部分覆盖，不做像素级比对。
