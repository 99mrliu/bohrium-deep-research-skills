---
name: source-veritas-deck
description: 当需要把论文/科研材料组织成学术汇报 PPT、且必须保证页内每个数字、图、引文都能逐字回溯到源文件时使用。本 Skill 先为源 PDF 建立带 sha256 的语料台账，再用逐条断言核验门禁（fidelity gate）把关：未核验内容自动丢弃或门禁失败，绝不静默上页。适用于对"数字与源材料一致""证据可复核"要求高的学术 PPT 模板适配任务。
---

# source-veritas-deck — 上游数据真实性优先的学术 PPT 构建

## 用途与重心

本 Skill 的架构重心是**上游数据真实性（upstream data fidelity）**，不是通用
deck 流水线。世界观：先把论文 PDF 变成一份带 sha256 的**语料台账**
（`corpus/corpus.jsonl` + `corpus/figs/`），此后每一页幻灯片的每条
bullet、每个数字、每张图、每句引文都必须回溯到台账条目，由
**fidelity gate** 在构建 deck 之前逐条核验。信条：**宁可少写，不可无据**。

标志性交付物：`/app/output/fidelity_report.json`（逐条 verdict：
verified | loose | unverified）。

## 适用与不适用

- 适用：论文/技术报告 → 学术汇报 PPT；模板套用 + 证据映射 + 导出复核；
  评审会逐页核对数字与图的场景。
- 不适用：无源材料的自由创作型 PPT；纯图片型扫描 PDF 且无 OCR（台账为空，
  一切判 unverified，应记 degraded 并说明）；需要单位换算/改写数字的科普
  场景（本 Skill 只接受逐字数字）。

## 环境依赖与自检

- python3 ≥ 3.10；依赖 `python-pptx`、`PyMuPDF`、`pillow`
  （缺失时 `prepare` 自动 pip 安装并记 change_log；装不上则记 degraded）。
- `soffice`（LibreOffice，查 /opt/homebrew/bin/soffice 与 PATH）用于导出
  PDF；`pdftoppm` 用于逐页 PNG 预览。二者缺失只记 degraded，不中断、不伪造。
- 自检：`python3 scripts/extract_source.py --help` 可运行即依赖就绪。

## 输入输出契约

- 输入：`/input/case.json`（`case_id` + `output_contract.fields`，可有
  `materials` 路径）、`/input/task.md`、材料（论文 PDF、模板 pptx；
  **必须读真实文件**，找不到就在 /input 递归扫 *.pdf / *.pptx）。
- 工作区 `/app/work`：`corpus/`（台账）、`slide_plan.json`（Agent 唯一需要
  创作的文件）、`slide_plan.verified.json`、`change_log.json`、`build_log.json`。
- 交付 `/app/output/`：`result.json`（partial-first：prepare 阶段就写入，
  覆盖 output_contract 声明的**全部**字段，状态诚实 success|partial|failed，
  partial 必写缺什么）、`deck.pptx`、`deck.pdf`、`preview/slide-N.png`、
  `fidelity_report.json`、`qa_report.json`。
- result.json 字段：case_id、status、summary、artifacts（path+sha256）、
  evidence_map（逐页来源锚点+verdict）、sources（实际读过的文件+sha256）、
  uncertainty、change_log，以及 contract 声明的任何其他字段（超集覆盖）。

## 两阶段标准流程

```bash
S=/skills/weekly-skill
python3 $S/scripts/run_case.py prepare --input /input --work /app/work --output /app/output
#   → 引导依赖 → 读输入 → 建语料台账 → 写 partial result.json
#   → 预填 slide_plan.json（含章节/图/数字候选锚点）→ 打印 NEXT ACTION
# Agent 编辑 /app/work/slide_plan.json（唯一创作步骤：只用台账内容，
#   数字逐字、图用 corpus/figs 路径、引文逐字）
python3 $S/scripts/run_case.py finish --input /input --work /app/work --output /app/output
#   → fidelity gate → 构建 deck.pptx → 导出 PDF/PNG → QA → 定稿 result.json
```

总模型调用 ≤6 次：prepare 1 次、编辑 plan 1–2 次、finish 1 次、核对 1 次。

## 本方向 spike：fidelity gate

`scripts/verify_fidelity.py`（规则全文见 `references/fidelity-rules.md`）：

1. 每个数字 token（含百分数、小数、单位）必须**逐字**出现在证据锚定的
   台账文本中；只出现在语料他处记 `loose`；完全不存在记 `unverified`。
2. 每条证据 ref（页/图/表/章节）必须解析到真实台账条目。
3. 每个图路径必须存在且 sha256 与台账**字节一致**（禁止静默重渲染/替换）。
4. 每句 quote 必须是源文本的逐字子串（空白归一化）。
5. unverified 条目默认**自动丢弃**并记 change_log；`--strict` 直接门禁失败。
   绝不静默保留无据数字。

## 异常处理表

| 异常 | 处置 |
|-|-|
| 模板缺版式 | build_deck 按 kind 回退到 Title and Content / Title Only / layouts[1]，记 build_log |
| 占位符缺失 | 在版心内加 textbox 兜底，`fallbacks` 记 build_log 与逐页清单 |
| 文本溢出 | bullets 写入占位符/word_wrap 文本框；不压字号硬塞，过多内容应回到 plan 阶段删减 |
| 字体缺失 | 不伪造；导出阶段若字体回退由 soffice 完成，QA 只核对页数与渲染成功，异常记 degraded |
| 图缺失 / sha256 不符 | 门禁判 unverified，自动丢弃并记 change_log，绝不上页 |
| 导出失败（无 soffice/pdftoppm） | qa_report.json 记 degraded，pptx 仍交付，result.json 降 partial |
| 扫描 PDF 无文本层 | 台账为空 → 一切 unverified → 记 degraded 并在 uncertainty 说明 |

## 预算守则

- ≤6 次模型调用；prepare 立即写诚实 partial result.json，再增量完善。
- Agent 只编辑 `slide_plan.json`；不要手工改 pptx XML，除非构建审计
  （build_log 的 fallbacks）明确指向占位符问题且定位清楚。
- 数字拿不准就查 `work/corpus/corpus.jsonl`，不要凭记忆写。

## 最小示例

`examples/run_example.sh`：在 mktemp 临时目录中生成合成案例
（合成 template.pptx + 6 页合成 paper.pdf + case.json + task.md）→
prepare → `fill_example_plan.py` 自动填 plan → finish → 打印产物与
sha256。产物全部在临时目录，不写回 bundle；该示例为合成示例，非正式案例结果。

## 限制

- 只认逐字数字：单位换算、四舍五入改写都会判 unverified（设计上如此）。
- 跨页断句引文可能过不了逐字子串检查。
- 章节检测为启发式，冷门章节名可能漏检（不影响数字核验）。
- soffice 渲染与 PowerPoint 渲染可能存在字体级差异；本 Skill 以
  soffice 导出件为 QA 基准并如实记录。
