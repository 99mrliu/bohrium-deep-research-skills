---
name: ppt-deck-surgery
description: 把已有 PPT 起始稿按新任务做"手术式"版本化编辑（论文/PDF/学术汇报 PPT/PPTX/slides 演示适配场景）；当 /input 提供起始稿 deck、要求按新模板/时长/受众改造并保留证据映射时触发，也覆盖从零生成后的修订轮次。
---

# ppt-deck-surgery — 起始稿手术与版本化编辑

## 核心立场

编辑一本已有 deck 是**变更工程**，不是重新写作。平台案例可能给"从零生成"（generate），
也可能给"起始稿适配"（edit/adapt）：已有一本 PPT，要求按新任务、新模板、新时长改造。
第一性问题是：**每一次改动都必须可审计、可复跑、可撤销**。凭感觉直接改文件，
改错了无法回滚、评测无法复核、Agent 自己也无法证明"只改了该改的"。
本 Skill 把编辑当作手术：先诊断、再下刀、逐刀记录、术后验伤。

## 三支柱

1. **先诊断后动刀**：`deck_probe.py` 解析起始稿（版式、占位符、逐页文本哈希、主题字体），
   `evidence_scan.py` 扫描论文锚点（Figure/Table caption、带单位数值、limitations 句），
   `plan_ops.py` 汇总出结构化手术建议骨架（诊断 + 候选动作），Agent 填决策成 ops_journal.json。
2. **ops 幂等应用**：`deck_ops.py` 支持 set_title / replace_text / set_bullets /
   insert_slide / delete_slide / move_slide / set_notes / add_figure 八种 op；
   op_id 去重幂等 + 内容级幂等；每个 op 记录 applied/skipped/failed + 原因；
   应用前快照 v1，之后每刀存 versions/vN.pptx。
3. **最小改动校验**：`surgery_lint.py` 证明未涉及页文本哈希不变、主题字节级未改写、
   每条 change_record 有 reason + 存在的 rollback 指针；`deck_diff.py` 输出页级机器 diff
   （增/删/移/标题变更/文本变更/备注变更），对接 result.json 的 change_records 形态
   `{version, slide, change, reason, rollback}`。

## 输入契约

- `/input/case.json`：含 `case_id`、`output_contract`（result.json 字段清单，运行时读取，禁止硬编码）。
- `/input/task.md`：受众、时长、页数上限、模板要求、generate/edit 模式线索。
- `/input/` 科研材料：paper.pdf、可能的 target-template.pptx、**起始稿 pptx（edit 模式的手术对象）**、data.csv。
- **先读真实文件，禁止凭文件名猜内容。**

## 输出契约

产物进 `/app/output/`：最终 deck（pptx）、render/（PDF+PNG）、result.json、
审计文件（ops_journal.json、ops_log.json、deck_diff.json、surgery_report.json）。

result.json 字段（以 case.json 的 output_contract 为准，另加 uncertainties、change_records）：

| 字段 | 形态 |
|---|---|
| case_id | 来自 case.json |
| status | success / partial / failed；partial 必须写明缺什么、为什么 |
| editable_source | `{path, format:"pptx", slides:N, notes_present:bool}` |
| export_artifact | `{pdf, rendered:bool, previews:[png...], pages:N}`；渲染工具缺失时 rendered=false + exceptions 记 tool_missing |
| content_map | 每页 `{slide, role, title, claims[], figures[], table, sources:[{kind,ref,locator,quote}], notes_present, notes_time_sec}`；quote 为论文逐字句 |
| compliance_checks | `[{check, expected, actual, pass}]`，actual 一律脚本实测（slide_count / export_page_match / placeholder_free / evidence_coverage / notes_coverage） |
| exceptions | 材料缺失、无法判断、运行失败分类说明 |
| uncertainties | 不确定项 |
| change_records | `[{version, slide, change, reason, rollback}]`，rollback 指向存在的 versions/vK.pptx |

## 分阶段流程

