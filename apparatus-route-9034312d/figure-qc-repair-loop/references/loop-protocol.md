# 修复闭环协议（loop protocol）

render → QC → 修 IR → re-render → re-QC 的有界循环。执行器：
`scripts/repair_loop.py`（每调用一次 = 一轮，轮次由 `loop_log.json` 自动递增）。

## 轮次预算

- **硬上限 2 轮**（`--max-rounds 2`，默认即 2）。第 3 次渲染前必须停手。
- 预算的语义：round 1 检出缺陷 → agent 修 IR → round 2 复检。round 2 仍有 error 即耗尽。
- 每轮产物全部保留：`figure.roundN.svg`、`qc_report.roundN.json`、`loop_log.json`——
  round1 vs round2 的缺陷计数对比就是**可验证的质量提升证据**，禁止删除或回写篡改。

## 一轮内部顺序

1. `ir_render.py` 渲染 IR → `figure.roundN.svg`（渲染失败：记 log，status=failed，立即止损）。
2. `qc_figure.py` 跑全部 IR/SVG 级检测器 → `qc_report.roundN.json`。
3. 仅当（无 error）或（本轮已是最后一轮）时：复制为 `figure.svg` 并
   `export_svg.py` 导出 PDF/PNG，随后带 `--export-pdf/--export-png` 复检（EXPORT_FAIL）。
4. 判定并记账（见下）。

## 判定与升级

| 本轮结果 | action | 后续 |
|---|---|---|
| errors = 0（导出复检也通过） | clean | 交付；result.json status="ok"；warn 照实列入 uncertainties |
| errors > 0 且 round < max | needs_repair | **agent 按 suggested_fix 编辑 IR**（永不手改 SVG），同一命令重跑 |
| errors > 0 且 round = max | partial | 尽力交付：SVG/PDF/PNG 照交，`loop_log.json.residual_defects` 逐条抄入 result.json `uncertainties`，status="partial" |
| 渲染/质检脚本自身失败 | failed | 保留现场与 log，status="failed"，说明失败环节 |

升级规则：EXPORT_FAIL 在预算内也走 needs_repair（可重试导出或换工具）；
FONT_RISK/LABEL_SOURCE_MISMATCH/UNVERIFIED_QUOTE 等 warn 不消耗轮次。

## 诚实 partial 规则（不可协商）

1. 残余缺陷**逐条**列出：code、element、evidence、影响说明；不允许概括为"有些小问题"。
2. 永不删除、弱化或跳过任何检测器；永不手改 SVG 让几何检查"碰巧通过"；
   永不修改历史轮次的 qc_report/loop_log。
3. partial 不等于失败：它表示"产物可用，但列出的缺陷未在预算内修完"，
   下游可据 uncertainties 决定是否人工接管。
4. result.json 必须体现 qc 历史：每轮 errors/warns/codes 计数（before/after 证据）。

## EDIT 任务补充

- 先把原图逆向为 IR（保留原节点 id/文案/结构），再进入同一闭环。
- 每处 IR 修改记入 `change_records`：`{round, path（如 edges[1].to）, old, new, 依据缺陷 code}`。
- 保源原则：未被缺陷报告指向的内容不做"顺手美化"。

## 与其他 bundle 的分工

本闭环不做证据引文门控（quote 仅轻核对、warn 级），不做排版引擎（渲染器刻意简单）。
遇到需要精美版式或严格逐句溯源的任务，应在 uncertainties 声明该边界。
