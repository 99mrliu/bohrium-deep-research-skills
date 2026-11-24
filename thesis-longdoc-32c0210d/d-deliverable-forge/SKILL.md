---
name: deliverable-forge
description: 把"交付"本身工程化——运行时把 case.json 的 output_contract 编译成清单，从 result_parts 装配 result.json（六道硬门），把改后章节渲染成真实 PDF/PNG 预览（pandoc→xelatex→soffice 降级链，FORGE_NO_RENDER=1 可确定性跳过），最后做原子写交付自验并产出 sha256 manifest。适用于学位论文/长文档分章节编辑任务中"组装并验证最终交付物"的环节，保证绝不出现"声称交付了但路径不存在/预览是伪造"。
---

# deliverable-forge — 下游交付与渲染工程

## 1. 用途与触发条件

当你已经把章节改完（或改了一部分），需要**组装并验证最终交付物**时使用本 Skill：

- 把 case.json 的 `output_contract.fields` 编译成待填清单（脚本，运行时读取，不硬编码）；
- 从 `result_parts/` 零件装配出含全部契约字段的 `result.json`，六道硬门把关；
- 把改后章节渲染成**真实**的 PDF/PNG 预览，渲染器不可用就如实记录、不列假预览；
- 交付终检：契约键齐全、artifact 逐文件 sha256 进 manifest、预览非空、交付章节与工作副本一致。

触发词：交付、result.json、output_contract、预览、渲染、manifest、验收。

## 2. 输入契约

```
/input/case.json                      {"case_id","task","output_contract":{"fields":[...]}}
/input/task.md                        任务叙述
/input/organizer-edit-workorder.json  编辑工单（实际编辑目标与验收判据）
/input/chapters/*.md                  分章节可编辑工作稿（W16 形态；若给 PDF 需自行 pdftotext）
/app/work/                            工作目录（可写）
/app/output/                          最终交付目录，必须含 result.json
```

契约字段集合以**实际 case.json 为准**，脚本运行时读取；任何字段缺产出 → 填 `null`
并在 `problems` 记录（脚本自动做），不得静默省略键。

设 `FORGE=/skills/weekly-skill/deliverable-forge`（若安装根不同，换成实际路径）。

## 3. 工作流（按序执行；标注【脚本】/【模型】）

### 步骤 0【模型】读输入
读 case.json、task.md、organizer-edit-workorder.json，浏览 chapters/。
**预算意识**：900s/64 请求内先求"可交付的 partial"，再改进。任何时候跑步骤 3
都会落盘一个可解析的 result.json——这是你的保险丝。

### 步骤 1【脚本】编译契约清单
```bash
python3 $FORGE/scripts/contract_checklist.py \
  --case /input/case.json --out /app/work/checklist.json
```
输出每个契约字段的待填项与零件文件命名约定。退出码≠0 ⇒ case.json 缺
`output_contract.fields`，按异常矩阵第 5 条处理。

### 步骤 2【模型】编辑章节 + 写零件
在 `/app/work/chapters/` 上完成工单编辑（机械替换优先用 sed/python 一次性做完），
把最终章节拷到 `/app/output/chapters/`，然后向 `/app/work/result_parts/` 写零件：

- 每个契约字段一个 `<field>.json` 或 `<field>.md`（清单里已列出字段名）；
- `edited_chapters` 写 JSON 对象：`{"ch01.md": "chapters/ch01.md", ...}`；
- `_meta.json`：`{"case_id": "<照抄case.json>", "status": "complete"}`（没改完就写 `"partial"`）；
- `artifacts.json`：交付文件相对路径列表，**只列真实存在的文件**；
- `sources.json`：实际用过的输入材料。

填充语义详见 `references/output_contract.md`。零件文本里提到的任何
`/app/output/...` 路径都会被核验真实存在（门 G3）——先落盘，再提及。

### 步骤 3【脚本】装配 result.json（六道硬门 + 原子写）
```bash
python3 $FORGE/scripts/assemble_result.py \
  --case /input/case.json --parts-dir /app/work/result_parts \
  --output-dir /app/output --output /app/output/result.json
```
退出码 0 = 六门全过；1 = 有门没过但 result.json 已带 `problems` 落盘（读输出逐条修复后重跑）；2 = case.json 不可读。`status=complete` 而 problems 非空会被强制降级 `partial`（门 G5）。