| 阶段 | 动作 | 脚本 | 产出 | 门禁 |
|---|---|---|---|---|
| 0. 落盘 | 读 case.json/task.md，判定 generate/edit，建立工作目录 | — | 模式判定记录 | edit 模式必须找到起始稿文件本体 |
| 1. 证据 | 扫描论文锚点 | `evidence_scan.py paper.pdf --report evidence.json` | evidence.json | engine 非 tool_missing，否则诚实降级 |
| 2. 诊断 | 解析起始稿 | `deck_probe.py 起始稿.pptx --report probe_report.json` | probe_report.json（含逐页 text_hash 基线） | 页数、主题 sha1 记录完整 |
| 3. 方案 | 生成建议骨架；**Agent 手工填 ops_journal.json** | `plan_ops.py --probe ... --task ... --evidence ... --suggest ops_suggested.json` | ops_suggested.json → ops_journal.json | 每个 op 有 op_id + reason；页码语义见 ops-schema.md |
| 4. 手术 | 幂等应用 + 快照 | `deck_ops.py 起始稿.pptx --ops ops_journal.json --out deck_final.pptx --versions-dir versions/ --log ops_log.json` | deck_final.pptx、versions/v1..vN、ops_log.json | 无 failed；**先存后优检查点：此时已可交付诚实 partial** |
| 5. 验伤 | 机器 diff + 最小改动校验 | `deck_diff.py v1.pptx final.pptx --report deck_diff.json`；`surgery_lint.py v1.pptx final.pptx --ops ... --log ... --report surgery_report.json` | deck_diff.json、surgery_report.json | lint 退出码 0（有 error 则退出 1，必须修） |
| 6. 渲染 | 真实渲染 | `render_check.py deck_final.pptx --out-dir render/ --report render_report.json` | render/（PDF+PNG） | rendered=true 且 pages==slides，否则 exceptions |
| 7. 汇总 | 生成 result.json | `make_result.py --case ... --task ... --deck ... --evidence ... --ops-log ... --diff ... --render ... --out result.json` | result.json | 含 output_contract 全字段；checks 全 pass 或诚实 partial |

generate 模式（/input 无起始稿）：先用模板生成初稿（可复用 insert_slide/set_bullets ops
从空白模板搭建），之后所有修订轮次同样走 ops_journal → deck_ops → lint 闭环。

## 预算纪律（64 请求 / 900 秒）

| 阶段 | 请求预算 | 要点 |
|---|---|---|
| 读输入 + 诊断 | ≤8 | case/task/probe/evidence 一次读完，不反复打开 |
| 填 ops_journal | ≤12 | 一次写全，避免逐 op 来回 |
| 手术 + 验伤 + 渲染 | ≤6 | 脚本链一次跑完；失败按 stderr 精修 |
| result.json + 自检 | ≤6 | 先存后优：阶段 4 完成即把当前 best 落盘 /app/output |
| 余量 | ≥50% | 留给意外重试；预算将尽时优先保证 partial 完整 |

**先存后优检查点**：阶段 4（deck_final.pptx + versions + ops_log）完成后立即复制到
/app/output；后续每个阶段完成都增量覆盖。即使阶段 5-7 全部失败，也有可编辑产物 +
完整 ops 审计链。

## 异常速查

| 异常 | 处理 |
|---|---|
| PDF 加密/扫描件 | evidence_scan 降级链全失败 → engine=tool_missing，evidence 空骨架，result.json 记 exception，evidence_coverage 如实 fail |
| 图抽不出 | add_figure 用 data.csv 现场重绘 PNG；不行则在 uncertainties 说明，不伪造图 |
| 公式为图片 | replace_text 不动它；在 content_map.sources 用所在页 quote 溯源 |
| 模板占位符不足 | set_bullets/add_figure 退到非占位符文本框；insert_slide 换用相邻版式并记录 |
| 字体缺失 | 不改主题（主题保护）；渲染差异在 uncertainties 说明 |
| 页数超限 | 优先 delete_slide 合并冗余页（须 reason 充分），禁止无脑删证据页 |
| op 应用失败 | deck_ops 记 failed 继续后续 op，退出码 2；修 journal 后重跑（幂等，已 applied 自动 skip） |
| 预算将尽 | 立即固化当前版本 + result.json（status=partial，写明缺什么） |

## 诚实 partial 规则

- status=partial 时 exceptions 必须逐条写明：缺什么、为什么、尝试过什么。
- 渲染工具缺失 → export_artifact.rendered=false + tool_missing，**禁止未渲染声称渲染通过**。
- 所有 compliance_checks.actual 来自脚本实测；测不出来就 actual=null + pass=false + exception。
- 禁止伪造软件状态、科学数据、基准分数；不提交预制答案，输出全部来自真实运行。

## 自查清单

- [ ] result.json 含 case_id + output_contract 全部原字段名 + uncertainties + change_records
- [ ] change_records 每条 {version, slide, change, reason, rollback} 且 rollback 文件存在
- [ ] surgery_lint 退出码 0（未涉及页哈希不变、主题未改写、记录完整）
- [ ] deck_diff 与 ops_journal 相互印证，无账外改动
- [ ] render/ 有真实 PDF + 逐页 PNG，pages == slides
- [ ] content_map 每条 sources.quote 是论文逐字句
- [ ] 同一 ops_journal 重跑 deck_ops 全部 skipped、无新版本（幂等）
- [ ] 合成/真实输入分清；合成示例已显著标注
