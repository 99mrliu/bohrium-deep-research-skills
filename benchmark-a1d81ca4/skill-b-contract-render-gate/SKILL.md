---
name: contract-render-gate
description: 下游交付契约工程与真实渲染预览技能：把 agent 起草的内容按 case.json 的 output_contract 动态契约化填充 result.json，生成 SVG 状态面板与 stdlib 手写 PNG 位图预览，再经自检门禁（契约齐全率/provenance 覆盖/sha256 一致）判定 DELIVER 或 BLOCK。支持 T1 阅读问答与 T2 benchmark-DRAFT 出题工单。Use when finalizing literature-reading benchmark deliverables that must pass a contract gate and ship real rendered previews.
---

# contract-render-gate

## 用途与适用条件

本技能负责文献阅读工单的**下游交付**：它不替 agent 撰写答案或题目，而是把
agent 起草的工作文件**契约化、渲染、门禁交付**——交付物先过契约门禁再过
渲染门禁，每个字段可追溯到工作文件与证据锚点，预览是真实生成的位图而非
口头声明。适用于所有携带 `output_contract` 字段集的案例。

## 运行时契约

1. 平台把本技能装在 `/skills/weekly-skill`；官方 DeepSeek Harness 在 3 个
   隐藏固定案例上各跑 3 次。
2. 每个案例输入：`/input/case.json`（含 case_id 与 output_contract 字段集——
   字段集**运行时动态读取，不得假设固定字段名**）、`/input/task.md`、以及
   `/input` 下的源材料（真实 PDF，或段落/表格文本 txt/md/json；组织方
   revision2 案例给的是段落/表格文本）。
3. 工作目录 `/app/work`；最终交付 `/app/output`，含 `result.json`：必须含
   原始 case_id 与 output_contract 要求的全部字段（填不了的填 null 并记入
   uncertainty，**不得编造**），另含诚实 status（成功/部分完成/无法判断/
   拒答 + status_reason）、sources、uncertainty、change_records。
   partial（部分完成）必须指明局限。
4. 可编辑产物必须同时给真实渲染的 PDF/PNG 预览供人工目检（本技能产出
   preview.svg + preview.png）。
5. 预算：64 次模型请求、900 秒；**必须先尽早写合法的部分 result.json 再
   增量完善**（流程第 0 步）。
6. 技能包：≤50 个 UTF-8 文本文件、单文件 ≤500KB、总 ≤2MB、无符号链接；
   **不含 3 个隐藏案例的预制答案**（本包 examples/ 为合成示例）。
7. python3 脚本只允许标准库（3.8+）；可选外部工具（pdftotext、rsvg-convert、
   inkscape、magick、pdftoppm、qlmanage）用 `shutil.which` 探测，缺失优雅
   降级，绝不崩溃。

## 依赖

- 必需：python3 ≥ 3.8 标准库（json/os/sys/struct/zlib/hashlib/shutil/
  subprocess/tempfile/xml.etree）。
- 可选（缺失自动降级）：rsvg-convert / inkscape / magick 用于 SVG→PNG
  高清版；pdftotext 等若 agent 需抽取 PDF 文本可自行探测。

## 两类工单识别

读 `/input/task.md`：出现"出题 / 题卡 / benchmark / DRAFT / 草拟 / 4 道 /
四道"任一触发词 → **T2**（benchmark-DRAFT 出题：从段落/表格文本起草 4 道
含任务、材料范围、参考答案、评分规则、证据锚点、难度、授权的题卡）；
否则 → **T1**（阅读问答/解析/翻译/抽取）。两类工单的契约化、渲染、门禁
流程完全一致，仅 agent 起草的工作文件内容不同。

## 工作流程

| 步 | 动作 | 命令 |
| --- | --- | --- |
| 0 | 锁定部分结果 | `python3 /skills/weekly-skill/scripts/contract_scan.py` 后 `fill_result.py --init`，立即写合法骨架（字段全 null，status=无法判断） |
| 1 | 契约扫描 | `contract_scan.py --case /input/case.json --out /app/work/contract.json`，动态提取字段集 |
| 2 | agent 起草 | agent 在 `/app/work` 写 `answers.json` 或 `items.json` + `evidence_map.json`（顶层键名对齐契约字段名；锚点指向源材料真实行号） |
| 3 | 契约填充 | `fill_result.py`：逐字段校验（类型/空值/超长截断），缺字段置 null 记 uncertainty，生成 field_provenance |
| 4 | 渲染预览 | `render_preview.py`：生成 preview.svg（ET 校验 well-formed）+ preview.png（stdlib 手写编码器）+ preview_record.json；**人工目检位图** |
| 5 | 门禁 | `selfcheck_gate.py`：gate_report.json，verdict=DELIVER 方可交付；**BLOCK 不得声称成功**，保留部分 result.json 并附 block_reasons |

各脚本均可用 `--help` 查看参数；路径默认值即平台契约路径。

## 异常处理表

| 异常 | 行为 |
| --- | --- |
| case.json 缺失/畸形 | contract.json degraded=true，仅保证 case_id，notes 记明原因 |
| 缺 output_contract | 同上，降级不中断 |
| 工作文件缺失/畸形 JSON | 跳过并记 uncertainty，对应字段置 null |
| 字段类型不匹配 | 置 null 并记 uncertainty（期望 vs 实际类型） |
| 字符串 >8000 字符 | 截断 + `[TRUNCATED]` 标记 + 告警 |
| 外部渲染器全部缺失 | preview_note 记明，使用内置 PNG 编码器，不崩溃 |
| 门禁 BLOCK | 保留部分 result.json，gate_report 逐条列出原因 |

## 交付前自查

1. `result.json` 含原始 case_id、契约全部字段、status/status_reason、
   sources、uncertainty、change_records、field_provenance。
2. 必填字段齐全率 100%；任何 null 都在 uncertainty 中有原因。
3. preview.svg / preview.png 存在，sha256 与 preview_record.json 一致。
4. `gate_report.json` verdict=DELIVER；若为 BLOCK，交付说明中必须写明
   部分完成与局限，不得声称成功。
5. 重跑 render_preview 两次，PNG sha256 逐字节一致（确定性）。

## 限制

- 内置 PNG 用 5x7 ASCII 点阵字体，**不渲染 CJK**（非 ASCII 显示为 `?`）；
  中文内容请看 SVG。
- 门禁只校验**结构与契约合规性**；答案/题卡的语义正确性不在门禁范围，
  需 agent 自行保证。
- 本包不含任何预制答案；examples/ 为合成示例（SYNTHETIC EXAMPLE）。

## 参考文档

- `references/contract_handling.md`：契约解析、填充与 null/uncertainty、
  provenance 规范。
- `references/rendering_spec.md`：SVG 版式、内置 PNG 编码器、外部渲染器
  探测与降级表。
