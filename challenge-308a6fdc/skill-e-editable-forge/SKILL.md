---
name: editable-deliverable-forge
description: 当需要把 Markdown 成稿交付为真实可打开、可编辑的 Word（DOCX）稿件、需要带修订留痕（tracked changes）的改稿供人工逐条 accept/reject、或需要为 Office 产物附带真实渲染的 PDF/PNG 预览时触发。核心能力：纯 Python3 标准库把 Markdown 子集编译为结构正确的 OOXML 包（含样式与表格）；按 edit_plan.json（find/replace/reason）生成真·Word 修订（w:ins/w:del，author 与日期齐全）并输出逐条复核 CSV；编译后立即做 zip 完整性、XML 良构与文本 round-trip 验证（保留率阈值 0.99）；按 soffice/libreoffice → pandoc → textutil+cupsfilter → qlmanage → 自足 HTML 的降级链产出真实预览。红线：绝不伪造预览文件或软件状态——渲染器全部不可用时只生成 preview.html 并在 forge_report 与 result.json 中如实记录 preview_status。不适用于纯结构化 JSON 产物、无文档交付物的任务或需要完整 Word 排版特性（图片、公式、目录、页眉页脚）的场景。
---

# Editable Deliverable Forge — 可编辑产物与修订留痕锻造

## 定位

这是一个**产物端的文件工程** skill：不做事实核验、不做文体润色，解决的是学术写作交付的
"**改得动**"问题——把 Markdown 成稿编译成真实可打开、可编辑、带真·Word 修订痕迹的
DOCX，配逐条接受/拒绝复核表、round-trip 验证报告与真实渲染预览。与其他写作 skill 的
本质区别：它的输出是**结构正确的 OOXML 二进制与验证证据**，而不是又一管道式内容检查。

## 运行时契约（评测平台）

- skill 安装于 `/skills/weekly-skill`；harness agent 在固定案例上运行。
- 输入：`/input/case.json`、`/input/task.md` 及材料文件。先读实际文件，不臆测内容。
- 工作目录 `/app/work`；最终产物放 `/app/output`。
- `/app/output/result.json` 必须**原样包含 case.json 中 output_contract 的全部字段**
  （典型键：`case_id`、`deliverable`、`preserved_facts`、`evidence_map`、`change_log`），
  `case_id` 原样照抄；含诚实的 `status` / `sources` / `uncertainty` / 修改记录。
  无内容可填的字段写 `"PENDING"`，不留空、不编造。
- 可编辑 Office 产物应**尽力**附带真实渲染的 PDF/PNG 预览；渲染工具不存在时如实记录，
  **禁止伪造预览**。
- 执行预算：**64 次模型请求 / 900 秒**。脚本执行不占模型请求，尽量把确定性工作交给脚本。

## 快速开始（可复制命令）

```bash
SKILL=/skills/weekly-skill   # 本地开发时改为 bundle 根目录
mkdir -p /app/work /app/output

# 0) 在 /app/work 中准备好成稿 draft.md（可选：edit_plan.json 修改记录）

# 1) 端到端一条命令：编译 + 修订 + 验证 + 渲染 + 装配 result.json
python3 "$SKILL/scripts/docx_forge.py" run \
  --case /input/case.json \
  --md /app/work/draft.md \
  --edit-plan /app/work/edit_plan.json \
  --outdir /app/output

# 也可分步执行（调试/复用时）：
# 2) 仅编译干净版
python3 "$SKILL/scripts/docx_forge.py" build --md /app/work/draft.md --out /app/output/deliverable.docx
# 3) 编译修订留痕版 + 复核 CSV
python3 "$SKILL/scripts/docx_forge.py" build --md /app/work/draft.md \
  --out /app/output/deliverable_tracked.docx \
  --edit-plan /app/work/edit_plan.json --review-csv /app/output/review_record.csv
# 4) 单独验证（注意：修订版应与"应用全部修改后的期望文本"对比，run 子命令已自动处理）
python3 "$SKILL/scripts/docx_forge.py" verify --docx /app/output/deliverable.docx --md /app/work/draft.md
# 5) 单独渲染预览
python3 "$SKILL/scripts/docx_forge.py" render --docx /app/output/deliverable_tracked.docx \
  --md /app/work/draft.md --outdir /app/output
```

`/app/output` 产物：`deliverable.docx`、`deliverable_tracked.docx`、`review_record.csv`、
`forge_report.md`、`preview.pdf` / `preview-*.png` / `preview.html`（按实际渲染能力）、
`result.json`。

## 时间表（900 秒预算）

