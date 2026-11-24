# gated-pipeline-deck — 流水线契约（阶段 / 检查点 / 门禁 / 续跑手册）

本文件是 `gated-pipeline-deck` 的绑定契约：任何对脚本行为的修改都必须保持这里的
语义不变。读者：Harness Agent、复跑者、评审。

## 1. 阶段机总览

| 阶段 | 名称 | 职责 | 主要产出 | 谁执行 |
|-|-|-|-|-|
| S0 | bootstrap-deps | 缺 python 包则 pip 安装；探测 soffice/pdftoppm；记录 degraded | work/tools.json | 脚本 |
| S1 | read-inputs | 读 case.json/task.md/全部材料并做 sha256 台账；**立即写 partial result.json** | work/inputs_inventory.json, output/result.json, output/qa_gates.json | 脚本 |
| S2 | extract-source | PyMuPDF 逐页文本 + 图抽取（内嵌位图优先，矢量图整页渲染）；数字候选索引 | work/paper/extract.json, paper_text.txt, pages/, figs/ | 脚本 |
| S3 | dissect-template | 模板母版/版式/占位符清单、页面尺寸 | work/template_report.json | 脚本 |
| S4 | plan-skeleton | 预填 slide_plan.json 骨架（证据锚点候选），**STOP 等待 Agent 编辑** | work/slide_plan.json | 脚本预填 → **Agent 编辑** |
| S5 | plan-gate | 机器门禁：schema / 页型覆盖 / 证据锚点可解析 / 数字逐字 | work/gates/plan_gate.json | 脚本 |
| S6 | build-deck | 以模板为底 python-pptx 构建，占位符填充，图等比缩放，notes 讲稿 | output/deck.pptx, work/build_report.json | 脚本 |
| S7 | export-render | soffice→PDF；pdftoppm→PNG（缺失退回 pymupdf 栅格）；页数一致性 | output/deck.pdf, output/preview/*.png, work/export_report.json | 脚本 |
| S8 | qa-gate | 汇总六个机器门禁，overall = 最差门禁 | output/qa_gates.json, work/gates/qa_gates.json | 脚本 |
| S9 | finalize-result | 写齐 result.json 终态、打印逐页核对清单 | output/result.json, output/pipeline_manifest.json | 脚本 |

**唯一需要模型创作的环节在 S4 与 S5 之间**（编辑 slide_plan.json）。其余全部是
脚本阶段，确定性、可重放。

## 2. 检查点格式与幂等保证

每个阶段成功后写 `/app/work/checkpoints/S<n>.json`：

```json
{
  "stage": "S2",
  "name": "extract-source",
  "status": "ok",
  "inputs_sha": "<sha256 of 输入文件集合（路径+内容）>",
  "outputs": ["/app/work/paper/extract.json", "..."],
  "wall_time_s": 1.23,
  "at": "2026-01-01T00:00:00+00:00"
}
```

失败时写 `/app/work/checkpoints/S<n>.failed.json`：`{stage, name, status:"failed",
error, resume_hint, at}`，进程以非零码退出，stdout 打印 `FAIL Sn ...` 与
`RESUME: <精确命令>`。

幂等规则：

1. 重跑时，若 `S<n>.json` 存在、`status=="ok"`、且当前输入指纹 == `inputs_sha`，
   阶段被跳过，日志打印 `skip Sn (checkpoint valid)`。
2. 任一输入文件内容变化（sha256 改变）→ 该阶段检查点自动失效并重跑；其下游阶段
   因为输入包含上游产物，也随之失效重跑（级联失效）。
3. 例外：**S4 的输入指纹不含 slide_plan.json**——plan 是 S4 的产出而非输入，
   Agent 编辑 plan 不会触发 S4 重跑，编辑内容不会被覆盖。若上游（论文/模板）
   变化导致 S4 重跑，而已存在的 plan 与上次预填不同，S4 会先把旧 plan 备份为
   `slide_plan.json.backup-<ts>` 再重新预填。
4. 想强制重跑某阶段：删除对应 `checkpoints/S<n>.json` 再跑 `finish`。

各阶段输入依赖（决定级联失效范围）：

| 阶段 | 输入指纹 |
|-|-|
| S0 | （空，总是可跳） |
| S1 | /input 下全部文件 |
| S2 | work/inputs_inventory.json |
| S3 | work/inputs_inventory.json |
| S4 | work/paper/extract.json + work/template_report.json |
| S5 | work/slide_plan.json + work/paper/extract.json |
| S6 | work/slide_plan.json + work/gates/plan_gate.json + work/template_report.json |
| S7 | output/deck.pptx + work/build_report.json |
| S8 | work/gates/plan_gate.json + build_report.json + export_report.json |
| S9 | work/gates/qa_gates.json + build_report.json + export_report.json |

## 3. partial-first 保证

- S1 完成后，`/app/output/result.json` 必然存在：`status="partial"`，`case_id`
  与 case.json `output_contract.fields` 声明的**全部字段**都在（未完成的字段是
  诚实占位，不编造），`sources` 已列出全部输入文件及 sha256。
- S1 同时初始化 `/app/output/qa_gates.json`：六个门禁全部 `degraded`
  （"not yet evaluated"），S5/S8 逐步更新。
- 每个阶段完成后 `/app/output/pipeline_manifest.json` 被重写为当前最新状态。
- 推论：**在任何预算点被杀死，`/app/output` 都是一个合法的、诚实的 partial**。

## 4. 机器门禁（qa_gates.json）

`/app/output/qa_gates.json`：`{case_id, gates: [{gate, status, evidence_path,
detail}], overall, updated_at}`。`status ∈ {pass, fail, degraded}`；
`overall` = 全部门禁中最差者（fail > degraded > pass）。

| 门禁 | 判定 | 评估于 |
|-|-|-|
| contract-fields-present | result.json 含 case_id + output_contract 全部字段 | S8 |
| evidence-anchors-resolve | 每页 evidence 锚点可解析：页码在范围内且 quote 逐字命中该页；图标签在抽取清单或源文中；figures[].path 文件存在 | S5 |
| numbers-verbatim-vs-source | bullets/claim 中每个数字 token 在源文中逐字出现（空白归一化；拆行数字去空白兜底） | S5 |
| template-layouts-used | 每页用模板真实版式构建；占位符缺失用了 textbox 兜底 → degraded；版式名不在模板版式清单 → fail | S8 |
| export-page-parity | deck.pdf 页数 == deck.pptx 页数；无渲染器 → degraded；不一致 → fail | S8 |
| preview-pages-rendered | PNG 预览数 == PDF 页数；回退渲染路径 → degraded；0 张 → fail/degraded | S8 |

**纪律：门禁 fail 或 degraded 时不允许把 result.json 标为 success；S9 只会写
success（全 pass）/ partial（有产物但有门禁未过）/ failed（deck 都没产出）。**

## 5. 续跑手册（Harness Agent 失败处置）

统一入口（两条命令覆盖全流程）：

```bash
S=/skills/weekly-skill
python3 $S/scripts/run_case.py prepare --input /input --work /app/work --output /app/output
# ... Agent 编辑 /app/work/slide_plan.json ...
python3 $S/scripts/run_case.py finish  --input /input --work /app/work --output /app/output
```

| 症状 | 处置 |
|-|-|
| 任何阶段 FAIL，stdout 有 `RESUME:` 行 | 修复其指出的问题（通常是输入/plan），**原样重跑该命令**，已完成阶段自动 skip |
| 进程被杀/超时 | 直接重跑 `finish`；检查点保证从最近成功阶段续跑 |
| S5 plan-gate FAIL | 按 stdout 的 `slide k bullets[j]: ...` 定位修复 slide_plan.json，重跑 `finish` |
| finish 报 "plan 未编辑"（S4 预填 sha 未变） | 说明忘了编辑 slide_plan.json；编辑后重跑 `finish` |
| 想重做 S6 之后 | `rm /app/work/checkpoints/S{6,7,8,9}.json` 后重跑 `finish` |
| 换论文/换模板 | 直接重跑 `prepare`→编辑 plan→`finish`；S1 输入指纹变化会级联失效全部下游 |
| 想单独调试 plan 门禁 | `python3 $S/scripts/plan_gate.py --input /input --work /app/work --output /app/output` |
| 随时查看进度 | `python3 $S/scripts/run_case.py status --input /input --work /app/work --output /app/output` |

## 6. 预算守则（64 请求 / 900 秒）

- **脚本便宜的阶段全部交给脚本**：S0–S3、S5–S9 共 9 个阶段零模型调用，
  总墙钟通常 <60 秒（含 soffice 导出）。
- 模型只花在 S4→S5 之间：读 slide_plan.json 骨架 + 抽取摘要（work/paper/），
  一次编辑完成 mainline/claim/bullets/notes。预算建议：
  prepare(1) + 读骨架/材料(≤2) + 编辑 plan(1) + finish(1) + status 核对(1) ≤ 6 次。
- 不要手工改 pptx XML；占位符缺失交给 S6 的 textbox 兜底（会记 degraded，可解释）。
- 不要在脚本阶段失败时重试模型创作——先看 `RESUME:` 行。
- 快超预算时什么都别做：`/app/output` 已经是合法 partial。
