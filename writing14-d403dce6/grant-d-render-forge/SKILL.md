---
name: grant-d-render-forge
description: 把基金申请书章节稿交付为可编辑文件集（Markdown 母稿 + 标准库生成的 DOCX + 真实渲染 PDF/PNG 预览 + 版本间修改记录 + 按 output_contract 装配的 result.json）。Use when 需要把写好的章节稿落成可编辑交付物、生成真实渲染预览、记录版本差异或装配/校验 result.json 时。
---

# grant-d-render-forge：章节稿交付工程（可编辑交付物、真实预览、版本差异、合同化装配）

## 运行契约

先读 `/input/case.json` 与 `/input/task.md`；可能存在 `/input/organizer-workorder.json` 与 `environment/resources.yaml`，一并读取。`output_contract` 的字段清单**运行时从 case.json 读取，不得硬编码**。工作目录 `/app/work`，最终产物与可编辑稿件归 `/app/output`，其中必须有 `result.json`：含原始 `case_id`、全部 output_contract 字段、诚实的 `status`（success/partial/unable_to_determine/refused）+ 原因 + sources + uncertainty。材料清单一出来就先落诚实的 partial，再就地迭代改进；预算 64 次模型请求 / 900 秒。只依据实际读到的材料（PDF 用 pdftotext 实读），绝不按文件名或领域标签补造内容；组织方已声明申请人证据缺失时按缺失处理，列缺口清单。

## 聚焦问题

基础 Agent 的典型失败：章节稿只出现在对话框里，不落可编辑文件；没有渲染预览，排版无法目检；改稿无差异记录，申请人无法审查改动；result.json 字段与案例自己的 output_contract 不符或自报 success。本 Skill 把"交付"合同化：每份交付物有生成脚本、验收退出码与诚实降级路径。

## 工作流程

1. **读合同**：解析 case.json，取出 `case_id` 与 `output_contract` 字段清单；对照 `references/delivery_contract.md` 确定应交付物（母稿/docx/预览/change_record/result.json）。
2. **落母稿**：章节稿写为 `/app/output/draft_v1.md`（UTF-8 Markdown，用本 Skill 支持的子集，见 `references/format_mapping.md`）；材料缺失处写 `【待申请人确认：…】` 占位。
3. **改稿循环**：每次修订另存 `draft_v2.md`、`draft_v3.md`……不覆盖旧版；定稿版本记为 vN。
4. **生成修改记录**：`python3 scripts/version_diff.py draft_v1.md draft_vN.md -o /app/output/change_record.md`；按 `references/change_record_guide.md` 为各小节变更补写理由（只许引用材料/工单）。
5. **生成可编辑 DOCX**：`python3 scripts/md2docx.py /app/output/draft_vN.md /app/output/draft_vN.docx`；退出码非 0 时按 `references/ooxml_minimal.md` 排错，不得跳过校验直接交付。
6. **生成真实预览**：`python3 scripts/make_previews.py /app/output/draft_vN.docx --outdir /app/output`；读 `preview_status.json`：status=ok 才可声称"已附预览"；degraded 时把缺失工具与未生成产物写进 result.json 的 uncertainty，绝不伪造预览图。
7. **装配结果**：`python3 scripts/assemble_result.py --case /input/case.json --outdir /app/output --status <四态> --reason "…" --source "…" --uncertainty "…" --deliverable draft_vN.md --deliverable draft_vN.docx --deliverable change_record.md … --set change_records='"change_record.md"'`；deliverable 只列真实存在的文件（脚本强制校验）。
8. **终检**：`python3 scripts/assemble_result.py --validate --case /input/case.json --outdir /app/output`；退出码 0 才结束任务，否则按报告逐项修复。

## 事实与来源红线（四态标注）

- **已完成**[申请人，有材料证据]：标注材料出处，可写入研究基础。
- **外部工作**[原论文/既有成果，归外部作者]：引述时标明归属，不得写成申请人成果。
- **拟开展**[本研究计划]：计划、拟采集数据、拟建模型一律标"拟"。
- **待确认**[材料缺失需人工确认]：以 `【待申请人确认：…】` 占位，列入 uncertainty 与 change_record 人工确认项。
- 不新增材料之外的事实；引用无法核实标"未核验"；禁用"首次/国际领先/填补空白"式断言。

