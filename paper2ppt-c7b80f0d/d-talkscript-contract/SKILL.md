---
name: ppt-talkscript-contract
description: 把论文/PDF 科研材料转成"讲稿契约优先"的学术汇报 PPT——先写逐字讲稿、按时长切节拍、每拍幂等投影成一页，备注即讲稿而非页面文字复读；附证据逐字引用与渲染验证。当用户要求将论文、PDF、研究材料做成学术汇报、PPT、PPTX、slides、演示、答辩或带讲稿/备注的幻灯片时使用。
---

# ppt-talkscript-contract — 讲稿契约优先的论文转学术 PPT

## 核心立场

学术 PPT 首先是一场**有时长预算的口头报告**，幻灯片只是讲稿的逐拍投影。常见失败不是
"生成不出幻灯片"，而是生成的 deck 讲不通：页面堆字、备注复读页面、时长失控、证据无
出处。本 Skill 把转换顺序倒过来——先写逐字讲稿，按时长切成节拍（beat），校验通过后
每拍投影成一页；机器门禁保证备注是讲稿本身。证据、时长、备注质量全部可机器复核。

**声明**：本 Skill 不提交任何预制答案；所有输出全部来自对真实输入文件的实时运行。

## 三支柱

1. **时长是一等约束**：从 task.md 读报告时长与页数上限；中文口播按 240 字/分钟、英文
   150 词/分钟折算字数预算；字数预算分配到拍，再决定页数。
2. **备注≠页面文字**：每页备注 = 该拍讲稿原文（含过渡句与"被问到时"补充）；门禁强制
   备注与页面可见文字的 token Jaccard 相似度 ≤0.5，杜绝复读。
3. **逐拍幂等打造**：一次只构建/更新一页（`slide_forge.py` 的 upsert 幂等，自建元素
   `forge_` 前缀管理，重跑只更新不堆积）；每页挂证据引用（figure/table/section + 逐字
   quote + 页码）；任何时刻整本 deck 可打开、可交付。

## 输入契约

- `/input/case.json`：含 `case_id` 与 `output_contract`（result.json 必须包含其列出的
  全部字段，**原字段名，运行时读取，禁止硬编码**）。
- `/input/task.md`：受众、时长（分钟）、页数上限、模板要求、语言。
- `/input/` 下材料：`paper.pdf`，可能有 `target-template.pptx`、起始稿 pptx、`data.csv`。
- **先读真实文件，禁止凭文件名猜内容。** 环境可能有 `environment/resources.yaml` 列出
  可用工具，先查再用。
- 中间产物一律写入 `/app/work`（下文本地示例相对路径 `work/` 即对应 `/app/work`）；最终交付物写入 `/app/output`。

## 输出契约

`/app/output/` 下：`presentation.pptx`（可编辑、含备注）、`presentation.pdf`、
`preview-*.png`、`result.json`，以及本方向特色交付物：`talkscript.md`、`beats.json`、
`beat_report.json`、`notes_report.json`、`rehearsal.json`。

### result.json 字段表

| 字段 | 形态 | 来源 |
| --- | --- | --- |
| `case_id` | string | case.json 原样 |
| `status` | success / partial / failed | 由实测 checks 与 exceptions 推出 |
| `editable_source` | `{path, format:"pptx", slides, notes_present}` | python-pptx 实测 |
| `export_artifact` | `{pdf, rendered, previews[], pages}` | PDF 页数实测；渲染工具缺失时 rendered=false 且 exceptions 记 tool_missing |
| `content_map` | 每页 `{slide, role, title, claims[], figures[], table, sources:[{kind,ref,locator,quote}], notes_present, notes_time_sec}` | beats + evidence + deck 实测 |
| `compliance_checks` | `[{check, expected, actual, pass}]` | **actual 必须脚本实测**：slide_count / export_page_match / placeholder_free / evidence_coverage / notes_coverage |
| `exceptions` | array | 材料缺失、无法判断、运行失败分别说明 |
| `uncertainties` | array | 语速假设等附加不确定项 |
| `change_records` | `[{version, slide, change, reason, rollback}]` | 每次门禁触发的修改留痕 |

`content_map.sources[].quote` 必须逐字命中论文提取文本（`make_result.py` 做子串校验，
计入 `evidence_coverage`）。

## 分阶段流程

### 阶段 0 — 读输入（先存后优检查点 A）
读取 case.json / task.md / 材料清单；记录时长、页数上限、模板路径、output_contract。
任何后续失败都要保证已落盘的 partial 可交付。

### 阶段 1 — 证据扫描
- 动作：`python3 scripts/evidence_scan.py paper.pdf --out work/evidence.json`
- 产出：分页文本（降级链 pdftotext → pymupdf → pypdf）、Figure/Table caption 索引
  （含页码）、数值锚点（值+单位+上下文+页码）。
- 门禁：exit 0 且 figures/tables/anchors 非空；三链全断 exit 2 → 走异常速查表。

### 阶段 2 — 讲稿与切拍（预算大头）
- 动作：写 `talkscript.md`（逐字稿），再结构化到 `work/beats.json`（schema 见
  `references/talkscript-format.md`）。
- 校验：`python3 scripts/beat_cut.py work/beats.json --evidence work/evidence.json
  --minutes 10 --max-slides 8 --report work/beat_report.json`
