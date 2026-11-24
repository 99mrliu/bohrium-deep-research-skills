---
name: editorial-delivery-forge
description: 审稿回复与论文修改场景下，把裁决与落稿结果锻造成编辑部就绪交付件（修订稿、回复信、定位表、证据清单）并渲染真实 PDF/PNG 预览与自包含 HTML 审查包；当任务要求处理审稿意见、产出可提交交付件或需要可目检预览时触发。
---

# editorial-delivery-forge — 编辑部就绪交付锻造

## 用途

在「审稿回复与论文修改」任务中，上游判断（逐条裁决 + 锚点落稿）只做最小可用实现；
本 Skill 的第一公民是**交付件质量**：把修订结果锻造成可直接交编辑部的产物——统一排版
规范的修订稿（带 CHG 修改标记与修改摘要表）、结构化回复信（信头、总述、逐条、收口表）、
修改定位表、证据清单，全部编号同源一致；随后渲染真实 PDF/PNG 预览，并生成自包含
HTML 审查包（改动卡片 before/after 对照 + 覆盖矩阵 + 证据表 + 可点击锚点跳转），
让编辑/评审一键目检。渲染与一致性是本 Skill 的灵魂。

## 运行契约（必须严格遵守）

- 输入：`/input/case.json` 与 `task.md`；材料在 `materials/manuscript-baseline.md`
  （组织方基线摘要）与 `materials/reviewer-comments.md`（意见摘要）。
- 工作目录 `/app/work`；最终产物与 `result.json` 放 `/app/output`。
- `result.json` 必须含**原始 case_id** 和案例 `output_contract` 的**全部字段**
  （字段名以 case.json 的 output_contract 为准），并含诚实的 `status`、`sources`、
  `uncertainty` 与修改记录。缺字段即判失败；做不到就诚实写 `partial`，禁止伪装完成。
- 可编辑产物（稿件/改稿）应有**真实渲染的 PDF/PNG 预览**供检查（见
  `references/preview_protocol.md`）。
- **预算：64 次模型请求、900 秒。第一条命令必须落一个合法的 partial result.json
  （`scripts/make_result.py --status partial`），随后全部机械工作交给脚本，Agent 只做
  判断与润色。**
- 平台约束：≤50 个 UTF-8 文本文件、单文件 ≤500KB、总计 ≤2MB、无符号链接、无二进制。
  脚本只用 Python 3 标准库；matplotlib 缺失时降级（写 `render_manifest.json` 注明）不阻断。

## 快速路径（两条命令；cwd 无关）

```bash
export SKILL=/skills/weekly-skill

# 0) 预算安全网：第一条命令先落合法 partial result.json
python3 "$SKILL/scripts/make_result.py" --case /input/case.json \
  --outdir /app/output --status partial --uncertainty "处理进行中，交付件尚未生成"

# 1) prepare：Agent 阅读材料后手写两个 JSON（判断），脚本做最小锚点落稿（机械）
#    - /app/work/decisions.json：逐条子要求 R#.# 的裁决 + 证据清单 EV-## + uncertainties
#    - /app/work/edits.json：逐字唯一锚点定位的修改 CHG-##
python3 "$SKILL/scripts/apply_edits.py" \
  --baseline materials/manuscript-baseline.md \
  --edits /app/work/edits.json --work /app/work

# 2) forge：同源锻造全部交付件 + 渲染预览 + HTML 审查包 + 最终 result.json
python3 "$SKILL/scripts/forge_pack.py" --work /app/work --out /app/output --case /input/case.json
python3 "$SKILL/scripts/render_preview.py" --outdir /app/output/preview \
  /app/output/revised-manuscript.md /app/output/response-letter.md /app/output/change_record.md
python3 "$SKILL/scripts/html_pack.py" --work /app/work --out /app/output --case /input/case.json
python3 "$SKILL/scripts/make_result.py" --case /input/case.json --outdir /app/output \
  --status partial --change-records /app/output/change_record.md \
  --artifact revised_manuscript=/app/output/revised-manuscript.md \
  --artifact response_letter=/app/output/response-letter.md \
  --artifact change_locations=/app/output/change-locations.json \
  --artifact evidence_checklist=/app/output/evidence-checklist.json \
  --artifact preview=/app/output/preview \
  --artifact review_pack=/app/output/review_pack.html
```

（artifact 的字段名必须以实际 case.json 的 `output_contract` 为准，上面只是示例；
`make_result.py` 会自动补全缺失字段为 null 并把 status 强制为 partial。）

## 交付件规范摘要（详见 references/deliverable_style.md）

