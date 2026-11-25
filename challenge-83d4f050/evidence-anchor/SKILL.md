---
name: evidence-anchor
description: 从真实论文 PDF、figure03、机制文字和原始数据构建“证据账本优先”的生物机制图与通路图；适用于要求每个实体、关系、数值和修改都可回溯到原文页码/图号/短引文的绘图、重绘或保源编辑任务，并以可编辑 SVG、PNG/PDF 预览和完整 result.json 交付。普通统计计算或非生物装饰插画不触发。
---

# Evidence Anchor：先闭合证据，再允许落笔

## 核心判断

图面不是文本标签的拼贴，而是带证据的机制陈述。主产物是 `claims.json + source_manifest.json`，SVG 只是其投影。先读实际 `figure03` 与图注，再核对正文；不要把领域常识写成论文事实，不从低质量转录文本猜内容。数据图必须从原始表文件取数，不从旧图像素反推数值。

## 运行契约

1. 首先枚举并阅读 `/input/case.json`、`/input/task.md`、实际论文/图件/数据以及存在的 `artifacts/figure-workorder.json`。PDF 用真实解析器提取；低置信度 OCR 只作旁证。
2. 在 `/app/work` 建工作文件，最终文件放 `/app/output`。先保存诚实的 partial `result.json`，再迭代改进。预算为 900 秒、64 次请求时，不追求装饰而牺牲证据闭合。
3. `result.json` 必须含输入 `case_id` 和 `case.json.output_contract` 的全部原始字段；通常包括 `case_id,status,editable_source,export_artifact,content_map,compliance_checks,exceptions`。不得删除平台追加字段。状态只能是 `success|partial|failed`，任何缺失导出、未解决冲突、失败检查均降为 partial/failed 并解释影响。
4. 安装后的技能一般为 `/skills/weekly-skill`；脚本路径始终相对本 `SKILL.md`，不要硬编码本机目录。需要 Python 3；SVG 生成仅用标准库。PNG/PDF 导出使用环境提供的 PyMuPDF（`import pymupdf`）；缺失会返回非零并诚实 partial，不伪报成功。

## 证据工作流

### A. 材料登记与 figure03 定位

逐文件登记路径、SHA-256、版本、角色和可用解析方式。找到 figure03 本体、图注、正文首次引用与相关补充材料，分别记录。每条证据采用：

```json
{"id":"E1","file":"paper.txt","locator":"paper.pdf p.6 Fig.3 legend","quote":"exact contiguous source sentence","evidence_type":"direct"}
```

`file` 为相对于 `/input` 的真实文本文件；原始 PDF 的 SHA-256 也要登记。引文须是逐字短摘，`locator` 必须使用原 PDF 页码、面板与图号。只有标题或 OCR 低置信度排版不能作为定论证据。

### B. 主张账本

读 `references/claims-schema.md`，将当前案例写为 `/app/work/claims.json`。每个实体、边、视觉编码都必须引用至少一个 `evidence_ids`。区分实体、复合物、细胞类型和区室；区分激活、抑制、结合、修饰、转运。结合不自动蕴含激活；相关性不自动蕴含因果。方向或区室不明时使用 `uncertain`，并列为 exception，不用灰虚线掩盖后仍宣称成功。

并行分支、反馈和跨膜转运逐项核对。数据编码必须链接原始文件、行/列和计算规则；手工录入的值只可作为待核数据，不能冒充原值。

### C. 渲染与回读

```bash
python3 "$SKILL_DIR/scripts/evidence_pipeline.py" \
  --input /input --work /app/work --output /app/output \
  --claims /app/work/claims.json
```

脚本执行引文回查（文本材料）、证据引用完整性、语义词表、SVG 可解析性和真实 PNG/PDF 导出。它不会替 Agent 判断论文生物学。返回码 0 表示机械检查通过，2 表示存在限制；均保留产物。`content_map` 自动把图面 ID 连接到引文与定位，`source_manifest.json` 保留来源哈希。

必须打开 PNG 目检：标签是否截断，箭头是否遮挡节点，区室和膜位置是否可读，所有关键实验条件是否误删。机械通过不等于科学正确。

### D. 保源编辑

如果工单针对既有 SVG，优先使用 `patch_svg.py`，按稳定元素 ID 修改，禁止整图重画：

```bash
python3 "$SKILL_DIR/scripts/patch_svg.py" --input /input/original.svg \
  --operations /app/work/operations.json --output /app/output/figure_edited.svg \
  --record /app/output/change_records.json
```

操作支持 `set_text,set_attribute,remove_element`，默认拒绝无匹配或多匹配 ID。变化必须来自工单/证据；未变元素以结构哈希抽查，原文件永不覆盖。编辑后重新导出与目检，并将日志加入 result。

### E. 数据图与多面板

先用原始 CSV/TSV/JSON 校验列名、行数、单位和过滤条件；再让每个标记/颜色/线宽对应明确单元格。统计变换写入 encodings，不把变换结果伪装成原始测量。若 figure03 含机制面板与数据面板，分别提取后用一致坐标和面板字母组合，panel 级 content_map 不可合并成一句“来自论文”。

## 完成门

- 每个可见关键实体、边、数值、面板与编辑均映射真实来源；无孤立证据 ID。
- SVG 保留真实 `<text>`、分层 `<g>` 和稳定 ID；PNG/PDF 真实生成且已目检。
- `compliance_checks` 只写实际执行结果；未执行的科学人工判断不能写成 pass。
- `exceptions` 区分材料缺失、科学歧义、工具失败；partial 明确“缺什么、影响什么、已交付什么”。

## 合成最小示例

`examples/` 全部是 **SYNTHETIC 合成示例**，不是固定案例或预写答案。执行 `examples/run_demo.sh`，或见 `examples/guide.md`。示例真实生成 SVG/PNG/PDF/source_manifest/result，另演示保源修改和失败证据回查。