### 步骤 4【脚本】真实渲染预览
```bash
python3 $FORGE/scripts/render_preview.py \
  --chapters-dir /app/output/chapters --out-dir /app/output/preview \
  --result /app/output/result.json --report /app/work/render_report.json \
  --title "<论文题> edited chapters"
```
按 pandoc→xelatex→soffice 顺序探测（各带 timeout），产出
`preview/edited_chapters.pdf` 及首页 `.png`（pdftoppm）。全部不可用 ⇒ 退出码 1，
`limits` 记 `renderer_unavailable`，artifacts 不列预览，**绝不伪造**。做确定性
测试时设 `FORGE_NO_RENDER=1` 跳过渲染。

### 步骤 5【脚本】交付终检 + manifest
```bash
python3 $FORGE/scripts/verify_delivery.py \
  --case /input/case.json --result /app/output/result.json \
  --output-dir /app/output --work-dir /app/work \
  --manifest /app/output/manifest.json
```
C1 可解析 / C2 case_id 一致 / C3 契约键齐全（null 必须有 problem 记录）/
C4 artifact 逐文件 sha256 进 manifest（preview/ 下文件必须非空）/
C5 交付章节与 `/app/work/chapters/` 最新副本逐字节一致。退出码≠0 ⇒ 读
manifest.json 的 `checks` 逐条修复，重跑步骤 3–5。

### 步骤 6【模型】收尾
确认 `/app/output/` 至少含：result.json、manifest.json、chapters/、（有渲染器时）preview/。
时间将尽时：立即重跑步骤 3 落盘当前 partial，再补零件。

## 4. 输出契约（result.json 填充规则）

完整规则见 `references/output_contract.md`。要点：

- 含 `case_id` + `output_contract.fields` 的**全部**字段（运行时读取）；
- 字段缺产出 → `null` + `problems` 对应记录（诚实 partial；静默 null 在终检 C3 判失败）；
- `status`：complete/partial/failed；problems 非空 ⇒ 至多 partial（自动降级）；
- `artifacts` 只列真实存在的文件；预览只列真实渲染产物；
- 先存可用 partial 再增量改进。

## 5. 异常矩阵

| 异常 | 检测点 | 降级路径 |
|-|-|-|
| 渲染器全部不可用 | render_preview 退出 1 | limits 记 `renderer_unavailable`，artifacts 不列预览，继续交付（PDF 预览非契约字段） |
| 章节目录缺失/为空 | render_preview 退出 1 | limits 记 no chapter markdown；检查 `--chapters-dir` 是否指向真实副本 |
| 契约字段与产出物语义不匹配 | 模型判断 + 门 G1 | 填最贴近的如实内容 + problems 说明缺口；完全无法产出 → 不写零件，门 G1 自动填 null + problem。**禁止改名冒充** |
| 零件 JSON 写错 | 门 G6 | 该字段 null + problem；修复后重跑步骤 3 |
| 文本提到不存在的 /app/output 路径 | 门 G3 | 先落盘文件再提及，或删去该句；重跑步骤 3 |
| artifacts 列了不存在/空文件 | 门 G4 / 检 C4 | 从 artifacts.json 移除或补齐文件；预览为空按伪造判失败 |
| case.json 缺 output_contract.fields | 步骤 1 退出 2 | 通读 task.md，按任务叙述推断字段集合并把推断写入 result.json 的 limits，仍按上述流程装配 |
| 时间不足 | 模型自检 | 立即跑步骤 3 落盘 partial（result.json 始终可解析），重跑步骤 5；有余量再补零件 |

## 6. 依赖与文件清单

- 必需：python3（仅标准库）。脚本：contract_checklist.py / assemble_result.py /
  render_preview.py / verify_delivery.py。
- 可选渲染器：pandoc、xelatex、soffice（LibreOffice，macOS 会探测
  /Applications/LibreOffice.app）；PNG 需 pdftoppm（poppler）。
- 可选输入工具：pdftotext（案例只给 PDF 时自行抽取）。
- references/：output_contract.md（字段填充与诚实 partial 语义）、
  renderers.md（探测顺序、降级、命名约定）。
- examples/synthetic/：合成示例（非正式案例），`run_example.sh` 一键端到端，
  `expected/` 由真实运行固化。

## 7. 已知边界

- 内置 md→HTML/LaTeX 是预览级转换（标题/段落/列表/代码块），复杂表格、数学式、
  交叉引用排版不保真；预览用途是"证明稿件真实可读"，不是出版排版。
- pandoc→PDF 依赖系统 PDF 引擎，失败属正常降级，会自动落到下一渲染器。
- soffice 首次启动可能需 20–40s；`--timeout` 默认 120s，可调。
- C5 要求交付章节与 `/app/work/chapters/` 副本逐字节一致：装配后不要再单手改
  output 副本，两边同步改或重新拷贝。
- 门 G3 只核验文本中字面出现的 `/app/output/...` 路径，不核验语义正确性。