## 异常处理表

| 异常 | 处理 |
| --- | --- |
| PDF 加密/无文本层 | 尝试渲染+OCR；仍不可读则声明不可读，相关内容按缺失处理并落 partial |
| 材料缺失 | `【待申请人确认：…】` 占位 + 缺口清单进 uncertainty + 人工确认项 |
| 材料冲突 | 两说并存并各自注明出处，不擅自取舍；列入 uncertainty |
| 超长输入 | 先抽骨架（标题/表格/结论句），按预算分段精读；截断处声明 |
| 格式冲突（案例要求与默认模板不符） | 以案例 task.md 与 output_contract 为准，模板降级为参考 |
| 七要素清单与默认不同 | 以案例给定清单为准，element_mapping 逐条对应案例要素 |
| soffice/pdftoppm 缺失 | make_previews.py 诚实 degraded（退出码 0），缺失信息进 uncertainty；--strict 场景退出码 1 |
| docx 校验失败 | 按 references/ooxml_minimal.md 排错后重生成；校验不通过不交付 |
| result.json 校验失败 | 按 --validate 报告逐项修复；缺字段宁填【缺失：待补充】占位并 partial，不得留空或自报 success |

## 脚本与资源清单

| 路径 | 功能 | 退出码语义 |
| --- | --- | --- |
| `scripts/md2docx.py 输入.md 输出.docx` | 标准库 zipfile 手写最小 OOXML（含中文字体声明 SimSun/标题 SimHei），生成后复读校验 | 0 通过；1 读写/校验失败；2 参数错误 |
| `scripts/make_previews.py 输入.docx --outdir 目录 [--strict]` | 探测 soffice/pdftoppm 真实渲染 PDF/PNG；缺失写 preview_status.json 诚实降级 | 0 ok 或 degraded；1 错误或 strict 下降级；2 参数错误 |
| `scripts/version_diff.py 旧.md 新.md -o change_record.md` | unified diff（上下文 2 行）+ 变更统计 + 按小节归组 + 人工确认项清单 | 0 成功；1 读取失败；2 参数错误 |
| `scripts/assemble_result.py --case case.json --outdir /app/output [选项] [--validate]` | 按 output_contract 装配/校验 result.json，deliverables 存在性强校验，幂等 | 0 装配成功/校验通过；1 错误或校验不通过；2 参数错误 |
| `references/delivery_contract.md` | 交付物清单、命名约定、验收标准、案例格式要求映射 | — |
| `references/ooxml_minimal.md` | 最小 docx 部件清单与损坏原因排错索引 | — |
| `references/format_mapping.md` | Markdown→DOCX 样式映射与不支持项标注约定 | — |
| `references/change_record_guide.md` | 修改记录四部分写法与反模式 | — |

最小示例（合成示例，非正式案例结果，见 `examples/README.md`）：

```bash
python3 scripts/md2docx.py examples/draft_v2.md draft_v2.docx
python3 scripts/make_previews.py draft_v2.docx --outdir previews
python3 scripts/version_diff.py examples/draft_v1.md examples/draft_v2.md -o change_record.md
python3 scripts/assemble_result.py --case examples/case.json --outdir . \
    --status partial --deliverable draft_v2.docx --validate
```

## 版本与维护

- 版本：1.0.0（2026-11）。
- 依赖：Python 3（仅标准库）；soffice（LibreOffice）与 pdftoppm（poppler）为可选探测项，缺失时诚实降级而非报错。
- 适用范围：基金申请书章节稿的交付工程；Markdown 子集以外的排版（页眉页脚、图片、公式、上下标格式）不在 docx 生成范围内，由申请人在 Word 中完成。
- 确定性：md2docx 固定 zip 时间戳、version_diff 固定上下文行数、assemble_result 键排序无时间戳；同输入二次运行字节一致。
