---
name: ppt-native-edit-proofer
description: 把论文/PDF 科研材料组织成"原生可编辑"的学术汇报 PPT（PPTX/slides/演示），并用机器门禁证明可编辑性——真文本、真表格、主题字体继承、字号合规、无占位符残留、round-trip 重开校验与真实渲染度量。当任务要求交付可编辑、换机稳健的论文汇报 PPT 时触发。
---

# ppt-native-edit-proofer — 原生可编辑性工程

## 核心立场

学术 PPT 的第一性问题不是"做出来"，而是"交付之后还能被改"。评测方、合作者、
换一台没有装私有字体的机器打开时，截图贴字、图片表格、转曲文本、硬编码字体
都会让 deck 变成只读图片。本方向把**可编辑性当作可机器验证的工程属性**：
不自述"可编辑"，用静态门禁 + round-trip 重开 + 真实渲染度量来证明。

## 三支柱

1. **原生元素构建**（`build_native.py`）：只用 python-pptx 原生 shape——文本框、
   真 table shape、图片 + 数值 sidecar。不显式设置字体名，继承模板主题字体；
   正文 ≥14pt，脚注/表格单元格/图注 ≥10pt（deck.json meta 可配）。
2. **可编辑性机器门禁**（`edit_lint.py`）：静态扫描成品——text-as-image 嫌疑
   （有图无文）、字体清单 vs 白名单（主题字体 + 安全字体）、占位符残留
   （"Click to add"/空 placeholder）、最小字号、真表格校验、图片可解码。
   退出码 1 = 存在 error，构建不得通过。
3. **重开与渲染证据**（`roundtrip_check.py` + `render_diff.py`）：重新打开成品
   逐页校验结构（页数/shape/备注/图片解码/OOXML zip 完整性）；soffice 真实渲染
   PDF+PNG 并度量（页数匹配、近空白页检测、渲染 sha256 记录）。无 soffice 时
   诚实 `tool_missing`，禁止未渲染却声称渲染通过。

## 输入契约

- `/input/case.json`：`case_id` + `output_contract`（字段名运行时读取，禁止硬编码）。
- `/input/task.md`：受众、时长、页数上限、模板要求。
- `/input/` 科研材料：paper.pdf、可能有 target-template.pptx、起始稿、data.csv。
  **先读真实文件，禁止凭文件名猜内容。**
- 工作区 `/app/work`，最终产物 `/app/output/`。

## 输出契约

result.json 必须含 case.json `output_contract` 列出的**全部字段（原字段名）**，
另加 `uncertainties`、`change_records`。已核实字段形态：

| 字段 | 形态 |
|---|---|
| `case_id` | 与 case.json 一致 |
| `status` | success / partial / failed（partial 写明缺什么、为什么） |
| `editable_source` | `{path, format:"pptx", slides:N, notes_present:bool}` |
| `export_artifact` | `{pdf, rendered:bool, previews:[png...], pages:N}` |
| `content_map` | 每页 `{slide, role, title, claims[], figures[], table, sources:[{kind,ref,locator,quote}], notes_present, notes_time_sec}` |
| `compliance_checks` | `[{check, expected, actual, pass}]`，**actual 必须脚本实测** |
| `exceptions` | 材料缺失 / 无法判断 / 运行失败 / tool_missing 分别说明 |

特色交付物：`font_report.json`、`editability_report.json`、
`roundtrip_report.json`、`render/`（PDF+PNG+度量）。

## 分阶段流程