- **编号体系全局唯一、三方同源**：意见子要求 `R#.#`（如 R1.2）↔ 修改 `CHG-##`
  （如 CHG-03）↔ 证据 `EV-##`（如 EV-01）。修订稿、回复信、定位表/证据清单/HTML 包
  全部由 `forge_pack.py` 从同一数据源（decisions.json + changes.json）生成，编号
  不可能漂移；禁止手工另写任何一份交付件。
- **修订稿**：正文内嵌 `⟦CHG-##-BEGIN⟧…⟦CHG-##-END⟧` 可见标记；无法补做的改动用
  `【待补数据 EV-##】` 诚实占位；文末附「修改摘要表」（CHG | 关联意见 | 位置 | 类型 | 摘要）。
- **回复信**：信头占位（稿件编号/标题/日期/责任编辑留空待填）→ 总述（用统计数字：
  意见数、子要求数、接受/部分/无法完成各几）→ 逐条块（每条子要求：要点、裁决、
  回应、关联 CHG/EV）→ 收口两表（裁决汇总表、修改—证据对照表）。
- **语言随意见**：审稿意见用什么语言，回复信与批注就用什么语言。

## 事实红线（违者判负）

- 只修订 `materials/manuscript-baseline.md` 指定基线；只处理
  `materials/reviewer-comments.md` 实际给出的意见，不得虚构意见。
- **不得冒称真实审稿人逐字要求**（意见摘要≠原文）；不得冒称真实补做了实验/数据
  （无法补做的用 `【待补数据 EV-##】` 占位并在证据清单标 `pending`/`impossible`）；
  不得冒称原作者已改稿；不得冒称编辑部已接收。
- 实质性修改必须真实落在基线文本中（逐字锚点），回复信里声称的每处修改必须能在
  revised-manuscript.md 中找到对应 CHG 标记——`html_pack.py` 的覆盖矩阵即用于此核查。

## 异常处理表

| 异常 | 处理 |
|---|---|
| matplotlib 缺失 | `render_preview.py` 写 `preview/render_manifest.json` 注明降级原因后正常退出（exit 0），不阻断后续步骤；result.json 的 uncertainty 中注明无预览 |
| 中文字体缺失 | 按 PingFang SC → Hiragino Sans GB → STSong → Noto Sans CJK 回退链探测；全部缺失仍真实渲染（中文呈占位框）并在 manifest 注明 `cjk_font_available: false` |
| 锚点找不到/不唯一 | `apply_edits.py` 不中断：该 CHG 记 `failed`，进 `apply_report.json` 的 `pending_review`，status 记 `pending_review`；Agent 修正锚点后重跑 |
| 意见冲突 | decisions.json 中对该子要求裁决 `partial`/`decline` 并在 rationale 写明冲突点，回复信逐条块如实呈现，不许静默择一 |
| 无法补做（算力/数据不可得） | 裁决 `unable` + 证据 `impossible`，正文仅允许加「局限性说明」类诚实表述，严禁编造数据 |
| 长稿件分页 | `render_preview.py` 自动按 A4 比例逐页切分，每页一张 PNG，页眉含文件名与页码；合并输出 preview.pdf |
| 首条命令 | 必须是 `make_result.py --status partial` 落安全网 result.json |

## 脚本清单（均为 Python 3 标准库；仅 render_preview 可选依赖 matplotlib）

| 脚本 | 职责 |
|---|---|
| `scripts/apply_edits.py` | 最小锚点落稿引擎：逐字唯一锚点匹配，插入 CHG 标记，产出 `revised_marked.md`、`changes.json`、`apply_report.json`（含 pending_review） |
| `scripts/forge_pack.py` | 从 decisions.json + changes.json 同源锻造 `revised-manuscript.md`、`response-letter.md`、`change-locations.json`、`evidence-checklist.json`、`change_record.md` |
| `scripts/render_preview.py` | matplotlib 逐段排版文字到 A4 比例页面，每页 PNG 存 `preview/`，合并 `preview.pdf`；降级写 `render_manifest.json` |
| `scripts/html_pack.py` | 生成自包含 `review_pack.html`：状态徽标、改动卡片（before/after+定位+子要求）、覆盖矩阵（可点击锚点跳转）、证据表、不确定性列表 |
| `scripts/make_result.py` | 组装 `result.json`：case_id、status、sources、uncertainty、output_contract 全部字段（--artifact）、change_records；缺字段自动降级 partial |

## 最小示例

`examples/` 内含合成示例（case_id `SYNTH-EXAMPLE-ONLY-005`，**合成示例，非正式案例
结果**）：虚构短稿 + 2 条意见 3 子要求（含 1 条无法补做）+ 填好的
decisions.json/edits.json + `run_example.sh` 端到端脚本
（落稿→forge→render→html→result，产物到 `examples/output/`，该目录为运行产物、
不属于 bundle 本体）。运行：

```bash
bash examples/run_example.sh
```
