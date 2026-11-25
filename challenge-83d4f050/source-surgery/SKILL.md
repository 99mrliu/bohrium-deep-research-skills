---
name: source-surgery
description: 对现有生物机制图或通路图的可编辑 SVG 做最小、可回滚、可核对的定向修改；按稳定 ID 改标签、边型、样式或位置，保留无关图层与元数据，生成真实 PNG/PDF、逐项变更记录和标准 result.json。适用于 figure03 保源编辑；无源大图重绘或非生物美术不触发。
---

# Source Surgery：源文件保留优先

## 运行契约

先读 `/input/case.json`、`/input/task.md`、实际论文/figure03/图注/数据及 `artifacts/figure-workorder.json`。不得根据文件名猜机制，不得把位图当成可编辑矢量源。中间文件放 `/app/work`，最终文件放 `/app/output`，必须写 `/app/output/result.json`。

`result.json` 保留原始 `case_id` 和 `case.json.output_contract` 的全部字段，通常为 `case_id,status,editable_source,export_artifact,content_map,compliance_checks,exceptions`，并补 `sources,uncertainty,change_records`。状态只用 `success|partial|failed`。缺可编辑源、操作失败、缺导出或尚未目检均不得写 success；partial 必须说明限制。

正式入口：

```bash
python3 /skills/weekly-skill/scripts/run_case.py \
  --input /input --work /app/work --output /app/output \
  --operations /app/work/operations.json
```

工单可位于 `/input/artifacts/figure-workorder.json`，也可由 Agent 将其中操作规范化为 `/app/work/operations.json`。操作数组支持 `set_text,set_attribute,set_style,move_by,replace_edge_kind`；具体字段见 `references/operations.md`。每个目标必须是唯一稳定 ID。

## 科学与事务流程

1. 核对 figure03 原图、图注和正文，写清 changed/unchanged 范围；生物方向与关系修改必须有原始材料依据，不能由脚本猜测。
2. 启动即写 partial result；记录原 SVG SHA-256。拒绝 DOCTYPE/ENTITY、缺 ID、重复 ID、危险 CSS/外部链接和覆盖原件。
3. 全部操作在内存副本执行。任一失败即最终 edited SVG/PNG/PDF 不交付，result=failed，原件不变。
4. 对非目标元素比较直接内容及完整子树哈希；保留 layers、metadata、defs、notes。变更记录含 before/after XML、操作原因和来源定位。
5. PyMuPDF 从编辑后的真实 SVG 生成 `figure_edited.png/pdf`，检查 PDF 单页文字回读。打开 PNG 和 PDF 渲染页目检标签、箭头、布局和保护内容。
6. 初次机器成功保持 partial。目检后把含具体观察的 JSON 作为 `--visual-review` 再运行，才消除 pending exception 并写 success；科学不确定性仍需保留。

## 无源任务与数据

只有确认无原始可编辑 SVG 时才参考 `minimal_svg.py` 新建源，并明确 `source_preserving=false`。真实数据图必须直接读取原始表，保留行列定位；不得从像素反推测量值。多面板只修改工单指定面板，其他面板纳入 unchanged 审计。

## 合成最小示例

`examples/synthetic_case/` 全部为 **SYNTHETIC 合成示例**，不是正式答案。执行：

```bash
python3 scripts/run_case.py --input examples/synthetic_case/input \
  --work /tmp/source-surgery-work --output /tmp/source-surgery-output
```

真实生成编辑 SVG、PNG、PDF、变更记录、未变元素审计和 result；机器结束后为诚实 partial，等待原生目检。另可执行 `python3 scripts/validate_example.py` 验证 missing-ID 与 duplicate-ID 原子失败。`source_surgery.py` 是本 bundle 内部事务引擎，正式案例统一使用上述 `run_case.py` 标准入口。
