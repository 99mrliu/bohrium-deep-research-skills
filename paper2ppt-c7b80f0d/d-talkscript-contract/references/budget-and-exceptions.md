# budget-and-exceptions.md — 预算分配、异常速查、诚实 partial

## 1. 64 请求 / 900 秒分配

讲稿写作是预算大头（阶段 2 占 ~40% 请求）。分配表（与 SKILL.md 一致）：

| 阶段 | 请求 | 时间 | 落盘检查点 |
| --- | --- | --- | --- |
| 0 读输入 | ≤4 | 60 s | 输入契约笔记 |
| 1 evidence_scan | ≤4 | 90 s | evidence.json |
| 2 讲稿+beat_cut | ≤28 | 360 s | talkscript.md + beats.json + beat_report PASS |
| 3 slide_forge ×N | ≤14 | 180 s | 全页可交付 partial deck |
| 4 notes_lint + rehearse | ≤6 | 90 s | notes_report PASS + rehearsal.json |
| 5 渲染 + make_result | ≤4 | 90 s | PDF/PNG + result.json |
| 机动 | 4 | 30 s | 门禁返工 |

**先存后优**：阶段 2 一通过就把 beats.json 落盘；阶段 3 每 forge 一页就是一个
可交付状态；阶段 5 的 result.json 优先保证字段完整、actual 实测，其次才追求
checks 全 pass。

## 2. 异常速查（含退出码语义）

| 异常 | 信号 | 处置 |
| --- | --- | --- |
| PDF 加密/扫描件 | evidence_scan exit 2（三链全断） | exceptions 记 `unreadable_pdf`；若 task 允许用 data.csv/补充材料保底；status=partial |
| pdftotext 缺失 | evidence.json 的 `engine` 显示 pymupdf 或 pypdf | 正常降级，无需处理；全部缺失才 exit 2 |
| 图取不出 | forge_log 该页 `figure_placeholder=true` | 占位框带引用文字，页面仍可追溯；不阻断 |
| 公式为图片 | evidence 文本里找不到公式 | beats 引用其 page:/fig:，讲稿口述；禁止臆造公式文本 |
| 模板无正文占位符 | slide_forge 自动用 forge_ 文本框 | 正常降级；forge_log 可查 |
| 字体缺失 | 渲染后字形替换 | uncertainties 注明；不嵌入字体 |
| 拍数 > 页数上限 | beat_cut error，exit 1 | 合并相关拍（如同节两结果合一），重跑 beat_cut |
| 总时长超预算 ±10% | beat_cut error，exit 1 | 先砍形容词与重复例证，再考虑合并拍；禁止删证据引用凑数 |
| 总口播 > 预算 | notes_lint error，exit 1 | 修剪 beat_text/过渡句，重 forge 受影响页，记 change_records |
| 备注复读 | notes_lint jaccard error | 把 bullets 改电报式短句、讲稿保持完整句 |
| 预算将尽 | 剩余请求 <10 | 停止新增拍；已 forge 页 + result.json(partial) 交付 |
| python-pptx / matplotlib 缺失 | 脚本 stderr 明确说明，exit 2 | exceptions 记 `tool_missing:<name>`；status=partial |
| soffice 缺失 | 渲染步骤失败 | export_artifact.rendered=false + exceptions 记 tool_missing；禁止声称已渲染 |

## 3. 诚实 partial 规则

1. status 只能是 success / partial / failed，由实测 checks 与 exceptions 推出
   （make_result.py `--status auto` 的逻辑：contract 字段缺失→failed；
   checks 全 pass 且无 exceptions→success；其余→partial）。
2. partial 必须在 exceptions 里逐条写清缺什么、为什么、哪一步可以补。
3. 所有 compliance_checks 的 actual 来自脚本实测；quote 逐字校验失败会拉低
   evidence_coverage 并导致 status=partial——这是特性，不要绕过。
4. 禁止伪造软件状态（如把 exit 1 写成 PASS）、科学数据、基准分数。
5. change_records 记录每次门禁触发的修改：version / slide / change / reason /
   rollback（回滚方式 = 用旧版 beats.json 重跑 slide_forge，逐页幂等）。
