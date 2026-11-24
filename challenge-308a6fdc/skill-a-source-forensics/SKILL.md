---
name: source-forensics-kit
description: 当任务要求基于给定上游材料（PDF/CSV/Markdown/txt/图片等）进行学术写作或报告撰写、且必须证明"agent 真的读了真实文件、正文每条事实性论断都能解析回材料真实位置"时触发。核心能力：对 /input 材料做 SHA-256 哈希与 magic-bytes 类型嗅探并建库（manifest.json + 抽取回执 + 行/页锚点索引）；对交付稿做论断锚核验，抓出 ANCHOR-MISMATCH（锚位原文与论断无共同关键 token）与 UNANCHORED-CLAIM（含数字或"表明/显示"等事实线索却无锚的句子）；交付时 re-hash 全部输入给出完整性证明；按 case.json 的 output_contract 装配 result.json。红线：绝不臆造材料内容——无 pdftotext 时如实记 extractor_unavailable，图片/二进制记 non_text_material，扫描件记 no_text_layer；锚核验未通过（存在 ANCHOR-MISMATCH 或 UNANCHORED-CLAIM）不得宣称完成，必须补锚/删除/标【待确认】；result.json 不删契约字段，无内容填 "PENDING"。不适用于：无上游材料的纯创作、仅需文体润色或排版渲染的任务、需要 OCR/图片理解本身作为交付物的任务（本 skill 只标记缺口，不做 OCR）。
---

# source-forensics-kit：上游材料取证与锚定溯源

**定位一句话**：本 skill 不管写作过程管理、不管文体、不管渲染，只解决"上游数据真实性"——证明 agent 真的读了真实文件，且正文每条事实性论断都能解析到材料的真实位置（行锚 `M3:L42` / 页锚 `M1:p3`）。

## 运行契约

- 输入：`/input/case.json`（含 `case_id` 与 `output_contract`）、`/input/task.md`、若干材料文件（PDF/CSV/Markdown/txt/图片）。
- 工作目录：`/app/work`（放 manifest、receipts、anchor_index、抽取文本）。
- 输出目录：`/app/output`：交付稿 + `audit_report.md` + `result.json`。
- `result.json` 必须原样包含 `output_contract` 的全部字段（典型键：`case_id`、`deliverable`、`preserved_facts`、`evidence_map`、`change_log`），`case_id` 与输入原样一致；另含诚实的 `status`、`sources`、`uncertainty`、`integrity_check`、`change_log` 与 `forensics` 摘要。字段无内容填 `"PENDING"`，不删字段。
- 可编辑产物尽力渲染真实 PDF/PNG 预览；工具不存在时如实记录，不伪造。部分完成要如实说明限制。
- 执行预算：64 次模型请求 / 900 秒。脚本确定性、秒级完成，不占模型预算。

## 命令清单（可直接复制）

```bash
# 1. 取证建库（秒级）：manifest.json + receipts/ + anchor_index.json + extracted/
python3 /skills/weekly-skill/scripts/forensic_intake.py --input /input --work /app/work

# 2. 阅读 /app/work/extracted/ 下的抽取文本与 receipts，确定材料编号 M1、M2…
#    （图片/二进制材料在 receipts 中标为 non_text_material，需人工读图）

# 3. 写作：每条事实性论断句尾挂锚，如 "……提升了 12%[M2:L18]"
#    锚语法见 references/anchoring-protocol.md
mkdir -p /app/output
#    → 产出 /app/output/deliverable.md

# 4. 锚核验 + 完整性证明 + 装配 result.json（秒级）
python3 /skills/weekly-skill/scripts/anchor_audit.py \
  --work /app/work --input /input --case /input/case.json \
  --deliverable /app/output/deliverable.md --output /app/output

# 5. 若报告存在 ANCHOR-MISMATCH / UNANCHORED-CLAIM：修稿后重跑第 4 步直至 PASS。
#    CI 卡口可加 --strict（审计未通过或完整性失败时退出码 3）。
```

退出码约定：`0` 成功；`1` 硬失败（缺文件/坏 JSON）；`2` 输入目录为空（仅 intake）；`3` 审计未通过（仅 `--strict`）。

## 时间表（900 秒预算内）

| 时间 | 动作 |
|---|---|
| 0–5 min | 跑 `forensic_intake.py`，读 manifest 与 receipts，确认材料编号、类型、缺口 |
| 5–15 min | 读 `/app/work/extracted/` 抽取文本（行号/页号即锚），写带锚交付稿 |
| 15–25 min | 跑 `anchor_audit.py`，处理全部 ANCHOR-MISMATCH 与 UNANCHORED-CLAIM |
| 25–30 min | 复核 `audit_report.md` 与 `result.json`（status/uncertainty/完整性） |
| **≤35 min** | **必须交付一版**（即使 status=partial，也要如实写 uncertainty） |

## 异常处理

- **扫描件 PDF**：`pdftotext` 能跑但无文字层 → receipt 记 `no_text_layer`，result.json 的 uncertainty 公示，需人工阅读，不得臆造页内容。
- **加密/损坏 PDF**：`pdftotext` 返回非零 → 记 `extractor_error:<原因>`，同样如实公示。
- **无 pdftotext**：记 `extractor_unavailable`，PDF 内容一律不得引用为"已读"。
- **图片/zip/二进制**：记 `non_text_material`；正文若引用其内容，必须在 uncertainty 中说明"未经自动锚定"。
- **材料冲突**（两份材料数字打架）：两条论断分别挂各自锚，并在交付稿中标注冲突、在 `change_log` 记录取舍理由。
- **锚误报**：合法引用被判 ANCHOR-MISMATCH 时，按 references/anchoring-protocol.md 处理（改写论断句共享关键词、加区间锚、或标【待确认】）；不得为通过核验而编造锚。

## 最小示例

`examples/` 内含完整可跑的合成示例（合成数据，非真实科研数据、非正式案例结果）：

```bash
cd examples
python3 ../scripts/forensic_intake.py --input input --work /tmp/sf_work
python3 ../scripts/anchor_audit.py --work /tmp/sf_work --input input \
  --case input/case.json --deliverable output/deliverable.md --output output
```

详见 `examples/README.md`；锚语法与误报处理见 `references/anchoring-protocol.md`；方法细节与限制见 `references/method.md`。
