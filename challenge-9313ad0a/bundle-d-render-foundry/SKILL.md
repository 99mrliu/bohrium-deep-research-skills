---
name: render-foundry
description: 当需要将科研思维导图以多种可编辑格式（FreeMind/OPML/Markdown/Mermaid/Markmap HTML）确定性导出、生成真实 PNG/PDF 预览并完成 .mm 往返校验时使用本技能；适用于下游交付与人工审阅环节。
---

# render-foundry：思维导图多格式交付与预览渲染

## 何时使用

本技能面向思维导图构建流程的**下游交付环节**：上游（无论人工整理抑或其他技能）已产出符合输入模式的 `mindmap.json`，需要将其转换为可被常见思维导图工具直接导入编辑的文件、生成可供人工检查的确定性版面预览，并以自动化往返校验保证导出内容与原图严格一致。

典型适用场景：

- 将文献调研、研究规划、实验设计等思维导图交付给使用 FreeMind、Freeplane、XMind、大纲工具或 Mermaid/Markmap 生态的协作者；
- 评审或归档场景下需要一份真实渲染的 PNG/PDF 预览以检查版面可读性；
- 需要字节级可重现的导出结果（同一输入在任何重跑中产生逐字节一致的文本输出），以支持差异审查与版本管理。

不适用场景：

- 上游尚未形成结构化 `mindmap.json`，需要从原始文献自由抽取构图（属上游构图技能职责）；
- 需要交互式在线协作编辑（本技能产出静态交付物）；
- 图规模超过数百节点且要求自动美化排版（确定性整齐树布局在超大图上版面效率有限，见“限制”）；
- 需要精确复刻某商业工具专有样式（颜色主题、图标库等不在交付范围）。

## 固定运行方式

运行时契约：评测环境提供 `/input/case.json` 与 `/input/task.md` 及素材文件；处理过程在 `/app/work` 下进行；最终交付物置于 `/app/output`，其中必须包含 `result.json`，其须保留原始 `case_id`、包含案例 `output_contract` 所指定的全部字段、如实标注状态（完整/部分完成须尽早声明）、来源与证据、不确定性列表及变更记录。本技能的三个脚本均以此为前提组织输入输出：

```bash
# 1. 多格式导出（纯标准库）
python3 scripts/emit_formats.py --map mindmap.json --outdir OUT

# 2. 确定性预览渲染（matplotlib，缺失时优雅降级）
python3 scripts/render_preview.py --map mindmap.json --outdir OUT

# 3. .mm 往返一致性校验（纯标准库；一致退出 0，不一致退出 1）
python3 scripts/roundtrip_check.py --map mindmap.json --mm OUT/mindmap.mm \
    --report OUT/roundtrip_report.json
```

输入模式（`mindmap.json`）：

```json
{
  "root": "<id>",
  "nodes": [
    {"id": "<id>", "parent": "<id 或 null>", "label": "<文本>",
     "kind": "<类别>", "note": "<可选备注>"}
  ],
  "relations": [
    {"from": "<id>", "to": "<id>", "type": "<关系类型>", "note": "<可选>"}
  ]
}
```

约束：根节点 `parent` 为 `null`，其余节点 `parent` 必须指向已存在的 `id`；`id` 全局唯一；`relations` 端点必须存在。未知顶层字段（如 `_meta`）被忽略，可用于标注数据来源。

## 工作流程

1. **校验与载入**：检查模式合法性（根存在、父引用闭合、关系端点存在、id 唯一）；不合法即以退出码 2 报错并终止，不产出半成品。
2. **多格式导出**：以 id 字典序稳定排序子节点，依次导出五种格式（见下节）。相同输入产生字节级一致输出；同案例重跑可安全覆盖。
3. **预览渲染**：按确定性整齐树算法布局并渲染 PNG/PDF，同时写入 `render_manifest.json`（工具版本、字体选择、节点/关系数、画布尺寸、状态）。
4. **版面检查（强制）**：打开 PNG 目视检查：不得出现文本重叠、标签裁剪、关系线压字、CJK 字符缺字（豆腐块）。发现问题必须通过重平衡标签/树结构修复，不得静默交付不可读预览。
5. **往返校验**：将 `.mm` 解析回 `(id, label, parent)` 三元组与 `(from, to)` 关系集合，与源 `mindmap.json` 严格比对；`match=true` 方可视为导出可信。不一致时退出码为 1，报告列明差异。
6. **汇总交付**：将全部文本输出与预览纳入 `/app/output`，在 `result.json` 中登记产物清单、校验结果、字体回退情况与不确定性。

## 输出物说明