| 阶段 | 时间 | 动作 |
|---|---|---|
| 0–90 s | 读输入 | 读 `/input/case.json`、`task.md`、材料；确定 output_contract 键与交付体裁 |
| 90–300 s | 成稿 | 在 `/app/work` 写 `draft.md`（只用支持的 Markdown 子集，见下）与可选 `edit_plan.json` |
| 300–420 s | 锻造 | 跑 `run` 子命令；读 forge_report，确认 retention ≥ 0.99、修订命中数符合预期 |
| 420–540 s | 修补 | 若 retention 不达标或有 misses：修正 draft/edit_plan 后重跑（脚本秒级完成） |
| 540–660 s | 装配核对 | 目检 `result.json`：契约键齐全、case_id 原样、preview_status 诚实 |
| 660–900 s | 缓冲 | 保留给意外（渲染超时、材料超长、二次修订）；超时就交付已验证的部分产物并在 uncertainty 说明 |

模型请求预算：读输入 ≤3 次、成稿 ≤4 次、核对 ≤3 次，总 ≤12 次，远低于 64 次上限；
**绝不用模型逐字抄写文档内容，一律走脚本**。

## Markdown / OOXML 子集支持范围

支持：`#`/`##`/`###` 标题、段落（软换行合并）、`-` 无序列表、`| 表格 |`（含分隔行、
列数不齐自动补齐）、`**加粗**`、`*斜体*`。中文通过 styles.xml 声明 SimSun/等线
（仅声明，不内嵌字体）。详见 `references/ooxml-subset.md`。

## 修订留痕模式（edit_plan.json）

```json
{"edits": [{"find": "原文片段", "replace": "新文本", "reason": "修改理由"}]}
```

- 命中：对应区间生成 `<w:del>`（原文，w:delText）+ `<w:ins>`（新文），
  `w:author="skill-agent"`、`w:date` 为 UTC 时间戳——Word 中显示为真修订，可逐条 accept/reject。
- 每条修改只应用到**第一处命中**；同一文本多处出现请拆成多条或人工核对。
- 未命中：**不做近似替换**，如实记入 misses、review_record.csv 与 result.json 的 uncertainty。
- `review_record.csv` 的"接受状态"列留空，供人工复核时填 accept/reject。
  人工操作流程见 `references/review-workflow.md`。

## 渲染器探测顺序与降级（真实渲染，绝不伪造）

1. `soffice` / `libreoffice --headless --convert-to pdf` → 版式级 PDF
2. `pandoc docx -o pdf` → 版式级 PDF
3. `textutil` + `cupsfilter`（macOS）→ 纯文本版式 PDF（真实渲染，排版不同，报告中注明）
4. `qlmanage -t`（macOS）→ docx 首页缩略图 PNG（真实渲染，无 PDF）
5. 全不可用 → 自足 `preview.html`，顶部显式标注"未找到 PDF 渲染器，此为 HTML 预览"

PDF 生成后若探测到 `pdftoppm`，自动转逐页 PNG。每一步的探测结果、命中渲染器与失败原因
都写进 `preview_status`（forge_report.md 与 result.json）。**渲染失败的空文件会被删除，
绝不把空 PDF/PNG 当产物。**

## 异常处理

- **edit_plan 片段未命中**：记入 misses，CSV/报告/result.json 三处可见，exit code 仍可能为 0
  （编译本身成功），但 `uncertainty` 字段会显式提示需人工处理。
- **非法 XML 字符**：编译前统一剔除 XML 1.0 不允许的控制字符并转义 `&<>`，不会产出坏文件。
- **超长表格**：不截断内容；列数不齐以表头为准补齐空单元格，保证表格合法。
- **retention < 0.99**：forge_report 标"未达标"，result.json `status="partial"`；
  常见原因是 draft.md 用了子集外的语法（图片、代码块、有序列表数字），改用子集语法重跑。
- **渲染器超时/失败**：记录日志摘要，自动降级到链上的下一级。

## 最小示例

`examples/` 下有合成示例全套（`case_id="EXAMPLE-NOT-A-TEST-CASE"`）：输入 case.json /
task.md / draft.md / edit_plan.json，以及真实运行产生的文本输出（forge_report.md /
review_record.csv / result.json / preview.html）。**均为合成示例，非正式案例结果。**
二进制产物（docx/pdf/png）按 bundle 规则不随包分发，用上面的 `run` 命令即可本地重建，
命令见 `examples/README.md`。

## 文件清单

- `scripts/docx_forge.py` — 编译 + 修订 + 验证 + 渲染 + 装配（argparse 五个子命令，中文注释）
- `references/ooxml-subset.md` — OOXML/Markdown 子集与已知限制
- `references/review-workflow.md` — Word 中 accept/reject 操作与 review_record.csv 用法
- `examples/` — 合成示例输入与文本输出
