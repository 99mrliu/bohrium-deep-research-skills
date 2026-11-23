# 审计细则（Audit Rubric）

每条审计列出：检查内容 / 通过标准 / 严重级 / 典型修复。
严重级：**error**（阻断，必须修复或如实进入 result.json exceptions）、
**warning**（应修复；不修复必须说明）、**skipped**（审计器或工具缺失，
**绝不算通过**，必须在 result.json 中注明）。

## 1. audit_svg_parse（SVG 回解析）

| 检查 | 内容 | 通过标准 | 严重级 | 典型修复 |
|---|---|---|---|---|
| parse | SVG 可被 xml.etree 解析 | 无 ParseError | error（致命，后续审计无法运行） | 修正 XML；不要手写拼接，改用 ElementTree |
| graph | 抽取实体/边/图例/文本 | figure_graph.json 生成 | — | — |

## 2. audit_semantic_diff（主张表 ↔ 图面一致性，核心审计）

| 检查 | 内容 | 通过标准 | 严重级 | 典型修复 |
|---|---|---|---|---|
| entity.missing | claims 实体在图中存在 | 每个 claims entity id 都有 `entity:<id>` | error | 补画实体，或从 claims 删除（须有依据） |
| entity.extra | 图中实体都在 claims 中 | 无未声明实体 | warning | 补 claims 条目（带来源）或删除图元 |
| entity.label_mismatch | 图面标签 == claims 标签 | 完全一致 | error | `rename-label` |
| entity.label_not_in_text | 标签出现在 `<text>` 中 | 可见文本含该标签 | error | 标签被路径化/栅格化？重加文本 |
| entity.compartment_mismatch | 区室一致 | data-compartment == claims | warning | 移动实体或更正 claims |
| edge.missing | claims 边在图中存在 | `edge:<id>` 存在 | error | 补画边 |
| edge.direction_reversed | 方向未反 | from/to 不互换 | error | `swap-edge-direction` |
| edge.endpoint_mismatch | 端点正确 | from/to 与 claims 一致 | error | `set-edge-endpoints` |
| edge.kind_mismatch | 语义一致（激活/抑制/结合…） | data-edge-kind == claims.kind | error | `set-edge-kind` |
| edge.evidence_mismatch | 证据强度一致（虚线语义） | confirmed/uncertain 一致 | warning | `set-edge-evidence` |
| edge.badge_missing | P/Ub 徽章存在 | 磷酸化有 P、泛素化有 Ub | warning | `set-edge-kind` 自动补徽章 |
| edge.endpoints_unreadable | 方向可机器核验 | data-from/to 存在 | warning | 补 data 属性 |
| legend.missing_item | 图例项齐全 | 每个 claims.legend item 有 `legend-swatch:<item>` | error | `add-legend-item` |
| legend.extra_item | 图例无未声明项 | — | warning | 补 claims 或删项 |
| expected_label.missing | 关键标签渲染 | expected_labels ⊆ 图面文本 | error | 补文本 |

## 3. audit_pixels（PNG 像素探针）

| 检查 | 内容 | 通过标准 | 严重级 | 典型修复 |
|---|---|---|---|---|
| png.openable | PIL 可解码 | 打开成功 | error | 重新导出 |
| png.dimensions | 尺寸合理 | 短边 ≥100px，纵横比与 SVG 差 ≤5% | error | 导出时匹配画布 |
| png.nonempty | 非空白 | 不同颜色数 ≥6 | error | 渲染失败，检查导出器 |
| png.background | 背景非异常暗 | 四角中位亮度均值 ≥80 | warning | 背景设为白色 |
| color.check | 颜色断言 | 采样色与 expect_color_hex 每通道差 ≤24 | error | `set-fill` 修正色块/节点填充 |
| ocr.key_labels | OCR 检出关键标签 | tesseract 存在时前 3 个 expected_labels 可检出 | warning | 字号过小/对比度低；tesseract 缺失 → **skipped，不算通过** |

## 4. audit_exports（导出质量）

| 检查 | 内容 | 通过标准 | 严重级 | 典型修复 |
|---|---|---|---|---|
| artifact.exists | 声明产物存在且非琐碎大小 | svg≥400B/png≥2KB/pdf≥800B | error | 重新导出 |
| png.dpi | 分辨率元数据 | dpi ≥150；无元数据 → warning | warning | 导出时 dpi=300 |
| pdf.structure | 页数/MediaBox | ≥1 页且 MediaBox 可解析 | error/warning | 重新导出 |
| pdf.fonts_embedded | 字体全部嵌入 | pdffonts 全部 emb=yes | error；pdffonts 缺失 → **skipped** | 换导出器或嵌入字体 |
| pdf.text_present | 文本层存在 | pdftotext 抽取非空 | warning；pdftotext 缺失 → **skipped** | 不要轮廓化文本 |
| svg.wellformed | XML 合法 | 解析成功 | error | 修正 XML |
| svg.raster_embedded | 无栅格 `<image>` | 0 个 | warning | 重画为矢量 |
| svg.fonts_generic | 通用字体族 | 均在白名单 | warning | 改 font-family |

## 5. audit_edit_diff（编辑类 case 的前后对拍）

| 检查 | 内容 | 通过标准 | 严重级 | 典型修复 |
|---|---|---|---|---|
| edit.target_unchanged | 声明要改的元素确实改了 | changed_elements 全部有差异 | error | 编辑未生效，重做 |
| edit.sample_changed | 声明不动的元素没变 | unchanged_sample 全部字节级一致 | error | 回滚误改 |
| edit.unexpected_change | 无计划外改动 | changed/added/removed ⊆ changed_elements | error | 回滚或把改动如实声明进 claims |
| edit.missing_element | 期望元素仍存在 | id 未丢失 | error | 保持 id 稳定 |

无 edit_expectations 时：全部差异以 warning 列出，由智能体人工核对并说明。

## 诚实性规则（不可违反）

1. **skipped ≠ passed**：工具缺失（pdffonts/tesseract/PIL/matplotlib）导致的跳过，
   记入 audit_report.json 的 skipped 列表，并抄入 result.json 的 compliance_checks
   （result: "skipped"）或 exceptions。
2. **违例不静默丢弃**：修复循环结束后仍存在的违例，逐条进入 result.json exceptions。
3. **无据不断言**：方向/效应在材料中无依据 → evidence="uncertain"（虚线），
   不得画成确定箭头。
4. **数值可溯源**：任何编码数值（如 log2FC）必须在 content_map 中给出数据定位。
5. **审计器自身失败**：以 warning（auditor.crashed）上报，绝不视为通过。
6. **status 诚实**：exceptions 非空时 status 不得为 success（build_result.py 会自动降级）。
