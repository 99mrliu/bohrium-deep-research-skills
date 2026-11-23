---
name: er-manifest-figure
description: 实体-关系清单驱动的科研机制图/关系示意图生成与编辑。当任务给出论文 PDF、文字描述或数据表，要求绘制机制图、通路图、结构关系图或流程图，并交付可编辑源文件（分层 SVG）、导出件（PNG/PDF）与可核验证据时使用。核心方法：不直接画图，先把来源材料编译成一份机器可核对的实体-关系清单 manifest.json（每个实体、每条关系都带来源定位与原文引句），再由确定性脚本把清单渲染为分层 SVG，最后用校验脚本把图与清单逐项对账（含反幻觉检查：图中任何文字都必须能追溯到清单）。编辑 = 改清单重渲染，天然保源。不适用：纯统计图表的数值计算（用数据绑定类工具）；海报/插画等艺术设计；材料中确实没有足够信息时的凭空补图。
---

# er-manifest：清单驱动的机制图生成与保真校验

## 解决什么问题

Agent 画机制图的典型失败：抑制画成激活、上下游颠倒、包含画成并列、图里出现来源
材料中不存在的基因名/浓度/时间点。根因是"看着材料直接画"，图面对象与来源断言
之间没有可核对的中介。本 Skill 在两者之间插入一份**实体-关系清单 manifest**：

```
来源材料 (PDF/文本/表格)
   │  人工抽取 + 引句定位（Agent 的科学判断）
   ▼
manifest.json  ──verify──►  对账报告（每个图面元素 ↔ 清单 ↔ 来源引句）
   │  render（确定性脚本，零自由发挥）
   ▼
分层可编辑 SVG ──export──► PNG(300dpi) / PDF + 导出报告
```

图的正确性由"清单与来源的对应"和"图与清单的对账"两步分别保证；渲染脚本不含
任何科学判断，因此**改数据/改关系只改清单，图自动同步**。

## 运行环境契约（平台固定案例）

1. 输入在 `/input/`：`case.json`（含 `case_id`、`output_contract`、材料清单）、
   `task.md`、材料本体（PDF/CSV/图片等）。**先读真实文件**，不要凭文件名猜测内容。
   `environment/resources.yaml`（若在 `/input/` 或 `/app/` 下存在）列出可用工具，
   先用 `which`/`python3 -c "import ..."` 探测后端。
2. 中间产物放 `/app/work/`，最终交付放 `/app/output/`。
3. `/app/output/result.json` 必须包含 `case_id` 以及 `output_contract` 声明的
   **全部原始字段**（逐键对齐，缺键写 `null` 并在 `uncertainty` 说明原因），
   另附 `status`、`sources`、`uncertainty`、`change_log`。
4. 交付物必须含：可编辑源文件（分层 SVG）+ 导出件（PNG/PDF）+ 真实渲染的
   PNG/PDF 预览 + 校验/导出报告。部分完成时保存诚实的状态与限制说明，
   **先存可用的部分结果，再迭代改进**。
5. 预算约束：约 64 次模型请求 / 900 秒。清单抽取最多两轮精读，渲染与校验全部
   交给脚本，不要手写 SVG。

## 工作流（严格按序）

### 步骤 0：建目录、读任务、探测工具

```bash
mkdir -p /app/work /app/output
cat /input/case.json        # 记录 case_id、output_contract 全部键、材料路径
cat /input/task.md
python3 -c "import sys; print(sys.version)"
```

### 步骤 1：精读来源，填写实体-关系清单

- PDF 用 `pdftotext -layout`（或平台 PDF 工具）抽文本；图表数据直接读数据文件。
- 按 `resources/manifest_schema.md` 的格式写 `/app/work/manifest.json`。
- **每一条 entity / relation 必须带 `evidence.locator`（页码/段落/表号）和
  `evidence.quote`（原文短引句）**。找不到出处的内容一律不进清单。
- 关系类型只能取自 `resources/relation_vocabulary.md` 的受控词表
  （activates / inhibits / binds / produces / degrades / translocates /
  modifies / contains / unclear）。方向存疑时用 `unclear` 并在
  `manifest.uncertainty` 里写明——**禁止猜方向**。
