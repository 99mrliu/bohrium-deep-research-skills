---
name: figure-qc-repair-loop
description: >-
  从论文 PDF / 数据表等研究材料生成或编辑实验装置示意图、步骤流程图、物料流向图、
  技术路线图，且对正确性与可验证性有要求、或导出的 PNG/PDF 必须通过检查时使用。
  核心是"质检缺陷驱动的修复闭环"：轻量 IR（中间表示）→ 渲染 → 自动 QC（10 项
  缺陷检测器：悬空连线、流向反向、编号错位、标签与来源不符、图例不一致、文字溢出、
  字体风险、画布溢出、导出失败、引文未核实）→ agent 修 IR → 重渲染重检，最多 2 轮，
  然后带残余缺陷清单诚实交付。不适用：需要精美排版引擎的出版级插图（本技能渲染器
  刻意简单）、纯数据图表（折线/柱状图）、以及不要求可追溯/可机检的一次性草图。
---

# figure-qc-repair-loop — 质检缺陷驱动修复闭环

生成/编辑科研图示时，经典翻车点（部件与材料对不上、凭空补连接、箭头反向、编号错位、
图例与图形不一致、无源文件、中文变方框、画布溢出）都被编码成**自动检测器 + 文档化修复
动作**（见 `references/failure-taxonomy.md`）。流程：agent 写 IR → 脚本渲染 → 脚本质检
→ agent 只改 IR → 重渲染重检，最多 2 轮。每轮 before/after 的 QC 报告即质量提升证据。

## 铁律

1. **agent 只编辑 IR（figure_ir.json），永不手改 SVG**，SVG 永远由 ir_render.py 重新生成。
2. **永不删除或弱化任何检查来"通过"质检**；预算耗尽就 status=partial + 残余缺陷清单。
3. 输出 JSON 报告（qc_report / loop_log / export_report / result.json）**始终写出**，即使中途失败。
4. 连接关系只画源文本支持的；源文本没有就连不上——宁可少连，不可凭空补。

## 步骤表

| 步骤 | 动作 | 命令 |
|---|---|---|
| 1 | 读任务与合同：读 `/task.md` 与 `/input/case.json`，记录 case_id，把 output_contract 每个字段名**逐字抄下**（result.json 用） | `cat /task.md /input/case.json` |
| 2 | 材料盘点到 `/app/work/sources/`：PDF 用 `pdftotext -layout in.pdf out.txt`（缺工具则记 note 降级）；表格直接复制 | `pdftotext -layout /input/xx.pdf /app/work/sources/xx.txt` |
| 3 | **先写 result.json 骨架**到 `/app/output/result.json`：case_id + 合同字段 + status:"in_progress"，之后每轮更新 | — |
| 4 | 按 `references/ir-schema.md` 编写 IR `/app/work/figure_ir.json`（节点/边都带 source.locator + source.quote 原文片段） | — |
| 5 | 跑一轮闭环（渲染→QC→干净则导出→导出复检；自动写 loop_log.json） | `python3 scripts/repair_loop.py --ir /app/work/figure_ir.json --workdir /app/work --source-dir /app/work/sources --out-dir /app/output` |
| 6 | 若返回 needs_repair（退出码 2）：读打印的 error 清单，按 suggested_fix **改 IR**，用**同一命令**重跑（轮次自动递增） | 同步骤 5 |
| 7 | 收尾：clean（退出码 0）→ status:"ok"；partial（退出码 3）→ status:"partial" 并把 `loop_log.json.residual_defects` 抄进 result.json 的 uncertainties；补 sources/change_records/qc 历史 | — |

手动单步（调试时用，正常情况下 repair_loop 已覆盖）：

```bash
python3 scripts/ir_render.py  figure_ir.json -o figure.svg            # 渲染
python3 scripts/qc_figure.py  figure_ir.json figure.svg sources/ --report qc_report.json
python3 scripts/export_svg.py figure.svg --pdf figure.pdf --png figure.png --report export_report.json
python3 scripts/qc_figure.py  figure_ir.json figure.svg sources/ --report qc_report.json \
        --export-pdf figure.pdf --export-png figure.png               # 导出后复检
```