| 阶段 | 动作 | 脚本 | 产出 | 门禁 |
|---|---|---|---|---|
| 0 存盘 | 读 case.json/task.md/材料；先落盘诚实 partial 骨架 | — | work/ 目录 | 输入可读 |
| 1 字体 | 环境字体发现，白名单建议 | `font_probe.py --report font_report.json` | font_report.json | 无法发现时 honest unknown，不阻断 |
| 2 证据 | 提取 PDF 全文，deck.json 每条 quote 逐字命中 | `evidence_scan.py --paper paper.pdf --deck deck.json --report evidence_scan.json` | evidence_scan.json | coverage<1.0 退出 1，content_map 不得含未命中 quote |
| 3 构建 | 原生 shape 构建（真表格/图片/备注/证据页脚） | `build_native.py deck.json --template t.pptx --fig-dir figs/ --fonts font_report.json --out presentation.pptx --report build_report.json` | pptx + build_report.json | python-pptx 缺失 → 退出 2 诚实失败 |
| 4 门禁 | 可编辑性静态扫描 | `edit_lint.py presentation.pptx --report editability_report.json` | editability_report.json | 退出 1 = 有 error，必须修复重建 |
| 5 重开 | round-trip 校验 | `roundtrip_check.py presentation.pptx --report roundtrip_report.json --expect build_report.json` | roundtrip_report.json | 退出 1 = 结构损坏 |
| 6 渲染 | soffice→PDF→pdftoppm→PNG 度量 | `render_diff.py presentation.pptx --out-dir render/ --report render_report.json --profile /tmp/lo-c` | render/ + render_report.json | 近空白页/页数不符 → 退出 1；无 soffice → tool_missing 诚实标记 |
| 7 汇总 | 按 output_contract 组装 result.json | `make_result.py --case case.json --deck deck.json --work-dir work/ --output-dir output/ --out result.json` | result.json | 全字段在；actual 全部来自实测报告 |

## 预算纪律（64 请求 / 900 秒）

| 预算 | 分配 |
|---|---|
| 阶段 0-2（读+证据） | ≤12 请求 / ≤180 秒；deck.json 落盘即第一个检查点 |
| 阶段 3-4（构建+门禁） | ≤20 请求 / ≤300 秒；pptx 落盘 = 第二个检查点（此时已可交 partial） |
| 阶段 5-7（重开+渲染+汇总） | ≤16 请求 / ≤240 秒 |
| 机动（修复门禁报错） | ≤16 请求 / ≤180 秒；剩 120 秒时停止优化，只保证 result.json 诚实 |

先存后优：每个阶段产物先落盘再改进；任何中断都留有可用 partial。

## 异常速查表

| 异常 | 处置 |
|---|---|
| PDF 加密/扫描件 | evidence_scan 走 pdftotext→pymupdf→pypdf 链；全失败 → 退出 2，exceptions 记 `tool_missing`，quote 留空并标注 |
| 图抽不出 | 用 data.csv 重绘 + sidecar；无数据 → 该页降级为 bullets 并记 exceptions |
| 公式为图片 | 允许作为图片插入，但该页必须有文本 shape，否则 edit_lint 报 text-as-image |
| 模板占位符不足 | build_native 自动改用命名文本框，删除未用空占位符 |
| 字体缺失 | 不硬编码字体名，继承主题字体；font_probe 风险列表写入 result.uncertainties |
| 页数超限 | slide_count 门禁 fail → 合并/删除低价值页后重建，禁止隐瞒 |
| 预算将尽 | 停在最近一个检查点，result.json status=partial 写明缺什么 |
| 无 soffice | render_diff 写 rendered=false + tool_missing，exit 0；禁止伪造渲染 |

## 诚实 partial 规则

- status=partial 必须在 exceptions 写明：缺什么、为什么、下一步是什么。
- compliance_checks 的 actual 一律来自脚本测量；测不出就写 `"not_rendered"`/
  `null` 并 pass=false，禁止凭空断言。
- 渲染工具缺失时 `export_artifact.rendered=false` + exceptions 记 `tool_missing`。

## 自查清单

- [ ] 所有文字是文本 shape，无 text-as-image 页
- [ ] 表格是原生 table shape，单元格全是文本
- [ ] 未显式设置任何字体名（继承主题）；edit_lint 字体门禁 PASS
- [ ] 无 "Click to add" 残留、无空占位符
- [ ] 最小实测字号 ≥10pt（脚注类）/ ≥14pt（正文）
- [ ] round-trip 重开 PASS（zip 完整/页数/备注/图片可解码）
- [ ] render/ 有真实 PDF+PNG，页数匹配，无近空白页
- [ ] result.json 含 output_contract 全字段 + uncertainties + change_records
- [ ] 每条 content_map quote 被 evidence_scan 逐字命中
- [ ] 不提交预制答案；输出全部来自真实运行
