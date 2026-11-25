---
name: quality-gates
description: 为生物机制图、通路图和科研图表提供可恢复的过程质量控制：原子 checkpoint、动态输出合同、SVG/PNG/PDF 回读、确定性重跑、诚实 partial/failed、故障恢复和绑定文件哈希的原生目检。适用于需要证明图稿生成与交付过程可靠的场景，不替代论文生物学判断。
---

# Quality Gates：先保底，再逐级证明可交付

## 运行契约与科学责任

先读 `/input/case.json`、`/input/task.md`、实际论文/figure03/图注/原始数据和编辑工单。Agent 负责实体、关系、反馈、不确定性和图表编码判断；脚本只验证“规格—产物—合同”一致，不能证明生物学真实。

在 `/app/work/specification.json` 写当前案例的结构化规格，字段见 `references/state-machine.md`。最终文件放 `/app/output`，启动立即写 partial `result.json`。结果必须含原始 `case_id` 和 `case.json.output_contract` 全部字段，通常包括 `case_id,status,editable_source,export_artifact,content_map,compliance_checks,exceptions`，并补 `sources,uncertainty,change_records`。状态只用 `success|partial|failed`。

正式入口：

```bash
python3 /skills/weekly-skill/scripts/run_case.py \
  --input /input --work /app/work --output /app/output \
  --spec /app/work/specification.json
```

Python 3 与 PyMuPDF 必须实际可用；失败写 failed/partial，不伪报导出。

## 阶段门

1. **observed**：冻结 case/task/spec 路径和 SHA-256，盘点输入及版本。缺材料不得补造。
2. **specified**：规格必须由当前材料产生，记录实体、边、来源、反馈和 uncertain；不使用随包示例代替。
3. **rendered**：`simple_renderer.py` 仅把 Agent 规格变成带真实文本和稳定 ID 的 SVG。已有可编辑源的保源编辑任务不能用重绘掩盖源丢失，应保留原 DOM 和 change records。
4. **exported**：从 SVG 实际导出 PNG/PDF；checkpoint 原子写 `run_manifest.json`。
5. **audited**：回读 SVG 实体/边/方向/关系/图例，PNG 非白像素，PDF 单页及文字；验证 content_map、来源、变更记录和所有动态合同字段。任一失败返回 3，并保留失败阶段。
6. **delivered**：机器通过仍为 partial。实际打开 PNG 与 PDF 渲染页后，写 `/app/work/visual_review.json`：

```json
{"observations":["本次实际看到的标签、边和版面"],"limitations":["本次实际限制"],"png_sha256":"...","pdf_sha256":"..."}
```

哈希必须对应当前产物。加 `--visual-review /app/work/visual_review.json` 重跑，核对通过才写 success。只有机械检查不能宣称科学或视觉通过。

## 恢复、重复运行与预算

同一目录可用 `--resume`；checkpoint 记录已完成阶段，修复缺文件/缺字段后重跑。不得从 failed 直接写 success。相同输入与规格应产生确定性 SVG/PNG/PDF/result；时间不足优先保留 partial result、可编辑源和已执行检查。900 秒内先保底后改进。

## 合成最小示例

`examples/synthetic_case/` 全部为 **SYNTHETIC 合成示例**。执行：

```bash
python3 scripts/run_case.py --input examples/synthetic_case/input \
  --work /tmp/quality-work --output /tmp/quality-output \
  --spec examples/synthetic_case/input/specification.json
```

真实生成 SVG/PNG/PDF、manifest、content map、审计和 result；未提供真实目检时保持 partial。`python3 scripts/validate_example.py` 另行验证缺 PNG、缺 result 字段、科学审核失败和恢复路径。旧 `runner.py` 是本 bundle 内部审计库；正式案例统一使用 `run_case.py` 标准入口。