## 异常处理（缺陷代码 → 检测 → 原因 → 修复）

| 代码 | 检测 | 常见原因 | 修复动作 |
|---|---|---|---|
| DANGLING_EDGE | 边端点 id 不在 nodes；箭头端点几何上未触及任何节点盒 | 改了节点 id 忘改边；凭空补连接 | 端点改为存在的 id；源文本无此连接则删边 |
| REVERSED_FLOW | 顺序语义边 from.order ≥ to.order；箭头方向与声明顺序矛盾 | 物料/步骤流向画反 | 交换 from/to 或修正 order 使沿流向递增 |
| NUMBERING_GAP | order 不是 1..n 连续；与源文本枚举步数不符 | 步骤编号与正文错位 | 重排 order 为连续整数并对应正文 |
| LABEL_SOURCE_MISMATCH | 标签词元在源文本找不到（warn） | 部件名称与材料对不上/自造词 | 换用源文本原词；合理缩写需在 uncertainties 说明 |
| LEGEND_MISMATCH | 图例色块/线型 vs 边实际样式（解析 SVG） | IR legend 里残留旧颜色 | 删掉 legend 自定义 color/dash 或整个 legend（自动生成） |
| TEXT_OVERFLOW | 标签估算宽（CJK 1em/ASCII 0.55em）>盒宽 error，>90% warn | 标签太长 | 用源文本简称缩短；或 canvas 加大尺寸 |
| FONT_RISK | 有 CJK 但系统无中文字体（warn） | 容器无 Noto/文泉驿 → 中文变方框 | 装字体或靠回退链；导出后目检 PNG |
| CANVAS_OVERFLOW | 元素包围盒超出 viewBox | canvas 尺寸给小了 | canvas 改大或改回 "auto" |
| EXPORT_FAIL | PNG/PDF 缺失/零字节/文件头错 | 导出工具全部失败 | 看 export_report.json attempts 换工具；不行就只交 SVG 并声明 |
| UNVERIFIED_QUOTE | source.quote 在源文本找不到（warn） | 引文凭记忆改写 | 从抽取文本复制原文替换；仅记录不阻断 |

**预算耗尽**：2 轮后仍有 error → repair_loop 照样导出并置 partial；把
`loop_log.json.residual_defects` 原样抄进 result.json `uncertainties`，写清每个残余缺陷的
code/evidence/影响。这是合规交付；删检查、改检测器、手改 SVG 蒙混均为违规。

## 预算纪律（64 请求 / 900 秒）

- 闭环**硬上限 2 轮**（repair_loop --max-rounds 2）；第 3 次渲染前必须停手交 partial。
- 每轮 = 1 次 repair_loop 调用；步骤 1–4 合计不超过约 10 次工具调用。
- result.json 骨架第 3 步就落盘，之后每轮更新——任何中断都有部分结果可查。
- 不追求排版美观迭代；QC 干净即停。

## EDIT 类任务（保源编辑）

同一闭环：先把用户给的图/描述逆向成 IR（尽量保留原结构、id、文案），把每处修改写进
`change_records`（{round, 修改的 IR 字段, 旧值, 新值, 依据的缺陷 code}），再按步骤 5–7 执行。

## result.json 结构

```json
{"case_id": "...", "<output_contract 字段逐字>": "...",
 "status": "ok|partial|failed",
 "sources": [{"locator": "...", "used_for": "..."}],
 "uncertainties": ["残余缺陷/降级说明，含 code 与 evidence"],
 "change_records": [...],
 "qc": {"rounds": [{"round": 1, "errors": 5, "codes": [...]}, {"round": 2, "errors": 0}],
        "loop_log": "/app/work/loop_log.json"}}
```

详见 `references/loop-protocol.md`（轮次预算/升级/诚实 partial 规则）与
`examples/minimal/`（完整两轮合成示例）。
