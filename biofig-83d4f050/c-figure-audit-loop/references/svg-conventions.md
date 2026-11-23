# SVG 约定（审计器依赖的机器可读结构）

本技能的所有产出 SVG（无论是 `scripts/mini_svg_builder.py` 生成，还是智能体手写）
都必须遵守下列约定。审计器**优先读取 `data-*` 属性**；仅在缺失时才退化到
marker/样式启发式推断，并对推断结果记 warning（绝不静默猜测）。

## 分层（layer groups）

```xml
<svg xmlns="http://www.w3.org/2000/svg" width="..." height="..." viewBox="...">
  <defs> …marker 定义… </defs>
  <g id="layer-compartments"> … </g>
  <g id="layer-edges"> … </g>        <!-- 先画边，节点盖住线头 -->
  <g id="layer-entities"> … </g>
  <g id="layer-legend"> … </g>
</svg>
```

## 实体（entity）

```xml
<g id="entity:RTK" class="entity"
   data-entity-type="protein"        <!-- gene|protein|complex|small_molecule|cell_type|other -->
   data-compartment="membrane"
   data-source="paper p.7 Fig.3B">   <!-- 来源定位，来自 claims -->
  <rect class="entity-box" x=".." y=".." width=".." height=".." fill="#dceaf7"/>
  <text class="entity-label" ...>RTK</text>   <!-- 基因斜体 font-style="italic"，蛋白正体 -->
</g>
```

## 边（edge）

```xml
<g id="edge:e2" class="edge"
   data-edge-kind="activates"        <!-- activates|inhibits|binds|phosphorylates|
                                           ubiquitinates|transports|recruits|modifies -->
   data-from="RTK" data-to="ADAPTOR" <!-- 方向：from=调控源, to=靶（箭头/T杠端） -->
   data-evidence="confirmed"         <!-- confirmed|uncertain；uncertain 必须虚线 -->
   data-source="paper p.8 ¶2">
  <line class="edge-line" x1=".." y1=".." x2=".." y2=".."
        marker-end="url(#marker-activates)"/>
  <!-- 磷酸化/泛素化在边中点加徽章： -->
  <circle class="edge-badge-bg" .../><text class="edge-badge">P</text>
</g>
```

Marker 约定（定义在 `<defs>`）：

| kind            | marker id           | 视觉语义           |
|-----------------|---------------------|--------------------|
| activates       | `marker-activates`  | 实心箭头           |
| inhibits        | `marker-inhibits`   | T 形杠（红色）     |
| binds           | 无 marker           | 无箭头直线（结合） |
| phosphorylates  | `marker-arrow` + 徽章 `P`  | 箭头+磷酸化徽章 |
| ubiquitinates   | `marker-arrow` + 徽章 `Ub` | 箭头+泛素化徽章 |
| transports/recruits/modifies | `marker-arrow` | 空心/实心箭头 |

证据语义：`data-evidence="uncertain"` ⇔ `stroke-dasharray="6,4"`（虚线）。
**方向或效应在材料中没有依据时，必须标 `uncertain`，不得编造确定性。**

## 图例（legend）

```xml
<g id="layer-legend">
 <g id="legend">
  <rect class="legend-frame" .../>
  <g id="legend-swatch:log2FC_low" class="legend-item">
    <rect class="swatch" x=".." y=".." width="18" height="14" fill="#2166ac"/>
    <text class="legend-label">log2FC_low: log2FC = -2 (down)</text>
  </g>
  …
 </g>
</g>
```

* 每个图例项一个 `legend-swatch:<item>` 组；`<item>` 必须与 claims.legend[].item 完全一致。
* 像素审计器通过该 id 定位色块区域采样，与 `claims.color_checks[].expect_color_hex` 比对。

## 区室（compartment）

```xml
<rect id="compartment:cytosol" class="compartment-band" .../>
<text class="compartment-label">cytosol</text>
```

跨膜实体放在 `membrane` 带；跨区室的边直接画直线跨越带边界即可。

## 命名与可审计性要点

1. 所有 id 全局唯一；实体/边/图例项 id 前缀分别是 `entity:` / `edge:` / `legend-swatch:`。
2. `data-source` 携带 claims 中的来源定位（页码/图号/数据文件行），审计违例回溯用。
3. 不嵌入栅格 `<image>`（编辑性启发式检查会报 warning）。
4. `font-family` 只用通用族（sans-serif / serif / monospace / Arial / Helvetica /
   DejaVu * 等，见 `svg_conventions.GENERIC_FONT_FAMILIES`）。
5. 编辑类 case：编辑前后 SVG 的 id 必须保持稳定，否则 `audit_edit_diff.py`
   会把重命名误判为 删除+新增。