- 门禁：每拍必填字段齐全、证据引用存在、过渡句非空、拍数 ≤ 页数上限、时长合计在预算
  ±10% 内；有 error 则 exit 1，必须改稿重跑，**不要绕过**。

### 阶段 3 — 逐拍投影（幂等）
- 动作：对每拍 i：
  `python3 scripts/slide_forge.py output/presentation.pptx --beat work/beats.json#i
  --template input/target-template.pptx --evidence work/evidence.json
  --paper input/paper.pdf --log work/forge_log.json`
- 行为：deck 不存在时以模板母版新建（模板示例页清空并记录）；`forge_` 元素重跑只更新；
  备注 = 拍讲稿 + [TRANSITION] + [IF-ASKED]；页脚小字放引用；图取不到 → 带引用文字的
  占位框并在 forge_log 记 `figure_placeholder=true`。
- 检查点 B：全部拍 forge 完即是一个可交付 partial。

### 阶段 4 — 备注门禁与彩排
- 门禁：`python3 scripts/notes_lint.py output/presentation.pptx --minutes 10
  --report work/notes_report.json`（备注存在 / Jaccard ≤0.5 / 含过渡强调标记 /
  总口播 ≤ 预算；有 error exit 1）。
- 彩排：`python3 scripts/rehearse.py output/presentation.pptx --cpm 240 --wpm 150
  --report work/rehearsal.json`（逐页秒数、超速页、过薄页警告）。
- 门禁失败 → 回到阶段 2 改稿，重 forge 受影响页（幂等），并把修改记入 change_records。

### 阶段 5 — 渲染与组装
- 渲染：`soffice --headless --convert-to pdf`（并发加
  `-env:UserInstallation=file:///tmp/lo-<key>`）→ `pdftoppm -png` 生成 preview；
  soffice 缺失 → rendered=false + exceptions 记 tool_missing，**禁止未渲染声称渲染**。
- 组装：`python3 scripts/make_result.py --case case.json --task task.md
  --deck presentation.pptx --pdf presentation.pdf --previews "preview-*.png"
  --beats beats.json --evidence evidence.json --notes-report notes_report.json
  --rehearsal rehearsal.json --change-records change_records.json --out result.json`

## 预算纪律（64 请求 / 900 秒）

| 阶段 | 请求预算 | 时间预算 | 检查点 |
| --- | --- | --- | --- |
| 0 读输入 | ≤4 | 60 s | A：输入契约落盘 |
| 1 证据扫描 | ≤4 | 90 s | evidence.json |
| 2 讲稿+切拍 | ≤28 | 360 s | beat_report PASS |
| 3 逐拍 forge | ≤14 | 180 s | B：全页可交付 partial |
| 4 门禁+彩排 | ≤6 | 90 s | notes_lint PASS |
| 5 渲染+result | ≤4 | 90 s | result.json |
| 机动 | 4 | 30 s | — |

规则：讲稿写作是预算大头；每个检查点先落盘诚实 partial，再增量改进；预算将尽时优先
保证 result.json 字段完整 + status 如实（partial），不追求页数补齐。

## 异常速查表

| 异常 | 处理 |
| --- | --- |
| PDF 加密/扫描件 | evidence_scan 三链全断 exit 2 → exceptions 记 `unreadable_pdf`；用 data.csv/已有文本保底，status=partial |
| 图抽不出 | slide_forge 自动放带引用文字的占位框并记 forge_log；内容不阻断 |
| 公式为图片 | 在 beats 里引用其所在 page:/fig:，讲稿中口述，不臆造 LaTeX |
| 模板占位符不足 | slide_forge 自动降级为 forge_ 文本框；log 记录 |
| 字体缺失 | 不嵌入字体；渲染用 LibreOffice 默认替换，uncertainties 注明 |
| 页数超限 | beat_cut 阶段就拦截（拍数 > max-slides 报 error），合并拍再 forge |
| 时长超标 | notes_lint 总口播 > 预算报 error；删改讲稿而非删证据 |
| 预算将尽 | 停止新增拍；forge 已校验拍；result.json 以 partial + exceptions 交付 |
| python-pptx 缺失 | 脚本明确 stderr + exit 2；status=partial，exceptions 记 tool_missing |

## 诚实 partial 规则

- status ∈ {success, partial, failed}；partial 必须写明缺什么、为什么。
- 所有 compliance_checks 的 actual、所有报告数字必须来自脚本真实测量，禁止凭空断言。
- 禁止伪造软件状态、科学数据、基准分数；禁止未渲染却声称渲染通过。
- 任何脚本缺依赖不得直接崩溃：软导入降级或明确 stderr + 非零退出。

## 自查清单

- [ ] result.json 含 case.json `output_contract` 全部字段（原字段名）+ uncertainties + change_records
- [ ] compliance_checks 的 actual 全部是实测值
- [ ] content_map 每条 source 的 quote 逐字命中论文提取文本
- [ ] 每页有备注；Jaccard ≤0.5；含过渡/强调标记；总口播 ≤ 预算（notes_lint PASS）
- [ ] beat_cut PASS（引用存在、过渡非空、拍数与时长达标）
- [ ] deck 可打开；forge_log 无未解释的 figure_placeholder
- [ ] PDF/PNG 真实渲染，页数与 deck 页数一致
- [ ] change_records 记录每次门禁触发的修改与回滚方式
