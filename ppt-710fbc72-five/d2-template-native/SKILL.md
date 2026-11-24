---
name: template-native-deck
description: 学术 PPT 模板真实套用与 XML 级继承审计。当任务要求"按指定模板/起始稿"把论文或研究材料组织成可编辑演示文稿，并且母版/版式/占位符继承关系必须真实发生、主题字体与主题色必须原样保留、结果需要逐页可审计时使用。核心机制：先把模板解剖成 inventory（唯一合法版式来源），严格从模板构建，再用 zip+XML 级审计（关系链/占位符 idx/主题指纹）把关——审计不过不交付。
---

# template-native-deck — 模板套用工程与继承审计

## 用途与重心

重心是**模板的结构性真实继承**，不是通用做 PPT 流水线：

1. `inspect_template.py` 把模板/起始稿解剖成 `template_inventory.json`：
   页面尺寸、每个母版、每个版式（名字/索引/部件路径）、每个版式的全部占位符
   （idx/类型/名字/几何）、主题字体（major/minor 的 latin+ea）、主题色方案，
   以及主题部件原始字节的 sha256 **指纹**。
2. 构建严格发生在模板自己的 `Presentation` 上：起始稿旧页先删（记录），新页
   只经模板的 `slide_layouts` 添加，占位符按 idx/type 填充；**不设任何字体/
   颜色**，一切继承。占位符缺失时按决策表替代并记录，绝不退回空白默认外观。
3. `audit_inheritance.py`（spike）对构建产物做 **XML 级审计**：逐页验证
   slide→layout→master→theme 关系链、占位符 idx ⊆ 版式 idx、版式名 ∈
   inventory、页面尺寸一致、**主题指纹逐字节匹配**、版式部件确属模板本体。

## 适用 / 不适用

- 适用：有明确模板 pptx 或起始稿；要求"模板被真实套用"可复核；需要交付
  pptx + PDF/PNG 预览 + 证据映射。
- 不适用：无模板、从零自由设计视觉风格；纯网页/海报输出；只需要 PDF 不需要
  可编辑 pptx 的场景。

## 环境依赖与自检

- python3 + python-pptx、PyMuPDF、pillow（prepare 会自动 pip 安装缺失项并记录）。
- soffice（LibreOffice，PDF 导出）与 pdftoppm（PNG 预览）：缺失只记 degraded，
  不中断、不伪造。
- 自检：跑 `examples/run_example.sh`，期望 `inheritance_report.json` 中
  `overall_pass=true` 且负向测试 `theme_preserved=false`。

## 输入输出契约

- 输入：`/input/case.json`（`case_id`、`output_contract.fields`、可选
  `materials`）、`/input/task.md`、材料（模板/起始稿 pptx、论文 pdf）。
  **必须读真实文件**，不得按文件名猜内容。
- 工作区 `/app/work`：`template_inventory.json`、`slide_plan.json`、
  `paper/`（text+figs）、`build_report.json`、`plan_lint.json`。
- 交付 `/app/output`：`deck.pptx`、`deck.pdf`、`preview/slide-*.png`、
  `inheritance_report.json`、`qa_report.json`、`result.json`。
- `result.json` 必含 case.json `output_contract` 声明的全部字段（缺省
  case_id/status/summary/artifacts/evidence_map/sources/uncertainty/
  change_log），artifacts 带 sha256；**先存诚实 partial，再增量改进**；
  status=success 的前提：构建成功 + 审计 overall_pass + 渲染页数一致。

## 两阶段标准流程（预算 ≤6 次模型调用）

```bash
S=/skills/weekly-skill
python3 $S/scripts/run_case.py prepare --input /input --work /app/work --output /app/output
# → 引导依赖 → 读 case/task/材料 → 解剖模板 + 抽取论文
# → 立即写 partial result.json（全字段）→ 预填 slide_plan.json（含合法 layout）
# → 打印 NEXT ACTION
# 【唯一创作步】Agent 编辑 /app/work/slide_plan.json：
#   mainline + 每页 title/claim/bullets/figures/evidence/notes；
#   layout 只能取自 plan._legal_layouts（即 inventory）
python3 $S/scripts/run_case.py finish --input /input --work /app/work --output /app/output
# → plan 版式门禁 → 严格从模板构建 deck.pptx → XML 继承审计
# → 导出 PDF/PNG + QA → 定稿 result.json → 打印逐页核对清单
```

## 本方向 spike：XML 级继承审计

`audit_inheritance.py`（纯 stdlib：zipfile + xml.etree）对 deck 与模板分别解包：
(a) 每页 slide→layout→master→theme 的 r:id 链全部解析成功（无悬空）；
(b) 页面上每个占位符 idx 都存在于其版式（idx 缺省=0，type 缺省=body）；
(c) 版式名 ∈ inventory；(d) `sldSz` 与模板一致；(e) 主题部件与模板主题
**字节级指纹一致**（主题字体/颜色因此可证保留）；(f) 版式部件 sha256 ∈ 模板
自身版式集合（排除外来/默认模板版式）。细则见
`references/ooxml-inheritance.md`。

**审计不过不交付**：overall_pass=false 时 status 至多为 partial，failures
写入 uncertainty，修复后重跑 finish。

## 异常处理表

| 异常 | 处置 |
|---|---|
| 模板缺版式（plan layout 不在 inventory） | 按回退链选最近版式，记 substitution，uncertainty 说明 |
| 占位符缺失（无 title/body/picture ph） | 版式内容界内加纯文本框/等比插图，记 substitution；不设字体颜色 |
| 文本溢出 | 不压字号硬塞；精简 bullets，讲稿进 notes；溢出风险写 uncertainty |
| 字体缺失（主题字体未安装） | 继承关系不受影响（指纹仍匹配）；渲染回退记入 qa_report degraded |
| 图片缺失/路径错 | 跳过该图，记 missing_figures，status 降 partial |
| soffice/pdftoppm 缺失 | 记 degraded，pptx 与审计仍交付，不伪造渲染 |
| 审计 overall_pass=false | 按 references 的裁决表定位；修复重跑；否则 partial 交付并写明 |
| 起始稿带旧页 | 全部删除并记录 deleted_slides；只在其模板体系上重建 |

## 预算守则

- 全程 ≤6 次模型调用：prepare（1）→ 读抽取文本与 inventory、填 plan（1–2）
  → finish（1）→ 看核对清单收尾（1）。
- 先 partial 后完善：prepare 已落盘全字段 partial result.json。
- 不要手工改 XML，除非审计失败且 references 裁决表定位明确。

## 最小示例

`examples/run_example.sh`（合成示例，非交互）：生成合成模板（定制主题）+
合成论文 → prepare → 自动填 plan → finish → 负向主题指纹测试。详见
`examples/README.md`。

## 限制

- 单母版多版式场景覆盖最完整；多母版模板按母版分组审计，跨母版混用会如
  实记录但不额外合并。
- 主题指纹是字节级判定：构建链若重写主题 XML（即使语义等价）会判失败——
  这是有意的严格性。
- 文本溢出检测依赖渲染 QA（页数一致 + PNG 可打开），不做逐字形版面测量。
- LibreOffice 渲染与 PowerPoint 可能有字体回退差异，差异记 degraded 而非隐瞒。