| 文件 | 格式 | 用途与导入目标 |
| --- | --- | --- |
| `mindmap.mm` | FreeMind XML | **主可编辑交付物**。FreeMind 直接打开；Freeplane「文件→打开」；XMind「文件→导入→FreeMind」。保留节点 ID、备注（rich_content）与 arrowlink 关系。 |
| `mindmap.opml` | OPML 2.0 | 大纲交换格式。可导入 OmniOutliner、Workflowy、Dynalist、Logseq 及多数大纲/笔记工具；备注置于 `_note` 属性。 |
| `mindmap.md` | Markdown 大纲 | 纯文本审阅、版本管理与粘贴入文档；亦可被 Markmap、Obsidian 等消费。 |
| `mindmap.mmd` | Mermaid `mindmap` | 嵌入支持 Mermaid 的 Markdown 环境（GitHub、GitLab、Typora、Obsidian 等）直接渲染。 |
| `mindmap.html` | 自包含 Markmap 页 | 浏览器直接打开：在线时经 CDN 加载 markmap-autoloader 渲染交互图；离线时静态嵌套列表完整可读，并内嵌原图 JSON 供程序化复用。 |
| `mindmap.png` / `mindmap.pdf` | 预览图 | 人工版面检查与归档。**运行时产物，不入技能包。** |
| `render_manifest.json` | 渲染清单 | 记录 Python/matplotlib 版本、CJK 字体请求序列与实际选中、画布尺寸、状态（`rendered` / `skipped_no_matplotlib`）。 |
| `roundtrip_report.json` | 校验报告 | `.mm` 往返比对结果；`match` 为 true 表示逐字段一致。 |

## 异常处理表

| 异常 | 行为 |
| --- | --- |
| matplotlib 缺失 | `render_preview.py` 捕获 `ImportError`，仅写 `render_manifest.json`（`status=skipped_no_matplotlib`），退出码 0，不中断流程；其余文本交付物不受影响。 |
| CJK 字体缺失 | 按固定候选序列扫描 matplotlib 字体库；全部缺失时仍以默认字体渲染，manifest 中 `font.chosen=null`、`font.fallback=true`，并在 `result.json` 不确定性中声明中文可能无法正确显示。 |
| 标签过长 | 列间距由全局最长标签推导（`spacing = 0.32 × 最大长度 + 2.0`，下限 3.0）；若目视检查仍发现溢出，应缩短标签或拆分节点后重跑。 |
| 节点爆炸导致版面不可读 | 画布尺寸随节点数增长；发现重叠/过密时不得交付，应通过折叠子树、分层拆图（多张子图分别导出）修复。 |
| XML 特殊字符 | 属性与文本统一经 `xml.sax.saxutils.escape` 处理（含引号、`&`、尖括号）；往返校验保证转义可逆。 |
| Mermaid 保留字 | 裸标签中的 `()`、`[]` 替换为全角等价字符 `（）［］`，避免与 `root((...))` 等语法冲突；其他特殊字符引发的渲染失败应在 Mermaid 目标环境中复核。 |
| 同案例重跑确定性 | 全部文本输出字节级确定（稳定排序、无时间戳、无随机性）；重跑可直接覆盖比对。PDF 已去除创建时间元数据。 |

## 最小合成示例说明

`examples/synthetic-input/mindmap.json` 为**合成示例**（虚构课题「催化剂Q研究规划」，14 节点、3 层、2 条备注、3 条类型化关系，不代表任何真实研究内容）。`examples/synthetic-output/` 收录其真实导出的全部**文本**产物与两份 JSON 报告（`roundtrip_report.json` 中 `match=true`）。`mindmap.png` 与 `mindmap.pdf` 属运行时产物且为二进制，**不入包**；其已在构建时于临时目录生成并目视检查通过（版面无重叠、CJK 渲染正确、字体选中 PingFang SC），复现方式见 `examples/README.md`。

## 限制

- 布局为单棵整齐树，`relations` 仅以弧线叠加表达，交叉关系极多时视觉噪音不可避免；
- 文本宽度以字符数近似估计，极端混排（长英文串与 CJK 混合）下间距可能偏保守；
- HTML 内嵌 Markdown 模板不支持标签中出现 `</` 序列（会提前闭合 `<script>`），输入含此类内容时须先行改写；
- 字体选择依赖运行时环境已安装的字体，跨机器渲染字形可能不同（manifest 已记录实际选择以供审计）；
- `.mm` 中 arrowlink 不携带关系类型文本（FreeMind 格式限制），类型信息完整保留于 `.md`、`.html` 与预览图中；
- 预览确定性限于同一运行环境；不同 matplotlib 版本的字重与抗锯齿可能存在细微差异。