- 包含/分组关系用 `groups`（容器嵌套），不要画成并列框。
- 布局：给每个实体一个 `grid: {col, row}`（列=层级/时序，行=并列分支）即可，
  像素坐标由脚本算；复杂图可加 `box` 精调。

### 步骤 2：确定性渲染为分层 SVG

```bash
python3 /skills/weekly-skill/scripts/render_manifest.py \
  --manifest /app/work/manifest.json \
  --svg /app/output/figure.svg \
  --report /app/work/render_report.json
```

脚本负责：网格→坐标、分组容器、按关系类型出箭头（activates=箭头、
inhibits=T 形抑制符、binds=连线圆点等）、自动图例、分层分组
（background/groups/relations/entities/labels/legend，Inkscape 可识别）、
每个元素带稳定 id（`ent-*` / `rel-*`）和 `data-*` 校验属性。渲染报告列出
布局警告（重叠、出界）。

### 步骤 3：图-清单对账（含反幻觉门禁）

```bash
python3 /skills/weekly-skill/scripts/verify_figure.py \
  --manifest /app/work/manifest.json \
  --svg /app/output/figure.svg \
  --out /app/output/verification_report.json
```

校验项：清单中每个实体/关系在图中恰好出现一次且端点、类型、方向一致；
图中每段可见文字都能追溯到清单（标题、实体标签、边标签、图例、声明过的
注释），出现清单之外的文字即判 fail；每条实体/关系都有非空来源定位。
**fail 时必须回到步骤 1 或 2 修正，不得带病交付。**

### 步骤 4：导出与预览

```bash
python3 /skills/weekly-skill/scripts/export_preview.py \
  --svg /app/output/figure.svg \
  --outdir /app/output --basename figure --dpi 300 \
  --report /app/output/export_report.json
```

脚本按 cairosvg → rsvg-convert → inkscape → chromium → ImageMagick 顺序探测
导出后端，生成 PNG(指定 dpi) 与 PDF，并核验导出件尺寸/文件头；失败项如实写进
`export_report.json` 的 `failures`，不得谎报。若 PNG 与 PDF 都失败，SVG 本体
仍须交付，并在 `result.json` 的 `uncertainty` 中说明导出环境缺失。

### 步骤 5：编辑（源保留式修改）

改图 = 改 `manifest.json` 中对应条目（保留其余条目与 evidence），重跑步骤 2–4。
把每次改动追加到 `/app/output/change_log.json`：`{ts, target, before, after,
reason, source}`。不要手改 SVG 后再改清单造成双源漂移——清单是唯一事实源。

### 步骤 6：写 result.json

按 `output_contract` 逐键填写；`sources` 列出每个关键元素的来源定位；
`status` ∈ {complete, partial, failed}；`uncertainty` 写明方向存疑的关系、
材料缺失处、导出失败项。

## 异常处理

| 情况 | 处置 |
|-|-|
| 材料缺失/无法解析 | result.json 记 `status:"failed"` + 原因；不编造内容 |
| 来源描述互相矛盾 | 两处引句都记入 `uncertainty`，关系类型用 `unclear` |
| 关系方向读不出 | `unclear` 类型 + uncertainty 说明，禁止默认按激活画 |
| 校验 fail | 回到清单修正后重渲染；三次不过则在 result.json 声明 partial |
| 导出后端全部缺失 | 交付 SVG + 如实报告；尝试浏览器截图兜底 |
| 实体过多图面拥挤 | 增大 canvas 或拆子图（manifest.subfigures），不缩字号到 8pt 以下 |

## 资源清单

- `scripts/render_manifest.py`：清单→分层 SVG（纯标准库，无第三方依赖）。
- `scripts/verify_figure.py`：图-清单对账 + 反幻觉门禁（纯标准库）。
- `scripts/export_preview.py`：多后端 PNG/PDF 导出 + 导出件核验（纯标准库，
  后端缺失时如实降级）。
- `resources/manifest_schema.md`：清单字段规范与完整示例。
- `resources/relation_vocabulary.md`：受控关系词表、图形语法与方向规则。
- `examples/minimal_example.md`：一组**示意**输入→清单→输出说明（非正式案例结果）。

## 边界与维护

清单的规模上限约 60 实体 / 80 关系（超出请拆子图）；自动布局只保证分层可读，
精细排版用 `box` 覆盖；脚本不做统计计算。版本：v1.0（2026-11）。
