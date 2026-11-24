# modes-and-contract.md — generate/edit 双模式判定、result.json 契约、异常速查与预算纪律

## 双模式判定

| 信号 | 模式 | 入口 |
|---|---|---|
| /input 下存在起始稿 pptx（非模板，如 starting-deck.pptx、draft.pptx），或 task.md 出现 adapt/edit/revise/改造/修订 | **edit** | deck_probe 起始稿 → 手术全流程 |
| 只有 paper.pdf + target-template.pptx，无起始稿 | **generate** | 从模板空白 deck 起步，全部内容经 insert_slide/set_bullets ops 搭建，之后修订轮次同样走 ops 闭环 |

判定要点：**先读真实文件**——target-template.pptx 通常 0 页或仅示例页（用 deck_probe 看
slide_count 与占位符即知）；起始稿有实质页内容。两者同时存在时：起始稿是手术对象，
模板是主题/版式参照；若起始稿主题与模板不符，也**不**整体换主题（主题保护），
在 uncertainties 说明。拿不准时按 edit 处理并在 exceptions 写明判定依据。

generate 模式的等价物：先建一份"空 journal + 全 insert_slide ops"搭出初稿（即 v1=模板），
后续所有改动仍然 ops 化。这样两种模式共享同一套审计/回滚/lint 机制。

## result.json 契约

- 字段名与顺序以 case.json 的 `output_contract` 为准（运行时读取，禁止硬编码）；
  契约之外必须另加 `uncertainties`、`change_records`。
- 已核实形态：
  - `editable_source`: `{path, format:"pptx", slides:N, notes_present:bool}`
  - `export_artifact`: `{pdf, rendered:bool, previews:[png...], pages:N}`
  - `content_map`: 每页 `{slide, role, title, claims[], figures[], table, sources:[{kind,ref,locator,quote}], notes_present, notes_time_sec}`
  - `compliance_checks`: `[{check, expected, actual, pass}]`，actual 全部脚本实测
  - `exceptions`: 数组
- 推荐 checks（make_result.py 默认实测）：slide_count（页数上限，从 task.md 解析）、
  export_page_match（渲染页数==deck 页数）、placeholder_free（占位/栏目名标题计数）、
  evidence_coverage（有 claims 的页中带逐字 quote 溯源的比例）、notes_coverage（备注覆盖比例）。

## change_records 写法

来自 ops_log.json 的 applied 记录，每条：

```json
{"version": "v3", "slide": 3,
 "change": "replace_text: replaced 1x '99.9 ms' -> '42.7 ms'",
 "reason": "plan_ops diagnostic: '99.9 ms' not found in evidence; paper page 2 states ...",
 "rollback": "/abs/versions/v2.pptx"}
```

- `version`：该 op 应用后产生的版本号；`rollback`：应用前的版本文件（必须真实存在，
  surgery_lint 校验）。
- skipped/failed 的 op 不进 change_records；failed 进 exceptions。

## 异常速查

| 异常 | result.json 处理 |
|---|---|
| PDF 加密/扫描件、无文本层 | evidence engine=tool_missing；evidence_coverage 实测 fail；exception: tool_missing |
| 起始稿损坏/非 pptx | deck_probe 退出 2；status=failed + exception |
| python-pptx 缺失 | deck_ops 退出 3（不伪造编辑）；status=partial（只有诊断产物） |
| soffice 缺失 | render_check 退出 3；export_artifact.rendered=false + tool_missing |
| 渲染页数与 deck 页数不符 | export_page_match pass=false；status≤partial；查是否有隐藏页/空白页 |
| op failed | 进 exceptions；修正 journal 重跑（幂等） |
| 页数超限 | delete_slide 需充分 reason；无法合规时 slide_count 如实 fail |

## 预算纪律

- 64 请求 / 900 秒：诊断 ≤8、填 journal ≤12、脚本链 ≤6、result+自检 ≤6，余量留给重试。
- **先存后优**：deck_ops 完成（阶段 4）即把 deck_final.pptx + ops 审计文件复制到
  /app/output；之后每阶段增量覆盖。任何时刻中断都有诚实 partial。
- 预算将尽：立即固化当前版本，result.json status=partial 写明缺口，不赌最后一把大改。
